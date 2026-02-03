import os
from datetime import datetime
from PIL import ImageGrab

class ScreenRecorder:
    def __init__(self, root_dir="screenshots"):
        self.root_dir = root_dir

    def _ensure_daily_folder(self):
        """内部方法：确保当天的文件夹存在"""
        now = datetime.now()
        # 路径结构: screenshots/2026/February/02
        path = os.path.join(
            self.root_dir,
            str(now.year),
            now.strftime("%B"),
            now.strftime("%d")
        )
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def take_screenshot(self):
        """执行一次截图并保存"""
        try:
            save_dir = self._ensure_daily_folder()
            timestamp = datetime.now().strftime("%H-%M-%S")
            filename = f"{timestamp}.png"
            filepath = os.path.join(save_dir, filename)

            # 截图核心
            screenshot = ImageGrab.grab()
            screenshot.save(filepath)
            print(f"📸 [{timestamp}] 截图已保存")
            return True
        except Exception as e:
            print(f"❌ [Recorder] 截图失败: {e}")
            return False