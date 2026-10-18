"""Danh sách mặt bị loại của một lượt (xoá mềm): runs/<lượt>/excluded.txt, mỗi dòng một tên mặt không đuôi, dòng # là chú thích.

Chỉ thư viện chuẩn. Loại trừ chỉ là BỘ LỌC lúc đọc: không bao giờ sửa meta.json, flags.json, mp50.json, pred478.json,
autoqc.csv, no_face.csv hay triage_*.csv, nên khôi phục = gỡ tên khỏi danh sách. Mọi nơi đọc mặt của lượt phải trừ tập này.
"""
import os
import threading
import time

FILE = "excluded.txt"
HEADER = "# Mặt bị loại khỏi lượt này (xoá mềm). Mỗi dòng một tên không đuôi. Gỡ tên khỏi đây = khôi phục (kèm file trong _trash).\n"
EXTS = (".png", ".jpg", ".jpeg")
_LOCK = threading.RLock()


def path(run_dir):
    return os.path.join(run_dir, FILE)


def _stem(name):
    s = str(name).strip()
    base, ext = os.path.splitext(s)
    return base if ext.lower() in EXTS else s


def read_excluded(run_dir):
    """Tập tên (không đuôi) bị loại; không có file thì rỗng."""
    try:
        with open(path(run_dir), encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError:
        return set()
    return {_stem(ln) for ln in lines if ln.strip() and not ln.strip().startswith("#")}


def _write(run_dir, names):
    os.makedirs(run_dir, exist_ok=True)
    p = path(run_dir)
    tmp = p + f".tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEADER + "".join(n + "\n" for n in sorted(names)))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


class _FileLock:
    """Khoá file đơn giản (O_EXCL) giữa các tiến trình; quá 10 giây thì coi là khoá mồ côi và bỏ."""

    def __init__(self, run_dir):
        self.p = path(run_dir) + ".lock"

    def __enter__(self):
        t0 = time.time()
        while True:
            try:
                fd = os.open(self.p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                if time.time() - t0 > 10:
                    try:
                        os.remove(self.p)
                    except OSError:
                        pass
                time.sleep(0.05)
            except OSError:
                return self                      # không tạo được khoá thì vẫn ghi (os.replace vẫn nguyên tử)

    def __exit__(self, *exc):
        try:
            os.remove(self.p)
        except OSError:
            pass


def add(run_dir, names):
    """Thêm tên vào danh sách (nguyên tử). Trả tập mới."""
    with _LOCK, _FileLock(run_dir):
        cur = read_excluded(run_dir)
        cur |= {_stem(n) for n in names}
        _write(run_dir, cur)
        return cur


def remove(run_dir, names):
    """Gỡ tên khỏi danh sách (nguyên tử). Trả tập mới."""
    with _LOCK, _FileLock(run_dir):
        cur = read_excluded(run_dir)
        cur -= {_stem(n) for n in names}
        _write(run_dir, cur)
        return cur


def keep(d, excluded):
    """Bản sao dict/list/tập `d` bỏ các tên bị loại (khoá dict, hoặc phần tử nếu là list/tập)."""
    if isinstance(d, dict):
        return {k: v for k, v in d.items() if k not in excluded}
    return type(d)(x for x in d if x not in excluded) if isinstance(d, (list, tuple, set)) else d
