import os
import json
import time
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple

from PIL import Image
from google import genai
from google.genai import types

from config import AppConfig
from utils_paths import ensure_dir


def _infer_capture_interval_minutes(frame_times: List[datetime], fallback: int) -> int:
    if len(frame_times) < 2:
        return max(1, int(fallback))
    deltas = []
    for i in range(len(frame_times) - 1):
        dt = (frame_times[i + 1] - frame_times[i]).total_seconds() / 60.0
        if dt > 0:
            deltas.append(dt)
    if not deltas:
        return max(1, int(fallback))
    deltas.sort()
    mid = len(deltas) // 2
    median = deltas[mid] if len(deltas) % 2 == 1 else (deltas[mid - 1] + deltas[mid]) / 2.0
    # Round to nearest minute
    return max(1, int(round(median)))


def _image_similarity(path_a: str, path_b: str) -> float:
    """
    Best-effort similarity metric: resize to 64x64 grayscale, compute normalized mean absolute diff.
    Returns similarity in [0,1], 1 = identical.
    """
    try:
        with Image.open(path_a) as ia:
            ia = ia.convert("L").resize((64, 64))
            a = list(ia.getdata())
        with Image.open(path_b) as ib:
            ib = ib.convert("L").resize((64, 64))
            b = list(ib.getdata())
        if len(a) != len(b) or not a:
            return 0.0
        diff = 0
        for x, y in zip(a, b):
            diff += abs(x - y)
        mean_diff = diff / float(len(a))
        sim = 1.0 - (mean_diff / 255.0)
        if sim < 0.0:
            sim = 0.0
        if sim > 1.0:
            sim = 1.0
        return sim
    except Exception:
        return 0.0

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


def _parse_time_from_filename(filename: str) -> Optional[Tuple[int, int, int]]:
    base = os.path.splitext(filename)[0]
    parts = base.split("-")
    if len(parts) != 3:
        return None
    try:
        hh, mm, ss = int(parts[0]), int(parts[1]), int(parts[2])
        if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
            return hh, mm, ss
        return None
    except ValueError:
        return None


def _list_day_images(day_dir: str, day_date: date) -> List[Tuple[datetime, str]]:
    items: List[Tuple[datetime, str]] = []
    if not os.path.isdir(day_dir):
        return items
    for name in os.listdir(day_dir):
        lower = name.lower()
        if not (lower.endswith(".png") or lower.endswith(".jpg") or lower.endswith(".jpeg")):
            continue
        t = _parse_time_from_filename(name)
        if not t:
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


def _normalize_frame_json(raw: Dict[str, Any]) -> Dict[str, Any]:
    def as_str(v: Any) -> str:
        return v if isinstance(v, str) else ""
    def as_float(v: Any) -> float:
        try:
            return float(v)
        except Exception:
            return 0.0
    def as_list_str(v: Any) -> List[str]:
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
            return out[:3]
        return []

    return {
        "dominant_surface": as_str(raw.get("dominant_surface", "")).strip() or "Unknown",
        "activity": as_str(raw.get("activity", "")).strip() or "Other",
        "context_detail": as_str(raw.get("context_detail", "")).strip(),
        "confidence": max(0.0, min(1.0, as_float(raw.get("confidence", 0.0)))),
        "supporting_surfaces": as_list_str(raw.get("supporting_surfaces", [])),
        "notes": as_str(raw.get("notes", "")).strip(),
    }


def _read_image_size(path: str) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def _compute_target_long_edge(cfg: AppConfig, screen_w: int, screen_h: int) -> int:
    long_edge = max(screen_w, screen_h)
    if long_edge <= cfg.min_long_edge:
        return long_edge
    target = int(round(long_edge * cfg.downscale_ratio))
    if target < cfg.min_long_edge:
        target = cfg.min_long_edge
    if target > cfg.max_long_edge:
        target = cfg.max_long_edge
    return target


def _preprocess_image_bytes(cfg: AppConfig, src_path: str, target_long_edge: int):
    original_size = os.path.getsize(src_path)
    with Image.open(src_path) as im:
        out_format = cfg.preprocess_format.lower()
        if out_format == "jpeg":
            im = im.convert("RGB")

        w, h = im.size
        long_edge = max(w, h)
        resized = False

        if long_edge > target_long_edge:
            scale = target_long_edge / float(long_edge)
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            im = im.resize((new_w, new_h), resample=Image.LANCZOS)
            resized = True

        import io
        buf = io.BytesIO()
        if out_format == "jpeg":
            im.save(buf, format="JPEG", quality=cfg.jpeg_quality, optimize=True, progressive=True)
            mime = "image/jpeg"
        else:
            im.save(buf, format="PNG", optimize=True)
            mime = "image/png"

        data = buf.getvalue()

    stats = {
        "src_bytes": original_size,
        "out_bytes": len(data),
        "src_resolution": f"{w}x{h}",
        "out_resolution": f"{im.size[0]}x{im.size[1]}",
        "resized": resized,
        "target_long_edge": target_long_edge,
        "format": cfg.preprocess_format.lower(),
    }
    return data, mime, stats


