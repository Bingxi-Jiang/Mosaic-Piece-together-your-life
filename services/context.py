import glob
import os
import json


class ContextManager:
    def __init__(self, artifacts_dir = "artifacts"):
        self.artifacts_dir = artifacts_dir

    def load_latest_todo(self):
        """加载最新的 To-Do JSON 文件"""
        try:
            # 寻找所有 json 文件
            list_of_files = glob.glob(f'{self.artifacts_dir}/*.json')
            if not list_of_files:
                print("⚠️ [Context] 未找到 To-Do 任务文件。")
                return []

            # 找最新的
            latest_file = max(list_of_files, key = os.path.getctime)

            with open(latest_file, 'r', encoding = 'utf-8') as f:
                data = json.load(f)
                tasks = data.get('value', [])
                print(
                    f"📚 [Context] 已加载记忆: {os.path.basename(latest_file)} (含 {len(tasks)} 条任务)")
                return tasks

        except Exception as e:
            print(f"❌ [Context] 读取出错: {e}")
            return []