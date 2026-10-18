"""Tab "Nạp ảnh" của trang rà soát M28: logic thuần (kiểm ảnh, đặt tên, chạy prepare bằng tiến trình con, đọc kết quả).

Người dùng kéo thả ảnh .jpg/.jpeg/.png vào trang; mỗi lần nạp là một LƯỢT MỚI (runs/<lượt>/inbox/) rồi chạy
`python tool\\m28.py prepare --run <lượt> --images runs\\<lượt>\\inbox --box auto` bằng tiến trình con, xong thì rà lượt đó.

Quy ước (giống review_app.py):
  * Chỉ thư viện chuẩn; PIL nạp lười trong hàm. Không import gradio, torch, mediapipe, cv2 (kiểm cài đặt bằng importlib.util.find_spec).
  * Chỉ ghi dưới runs/<lượt>/ (mọi đường dẫn đích kiểm bằng realpath + commonpath). Không chạy qua shell, không gọi mạng.
  * Ảnh được chép NGUYÊN BYTE vào inbox/ với tên đã làm sạch; tên gốc ghi ở nap_ten_goc.csv (ngoài inbox/).
  * Ảnh người thật chỉ xử lý trên máy này; không đưa ảnh hay ảnh chụp trang ra dịch vụ bên ngoài.

Phần Gradio nằm ở review_app.py (`_nap_tab`); ở đây có cả mô hình hiển thị thuần (HTML tóm tắt, tiến độ) để test không cần gradio.
"""
import collections
import csv
import datetime
import hashlib
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import warnings

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
from m28core import cvat_io, dang_chay, loai_tru  # noqa: E402  (chỉ thư viện chuẩn)

# ---------- hằng số ----------
PREPARE = ["crop", "mediapipe", "map50", "flags", "autoqc", "overlays"]      # chép từ m28.PREPARE (test so khớp)
MAX_BYTES = 25 * 1024 * 1024        # mỗi ảnh
MAX_FILES = 200                     # mỗi lần nạp
MIN_SIDE = 32                       # cạnh ngắn nhất (px)
MAX_PIXELS = 50_000_000
MAX_STEM = 60
EXTS = (".jpg", ".jpeg", ".png")
REAL_FORMATS = {"JPEG": ".jpg", "MPO": ".jpg", "PNG": ".png"}     # định dạng thật -> đuôi lưu (luôn chữ thường)
RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
NAP_DIR = "_nap"                    # runs/_nap/: thư mục tạm của trang khi chưa có lượt nào (--nap)
MODEL_NAME = "face_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
NO_FACE_VI = {"khong_thay_mat": "MediaPipe không thấy mặt", "khong_doc_duoc_anh": "không đọc được ảnh"}
STEP_VI = {"xong": "xong", "bo_qua": "bỏ qua (đã xong từ trước)", "dung": "dừng giữa chừng", "loi": "lỗi", None: "chưa chạy"}
MULTI_FACE_NOTE = ("Ảnh nhiều mặt: `--box auto` chỉ lấy **mặt lớn nhất**; cần mặt khác thì Sửa nhãn trong CVAT.")
LOG_LINES = 500
NOTE_MAX = 500                      # ghi chú của đợt (dot.json)


CLOSING_MSG = "Trang đang đóng (đã bấm Close page): không ghi thêm được."   # dùng chung review_app, dot_ui, ca_kho


class RunError(Exception):
    """Lỗi người dùng sửa được (thiếu file, sai tên...). Thông điệp tiếng Việt, nói rõ cách sửa."""


# ---------- tên ----------
def clean_stem(name):
    """Tên sạch ASCII cho ảnh: phần sau dấu / hoặc \\ cuối, bỏ đuôi ảnh, bỏ dấu tiếng Việt, ký tự lạ -> _, tối đa 60 ký tự."""
    base = re.split(r"[\\/]", str(name))[-1]
    stem, ext = os.path.splitext(base)
    if ext.lower() not in EXTS:
        stem = base
    stem = stem.replace("đ", "d").replace("Đ", "D")
    stem = "".join(c for c in unicodedata.normalize("NFKD", stem) if not unicodedata.combining(c))
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_-.")[:MAX_STEM].strip("_-.")
    if not stem:
        return "anh"
    if stem.upper() in WIN_RESERVED:
        stem += "_anh"
    return stem


def unique_stems(stems):
    """Đánh số _2, _3... cho tên trùng, so KHÔNG phân biệt hoa thường (Windows, CVAT, steps._unique).
    Ví dụ a, A, a_2 -> a, A_2, a_2_2."""
    used, out = set(), []
    for s in stems:
        cand, k = s, 1
        while cand.lower() in used:
            k += 1
            suffix = f"_{k}"
            cand = s[:MAX_STEM - len(suffix)] + suffix if len(s) + len(suffix) > MAX_STEM else s + suffix
        used.add(cand.lower())
        out.append(cand)
    return out


def _mb(n):
    return f"{n / 1048576:.1f}".replace(".", ",") + " MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB"


def _orig(path):
    return re.split(r"[\\/]", str(path))[-1]


# ---------- kiểm ảnh ----------
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def check_image(path, max_bytes=MAX_BYTES, min_side=MIN_SIDE, max_pixels=MAX_PIXELS):
    """(thông tin, None) nếu nhận, (None, lý do tiếng Việt) nếu loại. Không tin đuôi file: phải mở được bằng PIL
    (open + verify, mở lại đọc kích thước) và định dạng thật là JPEG/MPO/PNG. Thông tin: bytes, w, h, ext, format."""
    ext = os.path.splitext(str(path))[1].lower()
    if ext not in EXTS:
        return None, "đuôi file không phải .jpg, .jpeg hoặc .png"
    try:
        size = os.path.getsize(path)
    except OSError:
        return None, "không đọc được file"
    if size <= 0:
        return None, "file rỗng"
    if size > max_bytes:
        return None, f"file {_mb(size)}, lớn hơn giới hạn {_mb(max_bytes)} mỗi ảnh"
    try:
        from PIL import Image
    except ImportError:
        return None, "thiếu thư viện pillow để kiểm ảnh (pip install -r requirements-ui.txt)"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as im:
                fmt, (w, h) = im.format, im.size
                if fmt not in REAL_FORMATS:
                    return None, f"file này thật ra là {fmt or 'không phải ảnh'}, chỉ nhận JPG hoặc PNG"
                if w * h > max_pixels:
                    return None, f"ảnh {w}x{h} quá lớn (tối đa {max_pixels // 1_000_000} triệu điểm ảnh)"
                im.verify()
            with Image.open(path) as im:
                w, h = im.size
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None, f"ảnh quá lớn (tối đa {max_pixels // 1_000_000} triệu điểm ảnh)"
    except Exception:                                   # UnidentifiedImageError, ảnh hỏng/cắt dở, file text đổi đuôi...
        return None, "không mở được như một ảnh JPG/PNG hợp lệ (file hỏng hoặc không phải ảnh)"
    if min(w, h) < min_side:
        return None, f"ảnh {w}x{h} quá nhỏ (cạnh ngắn phải từ {min_side} px)"
    return dict(bytes=size, w=w, h=h, ext=REAL_FORMATS[fmt], format=fmt), None


