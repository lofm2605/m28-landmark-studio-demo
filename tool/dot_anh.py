"""Tab "Các đợt" của trang rà soát M28: logic thuần (liệt kê đợt, thẻ đợt, lưới ảnh, xoá mềm ảnh/đợt, thùng rác, khôi phục).

Mỗi đợt = một thư mục lượt runs/<lượt> (có inbox/ hoặc crop/; tên bắt đầu bằng _ như _nap, _trash không phải đợt).
Quy ước (giống nap_anh.py / review_app.py):
  * Chỉ thư viện chuẩn; PIL nạp lười trong hàm. Không import gradio, numpy, steps, torch, mediapipe, cv2. Không gọi mạng.
  * XOÁ MỀM: tên mặt vào runs/<lượt>/excluded.txt TRƯỚC, rồi file của ảnh (inbox/<file>, crop/images/<tên>.png, overlays/<tên>.png)
    chuyển bằng os.replace vào runs/<lượt>/_trash/<thời điểm>_<tên>/files/<đường dẫn gốc> kèm manifest.json. Không sửa meta.json,
    flags.json, mp50.json, pred478.json, autoqc.csv, no_face.csv, triage_*.csv: loại trừ chỉ là bộ lọc lúc đọc, khôi phục = gỡ tên
    khỏi danh sách và chuyển file về chỗ cũ (đích đã có file thì từ chối).
  * Xoá cả đợt: os.replace(runs/<lượt>, runs/_trash/<lượt>__<YYYYmmdd-HHMMSS>); khôi phục được nếu tên chưa bị dùng lại.
  * Mọi đường dẫn nguồn/đích kiểm bằng nap_anh._inside (realpath + commonpath): symlink trỏ ra ngoài bị từ chối. Tên đợt và tên ảnh
    đến từ trình duyệt chỉ được dùng khi là phần tử của danh sách do server tính, không bao giờ ghép đường dẫn từ chuỗi của client.
  * Xoá ảnh/đợt bị chặn khi lượt đang có việc chạy (file khoá .dang_chay: prepare, push, xoá task, gộp job).
Ảnh nhỏ cho lưới tạo bằng PIL (≈160 px, JPEG, xoay EXIF) và nhúng data URI: không mở thêm đường phát file của Gradio.
"""
import base64
import collections
import csv
import datetime
import glob
import html
import io
import json
import os
import re
import shutil
import sys
import time

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import nap_anh  # noqa: E402
from m28core import cvat_io, dang_chay, loai_tru, phan_loai  # noqa: E402
from nap_anh import RUN_RE, RunError, _inside  # noqa: E402

PAGE_SIZE = 24
GRID_COLS, GRID_ROWS = 6, 3                  # popup quản lý đợt: 3 hàng ảnh mỗi trang, có nút trang trước / trang sau
THUMB_PX = 160
TRASH = "_trash"
RUN_TRASH = "_trash"                                           # runs/_trash/: các đợt đã xoá
ENTRY_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9_-]{0,31})__(\d{8}-\d{6})")
FOLDER_RE = re.compile(r"(\d{8}-\d{6})_([A-Za-z0-9._-]{1,80})(?:_\d+)?")
NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,80}")
TOKEN_TTL = 600                                                # giây: yêu cầu xác nhận quá cũ bị bỏ
STATUS_VI = {"nhan": "Nhận", "gan_tay": "Sửa nhãn", "bo": "Bỏ", "": "Chưa rà", "khong_thay_mat": "Không thấy mặt",
             "khong_dung_duoc": "Không dùng được"}
DECISION_VI = {"nhan": "Nhận", "gan_tay": "Sửa nhãn", "bo": "Bỏ ảnh", "": "chưa rà"}
S_PREPARING, S_NOT_READY, S_NOT_REVIEWED, S_REVIEWING, S_DONE = "dang_chuan_bi", "chua_prepare", "chua_ra", "dang_ra", "da_xong"
S_PUSHING, S_PUSHED, S_PARTIAL, S_DELETING = "dang_day", "da_day", "day_do", "dang_xoa_task"
S_COLLECTING = "dang_gop"                                      # nút Merge jobs & Finish đang chạy collect (khoá .dang_chay loại "collect")
S_COMPLETED = "hoan_thanh"                                     # đã đẩy CVAT và đã gộp job xuất file nhãn gộp: thẻ đợt hiện "Completed"
BUSY_STATES = (S_PREPARING, S_PUSHING, S_DELETING, S_COLLECTING)
GOP_FILE = "gop_job.json"                                      # runs/<lượt>/gop_job.json: kết quả lần gộp job gần nhất (gop_job.write_gop)


# ---------- đọc dữ liệu ----------
def _jload(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_dot(run_dir):
    """dot.json (ghi khi nạp) hoặc {}."""
    d = _jload(os.path.join(run_dir, "dot.json"))
    return d if isinstance(d, dict) else {}


def read_push(run_dir):
    """push.json hoặc None; file hỏng thì {"trang_thai": "hong"} (trang không vỡ)."""
    p = os.path.join(run_dir, "push.json")
    if not os.path.exists(p):
        return None
    d = _jload(p)
    return d if isinstance(d, dict) else {"trang_thai": "hong"}


def read_gop(run_dir):
    """gop_job.json (ghi khi Merge jobs & Finish xuất được file gộp) hoặc None; thiếu/hỏng thì None (trang không vỡ)."""
    d = _jload(os.path.join(run_dir, GOP_FILE))
    return d if isinstance(d, dict) else None


def is_merged(g):
    """gop_job.json (đã đọc) cho biết đã xuất được file nhãn gộp (có đường dẫn xml)."""
    return isinstance(g, dict) and isinstance(g.get("xml"), str) and bool(g["xml"])


def run_date(run_dir):
    """Chuỗi ISO ngày nạp: dot.json, rồi dòng đầu log.txt, rồi mtime thư mục."""
    d = read_dot(run_dir).get("ngay_nap")
    if isinstance(d, str) and d:
        return d
    try:
        with open(os.path.join(run_dir, "log.txt"), encoding="utf-8") as f:
            first = f.readline().split("\t")[0].strip()
        datetime.datetime.strptime(first, "%Y-%m-%d %H:%M:%S")
        return first.replace(" ", "T")
    except (OSError, ValueError):
        pass
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(run_dir)).isoformat(timespec="seconds")
    except OSError:
        return ""


def fmt_date(iso):
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return iso or "?"


def is_run_dir(path):
    return os.path.isdir(path) and (os.path.isdir(os.path.join(path, "inbox")) or os.path.isdir(os.path.join(path, "crop")))


