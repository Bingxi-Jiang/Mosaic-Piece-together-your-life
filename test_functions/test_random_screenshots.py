import os
import shutil
import random
from datetime import datetime, date, timedelta
from typing import List, Tuple, Optional

# =======================
# Global Configuration
# =======================

# 源截图根目录（你现有的截图都在这里）
SOURCE_SCREENSHOT_ROOT = "screenshots"

# 生成“测试日”的输出根目录（不会改动原始数据）
OUTPUT_SCREENSHOT_ROOT = "screenshots_test"

# 测试覆盖的时间段：08:00 到 20:00（本地时间）
TEST_START_HOUR = 8
TEST_END_HOUR = 20

# 是否随机打乱图片顺序
RANDOM_SHUFFLE = True

# 随机种子（固定则每次结果一致；设为 None 则每次不同）
RANDOM_SEED: Optional[int] = 42

# 输出日期：默认用今天；也可以指定，例如 date(2026, 1, 17)
OUTPUT_DATE: Optional[date] = None

# 是否允许同一秒冲突时自动 +1 秒（避免重名覆盖）
AVOID_FILENAME_COLLISION = True

# 支持的图片后缀
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def _ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def _month_name(dt: date) -> str:
    # 与你之前的目录结构一致：January, February...
    return dt.strftime("%B")


def _day_folder(root: str, d: date) -> str:
    return os.path.join(root, d.strftime("%Y"), _month_name(d), d.strftime("%d"))


def _list_images_recursive(root: str) -> List[str]:
    paths: List[str] = []
    if not os.path.isdir(root):
        return paths

    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in IMAGE_EXTS:
                paths.append(os.path.join(dirpath, fn))
    return paths


def _collect_source_images_for_today_style(root: str) -> List[str]:
    """
    从 screenshots 根目录下收集所有图片（递归）。
    你说 screenshots 里已经有些照片了，这里不假设它们一定在“今天”的文件夹里。
    """
    return _list_images_recursive(root)


def _format_filename(dt: datetime, ext: str) -> str:
    # 你的现有命名规范：HH-MM-SS.png
    return dt.strftime("%H-%M-%S") + ext.lower()


def _compute_schedule(d: date, n: int) -> List[datetime]:
    """
    给 n 张图分配时间点，覆盖 [08:00, 20:00]（含起点，不含终点），尽量均匀。
    如果 n == 1，则放在 08:00:00。
    """
    start_dt = datetime(d.year, d.month, d.day, TEST_START_HOUR, 0, 0)
    end_dt = datetime(d.year, d.month, d.day, TEST_END_HOUR, 0, 0)

    if n <= 0:
        return []

    if n == 1:
        return [start_dt]

    total_seconds = int((end_dt - start_dt).total_seconds())
    # n 个点均匀铺开到区间内（最后一个点不强制等于 end_dt）
    step = total_seconds / float(n - 1)

    times: List[datetime] = []
    for i in range(n):
        t = start_dt + timedelta(seconds=int(round(step * i)))
        # 保证不会超过 end_dt（极端四舍五入）
        if t > end_dt:
            t = end_dt
        times.append(t)

    return times


def _safe_copy(src: str, dst: str) -> None:
    _ensure_dir(os.path.dirname(dst))
    shutil.copy2(src, dst)


def _unique_destination_path(dest_dir: str, base_dt: datetime, ext: str) -> str:
    """
    生成不冲突的目标路径。若发生同名，则在秒级递增直到不冲突（或直接覆盖由你控制）。
    """
    dt_try = base_dt
    for _ in range(200):  # 200 秒足够避免冲突
        name = _format_filename(dt_try, ext)
        path = os.path.join(dest_dir, name)
        if not AVOID_FILENAME_COLLISION or not os.path.exists(path):
            return path
        dt_try = dt_try + timedelta(seconds=1)
    # 最后兜底：加随机后缀
    name = dt_try.strftime("%H-%M-%S") + f"_{random.randint(1000,9999)}" + ext.lower()
    return os.path.join(dest_dir, name)


def generate_randomized_test_day() -> str:
    # 日期
    d = OUTPUT_DATE if OUTPUT_DATE is not None else datetime.now().date()

    # 收集所有源图
    source_images = _collect_source_images_for_today_style(SOURCE_SCREENSHOT_ROOT)
    if not source_images:
        raise RuntimeError(f"No images found under: {SOURCE_SCREENSHOT_ROOT}")

    # 随机
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)

    images = list(source_images)
    if RANDOM_SHUFFLE:
        random.shuffle(images)

    # 分配时间点
    schedule = _compute_schedule(d, len(images))

    # 输出目录：screenshots_test/YYYY/Month/DD
    out_dir = _day_folder(OUTPUT_SCREENSHOT_ROOT, d)
    _ensure_dir(out_dir)

    # 复制并重命名
    for src_path, dt_local in zip(images, schedule):
        _, ext = os.path.splitext(src_path)
        ext = ext.lower()
        if ext not in IMAGE_EXTS:
            # 防御性：跳过非常规后缀
            continue

        dst_path = _unique_destination_path(out_dir, dt_local, ext)
        _safe_copy(src_path, dst_path)

    return out_dir


if __name__ == "__main__":
    out = generate_randomized_test_day()
    print(f"Test day folder generated at: {os.path.abspath(out)}")
    print(f"Time span: {TEST_START_HOUR:02d}:00 to {TEST_END_HOUR:02d}:00")
    print(f"Output root: {os.path.abspath(OUTPUT_SCREENSHOT_ROOT)}")
