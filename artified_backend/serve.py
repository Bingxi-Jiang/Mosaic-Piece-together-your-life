# artified_backend/serve.py
import os
import json
import time
import secrets
import sys
import threading
from datetime import datetime, date as ddate
from typing import Optional, List, Dict, Any
import traceback
from zoneinfo import ZoneInfo


from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config import AppConfig
from .utils_paths import day_folder, artifacts_dir

# ✅ call main.py build function directly
from .main import build_all_artifacts

# ✅ blacklist checker (USED by web capture loop)
from .services.app_monitor import check_blacklist

# ✅ Google export pipeline
from .pipelines.google_export_pipeline import export_google_today

# Google OAuth
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials


def resource_path(rel_path: str) -> str:
    """
    Works for dev + PyInstaller onefile.
    In onefile mode, files are unpacked to sys._MEIPASS.
    """
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    return os.path.join(base, rel_path)


app = FastAPI()
cfg = AppConfig()

# ✅ unified data root
DATA_DIR = os.environ.get("MOSAIC_DATA_DIR", os.path.abspath(os.path.expanduser("~/Documents/Mosaic")))
DATA_DIR = os.path.abspath(os.path.expanduser(DATA_DIR))

# ✅ unify screenshots root
cfg.data_dir = DATA_DIR
cfg.screenshot_root = os.path.join(DATA_DIR, "screenshots")
os.makedirs(cfg.screenshot_root, exist_ok=True)

# ✅ unify privacy_config location (web UI reads/writes this)
cfg.privacy_config_file = os.path.join(DATA_DIR, "privacy_config.json")
os.makedirs(os.path.dirname(cfg.privacy_config_file) or ".", exist_ok=True)
if not os.path.exists(cfg.privacy_config_file):
    with open(cfg.privacy_config_file, "w", encoding="utf-8") as f:
        json.dump({"blocked_apps": [], "blocked_keywords": []}, f, ensure_ascii=False, indent=2)

print(f"[Mosaic] DATA_DIR = {DATA_DIR}")
print(f"[Mosaic] screenshot_root = {cfg.screenshot_root}")
print(f"[Mosaic] privacy_config_file = {cfg.privacy_config_file}")


# ----------------------------
# CORS (dev friendly)
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # prod: set to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------
# Static mounts
# ----------------------------
app.mount("/screenshots", StaticFiles(directory=cfg.screenshot_root), name="screenshots")

WEB_DIR = resource_path("web")
if os.path.isdir(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))
else:
    @app.get("/", response_class=HTMLResponse)
    def index_missing():
        return HTMLResponse(f"<h3>web/ folder not found: {WEB_DIR}</h3>")


# ----------------------------
# Helpers: day dirs / artifacts
# ----------------------------
def _list_day_dirs(root: str) -> list[str]:
    out = []
    if not os.path.isdir(root):
        return out
    for y in sorted(os.listdir(root)):
        ydir = os.path.join(root, y)
        if not os.path.isdir(ydir):
            continue
        for mon in sorted(os.listdir(ydir)):
            mdir = os.path.join(ydir, mon)
            if not os.path.isdir(mdir):
                continue
            for dd in sorted(os.listdir(mdir)):
                ddir = os.path.join(mdir, dd)
                if os.path.isdir(ddir):
                    out.append(ddir)
    return out


def _parse_day_dir_to_date(day_dir: str) -> Optional[ddate]:
    parts = day_dir.replace("\\", "/").split("/")
    if len(parts) < 3:
        return None
    try:
        yyyy = int(parts[-3])
        mon_name = parts[-2]
        dd = int(parts[-1])
        mon_num = datetime.strptime(mon_name, "%B").month
        return ddate(yyyy, mon_num, dd)
    except Exception:
        return None