def _merge_frames_into_segments(cfg: AppConfig, frames: List[FrameResult], day_dir: str) -> List[Dict[str, Any]]:
    """
    Builds segments using real screenshot timestamps.
    - Transition boundaries use midpoints between screenshots when surface/activity changes (smooth flow).
    - Segment ends use next screenshot time (not a fixed 15 minutes).
    - Best-effort Idle carving: if two consecutive frames are very similar and far apart, carve out an Idle segment.
    """
    if not frames:
        return []

    # Infer interval from real timestamps (median delta), fallback to cfg.capture_interval_minutes
    frame_times = [fr.dt for fr in frames]
    inferred_interval = _infer_capture_interval_minutes(frame_times, cfg.capture_interval_minutes)

    # Group consecutive frames by bucket
    buckets = [(fr.dominant_surface, fr.activity) for fr in frames]

    # Build initial segments using bucket runs and midpoint boundaries
    initial = []
    start_idx = 0
    n = len(frames)

    def boundary_mid(a: datetime, b: datetime) -> datetime:
        return a + (b - a) / 2

    while start_idx < n:
        bkt = buckets[start_idx]
        end_idx = start_idx
        while end_idx + 1 < n and buckets[end_idx + 1] == bkt:
            end_idx += 1

        # segment start boundary: midpoint between prev frame and first frame of this run (if different bucket)
        if start_idx == 0:
            seg_start = frames[start_idx].dt
        else:
            seg_start = boundary_mid(frames[start_idx - 1].dt, frames[start_idx].dt)

        # segment end boundary: midpoint between last frame of this run and next frame (if exists), else fallback interval
        if end_idx < n - 1:
            seg_end = boundary_mid(frames[end_idx].dt, frames[end_idx + 1].dt)
        else:
            seg_end = frames[end_idx].dt + timedelta(minutes=inferred_interval)

        # collect info
        chunk = frames[start_idx:end_idx + 1]
        first = chunk[0]

        sup: List[str] = []
        for fr in chunk:
            for s in fr.supporting_surfaces:
                if s not in sup and s != fr.dominant_surface:
                    sup.append(s)
        sup = sup[:3]

        avg_conf = sum(fr.confidence for fr in chunk) / max(1, len(chunk))
        duration_minutes = int(round((seg_end - seg_start).total_seconds() / 60))

        risk_flags: List[str] = []
        if avg_conf < 0.60:
            risk_flags.append("low_confidence")

        initial.append({
            "start_dt": seg_start,
            "end_dt": seg_end,
            "dominant_surface": first.dominant_surface,
            "activity": first.activity,
            "context_detail": first.context_detail,
            "confidence": round(avg_conf, 3),
            "supporting_surfaces": sup,
            "evidence_frames": [fr.filename for fr in chunk],
            "notes": first.notes,
            "risk_flags": risk_flags or ["none"],
        })

        start_idx = end_idx + 1

    # Idle carving intervals from consecutive frames across the full day
    # If two consecutive screenshots are very similar AND far apart, we carve out an Idle interval.
    idle_intervals: List[Tuple[datetime, datetime, float]] = []
    for i in range(n - 1):
        a = frames[i]
        b = frames[i + 1]
        delta_min = (b.dt - a.dt).total_seconds() / 60.0
        if delta_min < cfg.idle_gap_minutes:
            continue
        path_a = os.path.join(day_dir, a.filename)
        path_b = os.path.join(day_dir, b.filename)
        sim = _image_similarity(path_a, path_b)
        if sim < cfg.idle_similarity_threshold:
            continue

        # carve idle excluding small margins around captures
        margin = min(cfg.idle_margin_minutes, int(delta_min / 4))
        start = a.dt + timedelta(minutes=margin)
        end = b.dt - timedelta(minutes=margin)
        if end > start:
            idle_intervals.append((start, end, sim))

    # Apply interval carving: subtract idle intervals from segments, then insert Idle segments
    def subtract_interval(seg, cut_start: datetime, cut_end: datetime):
        s = seg["start_dt"]
        e = seg["end_dt"]
        if cut_end <= s or cut_start >= e:
            return [seg]  # no overlap
        out = []
        # left part
        if cut_start > s:
            left = dict(seg)
            left["end_dt"] = cut_start
            out.append(left)
        # right part
        if cut_end < e:
            right = dict(seg)
            right["start_dt"] = cut_end
            out.append(right)
        return out

    carved = initial
    idle_segments = []
    for (istart, iend, sim) in idle_intervals:
        new_carved = []
        for seg in carved:
            new_carved.extend(subtract_interval(seg, istart, iend))
        carved = new_carved
        idle_segments.append({
            "start_dt": istart,
            "end_dt": iend,
            "dominant_surface": "Idle",
            "activity": "Idle",
            "context_detail": "No visible change; likely away/idle.",
            "confidence": 0.6,
            "supporting_surfaces": [],
            "evidence_frames": [],
            "notes": f"Auto-detected idle (similarity={sim:.3f}).",
            "risk_flags": ["idle_detected"],
        })

    all_segments = carved + idle_segments
    all_segments.sort(key=lambda s: s["start_dt"])

    # Normalize + assign IDs and HH:MM fields
    segments: List[Dict[str, Any]] = []
    for idx, seg in enumerate(all_segments, start=1):
        duration_minutes = int(round((seg["end_dt"] - seg["start_dt"]).total_seconds() / 60))
        if duration_minutes <= 0:
            continue
        segments.append({
            "segment_id": f"S{idx:03d}",
            "start_time_local": seg["start_dt"].strftime("%H:%M"),
            "end_time_local": seg["end_dt"].strftime("%H:%M"),
            "duration_minutes": duration_minutes,
            "dominant_surface": seg["dominant_surface"],
            "activity": seg["activity"],
            "context_detail": seg["context_detail"],
            "confidence": seg["confidence"],
            "supporting_surfaces": seg["supporting_surfaces"],
            "evidence_frames": seg["evidence_frames"],
            "notes": seg["notes"],
            "risk_flags": seg["risk_flags"],
        })

    return segments, inferred_interval