def plan_upload(paths, max_bytes=MAX_BYTES, max_files=MAX_FILES, min_side=MIN_SIDE, max_pixels=MAX_PIXELS):
    """Duyệt các file người dùng thả vào. Trả dict(ok=[...], rejected=[(tên gốc, lý do)]).
    Mỗi ảnh nhận: orig, stem, ext, bytes, w, h, sha256, src. Ảnh quá giới hạn số lượng, trùng nội dung (sha256) TRONG lần nạp này hoặc lỗi bị loại
    (ảnh đã có ở đợt khác vẫn nạp được: mỗi đợt độc lập)."""
    ok, rejected, seen = [], [], {}
    for p in paths or []:
        orig = _orig(p)
        if len(ok) >= max_files:
            rejected.append((orig, f"vượt {max_files} ảnh mỗi lần"))
            continue
        info, why = check_image(p, max_bytes, min_side, max_pixels)
        if why:
            rejected.append((orig, why))
            continue
        try:
            sha = _sha256(p)
        except OSError:
            rejected.append((orig, "không đọc được file"))
            continue
        if sha in seen:
            rejected.append((orig, f"trùng nội dung với {seen[sha]}"))
            continue
        seen[sha] = orig
        ok.append(dict(orig=orig, stem="", ext=info["ext"], bytes=info["bytes"], w=info["w"], h=info["h"], sha256=sha,
                       src=str(p)))
    for it, stem in zip(ok, unique_stems([clean_stem(it["orig"]) for it in ok])):
        it["stem"] = stem
    return dict(ok=ok, rejected=rejected)


def new_name(item):
    return item["stem"] + item["ext"]


# ---------- tên lượt, thư mục ----------
def _listing(runs_root):
    try:
        return os.listdir(runs_root)
    except OSError:
        return []


def next_run_name(runs_root):
    """NAP_001, NAP_002... : số lớn nhất trong các thư mục runs/NAP_<số> (không phân biệt hoa thường) + 1."""
    names = _listing(runs_root)
    n = 0
    deleted = [d.split("__")[0] for d in _listing(os.path.join(runs_root, "_trash"))]      # đợt đã xoá mềm: không dùng lại tên
    for d in names + deleted:
        m = re.fullmatch(r"NAP_(\d+)", d, re.IGNORECASE)
        if m and (d in deleted or os.path.isdir(os.path.join(runs_root, d))):
            n = max(n, int(m.group(1)))
    taken = {d.lower() for d in names}
    n += 1
    while f"nap_{n:03d}" in taken:
        n += 1
    return f"NAP_{n:03d}"


def check_run_name(name, runs_root):
    """Tên lượt hợp lệ (đã bỏ khoảng trắng hai đầu) hoặc RunError. Không trùng thư mục/file có sẵn (so không phân biệt hoa thường)."""
    name = (name or "").strip()
    if not RUN_RE.fullmatch(name):
        raise RunError(f"Tên lượt {name!r} không hợp lệ: chỉ dùng chữ không dấu, số, gạch dưới, gạch ngang, bắt đầu bằng chữ hoặc số, "
                       "tối đa 32 ký tự (ví dụ NAP_001, KHACH_A).")
    if name.upper() in WIN_RESERVED:
        raise RunError(f"Tên lượt {name} là tên dành riêng của Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9): đặt tên khác.")
    if name.lower() in {d.lower() for d in _listing(runs_root)}:
        raise RunError(f"Lượt {name} đã có trong {os.path.normpath(runs_root)}: nạp ảnh luôn tạo lượt mới, hãy đặt tên khác "
                       "hoặc để trống để tự đặt NAP_xxx.")
    return name


def runs_layout(run_dir):
    """(runs_root, project_root, lỗi|None). m28 dùng đường dẫn tương đối runs/ từ thư mục chạy nên runs_root phải tên `runs`."""
    runs_root = os.path.dirname(os.path.abspath(run_dir))
    project_root = os.path.dirname(runs_root)
    if os.path.basename(runs_root).lower() != "runs":
        return runs_root, project_root, ("Tab Nạp ảnh chưa dùng được: chạy trang từ thư mục source-tool\\m28-prelabel "
                                         "(có thư mục runs\\), ví dụ python tool\\review_app.py --nap P2.")
    return runs_root, project_root, None


def _inside(path, base):
    try:
        p, b = os.path.realpath(path), os.path.realpath(base)
        return os.path.commonpath([p, b]) == b
    except ValueError:                                   # khác ổ đĩa
        return False


def clean_note(note):
    """Ghi chú của đợt: bỏ ký tự điều khiển, gọn khoảng trắng, tối đa NOTE_MAX ký tự."""
    t = "".join(c if c in "\n\t" or ord(c) >= 32 else " " for c in str(note or ""))
    return re.sub(r"[ \t]+", " ", t).strip()[:NOTE_MAX]


def stage_upload(runs_root, run, plan, cleanup_root=None, note="", reviewer=""):
    """Tạo runs/<lượt>/inbox/ (giữ chỗ nguyên tử), chép NGUYÊN BYTE các ảnh nhận, ghi nap_ten_goc.csv và dot.json (tên đợt, ngày nạp,
    ghi chú, người nạp, số ảnh). Trả đường dẫn runs/<lượt>.
    Lượt đã có -> RunError, không bao giờ ghi vào lượt cũ. cleanup_root: xoá (best effort) bản tạm trong thư mục này sau khi chép."""
    run = check_run_name(run, runs_root)
    if not plan["ok"]:
        raise RunError("Chưa có ảnh hợp lệ nào để nạp.")
    os.makedirs(runs_root, exist_ok=True)
    run_dir = os.path.join(runs_root, run)
    try:
        os.mkdir(run_dir)                                # mkdir nguyên tử: FileExistsError nếu lượt đã có
        inbox = os.path.join(run_dir, "inbox")
        os.mkdir(inbox)
    except FileExistsError:
        raise RunError(f"Lượt {run} đã có: nạp ảnh luôn tạo lượt mới, đặt tên khác.")
    except OSError as e:
        raise RunError(f"Không tạo được thư mục lượt {run} ({e}).")
    try:
        if not _inside(run_dir, runs_root):
            raise RunError("Đường dẫn lượt nằm ngoài thư mục runs: từ chối.")
        rows = []
        for it in plan["ok"]:
            dest = os.path.join(inbox, new_name(it))
            if not _inside(dest, run_dir):
                raise RunError(f"Đường dẫn đích của {it['orig']} nằm ngoài runs\\{run}: từ chối.")
            try:
                shutil.copyfile(it["src"], dest)
                if _sha256(dest) != it["sha256"]:
                    raise RunError(f"Bản chép của {it['orig']} khác bản gốc (file bị đổi trong lúc nạp): thả lại ảnh.")
            except OSError as e:
                raise RunError(f"Không chép được {it['orig']} ({e}): thả lại ảnh.")
            rows.append([it["orig"], new_name(it), it["bytes"], it["sha256"]])
        csv_path = os.path.join(run_dir, "nap_ten_goc.csv")
        if not _inside(csv_path, run_dir):
            raise RunError("Đường dẫn nap_ten_goc.csv nằm ngoài lượt: từ chối.")
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:      # BOM để Excel đọc đúng chữ có dấu
            w = csv.writer(f)
            w.writerow(["ten_goc", "ten_moi", "bytes", "sha256"])
            w.writerows(rows)
        cvat_io.atomic_write_json(os.path.join(run_dir, "dot.json"), dict(
            ten=run, ngay_nap=datetime.datetime.now().isoformat(timespec="seconds"), ghi_chu=clean_note(note),
            nguoi_nap=str(reviewer or ""), so_anh=len(rows)))
    except BaseException:
        shutil.rmtree(run_dir, ignore_errors=True)       # lượt vừa tạo dở ở trên, chưa ai dùng
        raise
    if cleanup_root:
        for it in plan["ok"]:
            if _inside(it["src"], cleanup_root) and os.path.realpath(it["src"]) != os.path.realpath(cleanup_root):
                try:
                    os.remove(it["src"])
                except OSError:
                    pass
    return run_dir


