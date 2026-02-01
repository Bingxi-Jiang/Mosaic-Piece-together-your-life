from dataclasses import dataclass, field
from typing import List, Optional
import os


@dataclass
class AppConfig:
    # ---------- runtime ----------
    timezone_name: str = "America/Los_Angeles"
    screenshot_interval_sec: int = 60
    stop_time_local: str = "23:00"

    # ---------- storage ----------
    screenshot_root: str = "screenshots"
    artifacts_dirname: str = "artifacts"
    session_log_name: str = "session_log.jsonl"

    # ---------- blacklist ----------
    blacklist_keywords: List[str] = field(default_factory=lambda: [
        "WeChat", "微信", "Facebook", "Instagram", "TikTok"
    ])
    blacklist_poll_interval_sec: int = 2

    # ---------- Gemini ----------
    gemini_api_key_env: str = "GEMINI_API_KEY"
    gemini_text_model: str = "gemini-3-flash-preview"
    gemini_image_model: str = "gemini-3-pro-image-preview"

    # ---------- timeline ----------
    # capture_interval_minutes is a fallback; the pipeline will infer interval from filenames.
    capture_interval_minutes: int = 15
    enable_preprocess: bool = True
    preprocess_format: str = "png"   # "png" or "jpeg"
    jpeg_quality: int = 78
    downscale_ratio: float = 0.55
    min_long_edge: int = 900
    max_long_edge: int = 1600
    request_sleep_seconds: float = 0.2

    # idle / AFK detection (best-effort)
    # If two consecutive screenshots are very similar and far apart in time, we carve out an Idle segment.
    idle_gap_minutes: int = 20
    idle_similarity_threshold: float = 0.985
    idle_margin_minutes: int = 5

    # ---------- generation ----------
    style_preset: str = "year_in_review_cute"
    avoid_sensitive_text: bool = True
    target_image_hint: str = "1024x1024"

    # ---------- Google ----------
    google_scopes: List[str] = field(default_factory=lambda: [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/tasks.readonly",
    ])
    google_credentials_file: str = "credentials.json"
    google_token_file: str = "token_combined.json"

    def gemini_api_key(self) -> Optional[str]:
        return os.environ.get(self.gemini_api_key_env)
