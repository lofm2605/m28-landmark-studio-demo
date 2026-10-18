"""Cài đặt của trang rà soát M28 (tab "Cài đặt"): MỘT nguồn cấu hình duy nhất cho CVAT (link, token, tổ chức), tên người rà mặc định,
đường dẫn (thư mục ảnh, file face_landmarker.task) và ngưỡng t_flip của cờ low_conf. Logic thuần: KHÔNG import gradio, torch,
cvat_sdk, và KHÔNG gọi mạng (chỉ module cai_dat_thu.py, chạy trong tiến trình con riêng, gọi CVAT).

Nơi lưu (ngoài repo, trong hồ sơ người dùng; user_dir()):
    Windows        %APPDATA%\\m28\\            (thiếu APPDATA thì %USERPROFILE%\\AppData\\Roaming\\m28)
    Linux / macOS  $XDG_CONFIG_HOME/m28/ hoặc ~/.config/m28/
    M28_CONFIG_DIR đặt thì dùng thư mục đó (chỉ để test / máy đặc biệt).
  Thư mục rơi vào trong repo hoặc thư mục chạy code bị TỪ CHỐI (token không bao giờ nằm cạnh file có thể bị commit).
  cvat.json   {"version":1, "url", "token", "org"}  CHỈ khi người dùng bật "Nhớ trên máy này" (mặc định tắt).
  cai_dat.json {"version":1, "reviewer", "images_dir", "model_path"}  không có bí mật.

Quyền file: ghi nguyên tử (file tạm cùng thư mục tạo bằng O_CREAT|O_EXCL mode 0o600, fsync, os.replace). Trên Linux/macOS thư mục
0o700 và file 0o600, được kiểm lại bằng stat sau khi ghi (không đạt thì xoá file và báo lỗi). Trên Windows os.chmod KHÔNG đặt được quyền
thật: file chỉ được bảo vệ bởi quyền của hồ sơ người dùng (thư mục %APPDATA% của chính bạn); bản này KHÔNG dùng keyring/DPAPI và không
giả vờ là có.

Ưu tiên nguồn của link/token/tổ chức (effective()): giá trị người dùng vừa Lưu trong phiên này ("session", hoặc "file" nếu đã bật Nhớ)
> biến môi trường CVAT_URL + CVAT_ACCESS_TOKEN khi cả hai có ("env") > file đã lưu ("file"). Biến môi trường của cmd không bao giờ bị
sửa: Lưu chỉ đổi giá trị trang này dùng. Một Settings dùng chung cả tiến trình (get()), nên cài đặt sống qua lần chuyển lượt.
Token chỉ ra khỏi module này theo hai đường: (1) cvat_env()/child_env_updates() cho tiến trình con (qua biến môi trường của chính nó, không
bao giờ qua đối số dòng lệnh), (2) mask() ("••••3456") cho trình duyệt. Không đối tượng nào ở đây có repr/str lộ token.
"""
import hashlib
import ipaddress
import json
import ntpath
import os
import posixpath
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
import zipfile
from urllib.parse import urlsplit

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
from m28core import cvat_io  # noqa: E402
from nap_anh import REVIEWER_RE, RunError, check_reviewer as _check_reviewer  # noqa: E402,F401  (một quy tắc tên người rà cho cả repo)

ENV_DIR = "M28_CONFIG_DIR"
FILE_CVAT, FILE_PREFS = "cvat.json", "cai_dat.json"
SOURCE_LABEL = {"env": "từ biến môi trường", "file": "đã lưu trên máy", "session": "nhập trong phiên này", None: ""}
PROBE_SCRIPT = "cai_dat_thu.py"
TEST_TIMEOUT = 20.0
CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
TOKEN_RE = re.compile(r"[\x21-\x7e]{8,512}")
ORG_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
IMAGE_EXTS = (".jpg", ".jpeg", ".png")
FROZEN_PREFIX = "NHAP"


class SettingsError(RunError):
    """Lỗi người dùng sửa được (thông báo tiếng Việt, không bao giờ chứa token)."""


# ---------- tiện ích ----------
def mask(token):
    """Dạng duy nhất của token được về trình duyệt: '••••' + 4 ký tự cuối (token ngắn hơn 8 ký tự thì chỉ '••••')."""
    token = token or ""
    return "••••" if os.environ.get("M28_PUBLIC_DEMO") == "1" else ("••••" + token[-4:] if len(token) >= 8 else "••••")


def fingerprint(url, token, org=""):
    """Dấu vân tay (băm) của bộ giá trị CVAT để biết kết quả thử kết nối còn đúng với giá trị đang dùng. Chỉ giữ trong bộ nhớ."""
    return hashlib.sha256("\x00".join((url or "", token or "", org or "")).encode("utf-8")).hexdigest()


def fmt_vi(x, digits=4):
    """0.0672 -> '0,0672' (số thập phân kiểu Việt)."""
    s = f"{float(x):.{digits}f}".rstrip("0").rstrip(".")
    return (s or "0").replace(".", ",")


def _n(n):
    return f"{int(n):,}".replace(",", ".")


def _mb(n):
    return f"{n / 1048576:.1f}".replace(".", ",") + " MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB"


# ---------- nơi lưu ----------
def user_dir(environ=None, platform=None):
    """Thư mục cài đặt của người dùng (ngoài repo), xem docstring đầu file. environ/platform thay được để test."""
    env = os.environ if environ is None else environ
    plat = sys.platform if platform is None else platform
    override = (env.get(ENV_DIR) or "").strip()
    if override:
        return os.path.abspath(override)
    if plat.startswith("win"):
        base = (env.get("APPDATA") or "").strip()
        if not base:
            prof = (env.get("USERPROFILE") or "").strip()
            if not prof:
                raise SettingsError("Không xác định được thư mục %APPDATA% hay %USERPROFILE% để lưu cài đặt: đặt biến M28_CONFIG_DIR "
                                    "sang một thư mục trong hồ sơ của bạn (ngoài repo).")
            base = ntpath.join(prof, "AppData", "Roaming")
        return ntpath.join(base, "m28")
    xdg = (env.get("XDG_CONFIG_HOME") or "").strip()
    if xdg and posixpath.isabs(xdg):
        return posixpath.join(xdg, "m28")
    home = (env.get("HOME") or "").strip() or os.path.expanduser("~")
    if not home or home == "~":
        raise SettingsError("Không xác định được thư mục HOME để lưu cài đặt: đặt biến M28_CONFIG_DIR sang một thư mục ngoài repo.")
    return posixpath.join(home, ".config", "m28")