def make_upload_thumb(src, out_dir, key, size=160):
    """Ảnh nhỏ JPEG ~size px cho lưới xem trước (đã xoay theo EXIF). Trả đường dẫn hoặc None nếu lỗi."""
    try:
        from PIL import Image, ImageOps
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, re.sub(r"[^\w.-]", "_", key) + ".jpg")
        if os.path.exists(out):
            return out
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((size, size), Image.Resampling.LANCZOS)
            tmp = out + f".tmp{os.getpid()}"
            im.save(tmp, format="JPEG", quality=85)
        os.replace(tmp, out)
        return out
    except Exception:
        return None


# ---------- kiểm môi trường, lệnh ----------
def preflight(project_root, tool_dir=None):
    """Danh sách lỗi (tiếng Việt, kèm cách sửa) trước khi chạy prepare; rỗng = ổn."""
    tool_dir = TOOL_DIR if tool_dir is None else tool_dir
    errs = []
    for rel, who in (("m28_config.json", "file cấu hình 50 điểm của P3"), ("map_mp50.json", "file ánh xạ 478 -> 50 điểm của P3")):
        p = os.path.join(project_root, "config", rel)
        if not os.path.isfile(p):
            errs.append(f"Thiếu config\\{rel} ({who}) trong {os.path.normpath(project_root)}: "
                        "chạy trang từ thư mục source-tool\\m28-prelabel hoặc lấy lại file từ repo (git checkout config).")
    if not configured_model() and not any(os.path.isfile(os.path.join(d, MODEL_NAME)) for d in (project_root, tool_dir)):
        errs.append(f"Thiếu {MODEL_NAME} (model MediaPipe, khoảng 3,7 MB): trong cmd, ở thư mục chạy lệnh, gõ "
                    f"curl -L -o {MODEL_NAME} {MODEL_URL} (xem HUONG-DAN-WINDOWS mục 3), hoặc chọn file bằng nút Paths ở đầu trang.")
    for mod, pip in (("mediapipe", "mediapipe"), ("cv2", "opencv-python")):
        try:
            found = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            errs.append(f"Chưa cài {mod}: gõ python -m pip install -r requirements.txt (gói {pip}).")
    return errs


def configured_model():
    """Đường dẫn model do người dùng cài ở tab Cài đặt nếu file còn đó, không thì None (khi đó m28.py tìm model mặc định như cũ)."""
    import cai_dat                                  # nạp lười: cai_dat import nap_anh (RunError, quy tắc tên người rà)
    p = cai_dat.get().model_path()
    return p if p and os.path.isfile(p) else None


def prepare_cmd(run, tool_dir=None, python=None, model=None):
    """Lệnh chạy prepare (list đối số, không shell). Chạy với cwd = thư mục cha của runs/. model: đường dẫn face_landmarker.task đã cài
    ở tab Cài đặt (thêm --model); None thì m28.py tìm model mặc định. Prepare không cần và không nhận token CVAT."""
    tool_dir = TOOL_DIR if tool_dir is None else tool_dir
    cmd = [python or sys.executable, "-u", os.path.join(tool_dir, "m28.py"), "prepare", "--run", run,
           "--images", os.path.join("runs", run, "inbox"), "--box", "auto"]
    if model:
        cmd += ["--model", model]
    return cmd


CVAT_ENV_KEYS = ("CVAT_URL", "CVAT_ACCESS_TOKEN", "CVAT_ORG")


def child_env(environ=None, cvat=None):
    """Bản sao môi trường cho tiến trình con. UTF-8 bắt buộc: trên Windows stdout là pipe (cp1252) và m28 in chữ có dấu.
    Biến CVAT_* của môi trường gốc luôn bị bỏ; chỉ khi `cvat` (dict CVAT_URL/CVAT_ACCESS_TOKEN/[CVAT_ORG], xem cai_dat.child_env_updates)
    được truyền (push, xoá task, thử kết nối) thì chúng mới vào môi trường tiến trình con. Token chỉ đi bằng đường này, không qua đối số."""
    env = dict(os.environ if environ is None else environ)
    for k in CVAT_ENV_KEYS:
        env.pop(k, None)
    env.update(cvat or {})
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    return env


# ---------- tiến độ ----------
def parse_progress(lines, n_inbox=0, n_crop_files=None):
    """Tiến độ từ các dòng m28 in ra: dòng bắt đầu bằng "<bước>:" hoặc "bỏ qua <bước>" = bước xong. Trong bước crop, tiến độ con
    = số ảnh cắt đã có / số ảnh trong inbox (n_crop_files=None: không biết hoặc crop đã xong từ trước).
    Trả dict(done, total, current, frac, label, steps=[(bước, "xong"|"dang_chay"|"cho")])."""
    done = []
    for ln in lines:
        s = ln.strip()
        for step in PREPARE:
            if (s.startswith(step + ":") or s.startswith("bỏ qua " + step)) and step not in done:
                done.append(step)
    total = len(PREPARE)
    cur = next((s for s in PREPARE if s not in done), None)
    sub = 0.0
    if cur == "crop" and n_crop_files is not None and n_inbox:
        sub = min(0.95, n_crop_files / n_inbox)
    frac = (len(done) + sub) / total
    if cur is None:
        label = f"Xong {total}/{total} bước"
    elif not lines and not (cur == "crop" and sub):
        label = "Đang nạp MediaPipe…"
    else:
        label = f"Bước {len(done) + 1}/{total} · {cur}"
        if cur == "crop" and n_crop_files is not None and n_inbox:
            label += f" ({min(n_crop_files, n_inbox)}/{n_inbox} ảnh)"
    steps = [(s, "xong" if s in done else "dang_chay" if s == cur else "cho") for s in PREPARE]
    return dict(done=len(done), total=total, current=cur, frac=frac, label=label, steps=steps)


def count_files(path, exts=EXTS):
    try:
        return sum(1 for f in os.listdir(path) if f.lower().endswith(exts))
    except OSError:
        return 0


def auto_open_action(run, snap):
    """Việc của nút Upload & Open ở mỗi nhịp đồng hồ: `run` = lượt đang chờ tự mở (None = không chờ), `snap` = job.snapshot().
    'none' không chờ gì; 'wait' lượt đó còn đang chuẩn bị; 'go' lượt đó chuẩn bị xong → chuyển trang sang lượt đó (một lần);
    'drop' lượt đó lỗi, bị huỷ hoặc job đã sang lượt khác → bỏ yêu cầu (mở tay ở tab Các đợt → Open batch khi cần)."""
    if not run:
        return "none"
    if snap.get("run") != run:
        return "drop"
    st = snap.get("state")
    if st == "dang_chay":
        return "wait"
    return "go" if st == "xong" else "drop"


def job_progress(run_dir, lines):
    """parse_progress cho một lượt trên đĩa (đếm ảnh inbox và ảnh cắt)."""
    n_inbox = count_files(os.path.join(run_dir, "inbox"))
    crop_done = os.path.exists(os.path.join(run_dir, "crop", "done.txt"))
    n_crop = None if crop_done else count_files(os.path.join(run_dir, "crop", "images"), (".png",))
    return parse_progress(lines, n_inbox, n_crop)


