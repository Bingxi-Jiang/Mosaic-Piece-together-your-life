from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo


def now_local(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def today_local_date(tz_name: str) -> date:
    return now_local(tz_name).date()


def parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")
    return dtime(hour=int(hh), minute=int(mm))


def is_past_stop_time(now_dt: datetime, stop_hhmm: str) -> bool:
    stop_t = parse_hhmm(stop_hhmm)
    return now_dt.timetz().replace(tzinfo=None) >= stop_t