def _latest_day_dir(root: str) -> Optional[str]:
    day_dirs = _list_day_dirs(root)
    dated = []
    for ddir in day_dirs:
        dt = _parse_day_dir_to_date(ddir)
        if dt:
            dated.append((dt, ddir))
    if not dated:
        return None
    dated.sort(key=lambda x: x[0])
    return dated[-1][1]


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _find_artifact(day_dir: str, prefix: str) -> Optional[str]:
    adir = artifacts_dir(day_dir, cfg.artifacts_dirname)
    if not os.path.isdir(adir):
        return None
    for name in os.listdir(adir):
        if name.startswith(prefix) and name.endswith(".json"):
            return os.path.join(adir, name)
    return None


def _find_redraw(day_dir: str) -> Optional[str]:
    adir = artifacts_dir(day_dir, cfg.artifacts_dirname)
    if not os.path.isdir(adir):
        return None
    for name in os.listdir(adir):
        if name.startswith("redraw_") and name.lower().endswith((".png", ".jpg", ".jpeg")):
            return os.path.join(adir, name)
    return None


def _list_screenshots(day_dir: str) -> List[str]:
    if not os.path.isdir(day_dir):
        return []
    out = []
    for name in os.listdir(day_dir):
        if name.lower().endswith((".png", ".jpg", ".jpeg")):
            out.append(name)
    out.sort()
    return out


def _strip_redraw_outputs(day_dir: str, day: ddate) -> Dict[str, Any]:
    """
    Build(无redraw) 用：删掉 artifacts 里的 redraw_* 图片，并把 daily_report outputs.image 相关字段清掉。
    """
    adir = artifacts_dir(day_dir, cfg.artifacts_dirname)
    os.makedirs(adir, exist_ok=True)

    removed_files: List[str] = []

    # 1) delete redraw_*.(png/jpg/jpeg)
    try:
        for name in os.listdir(adir):
            low = name.lower()
            if name.startswith("redraw_") and low.endswith((".png", ".jpg", ".jpeg")):
                p = os.path.join(adir, name)
                try:
                    os.remove(p)
                    removed_files.append(p)
                except Exception:
                    pass
    except Exception:
        pass

    # 2) patch daily_report json (if exists)
    report_prefix = f"daily_report_{day.isoformat()}"
    report_path = _find_artifact(day_dir, report_prefix)
    patched = False
    if report_path and os.path.exists(report_path):
        try:
            data = _read_json(report_path)
            if isinstance(data, dict):
                outputs = data.get("outputs")
                if isinstance(outputs, dict):
                    image = outputs.get("image")
                    if isinstance(image, dict):
                        # clear anything that points to redraw
                        for k in [
                            "redraw_url", "url", "file", "path", "image_path", "redraw_image",
                            "mime_type", "prompt", "model", "notes"
                        ]:
                            if k in image:
                                image.pop(k, None)
                        # if you prefer: remove image entirely when empty
                        if not image:
                            outputs.pop("image", None)
                        patched = True
            if patched:
                _write_json(report_path, data)
        except Exception:
            patched = False

    return {
        "redraw_removed": len(removed_files),
        "report_patched": patched,
    }


# ----------------------------
# Privacy config helpers (web UI)
# ----------------------------
def _reload_privacy_into_cfg() -> Dict[str, Any]:
    """
    Reload blacklist fields from cfg.privacy_config_file
    Format:
      { "blocked_apps": [...], "blocked_keywords": [...] }
    """
    try:
        data = _read_json(cfg.privacy_config_file) if os.path.exists(cfg.privacy_config_file) else {}
    except Exception:
        data = {}

    apps = data.get("blocked_apps") if isinstance(data.get("blocked_apps"), list) else []
    kws = data.get("blocked_keywords") if isinstance(data.get("blocked_keywords"), list) else []

    apps = [x.strip() for x in apps if isinstance(x, str) and x.strip()]
    kws = [x.strip() for x in kws if isinstance(x, str) and x.strip()]

    cfg.blacklist_app_names = apps
    cfg.blacklist_title_keywords = kws
    cfg.blacklist_url_keywords = kws

    return {
        "privacy_config_file": os.path.abspath(cfg.privacy_config_file),
        "blocked_apps": cfg.blacklist_app_names,
        "blocked_keywords": cfg.blacklist_title_keywords,
    }


