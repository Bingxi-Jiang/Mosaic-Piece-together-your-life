import os
import json
import re
import time
import random
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from google import genai
from google.genai import types

from ..config import AppConfig
from ..utils_paths import ensure_dir


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, obj: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _sanitize_text(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"\b\d{6,}\b", "[REDACTED_NUMBER]", s)
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", s)
    return s


def _timeline_to_compact_text(cfg: AppConfig, timeline: Dict[str, Any], max_lines: int = 120) -> str:
    date_local = timeline.get("date_local", "")
    lines: List[str] = [f"Date: {date_local} ({cfg.timezone_name})"]

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
            st = seg.get("start_time_local", "")
            et = seg.get("end_time_local", "")
            dom = seg.get("dominant_surface", "")
            act = seg.get("activity", "")
            dur = seg.get("duration_minutes", "")
            conf = seg.get("confidence", "")
            lines.append(f"- {st}-{et} | {dom} | {act} | {dur}min | conf={conf}")

    txt = "\n".join(lines)
    return _sanitize_text(txt) if cfg.avoid_sensitive_text else txt


def _style_prompt(style_preset: str) -> Dict[str, str]:
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
        "abstract": {"name": "Abstract", "prompt": "Create an abstract art piece that conveys the day's rhythm and mood. Use symbolic motifs rather than literal UI screens."},
        "watercolor": {"name": "Watercolor", "prompt": "Create a watercolor illustration with paper texture, soft bleeding edges, and light washes."},
        "pixel_art": {"name": "Pixel Art", "prompt": "Create a pixel art scene (16-bit style), readable silhouettes, mini-scenes for the day's major activities."},
        "isometric": {"name": "Isometric", "prompt": "Create an isometric diorama of a desk/workspace and surrounding mini-scenes. Clean lines, subtle shadows."},
        "minimalist": {"name": "Minimalist", "prompt": "Create a minimalist poster-like illustration with few shapes and strong composition, using icons to represent activities."},
        "cyberpunk": {"name": "Cyberpunk", "prompt": "Create a cyberpunk illustration with neon lighting, high contrast, futuristic motifs, tasteful not overly dark."},
    }
    return presets.get(style_preset, presets["year_in_review_cute"])


def _vibe_analysis_prompt(timeline_text: str, google_text: str) -> str:
    return f"""
You are given a user's desktop-usage timeline for a single day, and optionally their Google Calendar/Tasks summary.

Task A — Vibe analysis:
Infer the day's vibe. Choose ONE primary vibe label from:
["hurried_anxious", "calm_relaxed", "creative_flow", "deep_focus", "distracted_scattered", "social_connected", "learning_mode", "mixed_unclear"].

Task B — Caring message:
Write a supportive message that feels warm and human (not cheesy).

Task C — Plan follow-through (if Google info exists):
Compare timeline and plan items. Estimate completion rate 0-100 and list 2-5 bullets of evidence (high-level, no private titles).

Hard rules:
- Do NOT reveal sensitive content. Do NOT include personal names, passwords, financial or medical details.
- Base your reasoning ONLY on the provided text.
- Output STRICT JSON only, with keys exactly:
{{
  "primary_vibe": "...",
  "confidence": 0.0,
  "why": ["...","...","..."],
  "notable_patterns": ["...","..."],
  "caring_message": "...",
  "quote": "...",
  "humor_alt": "...",
  "plan_follow_through": {{
      "has_google_data": true,
      "estimated_completion_pct": 0,
      "evidence": ["...","..."]
  }}
}}

Timeline:
{timeline_text}

Google (optional):
{google_text}
""".strip()


def _redraw_image_prompt(cfg: AppConfig, timeline_text: str, style_block: str) -> str:
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
- Target size hint: {cfg.target_image_hint}

