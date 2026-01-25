import os
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from google import genai
from google.genai import types


# =======================
# Global Configuration
# =======================

# 1) 直接把 Gemini API Key 粘贴在这里（不使用环境变量）
GEMINI_API_KEY = "AIzaSyAi8N4Jv8-wCi9iSQDjm8vSe8BVoJhdPyE"

# 2) 输入：timeline JSON 的路径（为空则自动在“今天的截图目录”里找 timeline_YYYY-MM-DD.json）
TIMELINE_JSON_PATH = ""

# 3) 截图根目录（用于自动定位“今天”目录 & 输出结果）
SCREENSHOT_ROOT = "screenshots_test"
TIMEZONE_NAME = "America/Los_Angeles"

# 4) Gemini 模型
# - 文本分析：Flash 更快更省
TEXT_MODEL = "gemini-3-flash-preview"
# - 图像生成：Gemini 3 Pro Image（preview）
IMAGE_MODEL = "gemini-3-pro-image-preview"

# 5) 你要的“风格选择”（你只需要改这个变量）
# 可选： "year_in_review_cute", "abstract", "watercolor", "pixel_art", "isometric", "minimalist", "cyberpunk"
STYLE_PRESET = "year_in_review_cute"

# 6) 输出目录：默认输出到 timeline JSON 同目录
OUTPUT_DIR = ""

# 7) 安全：避免输出敏感信息（模型也会被提示不要写）
AVOID_SENSITIVE_TEXT = True

# 8) 控制输出图片尺寸（提示词层面；实际由模型决定）
# 你后续做网页展示，1024 或 1536 通常足够
TARGET_IMAGE_HINT = "1024x1024"


# =======================
# Utilities
# =======================

def _ensure_dir(path: str) -> None:
    if path and not os.path.exists(path):
        os.makedirs(path)


def _today_folder(now: datetime) -> str:
    year = now.strftime("%Y")
    month = now.strftime("%B")
    day = now.strftime("%d")
    return os.path.join(SCREENSHOT_ROOT, year, month, day)


def _find_today_timeline_json() -> str:
    day_dir = _today_folder(datetime.now())
    fname = f"timeline_{datetime.now().strftime('%Y-%m-%d')}.json"
    path = os.path.join(day_dir, fname)
    if not os.path.isfile(path):
        raise RuntimeError(f"Cannot find today's timeline JSON at: {path}")
    return path


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, obj: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _sanitize_text(s: str) -> str:
    # 简单防御：去掉可能的“长串数字/邮箱”等（避免无意间把敏感信息写进报告）
    if not s:
        return s
    s = re.sub(r"\b\d{6,}\b", "[REDACTED_NUMBER]", s)
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", s)
    return s


def _timeline_to_compact_text(timeline: Dict[str, Any], max_lines: int = 120) -> str:
    """
    把 timeline JSON 压缩成可喂给模型的文字摘要：
    - 重点用 timeline_human_readable + timeline_segments
    - 控制长度，避免 token 爆炸
    """
    date_local = timeline.get("date_local", "")
    lines: List[str] = [f"Date: {date_local} ({TIMEZONE_NAME})"]

    hr = timeline.get("timeline_human_readable", [])
    if isinstance(hr, list) and hr:
        lines.append("Timeline (human readable):")
        for x in hr[:max_lines]:
            if isinstance(x, str):
                lines.append(f"- {x}")

    segs = timeline.get("timeline_segments", [])
    if isinstance(segs, list) and segs:
        lines.append("Segments (structured):")
        for seg in segs[: min(len(segs), 80)]:
            try:
                st = seg.get("start_time_local", "")
                et = seg.get("end_time_local", "")
                dom = seg.get("dominant_surface", "")
                act = seg.get("activity", "")
                dur = seg.get("duration_minutes", "")
                conf = seg.get("confidence", "")
                lines.append(f"- {st}-{et} | {dom} | {act} | {dur}min | conf={conf}")
            except Exception:
                continue

    txt = "\n".join(lines)
    return _sanitize_text(txt) if AVOID_SENSITIVE_TEXT else txt


# =======================
# Prompt templates
# =======================

