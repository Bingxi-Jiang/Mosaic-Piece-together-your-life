import os
import json
import datetime
from typing import Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import AppConfig
from utils_paths import ensure_dir


def _get_credentials(cfg: AppConfig) -> Credentials:
    creds = None
    if os.path.exists(cfg.google_token_file):
        creds = Credentials.from_authorized_user_file(cfg.google_token_file, cfg.google_scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(cfg.google_credentials_file):
                raise RuntimeError(f"Missing {cfg.google_credentials_file}. Needed for OAuth flow.")
            flow = InstalledAppFlow.from_client_secrets_file(cfg.google_credentials_file, cfg.google_scopes)
            creds = flow.run_local_server(port=0)

        with open(cfg.google_token_file, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return creds


def export_google_today(cfg: AppConfig, out_dir: str, day: datetime.date) -> str:
    creds = _get_credentials(cfg)
    cal_service = build("calendar", "v3", credentials=creds)
    task_service = build("tasks", "v1", credentials=creds)

    day_str = day.isoformat()

    now_utc = datetime.datetime.utcnow()
    start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
    end_of_day = now_utc.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + "Z"

    data_output: Dict[str, Any] = {
        "report_date": day_str,
        "export_timestamp": datetime.datetime.now().isoformat(),
        "calendar": {"summary": "今日历事件", "items": []},
        "tasks": {"summary": "今日截止任务", "items": []},
    }

    cal_results = cal_service.events().list(
        calendarId="primary",
        timeMin=start_of_day,
        timeMax=end_of_day,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    for event in cal_results.get("items", []):
        data_output["calendar"]["items"].append({
            "title": event.get("summary"),
            "start": event["start"].get("dateTime", event["start"].get("date")),
            "location": event.get("location", "N/A"),
        })

    task_lists = task_service.tasklists().list().execute().get("items", [])
    for t_list in task_lists:
        tasks = task_service.tasks().list(tasklist=t_list["id"]).execute().get("items", [])
        for task in tasks:
            due_date = task.get("due")
            if due_date and due_date.startswith(day_str):
                data_output["tasks"]["items"].append({
                    "title": task.get("title"),
                    "list_source": t_list["title"],
                    "status": task.get("status"),
                    "notes": task.get("notes", ""),
                })

    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, f"google_today_{day_str}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data_output, f, ensure_ascii=False, indent=2)

    return out_path