# ---------- tiến trình con ----------
class ChildJob:
    """Một việc chạy bằng tiến trình con, một job một lúc. Luồng nền đọc stdout (UTF-8, đã lọc token), giữ 500 dòng cuối và nối vào
    runs/<lượt>/<LOG_NAME> (log còn sau lỗi/huỷ/tải lại trang). Ghi file khoá runs/<lượt>/.dang_chay khi chạy (để xoá ảnh/đợt/task bị
    chặn, kể cả khi trang khác đang chạy). state: chua | dang_chay | xong | loi | da_huy. popen thay được khi test."""
    KIND = "job"
    LOG_NAME = "job_log.txt"
    NEEDS_CVAT = False                  # True: tiến trình con nhận CVAT_URL/CVAT_ACCESS_TOKEN từ cài đặt của trang (push, xoá task)
    LOCK = True

    def __init__(self, popen=subprocess.Popen):
        self._popen = popen
        self._lock = threading.RLock()
        self.state, self.returncode, self.run, self.run_dir = "chua", None, None, None
        self.lines = collections.deque(maxlen=LOG_LINES)
        self._proc = self._thread = None
        self._cancelled = False
        self._t0 = self._t1 = None

    @property
    def running(self):
        return self.state == "dang_chay"

    def _launch(self, run, run_dir, cmd, project_root, header):
        """Gọi trong self._lock. Ghi khoá, mở log, chạy tiến trình con, bật luồng đọc."""
        self.run, self.run_dir = run, run_dir
        self.lines.clear()
        self.returncode, self._cancelled = None, False
        self._t0, self._t1 = time.monotonic(), None
        log_path = os.path.join(run_dir, self.LOG_NAME) if self.LOG_NAME else os.devnull
        if self.LOCK and not dang_chay.acquire(run_dir, self.KIND):
            other = dang_chay.busy(run_dir)
            raise RunError(f"Lượt {run} đang có việc khác chạy ({other[0] if other else '?'}): chờ xong rồi thử lại.")
        try:
            with open(log_path, "a", encoding="utf-8", newline="\n") as f:
                f.write(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} {header} ===\n")
            self._proc = self._popen(cmd, cwd=project_root, env=self._child_env(), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as e:
            if self.LOCK:
                dang_chay.release(run_dir)
            self.lines.append(f"Không chạy được tiến trình {self.KIND}: {e}")
            self.state, self._t1 = "loi", time.monotonic()
            return
        self.state = "dang_chay"
        self._thread = threading.Thread(target=self._read, args=(self._proc, log_path, run_dir), daemon=True)
        self._thread.start()

    def _child_env(self):
        if not self.NEEDS_CVAT:
            return child_env()
        import cai_dat
        return child_env(cvat=cai_dat.child_env_updates())

    def _read(self, proc, log_path, run_dir):
        try:
            with open(log_path, "a", encoding="utf-8", newline="\n") as log:
                for raw in iter(proc.stdout.readline, b""):
                    line = cvat_io.scrub(raw.decode("utf-8", errors="replace").rstrip("\r\n"))      # token không bao giờ vào log
                    self.lines.append(line)
                    log.write(line + "\n")
                    log.flush()
        except (OSError, ValueError):
            pass
        rc = proc.wait()
        if self.LOCK:
            dang_chay.release(run_dir)                      # gỡ dấu "lượt đang bận" TRƯỚC khi báo xong: trang thấy xong rồi bấm việc kế tiếp ngay thì không bị báo bận nhầm
        with self._lock:
            self.returncode = rc
            self.state = "xong" if rc == 0 else "da_huy" if self._cancelled else "loi"
            self._t1 = time.monotonic()

    def cancel(self):
        """terminate(), chờ 5 giây, rồi kill(). Trả True nếu có job đang chạy để huỷ."""
        with self._lock:
            proc = self._proc
            if not self.running or proc is None:
                return False
            self._cancelled = True
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5)
        return True

    def snapshot(self):
        with self._lock:
            end = self._t1 if self._t1 is not None else time.monotonic()
            return dict(state=self.state, returncode=self.returncode, run=self.run, run_dir=self.run_dir, kind=self.KIND,
                        lines=list(self.lines), elapsed=0.0 if self._t0 is None else end - self._t0,
                        cancelling=self._cancelled and self.state == "dang_chay")


class PrepareJob(ChildJob):
    """Một lần chạy prepare bằng tiến trình con (log: runs/<lượt>/nap_log.txt). Chạy lại được sau loi/da_huy."""
    KIND = "prepare"
    LOG_NAME = "nap_log.txt"

    def start(self, run, runs_root, project_root, tool_dir=None, python=None):
        """Chạy prepare cho lượt `run` (thư mục runs_root/run đã có inbox/). Đang chạy thì RunError."""
        if os.environ.get("M28_PUBLIC_DEMO") == "1":
            raise RunError("Bản demo công khai không nạp ảnh mới: dùng đợt mẫu NAP_001. Cài tool về máy để nạp ảnh của bạn.")
        with self._lock:
            if self.running:
                raise RunError(f"Đang chuẩn bị lượt {self.run}: chờ xong hoặc bấm Cancel ở tab Nạp ảnh.")
            run_dir = os.path.join(runs_root, run)
            if not _inside(run_dir, runs_root) or not os.path.isdir(os.path.join(run_dir, "inbox")):
                raise RunError(f"Lượt {run} chưa có thư mục inbox: không chạy được.")
            self._launch(run, run_dir, prepare_cmd(run, tool_dir, python, configured_model()), project_root, f"prepare --run {run}")


TASK_RE = cvat_io.TASK_NAME_RE                                     # tên task: <người>-<đợt> (QĐ-021) hoặc demo-… kiểu cũ; chữ không dấu, số, _ -


def task_ok(task):
    """Tên task tiến trình con push / xoá task / gộp được dùng: đúng TASK_RE và không phải task chung m28-… (cvat_io.tool_task_name_ok)."""
    return cvat_io.tool_task_name_ok(task)
REVIEWER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,31}")      # tên người rà: không có "_" (là dấu ngăn trong tên file raw\\<task>\\<task>_<người>_<DDMM>.xml), bắt đầu bằng chữ/số


def check_reviewer(name):
    """Nơi DUY NHẤT định nghĩa quy tắc tên người rà (review_app.check_reviewer và tab Cài đặt gọi hàm này). Trả tên nếu hợp lệ, không thì RunError."""
    if not isinstance(name, str) or not REVIEWER_RE.fullmatch(name):
        raise RunError(f"Tên người rà {name!r} không hợp lệ: chỉ dùng chữ không dấu, số và gạch ngang, bắt đầu bằng chữ hoặc số "
                       "(tối đa 32 ký tự, không dùng gạch dưới), ví dụ P2 hoặc Lan-2. Tên này nằm trong tên file triage_<tên>.csv và raw\\<task>\\<task>_<tên>_<DDMM>.xml.")
    return name