def _style_prompt(style_preset: str) -> Dict[str, str]:
    """
    你要的风格 options：统一映射到图像生成 prompt 的“画风段落”
    """
    presets = {
        "year_in_review_cute": {
            "name": "Cute Year-in-Review",
            "prompt": (
                "Create a cute, warm 'year-in-review / daily recap' illustration. "
                "Chibi-style characters, soft shading, clean shapes, gentle glow, "
                "sticker-like elements, and a cohesive pastel palette. "
                "Add small iconic objects representing the day's activities."
            )
        },
        "abstract": {
            "name": "Abstract",
            "prompt": (
                "Create an abstract art piece that conveys the day's rhythm and mood. "
                "Use geometric shapes, expressive brush strokes, and symbolic motifs rather than literal UI screens."
            )
        },
        "watercolor": {
            "name": "Watercolor",
            "prompt": (
                "Create a watercolor illustration with visible paper texture, soft bleeding edges, and light washes. "
                "Focus on atmosphere and storytelling."
            )
        },
        "pixel_art": {
            "name": "Pixel Art",
            "prompt": (
                "Create a pixel art scene (16-bit style), crisp tiles and readable silhouettes. "
                "Depict the day's major activities as objects or mini-scenes."
            )
        },
        "isometric": {
            "name": "Isometric",
            "prompt": (
                "Create an isometric diorama of a desk/workspace and surrounding mini-scenes. "
                "Clean lines, subtle shadows, high readability."
            )
        },
        "minimalist": {
            "name": "Minimalist",
            "prompt": (
                "Create a minimalist poster-like illustration using few shapes and strong composition. "
                "Avoid clutter; use icons to represent activities."
            )
        },
        "cyberpunk": {
            "name": "Cyberpunk",
            "prompt": (
                "Create a cyberpunk illustration with neon lighting, high contrast, and futuristic UI motifs. "
                "Still keep it tasteful and not overly dark."
            )
        },
    }

    return presets.get(style_preset, presets["year_in_review_cute"])


def _vibe_analysis_prompt(timeline_text: str) -> str:
    """
    让 Gemini 输出一个固定 JSON（vibe + 解释 + 关怀建议 + 名言 + 幽默备选）
    """
    return f"""
You are given a user's desktop-usage timeline for a single day.

Task A — Vibe analysis:
Infer the day's vibe. Choose ONE primary vibe label from:
["hurried_anxious", "calm_relaxed", "creative_flow", "deep_focus", "distracted_scattered", "social_connected", "learning_mode", "mixed_unclear"].

Task B — Caring message:
Write a supportive message that feels warm and human (not cheesy). Optionally include one short quote.
If the day shows long work sessions, encourage sustainable pacing. If it shows a lot of distraction, suggest a gentle reset.

Hard rules:
- Do NOT reveal sensitive content. Do NOT include personal names, passwords, financial or medical details.
- Base your reasoning ONLY on the timeline text.
- Output STRICT JSON only, with keys exactly:
{{
  "primary_vibe": "...",
  "confidence": 0.0,
  "why": ["...","...","..."],
  "notable_patterns": ["...","..."],
  "caring_message": "...",
  "quote": "...",
  "humor_alt": "..."
}}

Timeline:
{timeline_text}
""".strip()


def _redraw_image_prompt(timeline_text: str, style_block: str) -> str:
    """
    “重绘这一天”的图片 prompt：不画真实屏幕，而是抽象/符号化重现。
    强制加入一些“重要元素”，像年度总结卡片那样。
    """
    return f"""
Create ONE illustration that "redraws the day" based on this desktop-usage timeline.

Composition requirements:
- A single cohesive scene (not a collage of many separate images).
- Represent major activities with symbolic, cute, or iconic objects and micro-scenes.
- Include a subtle timeline motif (e.g., a ribbon, clock arc, or progress bar) showing morning→evening.
- Avoid drawing real UI screenshots or readable private text. No usernames, no emails, no exact titles.

Style:
{style_block}

Quality:
- High readability, clean composition, emotionally warm.
- Target size hint: {TARGET_IMAGE_HINT}

Timeline (for inspiration, do not copy literal text):
{timeline_text}
""".strip()


# =======================
# Gemini calls
# =======================

def _require_api_key() -> None:
    if not GEMINI_API_KEY or GEMINI_API_KEY.strip() == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        raise RuntimeError("Please paste your Gemini API key into GEMINI_API_KEY in daily_generation.py.")


def _call_gemini_text_json(client: genai.Client, prompt: str) -> Dict[str, Any]:
    resp = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            thinking_config=types.ThinkingConfig(thinking_level="medium"),
        ),
    )
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Empty response from Gemini (text).")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini did not return valid JSON. Raw:\n{text}") from e


