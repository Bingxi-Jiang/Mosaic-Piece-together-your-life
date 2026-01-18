import os
import json
import time
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple

from PIL import Image
from google import genai
from google.genai import types


# =======================
# Global Configuration
# =======================

# 1) Gemini API Key: 直接把你的 key 粘贴到这里（不再用环境变量）
GEMINI_API_KEY = "AIzaSyAi8N4Jv8-wCi9iSQDjm8vSe8BVoJhdPyE"

# 2) 截图根目录与时间区间信息
SCREENSHOT_ROOT = "screenshots_test"
TIMEZONE_NAME = "America/Los_Angeles"

# 3) 截图间隔（分钟）：写入输出 + 合并 segment 用
CAPTURE_INTERVAL_MINUTES = 15

# 4) Gemini 模型
GEMINI_MODEL = "gemini-3-flash-preview"  # 或 "gemini-3-pro-preview"

# 5) 控制 token/成本：启用图像预处理（缩放 + 压缩）
ENABLE_PREPROCESS = True

# 预处理输出格式：建议 jpeg（省 token/带宽/速度），但会有轻微文字损失
# 可选："jpeg" 或 "png"
PREPROCESS_FORMAT = "png"

# JPEG 质量（仅当 PREPROCESS_FORMAT="jpeg" 时有效）
# 建议 70~85：70 更省，85 更清晰
JPEG_QUALITY = 78

# 预处理尺寸策略（核心）：
# - 先读取“用户当天截图中第一张”的分辨率作为屏幕大小近似
# - 若屏幕本身就很小，则不再缩放
# - 若屏幕很大，则按比例缩放，但保证长边不低于 MIN_LONG_EDGE，且不超过 MAX_LONG_EDGE
DOWNSCALE_RATIO = 0.55     # 大屏时默认缩放比例（0.5~0.7 推荐）
MIN_LONG_EDGE = 900        # 避免小屏再压缩到看不清
MAX_LONG_EDGE = 1600       # 控制大屏的最大长边，进一步省 token

# 你可以做“token消耗测试”的参数：
# - DRY_RUN=True：只预处理并输出统计，不调用 Gemini
# - SAMPLE_LIMIT：只取前 N 张来试算（0 表示全部）
DRY_RUN = False
SAMPLE_LIMIT = 0

# Gemini 请求节流（避免过快限流）
REQUEST_SLEEP_SECONDS = 0.2

# 置信度阈值（低于则标记 low_confidence）
LOW_CONFIDENCE_THRESHOLD = 0.60

# 连续帧合并规则：dominant_surface + activity 相同则合并
MERGE_BY_ACTIVITY_TOO = True


@dataclass
class FrameResult:
    dt: datetime
    filename: str
    dominant_surface: str
    activity: str
    context_detail: str
    confidence: float
    supporting_surfaces: List[str]
    notes: str


def _ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def _today_folder(now: datetime) -> str:
    year = now.strftime("%Y")
    month = now.strftime("%B")  # January...
    day = now.strftime("%d")
    return os.path.join(SCREENSHOT_ROOT, year, month, day)


def _parse_time_from_filename(filename: str) -> Optional[Tuple[int, int, int]]:
    base = os.path.splitext(filename)[0]
    parts = base.split("-")
    if len(parts) != 3:
        return None
    try:
        hh = int(parts[0])
        mm = int(parts[1])
        ss = int(parts[2])
        if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
            return None
        return hh, mm, ss
    except ValueError:
        return None


def _list_day_images(day_dir: str, day_date: date) -> List[Tuple[datetime, str]]:
    if not os.path.isdir(day_dir):
        return []

    items: List[Tuple[datetime, str]] = []
    for name in os.listdir(day_dir):
        lower = name.lower()
        if not (lower.endswith(".png") or lower.endswith(".jpg") or lower.endswith(".jpeg")):
            continue

        t = _parse_time_from_filename(name)
        if t is None:
            continue

        dt = datetime(day_date.year, day_date.month, day_date.day, t[0], t[1], t[2])
        items.append((dt, name))

    items.sort(key=lambda x: x[0])
    return items


