# Artified Backend (Integrated)

A small backend that:
1) captures desktop screenshots on a fixed interval,
2) pauses capture when a blacklist app/window is visible,
3) turns screenshots into a day timeline (Gemini),
4) generates lightweight feedback events,
5) optionally exports Google Calendar + Tasks (today),
6) produces a daily report JSON + one “redraw of the day” image (Gemini image model).

It is designed so a future Web UI / desktop app can read stable JSON artifacts from one folder.

---

## Folder output

Screenshots are saved into a day folder:

```
screenshots/YYYY/Month/DD/HH-MM-SS.png
```

Artifacts are saved into:

```
<day_dir>/artifacts/
  timeline_YYYY-MM-DD.json
  feedback_events_YYYY-MM-DD.json
  google_today_YYYY-MM-DD.json        (optional)
  daily_report_YYYY-MM-DD.json
  redraw_YYYY-MM-DD_<style>.png
```

A session log is appended into:

```
<day_dir>/session_log.jsonl
```

---

## What each module does

### `main.py`
The CLI entrypoint.
- `run`: real capture loop (screenshot + blacklist pause). When stop time is reached, it also builds artifacts.
- `simulate-day`: creates a fake “full day” folder by shuffling existing screenshots.
- `build-all`: builds artifacts for an existing day folder (no screenshot capture).

### `services/screenshot_service.py`
Takes one screenshot using `PIL.ImageGrab` and saves it as `HH-MM-SS.png`.

### `services/app_monitor.py`
Checks visible window titles (via `pygetwindow`) against `blacklist_keywords`.
If a hit is found, capture is paused until the window is no longer visible.

### `pipelines/timeline_pipeline.py`
Reads screenshots in a day folder and calls Gemini (text model) to label each screenshot.
It then merges frames into segments and writes `timeline_*.json`.

Important:
- Segment timing is based on **real screenshot timestamps** in filenames.
- `capture_interval_minutes` in the output JSON is **inferred from the median gap** between screenshots.
- Smooth transitions: segment boundaries use **midpoints** between screenshots when the activity changes.
- Best-effort idle detection: if two consecutive screenshots are far apart and almost identical, an **Idle** segment is carved out.

### `pipelines/trigger_pipeline.py`
Generates simple “feedback events” from the timeline segments.
It is intentionally low frequency (hour-level reminders) and message text varies.

### `pipelines/google_export_pipeline.py`
(Optional) Exports today’s Google Calendar events and Tasks due today.
Requires OAuth files (`credentials.json` + token file).

### `pipelines/daily_report_pipeline.py`
Creates:
- a vibe + caring message JSON (Gemini text),
- a “redraw of the day” image (Gemini image model),
- a combined `daily_report_*.json`.

### `tools/simulate_day.py`
Creates a fake day folder from existing screenshots (for testing without waiting all day).

---

## Quick start

### 1) Install dependencies (typical)
You’ll need packages used by the scripts:
- pillow
- pygetwindow
- google-genai
- google-api-python-client
- google-auth, google-auth-oauthlib

(Exact install command depends on your environment.)

### 2) Set Gemini API key
Set the environment variable:

**Windows PowerShell**
```powershell
$env:GEMINI_API_KEY="YOUR_KEY"
```

**macOS/Linux**
```bash
export GEMINI_API_KEY="YOUR_KEY"
```

---

## Common commands

### A) Capture screenshots every 3 seconds
This writes into `screenshots/YYYY/Month/DD/`:

```bash
python main.py run --interval 3
```

By default, it stops at 23:00 local time. You can change stop time:

```bash
python main.py run --interval 3 --stop 23:59
```

Note: `run` will also build timeline/report after stop time is reached.

---

### B) Create a simulated test day (`screenshots_test`)
This is used to test the full pipeline quickly:

```bash
python main.py simulate-day --source screenshots --outroot screenshots_test --seed 42
```

It will output a new day folder like:
```
screenshots_test/YYYY/Month/DD/
```

---

### C) Build timeline + report for an existing day folder
Use this if you already have screenshots and want artifacts immediately:

```bash
python main.py build-all --daydir screenshots_test/2026/January/31 --date 2026-01-31
```

---

## Configuration

Most knobs are in `config.py` (class `AppConfig`), for example:
- screenshot interval / stop time
- blacklist keywords
- Gemini models
- idle detection thresholds:
  - `idle_gap_minutes`
  - `idle_similarity_threshold`
  - `idle_margin_minutes`
- report style preset (`style_preset`)

---

## Notes / troubleshooting

- Screenshot capture uses `PIL.ImageGrab`, which may require permissions on macOS.
- `pygetwindow` window listing behavior depends on OS/window manager.
- Google export is optional. If `credentials.json` is missing, the pipeline will skip Google and continue.
- If Gemini returns non-JSON text, you’ll see a JSON parse error. Tighten the prompt or reduce temperature.