def push_cmd(run, reviewer, task, tool_dir=None, python=None, images=None):
    """Lệnh push (list đối số, không shell). CVAT_URL/CVAT_ACCESS_TOKEN đi qua MÔI TRƯỜNG của tiến trình con (child_env), không bao giờ qua
    đối số. images: thư mục ảnh đã cài ở tab Cài đặt, chỉ truyền khi lượt cần (ảnh gốc ở đường dẫn cũ không còn, steps._upload_path
    tìm lại theo <thư mục>/<rel>)."""
    tool_dir = TOOL_DIR if tool_dir is None else tool_dir
    cmd = [python or sys.executable, "-u", os.path.join(tool_dir, "m28.py"), "push", "--run", run, "--reviewer", reviewer, "--task", task]
    if images:
        cmd += ["--images", images]
    return cmd


def delete_task_cmd(run, task, tool_dir=None, python=None):
    """Lệnh xoá task (push --cleanup): chỉ xoá task ghi trong push.json của lượt, và chỉ khi --confirm-name gõ đúng tên."""
    tool_dir = TOOL_DIR if tool_dir is None else tool_dir
    return [python or sys.executable, "-u", os.path.join(tool_dir, "m28.py"), "push", "--run", run, "--cleanup", "--confirm-name", task]


def _check_cvat_start(job, run, runs_root, task):
    run_dir = os.path.join(runs_root, run)
    if not RUN_RE.fullmatch(run or "") or not os.path.isdir(run_dir) or not _inside(run_dir, runs_root):
        raise RunError(f"Lượt {run!r} không có trong {os.path.normpath(runs_root)}.")
    if not task_ok(task):
        raise RunError(f"Tên task {task!r} không hợp lệ: chỉ chữ không dấu, số, _ - (ví dụ Kien-NAP_005), không phải task chung {cvat_io.RESERVED_PREFIX}…")
    return run_dir


class PushJob(ChildJob):
    """Một lần đẩy lên CVAT bằng `m28.py push` (tiến trình con; chỉ tiến trình con gọi mạng). Log: runs/<lượt>/push_log.txt."""
    KIND = "push"
    LOG_NAME = "push_log.txt"
    NEEDS_CVAT = True

    def start(self, run, runs_root, project_root, reviewer, task, tool_dir=None, python=None, images=None):
        with self._lock:
            if self.running:
                raise RunError(f"Đang đẩy lượt {self.run} lên CVAT: chờ xong hoặc bấm Cancel.")
            run_dir = _check_cvat_start(self, run, runs_root, task)
            if not REVIEWER_RE.fullmatch(reviewer or ""):
                raise RunError(f"Tên người rà {reviewer!r} không hợp lệ.")
            self._launch(run, run_dir, push_cmd(run, reviewer, task, tool_dir, python, images), project_root, f"push --run {run} --task {task}")


class DeleteTaskJob(ChildJob):
    """Xoá task trên CVAT bằng `m28.py push --cleanup --confirm-name <tên>`. Cùng log push_log.txt của lượt."""
    KIND = "xoa_task"
    LOG_NAME = "push_log.txt"
    NEEDS_CVAT = True

    def start(self, run, runs_root, project_root, task, tool_dir=None, python=None):
        with self._lock:
            if self.running:
                raise RunError(f"Đang xoá task của lượt {self.run}: chờ xong.")
            run_dir = _check_cvat_start(self, run, runs_root, task)
            self._launch(run, run_dir, delete_task_cmd(run, task, tool_dir, python), project_root,
                         f"xoa task --run {run} --confirm-name {task}")


NGUOI_DO_RE = REVIEWER_RE               # người của đồng hồ / gói kết quả (= dong_ho.NGUOI_RE)
EXIT_CHUA_XONG = 3                      # = m28core.collect.EXIT_CHUA_XONG: --require-completed chặn vì còn job chưa completed
DONG_XML, DONG_CHUA_XONG = "COLLECT_XML: ", "COLLECT_JOBS_PENDING: "


def collect_cmd(task, person, tool_dir=None, python=None, force=False):
    """Lệnh gộp job của nút Merge jobs & Finish: collect cả task thành MỘT file raw/<task>/<task>_<Pk>_<DDMM>.xml (--overwrite: xuất lại nhãn mới nhất,
    --no-per-job: không tách file job). force=False thêm --require-completed (còn job chưa completed thì chưa xuất, thoát mã 3).
    Token KHÔNG ở đây: đi qua môi trường của tiến trình con."""
    tool_dir = TOOL_DIR if tool_dir is None else tool_dir
    cmd = [python or sys.executable, "-u", os.path.join(tool_dir, "m28.py"), "collect", "--task", task, "--reviewer", person, "--overwrite", "--no-per-job"]
    return cmd if force else cmd + ["--require-completed"]


class CollectJob(ChildJob):
    """Gộp các job của task CVAT của MỘT đợt thành một file (`m28.py collect`, tiến trình con; chỉ tiến trình con gọi mạng). Log: runs/<lượt>/collect_log.txt.
    force: bỏ --require-completed (người dùng đã xác nhận gộp dù còn job chưa completed)."""
    KIND = "collect"
    LOG_NAME = "collect_log.txt"
    NEEDS_CVAT = True

    def __init__(self, popen=subprocess.Popen):
        super().__init__(popen)
        self.person = self.task = None
        self.force = False

    def start(self, run, runs_root, project_root, person, task, force=False, tool_dir=None, python=None):
        with self._lock:
            if self.running:
                raise RunError(f"Đang gộp job của đợt {self.run}: chờ xong hoặc bấm Cancel ở khung gộp job của tab Các đợt.")
            run_dir = _check_cvat_start(self, run, runs_root, task)
            if not isinstance(person, str) or not NGUOI_DO_RE.fullmatch(person):
                raise RunError(f"Người {person!r} không hợp lệ: tên chỉ chữ không dấu, số và dấu -, bắt đầu bằng chữ hoặc số, tối đa 32 ký tự (đặt bằng nút Reviewer ở đầu trang).")
            self.person, self.task, self.force = person, task, bool(force)
            self._launch(run, run_dir, collect_cmd(task, person, tool_dir, python, force), project_root,
                         f"collect --task {task} --reviewer {person} --overwrite --no-per-job" + ("" if force else " --require-completed"))

    def snapshot(self):
        s = super().snapshot()
        with self._lock:
            s.update(person=self.person, task=self.task, force=self.force)
        return s


def jobs_cmd(run, tool_dir=None, python=None, reopen=False):
    """Đọc trạng thái job (chỉ đọc); reopen=True (nút Fix again): mở lại các job đã completed rồi đọc lại."""
    tool_dir = TOOL_DIR if tool_dir is None else tool_dir
    return [python or sys.executable, "-u", os.path.join(tool_dir, "cvat_jobs.py"), "--run", run] + (["--reopen"] if reopen else [])


class JobsJob(ChildJob):
    KIND = "cvat_jobs"
    LOG_NAME = None
    NEEDS_CVAT = True
    LOCK = False

    def start(self, run, runs_root, project_root, tool_dir=None, python=None, reopen=False):
        with self._lock:
            if self.running:
                raise RunError(f"Đang đọc trạng thái job của lượt {self.run}: chờ xong.")
            run_dir = os.path.join(runs_root, run)
            if not RUN_RE.fullmatch(run or "") or not os.path.isdir(run_dir) or not _inside(run_dir, runs_root):
                raise RunError(f"Lượt {run!r} không có trong {os.path.normpath(runs_root)}.")
            self._launch(run, run_dir, jobs_cmd(run, tool_dir, python, reopen), project_root,
                         f"cvat_jobs --run {run}" + (" --reopen" if reopen else ""))


DONG_JOBS, DONG_JOBS_LOI = "CVAT_JOBS: ", "CVAT_JOBS_LOI: "