def _mime_type_for_ext(ext: str) -> str:
    ext = ext.lower()
    if ext == ".png":
        return "image/png"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    return "application/octet-stream"


def _build_frame_prompt(dt_local: datetime, filename: str) -> str:
    return f"""
You are analyzing a user's desktop screenshot taken at local time {dt_local.strftime('%Y-%m-%d %H:%M:%S')} (file: {filename}).
Goal: identify what the user is doing, using DOMINANT on-screen surface (largest/most salient region). If the screenshot is a web page, prefer labeling the WEBSITE/PRODUCT (e.g., YouTube, Google Docs, Gmail, Canvas, GitHub, LeetCode, Notion) rather than "Chrome" or "Browser". Only use "Chrome/Browser" if you truly cannot infer the page/product.

Rules:
- Choose exactly ONE dominant_surface (string).
- Choose ONE activity label (short; e.g., Coding, Video/Tutorial, Writing/Reading, Messaging, Meeting, Gaming, Social, Email, Browsing, Terminal, File Management, Settings, Other).
- supporting_surfaces: list up to 3 secondary surfaces (strings) if visible. If none, empty list.
- context_detail: optional short hint. Do not include sensitive text like passwords, bank details, personal names.
- confidence: float 0.0-1.0.
- notes: optional short rationale.

Output STRICT JSON only (no markdown, no extra keys), with keys exactly:
{{
  "dominant_surface": "...",
  "activity": "...",
  "context_detail": "...",
  "confidence": 0.0,
  "supporting_surfaces": ["..."],
  "notes": "..."
}}
""".strip()


# =======================
# Preprocess (resize + compress)
# =======================

def _read_image_size(path: str) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size  # (w, h)


def _compute_target_long_edge(screen_w: int, screen_h: int) -> int:
    """
    根据“屏幕大小近似”（用当天第一张截图尺寸）决定缩放目标。
    - 小屏：不缩放（至少保持 MIN_LONG_EDGE）
    - 大屏：按 DOWNSCALE_RATIO 缩放，但不超过 MAX_LONG_EDGE
    """
    long_edge = max(screen_w, screen_h)
    if long_edge <= MIN_LONG_EDGE:
        return long_edge  # 不缩放
    # 按比例缩小
    target = int(round(long_edge * DOWNSCALE_RATIO))
    # clamp
    if target < MIN_LONG_EDGE:
        target = MIN_LONG_EDGE
    if target > MAX_LONG_EDGE:
        target = MAX_LONG_EDGE
    return target


def _preprocess_image_bytes(
    src_path: str,
    target_long_edge: int,
    out_format: str,
    jpeg_quality: int
) -> Tuple[bytes, str, Dict[str, Any]]:
    """
    返回：(bytes, mime_type, stats)
    """
    original_size_bytes = os.path.getsize(src_path)

    with Image.open(src_path) as im:
        im = im.convert("RGB") if out_format.lower() == "jpeg" else im.copy()

        w, h = im.size
        long_edge = max(w, h)

        resized = False
        if long_edge > target_long_edge:
            scale = target_long_edge / float(long_edge)
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            im = im.resize((new_w, new_h), resample=Image.LANCZOS)
            resized = True

        # 编码到内存
        import io
        buf = io.BytesIO()

        if out_format.lower() == "jpeg":
            im.save(buf, format="JPEG", quality=jpeg_quality, optimize=True, progressive=True)
            mime = "image/jpeg"
            ext = ".jpg"
        else:
            # PNG：不损失，但通常更大；依然能通过缩放减少 token
            im.save(buf, format="PNG", optimize=True)
            mime = "image/png"
            ext = ".png"

        data = buf.getvalue()

    stats = {
        "src_bytes": original_size_bytes,
        "out_bytes": len(data),
        "src_resolution": f"{w}x{h}",
        "out_resolution": f"{im.size[0]}x{im.size[1]}",
        "resized": resized,
        "target_long_edge": target_long_edge,
        "format": out_format.lower()
    }
    return data, mime, stats