# ----------------------------
# URL normalization helpers
# ----------------------------
def _to_screenshots_url_from_abs(abs_path: str) -> Optional[str]:
    if not abs_path:
        return None
    root = os.path.abspath(cfg.screenshot_root)
    try:
        rel = os.path.relpath(os.path.abspath(abs_path), root).replace("\\", "/")
    except Exception:
        return None
    if rel.startswith(".."):
        return None
    return f"/screenshots/{rel}"


def _to_screenshots_url_from_maybe_path(p: str) -> Optional[str]:
    if not p or not isinstance(p, str):
        return None

    s = p.replace("\\", "/").strip()

    if s.startswith("/screenshots/"):
        return s

    if s.startswith("artified_backend/screenshots/"):
        return "/" + s.replace("artified_backend/screenshots/", "screenshots/", 1)

    if s.startswith("screenshots/"):
        return "/" + s

    if os.path.isabs(s):
        url = _to_screenshots_url_from_abs(s)
        if url:
            return url

        marker = "/artified_backend/screenshots/"
        if marker in s:
            tail = s.split(marker, 1)[1]
            return "/screenshots/" + tail.lstrip("/")

    return None


def _patch_report_urls(data: dict, day_dir: str) -> dict:
    if not isinstance(data, dict):
        return data

    outputs = data.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
        data["outputs"] = outputs

    image = outputs.get("image")
    if not isinstance(image, dict):
        image = {}
        outputs["image"] = image

    redraw_abs = _find_redraw(day_dir)
    if redraw_abs:
        url = _to_screenshots_url_from_abs(redraw_abs)
        if url:
            image["redraw_url"] = url
            image["file"] = url

    for k in ["redraw_url", "url", "file", "path", "image_path", "redraw_image"]:
        v = image.get(k)
        if isinstance(v, str) and v:
            norm = _to_screenshots_url_from_maybe_path(v)
            if norm:
                image["redraw_url"] = image.get("redraw_url") or norm
                if k in ("file", "path", "image_path", "redraw_image"):
                    image[k] = norm

    if "redraw_url" not in image and redraw_abs:
        url = _to_screenshots_url_from_abs(redraw_abs)
        if url:
            image["redraw_url"] = url

    # if redraw removed -> clean empty
    if not _find_redraw(day_dir):
        if isinstance(outputs.get("image"), dict) and not outputs["image"]:
            outputs.pop("image", None)

    return data


# ----------------------------
# API: basic
# ----------------------------
@app.get("/api/health")
def api_health():
    return {
        "ok": True,
        "data_dir": DATA_DIR,
        "screenshot_root": cfg.screenshot_root,
        "privacy_config_file": cfg.privacy_config_file,
        "blacklist": _reload_privacy_into_cfg(),
        "google_token_file": getattr(cfg, "google_token_file", None),
    }


@app.get("/api/latest")
def api_latest():
    latest = _latest_day_dir(cfg.screenshot_root)
    if not latest:
        raise HTTPException(status_code=404, detail=f"No day folders found under {cfg.screenshot_root}")
    dt = _parse_day_dir_to_date(latest)
    return {"day_dir": os.path.abspath(latest), "date": dt.isoformat() if dt else None}


@app.get("/api/days")
def api_days():
    day_dirs = _list_day_dirs(cfg.screenshot_root)
    dates: List[str] = []
    for ddir in day_dirs:
        dt = _parse_day_dir_to_date(ddir)
        if dt:
            dates.append(dt.isoformat())
    dates = sorted(set(dates))
    return {"dates": dates}


# ----------------------------
# API: privacy config (web UI)
# ----------------------------
@app.get("/api/privacy/config")
def api_privacy_get():
    return _reload_privacy_into_cfg()