def read_jobs_result(lines, task_id=None):
    for d in reversed(_json_dong(lines, DONG_JOBS)):
        if task_id is not None and d.get("task_id") != task_id:
            continue
        return dict(jobs=_jobs_sach(d.get("jobs")), loi=None)
    for d in reversed(_json_dong(lines, DONG_JOBS_LOI)):
        return dict(jobs=[], loi=str(d.get("loi") or "")[:400] or "Không đọc được trạng thái job.")
    return dict(jobs=[], loi=None)


def _json_dong(lines, prefix):
    out = []
    for ln in lines:
        if ln.startswith(prefix):
            try:
                d = json.loads(ln[len(prefix):])
            except ValueError:
                continue
            if isinstance(d, dict):
                out.append(d)
    return out


def _so(v):
    """Số nguyên thật (không nhận bool) hoặc None."""
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _jobs_sach(jobs):
    """Danh sách job từ dòng máy đọc, chỉ giữ trường cần và đúng kiểu (giá trị từ tiến trình con, không tin mù). kind: nhan | gan_tay | khong_ro."""
    out = []
    for j in jobs if isinstance(jobs, list) else []:
        if not isinstance(j, dict) or _so(j.get("id")) is None:
            continue
        out.append(dict(id=j["id"], state=str(j.get("state", ""))[:40], stage=str(j.get("stage", ""))[:40], type=str(j.get("type") or "annotation")[:40],
                        start=_so(j.get("start")), stop=_so(j.get("stop")), n=_so(j.get("n")),
                        kind=j.get("kind") if j.get("kind") in ("nhan", "gan_tay") else "khong_ro"))
    return out


def read_collect_result(lines, project_root, task, person):
    """Kết quả của CollectJob từ các dòng log: dict(xml=đường dẫn tuyệt đối | None, xml_rel, jobs=[...], pending=[...] | None).
    Chỉ nhận file nằm trong <project>/raw/<task>/ (cách lưu hiện nay) hoặc ngay trong <project>/raw (bản cũ); không nhận thư mục con khác như raw/_cu/.
    Tên đúng <task>_<person>_<DDMM>.xml (không đoán tên theo ngày của trang: tiến trình con có thể chạy qua nửa đêm). pending: danh sách job chưa completed khi --require-completed chặn (None nếu không bị chặn)."""
    raw_dir = os.path.join(project_root, "raw")
    out = dict(xml=None, xml_rel="", jobs=[], pending=None)
    pat = re.compile(re.escape(task) + "_" + re.escape(person) + r"_\d{4}\.xml")
    for d in _json_dong(lines, DONG_XML):
        if d.get("task") != task or d.get("nguoi") != person or not isinstance(d.get("xml"), str):
            continue
        rel = d["xml"].replace("\\", "/")
        if not pat.fullmatch(os.path.basename(rel)):
            continue
        p = os.path.normpath(os.path.join(project_root, *rel.split("/")))
        try:
            cha = os.path.dirname(os.path.realpath(p))
            o_task = cha == os.path.realpath(os.path.join(raw_dir, task)) and task != "_cu"
            ngay_raw = cha == os.path.realpath(raw_dir)
        except (OSError, ValueError):
            o_task = ngay_raw = False
        if not (o_task or ngay_raw) or not _inside(p, raw_dir) or not os.path.isfile(p):
            continue
        rel = os.path.join("raw", task, os.path.basename(p)) if o_task else os.path.join("raw", os.path.basename(p))
        out.update(xml=p, xml_rel=rel, jobs=_jobs_sach(d.get("jobs")))
    for d in _json_dong(lines, DONG_CHUA_XONG):
        if d.get("task") != task:
            continue
        jobs = _jobs_sach(d.get("jobs"))
        pend = d.get("pending") if isinstance(d.get("pending"), list) else []
        ids = {i for i in pend if isinstance(i, int) and not isinstance(i, bool)}
        out.update(jobs=jobs, pending=[j for j in jobs if j["id"] in ids])
    return out


SMOKE_DIR = "_smoke"                # runs/_smoke/: nơi cvat_smoke.py ghi dữ liệu giả, đánh dấu dang_mo.json và báo cáo
SMOKE_N = 12                        # số bước của cvat_smoke.py
SMOKE_LINE = re.compile(r"^\[(\d+)/12\] ([^:]+): (.*)$")
SMOKE_REPORT_RE = re.compile(r"bao_cao_\d{8}_\d{6}(_\d+)?\.json")


def smoke_cmd(tool_dir=None, python=None, giu_task=False, giu_project=False, root=None):
    """Lệnh chạy cvat_smoke.py (list đối số, không shell). Token KHÔNG bao giờ ở đây: đi qua môi trường của tiến trình con (child_env).
    root: thư mục m28-prelabel của trang (để runs\\_smoke của tiến trình con trùng với runs_root của trang)."""
    tool_dir = TOOL_DIR if tool_dir is None else tool_dir
    cmd = [python or sys.executable, "-u", os.path.join(tool_dir, "cvat_smoke.py")]
    if root:
        cmd += ["--root", root]
    if giu_task:
        cmd.append("--giu-task")
    if giu_project:
        cmd.append("--giu-project")
    return cmd


def smoke_progress(lines):
    """Tiến độ từ các dòng `[k/12] <tên bước>: ...` của cvat_smoke.py (dòng `[k/6]` của push bị bỏ qua).
    Trả dict(k, frac, label, ket_qua) với ket_qua là ĐẠT/HỎNG/BỎ QUA của bước cuối đã xong hoặc None khi bước đang chạy."""
    last = None
    for ln in lines:
        m = SMOKE_LINE.match(ln.strip())
        if m and 1 <= int(m.group(1)) <= SMOKE_N:
            last = m
    if last is None:
        return dict(k=0, frac=0.0, label="Đang khởi động…", ket_qua=None)
    k, name, note = int(last.group(1)), last.group(2), last.group(3)
    running = note.startswith("đang chạy")
    kq = None if running else next((x for x in ("ĐẠT", "HỎNG", "BỎ QUA") if note.startswith(x)), None)
    return dict(k=k, frac=((k - 1) if running else k) / SMOKE_N, label=f"Bước {k}/{SMOKE_N} · {name}" + (f" · {kq}" if kq else ""), ket_qua=kq)


def read_smoke_report(run_dir, lines):
    """Báo cáo .json do dòng `SMOKE_JSON: <đường dẫn>` chỉ tới; chỉ nhận file tên bao_cao_<giờ>.json NẰM TRONG run_dir (runs/_smoke). Không có/hỏng thì None."""
    path = None
    for ln in lines:
        if ln.startswith("SMOKE_JSON: "):
            path = ln[len("SMOKE_JSON: "):].strip()
    if not path or not run_dir or not SMOKE_REPORT_RE.fullmatch(os.path.basename(path)) or not _inside(path, run_dir):
        return None
    try:
        if os.path.getsize(path) > 1024 * 1024:
            return None
        rep = _jload(path)
    except (OSError, ValueError):
        return None
    return rep if isinstance(rep, dict) and isinstance(rep.get("buoc"), list) else None


