import pygetwindow as gw
import time
import os

def is_app_running_as_window(app_name_keyword):
    """
    只检测 '应用' 栏：通过查找系统当前所有可见的窗口标题来判断
    """
    # 获取当前桌面上所有窗口的标题
    all_windows = gw.getAllTitles()
    
    for title in all_windows:
        # 只要标题中包含“微信”且窗口不是空的
        if title and app_name_keyword in title:
            # 进一步确认该窗口是否真的“可见”（在应用栏显示）
            window = gw.getWindowsWithTitle(title)[0]
            if window.visible:
                return True, title
    return False, None

def main():
    # 根据你的描述，微信的显示名称是“微信”
    target_keyword = "微信"
    
    print(f"--- 正在监控 Windows '应用' 栏，寻找窗口标题包含: {target_keyword} ---")
    
    already_open = False

    try:
        while True:
            is_open, actual_title = is_app_running_as_window(target_keyword)
            
            if is_open:
                if not already_open:
                    print(f"\n[!] 检测到应用开启!")
                    print(f"状态: {target_keyword} is OPEN")
                    print(f"具体窗口标题为: {actual_title}")
                    already_open = True
            else:
                if already_open:
                    print(f"\n[?] 应用已从'应用'栏消失 (已关闭或完全隐藏至后台)")
                    already_open = False
            
            # 打印一个点表示心跳，证明脚本在跑
            print(".", end="", flush=True)
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n监控已停止。")

if __name__ == "__main__":
    main()