@app.post("/api/privacy/config")
def api_privacy_set(body: Dict[str, Any] = None):
    body = body or {}
    apps = body.get("blocked_apps", [])
    kws = body.get("blocked_keywords", [])

    if not isinstance(apps, list) or not isinstance(kws, list):
        raise HTTPException(status_code=400, detail="blocked_apps/blocked_keywords must be lists")

    apps = [x.strip() for x in apps if isinstance(x, str) and x.strip()]
    kws = [x.strip() for x in kws if isinstance(x, str) and x.strip()]

    data = {"blocked_apps": apps, "blocked_keywords": kws}
    try:
        with open(cfg.privacy_config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"write privacy_config failed: {e}")

    out = _reload_privacy_into_cfg()
    return {"ok": True, **out}


# ----------------------------
# API: per-day
# ----------------------------
@app.get("/api/day/{yyyy}-{mm}-{dd}/timeline")
def api_timeline(yyyy: int, mm: int, dd: int):
    day = ddate(yyyy, mm, dd)
    ddir = day_folder(cfg.screenshot_root, day)
    path = _find_artifact(ddir, f"timeline_{day.isoformat()}")
    if not path:
        raise HTTPException(status_code=404, detail="timeline not found")
    return _read_json(path)


@app.get("/api/day/{yyyy}-{mm}-{dd}/feedback")
def api_feedback(yyyy: int, mm: int, dd: int):
    day = ddate(yyyy, mm, dd)
    ddir = day_folder(cfg.screenshot_root, day)
    path = _find_artifact(ddir, f"feedback_events_{day.isoformat()}")
    if not path:
        raise HTTPException(status_code=404, detail="feedback not found")
    return _read_json(path)


@app.get("/api/day/{yyyy}-{mm}-{dd}/report")
def api_report(yyyy: int, mm: int, dd: int):
    day = ddate(yyyy, mm, dd)
    ddir = day_folder(cfg.screenshot_root, day)
    path = _find_artifact(ddir, f"daily_report_{day.isoformat()}")
    if not path:
        raise HTTPException(status_code=404, detail="daily report not found")
    data = _read_json(path)
    return _patch_report_urls(data, day_dir=ddir)


@app.get("/api/day/{yyyy}-{mm}-{dd}/redraw")
def api_redraw(yyyy: int, mm: int, dd: int):
    day = ddate(yyyy, mm, dd)
    ddir = day_folder(cfg.screenshot_root, day)
    img = _find_redraw(ddir)
    if not img:
        raise HTTPException(status_code=404, detail="redraw image not found")
    return FileResponse(img)


@app.get("/api/day/{yyyy}-{mm}-{dd}/screenshots")
def api_list_screenshots(yyyy: int, mm: int, dd: int):
    day = ddate(yyyy, mm, dd)
    ddir = day_folder(cfg.screenshot_root, day)
    if not os.path.isdir(ddir):
        raise HTTPException(status_code=404, detail="day dir not found")
    names = _list_screenshots(ddir)
    items = [{"filename": n, "url": f"/api/day/{day.isoformat()}/screenshot/{n}"} for n in names]
    return {"date": day.isoformat(), "count": len(items), "items": items}


@app.get("/api/day/{yyyy}-{mm}-{dd}/screenshot/{filename}")
def api_screenshot(yyyy: int, mm: int, dd: int, filename: str):
    day = ddate(yyyy, mm, dd)
    ddir = day_folder(cfg.screenshot_root, day)
    if not os.path.isdir(ddir):
        raise HTTPException(status_code=404, detail="day dir not found")
    filename = os.path.basename(filename)
    path = os.path.join(ddir, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="screenshot not found")
    return FileResponse(path)


# ============================================================
# Capture: background loop (thread) + blacklist auto pause/resume
# ============================================================
try:
    import mss
    from PIL import Image
except Exception:
    mss = None
    Image = None


class CaptureManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self.running = False
        self.paused = False
        self.started_ts: Optional[float] = None
        self.last_shot_ts: Optional[float] = None
        self.interval_sec = 60
        self.last_block: Optional[Dict[str, Any]] = None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "paused": self.paused,
                "interval_sec": self.interval_sec,
                "started_ts": datetime.fromtimestamp(self.started_ts).isoformat() if self.started_ts else None,
                "last_shot_ts": datetime.fromtimestamp(self.last_shot_ts).isoformat() if self.last_shot_ts else None,
                "last_block": self.last_block,
            }

    def start(self, interval_sec: int = 10):
        if mss is None or Image is None:
            raise RuntimeError("Missing deps for capture. Run: pip install mss pillow")

        with self._lock:
            if self.running:
                return
            self.interval_sec = max(1, int(interval_sec))
            self.running = True
            self.paused = False
            self.last_block = None
            self.started_ts = time.time()
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            if not self.running:
                return
            self._stop_evt.set()
            self.running = False
            self.paused = False
            self.last_block = None

    def pause(self, paused: bool):
        with self._lock:
            if not self.running:
                return
            self.paused = paused

    def _ensure_day_dir(self, dt: ddate) -> str:
        ddir = day_folder(cfg.screenshot_root, dt)
        os.makedirs(ddir, exist_ok=True)
        return ddir

    def _capture_once(self) -> str:
        dt = ddate.today()
        ddir = self._ensure_day_dir(dt)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(ddir, f"shot_{ts}.png")

        with mss.mss() as sct:
            monitor = sct.monitors[1]  # main display
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            img.save(out_path)

        print("[CAPTURE] saved:", out_path)
        return out_path

    def _loop(self):
        _reload_privacy_into_cfg()

        while not self._stop_evt.is_set():
            with self._lock:
                paused = self.paused
                running = self.running
                interval = self.interval_sec

            if not running:
                break

            try:
                _reload_privacy_into_cfg()
            except Exception:
                pass

            if not paused:
                try:
                    hit, info = check_blacklist(
                        cfg.blacklist_title_keywords,
                        app_names=cfg.blacklist_app_names,
                        url_keywords=cfg.blacklist_url_keywords,
                    )

                    if hit and info:
                        with self._lock:
                            self.paused = True
                            self.last_block = {
                                "kind": info.kind,
                                "keyword": info.keyword,
                                "window_title": info.window_title,
                                "app_name": info.app_name,
                                "url": info.url,
                                "ts": datetime.now().isoformat(timespec="seconds"),
                            }
                        print("[CAPTURE] paused by blacklist:", self.last_block)
                    else:
                        _ = self._capture_once()
                        with self._lock:
                            self.last_shot_ts = time.time()
                            self.last_block = None
                except Exception:
                    pass
            else:
                try:
                    hit, _ = check_blacklist(
                        cfg.blacklist_title_keywords,
                        app_names=cfg.blacklist_app_names,
                        url_keywords=cfg.blacklist_url_keywords,
                    )
                    if not hit:
                        with self._lock:
                            self.paused = False
                            self.last_block = None
                        print("[CAPTURE] resumed (blacklist cleared)")
                except Exception:
                    pass

            t0 = time.time()
            while time.time() - t0 < interval:
                if self._stop_evt.is_set():
                    break
                time.sleep(0.2)


CAP = CaptureManager()


@app.get("/api/capture/status")
def capture_status():
    return CAP.status()


@app.post("/api/capture/start")
def capture_start(body: Dict[str, Any] = None):
    body = body or {}
    interval = body.get("interval_sec", 60)
    try:
        CAP.start(interval_sec=int(interval))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return CAP.status()


@app.post("/api/capture/stop")
def capture_stop():
    CAP.stop()
    return CAP.status()


@app.post("/api/capture/pause")
def capture_pause(body: Dict[str, Any] = None):
    body = body or {}
    CAP.pause(bool(body.get("paused", True)))
    return CAP.status()


