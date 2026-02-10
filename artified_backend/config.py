from dataclasses import dataclass, field
from typing import List, Optional
import os
import json
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent


def _default_data_dir() -> str:
    env = os.getenv("MOSAIC_DATA_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.expanduser("~/Documents/Mosaic"))


def _default_screenshot_root() -> str:
    env = os.getenv("MOSAIC_SCREENSHOT_ROOT")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(_default_data_dir(), "screenshots")


def _default_google_credentials_file() -> str:
    env = os.getenv("GOOGLE_OAUTH_CLIENT_JSON")
    if env:
        return os.path.abspath(os.path.expanduser(env))

    p1 = os.path.join(_default_data_dir(), "secrets", "google_oauth_client.json")
    if os.path.exists(p1):
        return p1

    return os.path.abspath(os.path.expanduser("artified_backend/secrets/google_oauth_client.json"))


def _default_google_token_file() -> str:
    env = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(_default_data_dir(), "secrets", "token.json")


def _default_privacy_config_file() -> str:
    """
    Priority:
      1) MOSAIC_PRIVACY_CONFIG
      2) <DATA_DIR>/privacy_config.json
      3) <project_root>/privacy_config.json
    """
    env = os.getenv("MOSAIC_PRIVACY_CONFIG")
    if env:
        return os.path.abspath(os.path.expanduser(env))

    p_data = os.path.join(_default_data_dir(), "privacy_config.json")
    if os.path.exists(p_data):
        return p_data

    p_root = os.path.abspath(os.path.join(_BASE_DIR, "..", "privacy_config.json"))
    return p_root


def _load_json(path: str) -> dict:
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _as_str_list(x) -> List[str]:
    if isinstance(x, list):
        return [v for v in x if isinstance(v, str)]
    return []


@dataclass
class AppConfig:
    # ---------- runtime ----------
    timezone_name: str = "America/Los_Angeles"
    screenshot_interval_sec: int = 60
    stop_time_local: str = "23:00"

    # ---------- storage (UNIFIED) ----------
    data_dir: str = field(default_factory=_default_data_dir)
    screenshot_root: str = field(default_factory=_default_screenshot_root)
    artifacts_dirname: str = "artifacts"
    session_log_name: str = "session_log.jsonl"

    # ---------- privacy config ----------
    privacy_config_file: str = field(default_factory=_default_privacy_config_file)

    # ---------- blacklist (legacy, still supported) ----------
    blacklist_keywords: List[str] = field(default_factory=lambda: [
        "WeChat", "微信", "Facebook", "Instagram", "TikTok"
    ])
    blacklist_poll_interval_sec: int = 2

    # ---------- blacklist (new, recommended) ----------
    blacklist_title_keywords: List[str] = field(default_factory=list)
    blacklist_app_names: List[str] = field(default_factory=list)
    blacklist_url_keywords: List[str] = field(default_factory=list)

    # ---------- Gemini ----------
    gemini_api_key_env: str = "GEMINI_API_KEY"
    gemini_text_model: str = "gemini-3-flash-preview"
    gemini_image_model: str = "gemini-3-pro-image-preview"

    # ---------- timeline ----------
    capture_interval_minutes: int = 15
    enable_preprocess: bool = True
    preprocess_format: str = "png"   # "png" or "jpeg"
    jpeg_quality: int = 78
    downscale_ratio: float = 0.55
    min_long_edge: int = 900
    max_long_edge: int = 1600

    # ---------- timeline / quota control ----------
    request_sleep_seconds: float = 12.5
    timeline_sample_stride: int = 6
    timeline_max_frames: int = 60

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
    google_credentials_file: str = field(default_factory=_default_google_credentials_file)
    google_token_file: str = field(default_factory=_default_google_token_file)

    def __post_init__(self):
        # normalize paths
        self.data_dir = os.path.abspath(os.path.expanduser(self.data_dir))
        self.screenshot_root = os.path.abspath(os.path.expanduser(self.screenshot_root))
        self.google_credentials_file = os.path.abspath(os.path.expanduser(self.google_credentials_file))
        self.google_token_file = os.path.abspath(os.path.expanduser(self.google_token_file))
        self.privacy_config_file = os.path.abspath(os.path.expanduser(self.privacy_config_file))

        # ensure dirs exist
        os.makedirs(self.screenshot_root, exist_ok=True)
        os.makedirs(os.path.dirname(self.google_token_file), exist_ok=True)

        # load privacy_config.json (optional)
        cfg = _load_json(self.privacy_config_file)

        # =========================
        # ✅ Preferred (web UI) format:
        # {
        #   "blocked_apps": [...],
        #   "blocked_keywords": [...]
        # }
        # =========================
        blocked_apps = _as_str_list(cfg.get("blocked_apps"))
        blocked_keywords = _as_str_list(cfg.get("blocked_keywords"))

        # =========================
        # Existing format (older):
        # {
        #   "blacklist": {
        #     "title_keywords": [...],
        #     "app_names": [...],
        #     "url_keywords": [...]
        #   }
        # }
        # =========================
        bl = cfg.get("blacklist") if isinstance(cfg.get("blacklist"), dict) else {}
        title_kws = _as_str_list(bl.get("title_keywords"))
        app_names = _as_str_list(bl.get("app_names"))
        url_kws = _as_str_list(bl.get("url_keywords"))

        # Backward compatibility:
        # { "blacklist_keywords": [...] } or bl["keywords"]
        legacy = _as_str_list(cfg.get("blacklist_keywords"))
        if not legacy:
            legacy = _as_str_list(bl.get("keywords"))

        # =========================
        # Merge priority:
        # 1) blocked_* (web UI)
        # 2) blacklist.* (new structured)
        # 3) legacy keys
        # 4) default blacklist_keywords
        # =========================
        if blocked_apps:
            self.blacklist_app_names = blocked_apps
        else:
            self.blacklist_app_names = app_names

        kw_source: List[str] = []
        if blocked_keywords:
            kw_source = blocked_keywords
        elif title_kws:
            kw_source = title_kws
        elif legacy:
            kw_source = legacy
        else:
            kw_source = list(self.blacklist_keywords)

        # Apply keywords to title + url for best coverage (title/url often differ)
        self.blacklist_title_keywords = list(kw_source)
        self.blacklist_url_keywords = url_kws if url_kws else list(kw_source)

        # keep legacy field in sync for logging/UI if explicitly set
        if legacy:
            self.blacklist_keywords = legacy

    def gemini_api_key(self) -> Optional[str]:
        return "GEMINI_KEY"
        #return os.environ.get(self.gemini_api_key_env)
