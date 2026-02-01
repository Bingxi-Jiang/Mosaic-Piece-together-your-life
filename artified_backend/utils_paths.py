import os
from datetime import date, datetime


def ensure_dir(path: str) -> None:
    if path and not os.path.exists(path):
        os.makedirs(path)


def month_name(d: date) -> str:
    return d.strftime("%B")


def day_folder(root: str, d: date) -> str:
    return os.path.join(root, d.strftime("%Y"), month_name(d), d.strftime("%d"))


def screenshot_filename(dt_local: datetime, ext: str = ".png") -> str:
    return dt_local.strftime("%H-%M-%S") + ext


def artifacts_dir(day_dir: str, artifacts_dirname: str) -> str:
    return os.path.join(day_dir, artifacts_dirname)