def _preprocess_day_images(
    day_dir: str,
    images: List[Tuple[datetime, str]]
) -> Tuple[List[Tuple[datetime, str, bytes, str]], Dict[str, Any]]:
    """
    对当天图像做预处理，返回：
    - processed: [(dt, filename, bytes, mime)]
    - summary stats
    """
    if not images:
        return [], {"note": "no images"}

    first_path = os.path.join(day_dir, images[0][1])
    screen_w, screen_h = _read_image_size(first_path)
    target_long_edge = _compute_target_long_edge(screen_w, screen_h)

    processed: List[Tuple[datetime, str, bytes, str]] = []
    total_src = 0
    total_out = 0

    # sample limit
    use_images = images
    if SAMPLE_LIMIT and SAMPLE_LIMIT > 0:
        use_images = images[:SAMPLE_LIMIT]

    per_image_stats: List[Dict[str, Any]] = []

    for dt_local, filename in use_images:
        src_path = os.path.join(day_dir, filename)
        data, mime, st = _preprocess_image_bytes(
            src_path=src_path,
            target_long_edge=target_long_edge,
            out_format=PREPROCESS_FORMAT,
            jpeg_quality=JPEG_QUALITY
        )
        processed.append((dt_local, filename, data, mime))
        total_src += int(st["src_bytes"])
        total_out += int(st["out_bytes"])
        per_image_stats.append({"filename": filename, **st})

    summary = {
        "screen_resolution_inferred": f"{screen_w}x{screen_h}",
        "target_long_edge": target_long_edge,
        "preprocess_enabled": True,
        "format": PREPROCESS_FORMAT.lower(),
        "jpeg_quality": JPEG_QUALITY if PREPROCESS_FORMAT.lower() == "jpeg" else None,
        "image_count_processed": len(processed),
        "total_src_bytes": total_src,
        "total_out_bytes": total_out,
        "compression_ratio": round((total_out / total_src), 4) if total_src > 0 else None,
        "per_image": per_image_stats  # 如太啰嗦你可删掉
    }
    return processed, summary


# =======================
# Gemini + Timeline
# =======================

def _normalize_frame_json(raw: Dict[str, Any]) -> Dict[str, Any]:
    def _as_str(v: Any) -> str:
        return v if isinstance(v, str) else ""

    def _as_float(v: Any) -> float:
        try:
            return float(v)
        except Exception:
            return 0.0

    def _as_list_str(v: Any) -> List[str]:
        if isinstance(v, list):
            out: List[str] = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
            return out[:3]
        return []

    norm = {
        "dominant_surface": _as_str(raw.get("dominant_surface", "")).strip() or "Unknown",
        "activity": _as_str(raw.get("activity", "")).strip() or "Other",
        "context_detail": _as_str(raw.get("context_detail", "")).strip(),
        "confidence": max(0.0, min(1.0, _as_float(raw.get("confidence", 0.0)))),
        "supporting_surfaces": _as_list_str(raw.get("supporting_surfaces", [])),
        "notes": _as_str(raw.get("notes", "")).strip(),
    }
    return norm


def _call_gemini_for_frame_bytes(
    client: genai.Client,
    image_bytes: bytes,
    mime_type: str,
    dt_local: datetime,
    filename: str
) -> Dict[str, Any]:
    prompt = _build_frame_prompt(dt_local, filename)

    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt
        ],
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            temperature=0.0
        ),
    )

    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Empty response from Gemini.")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini did not return valid JSON. Raw text:\n{text}") from e


def _detect_gaps(frames: List[FrameResult]) -> List[Dict[str, str]]:
    if not frames:
        return []
    expected = timedelta(minutes=CAPTURE_INTERVAL_MINUTES)
    gaps: List[Dict[str, str]] = []
    for i in range(1, len(frames)):
        delta = frames[i].dt - frames[i - 1].dt
        if delta > expected * 1.5:
            gaps.append({
                "start_time_local": frames[i - 1].dt.strftime("%H:%M"),
                "end_time_local": frames[i].dt.strftime("%H:%M"),
                "reason": "missing screenshots"
            })
    return gaps