def _extract_image_bytes_from_response(resp: Any) -> Optional[Tuple[bytes, str]]:
    """
    尽可能兼容 SDK 的返回结构：
    - 找 candidates[0].content.parts 里带 inline_data 的 part
    """
    try:
        cands = getattr(resp, "candidates", None)
        if not cands:
            return None
        content = getattr(cands[0], "content", None)
        if not content:
            return None
        parts = getattr(content, "parts", None)
        if not parts:
            return None

        for p in parts:
            inline = getattr(p, "inline_data", None)
            if inline is not None:
                data = getattr(inline, "data", None)
                mime = getattr(inline, "mime_type", None) or "image/png"
                if data:
                    return data, mime
    except Exception:
        return None
    return None


def _call_gemini_generate_image(client: genai.Client, prompt: str) -> Tuple[bytes, str]:
    """
    使用支持图片输出的模型生成图片。
    注意：部分 image 模型不支持 thinking_config，不能传 thinking_level。
    """
    resp = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7
            # 不要传 thinking_config：该模型可能不支持
        ),
    )

    extracted = _extract_image_bytes_from_response(resp)
    if not extracted:
        txt = (resp.text or "").strip()
        raise RuntimeError(
            "No image bytes found in response. "
            "Model may have returned text only.\n"
            f"Text:\n{txt}"
        )
    return extracted[0], extracted[1]


# =======================
# Main generation pipeline
# =======================

def generate_daily_story() -> Dict[str, Any]:
    _require_api_key()

    timeline_path = TIMELINE_JSON_PATH.strip() or _find_today_timeline_json()
    timeline = _load_json(timeline_path)

    out_dir = OUTPUT_DIR.strip() or os.path.dirname(timeline_path)
    _ensure_dir(out_dir)

    timeline_text = _timeline_to_compact_text(timeline)

    client = genai.Client(api_key=GEMINI_API_KEY)

    # 1) Vibe + caring
    vibe_prompt = _vibe_analysis_prompt(timeline_text)
    vibe = _call_gemini_text_json(client, vibe_prompt)

    # 2) Redraw image
    style = _style_prompt(STYLE_PRESET)
    style_block = style["prompt"]
    image_prompt = _redraw_image_prompt(timeline_text, style_block)

    img_bytes, img_mime = _call_gemini_generate_image(client, image_prompt)

    # 输出图片
    date_local = timeline.get("date_local", datetime.now().strftime("%Y-%m-%d"))
    img_ext = ".png" if "png" in (img_mime or "").lower() else ".jpg"
    img_name = f"redraw_{date_local}_{STYLE_PRESET}{img_ext}"
    img_path = os.path.join(out_dir, img_name)

    with open(img_path, "wb") as f:
        f.write(img_bytes)

    # 3) 汇总为 daily report JSON（供 UI 直接读取）
    report = {
        "schema_version": "1.0",
        "date_local": date_local,
        "timezone": TIMEZONE_NAME,
        "inputs": {
            "timeline_json": os.path.abspath(timeline_path),
            "style_preset": STYLE_PRESET,
            "style_name": style["name"],
        },
        "outputs": {
            "vibe": vibe,
            "image": {
                "file": img_path.replace("\\", "/"),
                "mime_type": img_mime,
                "prompt_used": image_prompt,
            }
        },
        "ui_modules": {
            "main_timeline_module": "Render timeline_human_readable + segments",
            "secondary_image_module": "Show redraw image + short caption",
            "secondary_caring_module": "Show caring_message + quote + humor_alt"
        }
    }

    if AVOID_SENSITIVE_TEXT:
        # 再保险：把 report 中的文本都做一次轻量脱敏
        def scrub_obj(x: Any) -> Any:
            if isinstance(x, str):
                return _sanitize_text(x)
            if isinstance(x, list):
                return [scrub_obj(i) for i in x]
            if isinstance(x, dict):
                return {k: scrub_obj(v) for k, v in x.items()}
            return x
        report = scrub_obj(report)

    report_path = os.path.join(out_dir, f"daily_report_{date_local}.json")
    _write_json(report_path, report)

    return {
        "timeline_json": timeline_path,
        "report_json": report_path,
        "image_path": img_path
    }


if __name__ == "__main__":
    result = generate_daily_story()
    print("Generated:")
    print(f"- Report JSON: {result['report_json']}")
    print(f"- Redraw image: {result['image_path']}")