Timeline (for inspiration, do not copy literal text):
{timeline_text}
""".strip()


# ---------------- Robust JSON helpers ----------------

def _extract_first_json_object(text: str) -> Optional[str]:
    if not text:
        return None
    s = text.strip()

    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()

    # Direct JSON object
    if s.startswith("{") and s.endswith("}"):
        return s

    # Best-effort first { ... } object
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None
    return m.group(0).strip()


def _loads_json_robust(text: str) -> Dict[str, Any]:
    if not text or not text.strip():
        raise ValueError("Empty model text")
    s = text.strip()
    try:
        return json.loads(s)
    except Exception:
        extracted = _extract_first_json_object(s)
        if not extracted:
            raise
        return json.loads(extracted)


def _call_generate_with_quota_retry(
    client: genai.Client,
    model: str,
    contents,
    temperature: float,
    max_retries: int = 6,
):
    """
    Handles free-tier 429 RESOURCE_EXHAUSTED by sleeping and retrying.
    """
    for attempt in range(max_retries + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                ),
            )
        except Exception as e:
            msg = str(e)

            if ("429" not in msg) and ("RESOURCE_EXHAUSTED" not in msg):
                raise

            # Parse "Please retry in XXs" if present
            delay = None
            m = re.search(r"Please retry in\s+([0-9.]+)s", msg)
            if m:
                delay = float(m.group(1))
            else:
                delay = min(60.0, (2.0 ** attempt)) + random.uniform(0.0, 1.0)

            if attempt >= max_retries:
                raise

            print(f"[quota] 429, sleeping {delay:.1f}s then retry (attempt {attempt+1}/{max_retries})...")
            time.sleep(delay)


def _call_gemini_text_json(cfg: AppConfig, client: genai.Client, prompt: str) -> Dict[str, Any]:
    """
    Robust JSON call:
    - gemini-2.5-flash: no thinking_config
    - strips code fences / extracts JSON object
    - retries once with strict instruction
    - 429 quota sleep+retry
    """
    resp = _call_generate_with_quota_retry(
        client=client,
        model=cfg.gemini_text_model,
        contents=[prompt],
        temperature=0.2,
    )
    text = (resp.text or "").strip()

    try:
        return _loads_json_robust(text)
    except Exception:
        hard = prompt + "\n\nIMPORTANT: Output ONLY valid JSON. No prose. No markdown. No code fences."
        resp2 = _call_generate_with_quota_retry(
            client=client,
            model=cfg.gemini_text_model,
            contents=[hard],
            temperature=0.0,
        )
        text2 = (resp2.text or "").strip()
        return _loads_json_robust(text2)


def _extract_image_bytes_from_response(resp: Any) -> Optional[Tuple[bytes, str]]:
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


def _call_gemini_generate_image(cfg: AppConfig, client: genai.Client, prompt: str) -> Tuple[bytes, str]:
    # image generation can also hit 429; reuse the same retry wrapper
    resp = _call_generate_with_quota_retry(
        client=client,
        model=cfg.gemini_image_model,
        contents=[prompt],
        temperature=0.7,
    )
    extracted = _extract_image_bytes_from_response(resp)
    if not extracted:
        txt = (resp.text or "").strip()
        raise RuntimeError("No image bytes found in response. Model returned text only:\n" + txt)
    return extracted[0], extracted[1]


def build_daily_report(
    cfg: AppConfig,
    timeline_path: str,
    out_dir: str,
    google_today_path: Optional[str] = None,
) -> Dict[str, str]:
    api_key = cfg.gemini_api_key()
    if not api_key:
        raise RuntimeError(f"Missing Gemini API key. Please set env: {cfg.gemini_api_key_env}")

    timeline = _load_json(timeline_path)
    timeline_text = _timeline_to_compact_text(cfg, timeline)

    google_text = "N/A"
    has_google = False
    if google_today_path and os.path.exists(google_today_path):
        has_google = True
        google_obj = _load_json(google_today_path)
        cal_n = len(google_obj.get("calendar", {}).get("items", []))
        task_n = len(google_obj.get("tasks", {}).get("items", []))
        google_text = f"Calendar items: {cal_n}; Tasks due today: {task_n}."

    client = genai.Client(api_key=api_key)

    vibe_prompt = _vibe_analysis_prompt(timeline_text, google_text)
    vibe = _call_gemini_text_json(cfg, client, vibe_prompt)

    style = _style_prompt(cfg.style_preset)
    img_prompt = _redraw_image_prompt(cfg, timeline_text, style["prompt"])
    img_bytes, img_mime = _call_gemini_generate_image(cfg, client, img_prompt)

    ensure_dir(out_dir)

    date_local = timeline.get("date_local", datetime.now().strftime("%Y-%m-%d"))
    img_ext = ".png" if "png" in (img_mime or "").lower() else ".jpg"
    img_name = f"redraw_{date_local}_{cfg.style_preset}{img_ext}"
    img_path = os.path.join(out_dir, img_name)

    with open(img_path, "wb") as f:
        f.write(img_bytes)

    report = {
        "schema_version": "1.0",
        "date_local": date_local,
        "timezone": cfg.timezone_name,
        "inputs": {
            "timeline_json": os.path.abspath(timeline_path),
            "google_today_json": os.path.abspath(google_today_path) if has_google else None,
            "style_preset": cfg.style_preset,
            "style_name": style["name"],
        },
        "outputs": {
            "vibe": vibe,
            "image": {
                "file": img_path.replace("\\", "/"),
                "mime_type": img_mime,
            }
        },
        "ui_modules": {
            "timeline": "Render timeline_human_readable + segments",
            "redraw": "Show redraw image + short caption",
            "caring": "Show caring_message + quote + humor_alt",
            "plan": "Show estimated_completion_pct if has_google_data"
        }
    }

    if cfg.avoid_sensitive_text:
        def scrub(x: Any) -> Any:
            if isinstance(x, str):
                return _sanitize_text(x)
            if isinstance(x, list):
                return [scrub(i) for i in x]
            if isinstance(x, dict):
                return {k: scrub(v) for k, v in x.items()}
            return x
        report = scrub(report)

    report_path = os.path.join(out_dir, f"daily_report_{date_local}.json")
    _write_json(report_path, report)

    return {"report_json": report_path, "image_path": img_path}
