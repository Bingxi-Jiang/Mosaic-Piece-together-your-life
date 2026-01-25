import json
import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/tasks.readonly'
]

def get_credentials():
    creds = None
    if os.path.exists('token_combined.json'):
        creds = Credentials.from_authorized_user_file('token_combined.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token_combined.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def fetch_today_data():
    creds = get_credentials()
    cal_service = build('calendar', 'v3', credentials=creds)
    task_service = build('tasks', 'v1', credentials=creds)

    today_date = datetime.date.today()
    today_str = today_date.isoformat()
    
    # 时间范围计算 (UTC 格式)
    now = datetime.datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + 'Z'

    # --- JSON 模板 ---
    data_output = {
        "report_date": today_str,
        "export_timestamp": datetime.datetime.now().isoformat(),
        "calendar": {
            "summary": "今日日历事件",
            "items": []
        },
        "tasks": {
            "summary": "今日截止任务",
            "items": []
        }
    }

    # 1. 抓取今日日历
    cal_results = cal_service.events().list(
        calendarId='primary', 
        timeMin=start_of_day, 
        timeMax=end_of_day,
        singleEvents=True, 
        orderBy='startTime'
    ).execute()
    
    for event in cal_results.get('items', []):
        data_output["calendar"]["items"].append({
            "title": event.get('summary'),
            "start": event['start'].get('dateTime', event['start'].get('date')),
            "location": event.get('location', 'N/A')
        })

    # 2. 抓取今日任务
    task_lists = task_service.tasklists().list().execute().get('items', [])
    for t_list in task_lists:
        tasks = task_service.tasks().list(tasklist=t_list['id']).execute().get('items', [])
        # 仅保留截止日期为今天的
        for task in tasks:
            due_date = task.get('due')
            if due_date and due_date.startswith(today_str):
                data_output["tasks"]["items"].append({
                    "title": task.get('title'),
                    "list_source": t_list['title'],
                    "status": task.get('status'),
                    "notes": task.get('notes', '')
                })

    # 3. 导出为 JSON 文件
    output_filename = f'google_today_{today_str}.json'
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(data_output, f, ensure_ascii=False, indent=4)
    
    print(f"成功导出！今日数据已存至: {output_filename}")

if __name__ == '__main__':
    fetch_today_data()