class SmokeJob(ChildJob):
    """Kiểm tra nhanh CVAT bằng `python tool\\cvat_smoke.py` (tiến trình con; chỉ tiến trình con gọi mạng). Log: runs/_smoke/smoke_log.txt.
    Token đi qua môi trường của tiến trình con (NEEDS_CVAT: link/token/tổ chức đang hiệu lực ở tab Cài đặt, kể cả giá trị nhập trong phiên)."""
    KIND = "cvat_smoke"
    LOG_NAME = "smoke_log.txt"
    NEEDS_CVAT = True

    def start(self, runs_root, project_root, giu_task=False, giu_project=False, tool_dir=None, python=None):
        with self._lock:
            if self.running:
                raise RunError("Đang chạy kiểm tra nhanh CVAT: chờ xong hoặc bấm Cancel check.")
            run_dir = os.path.join(runs_root, SMOKE_DIR)
            if not _inside(run_dir, runs_root):
                raise RunError(f"{run_dir} nằm ngoài {runs_root}: từ chối.")
            os.makedirs(run_dir, exist_ok=True)
            self._launch(SMOKE_DIR, run_dir, smoke_cmd(tool_dir, python, giu_task, giu_project, root=project_root), project_root,
                         "cvat_smoke" + (" --giu-task" if giu_task else "") + (" --giu-project" if giu_project else ""))