def repo_roots(project_root):
    """Thư mục chạy code (project_root) và gốc repo git chứa nó (tìm .git đi ngược lên), đã realpath."""
    d = os.path.realpath(project_root)
    roots = {d}
    cur = d
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            roots.add(cur)
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return roots


def inside_repo(path, project_root):
    return any(cvat_io.inside(path, r) for r in repo_roots(project_root))


# ---------- ghi file nguyên tử ----------
def _fsync_dir(d):
    if os.name == "nt":
        return
    try:
        fd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def atomic_write(path, data, private=True, mode=None):
    """Ghi bytes `data` vào `path` nguyên tử: file tạm cùng thư mục (O_CREAT|O_EXCL), fsync, os.replace. Lỗi giữa chừng không làm hỏng
    file cũ và không để lại file tạm. private=True: thư mục (nếu do ta tạo) 0o700, file 0o600 và kiểm lại bằng stat (POSIX; trên
    Windows os.chmod không có tác dụng thật nên không gọi). mode: quyền file đích khi private=False (POSIX)."""
    d = os.path.dirname(os.path.abspath(path))
    created = not os.path.isdir(d)
    os.makedirs(d, mode=0o700, exist_ok=True)
    if private and created and os.name != "nt":
        os.chmod(d, 0o700)
    tmp = os.path.join(d, f".{os.path.basename(path)}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(tmp, flags, 0o600 if private else 0o666)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if not private and mode is not None and os.name != "nt":
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    if private and os.name != "nt":
        os.chmod(path, 0o600)
        got = stat.S_IMODE(os.stat(path).st_mode)
        if got != 0o600:
            try:
                os.remove(path)
            except OSError:
                pass
            raise SettingsError(f"Hệ thống file ở {os.path.dirname(path)} không đặt được quyền chặt (0600, đang là {oct(got)}): "
                                "đã xoá file. Đặt M28_CONFIG_DIR sang thư mục trên ổ đĩa hỗ trợ quyền Unix.")
    _fsync_dir(d)


def _dump(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


# ---------- kiểm giá trị ----------
def _private_host(host):
    h = (host or "").strip("[]").lower()
    if not h:
        return False
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return h == "localhost" or h.endswith((".local", ".localhost")) or "." not in h
    nets = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7", "fe80::/10")
    return any(ip in ipaddress.ip_network(n) for n in nets)


def check_url(url):
    """dict(ok, url (đã chuẩn hoá, bỏ '/' cuối), error, warning). Chỉ phân tích chuỗi, KHÔNG phân giải DNS, không mạng."""
    raw = (url or "").strip() if isinstance(url, str) else ""
    bad = lambda why: dict(ok=False, url="", error=why, warning="")    # noqa: E731
    if not raw:
        return bad("Chưa nhập link CVAT. Ví dụ: http://localhost:8080")
    if CTRL_RE.search(raw) or re.search(r"\s", raw):
        return bad("Link CVAT không được có khoảng trắng hay ký tự điều khiển bên trong.")
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://", raw)
    if not m:
        return bad("Link CVAT phải bắt đầu bằng http:// hoặc https:// (ví dụ http://localhost:8080); thiếu thì cvat-sdk tự hiểu là https.")
    if m.group(1).lower() not in ("http", "https"):
        return bad(f"Chỉ nhận link http:// hoặc https://, không nhận {m.group(1).lower()}://.")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return bad("Link CVAT có cổng hoặc địa chỉ không hợp lệ (cổng phải là số từ 1 đến 65535).")
    if "@" in parts.netloc:
        return bad("Link CVAT không được chứa tên đăng nhập hay mật khẩu (dạng http://user:pass@host). Dùng ô Token.")
    if not parts.hostname:
        return bad("Link CVAT thiếu tên máy (ví dụ localhost).")
    if parts.fragment or "#" in raw or "?" in raw:
        return bad("Link CVAT không có dấu ? hoặc #: chỉ ghi địa chỉ gốc, ví dụ http://localhost:8080.")
    if port is not None and not 1 <= port <= 65535:
        return bad("Cổng trong link CVAT phải từ 1 đến 65535.")
    norm = cvat_io.norm_url(raw)
    warn = ""
    if parts.scheme.lower() == "http" and not _private_host(parts.hostname):
        warn = (f"Link dùng http:// tới {parts.hostname}, không phải máy này hay mạng nội bộ: token sẽ đi KHÔNG mã hoá qua mạng. "
                "Nếu server có https:// thì dùng https://.")
    return dict(ok=True, url=norm, error="", warning=warn)


def check_token(token):
    """(token, None) hoặc (None, lý do). Lý do không bao giờ chứa token."""
    t = token if isinstance(token, str) else ""
    if not t.strip():
        return None, "Chưa nhập token."
    if not TOKEN_RE.fullmatch(t):
        return None, ("Token không hợp lệ: chỉ gồm 8–512 ký tự in được, không có khoảng trắng hay ký tự điều khiển. "
                      "Dán lại token từ CVAT (Settings > Security) và kiểm không dính khoảng trắng.")
    return t, None


def check_org(org):
    o = (org or "").strip() if isinstance(org, str) else ""
    if o and not ORG_RE.fullmatch(o):
        return None, "Tổ chức (CVAT_ORG) chỉ gồm chữ không dấu, số, _ - . (tối đa 64 ký tự), hoặc để trống."
    return o, None


def check_reviewer(name):
    """Tên người rà theo ĐÚNG quy tắc của review_app (nap_anh.check_reviewer); trả tên đã bỏ khoảng trắng hai đầu, hoặc RunError."""
    return _check_reviewer((name or "").strip() if isinstance(name, str) else name)


def clean_path(text):
    """Đường dẫn dán vào (kiểu Windows D:\\m28\\data\\frames, có thể có ngoặc kép bọc ngoài, khoảng trắng đầu/cuối) -> chuỗi đã chuẩn hoá
    (os.path.normpath). Rỗng -> ''. Ký tự điều khiển hay quá dài -> SettingsError. Không mở rộng biến, không đụng đĩa."""
    s = (text or "").strip() if isinstance(text, str) else ""
    for _ in range(2):
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
            s = s[1:-1].strip()
    if not s:
        return ""
    if CTRL_RE.search(s):
        raise SettingsError("Đường dẫn có ký tự điều khiển (xuống dòng, tab…): dán lại cho đúng.")
    if len(s) > 1024:
        raise SettingsError("Đường dẫn quá dài (hơn 1024 ký tự).")
    return os.path.normpath(s)


def _res(level, path, lines, **kw):
    return dict(level=level, ok=level != "err", path=path, lines=lines, **kw)


def check_images_dir(path, limit_files=5000, limit_seconds=2.0, clock=time.monotonic):
    """Kiểm thư mục ảnh: tồn tại? là thư mục? đọc được? Đếm ảnh .jpg/.jpeg/.png CÓ GIỚI HẠN (dừng sau limit_files file hoặc
    limit_seconds giây, ghi 'từ N trở lên'), số thư mục con, 3 tên mẫu. Không mở ảnh, không hiển thị ảnh."""
    try:
        p = clean_path(path)
    except SettingsError as e:
        return _res("err", "", [str(e)], n_images=0, capped=False, n_subdirs=0, samples=[])
    empty = dict(n_images=0, capped=False, n_subdirs=0, samples=[])
    if not p:
        return _res("err", "", ["Chưa nhập đường dẫn."], **empty)
    if not os.path.exists(p):
        return _res("err", p, [f"Không thấy {p}: kiểm lại đường dẫn (ổ đĩa đã gắn chưa, gõ đúng chữ hoa/thường chưa)."], **empty)
    if not os.path.isdir(p):
        return _res("err", p, [f"{p} là một file, cần một thư mục (thư mục chứa ảnh, ví dụ data\\frames hoặc data\\crops)."], **empty)
    try:
        top = os.listdir(p)
    except OSError as e:
        return _res("err", p, [f"Có thư mục nhưng không đọc được ({e.strerror or 'lỗi quyền truy cập'}): kiểm quyền truy cập."], **empty)
    n_sub = sum(1 for x in top if os.path.isdir(os.path.join(p, x)))
    t0, n, capped, samples = clock(), 0, False, []
    for root, dirs, files in os.walk(p):
        dirs.sort()
        for f in sorted(files):
            if f.lower().endswith(IMAGE_EXTS):
                n += 1
                if len(samples) < 3:
                    samples.append(os.path.relpath(os.path.join(root, f), p))
                if n >= limit_files:
                    capped = True
                    break
        if capped or clock() - t0 > limit_seconds:
            capped = capped or True
            break
    lines = ["Thư mục tồn tại và đọc được."]
    level = "ok"
    if n == 0:
        level = "warn"
        lines.append(f"Chưa thấy ảnh .jpg/.jpeg/.png nào ({_n(n_sub)} thư mục con): đúng thư mục ảnh chưa?")
    else:
        lines.append(f"Thấy {'từ ' if capped else ''}{_n(n)} ảnh{' trở lên (dừng đếm sớm)' if capped else ''}, {_n(n_sub)} thư mục con.")
        lines.append("Ví dụ: " + ", ".join(samples))
    return _res(level, p, lines, n_images=n, capped=capped, n_subdirs=n_sub, samples=samples)


def check_model(path):
    """Kiểm file face_landmarker.task: tồn tại, là file, đọc được, kích thước (khoảng 3,7 MB là bình thường), đuôi .task, và là file zip (file thật của
    MediaPipe là zip có 2 byte 00 đứng trước 'PK', nên dùng zipfile.is_zipfile, không so chữ ký ở đầu file)."""
    try:
        p = clean_path(path)
    except SettingsError as e:
        return _res("err", "", [str(e)], size=0)
    if not p:
        return _res("err", "", ["Chưa nhập đường dẫn."], size=0)
    if not os.path.exists(p):
        return _res("err", p, [f"Không thấy {p}: kiểm lại đường dẫn."], size=0)
    if not os.path.isfile(p):
        return _res("err", p, [f"{p} là một thư mục, cần đường dẫn tới file face_landmarker.task."], size=0)
    try:
        size = os.path.getsize(p)
        is_zip = zipfile.is_zipfile(p)
    except OSError as e:
        return _res("err", p, [f"Có file nhưng không đọc được ({e.strerror or 'lỗi quyền truy cập'})."], size=0)
    if size == 0:
        return _res("err", p, ["File rỗng (tải dở?): tải lại model (HUONG-DAN-WINDOWS mục 3)."], size=0)
    level, lines = "ok", [f"File đọc được, {_mb(size)} (khoảng 3,7 MB là bình thường)."]
    if not is_zip:
        return _res("err", p, [f"File {_mb(size)} nhưng không phải file .task (file .task của MediaPipe là một gói zip): tải lại model."], size=size)
    if not p.lower().endswith(".task"):
        level = "warn"
        lines.append("Đuôi file không phải .task: chắc chắn đây là face_landmarker.task?")
    if size < 1048576 or size > 100 * 1048576:
        level = "warn"
        lines.append("Kích thước khác xa 3,7 MB: kiểm lại đã tải đúng và đủ file chưa.")
    return _res(level, p, lines, size=size)


# ---------- t_flip trong config/m28_config.json ----------
def parse_t_flip(value):
    """Số thực 0 < t <= 1 (chấp nhận dấu phẩy thập phân kiểu Việt '0,0672'); None nếu value là None. ValueError (tiếng Việt) nếu sai."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("t_flip phải là một số.")
    if isinstance(value, (int, float)):
        x = float(value)
    else:
        s = str(value).strip().replace(",", ".")
        if not re.fullmatch(r"[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", s):
            raise ValueError("t_flip phải là một số lớn hơn 0 và không quá 1, ví dụ 0,0672.")
        x = float(s)
    if not (x == x) or x in (float("inf"), float("-inf")) or not 0 < x <= 1:
        raise ValueError("t_flip phải lớn hơn 0 và không quá 1 (đây là tỉ lệ so với khoảng cách hai mắt), ví dụ 0,0672.")
    return x


def read_config(config_path):
    """dict(ok, cfg, error). Không ném."""
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except OSError as e:
        return dict(ok=False, cfg=None, error=f"Không đọc được {os.path.normpath(config_path)} ({e.strerror or 'lỗi'}).")
    except ValueError:
        return dict(ok=False, cfg=None, error=f"{os.path.normpath(config_path)} không phải JSON hợp lệ: lấy lại file từ repo (git checkout config).")
    if not isinstance(cfg, dict) or not isinstance(cfg.get("points"), list):
        return dict(ok=False, cfg=None, error=f"{os.path.normpath(config_path)} không đúng định dạng m28_config.json (thiếu points).")
    return dict(ok=True, cfg=cfg, error="")


def read_t_flip(config_path):
    """dict(ok, error, t_flip, status, frozen, iod_points, n_points). frozen = status không còn bắt đầu bằng 'NHAP' (P1 đã đóng băng)."""
    r = read_config(config_path)
    if not r["ok"]:
        return dict(ok=False, error=r["error"], t_flip=None, status="", frozen=False, iod_points=[], n_points=0)
    cfg = r["cfg"]
    t = cfg.get("t_flip")
    status = str(cfg.get("status", ""))
    ok_t = t is None or (isinstance(t, (int, float)) and not isinstance(t, bool))
    m = cfg.get("low_conf_v2") if isinstance(cfg.get("low_conf_v2"), dict) else None
    v2 = bool(m and m.get("w") and m.get("threshold") is not None)              # cờ phiên bản 2 (m28core.co_v2, QĐ-025): t_flip không còn quyết định cờ
    return dict(ok=ok_t, error="" if ok_t else "t_flip trong file không phải số hoặc null.", t_flip=t if ok_t else None, status=status,
                frozen=not status.startswith(FROZEN_PREFIX), iod_points=list(cfg.get("iod_points") or []), n_points=len(cfg["points"]),
                v2=v2, v2_threshold=float(m["threshold"]) if v2 else None)


def write_t_flip(config_path, value):
    if os.environ.get("M28_PUBLIC_DEMO") == "1":
        raise RunError("Bản demo công khai không đổi ngưỡng low_conf.")
    """Chỉ đổi khoá t_flip (số hợp lệ hoặc None); giữ nguyên MỌI trường khác, thứ tự khoá, định dạng (indent=1, ensure_ascii=False,
    có/không xuống dòng cuối như file hiện có). Ghi nguyên tử; lỗi thì file cũ nguyên vẹn. Trả dict(old, new, path). ValueError/RunError nếu sai."""
    new = parse_t_flip(value)
    try:
        with open(config_path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8")
        cfg = json.loads(text)
    except (OSError, ValueError) as e:
        raise SettingsError(f"Không đọc được {os.path.normpath(config_path)} để sửa t_flip ({type(e).__name__}): không ghi gì.")
    if not isinstance(cfg, dict) or not isinstance(cfg.get("points"), list):
        raise SettingsError(f"{os.path.normpath(config_path)} không đúng định dạng m28_config.json: không ghi gì.")
    if "\r\n" in text:
        raise SettingsError(f"{os.path.normpath(config_path)} dùng xuống dòng kiểu Windows (CRLF): giữ nguyên định dạng nên không tự sửa; "
                            "sửa tay hoặc chạy make_config.py --t-flip.")
    old = cfg.get("t_flip")
    before = json.loads(text)
    cfg["t_flip"] = new
    out = json.dumps(cfg, ensure_ascii=False, indent=1) + ("\n" if text.endswith("\n") else "")
    after = json.loads(out)
    names = lambda c: [p.get("name") for p in c["points"]]     # noqa: E731
    before_rest = {k: v for k, v in before.items() if k != "t_flip"}
    after_rest = {k: v for k, v in after.items() if k != "t_flip"}
    order_kept = "t_flip" not in before or list(before) == list(after)
    if names(before) != names(after) or before_rest != after_rest or not order_kept:
        raise SettingsError("Kết quả ghi thử không giữ nguyên các trường khác của config: không ghi gì.")
    try:
        with open(config_path, "rb") as f:
            if f.read() != raw:
                raise SettingsError("File config vừa bị đổi bởi chương trình khác trong lúc sửa: không ghi gì, thử lại.")
        mode = stat.S_IMODE(os.stat(config_path).st_mode)
        atomic_write(config_path, out.encode("utf-8"), private=False, mode=mode)
    except SettingsError:
        raise
    except OSError as e:
        raise SettingsError(f"Không ghi được {os.path.normpath(config_path)} ({e.strerror or 'lỗi'}): file cũ vẫn nguyên.")
    return dict(old=old, new=new, path=config_path)


def runs_with_flags(runs_root):
    """Tên các lượt trong runs/ đã có flags/flags.json (tính theo t_flip cũ nếu đổi t_flip sau đó). Bỏ thư mục bắt đầu bằng '_'."""
    out = []
    try:
        names = sorted(os.listdir(runs_root))
    except OSError:
        return out
    for n in names:
        if n.startswith("_"):
            continue
        if os.path.isfile(os.path.join(runs_root, n, "flags", "flags.json")):
            out.append(n)
    return out


def busy_runs(runs_root):
    """[(lượt, việc)] các lượt đang có việc chạy (khoá .dang_chay của tiến trình còn sống)."""
    from m28core import dang_chay
    out = []
    try:
        names = sorted(os.listdir(runs_root))
    except OSError:
        return out
    for n in names:
        b = dang_chay.busy(os.path.join(runs_root, n))
        if b:
            out.append((n, b[0]))
    return out


def pipeline_info(project_root):
    """dict(ok, pipe, error, path) từ config/pipeline.json; hỏng/thiếu thì ok=False kèm lý do (không ném SystemExit ra UI)."""
    path = os.path.join(project_root, "config", "pipeline.json")
    try:
        return dict(ok=True, pipe=cvat_io.load_pipeline(path), error="", path=path, exists=os.path.isfile(path))
    except SystemExit as e:
        return dict(ok=False, pipe=dict(cvat_io.DEFAULT_PIPELINE), error=str(e), path=path, exists=True)


# ---------- đọc file cài đặt ----------
def _read_json(path):
    """(dict | None, status) với status 'ok' | 'none' | 'hong' | 'khong_doc'. Không bao giờ đưa nội dung file vào thông báo."""
    try:
        with open(path, "rb") as f:
            raw = f.read(1 << 20)
    except FileNotFoundError:
        return None, "none"
    except OSError:
        return None, "khong_doc"
    try:
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "hong"
    return (d, "ok") if isinstance(d, dict) else (None, "hong")


def _parse_cvat_file(d):
    """dict(url, token, org) hợp lệ, hoặc None nếu sai kiểu / có ký tự lạ."""
    if d.get("version") != 1:
        return None
    out = {}
    for k in ("url", "token", "org"):
        v = d.get(k, "")
        if not isinstance(v, str) or len(v) > 4096 or CTRL_RE.search(v):
            return None
        out[k] = v.strip()
    if out["token"] and check_token(out["token"])[1]:
        return None
    if out["url"] and not check_url(out["url"])["ok"]:
        return None
    if out["org"] and check_org(out["org"])[1]:
        return None
    return out


def _parse_prefs_file(d):
    if d.get("version") != 1:
        return None
    out = {}
    for k in ("reviewer", "images_dir", "model_path"):
        v = d.get(k, "")
        if not isinstance(v, str) or len(v) > 1024 or CTRL_RE.search(v):
            return None
        out[k] = v
    if out["reviewer"] and not REVIEWER_RE.fullmatch(out["reviewer"]):
        out["reviewer"] = ""             # tên lưu từ bản cũ không còn hợp lệ (ví dụ có "_"): chỉ bỏ tên, GIỮ đường dẫn ảnh và model (không coi cả file là hỏng)
    return out


# ---------- Settings ----------
class Settings:
    """Cài đặt dùng chung cả tiến trình trang. environ=None: đọc os.environ MỖI LẦN (biến môi trường đổi giữa chừng thì thấy ngay);
    đưa dict vào để test. Mọi thay đổi dưới khoá, tăng `rev` (để tab trình duyệt cũ biết mình lỗi thời)."""

    def __init__(self, environ=None, platform=None, project_root=None):
        self._environ = environ
        self._platform = platform
        self.project_root = os.path.abspath(project_root or os.path.join(TOOL_DIR, ".."))
        self._lock = threading.RLock()
        self.rev = 0
        self._override = None            # dict(url, token, org, persisted) do Lưu trong phiên
        self._file = {}                  # nội dung cvat.json đã nạp (url, token, org)
        self.file_status = "none"        # none | ok | hong | khong_doc
        self.prefs = dict(reviewer="", images_dir="", model_path="")
        self.prefs_status = "none"
        self.ten_bo = ""                 # tên người rà đã lưu từ bản cũ nhưng không còn hợp lệ (ví dụ có "_"): đã bỏ, tab Cài đặt nhắc đặt lại
        self.dir_error = ""
        self.dir = ""
        self._test = None                # dict(fp, result, when)
        self.load()

    def __repr__(self):                  # không bao giờ in token
        return f"<Settings rev={self.rev} nguon={self.effective()['source']!r}>"

    __str__ = __repr__

    # -- môi trường, thư mục --
    @property
    def environ(self):
        return os.environ if self._environ is None else self._environ

    def _resolve_dir(self):
        try:
            d = user_dir(self.environ, self._platform)
        except SettingsError as e:
            return "", str(e)
        if inside_repo(d, self.project_root):
            return "", (f"Thư mục cài đặt {d} nằm trong repo/thư mục chạy code: từ chối (token sẽ nằm cạnh file có thể bị commit). "
                        "Đặt M28_CONFIG_DIR sang thư mục ngoài repo (ví dụ trong hồ sơ người dùng).")
        return d, ""

    def path_cvat(self):
        return os.path.join(self.dir, FILE_CVAT) if self.dir else ""

    def path_prefs(self):
        return os.path.join(self.dir, FILE_PREFS) if self.dir else ""

    def display_dir(self):
        """Thư mục để hiện cho người dùng (kể cả khi bị từ chối)."""
        if self.dir:
            return self.dir
        try:
            return user_dir(self.environ, self._platform)
        except SettingsError:
            return ""

    # -- nạp --
    def load(self):
        with self._lock:
            self.dir, self.dir_error = self._resolve_dir()
            self._file, self.file_status = {}, "none"
            self.prefs, self.prefs_status = dict(reviewer="", images_dir="", model_path=""), "none"
            if self.dir_error:
                return
            d, st = _read_json(self.path_cvat())
            if st == "ok":
                parsed = _parse_cvat_file(d)
                if parsed is None:
                    st = "hong"
                else:
                    self._file = parsed
                    cvat_io.register_secret(parsed["token"])
            self.file_status = st
            d, st = _read_json(self.path_prefs())
            if st == "ok":
                parsed = _parse_prefs_file(d)
                if parsed is None:
                    st = "hong"
                else:
                    self.prefs = parsed
                    cu = d.get("reviewer") if isinstance(d.get("reviewer"), str) else ""
                    self.ten_bo = cu if cu and not parsed["reviewer"] else ""
            self.prefs_status = st
            env = cvat_io.read_env(self.environ)
            cvat_io.register_secret(env["token"])

    def reload(self):
        with self._lock:
            self.load()
            self.rev += 1

    # -- CVAT --
    def _env_cfg(self):
        e = cvat_io.read_env(self.environ)
        return dict(url=e["url"], token=e["token"], org=e["org"])

    def effective(self):
        """dict(url, token, org, source). session/file (vừa Lưu) > env (đủ link và token) > file đã lưu. Không đủ cả hai thì trả nguồn có
        giá trị đầu tiên (thiếu một nửa, để lý do 'Thiếu …' rõ ràng), không có gì thì source=None."""
        with self._lock:
            cands = []
            if self._override:
                o = self._override
                cands.append(("file" if o["persisted"] else "session", dict(url=o["url"], token=o["token"], org=o["org"])))
            cands.append(("env", self._env_cfg()))
            if self.file_status == "ok":
                cands.append(("file", dict(self._file)))
            for src, c in cands:
                if c["url"] and c["token"]:
                    return dict(c, source=src)
            for src, c in cands:
                if c["url"] or c["token"]:
                    return dict(c, source=src)
            return dict(url="", token="", org="", source=None)

    def cvat_env(self):
        """Giống cvat_io.read_env(): dict(url, token, org) của nguồn đang hiệu lực. Nội bộ, KHÔNG gửi về trình duyệt."""
        e = self.effective()
        return dict(url=e["url"], token=e["token"], org=e["org"])

    def child_env_updates(self):
        """{'CVAT_URL', 'CVAT_ACCESS_TOKEN', ['CVAT_ORG']} cho môi trường của tiến trình con push / xoá task / thử kết nối."""
        e = self.effective()
        out = {}
        if e["url"]:
            out["CVAT_URL"] = e["url"]
        if e["token"]:
            out["CVAT_ACCESS_TOKEN"] = e["token"]
        if e["org"]:
            out["CVAT_ORG"] = e["org"]
        return out

    def env_note(self):
        """Mô tả biến môi trường CVAT_* của cmd (không giá trị token): ('none'|'partial'|'full')."""
        e = self._env_cfg()
        have = [bool(e["url"]), bool(e["token"])]
        return "full" if all(have) else "partial" if any(have) else "none"

    def snapshot(self):
        """Mọi thứ UI cần để vẽ (token chỉ ở dạng che)."""
        with self._lock:
            e = self.effective()
            fp = fingerprint(e["url"], e["token"], e["org"])
            test = self._test if self._test and self._test["fp"] == fp else None
            return dict(rev=self.rev, source=e["source"], source_label=SOURCE_LABEL[e["source"]], url=e["url"], org=e["org"],
                        has_token=bool(e["token"]), token_mask=mask(e["token"]) if e["token"] else "", test=test,
                        env=self.env_note(), file_status=self.file_status, file_path=self.path_cvat(), dir=self.display_dir(),
                        dir_error=self.dir_error, remember=e["source"] == "file", prefs=dict(self.prefs), prefs_status=self.prefs_status, ten_bo=self.ten_bo,
                        prefs_path=self.path_prefs(), file_exists=bool(self.path_cvat()) and os.path.exists(self.path_cvat()))

    def _stale(self, rev):
        return rev is not None and rev != self.rev

    def _bump(self):
        self.rev += 1

    def _remove_file(self, path):
        try:
            os.remove(path)
            return True, ""
        except FileNotFoundError:
            return True, ""
        except OSError as e:
            return False, f"Không xoá được {path} ({e.strerror or 'lỗi'})."

    def save_cvat(self, url, token, org, remember, rev=None):
        if os.environ.get("M28_PUBLIC_DEMO") == "1":
            return dict(ok=False, level="warn", stale=False, msg="Bản demo công khai dùng chung một cài đặt cho mọi người nên không đổi được (CVAT, tên người rà, đường dẫn, ngưỡng).")
        """Lưu link/token/tổ chức cho trang này; remember=True thì ghi thêm cvat.json (0600), False thì xoá cvat.json nếu có.
        token rỗng = giữ token đang dùng (chỉ khi nó không đến từ biến môi trường nếu remember). Trả dict(ok, level, msg, stale, warning)."""
        with self._lock:
            if self._stale(rev):
                return dict(ok=False, level="warn", stale=True, msg="Cài đặt vừa đổi ở tab khác, đã tải lại: kiểm lại rồi bấm Save.")
            u = check_url(url)
            if not u["ok"]:
                return dict(ok=False, level="err", stale=False, msg=u["error"])
            cur = self.effective()
            typed = (token or "").strip() if isinstance(token, str) else ""
            if typed:
                tok, why = check_token(typed)
                if why:
                    return dict(ok=False, level="err", stale=False, msg=why)
            elif cur["token"]:
                if cur["url"] and cvat_io.norm_url(cur["url"]) != u["url"]:
                    return dict(ok=False, level="err", stale=False,
                                msg="Đổi link thì dán lại token vào ô Token (token đang giữ chỉ dành cho link cũ, không tự gửi sang link mới).")
                tok = cur["token"]
                if remember and cur["source"] == "env":
                    return dict(ok=False, level="err", stale=False,
                                msg="Token đang lấy từ biến môi trường của cmd: dán token vào ô Token nếu muốn lưu trên máy này (tool không tự chép "
                                    "token của cmd ra file).")
            else:
                return dict(ok=False, level="err", stale=False, msg="Chưa có token: dán token CVAT vào ô Token.")
            o, why = check_org(org)
            if why:
                return dict(ok=False, level="err", stale=False, msg=why)
            cvat_io.register_secret(tok)
            persisted, notes, level = False, [], "ok"
            if remember:
                if self.dir_error:
                    notes.append("Không lưu ra file được: " + self.dir_error)
                    level = "warn"
                else:
                    try:
                        atomic_write(self.path_cvat(), _dump(dict(version=1, url=u["url"], token=tok, org=o)), private=True)
                        persisted = True
                        self._file = dict(url=u["url"], token=tok, org=o)
                        self.file_status = "ok"
                    except (OSError, SettingsError) as e:
                        notes.append(f"Không ghi được {self.path_cvat()} ({getattr(e, 'strerror', None) or e.__class__.__name__}): "
                                     "kiểm quyền thư mục hoặc đặt M28_CONFIG_DIR sang thư mục khác. Trang vẫn dùng giá trị này trong phiên.")
                        level = "warn"
            elif self.path_cvat() and (os.path.exists(self.path_cvat()) or self.file_status in ("hong", "khong_doc")):
                okd, err = self._remove_file(self.path_cvat())
                if okd:
                    self._file, self.file_status = {}, "none"
                    notes.append("Đã xoá file đã lưu trước đó (bỏ tick Nhớ).")
                else:
                    notes.append(err)
                    level = "warn"
            self._override = dict(url=u["url"], token=tok, org=o, persisted=persisted)
            self._bump()
            msg = ("Đã lưu và Nhớ trên máy này." if persisted else "Đã lưu cho phiên này (không ghi ra file).")
            if self.env_note() != "none":
                notes.append("Biến môi trường CVAT_* trong cmd không đổi; chỉ trang này dùng giá trị mới.")
            if u["warning"]:
                notes.append("Cảnh báo: " + u["warning"])
                level = "warn"
            return dict(ok=True, level=level, stale=False, persisted=persisted, msg=" ".join([msg] + notes))

    def forget_cvat(self, rev=None):
        if os.environ.get("M28_PUBLIC_DEMO") == "1":
            return dict(ok=False, level="warn", stale=False, msg="Bản demo công khai dùng chung một cài đặt cho mọi người nên không đổi được (CVAT, tên người rà, đường dẫn, ngưỡng).")
        """Quên token: xoá cvat.json (kể cả file hỏng) và giá trị đã nhập trong phiên. Biến môi trường của cmd thì không xoá được."""
        with self._lock:
            if self._stale(rev):
                return dict(ok=False, level="warn", stale=True, msg="Cài đặt vừa đổi ở tab khác, đã tải lại: kiểm lại rồi bấm Forget token.")
            level, notes = "ok", []
            if self.path_cvat():
                okd, err = self._remove_file(self.path_cvat())
                if okd:
                    self._file, self.file_status = {}, "none"
                else:
                    notes.append(err)
                    level = "warn"
            self._override = None
            self._test = None
            self._bump()
            env = self.env_note()
            if env != "none":
                notes.append("Token vẫn còn trong biến môi trường của cmd đang chạy trang này (và trang vẫn dùng nó): đóng cmd, hoặc gõ "
                             "set CVAT_ACCESS_TOKEN= rồi mở lại trang để bỏ hẳn.")
                level = "warn"
            return dict(ok=True, level=level, stale=False, env=env,
                        msg=" ".join(["Đã quên token đã nhập và xoá file đã lưu trên máy."] + notes))

    def record_test(self, url, token, org, result):
        with self._lock:
            self._test = dict(fp=fingerprint(url, token, org), result=result, when=time.strftime("%H:%M:%S"), ts=time.time())

    # -- người rà, đường dẫn --
    def _save_prefs(self):
        if self.dir_error:
            return False, self.dir_error
        try:
            atomic_write(self.path_prefs(), _dump(dict(version=1, **self.prefs)), private=True)
            self.prefs_status = "ok"
            return True, ""
        except (OSError, SettingsError) as e:
            return False, (f"Không ghi được {self.path_prefs()} ({getattr(e, 'strerror', None) or e.__class__.__name__}): kiểm quyền thư mục "
                           "hoặc đặt M28_CONFIG_DIR sang thư mục khác. Giá trị vẫn dùng được trong phiên này.")

    def default_reviewer(self):
        return self.prefs.get("reviewer") or ""

    def next_reviewer(self, current):
        """Tên người rà cho LƯỢT MỞ TIẾP THEO: tên mặc định đã lưu nếu có, không thì tên của trang hiện tại."""
        with self._lock:
            return self.prefs.get("reviewer") or current

    def set_reviewer(self, name, rev=None):
        if os.environ.get("M28_PUBLIC_DEMO") == "1":
            return dict(ok=False, level="warn", stale=False, msg="Bản demo công khai dùng chung một cài đặt cho mọi người nên không đổi được (CVAT, tên người rà, đường dẫn, ngưỡng).")
        with self._lock:
            if self._stale(rev):
                return dict(ok=False, level="warn", stale=True, msg="Cài đặt vừa đổi ở tab khác, đã tải lại: kiểm lại rồi bấm Save name.")
            try:
                n = check_reviewer(name)
            except RunError as e:
                return dict(ok=False, level="err", stale=False, msg=str(e))
            self.prefs["reviewer"] = n
            self.ten_bo = ""
            ok, err = self._save_prefs()
            self._bump()
            return dict(ok=True, level="ok" if ok else "warn", stale=False, name=n,
                        msg=f"Đã lưu tên người rà mặc định: {n}." + ("" if ok else " " + err))

    def set_path(self, kind, value, rev=None):
        if os.environ.get("M28_PUBLIC_DEMO") == "1":
            return dict(ok=False, level="warn", stale=False, check=None, msg="Bản demo công khai dùng chung một cài đặt cho mọi người nên không đổi được (CVAT, tên người rà, đường dẫn, ngưỡng).")
        """kind 'images_dir' | 'model_path'. Rỗng = xoá. Phải qua kiểm (không 'err') mới lưu."""
        with self._lock:
            if self._stale(rev):
                return dict(ok=False, level="warn", stale=True, check=None, msg="Cài đặt vừa đổi ở tab khác, đã tải lại: kiểm lại rồi bấm Save.")
            if kind not in ("images_dir", "model_path"):
                raise ValueError(kind)
            try:
                p = clean_path(value)
            except SettingsError as e:
                return dict(ok=False, level="err", stale=False, check=None, msg=str(e))
            chk = None
            if p:
                chk = check_images_dir(p) if kind == "images_dir" else check_model(p)
                if not chk["ok"]:
                    return dict(ok=False, level="err", stale=False, check=chk, msg="Chưa lưu: " + " ".join(chk["lines"]))
            self.prefs[kind] = p
            ok, err = self._save_prefs()
            self._bump()
            what = "thư mục ảnh" if kind == "images_dir" else "đường dẫn model"
            msg = (f"Đã lưu {what}: {p}" if p else f"Đã xoá {what} đã cài (dùng mặc định).") + ("" if ok else " " + err)
            return dict(ok=True, level="ok" if ok else "warn", stale=False, check=chk, msg=msg)

    def images_dir(self):
        return self.prefs.get("images_dir") or None

    def model_path(self):
        return self.prefs.get("model_path") or None


# ---------- một thể hiện dùng chung cả tiến trình ----------
_SETTINGS = None
_LOCK = threading.Lock()


def get():
    """Settings dùng chung của tiến trình (tạo lần đầu gọi; sống qua lần chuyển lượt của main())."""
    global _SETTINGS
    with _LOCK:
        if _SETTINGS is None:
            _SETTINGS = Settings()
        return _SETTINGS


def install(settings):
    """Đặt thể hiện dùng chung (test / chương trình khác). Trả thể hiện cũ."""
    global _SETTINGS
    with _LOCK:
        old, _SETTINGS = _SETTINGS, settings
    return old


def reset():
    install(None)


def cvat_env(environ=None):
    """Thay cho cvat_io.read_env(os.environ). Có `environ` (test cũ) thì dùng đúng nó; không thì lấy từ cài đặt (phiên > env > file)."""
    if environ is not None:
        return cvat_io.read_env(environ)
    return get().cvat_env()


def child_env_updates():
    return get().child_env_updates()


# ---------- thử kết nối CVAT (tiến trình con) ----------
def _err(kind, msg):
    return dict(ok=False, error_kind=kind, message=msg, server_version="", username="", project_found=None, project_id=None, org="")


def test_connection(url, token, org, pipe, *, timeout=TEST_TIMEOUT, python=None, tool_dir=None, project_root=None, environ=None,
                    popen=subprocess.Popen):
    """Thử kết nối CVAT bằng TIẾN TRÌNH CON (cai_dat_thu.py): trang không gọi mạng. Token đi qua biến môi trường của tiến trình con, không
    qua đối số. Kết quả JSON một dòng trên stdout; quá `timeout` giây thì kill. Chỉ ĐỌC trên CVAT (không tạo/sửa gì).
    Trả dict(ok, error_kind, message, server_version, username, project_found, project_id, org); mọi chuỗi đã qua scrub.
    error_kind: bad_url | bad_token | server_down | version_mismatch | redirect | timeout | no_sdk | other."""
    cvat_io.register_secret(token)
    u = check_url(url)
    if not u["ok"]:
        return _err("bad_url", u["error"])
    tok, why = check_token(token)
    if why:
        return _err("bad_token", why)
    o, why = check_org(org)
    if why:
        return _err("other", why)
    tool_dir = TOOL_DIR if tool_dir is None else tool_dir
    root = project_root or os.path.abspath(os.path.join(tool_dir, ".."))
    import nap_anh
    cvat = {"CVAT_URL": u["url"], "CVAT_ACCESS_TOKEN": tok}
    if o:
        cvat["CVAT_ORG"] = o
    env = nap_anh.child_env(environ, cvat=cvat)
    cmd = [python or sys.executable, "-u", os.path.join(tool_dir, PROBE_SCRIPT), "--version", str(pipe["cvat_version"]),
           "--project", str(pipe["project"])]
    try:
        p = popen(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        return _err("other", cvat_io.scrub(f"Không chạy được tiến trình thử kết nối ({e.strerror or e.__class__.__name__}).", tok))
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        try:
            p.communicate(timeout=5)
        except Exception:
            pass
        return _err("timeout", f"Server không trả lời trong {int(timeout)} giây (đã dừng thử). Kiểm CVAT có đang chạy không "
                               "(Ubuntu WSL: docker compose up -d, chờ 1-2 phút) và link đúng chưa.")
    text = cvat_io.scrub(out.decode("utf-8", errors="replace"), tok)
    res = None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict) and "ok" in d:
                res = d
                break
    if res is None:
        tail = cvat_io.scrub((err or b"").decode("utf-8", errors="replace"), tok).strip().splitlines()
        return _err("other", "Tiến trình thử kết nối kết thúc mà không báo kết quả" + (f" ({tail[-1][:200]})" if tail else "") + ".")
    clean = {k: res.get(k, d_) for k, d_ in (("ok", False), ("error_kind", ""), ("message", ""), ("server_version", ""), ("username", ""),
                                             ("project_found", None), ("project_id", None), ("org", ""))}
    for k in ("error_kind", "message", "server_version", "username", "org"):
        clean[k] = cvat_io.scrub(str(clean[k] if clean[k] is not None else ""), tok)
    clean["ok"] = bool(clean["ok"])
    return clean
