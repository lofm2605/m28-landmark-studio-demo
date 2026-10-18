"""File khoá runs/<lượt>/.dang_chay: lượt đang có việc chạy (prepare, push, xoá task) thì không cho xoá ảnh/đợt/task.

Chỉ thư viện chuẩn. Nội dung JSON {kind, pid, t}. Trang rà soát (PrepareJob/PushJob/DeleteJob) ghi khoá với pid của TRANG trước khi
chạy tiến trình con; tiến trình con (push, xoá task) thấy khoá do tiến trình cha của nó giữ thì dùng tiếp, còn chạy từ cmd mà chưa có
khoá thì tự ghi khoá của mình. Khoá của tiến trình đã chết (máy sập) là khoá mồ côi và bị bỏ qua.
"""
import json
import os
import sys
import time

FILE = ".dang_chay"


def path(run_dir):
    return os.path.join(run_dir, FILE)


def pid_alive(pid):
    """Tiến trình còn chạy không. Trên Windows KHÔNG dùng os.kill(pid, 0) (ở đó nó giết tiến trình)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, pid)             # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            try:
                code = ctypes.c_ulong()
                return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259     # STILL_ACTIVE
            finally:
                k.CloseHandle(h)
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read(run_dir):
    try:
        with open(path(run_dir), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def busy(run_dir):
    """(kind, pid) nếu lượt đang có việc chạy (khoá còn sống), không thì None."""
    d = read(run_dir)
    if d and pid_alive(d.get("pid")):
        return d.get("kind", "?"), d.get("pid")
    return None


def acquire(run_dir, kind, pid=None):
    """Ghi khoá. Trả True nếu ghi được; False nếu đã có khoá của tiến trình khác còn sống."""
    cur = busy(run_dir)
    me = pid or os.getpid()
    if cur and cur[1] != me:
        return False
    try:
        os.makedirs(run_dir, exist_ok=True)
        tmp = path(run_dir) + f".tmp{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(kind=kind, pid=me, t=time.strftime("%Y-%m-%dT%H:%M:%S")), f)
        os.replace(tmp, path(run_dir))
    except OSError:
        return True                                       # không ghi được khoá thì không chặn việc chính
    return True


def release(run_dir, pid=None):
    d = read(run_dir)
    if d and d.get("pid") == (pid or os.getpid()):
        try:
            os.remove(path(run_dir))
        except OSError:
            pass


OWNER_ENV = "M28_LOCK_OWNER"


def owners():
    """pid được coi là 'chủ khoá hợp lệ' của tiến trình con: cha trực tiếp, và pid trang ghi trong M28_LOCK_OWNER. Cần cả hai vì trên
    Windows python.exe trong .venv là bộ khởi chạy sinh ra python thật, nên cha trực tiếp của tiến trình con KHÔNG phải trang."""
    out = {os.getppid()}
    try:
        out.add(int(os.environ.get(OWNER_ENV, "")))
    except ValueError:
        pass
    return out


def mark_owner():
    """Gọi một lần trong tiến trình trang: mọi tiến trình con (push, xoá task, thử kết nối) kế thừa biến này."""
    os.environ[OWNER_ENV] = str(os.getpid())


class Guard:
    """with Guard(run_dir, "push"): dùng trong tiến trình con. Khoá do tiến trình cha giữ thì dùng tiếp (không xoá khi thoát);
    chưa có khoá thì tự ghi và tự xoá; khoá của tiến trình khác còn sống thì SystemExit."""

    def __init__(self, run_dir, kind, what):
        self.run_dir, self.kind, self.what = run_dir, kind, what
        self.own = False

    def __enter__(self):
        cur = busy(self.run_dir)
        if cur and cur[1] in owners():
            return self                                   # trang (tiến trình cha) đã giữ khoá cho việc này
        if cur:
            raise SystemExit(f"Lượt này đang có việc khác chạy ({cur[0]}, tiến trình {cur[1]}): chờ xong rồi {self.what}.")
        self.own = acquire(self.run_dir, self.kind)
        return self

    def __exit__(self, *exc):
        if self.own:
            release(self.run_dir)