# ---------- đọc kết quả prepare ----------
def _jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _orig_names(run_dir):
    """{tên mới không đuôi: tên gốc} từ nap_ten_goc.csv."""
    out = {}
    try:
        with open(os.path.join(run_dir, "nap_ten_goc.csv"), encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                out[os.path.splitext(r["ten_moi"])[0]] = r["ten_goc"]
    except (OSError, KeyError, csv.Error):
        pass
    return out


def _step_status(run_dir):
    st = {s: None for s in PREPARE}
    try:
        with open(os.path.join(run_dir, "log.txt"), encoding="utf-8") as f:
            for ln in f:
                p = ln.rstrip("\n").split("\t")
                if len(p) >= 3 and p[1] in st:
                    st[p[1]] = p[2]
    except OSError:
        pass
    return st


def read_prepare_result(run_dir, read_no_face=None):
    """Kết quả prepare của một lượt: số ảnh, số mặt dùng được (khoá flags.json), mặt không dùng được (tách bước crop và
    bước mediapipe), số mặt vào hàng đợi rà, trạng thái từng bước. read_no_face(run_dir) -> {tên: (lý do, bước)} (mặc định
    review_app._read_no_face)."""
    if read_no_face is None:
        from review_app import _read_no_face as read_no_face
    flags, gone = {}, loai_tru.read_excluded(run_dir)
    fpath = os.path.join(run_dir, "flags", "flags.json")
    if os.path.isfile(fpath):
        try:
            data = _jload(fpath)
            flags = {k: v for k, v in data.items() if k not in gone} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            flags = {}
    origs = _orig_names(run_dir)
    crop_dir = os.path.join(run_dir, "crop", "images")
    no_crop, no_draft = [], []
    for name, (why, step) in sorted(read_no_face(run_dir).items()):
        if name in flags or name in gone:
            continue
        row = dict(name=name, orig=origs.get(name, name), reason=NO_FACE_VI.get(why, why or "không rõ"), step=step)
        (no_draft if os.path.isfile(os.path.join(crop_dir, name + ".png")) else no_crop).append(row)
    return dict(run=os.path.basename(os.path.normpath(run_dir)), n_inbox=count_files(os.path.join(run_dir, "inbox")),
                n_faces=len(flags), no_crop=no_crop, no_draft=no_draft, n_queue=len(flags) + len(no_draft),
                steps=_step_status(run_dir))


# ---------- mô hình hiển thị (HTML thuần) ----------
def push_command(run, reviewer):
    return f"python tool\\m28.py push --run {run} --reviewer {reviewer} --task {cvat_io.task_name_for(reviewer, run)} --review-file triage_{reviewer}.csv"


def reopen_command(run_dir, reviewer):
    return f"python tool\\review_app.py runs\\{os.path.basename(os.path.normpath(run_dir))} {reviewer}"


def _e(x):
    return html.escape(str(x))


def preflight_html(errors, layout_error=None):
    if os.environ.get("M28_PUBLIC_DEMO") == "1":          # demo công khai: không có model, không nạp ảnh; nói rõ thay vì báo lỗi thiếu file
        return ('<div class="nap-box nap-warn" role="status"><b>Bản demo công khai không nạp ảnh mới.</b> Dùng đợt mẫu NAP_001 (10 mặt đã qua MediaPipe) '
                'ở bước 2 Rà soát. Cài tool về máy để nạp ảnh của bạn (hướng dẫn ở GitHub).</div>')
    errs = ([layout_error] if layout_error else []) + list(errors)
    if not errs:
        return '<div class="nap-box nap-ok nap-ready" role="status"><span class="nap-dot" aria-hidden="true"></span><b>Đủ model và cấu hình.</b> Có thể nạp ảnh.</div>'
    items = "".join(f"<li>{_e(e)}</li>" for e in errs)
    return (f'<div class="nap-box nap-err" role="alert"><b>Chưa nạp ảnh được:</b><ul>{items}</ul></div>')


def count_html(plan):
    if not plan or (not plan["ok"] and not plan["rejected"]):
        return ""                                       # chưa chọn ảnh: không ghi gì (khung kéo thả đã nói rõ)
    n_bad = len(plan["rejected"])                       # danh sách ảnh bị loại: popup Log prepare (có biểu tượng báo cạnh nút, log_flag_html)
    return (f'<div class="nap-count"><span><b>{len(plan["ok"])}</b> ảnh hợp lệ · <b>{n_bad}</b> bị loại</span>{COUNT_BTNS}</div>')


FLAG_ICON = {
    "warn": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "err": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
}


def log_flag_html(n_rej, snap, res=None):
    """Biểu tượng nhỏ bên phải nút Log prepare khi có cảnh báo hoặc lỗi (bấm = mở Log prepare). Một biểu tượng: có cảnh báo thì hiện cảnh báo
    (ưu tiên theo chủ repo), chỉ có lỗi thì hiện lỗi. Cảnh báo: ảnh bị loại lúc chọn, prepare bị huỷ, prepare xong nhưng có ảnh không cắt được /
    không có nháp / bước chưa xong. Lỗi: prepare dừng với lỗi."""
    st = (snap or {}).get("state")
    warns, errs = [], []
    if n_rej:
        warns.append(f"{n_rej} ảnh bị loại")
    if st == "da_huy":
        warns.append("prepare đã huỷ")
    if st == "xong" and res:
        if res.get("no_crop"):
            warns.append(f"{len(res['no_crop'])} ảnh không cắt được mặt")
        if res.get("no_draft"):
            warns.append(f"{len(res['no_draft'])} mặt không có nháp")
        if any(v not in ("xong", "bo_qua") for v in (res.get("steps") or {}).values()):
            warns.append("có bước prepare chưa xong")
    if st == "loi":
        rc = (snap or {}).get("returncode")
        errs.append("prepare dừng với lỗi" + (f" (mã {rc})" if rc is not None else ""))
    kind = "warn" if warns else ("err" if errs else "")
    if not kind:
        return ""
    what = "Cảnh báo" if kind == "warn" else "Lỗi"
    tip = f"{what}: " + " · ".join(warns + errs) + ". Bấm để xem Log prepare."
    return (f'<button type="button" class="nap-flag nap-flag-{kind}" data-nap-flag title="{_e(tip)}" aria-label="{_e(tip)}">'
            f'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{FLAG_ICON[kind]}</svg></button>')


# Đã chọn ảnh thì ô kéo thả ẩn đi (CSS #nap-drop:has(.file-preview-holder)); hai nút của nó (thêm ảnh, bỏ hết) chuyển xuống dòng đếm này.
# JS (review_app.NAP_X_JS) bấm hộ đúng nút gốc của Gradio trong ô kéo thả: thêm ảnh = cộng vào các ảnh đã chọn, bỏ hết = ô kéo thả hiện lại.
COUNT_BTNS = ('<span class="nap-count-btns">'
              '<button type="button" class="nap-cbtn" data-nap-add title="Thêm ảnh vào lần nạp này" aria-label="Thêm ảnh">'
              '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round" aria-hidden="true"><path d="M12 15V3M7 8l5-5 5 5M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/></svg></button>'
              '<button type="button" class="nap-cbtn" data-nap-clear title="Bỏ hết ảnh đã chọn" aria-label="Bỏ hết ảnh đã chọn">'
              '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button></span>')


def rejected_html(plan):
    rej = plan["rejected"] if plan else []
    if not rej:
        return ""
    items = "".join(f"<li><b>{_e(o)}</b>: {_e(why)}</li>" for o, why in rej)
    return f'<div class="nap-box nap-warn"><b>Bị loại ({len(rej)}):</b><ul>{items}</ul></div>'


def gallery_items(plan, thumb_dir):
    """[(đường dẫn ảnh nhỏ, chú thích "tên mới · 1,2 MB")] cho gr.Gallery."""
    out = []
    for it in plan["ok"] if plan else []:
        t = make_upload_thumb(it["src"], thumb_dir, f"{it['sha256'][:12]}_{it['stem']}")
        if t:
            out.append((t, f"{new_name(it)} · {_mb(it['bytes'])}"))
    return out


STATE_VI = {"chua": "Chưa chạy", "dang_chay": "Đang chạy", "xong": "Xong", "loi": "Lỗi", "da_huy": "Đã huỷ"}


def _mmss(sec):
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def progress_html(snap, prog):
    """Thanh tiến độ (kiểu .m28-bar) + dòng trạng thái."""
    st = snap["state"]
    if st == "chua":
        return ""
    pct = 100 if st == "xong" else round(100 * prog["frac"])
    label = prog["label"] if st == "dang_chay" else STATE_VI[st] + (
        f" (mã thoát {snap['returncode']})" if st == "loi" and snap["returncode"] is not None else "")
    if st == "dang_chay" and snap.get("cancelling"):
        label = "Đang huỷ…"
    cls = {"xong": "nap-st-ok", "loi": "nap-st-err", "da_huy": "nap-st-warn"}.get(st, "")
    return (f'<div class="nap-prog {cls}"><div class="nap-prog-top"><span class="nap-run">Lượt <b>{_e(snap["run"])}</b></span>'
            f'<span class="nap-label">{_e(label)}</span><span class="nap-time">{_mmss(snap["elapsed"])}</span></div>'
            f'<div class="m28-bar" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100">'
            f'<i style="width:{pct}%"></i></div></div>')


def _note_md(text):
    """Chỉ đổi **đậm** và `mã` sang thẻ HTML (sau khi escape)."""
    t = _e(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)


def summary_html(res, reviewer, snap=None):
    """Tóm tắt kết quả prepare: thẻ số, danh sách mặt không dùng được, ghi chú nhiều mặt, lệnh push gợi ý."""
    run = res["run"]
    cards = "".join(f'<div class="nap-card"><b>{v}</b><span>{_e(t)}</span></div>' for t, v in (
        ("Mặt dùng được", res["n_faces"]), ("Không thấy mặt", len(res["no_crop"]) + len(res["no_draft"])),
        ("Vào hàng đợi rà", res["n_queue"])))
    out = [f'<div class="nap-sum"><div class="nap-sum-title">Kết quả lượt <b>{_e(run)}</b> · {res["n_inbox"]} ảnh đã nạp</div>'
           f'<div class="nap-cards">{cards}</div>']
    if res["no_crop"]:
        items = "".join(f"<li><b>{_e(r['orig'])}</b>: {_e(r['reason'])}</li>" for r in res["no_crop"])
        out.append(f'<div class="nap-box nap-warn"><b>Bước crop: không có ảnh cắt ({len(res["no_crop"])}), '
                   f'push tự xếp vào Bỏ:</b><ul>{items}</ul></div>')
    if res["no_draft"]:
        items = "".join(f"<li><b>{_e(r['orig'])}</b>: {_e(r['reason'])}</li>" for r in res["no_draft"])
        out.append(f'<div class="nap-box nap-warn"><b>Bước mediapipe: không có nháp ({len(res["no_draft"])}), '
                   f'vẫn vào hàng đợi rà (chỉ Sửa nhãn hoặc Bỏ):</b><ul>{items}</ul></div>')
    bad = [(s, v) for s, v in res["steps"].items() if v not in ("xong", "bo_qua")]
    if bad:
        out.append('<div class="nap-box nap-warn">Trạng thái bước (log.txt): ' + ", ".join(f"{_e(s)}: {_e(STEP_VI.get(v, v))}" for s, v in bad) + "</div>")
    out.append(f'<div class="nap-note">{_note_md(MULTI_FACE_NOTE)}</div>')
    out.append('<div class="nap-note">Sau khi rà xong, đẩy lên CVAT bằng lệnh (cmd, từ thư mục source-tool\\m28-prelabel; ảnh gốc lấy từ '
               f'<code>crop\\meta.json</code>):<br><code class="nap-cmd">{_e(push_command(run, reviewer))}</code></div></div>')
    return "".join(out)


def empty_run_html(res, entry, why=""):
    bad = res["no_crop"] + res["no_draft"]
    items = "".join(f"<li>{_e(r['orig'])}: {_e(r['reason'])}</li>" for r in bad) or f"<li>{res['n_inbox']} ảnh: không ảnh nào cắt được mặt</li>"
    if entry:
        kept = (f"Đợt rỗng <b>{_e(res['run'])}</b> đã chuyển vào thùng rác (khôi phục được ở tab Các đợt, mục đợt đã xoá); "
                "không tạo đợt hay task nào để rà.")
    else:
        kept = f"Chưa chuyển được đợt <b>{_e(res['run'])}</b> vào thùng rác: {_e(why)} Xoá tay ở tab Các đợt."
    return (f'<div class="nap-box nap-err" role="alert"><b>Không có mặt nào để rà trong {res["n_inbox"]} ảnh vừa nạp.</b><ul>{items}</ul>'
            f'<div class="nap-note">{kept} Nạp ảnh khác có mặt người lái rõ ràng để tiếp tục.</div></div>')


def failure_html(snap):
    st = snap["state"]
    if st == "loi":
        return ('<div class="nap-box nap-err" role="alert"><b>prepare dừng với lỗi'
                + (f" (mã {snap['returncode']})" if snap["returncode"] is not None else "")
                + '.</b> Xem dòng cuối trong <b>Log prepare</b> (tự mở; mở lại bằng nút ở góc phải khung trên cùng), sửa nguyên nhân rồi bấm <b>Retry</b> (bước đã xong được bỏ qua).</div>')
    if st == "da_huy":
        return ('<div class="nap-box nap-warn" role="status"><b>Đã huỷ.</b> Ảnh vẫn nằm trong inbox của lượt; bấm <b>Retry</b> để chạy tiếp '
                "(lượt dở nằm trong runs\\, xoá tay nếu không cần).</div>")
    return ""