def _segments_to_human_lines(segments: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for seg in segments:
        lines.append(
            f"{seg['start_time_local']}–{seg['end_time_local']}  "
            f"{seg['dominant_surface']}  | {seg['activity']} (confidence: {seg['confidence']:.2f})"
        )
    return lines


def build_timeline(cfg: AppConfig, day_dir: str, day_date: date, out_dir: str) -> str:
    api_key = cfg.gemini_api_key()
    if not api_key:
        raise RuntimeError(f"Missing Gemini API key. Please set env: {cfg.gemini_api_key_env}")

    images = _list_day_images(day_dir, day_date)
    if not images:
        raise RuntimeError(f"No images found in: {day_dir}")

    client = genai.Client(api_key=api_key)

    first_path = os.path.join(day_dir, images[0][1])
    screen_w, screen_h = _read_image_size(first_path)
    target_long_edge = _compute_target_long_edge(cfg, screen_w, screen_h)

    frame_results: List[FrameResult] = []
    preprocess_stats = {
        "preprocess_enabled": cfg.enable_preprocess,
        "screen_resolution_inferred": f"{screen_w}x{screen_h}",
        "target_long_edge": target_long_edge,
        "format": cfg.preprocess_format.lower(),
    }

    for dt_local, filename in images:
        path = os.path.join(day_dir, filename)

        if cfg.enable_preprocess:
            img_bytes, mime, _st = _preprocess_image_bytes(cfg, path, target_long_edge)
        else:
            with open(path, "rb") as f:
                img_bytes = f.read()
            ext = os.path.splitext(filename)[1]
            mime = _mime_type_for_ext(ext)

        prompt = _build_frame_prompt(dt_local, filename)
        resp = client.models.generate_content(
            model=cfg.gemini_text_model,
            contents=[types.Part.from_bytes(data=img_bytes, mime_type=mime), prompt],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="low"),
                temperature=0.0,
            ),
        )
        text = (resp.text or "").strip()
        if not text:
            raise RuntimeError("Empty response from Gemini timeline model.")

        raw = json.loads(text)
        norm = _normalize_frame_json(raw)

        frame_results.append(FrameResult(
            dt=dt_local,
            filename=filename,
            dominant_surface=norm["dominant_surface"],
            activity=norm["activity"],
            context_detail=norm["context_detail"],
            confidence=norm["confidence"],
            supporting_surfaces=norm["supporting_surfaces"],
            notes=norm["notes"],
        ))

        time.sleep(cfg.request_sleep_seconds)

    segments, inferred_interval = _merge_frames_into_segments(cfg, frame_results, day_dir)
    timeline_lines = _segments_to_human_lines(segments)

    output = {
        "schema_version": "2.0",
        "date_local": day_date.strftime("%Y-%m-%d"),
        "timezone": cfg.timezone_name,
        "capture_interval_minutes": inferred_interval,
        "timeline_human_readable": timeline_lines,
        "timeline_segments": segments,
        "preprocess": preprocess_stats,
    }

    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, f"timeline_{day_date.strftime('%Y-%m-%d')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return out_path
