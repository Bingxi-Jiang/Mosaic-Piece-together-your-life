import os
from datetime import datetime
from PIL import ImageGrab

from ..utils_paths import ensure_dir, screenshot_filename


def take_screenshot_to(day_dir: str, dt_local: datetime) -> str:
    ensure_dir(day_dir)
    filename = screenshot_filename(dt_local, ".png")
    path = os.path.join(day_dir, filename)

    img = ImageGrab.grab()
    img.save(path)
    return path
