import os
import shutil
import random
from datetime import datetime, date, timedelta
from typing import List, Optional

from ..utils_paths import ensure_dir, day_folder


IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


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


def _format_filename(dt: datetime, ext: str) -> str:
    return dt.strftime("%H-%M-%S") + ext.lower()


def _compute_schedule(d: date, n: int, start_hour: int = 8, end_hour: int = 20) -> List[datetime]:
    start_dt = datetime(d.year, d.month, d.day, start_hour, 0, 0)
    end_dt = datetime(d.year, d.month, d.day, end_hour, 0, 0)

    if n <= 0:
        return []
    if n == 1:
        return [start_dt]

    total_seconds = int((end_dt - start_dt).total_seconds())
    step = total_seconds / float(n - 1)

    times: List[datetime] = []
    for i in range(n):
        t = start_dt + timedelta(seconds=int(round(step * i)))
        if t > end_dt:
            t = end_dt
        times.append(t)
    return times


def simulate_random_day(
    source_root: str,
    output_root: str,
    output_date: Optional[date] = None,
    random_seed: Optional[int] = 42,
    shuffle: bool = True,
) -> str:
    d = output_date or datetime.now().date()
    imgs = _list_images_recursive(source_root)
    if not imgs:
        raise RuntimeError(f"No images found under: {source_root}")

    if random_seed is not None:
        random.seed(random_seed)

    images = list(imgs)
    if shuffle:
        random.shuffle(images)

    schedule = _compute_schedule(d, len(images))
    out_dir = day_folder(output_root, d)
    ensure_dir(out_dir)

    used = set()
    for src_path, dt_local in zip(images, schedule):
        _, ext = os.path.splitext(src_path)
        ext = ext.lower()
        if ext not in IMAGE_EXTS:
            continue

        name = _format_filename(dt_local, ext)
        dst = os.path.join(out_dir, name)

        bump = 0
        while dst in used or os.path.exists(dst):
            bump += 1
            name = _format_filename(dt_local + timedelta(seconds=bump), ext)
            dst = os.path.join(out_dir, name)

        ensure_dir(os.path.dirname(dst))
        shutil.copy2(src_path, dst)
        used.add(dst)

    return out_dir