def _estimate_missing_expected(frames: List[FrameResult]) -> int:
    if len(frames) < 2:
        return 0
    expected = timedelta(minutes=CAPTURE_INTERVAL_MINUTES)
    missing = 0
    for i in range(1, len(frames)):
        delta = frames[i].dt - frames[i - 1].dt
        if delta > expected:
            miss = int(round((delta / expected) - 1))
            if miss > 0:
                missing += miss
    return missing


def _merge_frames_into_segments(frames: List[FrameResult]) -> List[Dict[str, Any]]:
    if not frames:
        return []

    segments: List[Dict[str, Any]] = []

    def same_bucket(a: FrameResult, b: FrameResult) -> bool:
        if a.dominant_surface != b.dominant_surface:
            return False
        if MERGE_BY_ACTIVITY_TOO and a.activity != b.activity:
            return False
        return True

    start_idx = 0
    for i in range(1, len(frames) + 1):
        if i == len(frames) or not same_bucket(frames[i - 1], frames[i]):
            chunk = frames[start_idx:i]
            first = chunk[0]
            last = chunk[-1]

            start_time = first.dt
            end_time = last.dt + timedelta(minutes=CAPTURE_INTERVAL_MINUTES)
            duration_minutes = int(round((end_time - start_time).total_seconds() / 60))

            sup: List[str] = []
            for fr in chunk:
                for s in fr.supporting_surfaces:
                    if s not in sup and s != fr.dominant_surface:
                        sup.append(s)
            sup = sup[:3]

            avg_conf = sum(fr.confidence for fr in chunk) / max(1, len(chunk))

            risk_flags: List[str] = []
            if avg_conf < LOW_CONFIDENCE_THRESHOLD:
                risk_flags.append("low_confidence")

            segments.append({
                "start_time_local": start_time.strftime("%H:%M"),
                "end_time_local": end_time.strftime("%H:%M"),
                "duration_minutes": duration_minutes,
                "dominant_surface": first.dominant_surface,
                "activity": first.activity,
                "context_detail": first.context_detail,
                "confidence": round(avg_conf, 3),
                "supporting_surfaces": sup,
                "evidence_frames": [fr.filename for fr in chunk],
                "notes": first.notes,
                "risk_flags": risk_flags or ["none"]
            })

            start_idx = i

    for idx, seg in enumerate(segments, start=1):
        seg["segment_id"] = f"S{idx:03d}"

    return segments


