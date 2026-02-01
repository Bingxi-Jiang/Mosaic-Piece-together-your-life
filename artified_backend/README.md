# Artified Backend (Integrated)

## Quick start

1) Set Gemini key (Windows PowerShell)
```powershell
$env:GEMINI_API_KEY="YOUR_KEY"
```

2) Simulate a day from existing screenshots (no need to wait a full day)
```bash
python main.py simulate-day --source screenshots --outroot screenshots_test --seed 42
```

3) Build all artifacts for a day folder
```bash
python main.py build-all --daydir screenshots_test/2026/January/31 --date 2026-01-31
```

4) Real capture mode (until stop time)
```bash
python main.py run --stop 23:00 --interval 900
```

Artifacts will be written into:
`<day_dir>/artifacts/`
