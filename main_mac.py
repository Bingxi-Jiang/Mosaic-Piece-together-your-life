import time
import threading

# 导入所有 Service
from services.context import ContextManager
from services.recorder import ScreenRecorder
# 导入 Privacy 类，以及刚才新写的 native 检测函数
from services.privacy_server_mac import MacPrivacyMonitor, is_native_app_sensitive


# === 配置 ===
SCREENSHOT_INTERVAL = 3


def main():
    print("🚀 Mosaic macOS 客户端启动中...")

    # 1. 模块初始化
    context_mgr = ContextManager(artifacts_dir = "artifacts")
    recorder = ScreenRecorder(root_dir = "screenshots")
    monitor = MacPrivacyMonitor()

    # 2. 读取上下文
    tasks = context_mgr.load_latest_todo()
    if tasks:
        print(f"   -> 当前首要任务: {tasks[0].get('title', 'Unknown')}")

    # 3. 启动 Web 隐私监听 (Web Hook)
    print("🛡️ 正在启动隐私卫士 (Port 5001)...")
    privacy_thread = threading.Thread(target = monitor.start_monitoring, daemon = True)
    privacy_thread.start()

    time.sleep(2)
    print(f"✅ 系统就绪! 全面监测中 (Web + Native)...")

    try:
        while True:
            # --- 第一道防线: Web 检查 (Web Check) ---
            if monitor.is_paused:
                print(f"⛔ [Web阻断] 隐私保护生效中... 原因: {monitor.pause_reason}")

            else:
                # --- 第二道防线: Native 检查 (Native Check) ---
                # 直接调用 service 里的函数，main 不用关心具体逻辑
                is_sensitive, app_name = is_native_app_sensitive()

                if is_sensitive:
                    print(f"⛔ [本地阻断] 检测到敏感应用: {app_name}")
                else:
                    # --- 全部通过，执行截图 ---
                    recorder.take_screenshot()

            time.sleep(SCREENSHOT_INTERVAL)

    except KeyboardInterrupt:
        print("\n👋 程序已退出。")


if __name__ == "__main__":
    main()