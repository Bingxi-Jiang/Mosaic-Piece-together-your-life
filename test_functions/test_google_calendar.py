import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_calendar_service():
    creds = None
    if os.path.exists('token_calendar.json'):
        creds = Credentials.from_authorized_user_file('token_calendar.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token_calendar.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def main():
    service = get_calendar_service()
    
    # 获取今天 00:00:00 和 23:59:59 的 UTC 时间格式
    now = datetime.datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + 'Z'
    
    print(f"正在获取今日 ({datetime.date.today()}) 的日历事件...")
    
    events_result = service.events().list(
        calendarId='primary', 
        timeMin=start_of_day,
        timeMax=end_of_day, # 限制在今天结束前
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])

    if not events:
        print('今天没有找到任何日历事件。')
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(f"今日事件: {start} - {event.get('summary', '无标题')}")

if __name__ == '__main__':
    main()