def list_runs(runs_root):
    """Tên các đợt (hợp lệ theo RUN_RE, là thư mục lượt thật nằm trong runs_root), mới nhất trước."""
    out = []
    try:
        names = os.listdir(runs_root)
    except OSError:
        return []
    for n in names:
        p = os.path.join(runs_root, n)
        if RUN_RE.fullmatch(n) and is_run_dir(p) and _inside(p, runs_root):
            out.append((run_date(p), n))
    out.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [n for _d, n in out]


def valid_run(runs_root, run):
    """Đường dẫn runs/<run> nếu `run` là đợt trong danh sách do server tính, không thì RunError."""
    if not isinstance(run, str) or not RUN_RE.fullmatch(run) or run not in list_runs(runs_root):
        raise RunError(f"Đợt {run!r} không có trong danh sách đợt (danh sách đã làm mới).")
    p = os.path.join(runs_root, run)
    if not _inside(p, runs_root):
        raise RunError(f"Đợt {run} nằm ngoài thư mục runs: từ chối.")
    return p


_CACHE = {}


def _cached(path, loader):
    """Đọc JSON lớn (meta.json, mp50.json) một lần cho mỗi (mtime, size)."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    c = _CACHE.get(path)
    if c and c[0] == key:
        return c[1]
    val = loader(path)
    _CACHE[path] = (key, val)
    if len(_CACHE) > 64:
        _CACHE.pop(next(iter(_CACHE)))
    return val


def read_flags_names(run_dir):
    d = _cached(os.path.join(run_dir, "flags", "flags.json"), _jload)
    return list(d) if isinstance(d, dict) else []


def read_meta(run_dir):
    d = _cached(os.path.join(run_dir, "crop", "meta.json"), _jload)
    return d if isinstance(d, dict) else {}


def read_mp50(run_dir):
    """mp50.json (nháp 50 điểm của máy: {tên: {orig, flip}}) hoặc {}; đọc một lần cho mỗi (mtime, size). Không sửa kết quả trả về."""
    d = _cached(os.path.join(run_dir, "map50", "mp50.json"), _jload)
    return d if isinstance(d, dict) else {}


def queue_names(run_dir, excluded=None):
    """Tên các mặt trong hàng đợi rà: mọi mặt trong flags.json, cộng mặt no_face còn ảnh cắt; trừ mặt xoá mềm.
    Trả (danh sách tên, số mặt không dùng được = no_face không có ảnh cắt). Khớp review_app.load_queue (có test so sánh)."""
    gone = loai_tru.read_excluded(run_dir) if excluded is None else excluded
    flags = [n for n in read_flags_names(run_dir) if n not in gone]
    have = set(flags)
    unusable = 0
    crop = os.path.join(run_dir, "crop", "images")
    for n in phan_loai.read_no_face(run_dir):
        if n in have or n in gone:
            continue
        if os.path.isfile(os.path.join(crop, n + ".png")):
            flags.append(n)
            have.add(n)
        else:
            unusable += 1
    return flags, unusable


def triage_of(run_dir, reviewer):
    """({tên: (quyết định, lý do)}, lỗi|None)."""
    p = os.path.join(run_dir, "review", f"triage_{reviewer}.csv")
    if not os.path.isfile(p):
        return {}, None
    try:
        return phan_loai.read_triage(p), None
    except (OSError, UnicodeDecodeError, ValueError, csv.Error) as e:
        return {}, f"không đọc được {os.path.basename(p)} ({type(e).__name__})"


def other_reviewers(run_dir, reviewer):
    out = []
    for p in sorted(glob.glob(os.path.join(glob.escape(os.path.join(run_dir, "review")), "triage_*.csv"))):
        who = os.path.basename(p)[len("triage_"):-len(".csv")]
        if who and who != reviewer:
            out.append(who)
    return out


def count_trash(run_dir):
    return len(list_trash(run_dir))


def counts(run_dir, reviewer):
    """Số Nhận / Sửa nhãn / Bỏ / Chưa rà của người rà hiện tại (dòng cuối mỗi tên, đã trừ ảnh xoá mềm) và hàng đợi."""
    gone = loai_tru.read_excluded(run_dir)
    names, unusable = queue_names(run_dir, gone)
    tri, err = triage_of(run_dir, reviewer)
    c = collections.Counter()
    for n in names:
        d = tri.get(n, ("", ""))[0]
        c[d if d in phan_loai.DECISIONS else ""] += 1
    return dict(total=len(names), nhan=c["nhan"], gan_tay=c["gan_tay"], bo=c["bo"], chua_ra=c[""], khong_dung_duoc=unusable, loi=err)


def run_busy(run_dir):
    """(loại việc, pid) nếu lượt đang có prepare/push/xoá task/gộp job chạy (file khoá .dang_chay còn sống), không thì None."""
    return dang_chay.busy(run_dir)


def run_state(run_dir, info):
    """(mã trạng thái, chữ hiển thị). info = kết quả counts + các cờ."""
    busy = run_busy(run_dir)
    if busy:
        kind = busy[0]
        if kind == "push":
            return S_PUSHING, "Đang đẩy lên CVAT"
        if kind == "xoa_task":
            return S_DELETING, "Đang xoá task trên CVAT"
        if kind == "collect":
            return S_COLLECTING, "Đang gộp job (CVAT)"
        return S_PREPARING, "Đang chuẩn bị"
    ps = read_push(run_dir)
    st = (ps or {}).get("trang_thai")
    if st == "xong":
        if is_merged(read_gop(run_dir)):
            return S_COMPLETED, "Completed"                  # đã gộp job: hết việc ở CVAT (nút Merge vẫn xuất lại được nếu sửa nhãn thêm)
        return S_PUSHED, "Đã đẩy CVAT"                     # tên task và id ở khung CVAT của popup quản lý đợt, trang Gộp & kết thúc
    if st in ("dang_tao", "da_tao", "da_nhap", "hong"):
        vi = {"dang_tao": "đang tạo task, chưa có id", "da_tao": "đã tạo task, chưa nhập nhãn", "da_nhap": "đã nhập nhãn, chưa kiểm xong",
              "hong": "push.json hỏng"}[st]
        return S_PARTIAL, f"Đẩy dở: {vi}"
    if not os.path.isfile(os.path.join(run_dir, "flags", "flags.json")):
        return S_NOT_READY, "Chưa prepare xong"
    if info["chua_ra"] == 0 and info["total"] > 0:
        return S_DONE, "Đã chốt" if os.path.isfile(os.path.join(run_dir, "review", "done.txt")) else "Đã rà hết"
    if info["nhan"] + info["gan_tay"] + info["bo"] == 0:
        return S_NOT_REVIEWED, "Chưa rà"
    return S_REVIEWING, "Đang rà"


def run_info(run_dir, reviewer):
    """Mọi thứ thẻ đợt cần (dict thuần, JSON được)."""
    name = os.path.basename(os.path.normpath(run_dir))
    dot = read_dot(run_dir)
    c = counts(run_dir, reviewer)
    inbox = os.path.join(run_dir, "inbox")
    if os.path.isdir(inbox):
        n_img = nap_anh.count_files(inbox)
    else:
        universe = set(read_meta(run_dir)) | set(read_flags_names(run_dir)) | set(phan_loai.read_no_face(run_dir))
        n_img = len(universe - loai_tru.read_excluded(run_dir))
    code, text = run_state(run_dir, c)
    ps = read_push(run_dir)
    return dict(name=name, ngay=run_date(run_dir), ghi_chu=str(dot.get("ghi_chu", "")), nguoi_nap=str(dot.get("nguoi_nap", "")),
                so_anh=n_img, nhan=c["nhan"], gan_tay=c["gan_tay"], bo=c["bo"], chua_ra=c["chua_ra"], khong_dung_duoc=c["khong_dung_duoc"],
                total=c["total"], loi_triage=c["loi"], nguoi_khac=other_reviewers(run_dir, reviewer), trash=count_trash(run_dir),
                state=code, state_text=text, push=ps, ready=os.path.isfile(os.path.join(run_dir, "flags", "flags.json")),
                task_deleted=(ps or {}).get("trang_thai") == "task_deleted", gop=read_gop(run_dir))


# ---------- ảnh của đợt ----------
def image_names(run_dir):
    """Tên (không đuôi) các ảnh còn sống của đợt, sắp theo tên. Đợt nạp: theo inbox/; đợt không có inbox: theo ảnh cắt, flags, no_face."""
    gone = loai_tru.read_excluded(run_dir)
    names = set()
    inbox = os.path.join(run_dir, "inbox")
    if os.path.isdir(inbox):
        for f in os.listdir(inbox):
            b, e = os.path.splitext(f)
            if e.lower() in nap_anh.EXTS:
                names.add(b)
    else:
        crop = os.path.join(run_dir, "crop", "images")
        if os.path.isdir(crop):
            names |= {os.path.splitext(f)[0] for f in os.listdir(crop) if f.lower().endswith(".png")}
        names |= set(read_flags_names(run_dir)) | set(phan_loai.read_no_face(run_dir))
    names -= gone
    return sorted(names, key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)])


def _find_inbox(run_dir, name):
    inbox = os.path.join(run_dir, "inbox")
    if not os.path.isdir(inbox):
        return None
    for f in os.listdir(inbox):
        b, e = os.path.splitext(f)
        if b == name and e.lower() in nap_anh.EXTS:
            return os.path.join(inbox, f)
    return None


def image_source(run_dir, name):
    """Đường dẫn ảnh dùng làm ảnh nhỏ: ảnh gốc trong inbox/, không thì ảnh cắt crop/images/ (None nếu không có)."""
    p = _find_inbox(run_dir, name)
    if p:
        return p
    c = os.path.join(run_dir, "crop", "images", name + ".png")
    return c if os.path.isfile(c) else None


def image_rows(run_dir, reviewer):
    """[dict(name, orig, status, status_text, src)] cho lưới ảnh."""
    origs = nap_anh._orig_names(run_dir)
    tri, _err = triage_of(run_dir, reviewer)
    nf = phan_loai.read_no_face(run_dir)
    flags = set(read_flags_names(run_dir))
    crop = os.path.join(run_dir, "crop", "images")
    out = []
    for n in image_names(run_dir):
        d = tri.get(n, ("", ""))[0]
        if d in phan_loai.DECISIONS:
            st = d
        elif n in flags:
            st = ""
        elif n in nf:
            st = "khong_thay_mat" if os.path.isfile(os.path.join(crop, n + ".png")) else "khong_dung_duoc"
        else:
            st = ""
        out.append(dict(name=n, orig=origs.get(n, n), status=st, status_text=STATUS_VI.get(st, st), src=image_source(run_dir, n)))
    return out


def page_slice(items, page, size=PAGE_SIZE):
    n_pages = max(1, -(-len(items) // size))
    page = min(max(int(page or 0), 0), n_pages - 1)
    return list(items[page * size:(page + 1) * size]), page, n_pages


_THUMBS = collections.OrderedDict()
_PLACEHOLDER = ("data:image/svg+xml;base64," + base64.b64encode(
    ('<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160"><rect width="160" height="160" fill="#d6d6d6"/>'
     '<text x="80" y="84" font-size="13" text-anchor="middle" fill="#555" font-family="sans-serif">Không có ảnh</text></svg>'
     ).encode("utf-8")).decode())


def thumb_data_uri(path, size=THUMB_PX):
    """Ảnh nhỏ JPEG ≈size px (xoay EXIF) dạng data URI, cache theo (đường dẫn, mtime, kích thước). Lỗi thì ảnh giữ chỗ."""
    if not path:
        return _PLACEHOLDER
    try:
        st = os.stat(path)
    except OSError:
        return _PLACEHOLDER
    key = (path, st.st_mtime_ns, st.st_size, size)
    if key in _THUMBS:
        _THUMBS.move_to_end(key)
        return _THUMBS[key]
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((size, size), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=80)
        uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        uri = _PLACEHOLDER
    _THUMBS[key] = uri
    while len(_THUMBS) > 700:
        _THUMBS.popitem(last=False)
    return uri


# ---------- thùng rác ----------
def trash_root(run_dir):
    return os.path.join(run_dir, TRASH)


def _rel(path, base):
    return os.path.relpath(path, base).replace(os.sep, "/")


def _unique_dir(parent, base):
    d, k = os.path.join(parent, base), 1
    while os.path.exists(d):
        k += 1
        d = os.path.join(parent, f"{base}_{k}")
    return d


def _face_files(run_dir, name):
    """Các file của ảnh `name` còn tồn tại: inbox/<file>, crop/images/<tên>.png, overlays/<tên>.png (đường dẫn tuyệt đối)."""
    out = []
    p = _find_inbox(run_dir, name)
    if p:
        out.append(p)
    for sub in (os.path.join("crop", "images"), "overlays"):
        q = os.path.join(run_dir, sub, name + ".png")
        if os.path.lexists(q):
            out.append(q)
    return out


def soft_delete_image(run_dir, name, *, reviewer="", decision="", pushed_task=None, now=None):
    """Xoá mềm một ảnh. Trả manifest. RunError nếu tên không hợp lệ/đường dẫn ra ngoài/đang chạy việc; lỗi giữa chừng thì hoàn lại."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or name in (".", ".."):
        raise RunError(f"Tên ảnh {name!r} không hợp lệ.")
    busy = run_busy(run_dir)
    if busy:
        raise RunError(f"Lượt {os.path.basename(run_dir)} đang có việc chạy ({busy[0]}): chờ xong rồi xoá.")
    if name in loai_tru.read_excluded(run_dir):
        raise RunError(f"Ảnh {name} đã nằm trong thùng rác.")
    files = _face_files(run_dir, name)
    for p in files:
        if not _inside(p, run_dir):
            raise RunError(f"File {os.path.basename(p)} trỏ ra ngoài thư mục lượt (liên kết tượng trưng): từ chối.")
    when = now or datetime.datetime.now()
    folder = _unique_dir(trash_root(run_dir), f"{when.strftime('%Y%m%d-%H%M%S')}_{name}")
    if not _inside(folder, run_dir):
        raise RunError("Đường dẫn thùng rác nằm ngoài lượt: từ chối.")
    loai_tru.add(run_dir, [name])                                       # vào danh sách loại TRƯỚC
    moved = []
    try:
        for p in files:
            rel = _rel(p, run_dir)
            dst = os.path.join(folder, "files", *rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(p, dst)
            moved.append((p, dst, rel))
        manifest = dict(ten=name, thoi_diem=when.isoformat(timespec="seconds"), nguoi_ra=reviewer, quyet_dinh=decision,
                        da_day_cvat=bool(pushed_task), task=pushed_task or None,
                        files=[dict(goc=rel, thung_rac=_rel(dst, folder)) for _p, dst, rel in moved])
        os.makedirs(folder, exist_ok=True)
        cvat_io.atomic_write_json(os.path.join(folder, "manifest.json"), manifest)
    except Exception as e:
        for p, dst, _rel_ in reversed(moved):                             # lỗi giữa chừng: chuyển ngược và gỡ khỏi danh sách
            try:
                os.replace(dst, p)
            except OSError:
                pass
        shutil.rmtree(folder, ignore_errors=True)
        loai_tru.remove(run_dir, [name])
        raise RunError(f"Không xoá được ảnh {name} ({type(e).__name__}: {e}); đã hoàn lại, không mất gì.")
    return manifest


def list_trash(run_dir):
    """Danh sách mục thùng rác của lượt, mới nhất trước: dict(folder, ten, thoi_diem, quyet_dinh, da_day_cvat, task, n_files)."""
    root = trash_root(run_dir)
    out = []
    try:
        entries = os.listdir(root)
    except OSError:
        return []
    for f in entries:
        if not FOLDER_RE.fullmatch(f):
            continue
        m = _jload(os.path.join(root, f, "manifest.json"))
        if not isinstance(m, dict) or not isinstance(m.get("ten"), str):
            continue
        out.append(dict(folder=f, ten=m["ten"], thoi_diem=str(m.get("thoi_diem", "")), quyet_dinh=str(m.get("quyet_dinh", "")),
                        da_day_cvat=bool(m.get("da_day_cvat")), task=m.get("task"), n_files=len(m.get("files", []))))
    out.sort(key=lambda d: d["folder"], reverse=True)
    return out


def restore_image(run_dir, folder, *, reviewer=""):
    """Khôi phục một mục thùng rác (folder phải nằm trong list_trash). Trả dict(ten, mo_lai): mo_lai = True khi mặt chưa có quyết định
    nên lượt có lại mặt chưa rà (review/done.txt bị xoá). Đích đã có file thì RunError và không chuyển gì."""
    items = {d["folder"]: d for d in list_trash(run_dir)}
    if folder not in items:
        raise RunError("Mục thùng rác này không còn (đã khôi phục hoặc đã dọn) (danh sách đã làm mới).")
    busy = run_busy(run_dir)
    if busy:
        raise RunError(f"Lượt {os.path.basename(run_dir)} đang có việc chạy ({busy[0]}): chờ xong rồi khôi phục.")
    root = os.path.join(trash_root(run_dir), folder)
    man = _jload(os.path.join(root, "manifest.json"))
    plan = []
    for f in man["files"]:
        src = os.path.join(root, *str(f["thung_rac"]).split("/"))
        dst = os.path.join(run_dir, *str(f["goc"]).split("/"))
        if not _inside(src, root) or not _inside(dst, run_dir) or ".." in str(f["goc"]).split("/"):
            raise RunError("Manifest trỏ ra ngoài thư mục lượt: từ chối khôi phục.")
        if os.path.lexists(dst):
            raise RunError(f"Không khôi phục được: {f['goc']} đã có file ở chỗ cũ (có thể đã nạp lại ảnh cùng tên). Đổi tên hoặc xoá file đó trước.")
        plan.append((src, dst))
    done = []
    try:
        for src, dst in plan:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
            done.append((src, dst))
    except OSError as e:
        for src, dst in reversed(done):
            try:
                os.replace(dst, src)
            except OSError:
                pass
        raise RunError(f"Không khôi phục được ({e}); đã hoàn lại.")
    name = man["ten"]
    loai_tru.remove(run_dir, [name])
    shutil.rmtree(root, ignore_errors=True)
    tri, _e = triage_of(run_dir, reviewer)
    reopened = tri.get(name, ("", ""))[0] not in phan_loai.DECISIONS
    if reopened:
        try:
            os.remove(os.path.join(run_dir, "review", "done.txt"))
        except OSError:
            pass
    return dict(ten=name, mo_lai=reopened)


def empty_trash(run_dir):
    """Dọn thùng rác (xoá VĨNH VIỄN) của lượt: chỉ rmtree runs/<lượt>/_trash (kiểm realpath). Trả số mục đã xoá. Tên vẫn nằm trong excluded.txt."""
    busy = run_busy(run_dir)
    if busy:
        raise RunError(f"Lượt {os.path.basename(run_dir)} đang có việc chạy ({busy[0]}): chờ xong rồi dọn.")
    root = trash_root(run_dir)
    if not os.path.isdir(root):
        return 0
    if os.path.islink(root) or os.path.basename(os.path.realpath(root)) != TRASH or not _inside(root, run_dir) \
            or os.path.realpath(root) == os.path.realpath(run_dir):
        raise RunError("Thư mục thùng rác không hợp lệ: từ chối dọn.")
    n = len(list_trash(run_dir))
    shutil.rmtree(root)
    return n


# ---------- xoá cả đợt ----------
def runs_trash(runs_root):
    return os.path.join(runs_root, RUN_TRASH)


def delete_run(runs_root, run, typed, *, active_run=None):
    """Xoá mềm cả đợt: gõ lại đúng tên (phân biệt hoa thường), không đang chạy việc, không phải đợt đang mở ở tab Rà soát.
    Chuyển runs/<run> -> runs/_trash/<run>__<YYYYmmdd-HHMMSS>. Trả tên mục trong _trash."""
    run_dir = valid_run(runs_root, run)
    if typed != run:
        raise RunError(f"Phải gõ lại đúng tên đợt ({run}), phân biệt hoa thường.")
    if active_run and os.path.realpath(run_dir) == os.path.realpath(active_run):
        raise RunError(f"Đợt {run} đang mở ở tab Rà soát: chuyển sang đợt khác (hoặc đóng trang) rồi mới xoá.")
    busy = run_busy(run_dir)
    if busy:
        raise RunError(f"Đợt {run} đang có việc chạy ({busy[0]}): chờ xong rồi xoá.")
    ps = read_push(run_dir)
    root = runs_trash(runs_root)
    os.makedirs(root, exist_ok=True)
    entry = f"{run}__{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    dst = os.path.join(root, entry)
    if os.path.exists(dst) or not _inside(dst, runs_root):
        raise RunError("Mục thùng rác trùng tên, thử lại sau 1 giây.")
    cvat_io.atomic_write_json(os.path.join(run_dir, "xoa_dot.json"), dict(
        ten=run, luc=datetime.datetime.now().isoformat(timespec="seconds"), task=(ps or {}).get("task"), trang_thai_push=(ps or {}).get("trang_thai")))
    try:
        os.replace(run_dir, dst)
    except OSError as e:
        try:
            os.remove(os.path.join(run_dir, "xoa_dot.json"))
        except OSError:
            pass
        raise RunError(f"Không chuyển được đợt {run} vào thùng rác ({e}). Đóng chương trình đang mở file trong đợt (Excel, trình xem ảnh) rồi thử lại.")
    return entry


def list_deleted_runs(runs_root):
    """[dict(entry, ten, luc, task)] các đợt đã xoá, mới nhất trước."""
    root = runs_trash(runs_root)
    out = []
    try:
        entries = os.listdir(root)
    except OSError:
        return []
    for e in entries:
        m = ENTRY_RE.fullmatch(e)
        if not m or not os.path.isdir(os.path.join(root, e)):
            continue
        meta = _jload(os.path.join(root, e, "xoa_dot.json")) or {}
        out.append(dict(entry=e, ten=m.group(1), luc=str(meta.get("luc", m.group(2))), task=meta.get("task")))
    out.sort(key=lambda d: d["entry"].split("__")[1], reverse=True)
    return out


def _deleted_entry(runs_root, entry):
    found = {d["entry"]: d for d in list_deleted_runs(runs_root)}
    if entry not in found:
        raise RunError("Mục này không còn trong thùng rác đợt (danh sách đã làm mới).")
    path = os.path.join(runs_trash(runs_root), entry)
    if not _inside(path, runs_trash(runs_root)):
        raise RunError("Đường dẫn nằm ngoài thùng rác đợt: từ chối.")
    return found[entry], path


def restore_run(runs_root, entry):
    """Khôi phục đợt đã xoá về runs/<tên> nếu tên chưa bị dùng lại (không phân biệt hoa thường)."""
    info, path = _deleted_entry(runs_root, entry)
    taken = {d.lower() for d in nap_anh._listing(runs_root)}
    if info["ten"].lower() in taken:
        raise RunError(f"Không khôi phục được: tên {info['ten']} đã có đợt khác dùng lại. Đổi tên hoặc xoá đợt đó trước.")
    dst = os.path.join(runs_root, info["ten"])
    os.replace(path, dst)
    try:
        os.remove(os.path.join(dst, "xoa_dot.json"))
    except OSError:
        pass
    return info["ten"]


def purge_run(runs_root, entry):
    """Xoá VĨNH VIỄN một đợt đã xoá (chỉ rmtree trong runs/_trash, kiểm realpath)."""
    info, path = _deleted_entry(runs_root, entry)
    if os.path.islink(path) or os.path.realpath(os.path.dirname(path)) != os.path.realpath(runs_trash(runs_root)):
        raise RunError("Đường dẫn không hợp lệ: từ chối.")
    shutil.rmtree(path)
    return info["ten"]


# ---------- yêu cầu chờ xác nhận ----------
def new_token():
    import secrets
    return secrets.token_hex(8)


class Pending:
    """MỘT yêu cầu xoá đang chờ xác nhận, kèm mã ngẫu nhiên. Mở yêu cầu mới thay thế yêu cầu cũ nên nút xác nhận của hộp cũ
    (mã không khớp, hoặc quá TOKEN_TTL giây) không bao giờ xoá nhầm ảnh khác."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.item = None

    def open(self, **kw):
        self.item = dict(kw, token=new_token(), t=self.clock())
        return self.item

    def take(self, token):
        """Trả yêu cầu nếu mã khớp và còn hạn (rồi xoá khỏi bộ nhớ: dùng một lần), không thì None."""
        it, self.item = self.item, None
        if it and token and token == it["token"] and self.clock() - it["t"] <= TOKEN_TTL:
            return it
        return None

    def cancel(self):
        self.item = None


# ---------- HTML ----------
def _e(x):
    return html.escape(str(x), quote=True)


def _counts_html(i):
    chips = [("c-nhan", "Nhận", i["nhan"]), ("c-gan_tay", "Sửa nhãn", i["gan_tay"]), ("c-bo", "Bỏ", i["bo"]), ("c-chua", "Chưa rà", i["chua_ra"])]
    out = "".join(f'<span class="m28-chip {c}">{t} <b>{v}</b></span>' for c, t, v in chips)
    if i["khong_dung_duoc"]:
        out += f'<span class="m28-chip c-chua">Không dùng được <b>{i["khong_dung_duoc"]}</b></span>'
    return out


def _mmss(s):
    s = max(0, int(round(float(s or 0))))
    h, r = divmod(s, 3600)
    return f"{h}:{r // 60:02d}:{r % 60:02d}" if h else f"{r // 60:02d}:{r % 60:02d}"


def _gio_html(i):
    """Chip giờ RIÊNG của đợt (đồng hồ ở đầu trang tính mỗi đợt một phiên): i['gio'] = [dict(nguoi, giay, tt)], tt: chay | tam_dung | cho | da_luu."""
    out = ""
    for g in i.get("gio") or []:
        tt = g.get("tt")
        txt = {"chay": f"▶ {_mmss(g.get('giay'))}", "tam_dung": f"⏸ {_mmss(g.get('giay'))}", "cho": "⏸ chờ bắt đầu", "da_luu": f"✓ đã lưu {_mmss(g.get('giay'))}"}.get(tt, "")
        if txt:
            out += f'<span class="m28-chip c-gio" title="Giờ riêng của đợt này; giờ các đợt khác không lẫn vào">⏱ {_e(g.get("nguoi", ""))} {txt}</span>'
    return out


def _state_cls(code):
    return {S_DONE: "ok", S_PUSHED: "ok", S_COMPLETED: "ok", S_PARTIAL: "warn", S_PREPARING: "info", S_PUSHING: "info", S_DELETING: "info",
            S_COLLECTING: "info", S_NOT_READY: "warn"}.get(code, "")


FOLDER_ICON = ('<svg class="dot-ic" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
               'stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>')


def folder_button(i):
    """Nút folder của đợt đã gộp job: mở thư mục chứa file nhãn gộp đã xuất (raw/<task>/, bản cũ: raw/). Chỉ gửi khoá thư mục cố định (data-folder)
    và tên đợt (data-run); server tự tìm thư mục từ gop_job.json của đợt, không nhận đường dẫn từ trình duyệt.
    Nhãn nút viết thẳng trong HTML (test quy ước nút tiếng Anh quét '>…</button>')."""
    g = i.get("gop")
    if not is_merged(g):
        return ""
    return (f'<button type="button" class="dot-btn dot-btn-folder" data-act="openfolder" data-folder="raw" data-run="{_e(i.get("name", ""))}" '
            f'title="Mở thư mục chứa file đã xuất: {_e(g["xml"].replace(chr(92), "/"))}" aria-label="Open folder of the exported file">{FOLDER_ICON}Open folder</button>')


def gop_text(g):
    """'Đã gộp job: raw/<file> · <giờ>[ · gộp khi còn N job chưa Finish][ · gói …]' từ gop_job.json (đã escape; rỗng nếu đợt chưa gộp lần nào)."""
    if not is_merged(g):
        return ""
    out = f'Đã gộp job: {_e(g["xml"].replace(chr(92), "/"))} · {_e(fmt_date(str(g.get("luc", ""))))}'
    chua = g.get("jobs_chua_xong") if isinstance(g.get("jobs_chua_xong"), list) else []
    if chua:
        out += f' · gộp khi còn {len(chua)} job chưa Finish'
    if g.get("goi"):
        out += f' · gói {_e(g["goi"])}'
    return out


def gop_html(g):
    """Dòng 'Đã gộp job' (gop_text) của khung CVAT trong popup quản lý đợt (rỗng nếu đợt chưa gộp lần nào)."""
    t = gop_text(g)
    return f'<div class="dot-gop" role="status">{t}</div>' if t else ""


def finish_button(i):
    """Nút Merge jobs & Finish (gộp mọi job của task CVAT thành một file, dừng và lưu đồng hồ của đợt): chỉ khi push.json ghi đẩy xong; tắt khi lượt đang có việc chạy.
    Nhãn nút viết thẳng trong HTML (test quy ước nút tiếng Anh quét '>…</button>')."""
    if (i.get("push") or {}).get("trang_thai") != "xong":
        return ""
    busy = i.get("state") in BUSY_STATES
    return (f'<button type="button" class="dot-btn dot-btn-finish" data-act="finish" data-run="{_e(i["name"])}"'
            + (' disabled title="Đang có việc chạy cho đợt này"' if busy else "") + '>Merge jobs & Finish</button>')


SETTINGS_ICON = ('<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
                 'stroke-linejoin="round" aria-hidden="true"><path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 '
                 '3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 '
                 '2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 '
                 '1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37c1 .608 2.296.07 '
                 '2.572-1.065z"/><circle cx="12" cy="12" r="3"/></svg>')


def card_html(i, *, active=False):
    """Thẻ một đợt ở trang Các đợt: chỉ để CHỌN đợt. Một nút Open batch (mở đợt, trang tải lại ở đợt đó) và nút bánh răng mở popup quản lý
    (ảnh, thùng rác, task CVAT, xoá đợt: grid_html). Merge jobs & Finish, Open folder, kết quả gộp nằm ở trang Gộp & kết thúc (gop_view_html)
    của đợt đang mở; đẩy lên CVAT ở khung Duyệt & Xuất CVAT của tab Rà soát."""
    name = i["name"]
    n = _e(name)
    meta = f'{_e(fmt_date(i["ngay"]))} · <b>{i["so_anh"]}</b> ảnh' + (f' · người nạp {_e(i["nguoi_nap"])}' if i["nguoi_nap"] else "")
    note = f'<div class="dot-note">{_e(i["ghi_chu"])}</div>' if i["ghi_chu"] else ""
    extra = []
    if i["nguoi_khac"]:
        extra.append("có kết quả của " + ", ".join(_e(x) for x in i["nguoi_khac"]))
    if i["trash"]:
        extra.append(f'{i["trash"]} ảnh trong thùng rác')
    if i["task_deleted"]:
        extra.append("task trên CVAT đã xoá, đẩy lại được")
    if i["loi_triage"]:
        extra.append(_e(i["loi_triage"]))
    ex = f'<div class="dot-extra">{" · ".join(extra)}</div>' if extra else ""
    can_ra = i["ready"] and not active and i["state"] not in BUSY_STATES
    why = "Đợt đang mở" if active else ("Chưa có flags.json (prepare chưa xong)" if not i["ready"] else
                                        "Đang có việc chạy" if not can_ra else "")
    if active:                                          # đợt đang mở: tới đúng bước đợt đang ở (review_app.current_step qua nút ẩn m28-go 'home')
        ra = '<button type="button" class="dot-btn dot-btn-ra" data-go="home" title="Tới bước đợt đang ở">Continue</button>'
        name_btn = f'<button type="button" class="dot-name" data-go="home" aria-label="Continue batch {n}">{n}</button>'
    else:                                               # đợt khác: bấm tên hay Open batch đều mở đợt (trang tải lại ở đúng bước của đợt đó)
        ra = (f'<button type="button" class="dot-btn dot-btn-ra" data-act="ra" data-run="{n}"' + ("" if can_ra else ' disabled')
              + (f' title="{_e(why)}"' if why else "") + '>Open batch</button>')
        name_btn = (f'<button type="button" class="dot-name" data-act="ra" data-run="{n}" aria-label="Open batch {n}"' + ("" if can_ra else ' disabled')
                    + '>' + n + '</button>')
    gear = (f'<button type="button" class="dot-btn dot-btn-icon" data-act="open" data-run="{n}" aria-label="Batch settings of {n}" '
            f'title="Batch settings: images, trash, CVAT task, delete">{SETTINGS_ICON}</button>')
    opened = ' <span class="dot-active">đang mở</span>' if active else ""
    return (f'<div class="dot-card" data-state="{i["state"]}"><div class="dot-card-head">'
            f'{name_btn}{opened}'
            f'<span class="dot-state st-{_state_cls(i["state"])}">{_e(i["state_text"])}</span></div>'
            f'<div class="dot-meta">{meta}</div>{note}<div class="dot-counts">{_counts_html(i)}{_gio_html(i)}</div>{ex}'
            f'<div class="dot-actions">{ra}{gear}</div></div>')


def _gop_row(ok, text):
    return (f'<li class="gop-row {"gop-ok" if ok else "gop-todo"}"><span class="gop-mark" aria-hidden="true">{"✓" if ok else "○"}</span>'
            f'<span>{text}</span></li>')


def gop_view_html(info, jobs=None):
    """Trang Gộp & kết thúc (bước 4): CHỈ đợt đang mở. Danh sách việc đã xong (rà, đẩy CVAT, job, gộp) và đúng nút của việc tiếp theo:
    còn mặt chưa rà / chưa đẩy -> về bước đó (data-go, review_app xử lý); đã đẩy -> Merge jobs & Finish, Open CVAT task; đã gộp -> file đã xuất, Open folder (nạp đợt mới bằng New upload ở thanh đầu trang).
    info: run_info của đợt đang mở (None: trang chưa mở đợt nào). jobs: dict(done, total, all_done) từ lần kiểm job gần nhất (None: chưa kiểm)."""
    if info is None:
        return ('<div class="dot-gop-view"><div class="dot-gridtitle">Gộp &amp; kết thúc</div>'
                '<div class="m28-empty">Chưa mở đợt nào: nạp ảnh ở bước 1 hoặc mở một đợt ở trang Các đợt.</div>'
                '<div class="dot-actions"><button type="button" class="dot-btn dot-btn-ra" data-go="nap">New upload</button>'
                '<button type="button" class="dot-btn" data-go="dot">Open batches</button></div></div>')
    n = _e(info["name"])
    ps = info.get("push") or {}
    st = ps.get("trang_thai")
    g = info.get("gop")
    pushed, merged = st == "xong", st == "xong" and is_merged(g)
    rows = [_gop_row(info["chua_ra"] == 0 and info["total"] > 0,
                     f'Đã rà {info["total"] - info["chua_ra"]}/{info["total"]} mặt' if info["total"] else "Đợt chưa có mặt nào để rà")]
    rows.append(_gop_row(pushed, f'Đã đẩy CVAT: task <b>{_e(ps.get("task", "?"))}</b> (id {_e(ps.get("task_id", "?"))})' if pushed else
                         (f'Đẩy dở: {_e(info["state_text"])}' if info["state"] == S_PARTIAL else "Chưa đẩy lên CVAT")))
    if pushed and not merged:
        if jobs and jobs.get("total"):
            rows.append(_gop_row(jobs.get("all_done"), f'Job trên CVAT: <b>{jobs["done"]}</b>/{jobs["total"]} xong'))
        else:
            rows.append(_gop_row(False, "Job trên CVAT: chưa có số (xem ở bước 3 Sửa trên CVAT)"))
    rows.append(_gop_row(merged, gop_text(g) if merged else "Chưa gộp job"))
    url = safe_task_url(ps.get("task_url")) if pushed else ""
    cvat = (f'<a class="dot-btn" href="{_e(url)}" target="_blank" rel="noopener noreferrer">Open CVAT task ↗</a>' if url else "")
    if merged:
        note = "Đợt đã xong. Sửa thêm nhãn trên CVAT thì bấm Merge jobs &amp; Finish lần nữa để xuất lại file."
        acts = f'{folder_button(info)}{finish_button(info)}{cvat}'          # nạp đợt mới: nút New upload ở thanh đầu trang
    elif pushed:
        done = bool(jobs and jobs.get("all_done"))
        note = ("Mọi job đã xong: bấm Merge jobs &amp; Finish để gộp cả task thành một file trong raw/." if done else
                "Sửa xong mọi job trên CVAT (Finish the job) rồi bấm Merge jobs &amp; Finish; còn job chưa xong thì tool hỏi lại trước khi gộp.")
        acts = f'{finish_button(info)}{cvat}'
    elif st in ("dang_tao", "da_tao", "da_nhap", "hong"):
        note = "Lần đẩy trước dừng giữa chừng: xem khung Duyệt &amp; Xuất CVAT ở tab Rà soát."
        acts = '<button type="button" class="dot-btn dot-btn-ra" data-go="push">Back to review</button>'
    elif info["chua_ra"] == 0 and info["total"] > 0:
        note = "Đã rà hết: đẩy lên CVAT ở khung Duyệt &amp; Xuất CVAT (tab Rà soát), sửa trên CVAT xong thì quay lại đây để gộp."
        acts = '<button type="button" class="dot-btn dot-btn-ra" data-go="push">Back to review</button>'
    else:
        note = f'Còn <b>{info["chua_ra"]}</b> mặt chưa rà: rà xong, đẩy lên CVAT, sửa trên CVAT rồi mới gộp ở đây.'
        acts = '<button type="button" class="dot-btn dot-btn-ra" data-go="ra">Back to review</button>'
    return (f'<div class="dot-gop-view"><div class="dot-gridhead"><span class="dot-gridtitle">Gộp &amp; kết thúc · đợt <b>{n}</b></span>'
            f'<span class="dot-state st-{_state_cls(info["state"])}">{_e(info["state_text"])}</span></div>'
            f'<ul class="gop-list">{"".join(rows)}</ul><div class="gop-note">{note}</div><div class="dot-actions">{acts}</div></div>')


def deleted_runs_html(rows):
    if not rows:
        return ""
    items = "".join(
        f'<div class="dot-del-row"><span><b>{_e(d["ten"])}</b> · xoá lúc {_e(fmt_date(d["luc"]))}'
        + (f' · task {_e(d["task"])} vẫn còn trên CVAT' if d["task"] else "") + '</span>'
        f'<span><button type="button" class="dot-btn" data-act="restore_run" data-entry="{_e(d["entry"])}">Restore</button>'
        f'<button type="button" class="dot-btn dot-btn-danger" data-act="purge_run" data-entry="{_e(d["entry"])}">Delete permanently…</button></span></div>'
        for d in rows)
    return f'<div class="dot-section"><div class="dot-section-title">Đợt đã xoá ({len(rows)})</div>{items}</div>'


def list_html(infos, active_name, deleted):
    """HTML danh sách thẻ của trang Các đợt."""
    if not infos:
        body = '<div class="m28-empty">Chưa có đợt nào: nạp ảnh ở tab <b>Nạp ảnh</b>.</div>'
    else:
        body = '<div class="dot-cards">' + "".join(card_html(i, active=i["name"] == active_name) for i in infos) + "</div>"
    return f'<div class="dot-list">{body}</div>{deleted_runs_html(deleted)}'


def grid_html(info, rows, page, trash, *, active=False):
    """Popup quản lý một đợt (nút bánh răng trên thẻ): lưới ảnh đã cắt đúng trang (rows: kết quả image_rows của toàn đợt), task CVAT, thùng rác, xoá đợt.
    Nằm đè lên danh sách thẻ; nút × (data-act=back), bấm nền tối hoặc Esc thì đóng (JS của tab)."""
    n = _e(info["name"])
    items, page, n_pages = page_slice(rows, page, GRID_COLS * GRID_ROWS)
    cells = []
    for r in items:
        nm = _e(r["name"])
        label = f'{nm}' + (f' <span class="dot-orig">({_e(r["orig"])})</span>' if r["orig"] != r["name"] else "")
        cells.append(
            f'<div class="dot-thumb st-{r["status"] or "chua"}"><img alt="{nm}" loading="lazy" src="{thumb_data_uri(r["src"])}">'
            f'<span class="dot-badge">{_e(r["status_text"])}</span>'
            f'<button type="button" class="dot-trash" data-act="delimg" data-run="{n}" data-name="{nm}" aria-label="Delete image {nm}" title="Delete image {nm}">'
            '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/>'
            '<path d="M10 11v6"/><path d="M14 11v6"/></svg></button>'
            f'<div class="dot-cap">{label}</div></div>')
    grid = "".join(cells) if cells else '<div class="m28-empty">Đợt này không còn ảnh nào.</div>'
    pager = ""
    if n_pages > 1:
        pager = (f'<div class="dot-pager"><button type="button" class="dot-btn" data-act="page" data-run="{n}" data-page="{page - 1}"'
                 + ("" if page > 0 else " disabled") + f'>‹ Prev page</button><span>Trang <b>{page + 1}</b>/{n_pages}</span>'
                 f'<button type="button" class="dot-btn" data-act="page" data-run="{n}" data-page="{page + 1}"'
                 + ("" if page < n_pages - 1 else " disabled") + '>Next page ›</button></div>')
    head = (f'<div class="dot-gridhead"><span class="dot-gridtitle" id="dot-pop-title">{SETTINGS_ICON} Đợt <b>{n}</b> · {_e(info["state_text"])}</span>'
            '<button type="button" class="dot-btn dot-pop-x" data-act="back" aria-label="Close batch settings" title="Close (Esc)">Close</button></div>'
            f'<div class="dot-counts">{_counts_html(info)}</div>')
    ps = info.get("push") or {}
    can_cvat = on_cvat(ps) and not active
    opt = (f'<label class="dot-del-opt{"" if can_cvat else " off"}"'
           + ("" if on_cvat(ps) else ' title="Đợt chưa đẩy lên CVAT: không có task nào để xoá"') + '>'
           f'<input type="checkbox" class="dot-del-cvat"{"" if can_cvat else " disabled"}> '
           + (f'Xoá luôn task <b>{_e(ps.get("task"))}</b> trên CVAT (mất nhãn đã sửa trên CVAT)' if on_cvat(ps) else "Xoá luôn task trên CVAT (đợt chưa đẩy lên CVAT)")
           + '</label>')
    delbar = (f'<div class="dot-del-bar">{opt}<button type="button" class="dot-btn dot-btn-danger" data-act="delrun" data-run="{n}"'
              + (' disabled title="Đợt đang mở ở tab Rà soát: chuyển sang đợt khác trước"' if active else "")
              + '>Delete batch…</button></div>')
    top = push_section_html(info, delbar) or f'<div class="dot-section dot-top">{delbar}</div>'      # xoá đợt ở đầu, chung khung với nút mở task
    return (f'<div class="dot-pop" role="dialog" aria-modal="true" aria-labelledby="dot-pop-title"><div class="dot-pop-box dot-detail">'
            f'{head}{top}<div class="dot-grid" role="list">{grid}</div>{pager}{trash_html(info["name"], trash)}</div></div>')


def safe_task_url(url):
    """Địa chỉ task CVAT để mở ở tab mới: chỉ http/https, có máy chủ, KHÔNG có user:pass@ (push đã từ chối, push.json có thể bị sửa tay). Không hợp lệ thì ''."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(str(url or "").strip())
        if u.scheme not in ("http", "https") or not u.netloc or u.username is not None or u.password is not None:
            return ""
    except ValueError:
        return ""
    return str(url).strip()


def open_task_button(url, cls="push-open-btn"):
    """Nút (thẻ <a>) 'Mở task trên CVAT' mở tab mới; thiếu hoặc sai địa chỉ thì không có nút (chuỗi rỗng)."""
    u = safe_task_url(url)
    return (f'<a class="{cls}" href="{_e(u)}" target="_blank" rel="noopener noreferrer">Mở task trên CVAT ↗</a>' if u else "")


def push_section_html(info, extra=""):
    """Khung đầu popup quản lý đợt: trạng thái task CVAT, nút mở task, dòng 'Đã gộp job', rồi `extra` (hàng Delete batch + ô tick xoá luôn task, grid_html).
    Đợt chưa có gì trên CVAT thì '' (grid_html dựng khung chỉ có hàng xoá)."""
    ps = info.get("push") or {}
    st = ps.get("trang_thai")
    if st not in ("xong", "da_tao", "da_nhap", "dang_tao", "task_deleted", "hong"):
        return ""
    name, tid = _e(ps.get("task", "?")), _e(ps.get("task_id", "?"))
    if st == "task_deleted":
        return (f'<div class="dot-section dot-cvat"><div><b>CVAT:</b> task {name} (id {tid}) đã được xoá '
                f'({_e(fmt_date(ps.get("task_deleted_at", "")))}). Đợt này đẩy lại được.</div>{extra}</div>')
    txt = {"xong": "Đã đẩy lên CVAT", "da_tao": "Đẩy dở: đã tạo task, chưa nhập nhãn", "da_nhap": "Đẩy dở: đã nhập nhãn, chưa kiểm xong",
           "dang_tao": "Đẩy dở: đang tạo task (chưa có id)", "hong": "push.json hỏng"}[st]
    url = safe_task_url(ps.get("task_url")) if st in ("xong", "da_tao", "da_nhap") else ""
    open_btn = f'<a class="dot-btn" href="{_e(url)}" target="_blank" rel="noopener noreferrer">Open CVAT task ↗</a>' if url else ""
    return (f'<div class="dot-section dot-cvat"><div class="dot-cvat-row"><span><b>CVAT:</b> {txt} · task <b>{name}</b> (id {tid})</span>{open_btn}</div>'
            f'{gop_html(info.get("gop"))}{extra}</div>')


def on_cvat(ps):
    """Đợt có task của tool trên CVAT (đã tạo task): Delete batch xoá kèm task được."""
    return (ps or {}).get("trang_thai") in ("xong", "da_tao", "da_nhap")


def trash_html(run, items):
    n = _e(run)
    if not items:
        return '<div class="dot-section"><div class="dot-section-title">Thùng rác của đợt</div><div class="dot-muted">Trống.</div></div>'
    rows = "".join(
        f'<div class="dot-del-row"><span><b>{_e(t["ten"])}</b> · xoá lúc {_e(fmt_date(t["thoi_diem"]))}'
        + (f' · quyết định {_e(DECISION_VI.get(t["quyet_dinh"], t["quyet_dinh"]))}' if t["quyet_dinh"] else "") + '</span>'
        f'<button type="button" class="dot-btn" data-act="restore" data-run="{n}" data-trash="{_e(t["folder"])}">Restore</button></div>'
        for t in items)
    return (f'<div class="dot-section"><div class="dot-section-title">Thùng rác của đợt ({len(items)})</div>{rows}'
            f'<button type="button" class="dot-btn dot-btn-danger" data-act="empty" data-run="{n}">Empty trash…</button></div>')
