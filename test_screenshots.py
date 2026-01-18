import time
import os
from datetime import datetime
from PIL import ImageGrab

# =======================
# Global Configuration
# =======================

# 截图时间间隔（秒）
# 15 分钟
SCREENSHOT_INTERVAL = 5

# 根目录
SCREENSHOT_ROOT = "screenshots"


def ensure_directory(path: str):
    """Create directory if it does not exist."""
    if not os.path.exists(path):
        os.makedirs(path)


def get_screenshot_directory(now: datetime) -> str:
    """
    Build directory path:
    screenshots / Year / Month / Day
    """
    year = now.strftime("%Y")
    month = now.strftime("%B")     # January, February, ...
    day = now.strftime("%d")

    directory = os.path.join(
        SCREENSHOT_ROOT,
        year,
        month,
        day
    )

    ensure_directory(directory)
    return directory


def take_screenshot():
    """Capture the entire screen and save it in structured folders."""
    now = datetime.now()

    save_dir = get_screenshot_directory(now)

    # 文件名：HH-MM-SS.png
    filename = now.strftime("%H-%M-%S") + ".png"
    filepath = os.path.join(save_dir, filename)

    screenshot = ImageGrab.grab()  # entire screen
    screenshot.save(filepath)

    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Saved -> {filepath}")


def main():
    ensure_directory(SCREENSHOT_ROOT)

    print("Screenshot service started")
    print(f"Interval: {SCREENSHOT_INTERVAL} seconds")
    print(f"Root directory: {os.path.abspath(SCREENSHOT_ROOT)}")

    while True:
        take_screenshot()
        time.sleep(SCREENSHOT_INTERVAL)


if __name__ == "__main__":
    main()