# ============================================================
# Build (no subprocess)
# ============================================================
def _build_for_date(day: ddate, *, with_redraw: bool) -> Dict[str, Any]:
    ddir = day_folder(cfg.screenshot_root, day)
    os.makedirs(ddir, exist_ok=True)

    try:
        imgs = [x for x in os.listdir(ddir) if x.lower().endswith((".png", ".jpg", ".jpeg"))]
    except Exception:
        imgs = []
    print("[BUILD] day_dir:", ddir, "images:", len(imgs), "with_redraw:", with_redraw)

    try:
        result = build_all_artifacts(cfg, day_dir=ddir, day=day)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"build failed: {type(e).__name__}: {e}")

    post = None
    if not with_redraw:
        post = _strip_redraw_outputs(ddir, day)

    return {
        "ok": True,
        "date": day.isoformat(),
        "day_dir": os.path.abspath(ddir),
        "with_redraw": with_redraw,
        "post_process": post,
        "result": result,
    }


@app.post("/api/build/today")
def api_build_today():
    # Build Today = full build (with redraw)
    return _build_for_date(ddate.today(), with_redraw=True)


@app.post("/api/build/latest")
def api_build_latest_full():
    # Keep old endpoint (full build) if you still need it somewhere
    latest = _latest_day_dir(cfg.screenshot_root)
    if not latest:
        raise HTTPException(status_code=404, detail="no day dir found")
    dt = _parse_day_dir_to_date(latest)
    if not dt:
        raise HTTPException(status_code=500, detail="latest day dir parse failed")
    return _build_for_date(dt, with_redraw=True)


@app.post("/api/build")
def api_build_latest_no_redraw():
    """
    Build = latest day, but NO redraw image
    """
    latest = _latest_day_dir(cfg.screenshot_root)
    if not latest:
        raise HTTPException(status_code=404, detail="no day dir found")
    dt = _parse_day_dir_to_date(latest)
    if not dt:
        raise HTTPException(status_code=500, detail="latest day dir parse failed")
    return _build_for_date(dt, with_redraw=False)


# ============================================================
# Google OAuth login (web flow) + auto export today
# ============================================================
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]

GOOGLE_CLIENT_SECRETS = resource_path(getattr(cfg, "google_client_secret_json", "credentials.json"))

# ✅ IMPORTANT: unify token path for BOTH web-flow + pipeline
GOOGLE_TOKEN_PATH = os.path.join(DATA_DIR, "token.json")
cfg.google_token_file = GOOGLE_TOKEN_PATH  # pipeline reads cfg.google_token_file

GOOGLE_REDIRECT_URI = getattr(cfg, "google_redirect_uri", "http://127.0.0.1:8000/api/auth/google/callback")
_GOOGLE_OAUTH_STATE = {"value": None}


def _save_google_token(creds: Credentials):
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    os.makedirs(os.path.dirname(GOOGLE_TOKEN_PATH) or ".", exist_ok=True)
    with open(GOOGLE_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _has_google_token() -> bool:
    return os.path.exists(GOOGLE_TOKEN_PATH)


def _ensure_google_today_export(day: ddate) -> str:
    ddir = day_folder(cfg.screenshot_root, day)
    os.makedirs(ddir, exist_ok=True)
    adir = artifacts_dir(ddir, cfg.artifacts_dirname)
    os.makedirs(adir, exist_ok=True)

    prefix = f"google_today_{day.isoformat()}"
    existing = _find_artifact(ddir, prefix)
    if existing and os.path.exists(existing):
        return existing

    out_path = export_google_today(cfg, out_dir=adir, day=day)
    return out_path


@app.get("/api/auth/google/status")
def google_auth_status():
    today = ddate.today()
    ddir = day_folder(cfg.screenshot_root, today)
    adir = artifacts_dir(ddir, cfg.artifacts_dirname)
    google_today_exists = False
    try:
        if os.path.isdir(adir):
            p = _find_artifact(ddir, f"google_today_{today.isoformat()}")
            google_today_exists = bool(p and os.path.exists(p))
    except Exception:
        google_today_exists = False

    return {
        "connected": _has_google_token(),
        "token_path": os.path.abspath(GOOGLE_TOKEN_PATH),
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "client_secrets": os.path.abspath(GOOGLE_CLIENT_SECRETS),
        "data_dir": DATA_DIR,
        "google_today_cached": google_today_exists,
        "today": today.isoformat(),
    }


@app.post("/api/auth/google/disconnect")
def google_auth_disconnect():
    if os.path.exists(GOOGLE_TOKEN_PATH):
        os.remove(GOOGLE_TOKEN_PATH)
    return {"ok": True, "connected": False}


@app.get("/api/auth/google/start")
def google_auth_start():
    if not os.path.exists(GOOGLE_CLIENT_SECRETS):
        raise HTTPException(status_code=500, detail=f"Missing client secrets: {GOOGLE_CLIENT_SECRETS}")

    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS,
        scopes=GOOGLE_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )
    state = secrets.token_urlsafe(24)
    _GOOGLE_OAUTH_STATE["value"] = state

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return {"auth_url": auth_url, "redirect_uri": GOOGLE_REDIRECT_URI}