def _segments_to_human_lines(segments: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for seg in segments:
        lines.append(
            f"{seg['start_time_local']}–{seg['end_time_local']}  "
            f"{seg['dominant_surface']}  | {seg['activity']} (confidence: {seg['confidence']:.2f})"
        )
    return lines


def _build_totals(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_surface: Dict[str, Dict[str, float]] = {}
    by_activity: Dict[str, int] = {}

    for seg in segments:
        minutes = int(seg.get("duration_minutes", 0))
        conf = float(seg.get("confidence", 0.0))
        surface = seg.get("dominant_surface", "Unknown")
        activity = seg.get("activity", "Other")

        if surface not in by_surface:
            by_surface[surface] = {"minutes": 0, "confidence_weighted_minutes": 0.0}
        by_surface[surface]["minutes"] += minutes
        by_surface[surface]["confidence_weighted_minutes"] += minutes * conf

        by_activity[activity] = by_activity.get(activity, 0) + minutes

    by_surface_list = []
    for k, v in by_surface.items():
        by_surface_list.append({
            "surface": k,
            "minutes": int(v["minutes"]),
            "confidence_weighted_minutes": round(v["confidence_weighted_minutes"], 2)
        })
    by_surface_list.sort(key=lambda x: x["minutes"], reverse=True)

    by_activity_list = []
    for k, v in by_activity.items():
        by_activity_list.append({"activity": k, "minutes": int(v)})
    by_activity_list.sort(key=lambda x: x["minutes"], reverse=True)

    context_switch_count = max(0, len(segments) - 1)

    return {
        "by_surface_minutes": by_surface_list,
        "by_activity_minutes": by_activity_list,
        "context_switch_count": context_switch_count
    }


def generate_timeline_for_today() -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY.strip() == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        raise RuntimeError("Please paste your Gemini API key into GEMINI_API_KEY in this file.")

    now = datetime.now()
    day_dir = _today_folder(now)
    day_date = now.date()

    images = _list_day_images(day_dir, day_date)
    if not images:
        raise RuntimeError(f"No images found in today's folder: {day_dir}")

    # sample limit（不预处理时也需要限制）
    use_images = images
    if SAMPLE_LIMIT and SAMPLE_LIMIT > 0:
        use_images = images[:SAMPLE_LIMIT]

    # 预处理
    preprocess_summary: Dict[str, Any] = {
        "preprocess_enabled": False,
        "note": "disabled"
    }

    if ENABLE_PREPROCESS:
        processed, preprocess_summary = _preprocess_day_images(day_dir, images)
        # 若 SAMPLE_LIMIT 生效，_preprocess_day_images 已经截断
        processed_inputs = processed
    else:
        # 不预处理：直接读取原文件 bytes
        processed_inputs = []
        for dt_local, filename in use_images:
            path = os.path.join(day_dir, filename)
            with open(path, "rb") as f:
                data = f.read()
            ext = os.path.splitext(filename)[1]
            mime = _mime_type_for_ext(ext)
            processed_inputs.append((dt_local, filename, data, mime))

        preprocess_summary = {
            "preprocess_enabled": False,
            "image_count_processed": len(processed_inputs),
            "total_out_bytes": sum(len(x[2]) for x in processed_inputs),
            "note": "using original images"
        }

    # DRY RUN：只看压缩结果，不消耗 token
    if DRY_RUN:
        report = {
            "date_local": day_date.strftime("%Y-%m-%d"),
            "day_folder": day_dir,
            "sample_limit": SAMPLE_LIMIT,
            "preprocess": preprocess_summary
        }
        out_name = f"dryrun_preprocess_{day_date.strftime('%Y-%m-%d')}.json"
        out_path = os.path.join(day_dir, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"DRY_RUN saved: {out_path}")
        print("Key stats:")
        print(f"- inferred screen: {preprocess_summary.get('screen_resolution_inferred')}")
        print(f"- target long edge: {preprocess_summary.get('target_long_edge')}")
        print(f"- total bytes before: {preprocess_summary.get('total_src_bytes')}")
        print(f"- total bytes after : {preprocess_summary.get('total_out_bytes')}")
        print(f"- compression ratio : {preprocess_summary.get('compression_ratio')}")
        return out_path

    # 调 Gemini
    client = genai.Client(api_key=GEMINI_API_KEY)

    frame_results: List[FrameResult] = []

    for dt_local, filename, img_bytes, mime in processed_inputs:
        raw = _call_gemini_for_frame_bytes(client, img_bytes, mime, dt_local, filename)
        norm = _normalize_frame_json(raw)

        frame_results.append(FrameResult(
            dt=dt_local,
            filename=filename,
            dominant_surface=norm["dominant_surface"],
            activity=norm["activity"],
            context_detail=norm["context_detail"],
            confidence=norm["confidence"],
            supporting_surfaces=norm["supporting_surfaces"],
            notes=norm["notes"]
        ))

        time.sleep(REQUEST_SLEEP_SECONDS)

    segments = _merge_frames_into_segments(frame_results)
    timeline_lines = _segments_to_human_lines(segments)
    gaps = _detect_gaps(frame_results)
    missing_expected = _estimate_missing_expected(frame_results)
    totals = _build_totals(segments)

    output = {
        "schema_version": "2.0",
        "date_local": day_date.strftime("%Y-%m-%d"),
        "timezone": TIMEZONE_NAME,
        "capture_interval_minutes": CAPTURE_INTERVAL_MINUTES,

        "timeline_human_readable": timeline_lines,
        "timeline_segments": segments,

        "totals": totals,

        "data_quality": {
            "image_count": len(frame_results),
            "missing_expected_images": missing_expected,
            "gaps": gaps
        },

        "preprocess": preprocess_summary
    }

    out_name = f"timeline_{day_date.strftime('%Y-%m-%d')}.json"
    out_path = os.path.join(day_dir, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return out_path


if __name__ == "__main__":
    path = generate_timeline_for_today()
    print(f"Output saved: {path}")
