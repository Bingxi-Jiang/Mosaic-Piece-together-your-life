import os
import json
import time
import argparse
from datetime import date as ddate

from config import AppConfig
from utils_time import now_local, today_local_date, is_past_stop_time
from utils_paths import ensure_dir, day_folder, artifacts_dir

from services.screenshot_service import take_screenshot_to
from services.app_monitor import check_blacklist

from pipelines.timeline_pipeline import build_timeline
from pipelines.trigger_pipeline import build_feedback_events
from pipelines.google_export_pipeline import export_google_today
from pipelines.daily_report_pipeline import build_daily_report

from tools.simulate_day import simulate_random_day


def _append_jsonl(path: str, obj: dict) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run_capture(cfg: AppConfig) -> str:
    today = today_local_date(cfg.timezone_name)
    day_dir = day_folder(cfg.screenshot_root, today)
    ensure_dir(day_dir)

    log_path = os.path.join(day_dir, cfg.session_log_name)

    paused = False
    pause_reason = None

    _append_jsonl(log_path, {
        "type": "session_start",
        "ts": now_local(cfg.timezone_name).isoformat(),
        "day_dir": os.path.abspath(day_dir),
        "stop_time_local": cfg.stop_time_local,
        "interval_sec": cfg.screenshot_interval_sec,
        "blacklist": cfg.blacklist_keywords,
    })

    while True:
        now_dt = now_local(cfg.timezone_name)

        if is_past_stop_time(now_dt, cfg.stop_time_local):
            _append_jsonl(log_path, {
                "type": "session_stop_time_reached",
                "ts": now_dt.isoformat(),
                "stop_time_local": cfg.stop_time_local,
            })
            break

        hit, info = check_blacklist(cfg.blacklist_keywords)
        if hit:
            if not paused:
                paused = True
                pause_reason = {"keyword": info.keyword, "title": info.window_title} if info else None
                _append_jsonl(log_path, {
                    "type": "pause_capture",
                    "ts": now_dt.isoformat(),
                    "reason": pause_reason,
                })
            time.sleep(cfg.blacklist_poll_interval_sec)
            continue

        if paused:
            paused = False
            _append_jsonl(log_path, {
                "type": "resume_capture",
                "ts": now_dt.isoformat(),
                "reason": pause_reason,
            })
            pause_reason = None

        path = take_screenshot_to(day_dir, now_dt)
        _append_jsonl(log_path, {
            "type": "screenshot",
            "ts": now_dt.isoformat(),
            "file": path.replace("\\", "/"),
        })

        time.sleep(cfg.screenshot_interval_sec)

    _append_jsonl(log_path, {
        "type": "session_end",
        "ts": now_local(cfg.timezone_name).isoformat(),
    })

    return day_dir


def build_all_artifacts(cfg: AppConfig, day_dir: str, day: ddate) -> dict:
    out_dir = artifacts_dir(day_dir, cfg.artifacts_dirname)
    ensure_dir(out_dir)

    timeline_path = build_timeline(cfg, day_dir=day_dir, day_date=day, out_dir=out_dir)
    feedback_path = build_feedback_events(cfg, timeline_path=timeline_path, out_dir=out_dir)

    google_path = None
    try:
        google_path = export_google_today(cfg, out_dir=out_dir, day=day)
    except Exception as e:
        _append_jsonl(os.path.join(day_dir, cfg.session_log_name), {
            "type": "google_export_failed",
            "ts": now_local(cfg.timezone_name).isoformat(),
            "error": str(e),
        })

    report_out = build_daily_report(cfg, timeline_path=timeline_path, out_dir=out_dir, google_today_path=google_path)

    return {
        "day_dir": os.path.abspath(day_dir),
        "artifacts_dir": os.path.abspath(out_dir),
        "timeline_json": os.path.abspath(timeline_path),
        "feedback_events_json": os.path.abspath(feedback_path),
        "google_today_json": os.path.abspath(google_path) if google_path else None,
        "daily_report_json": os.path.abspath(report_out["report_json"]),
        "redraw_image": os.path.abspath(report_out["image_path"]),
    }


def main():
    cfg = AppConfig()

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run real capture service until stop_time, then build artifacts")
    p_run.add_argument("--stop", default=cfg.stop_time_local, help="HH:MM local stop time")
    p_run.add_argument("--interval", type=int, default=cfg.screenshot_interval_sec, help="screenshot interval seconds")

    p_sim = sub.add_parser("simulate-day", help="Generate a simulated test day folder from existing screenshots")
    p_sim.add_argument("--source", default="screenshots", help="source screenshots root")
    p_sim.add_argument("--outroot", default="screenshots_test", help="output screenshots root")
    p_sim.add_argument("--seed", type=int, default=42)

    p_build = sub.add_parser("build-all", help="Build artifacts for an existing day_dir (no capture)")
    p_build.add_argument("--daydir", required=True, help="Path like screenshots/.../DD or screenshots_test/.../DD")
    p_build.add_argument("--date", required=True, help="YYYY-MM-DD")

    args = parser.parse_args()

    if args.cmd == "run":
        cfg.stop_time_local = args.stop
        cfg.screenshot_interval_sec = args.interval

        day_dir = run_capture(cfg)
        day = today_local_date(cfg.timezone_name)

        result = build_all_artifacts(cfg, day_dir=day_dir, day=day)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.cmd == "simulate-day":
        out_day_dir = simulate_random_day(
            source_root=args.source,
            output_root=args.outroot,
            random_seed=args.seed,
        )
        print(out_day_dir)
        return

    if args.cmd == "build-all":
        y, m, d = args.date.split("-")
        day = ddate(int(y), int(m), int(d))
        result = build_all_artifacts(cfg, day_dir=args.daydir, day=day)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