@app.get("/api/auth/google/callback")
def google_auth_callback(code: str, state: str):
    if not _GOOGLE_OAUTH_STATE.get("value") or state != _GOOGLE_OAUTH_STATE["value"]:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS,
        scopes=GOOGLE_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_google_token(creds)

    # ✅ AUTO export google today
    try:
        _ = _ensure_google_today_export(ddate.today())
        print("[GOOGLE] auto-export today done")
    except Exception as e:
        print("[GOOGLE] auto-export failed:", repr(e))

    return RedirectResponse(url="/")


@app.get("/api/google/today")
def api_google_today(date: Optional[str] = None):
    if not _has_google_token():
        raise HTTPException(status_code=401, detail="Google not connected.")

    day = ddate.today()
    if isinstance(date, str) and date.strip():
        try:
            day = ddate.fromisoformat(date.strip())
        except Exception:
            raise HTTPException(status_code=400, detail="bad date, expected YYYY-MM-DD")

    try:
        path = _ensure_google_today_export(day)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"google today export failed: {type(e).__name__}: {e}")

    try:
        data = _read_json(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"read google today json failed: {e}")

    return data


# ============================================================
# Midnight Scheduler: 24:00 stop capture + build today (with redraw)
# ============================================================
_SCHED_STOP = threading.Event()
_SCHED_THREAD: Optional[threading.Thread] = None

def _seconds_until_next_midnight(tz_name: str) -> float:
    tz = ZoneInfo(tz_name or "America/Los_Angeles")
    now = datetime.now(tz)
    tomorrow = (now.date()).toordinal() + 1
    next_midnight = datetime.fromordinal(tomorrow).replace(tzinfo=tz)  # 00:00:00 tomorrow
    delta = (next_midnight - now).total_seconds()
    # safety floor
    return max(1.0, float(delta))

def _midnight_loop():
    print("[SCHED] midnight scheduler started")
    while not _SCHED_STOP.is_set():
        try:
            wait_sec = _seconds_until_next_midnight(cfg.timezone_name)
            print(f"[SCHED] next run in {wait_sec:.1f}s (tz={cfg.timezone_name})")

            # wait with interrupt ability
            t0 = time.time()
            while time.time() - t0 < wait_sec:
                if _SCHED_STOP.is_set():
                    return
                time.sleep(0.5)

            # === it's midnight ===
            print("[SCHED] midnight reached -> stop capture + build today")

            # 1) stop capture
            try:
                CAP.stop()
            except Exception as e:
                print("[SCHED] CAP.stop failed:", repr(e))

            # 2) build today WITH redraw
            try:
                _ = _build_for_date(ddate.today(), with_redraw=True)
                print("[SCHED] build today done")
            except Exception as e:
                print("[SCHED] build today failed:", repr(e))

        except Exception as e:
            print("[SCHED] scheduler loop error:", repr(e))
            time.sleep(2.0)

@app.on_event("startup")
def _startup_scheduler():
    global _SCHED_THREAD
    if _SCHED_THREAD and _SCHED_THREAD.is_alive():
        return
    _SCHED_STOP.clear()
    _SCHED_THREAD = threading.Thread(target=_midnight_loop, daemon=True)
    _SCHED_THREAD.start()

@app.on_event("shutdown")
def _shutdown_scheduler():
    _SCHED_STOP.set()


