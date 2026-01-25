import os.path
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/tasks.readonly']

def get_tasks_service():
    creds = None
    if os.path.exists('token_tasks.json'):
        creds = Credentials.from_authorized_user_file('token_tasks.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token_tasks.json', 'w') as token:
            token.write(creds.to_json())
    return build('tasks', 'v1', credentials=creds)

def main():
    service = get_tasks_service()
    today_str = datetime.date.today().isoformat() # 格式如 "2023-10-27"
    
    results = service.tasklists().list().execute()
    items = results.get('items', [])

    print(f"正在检查今日 ({today_str}) 的待办任务...")
    found_any = False

    for item in items:
        tasks_result = service.tasks().list(tasklist=item['id']).execute()
        tasks = tasks_result.get('items', [])
        
        # 过滤出截止日期是今天的任务
        # 注意：Google Tasks 的 due 字段通常是 "YYYY-MM-DDT00:00:00.000Z"
        today_tasks = [t for t in tasks if t.get('due') and t['due'].startswith(today_str)]
        
        if today_tasks:
            found_any = True
            print(f"列表 [{item['title']}] 下的今日任务:")
            for task in today_tasks:
                print(f"  - {task['title']}")
                
    if not found_any:
        print("今天没有截止的待办任务。")

if __name__ == '__main__':
    main()