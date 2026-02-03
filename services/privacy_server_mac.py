import threading
import subprocess
import json
import os
from flask import Flask, request, jsonify


# === 配置文件路径 ===
CONFIG_FILE = "privacy_config.json"

# === [修改点] 空的配置模板 ===
# 不再包含默认名单，完全由用户决定
TEMPLATE_CONFIG = {
    "blocked_apps": [
        "ExampleApp_Name_Here"  # 这是一个示例，用户可以删除
    ],
    "blocked_keywords": [
        "example_keyword"  # 这是一个示例
    ]
}

# 全局配置变量
CURRENT_CONFIG = {"blocked_apps": [], "blocked_keywords": []}


def load_or_create_config():
    """
    加载配置文件。如果不存在，生成一个空的模板供用户填写。
    """
    global CURRENT_CONFIG
    try:
        if not os.path.exists(CONFIG_FILE):
            print(f"🆕 [Config] 初始化: 未找到配置，正在生成模板文件 -> {CONFIG_FILE}")
            print(f"👉 请打开 {CONFIG_FILE} 手动添加你要拦截的应用名或网址关键词。")

            with open(CONFIG_FILE, 'w', encoding = 'utf-8') as f:
                json.dump(TEMPLATE_CONFIG, f, indent = 4, ensure_ascii = False)

            # 初始状态设为空，避免拦截示例值
            CURRENT_CONFIG = {"blocked_apps": [], "blocked_keywords": []}
        else:
            with open(CONFIG_FILE, 'r', encoding = 'utf-8') as f:
                CURRENT_CONFIG = json.load(f)

                # 过滤掉示例值 (可选优化)
                apps = [a for a in CURRENT_CONFIG.get("blocked_apps", []) if
                        a != "ExampleApp_Name_Here"]
                words = [w for w in CURRENT_CONFIG.get("blocked_keywords", []) if
                         w != "example_keyword"]

                CURRENT_CONFIG["blocked_apps"] = apps
                CURRENT_CONFIG["blocked_keywords"] = words

                print(f"⚙️ [Config] 已加载用户配置: {len(apps)} 个应用, {len(words)} 个关键词")

    except Exception as e:
        print(f"⚠️ [Config] 配置文件加载失败 ({e})，隐私保护可能暂时失效。")
        CURRENT_CONFIG = {"blocked_apps": [], "blocked_keywords": []}


# --- 工具函数 ---
def get_active_app_name():
    """使用 AppleScript 获取前台应用名"""
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output = True, text = True)
        return result.stdout.strip()
    except Exception:
        return None


def is_native_app_sensitive():
    """检查本地应用是否在配置的黑名单中"""
    app_name = get_active_app_name()

    # [调试提示]
    # 如果你想让用户知道当前打开的App叫什么名字(方便他们填配置)，可以取消下面这行的注释
    # print(f"Current App: {app_name}")

    if app_name in CURRENT_CONFIG.get("blocked_apps", []):
        return True, app_name
    return False, app_name


# --- Flask 服务类 ---
class MacPrivacyMonitor:
    def __init__(self):
        # 启动时加载
        load_or_create_config()

        self.app = Flask(__name__)
        self.is_paused = False
        self.pause_reason = None
        self.setup_routes()

    def setup_routes(self):
        @self.app.route('/update_url', methods = ['POST'])
        def update_url():
            try:
                data = request.json
                url = data.get('url', '').lower()

                # 获取配置
                keywords = CURRENT_CONFIG.get("blocked_keywords", [])

                # 匹配逻辑
                matched_keyword = next((word for word in keywords if word in url), None)

                if matched_keyword:
                    if not self.is_paused:
                        print(f"\n🚨 [Web] 命中黑名单: {matched_keyword}")
                        self.is_paused = True
                        self.pause_reason = f"domain: {matched_keyword}"
                else:
                    if self.is_paused and self.pause_reason and "domain" in self.pause_reason:
                        print("\n🟢 [Web] 敏感浏览结束")
                        self.is_paused = False
                        self.pause_reason = None

                return jsonify({"status": "success"}), 200
            except Exception:
                return jsonify({"status": "error"}), 500

    def start_monitoring(self, port = 5001):
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        self.app.run(host = '0.0.0.0', port = port)