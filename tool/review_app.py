"""Trang rà soát nhãn nháp M28 (Gradio, chỉ chạy ở 127.0.0.1) — phần của P2.

Người rà xem nháp 50 điểm trên ảnh chồng và bấm Nhận / Sửa nhãn / Bỏ ảnh TRƯỚC khi nhập vào CVAT.
Sửa điểm không làm ở đây (làm trong CVAT).

    python tool\\review_app.py runs\\F5 P2            # chạy thẳng, từ thư mục source-tool\\m28-prelabel
    python tool\\m28.py review --run F5 --reviewer P2  # qua m28 (bước review --review ui)
    python tool\\review_app.py --nap P2              # chưa có lượt nào: chỉ mở tab "Nạp ảnh" (kéo thả ảnh -> prepare -> rà)

Trang có các tab: "Rà soát" (như cũ, thêm khung "Đẩy lên CVAT" dưới nút Xong: logic day_cvat.py, giao diện dot_ui.py), "Nạp ảnh" (logic
ở nap_anh.py: tạo lượt mới NAP_xxx từ ảnh kéo thả, chạy prepare bằng tiến trình con, rồi "Upload & Open" tự chuyển trang sang lượt mới (hoặc "Open batch" ở tab Các đợt) mà
không gõ lệnh), "Các đợt" (dot_anh.py + dot_ui.py: thẻ đợt, lưới ảnh, xoá mềm ảnh/đợt, thùng rác, xoá task trên CVAT; nút "Merge jobs & Finish" của gop_job.py gộp mọi job
của task thành MỘT file raw\\<task>\\<task>_<Pk>_<DDMM>.xml rồi dừng và lưu đồng hồ của đợt), "Ca khó", "Họp team",
Đồng hồ bấm giờ (dong_ho.py + dong_ho_ui.py, KHÔNG có tab riêng): chip ⏱ ở đầu trang thấy ở mọi tab, MỖI ĐỢT MỘT ĐỒNG HỒ (QĐ-007: giờ đợt này không lẫn đợt khác), tự chạy khi bấm Nạp ảnh, MỘT nút Pause/Resume; Save timing (dòng `outputs\\timing\\timing_<Pk>.csv`
đúng định dạng facetimer và gói kết quả `outputs\\ket_qua\\ketqua_<Pk>_<DDMM>_<đợt>.zip` gửi nhóm trưởng) hoặc Discard session nằm trong hộp "Đóng trang rà soát?"; nguồn sự thật là đồng hồ phía server, trạng thái ghi ra file nên đóng tab không mất; đóng trang thì tự tạm dừng),
"Thống kê" (thong_ke.py + thong_ke_html.py + thong_ke_ui.py: CHỈ BA chỉ số của thí nghiệm hai nhóm độc lập (QĐ-006): NME của nháp so với nhãn manual, tỉ lệ điểm phải sửa, so sánh thời gian manual với
assisted; đọc gói kết quả, nhãn raw\\ và timing; chỉ đọc, tính khi chọn tab, xuất CSV + HTML tĩnh không ảnh mặt; nhóm trưởng dùng tool\\tong_ket.py với các gói của thành viên), "Lọc dữ liệu" (loc_du_lieu.py + loc_ui.py: bộ lọc ảnh đã có nhãn sửa tay thành bộ train/val/test cho model landmark khác sau này, chỉ chuẩn bị
dữ liệu, không train, xem trước = dry-run, ghi dưới outputs\\train_sets), "Cài đặt" (cai_dat.py + cai_dat_ui.py: link/token/tổ chức CVAT, người rà mặc định, đường dẫn ảnh và model, t_flip của cờ low_conf).
Nút Xong chỉ ghi done.txt và khoá việc bấm quyết định (hiện dải xanh ở đầu trang); trang KHÔNG tự tắt, vẫn Đẩy lên CVAT, xem Các đợt,
xuất Ca khó được. Chỗ duy nhất tắt trang là nút "Close page" (có hộp xác nhận, đứng trên các tab), Ctrl+C, hoặc chuyển lượt.
Trang KHÔNG gọi mạng: đẩy lên CVAT, xoá task, gộp job và "Thử kết nối CVAT" chạy bằng tiến trình con (`m28.py push ...`, `m28.py collect ...`, cai_dat_thu.py). Link/token CVAT
lấy từ cai_dat.py: giá trị vừa Save ở tab Cài đặt > biến môi trường CVAT_URL/CVAT_ACCESS_TOKEN > file đã lưu ngoài repo (chỉ khi bật "Nhớ trên máy
này"); token chỉ vào tiến trình con qua môi trường của nó, không bao giờ qua đối số dòng lệnh, log, runs/ hay HTML.

Đọc  runs/<run>/flags/flags.json, overlays/, autoqc/autoqc.csv, no_face.csv, map50/mp50.json, crop/images/.
Ghi  runs/<run>/review/triage_<người rà>.csv (name,decision,reason,seconds; chỉ nối thêm dòng, mỗi dòng fsync)
     và runs/<run>/review/done.txt khi bấm Xong (m28 chỉ cần file này có mặt).

Quy ước:
  * Đầu module không nạp gradio, cũng không bao giờ nạp torch: phần logic thuần (hàng đợi, đọc/ghi CSV, hoàn tác,
    ảnh chồng, ảnh nhỏ) chỉ dùng thư viện chuẩn và PIL (nạp lười), test không cần trình duyệt.
  * Chỉ launch(server_name="127.0.0.1", share=False). Không tunnel, không Colab/Kaggle, không gọi mạng.
  * Chuyển sang lượt mới = dựng lại Blocks và launch lại trên CÙNG cổng, CÙNG tiến trình (xem main). Lý do không đổi Store tại chỗ:
    `store` nằm trong mọi closure của build_ui; allowed_paths (overlays, crop/images, _tmp của lượt) chỉ đặt lúc launch; tiêu đề
    trang, notes_html, had_done tính một lần. Đổi tại chỗ phải sửa mọi handler và chọc vào thuộc tính nội bộ của Gradio. Tự sinh
    tiến trình mới thì rối cửa sổ cmd (Windows) và tiến trình cha `m28.py review`. Cái giá: trang mất kết nối 1-3 giây.
  * Đóng ngang chừng không mất gì: mỗi lần bấm là một dòng CSV đã fsync; mở lại thì làm tiếp.
"""
import csv
import dataclasses
import datetime
import html
import io
import json
import math
import os
import re
import sys
import threading
import time
import types

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import ca_kho  # noqa: E402  (ca khó, tab Ca khó và Họp team; chỉ thư viện chuẩn ở đầu module)
import dot_anh  # noqa: E402
import cai_dat  # noqa: E402  (cài đặt dùng chung cả tiến trình: CVAT, người rà, đường dẫn; chỉ thư viện chuẩn)
import cai_dat_ui  # noqa: E402  (tab Cài đặt; không import gradio ở đầu module)
import cvat_ui  # noqa: E402
import day_cvat  # noqa: E402  (trạng thái link/token CVAT: tab Nạp ảnh đòi có trước khi nạp)
import dong_ho_ui  # noqa: E402  (chip đồng hồ ở đầu trang: bấm giờ theo phiên; không import gradio ở đầu module)
import dot_ui  # noqa: E402  (khung Đẩy lên CVAT và tab Các đợt; không import gradio ở đầu module)
import giao_dien  # noqa: E402
import gop_job  # noqa: E402  (Merge jobs & Finish: yêu cầu gộp còn dở chặn chuyển lượt; không gradio, không mạng)
import loc_ui  # noqa: E402  (tab Lọc dữ liệu; không import gradio ở đầu module)
import log_view  # noqa: E402  (khung log trong popup Log prepare / Log push; chỉ thư viện chuẩn)
import nap_anh  # noqa: E402  (logic tab Nạp ảnh; chỉ thư viện chuẩn)
import thong_ke_ui  # noqa: E402  (tab Thống kê; không import gradio ở đầu module)
from m28core import co_v2, dang_chay, loai_tru, mau_nhom  # noqa: E402  (khoá lượt; danh sách mặt xoá mềm excluded.txt)
from m28core.steps import DECISIONS, _stem  # noqa: E402  (dùng chung quy ước tên/quyết định với push)
from nap_anh import NO_FACE_VI, RunError  # noqa: E402,F401  (RunError dùng chung với nap_anh)

# ---------- hằng số (P5 chốt guideline_triage.md thì sửa ở đây) ----------
REASONS = [
    ("", "Khác"),                                   # không ghi mã lý do (trước đây hiện "(không)")
    ("LAT_GUONG", "đảo trái–phải"),                 # nháp bị lật gương: chấm mắt / lông mày trái nằm ở bên phải (mã cũ giữ nguyên)
    ("DON_CUC", "điểm dồn cục"),
    ("LECH_VUNG", "lệch cả một vùng"),
    ("QUAY_CHE", "quay > 80° hoặc che quá nửa"),
    ("NHIEU_MAT", "ảnh nhiều mặt cần gán"),
    ("KHONG_MAT", "không có mặt"),
    ("SAI_MAT", "sai mặt"),
    ("MO_NHO", "quá mờ hoặc quá nhỏ"),
]
REASON_CODES = [c for c, _ in REASONS]
REASON_VI = dict(REASONS)
LABELS = {"nhan": "Nhận", "gan_tay": "Sửa nhãn", "bo": "Bỏ ảnh"}
SUG_VI = {"on": "ổn", "can_xem": "cần xem", "nen_gan_tay": "nên sửa nhãn", "": "chưa có autoqc"}
PROBLEMS_VI = {"diem_ngoai_anh": "điểm ra ngoài ảnh", "diem_khong_hop_le": "điểm không hợp lệ"}
EMPTY_VI = {"tat_ca": "Không có mặt nào trong lượt này.", "chua_ra": "Đã rà hết: không còn mặt chưa rà. Bấm Push to CVAT ở khung Duyệt & Xuất CVAT.",
            "dang_ngo": "Không có mặt đáng ngờ nào.", "da_ra": "Chưa rà mặt nào."}
DEFAULT_PORT = 7860
PAGE_SIZE = 16                       # lưới ảnh nhỏ tab Rà soát: 4 cột × 4 hàng mỗi trang
FILTERS = [("tat_ca", "Tất cả"), ("chua_ra", "Chưa rà"), ("dang_ngo", "Đáng ngờ"), ("da_ra", "Đã rà")]
HEADER = ["name", "decision", "reason", "seconds"]

THUMB = 176          # cạnh ảnh nhỏ gồm cả viền (px)
BORDER = 6           # bề dày viền trạng thái vẽ thẳng vào ảnh nhỏ
STATUS_COLOR = {"": "#9ca3af", "nhan": "#16a34a", "gan_tay": "#d97706", "bo": "#dc2626"}
STATUS_LETTER = {"": "", "nhan": "N", "gan_tay": "S", "bo": "B"}
# màu và kiểu chấm của ảnh chồng nằm ở m28core/mau_nhom.py (cùng nguồn với steps.overlays và label CVAT)
DEFAULT_REVIEWER = "P1"          # tên người rà khi dòng lệnh không ghi và tab Cài đặt chưa lưu tên


def chua_dat_ten(ctx):
    """Trang mở không ghi tên (nhấp đúp chay.bat, chạy ./chay.sh) và tab Cài đặt CHƯA lưu tên nào: người rà đang là tên mặc định P1. Nạp ảnh và Open batch bị chặn đến khi
    Save name, vì tên đi vào file kết quả, đồng hồ và gói gửi nhóm trưởng: mọi người cùng để P1 thì thống kê gộp họ thành một người."""
    return bool(getattr(ctx, "reviewer_auto", False)) and not cai_dat.get().default_reviewer()
NOTEBOOK_VARS = ("COLAB_RELEASE_TAG", "COLAB_GPU", "KAGGLE_KERNEL_RUN_TYPE", "SPACE_ID")
VI_USAGE = ("Cách dùng: python tool\\review_app.py <thư mục lượt chạy> [người rà], ví dụ python tool\\review_app.py runs\\R1610 P5; "
            "chưa có lượt nào thì python tool\\review_app.py --nap [người rà] (chỉ tab Nạp ảnh), ví dụ python tool\\review_app.py --nap P5. "
            "Không ghi người rà thì dùng tên đã lưu bằng nút Reviewer (Save name), chưa lưu thì P1")


# ---------- kiểm tra đầu vào ----------
def run_name(run_dir):
    return os.path.basename(os.path.normpath(run_dir)) or str(run_dir)


def _shown(path):
    return os.path.normpath(path)


def check_reviewer(name):
    return nap_anh.check_reviewer(name)            # một quy tắc duy nhất (nap_anh.REVIEWER_RE), tab Cài đặt cũng dùng


def notebook_env(environ=None, modules=None):
    """Thông điệp lỗi nếu đang chạy trong Colab/Kaggle/Spaces, không thì None."""
    environ = os.environ if environ is None else environ
    modules = sys.modules if modules is None else modules
    if "google.colab" in modules or any(v in environ for v in NOTEBOOK_VARS):
        return ("Trang rà soát chỉ chạy trên máy của bạn (127.0.0.1), không chạy trong Colab/Kaggle/Spaces vì trên "
                "trang có ảnh mặt. Dùng --review excel nếu không mở được trang.")
    return None


# ---------- đọc dữ liệu của lượt chạy ----------
@dataclasses.dataclass
class Face:
    name: str                        # không đuôi, ví dụ F_004
    file: str                        # name + ".png": tên ghi vào CSV
    overlay: object = None           # đường dẫn overlays/<tên>.png nếu có
    crop: object = None              # đường dẫn crop/images/<tên>.png nếu có
    flags: object = None             # list[bool] 50 phần tử, None = không có nháp
    occ: object = None               # list[bool] 50 phần tử: điểm bị che (occluded, map50/mp50.json khoá occ); None = lượt chưa có thông tin này
    n_flags: int = 0
    suggestion: str = ""             # on | can_xem | nen_gan_tay | "" (chưa có autoqc)
    problems: list = dataclasses.field(default_factory=list)
    no_face_reason: object = None    # có = MediaPipe không thấy mặt, không có nháp

    @property
    def has_draft(self):
        return self.flags is not None

    @property
    def n_occ(self):
        return sum(self.occ) if self.occ else 0

    @property
    def rank(self):
        return 0 if (self.suggestion == "nen_gan_tay" or not self.has_draft) else 1 if self.suggestion == "can_xem" else 2

    @property
    def suspicious(self):
        return self.suggestion in ("can_xem", "nen_gan_tay") or self.n_flags > 0 or not self.has_draft


def _jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _text(path):
    with open(path, encoding="utf-8-sig", newline="") as f:          # utf-8-sig: file Excel có BOM
        return f.read()


def _delim(text):
    first = text.splitlines()[0] if text.strip() else ""
    return ";" if first.count(";") > first.count(",") else ","


def _dict_rows(path):
    """CSV có tiêu đề -> list dict (khoá thường, bỏ khoảng trắng). Không có file hoặc hỏng thì []."""
    if not os.path.exists(path):
        return []
    try:
        text = _text(path)
        rows = csv.DictReader(io.StringIO(text), delimiter=_delim(text))
        return [{(k or "").strip().lower(): (v or "") for k, v in r.items() if k is not None} for r in rows]
    except (OSError, ValueError, csv.Error):
        return []


def _read_autoqc(run_dir):
    out = {}
    for r in _dict_rows(os.path.join(run_dir, "autoqc", "autoqc.csv")):
        n = _stem(r.get("name", ""))
        if n:
            sug = r.get("suggestion", "").strip()
            out[n] = (sug if sug in ("on", "can_xem", "nen_gan_tay") else "",
                      [p.strip() for p in r.get("problems", "").split(";") if p.strip()])
    return out


def _read_no_face(run_dir):
    """{tên: (lý do, bước)}; mỗi tên một dòng, đọc từ cuối lên như steps._no_face."""
    rows = _dict_rows(os.path.join(run_dir, "no_face.csv"))
    out = {}
    for r in reversed(rows):
        n = _stem(r.get("name", ""))
        if n:
            out[n] = (r.get("reason", "").strip(), r.get("step", "").strip())
    return out


def _read_occ(run_dir):
    """{tên mặt: list[bool] theo thứ tự điểm của config} từ map50/mp50.json (khoá occ = tên các điểm bị che; thứ tự điểm = thứ tự khoá của orig). Thiếu file, hỏng, hay lượt
    chạy trước khi có tính năng này (không có khoá occ) thì {} và trang không hiện gì về occluded."""
    try:
        mp = _jload(os.path.join(run_dir, "map50", "mp50.json"))
    except (OSError, ValueError):
        return {}
    out = {}
    for name, p in (mp.items() if isinstance(mp, dict) else ()):
        if isinstance(p, dict) and isinstance(p.get("orig"), dict) and isinstance(p.get("occ"), list):
            occ = set(p["occ"])
            out[name] = [n in occ for n in p["orig"]]
    return out


def _load(run_dir):
    """(hàng đợi, ghi chú). Xem load_queue."""
    run = run_name(run_dir)
    if not os.path.isdir(run_dir):
        raise RunError(f"Không thấy thư mục lượt chạy {_shown(run_dir)} (đang đứng ở {os.getcwd()}). "
                       "Chạy lệnh từ thư mục source-tool\\m28-prelabel hoặc kiểm tên --run.")
    fpath = os.path.join(run_dir, "flags", "flags.json")
    if not os.path.isfile(fpath):
        raise RunError(f"Thiếu {_shown(fpath)}: chạy python tool\\m28.py prepare --run {run} ... trước.")
    try:
        fl = _jload(fpath)
    except (OSError, ValueError) as e:
        raise RunError(f"Không đọc được {_shown(fpath)} ({e}): chạy lại python tool\\m28.py prepare --run {run} ... "
                       "--force flags.")
    if not isinstance(fl, dict) or any(not isinstance(v, list) for v in fl.values()):
        raise RunError(f"{_shown(fpath)} sai định dạng (cần {{tên mặt: [cờ low_conf của 50 điểm]}}): chạy lại "
                       f"python tool\\m28.py prepare --run {run} ... --force flags.")
    gone = loai_tru.read_excluded(run_dir)                  # mặt xoá mềm: bộ lọc lúc đọc, file kết quả không bị sửa
    fl = {k: v for k, v in fl.items() if k not in gone}
    qc, nf = _read_autoqc(run_dir), _read_no_face(run_dir)
    occ_all = _read_occ(run_dir)

    def path_of(sub, name):
        p = os.path.join(run_dir, sub, name + ".png")
        return p if os.path.isfile(p) else None

    faces = []
    for name, v in fl.items():
        fl_b = [bool(x) for x in v]
        sug, probs = qc.get(name, ("", []))
        oc = occ_all.get(name)
        faces.append(Face(name, name + ".png", path_of("overlays", name), path_of(os.path.join("crop", "images"), name),
                          fl_b, oc if oc is not None and len(oc) == len(fl_b) else None, sum(fl_b), sug, probs, None))
    unusable = 0
    for name, (why, _step) in nf.items():
        if name in fl or name in gone:
            continue
        crop = path_of(os.path.join("crop", "images"), name)
        if crop is None:
            unusable += 1                      # không có ảnh cắt: không rà được, push tự xếp vào Bỏ
            continue
        faces.append(Face(name, name + ".png", None, crop, None, None, 0, "", [], why or "khong_thay_mat"))
    faces.sort(key=lambda f: (f.rank, -f.n_flags, f.name))
    if not faces:
        raise RunError(f"Hàng đợi rỗng: {_shown(fpath)} không có mặt nào"
                       + (f" (còn lại sau khi trừ {len(gone)} mặt đã xoá mềm)" if gone else "")
                       + (f" và {unusable} mặt trong no_face.csv không có ảnh cắt" if unusable else "")
                       + f". Kiểm lại bước prepare của lượt {run}.")
    notes = []
    if unusable:
        notes.append(f"{unusable} mặt không dùng được ở bước crop (no_face.csv), push tự xếp vào Bỏ.")
    return faces, notes


def load_queue(run_dir):
    """Hàng đợi rà: mọi mặt trong flags.json, cộng mặt no_face còn ảnh cắt (không có nháp, chỉ Sửa nhãn hoặc Bỏ).
    Thứ tự (rank, -số cờ, tên): nen_gan_tay/no_face, rồi can_xem, rồi còn lại (trùng steps._queue)."""
    return _load(run_dir)[0]


# ---------- đọc/ghi triage CSV ----------
def _parse(text):
    """Giống hệt steps.read_triage: (dấu phân cách, tiêu đề|None, (name, decision, reason, seconds), các dòng dữ liệu)."""
    delim = _delim(text)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    ci, di, ri, si, header = 0, 1, 2, 3, None
    if rows and "decision" in [c.strip().lower() for c in rows[0]]:
        header = [c.strip().lower() for c in rows.pop(0)]
        ci = header.index("name") if "name" in header else 0
        di = header.index("decision")
        ri = header.index("reason") if "reason" in header else -1
        si = header.index("seconds") if "seconds" in header else -1
    return delim, header, (ci, di, ri, si), rows


def read_rows(path):
    """Các dòng của triage CSV theo thứ tự trong file: dict(name, decision, reason, seconds). Không có file thì []."""
    if not os.path.exists(path):
        return []
    _d, _h, (ci, di, ri, si), rows = _parse(_text(path))
    out = []
    for r in rows:
        if r[0].strip().lower() == "name":
            continue
        get = lambda i: r[i].strip() if 0 <= i < len(r) else ""      # noqa: E731
        out.append(dict(name=_stem(get(ci)), decision=get(di).lower(), reason=get(ri), seconds=get(si)))
    return out


def latest(rows):
    """{tên: (decision, reason)}, dòng sau đè dòng trước. decision không thuộc DECISIONS (kể cả rỗng) = chưa rà."""
    return {r["name"]: (r["decision"], r["reason"]) for r in rows}


def _fmt_seconds(s):
    if s is None or s == "":
        return ""
    return s if isinstance(s, str) else f"{float(s):.1f}"


def append_row(path, file, decision, reason="", seconds=""):
    """Nối một dòng vào triage CSV rồi fsync. File mới/rỗng: ghi tiêu đề trước. File đã có: dùng lại dấu phân cách
    và tiêu đề của nó (tiêu đề 7 cột kiểu autoqc thì ghi 7 cột, mỗi giá trị đúng cột; không tiêu đề thì theo vị trí).
    PermissionError (Windows khoá file khi Excel đang mở) cứ để bay lên cho UI báo."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    delim, eol, header, idx = ",", "\r\n", None, (0, 1, 2, 3)
    text = _text(path) if os.path.exists(path) else ""
    if text.strip():
        delim, header, idx, _rows = _parse(text)
        eol = "\r\n" if "\r\n" in text else "\n" if "\n" in text else "\r\n"
    vals = (file, decision, reason, _fmt_seconds(seconds))
    out = io.StringIO()
    w = csv.writer(out, delimiter=delim, lineterminator=eol)
    if header is None and not text.strip():
        w.writerow(HEADER)
        w.writerow(vals)
    elif header is None:                                  # có dữ liệu nhưng không có tiêu đề: theo vị trí
        w.writerow(vals)
    else:
        row = [""] * max([len(header)] + [i + 1 for i in idx])
        for i, v in zip(idx, vals):
            if i >= 0:
                row[i] = v
        w.writerow(row)
    pre = eol if text and not text.endswith(("\n", "\r")) else ""      # file thiếu xuống dòng cuối: thêm trước khi nối
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(pre + out.getvalue())
        f.flush()
        os.fsync(f.fileno())


# ---------- hàng đợi, tiến độ, lọc, phân trang ----------
def _status(lat, name):
    d = lat.get(name, ("", ""))[0]
    return d if d in DECISIONS else ""


def next_pending(queue, lat, start_name=None):
    """Mặt chưa rà kế tiếp SAU start_name theo thứ tự hàng đợi, đi vòng lại đầu. start_name=None: tìm từ đầu."""
    n = len(queue)
    names = [f.name for f in queue]
    i0 = names.index(start_name) if start_name in names else -1
    for k in range(1, n + 1):
        name = names[(i0 + k) % n]
        if not _status(lat, name):
            return name
    return None


def progress(queue, lat):
    c = {"nhan": 0, "gan_tay": 0, "bo": 0}
    for f in queue:
        s = _status(lat, f.name)
        if s:
            c[s] += 1
    done = sum(c.values())
    return dict(total=len(queue), done=done, nhan=c["nhan"], gan_tay=c["gan_tay"], bo=c["bo"],
                remaining=len(queue) - done)


def filter_faces(queue, lat, mode):
    """mode: tat_ca | chua_ra | dang_ngo | da_ra."""
    if mode == "chua_ra":
        return [f for f in queue if not _status(lat, f.name)]
    if mode == "da_ra":
        return [f for f in queue if _status(lat, f.name)]
    if mode == "dang_ngo":
        return [f for f in queue if f.suspicious]
    return list(queue)


def _nm(x):
    return x if isinstance(x, str) else x.name


def page_of(items, name, size=PAGE_SIZE):
    """Chỉ số trang (từ 0) chứa mặt `name` trong danh sách; không thấy thì 0."""
    for i, x in enumerate(items):
        if _nm(x) == name:
            return i // size
    return 0


def page_slice(items, page, size=PAGE_SIZE):
    """(các phần tử của trang, trang đã kẹp vào [0, n_pages-1], n_pages). Danh sách rỗng: 1 trang."""
    n_pages = max(1, -(-len(items) // size))
    page = min(max(int(page), 0), n_pages - 1)
    return list(items[page * size:(page + 1) * size]), page, n_pages


def seconds_since(t_prev, t_now):
    """Số giây giữa hai lần bấm, làm tròn 1 chữ số, không âm. Chưa có mốc trước thì None (ghi ô trống)."""
    if t_prev is None or t_now is None:
        return None
    return round(max(0.0, float(t_now) - float(t_prev)), 1)


def fmt_points(flags):
    """Số điểm có cờ (đánh số từ 1 như trên ảnh chồng), gộp dãy liền nhau từ 3 điểm: '1–26, 28, 32–36'."""
    nums = [i + 1 for i, f in enumerate(flags or []) if f]
    parts, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f"{nums[i]}–{nums[j]}")
        else:
            parts += [str(x) for x in nums[i:j + 1]]
        i = j + 1
    return ", ".join(parts)


# ---------- trạng thái phía server ----------
class Store:
    """Hàng đợi + triage CSV + ngăn hoàn tác của một lượt rà. Bọc bằng khoá: handler Gradio chạy ở nhiều luồng."""

    def __init__(self, run_dir, reviewer, clock=time.monotonic):
        check_reviewer(reviewer)
        self.run_dir, self.reviewer, self.clock = run_dir, reviewer, clock
        self.lock = threading.RLock()
        self.faces, self.notes = _load(run_dir)
        self.by_name = {f.name: f for f in self.faces}
        self.path = os.path.join(run_dir, "review", f"triage_{reviewer}.csv")
        self.done_path = os.path.join(run_dir, "review", "done.txt")
        self.had_done = os.path.exists(self.done_path)
        try:
            self.rows = read_rows(self.path)
        except UnicodeDecodeError:
            raise RunError(f"{_shown(self.path)} không phải UTF-8: mở bằng Excel rồi lưu lại dạng 'CSV UTF-8', "
                           "hoặc đổi tên file cũ đi để rà lại từ đầu.")
        except OSError as e:
            raise RunError(f"Không đọc được {_shown(self.path)} ({e}). Đóng Excel nếu đang mở file này rồi chạy lại.")
        self.lat = latest(self.rows)
        self.resumed = self.progress()["done"]          # số mặt đã rà từ lần chạy trước
        self.undo_stack = []
        self.finished = False            # đã bấm Xong thật: khoá bấm quyết định / đánh dấu Ca khó mới ở mọi tab (trang vẫn mở, các tab khác dùng được)
        self.closed = False              # đã xác nhận "Đóng trang rà soát": mọi handler ghi từ chối (trang sắp tắt)

    def status(self, name):
        return _status(self.lat, name)

    def _reopen(self):
        """Có thay đổi sau khi đã chốt (mở lại lượt cũ): done.txt cũ hết đúng, xoá để phải bấm Xong lại."""
        try:
            if os.path.exists(self.done_path):
                os.remove(self.done_path)
        except OSError:
            pass

    def progress(self):
        return progress(self.faces, self.lat)

    def decide(self, name, decision, reason="", seconds=None):
        """Ghi một quyết định (CSV rồi bộ nhớ) và đẩy trạng thái cũ vào ngăn hoàn tác."""
        face = self.by_name.get(name)
        if face is None:
            raise ValueError(f"Không có mặt {name!r} trong hàng đợi.")
        if decision not in DECISIONS:
            raise ValueError(f"Quyết định {decision!r} không hợp lệ (nhan, gan_tay, bo).")
        if reason not in REASON_CODES:
            raise ValueError(f"Mã lý do {reason!r} không có trong danh sách lý do.")
        if decision == "nhan" and not face.has_draft:
            raise ValueError(f"{face.file} không có nháp (MediaPipe không thấy mặt): chỉ chọn được Sửa nhãn hoặc Bỏ ảnh.")
        if decision == "nhan":
            reason = ""
        with self.lock:
            old = self.lat.get(name, ("", ""))
            old = old if old[0] in DECISIONS else ("", "")
            append_row(self.path, face.file, decision, reason, seconds)       # lỗi ghi thì chưa đổi gì trong bộ nhớ
            self.rows.append(dict(name=name, decision=decision, reason=reason, seconds=_fmt_seconds(seconds)))
            self.lat[name] = (decision, reason)
            self.undo_stack.append((name, old[0], old[1]))
            self._reopen()

    def undo(self):
        """Hoàn tác lần bấm gần nhất: ghi một dòng trả mặt về trạng thái trước (seconds trống). Trả tên mặt hoặc None."""
        with self.lock:
            if not self.undo_stack:
                return None
            name, dec, why = self.undo_stack[-1]
            append_row(self.path, self.by_name[name].file, dec, why, "")
            self.undo_stack.pop()
            self.rows.append(dict(name=name, decision=dec, reason=why, seconds=""))
            self.lat[name] = (dec, why)
            self._reopen()
            return name

    def can_finish(self):
        with self.lock:
            return self.progress()["remaining"] == 0

    def exclude(self, name):
        """Xoá mềm một mặt của lượt đang rà: bỏ khỏi hàng đợi và ngăn hoàn tác liên quan (excluded.txt do dot_anh ghi trước).
        Trả True nếu mặt có trong hàng đợi. Không bao giờ làm hàng đợi rỗng (ValueError)."""
        with self.lock:
            if name not in self.by_name:
                return False
            if len(self.faces) <= 1:
                raise ValueError("Hàng đợi chỉ còn một mặt: không xoá được.")
            self.faces = [f for f in self.faces if f.name != name]
            self.by_name = {f.name: f for f in self.faces}
            self.undo_stack = [u for u in self.undo_stack if u[0] != name]
            return True

    def reload(self):
        """Đọc lại hàng đợi từ đĩa (sau khi khôi phục ảnh). Giữ nguyên quyết định đã có; mặt chưa rà thì done.txt đã bị gỡ bởi dot_anh."""
        with self.lock:
            self.faces, self.notes = _load(self.run_dir)
            self.by_name = {f.name: f for f in self.faces}
            self.undo_stack = [u for u in self.undo_stack if u[0] in self.by_name]
            if self.progress()["remaining"]:
                self._reopen()
                self.finished = False        # sau Xong mà khôi phục ảnh chưa rà: mở khoá để rà tiếp rồi bấm Xong lại

    def write_done(self):
        """Ghi review/done.txt nguyên tử (file tạm rồi os.replace). Còn mặt chưa rà thì từ chối."""
        with self.lock:
            left = self.progress()["remaining"]
            if left:
                raise ValueError(f"Còn {left} mặt chưa rà.")
            os.makedirs(os.path.dirname(self.done_path), exist_ok=True)
            tmp = self.done_path + f".tmp{os.getpid()}"
            when = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(f"xong\t{self.reviewer}\t{when}\t{len(self.faces)} mặt")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.done_path)
            return self.done_path


# ---------- ảnh chồng và ảnh nhỏ (PIL nạp lười) ----------
_FONTS = {}


def _font(size, bold=False):
    from PIL import ImageFont
    key = (size, bold)
    if key not in _FONTS:
        names = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"] if bold else
                 ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"])
        font = None
        for n in names:
            try:
                font = ImageFont.truetype(n, size)
                break
            except OSError:
                continue
        if font is None:
            try:
                font = ImageFont.load_default(size=size)
            except TypeError:
                font = ImageFont.load_default()
        _FONTS[key] = font
    return _FONTS[key]


def _text_at(draw, xy, text, fill, font, anchor, stroke=None):
    kw = dict(stroke_width=1, stroke_fill=stroke) if stroke else {}        # stroke: viền chữ cho đọc được trên mọi nền
    try:
        draw.text(xy, text, fill=fill, font=font, anchor=anchor, **kw)
    except ValueError:                                    # phông bitmap cũ không hỗ trợ anchor
        draw.text(xy, text, fill=fill, font=font, **kw)


def _save(img, path, fmt, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".tmp{os.getpid()}"
    img.save(tmp, format=fmt, **kw)
    os.replace(tmp, path)


def _tmp(run_dir, *parts):
    return os.path.join(run_dir, "_tmp", *parts)


def _safe(name):
    return re.sub(r"[^\w.-]", "_", name)


_MP50 = {}          # đường dẫn -> (mtime, dữ liệu): mp50.json của lượt 616 mặt vài MB, chỉ nạp một lần


def _mp50(run_dir):
    p = os.path.join(run_dir, "map50", "mp50.json")
    try:
        m = os.path.getmtime(p)
    except OSError:
        return None
    if p not in _MP50 or _MP50[p][0] != m:
        try:
            _MP50[p] = (m, _jload(p))
        except (OSError, ValueError):
            return None
    return _MP50[p][1]


def _style_mtime():
    """Giờ sửa của mau_nhom.py: ảnh chồng cũ hơn mốc này là ảnh vẽ kiểu cũ (một màu xanh/đỏ), trang vẽ lại tạm theo màu nhóm."""
    try:
        return os.path.getmtime(mau_nhom.__file__)
    except OSError:
        return 0.0


def _pil_dot(d, x, y, rgb, low):
    """Chấm cùng kiểu với steps.overlays: ổn = chấm bán kính R_OK viền tối; low_conf = cùng cỡ, viền trắng (như CVAT không đổi cỡ điểm)."""
    cx, cy = int(round(x)), int(round(y))
    if low:
        r = mau_nhom.R_LOW
        ring = r + mau_nhom.RING_LOW
        d.ellipse([cx - ring, cy - ring, cx + ring, cy + ring], fill=mau_nhom.WHITE)
    else:
        r = mau_nhom.R_OK
        d.ellipse([cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1], fill=mau_nhom.DARK)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb)


def _redraw_overlay(face, run_dir, pts, names=None):
    """Vẽ lại ảnh chồng như steps.overlays: chấm màu nhóm (tên điểm `names` thuộc nhóm nào; không có thì đỏ = low_conf, xanh = ổn như bản cũ), low_conf cùng cỡ, viền trắng,
    kèm số thứ tự i+1. Ảnh đã vẽ cũ hơn mau_nhom.py thì vẽ lại (bản vẽ kiểu cũ còn nằm trong _tmp)."""
    from PIL import Image, ImageDraw
    out = _tmp(run_dir, "overlays", face.name + ".png")
    src_m = max(os.path.getmtime(face.crop), os.path.getmtime(os.path.join(run_dir, "map50", "mp50.json")), _style_mtime())
    if os.path.exists(out) and os.path.getmtime(out) >= src_m:
        return out
    img = Image.open(face.crop).convert("RGB")
    d = ImageDraw.Draw(img)
    font = _font(10)
    for i, (x, y) in enumerate(pts):
        low = bool(face.flags[i])
        col = mau_nhom.dot_rgb(mau_nhom.group_of(names[i]) if names and i < len(names) else None, low)
        _pil_dot(d, x, y, col, low)
        _text_at(d, (int(x) + 4, int(y) - 3), str(i + 1), col, font, "ls", stroke=mau_nhom.DARK)
    _save(img, out, "PNG")
    return out


_IMG_OK = {}        # đường dẫn -> ((mtime_ns, size), đọc được không)


def _img_ok(path):
    """Ảnh mở và giải mã được (ảnh chồng bị cắt dở sau một lần prepare bị ngắt thì không). Có cache theo mtime/size."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    key = (st.st_mtime_ns, st.st_size)
    c = _IMG_OK.get(path)
    if c and c[0] == key:
        return c[1]
    try:
        from PIL import Image
    except ImportError:
        return True
    try:
        with Image.open(path) as im:
            im.load()
        ok = True
    except Exception:                                   # OSError, SyntaxError, ValueError, ảnh quá lớn...
        ok = False
    _IMG_OK[path] = (key, ok)
    return ok


def _placeholder(run_dir):
    from PIL import Image, ImageDraw
    out = _tmp(run_dir, "overlays", "_khong_co_anh.png")
    if not os.path.exists(out):
        img = Image.new("RGB", (512, 512), (214, 214, 214))
        _text_at(ImageDraw.Draw(img), (256, 256), "Không có ảnh chồng", (70, 70, 70), _font(30, True), "mm")
        _save(img, out, "PNG")
    return out


def _recolored(face, run_dir):
    """Ảnh chồng của lượt chuẩn bị TRƯỚC khi có màu theo nhóm (file cũ hơn mau_nhom.py, một màu xanh/đỏ): vẽ lại tạm vào _tmp theo màu nhóm để giống CVAT,
    không đụng file gốc, không cảnh báo. Chỉ khi tên điểm trong mp50.json đều thuộc nhóm đã biết (lượt tên cũ pNN giữ nguyên ảnh). Không vẽ được thì None."""
    try:
        if not (face.has_draft and face.crop and os.path.isfile(face.crop) and _img_ok(face.crop)):
            return None
        if os.path.getmtime(face.overlay) >= _style_mtime():
            return None
        orig = (_mp50(run_dir) or {}).get(face.name, {}).get("orig")
        if not orig or len(orig) != len(face.flags) or not mau_nhom.all_grouped(orig.keys()):
            return None
        return _redraw_overlay(face, run_dir, list(orig.values()), list(orig.keys()))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def overlay_for(face, run_dir):
    """(đường dẫn ảnh lớn, cảnh báo|None).
    Có overlays/<tên>.png đọc được thì dùng; thiếu hoặc hỏng mà có ảnh cắt và mp50.json thì vẽ lại vào runs/<run>/_tmp/overlays/
    (không đụng file gốc); mặt không có nháp (no_face) dùng ảnh cắt; thiếu cả hai thì ảnh xám 512 kèm cảnh báo."""
    bad = False
    if face.overlay and os.path.isfile(face.overlay):
        if _img_ok(face.overlay):
            return _recolored(face, run_dir) or face.overlay, None
        bad = True
    crop_ok = bool(face.crop and os.path.isfile(face.crop) and _img_ok(face.crop))
    if not face.has_draft:
        if crop_ok:
            return face.crop, None
        return _placeholder(run_dir), f"Thiếu hoặc hỏng ảnh cắt của {face.file} (crop/images): không xem được mặt này."
    if crop_ok:
        mp = _mp50(run_dir)
        orig = (mp or {}).get(face.name, {}).get("orig")
        if orig and len(list(orig.values())) == len(face.flags):
            try:
                what = "hỏng" if bad else "thiếu"
                return (_redraw_overlay(face, run_dir, list(orig.values()), list(orig.keys())),
                        f"Ảnh chồng overlays/{face.file} {what}: trang vẽ lại tạm từ ảnh cắt và mp50.json "
                        f"(chạy lại prepare --force overlays để sửa hẳn)." if bad else
                        f"Thiếu overlays/{face.file}: ảnh chồng này do trang vẽ lại tạm từ ảnh cắt và mp50.json.")
            except (OSError, ValueError, KeyError):
                pass
    head = f"Ảnh chồng overlays/{face.file} hỏng" if bad else f"Thiếu ảnh chồng overlays/{face.file}"
    return (_placeholder(run_dir),
            f"{head} và không vẽ lại được (thiếu ảnh cắt hoặc map50/mp50.json). "
            "Không xem được nháp: đừng chọn Nhận, chạy lại python tool\\m28.py prepare ... --force overlays.")


def _rgb_hex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in rgb)


def big_view(face, run_dir):
    crop_ok = bool(face.crop and os.path.isfile(face.crop) and _img_ok(face.crop))
    if not (face.has_draft and crop_ok):
        big, warn = overlay_for(face, run_dir)
        return big, warn, None
    orig = (_mp50(run_dir) or {}).get(face.name, {}).get("orig")
    if not orig or len(orig) != len(face.flags):
        big, warn = overlay_for(face, run_dir)
        return big, warn, None
    occ = face.occ if (face.occ is not None and len(face.occ) == len(face.flags)) else [False] * len(face.flags)
    try:
        out = []
        for i, (n, xy) in enumerate(orig.items()):
            low = bool(face.flags[i])
            g = mau_nhom.group_of(n)
            out.append({"x": float(xy[0]), "y": float(xy[1]), "i": i + 1, "n": n, "g": g,
                        "color": _rgb_hex(mau_nhom.dot_rgb(g, low)), "low": low, "occ": bool(occ[i])})
    except (IndexError, TypeError, ValueError):
        big, warn = overlay_for(face, run_dir)
        return big, warn, None
    return face.crop, None, out


def _pts_embed(pts):
    if not pts:
        return ""
    return ('<textarea id="m28-pts" style="display:none" aria-hidden="true">'
            + html.escape(json.dumps(pts, separators=(",", ":"))) + "</textarea>")


def _build_thumb(src, out, status):
    from PIL import Image, ImageDraw, ImageOps
    im = Image.open(src).convert("RGB")
    im.thumbnail((THUMB - 2 * BORDER, THUMB - 2 * BORDER), Image.Resampling.LANCZOS)
    im = ImageOps.expand(im, border=BORDER, fill=STATUS_COLOR[status])
    if STATUS_LETTER[status]:
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 25, 25], fill=STATUS_COLOR[status])
        _text_at(d, (13, 13), STATUS_LETTER[status], "white", _font(18, True), "mm")
    _save(im, out, "JPEG", quality=85)


def thumb_for(face, status, run_dir):
    """Ảnh nhỏ JPEG ~176 px (chất lượng 85) có viền 6 px theo trạng thái vẽ thẳng vào ảnh và nhãn N/G/B ở góc.
    Tên file chứa trạng thái nên URL đổi theo, trình duyệt không giữ ảnh cũ. Tạo lười, có cache theo mtime.
    Một ảnh hỏng không làm sập cả trang: rơi về ảnh xám 'Không có ảnh chồng'."""
    status = status if status in DECISIONS else ""
    src, _warn = overlay_for(face, run_dir)
    out = _tmp(run_dir, "thumbs", f"{_safe(face.name)}__{status or 'chua'}.jpg")
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        return out
    try:
        _build_thumb(src, out, status)
    except (OSError, SyntaxError, ValueError):
        _build_thumb(_placeholder(run_dir), out, status)
    return out


# ---------- phiên làm việc của một tab trình duyệt (dict thuần, để trong gr.State) ----------
def new_session(store):
    cur = next_pending(store.faces, store.lat, None) or store.faces[0].name
    ses = dict(cur=cur, mode="tat_ca", page=0, names=[], t=store.clock())
    _follow(store, ses)
    return ses


def ensure_session(store, ses):
    if not isinstance(ses, dict) or ses.get("cur") not in store.by_name:
        return new_session(store)
    return ses


def _filtered(store, ses):
    return filter_faces(store.faces, store.lat, ses["mode"])


def _follow(store, ses):
    """Đưa trang của lưới tới trang có mặt đang xem (nếu mặt đó nằm trong danh sách đã lọc)."""
    items = _filtered(store, ses)
    if any(f.name == ses["cur"] for f in items):
        ses["page"] = page_of(items, ses["cur"], PAGE_SIZE)


def act_select(store, ses, index):
    names = ses.get("names", [])
    if isinstance(index, int) and 0 <= index < len(names):
        ses["cur"] = names[index]
    return "", "info"


def act_filter(store, ses, mode):
    """Đổi bộ lọc. Mặt đang xem không nằm trong danh sách mới thì chuyển sang mặt chưa rà đầu tiên của danh sách
    (không có mặt chưa rà thì mặt đầu); danh sách rỗng thì giữ mặt cũ nhưng khoá N/G/B (xem make_view)."""
    ses["mode"] = mode if mode in dict(FILTERS) else "tat_ca"
    items = _filtered(store, ses)
    if items and not any(f.name == ses["cur"] for f in items):
        ses["cur"] = next_pending(items, store.lat, None) or items[0].name
    ses["page"] = page_of(items, ses["cur"], PAGE_SIZE) if any(f.name == ses["cur"] for f in items) else 0
    return "", "info"


def act_page(store, ses, delta):
    ses["page"] = ses.get("page", 0) + delta
    return "", "info"


def act_step(store, ses, delta):
    """← / →: đi trong danh sách đã lọc, không bỏ qua mặt đã rà."""
    items = _filtered(store, ses)
    if not items:
        return "Danh sách đang lọc trống.", "info"
    names = [f.name for f in items]
    if ses["cur"] in names:
        i = names.index(ses["cur"]) + delta
    else:
        i = 0 if delta > 0 else len(names) - 1
    ses["cur"] = names[min(max(i, 0), len(names) - 1)]
    _follow(store, ses)
    return "", "info"


STALE_MSG = "Bỏ qua một lần bấm vì ảnh chưa kịp đổi. Nhìn ảnh rồi bấm lại."
CLOSED_MSG = "Lượt này đã chốt khi đẩy lên CVAT: đã khoá quyết định, không ghi thêm được."
CLOSING_MSG = nap_anh.CLOSING_MSG


def act_decide(store, ses, decision, reason, shown):
    """Bấm Nhận / Sửa nhãn / Bỏ ảnh cho mặt `shown` (mặt người rà đang nhìn thấy khi bấm). Trả (thông báo, mức, đặt lại lý do).
    Nếu `shown` khác mặt hiện hành của server (bấm quá nhanh khi trang chưa kịp đổi ảnh) thì bỏ qua, không ghi gì.
    Bấm đúng quyết định (và lý do) mặt đó đang có thì không ghi thêm dòng nào."""
    if store.closed:
        return CLOSING_MSG, "info", False
    if store.finished:
        return CLOSED_MSG, "info", False
    if shown != ses["cur"]:
        return STALE_MSG, "info", False
    name = ses["cur"]
    before = _filtered(store, ses)
    if not any(f.name == name for f in before):
        return "Mặt đang xem không nằm trong bộ lọc này: chọn một ảnh trong lưới trước.", "info", False
    if decision in DECISIONS and store.status(name) == decision:
        cur_reason = store.lat[name][1]
        if decision == "nhan" or (reason or "") == cur_reason:
            return f"{name}.png đã là {LABELS[decision]}" + (f" [{REASON_VI.get(cur_reason, cur_reason)}]" if cur_reason else "") + " rồi, không ghi thêm.", "info", False
    now = store.clock()
    try:
        store.decide(name, decision, reason, seconds_since(ses.get("t"), now))
    except ValueError as e:
        return str(e), "warn", False
    except OSError as e:
        return (f"Không ghi được {_shown(store.path)}. Nếu đang mở bằng Excel thì đóng Excel rồi bấm lại. ({type(e).__name__})",
                "warn", False)
    ses["t"] = now
    why = store.lat[name][1]
    msg = f"Đã ghi {name}.png: {LABELS[decision]}"
    if why:
        msg += f" [{REASON_VI.get(why, why)}]"
    elif decision != "nhan":
        msg += " [Chưa có lý do]"
    nxt = next_pending(before, store.lat, name)                  # trước hết trong danh sách đang lọc
    if nxt is None:
        nxt = next_pending(store.faces, store.lat, name)
        if nxt is not None and not any(f.name == nxt for f in _filtered(store, ses)):
            ses["mode"] = "chua_ra"
            msg += ". Bộ lọc hiện tại hết mặt chưa rà, chuyển sang 'Chưa rà'."
    if nxt:
        ses["cur"] = nxt
    else:                                                         # 'Đã rà hết: bấm Push to CVAT' đã có ở thanh bước
        if not any(f.name == name for f in _filtered(store, ses)):
            ses["mode"] = "tat_ca"                                # bộ lọc 'Chưa rà' trống thì quay về Tất cả
    _follow(store, ses)
    return msg, "ok", True


def act_undo(store, ses, shown):
    if store.closed:
        return CLOSING_MSG, "info", False
    if store.finished:
        return CLOSED_MSG, "info", False
    if shown != ses["cur"]:
        return STALE_MSG, "info", False
    try:
        name = store.undo()
    except OSError as e:
        return (f"Không ghi được {_shown(store.path)}. Nếu đang mở bằng Excel thì đóng Excel rồi bấm lại. ({type(e).__name__})",
                "warn", False)
    if name is None:
        return "Chưa có gì để hoàn tác.", "info", False
    ses["cur"] = name
    ses["t"] = store.clock()
    if not any(f.name == name for f in _filtered(store, ses)):
        ses["mode"] = "tat_ca"                                    # mặt vừa hoàn tác rời bộ lọc đang chọn
    _follow(store, ses)
    return f"Đã hoàn tác {name}.png: về trạng thái trước đó.", "ok", True


def act_finish(store, ses):
    """Trả (thông báo, mức, đã xong thật). Xong chỉ ghi done.txt và khoá quyết định; KHÔNG tắt trang (nút 'Close page' lo việc đó)."""
    if store.closed:
        return CLOSING_MSG, "info", False
    if store.finished:
        return CLOSED_MSG, "info", False
    try:
        path = store.write_done()
    except ValueError as e:
        return str(e), "warn", False
    except OSError as e:
        return f"Không ghi được {_shown(store.done_path)} ({e}).", "warn", False
    store.finished = True
    return (f"Đã ghi {_shown(path)}: lượt này đã chốt, quyết định đã khoá."), "ok", True


# ---------- nút "Close page" (logic thuần, test không cần gradio) ----------
def close_check(store, ctx):
    """(được đóng, thông điệp, mức). Từ chối khi đang chuẩn bị / đẩy / xoá task hoặc đang chuyển lượt (đóng lúc đó giết việc đang chạy).
    Đã đang đóng thì cũng không cho đóng lần nữa (cờ nằm trên ctx, dùng chung mọi tab)."""
    if ctx.closing:
        return False, "Trang đang đóng.", "info"
    if ctx.switch_to is not None:
        return False, "Đang chuyển sang lượt mới: chờ trang tải lại rồi hãy đóng.", "warn"
    if ctx.job.running:
        return False, f"Đang chuẩn bị lượt {ctx.job.run}: chờ xong hoặc bấm Cancel ở tab Nạp ảnh.", "warn"
    if ctx.push_job.running or ctx.del_job.running:
        busy = ctx.push_job if ctx.push_job.running else ctx.del_job
        return False, f"Đang {'đẩy' if busy is ctx.push_job else 'xoá task của'} lượt {busy.run} (CVAT): chờ xong hoặc bấm Cancel.", "warn"
    if ctx.smoke_job.running:
        return False, "Đang chạy kiểm tra nhanh CVAT (popup CVAT): chờ xong hoặc bấm Cancel check.", "warn"
    if ctx.collect_job.running:
        return False, (f"Đang gộp job CVAT của lượt {ctx.collect_job.run} (Merge jobs & Finish, tab Các đợt): chờ xong hoặc bấm Cancel ở khung gộp job "
                       "của tab Các đợt."), "warn"
    return True, "", "info"


def close_prompt(store):
    """Nội dung hộp xác nhận Đóng: (loại, câu hỏi, cảnh báo). Loại: nap (chưa có lượt) | xong | chua_con (chưa Xong, còn mặt chưa rà)
    | chua_het (chưa Xong nhưng đã rà hết). 'Đã Xong' dựa vào done.txt có thật trên đĩa lúc này (không chỉ cờ store.finished)."""
    if store is None:
        return "nap", "Đóng trang rà soát? Chưa có lượt nào đang rà; việc đã làm ở các tab khác đã được lưu.", ""
    if store.finished or os.path.exists(store.done_path):
        return "xong", "Đóng trang rà soát? Lệnh m28 trong cmd sẽ đi tiếp.", ""
    left = store.progress()["remaining"]
    if left:
        return ("chua_con", "Đóng trang rà soát?",
                f"Lượt này còn mặt chưa rà (còn {left} mặt). m28 sẽ dừng ở bước review; "
                "gõ lại đúng lệnh để làm tiếp, các lần bấm đã lưu không mất.")
    return ("chua_het", "Đóng trang rà soát? Đã rà hết: đóng trang sẽ chốt lượt này (ghi done.txt), lệnh m28 trong cmd đi tiếp.", "")


def close_body_html(store, extra=""):
    kind, q, warn = close_prompt(store)
    w = f'<div class="nap-box nap-err" role="alert"><b>{html.escape(warn)}</b></div>' if warn else ""
    return f'<div class="modal-title" id="close-confirm-title">{html.escape(q)}</div>{w}{extra}'


CLOSED_HTML = ('<div class="m28-closed" role="alert"><div class="m28-closed-box"><b>Đã đóng trang rà soát.</b>'
               '<span>Quay lại cửa sổ cmd. Trang đã tắt, bấm gì cũng không còn tác dụng.</span></div></div>')


# ---------- mô hình hiển thị (thuần, test không cần gradio) ----------
CAP_OK, CAP_XEM, CAP_KHONG = "Ổn", "Cần xem", "Không nháp"


def caption(face, status):
    """Chú thích ảnh nhỏ ở lưới Rà soát: CHỈ gợi ý của máy (Cần xem / Ổn), không kèm tên, số cờ, quyết định (xem ở khung thông tin; quyết định đã rà là
    chữ N / S / B ở góc ảnh). Ngắn cho vừa một dòng; JS tô màu nổi bật theo đúng chữ (#grid .caption-label[data-cap])."""
    if not face.has_draft:
        return CAP_KHONG
    return CAP_OK if face.suggestion == "on" else CAP_XEM


def _chip(status, extra=""):
    cls = status or "chua"
    txt = LABELS.get(status, "Chưa rà") + (f" · {extra}" if extra else "")
    return f'<span class="m28-chip c-{cls}">{html.escape(txt)}</span>'


def notes_html(store):
    """Ghi chú cố định của phiên (không đổi khi đang rà): làm tiếp từ lần trước, mặt không dùng được ở bước crop."""
    notes = []
    if store.resumed:
        notes.append(f"Làm tiếp từ {os.path.basename(store.path)}: đã có {store.resumed} mặt rà từ lần trước.")
    notes += store.notes
    return "".join(f'<div class="m28-note">{html.escape(n)}</div>' for n in notes)


DONE_BAR_TEXT = ("Đã chốt lượt này khi đẩy lên CVAT: quyết định đã khoá. Theo dõi job ở bước Sửa trên CVAT, xem Các đợt, xuất Ca khó. "
                 "Xong việc bấm 'Close page' để quay lại cmd.")


def _svg(body, size=16):
    return (f'<svg class="ic" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>')


ICON = {
    "zap": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "chev": '<path d="m6 9 6 6 6-6"/>',
    "chevr": '<path d="m9 6 6 6-6 6"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "plus": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v1"/><path d="M3 9h18l-2 9H5z"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
}


def icon(name, size=16):
    return _svg(ICON[name], size)


BRAND_HTML = (f'<div class="m28-brand"><span class="m28-logo">{icon("zap", 16)}</span><span class="m28-brand-name">M28 Landmark Studio</span></div>')


MENU_MAX = 15


def _ngay(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso)).strftime("%d/%m %H:%M")
    except ValueError:
        return ""


def batch_menu_html(store, ctx):
    if ctx is None or not ctx.runs_root:
        return ""
    cur = run_name(store.run_dir) if store is not None else None
    items = []
    for r in dot_anh.list_runs(ctx.runs_root)[:MENU_MAX]:
        rd = os.path.join(ctx.runs_root, r)
        ready = os.path.isfile(os.path.join(rd, "flags", "flags.json"))
        st = (dot_anh.read_push(rd) or {}).get("trang_thai")
        done = st == "xong" and dot_anh.is_merged(dot_anh.read_gop(rd))
        tag = ("Đang mở" if r == cur else "Completed" if done else "Đã đẩy CVAT" if st == "xong" else "" if ready else "Chưa prepare xong")
        body = (f'<span class="m28-mi-name">{html.escape(r)}</span><span class="m28-mi-date">{html.escape(_ngay(dot_anh.run_date(rd)))}</span>'
                + (f'<span class="m28-mi-tag">{html.escape(tag)}</span>' if tag else ""))
        if r == cur:
            items.append(f'<button type="button" class="m28-mi m28-mi-cur" role="menuitem" data-go="ra">{body}</button>')
        elif not ready:
            items.append(f'<button type="button" class="m28-mi" role="menuitem" disabled>{body}</button>')
        else:
            items.append(f'<button type="button" class="m28-mi" role="menuitem" data-act="ra" data-run="{html.escape(r)}">{body}</button>')
    if not items:
        items.append('<div class="m28-mi-empty">Chưa có đợt nào.</div>')
    return (f'<div class="m28-pill-menu" role="menu"><div class="m28-mi-head">Chọn đợt để rà</div>{"".join(items)}'
            f'<button type="button" class="m28-mi-all" data-go="dot">All batches</button></div>')


def batch_pill_html(store, ctx=None):
    caret = (f'<button type="button" class="m28-pill-caret" data-pill-menu aria-haspopup="menu" title="Chọn đợt khác">{icon("chev", 14)}</button>'
             if ctx is not None else "")
    if store is None:
        main = (f'<button type="button" class="m28-pill" data-go="dot" title="Mở trang Các đợt">{icon("folder")}'
                f'<span class="m28-pill-muted">Chưa chọn đợt</span></button>')
    else:
        p = store.progress()
        pct = round(100 * p["done"] / p["total"]) if p["total"] else 0
        main = (f'<button type="button" class="m28-pill" data-go="dot" title="Mở trang Các đợt">{icon("folder")}'
                f'<b class="m28-pill-run">{html.escape(run_name(store.run_dir))}</b>'
                f'<span class="m28-pill-muted">{p["total"]} mặt · {pct}% đã rà</span></button>')
    return f'<div class="m28-pillgrp">{main}{caret}{batch_menu_html(store, ctx)}</div>'


HEAD_BTNS = (f'<div class="m28-head-btns"><button type="button" class="m28-head-btn" data-go="dot">{icon("open")}<span>Switch batch</span></button>'
             f'<button type="button" class="m28-head-btn m28-head-btn-blue" data-go="nap">{icon("plus")}<span>New upload</span></button></div>')


def header_html(store, ses):
    p = store.progress()
    tot = p["total"] or 1
    w = {k: round(100 * p[k] / tot, 2) for k in ("nhan", "gan_tay", "bo")}
    pct = round(100 * p["done"] / p["total"]) if p["total"] else 0
    chips = "".join(f'<span class="m28-chip c-{k}">{html.escape(t)} <b>{p[k]}</b></span>' for k, t in
                    (("nhan", "Nhận"), ("gan_tay", "Sửa nhãn"), ("bo", "Bỏ")))
    chips += f'<span class="m28-chip c-chua">Còn lại <b>{p["remaining"]}</b></span>'
    again = ('<span class="m28-chip c-gan_tay">Lượt này đã chốt trước đó</span>'
             if store.had_done and not store.finished else "")
    done = (f'<div class="m28-done-bar" role="status">{html.escape(DONE_BAR_TEXT, quote=False)}</div>' if store.finished else "")
    state = "Đã xong" if store.finished else ("Đã rà hết" if p["remaining"] == 0 else "Đang rà soát")
    bar = "".join(f'<i class="b-{k}" style="width:{w[k]}%"></i>' for k in ("nhan", "gan_tay", "bo"))
    return (f'{done}<div class="m28-head"><div class="m28-head-ic">{icon("layers", 20)}</div>'
            f'<div class="m28-head-main"><div class="m28-top"><span class="m28-kicker">Đang rà soát đợt:</span>'
            f'<span class="m28-run">{html.escape(run_name(store.run_dir))}</span><span class="m28-state">{state}</span>{again}</div>'
            f'<div class="m28-sub">Tổng {p["total"]} khuôn mặt · {p["done"]} đã rà · {p["remaining"]} chưa rà · người rà '
            f'<b>{html.escape(store.reviewer)}</b></div></div>'
            f'<div class="m28-prog"><span class="m28-count">Đã rà {p["done"]}/{p["total"]}</span>'
            f'<div class="m28-bar m28-bar3" role="progressbar" aria-valuenow="{p["done"]}" aria-valuemax="{p["total"]}">{bar}</div>'
            f'<span class="m28-pct">{pct}%</span><div class="m28-chips">{chips}</div></div>{HEAD_BTNS}</div>')


_TFLIP = {}


def _flip_cfg(run_dir):
    path = os.path.join(nap_anh.runs_layout(run_dir)[1], "config", "m28_config.json")
    try:
        m = os.path.getmtime(path)
    except OSError:
        return dict(t=None, iod=("mattrai_1", "matphai_1"))
    if path not in _TFLIP or _TFLIP[path][0] != m:
        info = cai_dat.read_t_flip(path)
        iod = tuple(info["iod_points"][:2]) if len(info["iod_points"]) >= 2 else ("mattrai_1", "matphai_1")
        cfg = None
        if info["ok"] and info.get("v2"):                                       # cờ phiên bản 2: cần cả config (mô hình, điểm, nhóm)
            try:
                with open(path, encoding="utf-8") as f:
                    cfg = json.load(f)
            except (OSError, ValueError):
                cfg = None
        _TFLIP[path] = (m, dict(t=info["t_flip"] if info["ok"] else None, iod=iod, cfg=cfg, thr=info.get("v2_threshold") if cfg else None))
    return _TFLIP[path][1]


def point_scores(store, face):
    mp = (_mp50(store.run_dir) or {}).get(face.name) or {}
    orig, flip = mp.get("orig"), mp.get("flip") or {}
    if not face.has_draft or not isinstance(orig, dict) or not orig:
        return None
    fc = _flip_cfg(store.run_dir)
    t = fc["t"]
    a, b = fc["iod"]
    iod = math.dist(orig[a], orig[b]) if a in orig and b in orig else 0.0
    occ = set(mp.get("occ") or ())
    pv = None
    if fc.get("cfg"):                                                             # cờ phiên bản 2: độ tin cậy từ xác suất (dưới 0,50 = có cờ)
        p2 = co_v2.probs(mp, fc["cfg"])
        pv = None if p2 is None else dict(zip([q["name"] for q in fc["cfg"]["points"]], (float(x) for x in p2)))
    rows = []
    for i, (name, p) in enumerate(orig.items()):
        err = math.dist(p, flip[name]) / iod if iod > 0 and name in flip else None
        if pv is not None and name in pv:
            conf = co_v2.confidence(pv[name], fc["thr"])
        elif err is None:
            conf = 0.0
        elif t:
            conf = max(0.0, min(1.0, 1.0 - err / (2.0 * t)))
        else:
            conf = max(0.0, min(1.0, 1.0 - err * 10.0))
        rows.append(dict(idx=i + 1, name=name, x=float(p[0]), y=float(p[1]), err=err, conf=conf,
                         low=bool(face.flags[i]) if face.flags and i < len(face.flags) else False, occ=name in occ,
                         group=mau_nhom.group_of(name) or "khac"))
    if pv is not None:
        stale = any(r["name"] in pv and r["low"] != (pv[r["name"]] > fc["thr"]) for r in rows)
    else:
        stale = bool(t) and not fc.get("cfg") and any(r["err"] is not None and r["low"] != (r["err"] > t) for r in rows)
    return dict(rows=rows, t=t, stale=stale, v2=bool(fc.get("cfg")))


GROUP_ORDER = ("longmaytrai", "longmayphai", "mattrai", "matphai", "songmui", "moingoai", "moitrong")


def _conf_table_html(store, face):
    if not face.has_draft:
        return '<div class="m28-empty conf-empty">Ảnh không có nháp (MediaPipe không thấy mặt)</div>'
    sc = point_scores(store, face)
    if sc is None:
        return '<div class="m28-empty conf-empty">Không tìm thấy toạ độ 50 điểm trong map50/mp50.json</div>'
    rows, t = sc["rows"], sc["t"]
    cut_low, cut_mid = (0.5, 0.65) if t or sc.get("v2") else (0.6, 0.8)
    pts = sorted(rows, key=lambda r: (r["conf"], r["idx"]))
    groups = [g for g in GROUP_ORDER if any(r["group"] == g for r in rows)]
    groups += sorted({r["group"] for r in rows} - set(groups))

    def card(key, label, sub, color, n_low):
        badge = f'<span class="card-warn-badge" title="{n_low} điểm low_conf">⚠ {n_low}</span>' if n_low else ""
        return (f'<div class="conf-group-card{" active" if key == "tat_ca" else ""}" data-group="{html.escape(key)}" style="--grp-col:{color}" '
                f'role="button" tabindex="0"><div class="card-top"><i class="conf-dot" style="background:{color}"></i>'
                f'<span class="card-name">{html.escape(label)}</span>{badge}</div><div class="card-sub">{html.escape(sub)}</div></div>')

    cards = [card("tat_ca", "Tất cả", f"{len(rows)} điểm", "#64748b", sum(r["low"] for r in rows))]
    for g in groups:
        gp = [r for r in rows if r["group"] == g]
        cards.append(card(g, g, f'{mau_nhom.GROUP_VI.get(g, g)} ({len(gp)})', mau_nhom.GROUP_COLOR.get(g, "#9ca3af"), sum(r["low"] for r in gp)))

    body = []
    for r in pts:
        badges = []
        if r["low"]:
            badges.append('<span class="conf-badge badge-warn">⚠ low_conf</span>')
        if r["occ"]:
            badges.append('<span class="conf-badge badge-occ">occluded</span>')
        if not badges:
            badges.append('<span class="conf-badge badge-ok">✓ Ổn</span>')
        cls = "score-low" if r["conf"] < cut_low else ("score-mid" if r["conf"] < cut_mid else "score-high")
        col = mau_nhom.GROUP_COLOR.get(r["group"], "#9ca3af")
        body.append(f'<tr class="conf-row" data-group="{html.escape(r["group"])}" data-pt="{r["idx"]}" data-x="{r["x"]:.1f}" data-y="{r["y"]:.1f}" '
                    f'data-name="{html.escape(r["name"])}" data-face="{html.escape(face.name)}" data-col="{col}" tabindex="0" role="button" '
                    f'title="Bấm để chỉ điểm #{r["idx"]} trên ảnh, nhấp đúp để phóng to tới điểm">'
                    f'<td>#{r["idx"]:02d}</td><td><span class="conf-name-cell"><i class="conf-dot" style="background:{col}"></i>'
                    f'<span class="conf-pt-name">{html.escape(r["name"])}</span></span></td><td>{"".join(badges)}</td>'
                    f'<td class="td-score"><span class="conf-score {cls}">{r["conf"]:.2f}</span></td></tr>')
    if sc.get("v2"):
        rule = 'Dưới <b>0,50</b> = low_conf (cờ phiên bản 2)'
    elif t:
        rule = (f'Dưới <b>0,50</b> = low_conf (t_flip <b>{cai_dat.fmt_vi(t)}</b>)')
    else:
        rule = 't_flip chưa đặt: chưa có cờ low_conf'
    stale = ('<div class="m28-warn conf-stale">Cờ low_conf trên ảnh của lượt này tính theo t_flip cũ hoặc cờ cũ: chạy lại '
             '<code>prepare --force flags autoqc overlays</code> để ảnh và bảng khớp nhau.</div>') if sc["stale"] else ""
    return (f'<div class="conf-table-wrapper">'
            f'<div class="conf-rule"><span>{rule}</span><button type="button" class="conf-edit" data-cd-open="tflip">Edit</button></div>{stale}'
            f'<div class="conf-group-cards" id="conf-group-cards">{"".join(cards)}</div>'
            f'<div class="conf-scroll-box"><table class="conf-table"><thead><tr><th style="width:13%">STT</th><th style="width:40%">Tên điểm</th>'
            f'<th style="width:29%">Trạng thái</th><th style="width:18%;text-align:right">Tin cậy</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></div>')


STEPS = (("nap", "Nạp ảnh"), ("ra", "Rà soát"), ("cvat", "Sửa trên CVAT"), ("gop", "Gộp & kết thúc"))
GO_TAB = {"nap": "nap", "ra": "ra", "push": "ra", "cvat": "cvat", "dot": "dot", "gop": "dot", "cakho": "cakho", "hop": "hop", "thongke": "thongke", "loc": "loc"}
# data-tab của bước: bước được viền "đang xem" khi tab đó mở. Bước 4 là một trang riêng TRONG tab Các đợt (dot_ui, view 'gop'): STEPS_JS coi tab đó là 'gop'
# khi trang Gộp & kết thúc đang hiện; danh sách đợt (nút đợt, Switch batch) thì không bước nào được viền.
STEP_TAB = {"nap": "nap", "ra": "ra", "cvat": "cvat", "gop": "gop"}
EXTRA_NAV = (("cakho", "Ca khó", False), ("hop", "Họp team", True), ("thongke", "Thống kê", True), ("loc", "Lọc dữ liệu", True))


def current_step(store, ctx=None):
    """Bước đợt đang ở, theo step_model (cùng thanh giai đoạn): 'nap' (chưa có đợt), 'ra' (đang rà), 'cvat' (đã đẩy, đang đẩy, job chưa xong hết),
    'gop' (mọi job CVAT xong hoặc đã gộp), 'push' (lần đẩy dừng giữa chừng: về khung Duyệt & Xuất CVAT ở tab Rà soát)."""
    m = step_model(store, ctx)
    if m["warn"]:
        return "push"
    return STEPS[min(m["cur"], len(STEPS) - 1)][0]


def landing_tab(store, ctx=None):
    """Tab mở sẵn khi vào trang (và khi bấm tên đợt đang mở, 'home'): đúng bước đợt đang ở (current_step). Bước 4 là tab Các đợt, trang 'gop'."""
    return GO_TAB[current_step(store, ctx)]


def step_model(store, ctx=None):
    if store is None:
        return dict(cur=0, warn=False, hint="Kéo thả ảnh vào tab <b>Nạp ảnh</b> rồi bấm <b>Upload &amp; Open</b>.")
    p = store.progress()
    ps = dot_anh.read_push(store.run_dir) or {}
    st = ps.get("trang_thai")
    run = html.escape(run_name(store.run_dir))
    if st == "xong" and dot_anh.read_gop(store.run_dir):
        return dict(cur=len(STEPS), warn=False, hint=f"Đợt <b>{run}</b> đã xong và đã lưu gói kết quả: nạp đợt mới ở bước 1.")
    if st == "xong":
        m = cvat_ui.model(store, ctx) if ctx is not None else {}
        if m.get("all_done"):
            return dict(cur=3, warn=False, hint='Mọi job trên CVAT đã xong: bấm <a href="#" class="m28-hint-link" data-go="gop">Merge jobs &amp; Finish</a> ở bước 4.')
        if m.get("total"):
            return dict(cur=2, warn=False, hint=f'Đang làm trên CVAT: <b>{m["done"]}</b>/{m["total"]} job đã xong. Xong hết sẽ tự chuyển sang bước 4.')
        return dict(cur=2, warn=False, hint="Đang làm trên CVAT: sửa nhãn từng job rồi bấm <b>Finish the job</b>; tool tự kiểm và chuyển sang bước 4.")
    if ctx is not None and ctx.push_job.running and ctx.push_job.run == run_name(store.run_dir):
        return dict(cur=2, warn=False, hint="Đang đẩy đợt này lên CVAT…")
    if p["remaining"] == 0:
        if st in ("dang_tao", "da_tao", "da_nhap", "hong"):
            return dict(cur=2, warn=True, hint="Lần đẩy trước dừng giữa chừng: xem khung <b>Duyệt &amp; Xuất CVAT</b>.")
        return dict(cur=1, warn=False, hint='Đã rà hết: bấm <a href="#" class="m28-hint-link" data-go="push">Push to CVAT</a> ở khung Duyệt &amp; Xuất CVAT.')
    return dict(cur=1, warn=False, hint=f'Còn <b>{p["remaining"]}</b>/{p["total"]} mặt chưa rà: Nhận (N) · Sửa nhãn (S) · Bỏ ảnh (B).')


def steps_html(store, ctx=None):
    m = step_model(store, ctx)
    items = []
    for i, (key, label) in enumerate(STEPS):
        cls = "st-done" if i < m["cur"] else ("st-cur" if i == m["cur"] else "st-todo")
        if i == m["cur"] and m["warn"]:
            cls += " st-warn"
        num = icon("check", 12) if i < m["cur"] else str(i + 1)
        inner = f'<i>{num}</i><span>{html.escape(label)}</span>'
        cur = ' aria-current="step"' if i == m["cur"] else ""
        if store is None and key != "nap":                  # chưa mở đợt nào: chỉ bước 1 bấm được; không data-go/data-tab nên không chuyển, không viền
            items.append(f'<span class="m28-step st-todo st-off" aria-disabled="true" title="Chưa mở đợt nào: nạp ảnh ở bước 1 hoặc chọn đợt ở nút đợt">'
                         f'{inner}</span>')
            continue
        items.append(f'<a class="m28-step {cls}" href="#" data-go="{key}" data-tab="{STEP_TAB[key]}"{cur}>{inner}</a>')
    hint = m["hint"]
    if ctx is not None:
        need = [b for b, miss in (('<button type="button" class="cd-link-btn" data-cd-open="reviewer">Set reviewer</button>', chua_dat_ten(ctx)),
                                  ('<button type="button" class="cd-link-btn" data-cd-open="cvat">Set CVAT</button>', not day_cvat.env_state()["ok"])) if miss]
        if need:
            hint = "Trước khi bắt đầu: " + " ".join(need) + " · " + hint
    extra = "".join(f'<a class="m28-nav{" m28-lead-only" if lead else ""}" href="#" data-go="{k}" data-tab="{k}">{html.escape(t)}</a>' for k, t, lead in EXTRA_NAV)
    sep = f'<span class="m28-step-sep">{icon("chevr", 14)}</span>'
    return (f'<nav class="m28-steps" aria-label="Các bước"><div class="m28-steps-row">{sep.join(items)}</div>'
            f'<div class="m28-step-hint"><span class="m28-dot"></span><span>{hint}</span></div>'
            f'<div class="m28-nav-extra">{extra}</div></nav>')


STEPS_JS = r"""
  if (!window.__m28Steps) {
    window.__m28Steps = true;
    document.addEventListener('click', (e) => {
      const a = e.target && e.target.closest ? e.target.closest('.m28-steps [data-go], #progress [data-go], #m28-batch [data-go], #cv-status [data-go], #dot-root [data-go]') : null;
      if (!a) { return; }
      e.preventDefault();
      const go = a.getAttribute('data-go');
      const box = document.querySelector('#m28-go textarea, #m28-go input');
      const btn = document.getElementById('m28-go-btn');
      if (!box || !btn) { return; }
      const proto = box.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(box, go);
      box.dispatchEvent(new Event('input', { bubbles: true }));
      setTimeout(() => btn.click(), 40);
      if (go === 'push') {
        setTimeout(() => { const c = document.getElementById('bot-cvat'); if (c) { c.scrollIntoView({ block: 'center', behavior: 'smooth' }); } }, 450);
      }
    });
    const syncView = () => {
      const t = document.querySelector('#tabs button[role="tab"][aria-selected="true"]');
      let id = t ? (t.getAttribute('data-tab-id') || '') : '';
      if (id === 'dot' && document.querySelector('#dot-root .dot-gop-view')) { id = 'gop'; }     // tab Các đợt đang hiện trang Gộp & kết thúc (bước 4)
      document.querySelectorAll('.m28-steps [data-tab]').forEach((el) => {
        const on = !!id && el.getAttribute('data-tab') === id;
        if (el.classList.contains('st-view') !== on) { el.classList.toggle('st-view', on); }
      });
      const lead = !!document.getElementById('btn-lead') && /: on$/.test(document.getElementById('btn-lead').textContent.trim());
      if (document.body.classList.contains('m28-lead') !== lead) { document.body.classList.toggle('m28-lead', lead); }
    };
    let svQ = false;
    new MutationObserver(() => { if (!svQ) { svQ = true; requestAnimationFrame(() => { svQ = false; syncView(); }); } })
      .observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['aria-selected'] });
    syncView();
    document.addEventListener('click', (e) => {
      const w = document.getElementById('m28-batch');
      if (!w) { return; }
      const t = e.target && e.target.closest ? e.target : null;
      if (t && t.closest('#m28-batch [data-pill-menu]')) { e.preventDefault(); w.classList.toggle('m28-menu-open'); return; }
      const it = t ? t.closest('#m28-batch [data-act]') : null;
      if (it) {
        e.preventDefault();
        if (!it.disabled && window.m28DotAct) {
          if (!document.getElementById('dot-act-go')) {      // Gradio chỉ dựng tab Các đợt lúc chọn nó lần đầu: nút ẩn nhận lệnh chưa có, nên mở tab trước rồi chờ nó dựng xong
            const dot = document.querySelector('#m28-batch [data-go="dot"]');
            if (dot) { dot.click(); }
          }
          window.m28DotAct({ act: it.getAttribute('data-act'), run: it.getAttribute('data-run') || '' }, 20);
        }
      }
      if (w.classList.contains('m28-menu-open')) { w.classList.remove('m28-menu-open'); }
    });
    document.addEventListener('keydown', (e) => {
      const w = document.getElementById('m28-batch');
      if (e.key === 'Escape' && w && w.classList.contains('m28-menu-open')) { w.classList.remove('m28-menu-open'); }
    });
    document.addEventListener('click', (e) => {           // pha bắt (chạy trước Gradio): nhớ đang đứng ở tab nào của Team lead lúc bấm nút, LEAD_SAVE_JS dùng khi tắt
      const b = e.target && e.target.closest ? e.target.closest('#btn-lead') : null;
      if (!b) { return; }
      window.__m28LeadFrom = ['hop', 'thongke', 'loc'].find((k) => { const p = document.getElementById('tab-' + k); return !!p && p.getClientRects().length > 0; }) || '';
    }, true);
  }
"""


def info_html(store, face, status, warn, pts=None):
    lat = store.lat.get(face.name, ("", ""))
    pos = [f.name for f in store.faces].index(face.name) + 1
    rows = [("Tên file", f'<span class="face-name">{html.escape(face.file)}</span>'),
            ("Vị trí", f"{pos}/{len(store.faces)}"),
            ("Trạng thái", _chip(status, lat[1] if status else ""))]
    if face.has_draft:
        pts_fl = fmt_points(face.flags)
        rows.append(("Điểm nghi sai", f"<b>{face.n_flags}/{len(face.flags)}</b>"
                     + (f' · điểm <span class="m28-pts">{html.escape(pts_fl)}</span>' if pts_fl else "")))
        if face.occ is not None:
            pts_occ = fmt_points(face.occ)
            rows.append(("Điểm bị che (occluded)", f"<b>{face.n_occ}/{len(face.occ)}</b>"
                         + (f' · điểm <span class="m28-pts">{html.escape(pts_occ)}</span> (vẽ vòng rỗng)' if pts_occ else "")))
        rows.append(("Gợi ý của máy", html.escape(SUG_VI[face.suggestion])))
        probs = ", ".join(PROBLEMS_VI.get(p, p) for p in face.problems)
        rows.append(("Vấn đề", html.escape(probs) if probs else "không"))
    else:
        why = NO_FACE_VI.get(face.no_face_reason, face.no_face_reason)
        rows.append(("Không có nháp", html.escape(f"{why} ({face.no_face_reason})")))
    body = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    warns = ""
    if not face.has_draft:
        warns += '<div class="m28-warn">Mặt này không có nháp: chỉ chọn Sửa nhãn hoặc Bỏ ảnh (nút Nhận đã khoá). Sửa nhãn mặt này lên CVAT là <b>ảnh trống</b>.</div>'
    if warn:
        warns += f'<div class="m28-warn">{html.escape(warn)}</div>'
    return f'<div class="m28-meta-card"><table class="m28-info">{body}</table>{warns}</div>{_pts_embed(pts)}'


def _msg_html(msg, level):
    if not msg:
        return ""
    return f'<div class="m28-msg m-{level}" role="status">{html.escape(msg)}</div>'


def make_view(store, ses, msg="", level="info"):
    """Mọi thứ UI cần vẽ, tính từ (store, ses). Cập nhật ses["page"] (kẹp) và ses["names"] (tên trên trang)."""
    items = _filtered(store, ses)
    page_items, page, n_pages = page_slice(items, ses["page"], PAGE_SIZE)
    ses["page"], ses["names"] = page, [f.name for f in page_items]
    face = store.by_name[ses["cur"]]
    status = store.status(face.name)
    big, warn, pts = big_view(face, store.run_dir)
    p = store.progress()
    counts = {m: len(filter_faces(store.faces, store.lat, m)) for m, _ in FILTERS}
    cur_i = ses["names"].index(face.name) if face.name in ses["names"] else None
    names_all = [f.name for f in items]
    pos = names_all.index(face.name) if face.name in names_all else None
    fin = bool(store.finished or store.closed)
    incl = pos is not None                       # mặt đang xem nằm trong danh sách đã lọc (N/G/B chỉ bật khi đúng)
    return dict(
        header=header_html(store, ses),
        filter_choices=[(f"{t} ({counts[m]})", m) for m, t in FILTERS], filter_value=ses["mode"],
        gallery=[(thumb_for(f, store.status(f.name), store.run_dir), caption(f, store.status(f.name)))
                 for f in page_items],
        selected=cur_i,
        page_html=(f'<div class="m28-page">Trang <b>{page + 1}</b>/{n_pages}</div>' if items else
                   f'<div class="m28-empty">{html.escape(EMPTY_VI.get(ses["mode"], EMPTY_VI["tat_ca"]))}</div>'),
        page_prev=page > 0 and not fin, page_next=page < n_pages - 1 and not fin,
        big=big, info=info_html(store, face, status, warn, pts), conf=_conf_table_html(store, face),
        nhan_ok=face.has_draft and not fin and incl, tay_ok=not fin and incl, bo_ok=not fin and incl,
        undo_ok=bool(store.undo_stack) and not fin,
        prev_ok=bool(items) and not fin and (pos is None or pos > 0),
        next_ok=bool(items) and not fin and (pos is None or pos < len(items) - 1),
        xong_label="Xong" if p["remaining"] == 0 else f"Xong (còn {p['remaining']} mặt chưa rà)",
        xong_ok=p["remaining"] == 0 and not fin,
        shown=face.name, msg=_msg_html(msg, level))


# ---------- giao diện Gradio ----------
GUIDE_HTML = ('<div class="m28-guide"><b>Nhận</b>: đúng dáng mặt, chỉ cần kéo nhẹ · <b>Sửa nhãn</b>: đảo trái–phải, dồn cục, '
              'lệch cả vùng, quay/che nhiều, nhiều mặt (lên CVAT ở job riêng <b>kèm nháp, mọi điểm đánh dấu low_conf</b>: kiểm kỹ từng điểm, '
              'giữ điểm đúng, sửa điểm sai; mặt không có nháp thì lên ảnh trống) · <b>Bỏ</b>: không mặt, sai mặt, mờ/nhỏ · '
              '<b>Phân vân Nhận/Sửa nhãn → chọn Nhận</b></div>')
KEYS_HTML = ('<div class="m28-keys"><b>Chỉ mở một tab. Chọn lý do (nếu có) trước, rồi mới bấm Sửa nhãn / Bỏ ảnh.</b><br>'
             '<kbd>N</kbd> Nhận · <kbd>S</kbd> Sửa nhãn (G cũng được) · <kbd>B</kbd> Bỏ ảnh · '
             '<kbd>Z</kbd> Undo · <kbd>K</kbd> Ca khó · <kbd>←</kbd> <kbd>→</kbd> Prev/Next · <kbd>0</kbd>–<kbd>8</kbd> chọn lý do '
             '(0 = không)</div>')
def _legend_html():
    """Chú giải ảnh chồng: màu chấm = nhóm (đúng màu label trên CVAT, lấy từ mau_nhom.GROUP_COLOR); chấm viền trắng (cùng cỡ) = low_conf."""
    chips = "".join('<span><i class="dot" style="background:%s"></i>%s</span>' % (mau_nhom.GROUP_COLOR[g], mau_nhom.GROUP_VI[g]) for g in mau_nhom.GROUP_COLOR)
    return ('<div class="m28-legend">' + chips + '<span><i class="dot ring"></i><b>viền trắng = low_conf (nhìn kỹ)</b></span>'
            '<span><i class="dot hollow"></i><b>vòng rỗng = occluded (bị che)</b></span>'
            '<span class="m28-sub">trái/phải theo ảnh</span></div>')


LEGEND_HTML = _legend_html()

CSS = """
/* Màu lấy từ biến của theme Gradio nên chế độ tối không hỏng; màu trạng thái dùng nền trong suốt. */
.gradio-container { max-width: 1560px !important; }
#progress, #pagelbl, #info, #msg, #legend, #guide, #keys, #notes { padding: 0 !important; }
#msg { min-height: 64px; }
#info { min-height: 250px; }
#msg .progress-text, #msg .meta-text-center, #msg .meta-text, #msg .generating, #msg .eta-bar { display: none !important; }
.m28-empty { padding: 28px 12px; text-align: center; font-size: 15px; color: var(--body-text-color-subdued);
  border: 1px dashed var(--border-color-primary); border-radius: 10px; }
/* Dải xanh sau Xong: nằm trong dòng (đầu trang, trên các tab), KHÔNG phủ màn hình, không chặn chuột/phím. */
.m28-done-bar { margin: 0 0 8px; padding: 10px 16px; border-radius: var(--radius-lg); font-size: 15px; font-weight: 700; overflow-wrap: anywhere;
  color: var(--body-text-color); background: color-mix(in srgb, #16a34a 18%, transparent); border: 1px solid #16a34a; border-left-width: 6px; }
/* Lớp phủ chỉ có SAU KHI xác nhận 'Đóng trang rà soát' (trang sắp tắt). */
.m28-closed { position: fixed; inset: 0; z-index: 100002; display: flex; align-items: center; justify-content: center; padding: 12px;
  background: color-mix(in srgb, var(--background-fill-primary) 96%, transparent); }
.m28-closed-box { display: flex; flex-direction: column; gap: 8px; padding: 28px 36px; text-align: center; max-width: 560px;
  background: var(--block-background-fill); border: 2px solid #16a34a; border-radius: 16px; font-size: 17px; }
.m28-closed-box b { font-size: 26px; color: #16a34a; }
#close-row { align-items: center; gap: 8px 14px; flex-wrap: wrap; }
#close-row > * { flex: 0 1 auto; min-width: 0; }
#btn-dong { max-width: 240px; }
#close-msg, #close-closed, #close-body { padding: 0 !important; }
#close-msg:not(:has(.html-container > div > *)), #close-closed:not(:has(.html-container > div > *)) { display: none; }
#close-confirm-title { margin: 0; }
#close-confirm-ok:not(:disabled) { background: #dc2626 !important; border-color: #b91c1c !important; color: #fff !important; }
.m28-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 28px; padding: 10px 16px;
  background: var(--block-background-fill); border: 1px solid var(--border-color-primary);
  border-radius: var(--radius-lg); }
.m28-top { display: flex; align-items: baseline; gap: 4px 14px; flex-wrap: wrap; }
.m28-title { font-size: 20px; font-weight: 800; letter-spacing: -.01em; }
.m28-sub { color: var(--body-text-color-subdued); font-size: 15px; }
.m28-prog { display: flex; align-items: center; gap: 10px 14px; flex: 1 1 460px; flex-wrap: wrap; min-width: 0; }
.m28-count { font-weight: 800; font-size: 17px; white-space: nowrap; }
.m28-bar { flex: 1 1 140px; min-width: 100px; height: 12px; border-radius: 999px; overflow: hidden;
  background: var(--border-color-primary); }
.m28-bar > i { display: block; height: 100%; background: #16a34a; border-radius: 999px; transition: width .25s; }
.m28-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.m28-chip { display: inline-flex; align-items: center; gap: 5px; padding: 2px 11px; border-radius: 999px;
  font-size: 14px; line-height: 20px; border: 1px solid var(--cc, #9ca3af); color: var(--body-text-color);
  background: color-mix(in srgb, var(--cc, #9ca3af) 17%, transparent); white-space: nowrap; }
.m28-chip b { font-weight: 800; }
.m28-head-btns { display: inline-flex; gap: 6px; }
.m28-head-btn { cursor: pointer; padding: 3px 12px; min-height: 30px; font-size: 14px; font-weight: 700; border-radius: 8px; color: var(--body-text-color);
  background: var(--background-fill-secondary); border: 1px solid var(--border-color-primary); }
.m28-head-btn:hover { border-color: #2563eb; }
.m28-head-btn:focus-visible { outline: 3px solid #2563eb; outline-offset: 2px; }
.c-nhan { --cc: #16a34a; } .c-gan_tay { --cc: #d97706; } .c-bo { --cc: #dc2626; } .c-chua { --cc: #9ca3af; }
.m28-note { font-size: 14px; line-height: 1.5; color: var(--body-text-color-subdued); }

#main { gap: 16px; align-items: flex-start; flex-wrap: nowrap; margin-bottom: 12px; }
#left, #center, #side { gap: 10px; }
#ra-bar { align-items: center; gap: 8px 14px; flex-wrap: wrap; margin-bottom: 8px; }
#ra-bar > #filter { flex: 1 1 420px !important; min-width: 0 !important; }
#ra-bar > #pager { flex: 0 1 380px !important; min-width: 0 !important; }
@media (min-width: 1100px) {
  /* Ba cột cao bằng nhau, theo cột giữa: cột phải không tự đòi chiều cao (contain: size), bảng Độ tin cậy co giãn lấp chỗ còn lại;
     cột trái kéo khung Duyệt & Xuất CVAT xuống cho bằng đáy (khi nội dung cột trái dài hơn thì cả hàng theo cột trái). */
  #main { align-items: stretch; }
  #left, #center, #side { align-self: stretch; }
  #left > #bot-cvat { flex: 1 1 auto; }
  #side { contain: size; }
  #side > #conf, #conf > .html-container, #conf > .html-container > div { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }
  #conf .conf-table-wrapper { flex: 1 1 0; min-height: 0; }
  #conf .conf-scroll-box { flex: 1 1 0; min-height: 140px; max-height: none; }
}
@media (max-width: 1099px) {
  #main { flex-wrap: wrap; }
  #center { order: 1; } #side { order: 2; } #left { order: 3; }
}

/* ---------- Khung Duyệt & Xuất CVAT (dưới cột 1) ---------- */
#bot-cvat { width: 100%; }
.m28-card { background: var(--block-background-fill); border: 1px solid var(--border-color-primary);
  border-radius: var(--radius-lg); padding: 14px 16px !important; gap: 10px; display: flex; flex-direction: column; }
.m28-card-title { font-size: 15px; font-weight: 800; color: var(--body-text-color); }
.m28-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }

/* ---------- Thẻ Metadata & Bảng Confidence 4 cột (Cột 3) ---------- */
.m28-meta-card { background: var(--block-background-fill); border: 1px solid var(--border-color-primary);
  border-radius: var(--radius-lg); padding: 10px 14px; margin-bottom: 8px; }
.m28-meta-card .m28-info { margin: 0; font-size: 14px; }
.m28-meta-card .m28-info th { padding: 4px 8px 4px 0; font-size: 13px; }
.m28-meta-card .m28-info td { padding: 4px 0; font-size: 14px; }

.conf-table-wrapper { display: flex; flex-direction: column; gap: 6px; background: var(--block-background-fill);
  border: 1px solid var(--border-color-primary); border-radius: var(--radius-lg); padding: 12px 14px; }
/* Cột 3 là MỘT khung: công tắc trên cùng chọn Độ tin cậy (mặc định) hoặc Thông tin ảnh; khung kia ẩn nhưng vẫn ở trong trang
   (JS đọc tên ảnh ở #info .face-name). Mặt có cảnh báo trong Thông tin ảnh thì nút Thông tin ảnh có chấm vàng. */
#side-tabs, #side-tabs .html-container { padding: 0 !important; }
.side-tabs { display: flex; gap: 4px; padding: 4px; border-radius: 12px; background: var(--background-fill-secondary);
  border: 1px solid var(--border-color-primary); }
.side-tab { flex: 1 1 0; min-width: 0; min-height: 36px; padding: 4px 8px; border: 0; border-radius: 9px; cursor: pointer; background: transparent;
  font-size: 14px; font-weight: 700; color: var(--body-text-color-subdued); display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
.side-tab:hover { color: var(--body-text-color); }
.side-tab[aria-selected="true"] { color: var(--body-text-color); background: color-mix(in srgb, #2563eb 28%, transparent); box-shadow: inset 0 0 0 1px #3b82f6; }
.side-tab:focus-visible { outline: 3px solid #2563eb; outline-offset: 1px; }
.side-tab-warn { display: none; width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; flex: none; }
#side:has(#info .m28-warn) .side-tab[data-side="info"] .side-tab-warn { display: inline-block; }
#side:not(:has(.side-tabs[data-view="info"])) > #info { display: none !important; }
#side:has(.side-tabs[data-view="info"]) > #conf { display: none !important; }
.conf-sub { font-size: 13px; color: var(--body-text-color-subdued); }
.conf-group-cards { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 8px 0; }
.conf-group-card { flex: 1 1 calc(50% - 6px); min-width: 120px; max-width: 100%;
  background: var(--background-fill-secondary); border: 1px solid var(--border-color-primary);
  border-radius: 8px; padding: 6px 8px; cursor: pointer; transition: all .15s ease-in-out;
  user-select: none; box-sizing: border-box; }
.conf-group-card:hover { border-color: color-mix(in srgb, var(--grp-col, #3b82f6) 60%, transparent);
  background: color-mix(in srgb, var(--grp-col, #3b82f6) 8%, var(--background-fill-secondary)); }
.conf-group-card.active { border-color: var(--grp-col, #3b82f6);
  background: color-mix(in srgb, var(--grp-col, #3b82f6) 15%, var(--block-background-fill));
  box-shadow: 0 0 0 1px var(--grp-col, #3b82f6); }
.conf-group-card .card-top { display: flex; align-items: center; gap: 5px; }
.conf-group-card .card-name { font-family: var(--font-mono); font-size: 13px; font-weight: 700;
  color: var(--body-text-color); flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conf-group-card.active .card-name { font-weight: 800; }
.conf-group-card .card-sub { font-size: 13px; color: var(--body-text-color-subdued); margin-top: 2px; padding-left: 13px; }
.conf-group-card .card-warn-badge { font-size: 13px; font-weight: 700; color: #ef4444;
  background: rgba(220, 38, 38, 0.15); border: 1px solid rgba(220, 38, 38, 0.4);
  padding: 0 3px; border-radius: 3px; margin-left: auto; white-space: nowrap; }
.conf-scroll-box { max-height: 320px; overflow-y: auto; border: 1px solid var(--border-color-primary); border-radius: 8px;
  background: var(--background-fill-secondary); }
.conf-table { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
.conf-table thead { position: sticky; top: 0; background: var(--block-background-fill); z-index: 2;
  box-shadow: 0 1px 0 var(--border-color-primary); }
.conf-table th { padding: 6px 6px; white-space: nowrap; font-weight: 700; color: var(--body-text-color-subdued); text-align: left; }
.conf-table td { padding: 5px 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border-bottom: 1px solid color-mix(in srgb, var(--border-color-primary) 40%, transparent); vertical-align: middle; }
.conf-table tr:hover { background: color-mix(in srgb, var(--border-color-primary) 30%, transparent); }
.conf-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; flex-shrink: 0; }
.conf-name-cell { display: inline-flex; align-items: center; white-space: nowrap; max-width: 135px; overflow: hidden; text-overflow: ellipsis; }
.conf-pt-name { font-family: var(--font-mono); font-size: 13px; }
.conf-badge { display: inline-block; font-size: 13px; padding: 1px 5px; border-radius: 4px; font-weight: 600; white-space: nowrap; margin-right: 2px; }
.badge-warn { background: rgba(220, 38, 38, 0.2); color: #ef4444; border: 1px solid rgba(220, 38, 38, 0.4); }
.badge-occ { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); }
.badge-ok { color: var(--body-text-color-subdued); opacity: 0.7; }
.td-score { text-align: right; }
.conf-score { font-family: var(--font-mono); font-weight: 800; font-size: 13px; padding: 1px 6px; border-radius: 4px; }
.score-low { color: #ef4444; background: rgba(220, 38, 38, 0.15); }
.score-mid { color: #f59e0b; background: rgba(245, 158, 11, 0.15); }
.score-high { color: #10b981; background: rgba(16, 185, 129, 0.15); }
.conf-empty { padding: 14px 8px !important; margin-top: 8px; }
.conf-rule { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; font-size: 13px; color: var(--body-text-color-subdued); }
.conf-rule b { color: var(--body-text-color); }
.conf-edit { cursor: pointer; padding: 1px 10px; min-height: 24px; font-size: 13px; font-weight: 700; border-radius: 6px; color: var(--body-text-color);
  background: var(--background-fill-secondary); border: 1px solid var(--border-color-primary); }
.conf-edit:hover { border-color: #2563eb; }
.conf-stale { margin-top: 2px; font-size: 13px; }
.conf-row { cursor: pointer; user-select: none; }
.conf-row:focus-visible { outline: 2px solid #22d3ee; outline-offset: -2px; }
.conf-row.hl, .conf-row.hl:hover { background: color-mix(in srgb, #22d3ee 22%, transparent) !important; box-shadow: inset 3px 0 0 #22d3ee; }
@keyframes m28-rowflash { 0%, 45% { background: color-mix(in srgb, #22d3ee 55%, transparent); } 100% { background: transparent; } }
.conf-row.hl.hl-flash td { animation: m28-rowflash 1.1s ease-out; }
@media (prefers-reduced-motion: reduce) { .conf-row.hl.hl-flash td { animation: none; } }
.m28-hl { position: absolute; left: 0; top: 0; z-index: 2; width: 0; height: 0; pointer-events: none; }
.m28-hl i { position: absolute; left: -17px; top: -17px; width: 34px; height: 34px; box-sizing: border-box; border-radius: 50%;
  border: 3px solid #22d3ee; box-shadow: 0 0 0 2px #0b1220, 0 0 14px 3px rgba(34, 211, 238, .8); animation: m28-hl-pulse 1.1s ease-in-out infinite; }
.m28-hl span { position: absolute; left: 22px; top: -30px; white-space: nowrap; padding: 2px 8px; border-radius: 6px; font: 700 13px var(--font-mono);
  color: #0b1220; background: #22d3ee; box-shadow: 0 0 0 2px #0b1220; }
.m28-hl.m28-hl-left span { left: auto; right: 22px; }
.m28-hl.m28-hl-out { display: none; }
@keyframes m28-hl-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.35); } }
@media (prefers-reduced-motion: reduce) { .m28-hl i { animation: none; } }


#filter { padding: 6px 8px !important; }
#filter .wrap { gap: 4px; flex-wrap: wrap; }
#filter label { padding: 5px 9px; font-size: 13px; white-space: nowrap; }
#filter input[type=radio] { display: none; }
#grid { padding: 0 !important; border: 0 !important; background: transparent !important; }
#grid .gallery-container, #grid .grid-wrap { height: auto !important; min-height: 0 !important; max-height: none !important;
  overflow: visible !important; }
#grid .grid-wrap { padding: 0 !important; }
#grid .grid-container { gap: 8px !important; grid-template-columns: repeat(4, minmax(0, 1fr)) !important; padding: 2px !important; }
#grid .thumbnail-item { border-radius: 8px !important; overflow: hidden; padding: 0 !important;
  border: 0 !important; background: var(--background-fill-secondary); box-shadow: none !important; }
#grid .thumbnail-item img { width: 100% !important; height: 100% !important; object-fit: contain !important; }
#grid .thumbnail-item.selected { outline: none !important; box-shadow: none !important; }
#grid .thumbnail-item.m28-cur { outline: 4px solid #2563eb !important; outline-offset: 1px; z-index: 1; }
#grid .caption-label[data-cap] { text-align: center !important; font-weight: 800 !important; letter-spacing: .01em; }
#grid .caption-label[data-cap="xem"] { background: #b45309 !important; color: #fff !important; }       /* Cần xem: cam đậm, nổi trên ảnh */
#grid .caption-label[data-cap="ok"] { background: #15803d !important; color: #fff !important; }        /* Ổn: xanh lá */
#grid .caption-label[data-cap="khong"] { background: #475569 !important; color: #fff !important; }     /* Không có nháp: xám */
#grid .caption-label { left: 3px !important; right: 3px !important; bottom: 3px !important; width: auto !important;
  max-width: none !important; white-space: normal !important; overflow: hidden; text-align: left !important; font-size: 13px !important;
  display: -webkit-box !important; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow-wrap: anywhere;   /* ảnh nhỏ hẹp: tối đa 2 dòng, không cắt giữa chừng */
  line-height: 1.2 !important; padding: 1px 4px !important; border-radius: 4px !important;
  background: color-mix(in srgb, var(--block-background-fill) 90%, transparent) !important;
  color: var(--body-text-color) !important; }
#pager { align-items: center; gap: 8px; flex-wrap: nowrap; }
#pager button { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; padding: 0 14px !important;
  white-space: nowrap; }
#pager > :nth-child(2) { flex: 1 1 auto !important; }
.m28-page { text-align: center; font-size: 15px; white-space: nowrap; color: var(--body-text-color-subdued); }
.m28-page b { color: var(--body-text-color); }

#big { position: relative; isolation: isolate; overflow: hidden !important; height: min(512px, 52vh, calc(100vw - 48px)) !important; padding: 0 !important; }
#big .image-container, #big .image-frame, #big .upload-container { height: 100% !important; overflow: hidden !important; }
#big img { width: 100% !important; height: 100% !important; object-fit: contain !important; }
#big .image-frame { position: relative !important; }
#big .m28-stage { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible;
  transform-origin: 0 0 !important; transform: translate(var(--zx, 0px), var(--zy, 0px)) scale(var(--zz, 1)); }
#big .m28-svg-overlay { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
#big .m28-svg-overlay line { stroke-linecap: round; stroke-linejoin: round; }
#big .m28-svg-overlay .occ { stroke-dasharray: 4; }
/* Phóng to ảnh lớn: CSS transform trên <img> (lăn chuột, kéo, nút +/-/1:1, nhấp đúp); ảnh gốc không đổi. */
#big img { transform-origin: 0 0 !important; transform: translate(var(--zx, 0px), var(--zy, 0px)) scale(var(--zz, 1));
  cursor: zoom-in; user-select: none; -webkit-user-drag: none; }
#big.m28-panning img { will-change: transform; }
#big.m28-fly img, #big.m28-fly .m28-stage { transition: transform .3s ease-out !important; }
@media (prefers-reduced-motion: reduce) { #big.m28-fly img { transition: none !important; } }
#big.m28-zoomed img { cursor: grab; } #big.m28-panning img { cursor: grabbing; }
.m28-zoom { position: absolute; top: 8px; right: 8px; z-index: 1; opacity: .55; transition: opacity .15s; display: flex; gap: 4px; align-items: center; padding: 3px 4px; border-radius: 8px;
  border: 1px solid var(--border-color-primary); background: color-mix(in srgb, var(--block-background-fill) 82%, transparent); }
#big:not(.m28-hasimg) .m28-zoom, #big:not(.m28-hasimg) .m28-pick, #big:not(.m28-haspts) .m28-pick, #big:not(.m28-hasimg) .m28-help { display: none; }
.m28-help { position: absolute; right: 8px; bottom: 8px; z-index: 1; display: flex; padding: 3px 4px; border-radius: 8px; opacity: .55; transition: opacity .15s;
  border: 1px solid var(--border-color-primary); background: color-mix(in srgb, var(--block-background-fill) 82%, transparent); }
.m28-help:hover, .m28-help:focus-within { opacity: 1; }
.m28-help button { min-width: 30px; height: 28px; padding: 0 6px; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-color-primary); background: var(--button-secondary-background-fill); color: var(--body-text-color); }
.m28-help button:hover { background: var(--button-secondary-background-fill-hover); }
.m28-help svg { display: block; }
.m28-zoom:hover, .m28-zoom:focus-within { opacity: 1; }
.m28-pick { position: absolute; top: 8px; left: 8px; z-index: 1; display: flex; gap: 4px; align-items: center; padding: 3px 4px; border-radius: 8px; opacity: .8;
  transition: opacity .15s; border: 1px solid var(--border-color-primary); background: color-mix(in srgb, var(--block-background-fill) 82%, transparent); }
.m28-pick:hover, .m28-pick:focus-within, #big.m28-picking .m28-pick { opacity: 1; }
.m28-pick button { height: 28px; padding: 0 10px; border-radius: 6px; font-weight: 800; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--border-color-primary); background: var(--button-secondary-background-fill); color: var(--body-text-color); }
.m28-pick button:hover { background: var(--button-secondary-background-fill-hover); }
.m28-pick button[aria-pressed="true"] { background: #0891b2; border-color: #22d3ee; color: #fff; }
.m28-pick-n { min-width: 22px; padding: 0 6px; border-radius: 999px; text-align: center; font-size: 13px; font-weight: 800; color: #0b1220; background: #22d3ee; }
.m28-pick-n[data-n="0"] { display: none; }
.m28-pick button[data-pk="hand"], .m28-pick button[data-pk="toggle"] { min-width: 30px; padding: 0 6px; justify-content: center; }
.m28-pick button svg { flex: none; display: block; }
.m28-pick button[data-pk="clear"] { min-width: 28px; padding: 0 6px; }
.m28-pick:not(.has-sel) button[data-pk="clear"] { display: none; }
#big.m28-zoomed:not(.m28-picking) .m28-stage { cursor: grab; }
#big.m28-picking img, #big.m28-picking .m28-stage { cursor: crosshair !important; }
.m28-pick-box { position: absolute; z-index: 2; pointer-events: none; border: 1.5px dashed #22d3ee; background: rgba(34, 211, 238, .12); border-radius: 2px; }
.m28-pick-box.del { border-color: #f87171; background: rgba(248, 113, 113, .12); }
.m28-zoom button { min-width: 30px; height: 28px; padding: 0 8px; border-radius: 6px; font-weight: 800; cursor: pointer;
  border: 1px solid var(--border-color-primary); background: var(--button-secondary-background-fill); color: var(--body-text-color); }
.m28-zoom button:hover { background: var(--button-secondary-background-fill-hover); }
.m28-zoom-lbl { min-width: 42px; text-align: center; font-size: 13px; color: var(--body-text-color-subdued); }
.m28-zoom-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.m28-legend { display: flex; flex-wrap: wrap; gap: 2px 16px; font-size: 14px; color: var(--body-text-color-subdued); }
.m28-legend .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: -1px; }
.m28-legend .hollow { background: transparent; border: 2px solid #9ca3af; box-shadow: 0 0 0 1px #141414; width: 12px; height: 12px; margin-right: 4px; vertical-align: -3px; }
.m28-legend .ring { background: #9ca3af; border: 2px solid #fff; }

#decide { display: grid !important; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
#decide > * { min-width: 0 !important; }
#decide #btn-cakho { grid-column: 1 / -1; min-height: 40px; }
#decide button { min-height: 64px; font-size: 15px; font-weight: 800; min-width: 0 !important; color: #fff; white-space: normal; overflow-wrap: anywhere;
  line-height: 1.15; padding: 0 6px !important; }                          /* cột giữa hẹp (khoảng 400 px): chữ xuống dòng trong nút thay vì tràn sang nút bên */
#btn-nhan { background: #16a34a !important; border-color: #15803d !important; }
#btn-gantay { background: #d97706 !important; border-color: #b45309 !important; }
#btn-bo { background: #dc2626 !important; border-color: #b91c1c !important; }
#decide button:hover:not(:disabled) { filter: brightness(.92); }
#decide button:disabled, #nav button:disabled { opacity: .4; cursor: not-allowed; }
#reason { padding: 8px 10px !important; }
#reason .wrap { display: grid !important; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
#reason label { padding: 5px 8px; font-size: 14px; line-height: 1.2; min-height: 34px; align-items: center; }
#nav { gap: 10px; flex-wrap: nowrap; }
#nav button { min-width: 0 !important; }
#nav button, #pager button { background: var(--background-fill-secondary) !important; color: var(--body-text-color) !important;
  border: 1px solid var(--border-color-primary) !important; }
#nav button:disabled, #pager button:disabled { opacity: .4; }
#reason [data-testid="block-info"], #reason legend, #reason > label > span, #reason .block-info { background: transparent !important;
  color: var(--body-text-color) !important; font-weight: 700; padding-left: 0 !important; }
#reason label.selected, #reason label:has(input:checked) { background: color-mix(in srgb, #2563eb 16%, transparent) !important;
  border-color: #2563eb !important; color: var(--body-text-color) !important; }
#reason input[type=radio]:checked { accent-color: #2563eb; background-color: #2563eb !important; }
@media (max-width: 600px) {
  #decide, #nav { gap: 6px; }
  #decide button { font-size: 15px; white-space: nowrap; padding: 0 4px !important; }
  #nav button { font-size: 15px; white-space: nowrap; padding: 0 6px !important; }
  #reason .wrap { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

.m28-info { width: 100%; border-collapse: collapse; font-size: 15px; }
.m28-info th { text-align: left; font-weight: 600; color: var(--body-text-color-subdued); width: 1%; white-space: nowrap;
  padding: 6px 12px 6px 0; vertical-align: top; border: 0; background: transparent; }
.m28-info td { padding: 6px 0; vertical-align: top; border: 0; background: transparent; overflow-wrap: anywhere; }
.m28-info tr + tr > * { border-top: 1px solid var(--border-color-primary); }
.m28-info .face-name { font-weight: 800; font-size: 16px; }
.m28-pts { font-family: var(--font-mono); font-size: 13px; }
.m28-warn { margin-top: 8px; padding: 8px 10px; border-radius: 8px; font-size: 14px; color: var(--body-text-color);
  background: color-mix(in srgb, #d97706 16%, transparent); border: 1px solid #d97706; }
.m28-msg { padding: 8px 10px; border-radius: 8px; font-size: 15px; border-left: 5px solid #9ca3af;
  background: var(--background-fill-secondary); }
.m28-msg.m-ok { border-left-color: #16a34a; } .m28-msg.m-warn { border-left-color: #d97706; }
.m28-guide, .m28-keys { font-size: 14px; line-height: 1.5; color: var(--body-text-color-subdued); }
.m28-guide b { color: var(--body-text-color); }
kbd { display: inline-block; min-width: 20px; padding: 0 5px; text-align: center; font: 600 13px var(--font-mono);
  border: 1px solid var(--border-color-primary); border-bottom-width: 2px; border-radius: 5px;
  background: var(--background-fill-secondary); color: var(--body-text-color); }
/* ---------- hai tab: Rà soát / Nạp ảnh ---------- */
#tabs { margin-top: 4px; }
#tabs > .tab-wrapper button, #tabs > .tab-container button { font-size: 15px; font-weight: 700; padding: 6px 16px; }
#tab-ra, #tab-nap { padding: 8px 0 0 !important; }
#tab-nap { max-width: 1120px; margin: 0 auto; width: 100%; gap: 10px; }
#nap-env, #nap-count, #nap-rejected, #nap-msg, #nap-prog, #nap-summary { padding: 0 !important; }
.nap-box { padding: 10px 14px; border-radius: 10px; font-size: 15px; line-height: 1.5; color: var(--body-text-color);
  border: 1px solid var(--bc, #9ca3af); background: color-mix(in srgb, var(--bc, #9ca3af) 14%, transparent); }
.nap-box ul { margin: 6px 0 0 20px; padding: 0; }
.nap-box li { overflow-wrap: anywhere; }
.nap-ok { --bc: #16a34a; } .nap-err { --bc: #dc2626; } .nap-warn { --bc: #d97706; }
#nap-drop { border: 2px dashed var(--border-color-primary) !important; border-radius: 14px; min-height: 170px;
  background: var(--background-fill-secondary); transition: border-color .15s, background .15s; }
#nap-drop:hover, #nap-drop:focus-within { border-color: #16a34a !important;
  background: color-mix(in srgb, #16a34a 8%, var(--background-fill-secondary)); }
#nap-drop [data-testid="upload-text"] { font-size: 0 !important; color: var(--body-text-color); }
#nap-drop [data-testid="upload-text"] .or { display: none; }
#nap-drop [data-testid="upload-text"]::after { content: "Kéo thả ảnh vào đây\\A hoặc bấm để chọn"; white-space: pre; display: block;
  font-size: 20px; font-weight: 700; line-height: 1.5; text-align: center; margin-top: 8px; }
#nap-drop .file-preview, #nap-drop table { font-size: 14px; }
.nap-count { font-size: 15px; color: var(--body-text-color-subdued); display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.nap-count-btns { display: inline-flex; gap: 2px; padding: 2px; border-radius: 8px; border: 1px solid var(--border-color-primary);
  background: var(--block-background-fill); }
.nap-cbtn { width: 30px; height: 28px; display: inline-flex; align-items: center; justify-content: center; border-radius: 6px; cursor: pointer;
  border: 0; background: transparent; color: var(--body-text-color-subdued); }
.nap-cbtn:hover { color: var(--body-text-color); background: var(--button-secondary-background-fill-hover); }
.nap-cbtn[data-nap-clear]:hover { color: #f87171; }
.nap-cbtn:focus-visible { outline: 2px solid #93c5fd; outline-offset: 1px; }
#nap-drop:has(.file-preview-holder) { display: none !important; }      /* đã chọn ảnh: ẩn ô kéo thả, nút thêm / bỏ hết nằm ở dòng đếm (nap_anh.COUNT_BTNS) */
.nap-count b { color: var(--body-text-color); font-size: 17px; }
#nap-list { padding: 0 !important; border: 0 !important; background: transparent !important; }
#nap-list .gallery-container, #nap-list .grid-wrap { height: auto !important; min-height: 0 !important; max-height: 340px !important;
  overflow-y: auto !important; }
#nap-list .grid-container { grid-template-columns: repeat(auto-fill, minmax(150px, 160px)) !important; gap: 8px !important; }
#nap-list .thumbnail-item { height: 160px !important; border-radius: 8px !important; overflow: hidden; padding: 0 !important; border: 0 !important;
  background: var(--background-fill-secondary); box-shadow: none !important; }
#nap-list .thumbnail-item img { width: 100% !important; height: 100% !important; object-fit: contain !important; }
#nap-list .caption-label { left: 3px !important; right: 3px !important; bottom: 3px !important; width: auto !important; max-width: none !important;
  white-space: normal !important; text-align: left !important; font-size: 13px !important; line-height: 1.15 !important;
  padding: 1px 4px !important; border-radius: 4px !important; overflow-wrap: anywhere;
  background: color-mix(in srgb, var(--block-background-fill) 90%, transparent) !important; color: var(--body-text-color) !important; }
#nap-btns { gap: 10px; flex-wrap: wrap; align-items: center; }
#nap-btns button { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; min-height: 42px; padding: 0 22px !important;
  font-size: 15px; font-weight: 800; border-radius: 10px !important; }
#nap-btns #nap-start, #nap-btns #nap-start:not(:disabled) { background: transparent !important; color: #93c5fd !important; border: 1px solid #2563eb !important; }
#nap-btns #nap-start:not(:disabled):hover { background: color-mix(in srgb, #1677ff 16%, transparent) !important; }   /* nút phụ: viền xanh, nút chính Upload & Open tô đặc */
#nap-cancel { margin-left: auto; background: transparent !important; color: #fca5a5 !important; border: 1px solid #7f1d1d !important; }
#nap-cancel:disabled, #nap-retry:disabled { display: none !important; }        /* Cancel chỉ hiện khi prepare đang chạy, Retry khi lỗi / huỷ */
#nap-cancel:disabled + #nap-retry { margin-left: auto; }
#nap-meta { gap: 12px; align-items: stretch; }
#nap-meta textarea, #nap-meta input { font-size: 15px !important; }
.nap-ready { display: flex; align-items: center; gap: 8px; padding-top: 8px !important; padding-bottom: 8px !important; }
.nap-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 0 3px color-mix(in srgb, #22c55e 25%, transparent); flex: none; }
#nap-log-flag { width: auto !important; min-width: 0 !important; flex: none !important; padding: 0 !important; align-self: center; }
#nap-log-flag:not(:has(.nap-flag)) { display: none !important; }
.nap-flag { width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--fc); color: var(--fc); background: color-mix(in srgb, var(--fc) 14%, transparent); }
.nap-flag:hover { background: color-mix(in srgb, var(--fc) 26%, transparent); }
.nap-flag:focus-visible { outline: 2px solid #93c5fd; outline-offset: 1px; }
.nap-flag-warn { --fc: #f59e0b; } .nap-flag-err { --fc: #ef4444; }
#nap-start:not(:disabled), #nap-start-open:not(:disabled) { background: #1677ff !important; border-color: #0f5fd1 !important; color: #fff !important; }
#nap-start:disabled, #nap-start-open:disabled, #nap-retry:disabled, #nap-cancel:disabled { opacity: .45; cursor: not-allowed; }
#nap-retry { background: var(--background-fill-secondary) !important; color: var(--body-text-color) !important;
  border: 1px solid var(--border-color-primary) !important; }
#nap-top { align-items: center; gap: 8px; flex-wrap: nowrap; }
#nap-log, #nap-rejected { padding: 0 !important; }
#nap-rejected .nap-box { max-height: 150px; overflow: auto; }
#nap-drop .file-preview-holder, #nap-drop table.file-preview { display: none !important; }        /* danh sách file trùng với lưới ảnh bên dưới: ẩn */
#nap-list .thumbnail-item { position: relative; }
.nap-x { position: absolute; top: 5px; right: 5px; z-index: 3; width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; font-size: 18px; font-weight: 800; line-height: 1; color: #fff; background: #dc2626; box-shadow: 0 0 0 2px #0b1220; cursor: pointer; }
.nap-x:hover { background: #b91c1c; } .nap-x:focus-visible { outline: 3px solid #93c5fd; outline-offset: 1px; }
#nap-list .thumbnail-item.nap-going { opacity: .35; }
#nap-top > #nap-env { flex: 1 1 auto !important; min-width: 0 !important; }
#nap-top .nap-ready { min-height: 42px; box-sizing: border-box; }
/* Nút Log prepare: nút riêng bên phải khung trạng thái (không nằm đè lên khung), có biểu tượng tài liệu; biểu tượng báo (nếu có) ở sau nút. */
#nap-log-open, #push-log-open { flex: none !important; width: auto !important; min-width: 0 !important; gap: 8px; padding: 0 16px !important;
  min-height: 42px; border-radius: 10px !important; font-size: 14px !important; font-weight: 700 !important;
  background: #0e1626 !important; border: 1px solid #1e2b42 !important; color: #cbd5e1 !important; box-shadow: none !important; }
#nap-log-open:hover, #push-log-open:hover { border-color: #3b82f6 !important; color: #f1f5f9 !important; }
#nap-log-open::before, #push-log-open::before { content: ""; width: 16px; height: 16px; flex: none; background: currentColor;
  -webkit-mask: var(--lg-icon) center / contain no-repeat; mask: var(--lg-icon) center / contain no-repeat; }
#nap-log-open, #push-log-open { --lg-icon: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z'/%3E%3Cpath d='M14 3v5h5M9 13h6M9 17h6'/%3E%3C/svg%3E"); }
.nap-prog { display: flex; flex-direction: column; gap: 6px; padding: 10px 14px; border-radius: 10px;
  background: var(--block-background-fill); border: 1px solid var(--border-color-primary); }
.nap-prog-top { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; font-size: 15px; }
.nap-label { font-weight: 800; font-size: 16px; }
.nap-time { margin-left: auto; font-family: var(--font-mono); color: var(--body-text-color-subdued); }
.nap-prog .m28-bar { flex: none; width: 100%; }
.nap-st-err .m28-bar > i { background: #dc2626; } .nap-st-warn .m28-bar > i { background: #d97706; }
.nap-sum { display: flex; flex-direction: column; gap: 10px; }
.nap-sum-title { font-size: 16px; }
.nap-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.nap-card { display: flex; flex-direction: column; align-items: center; padding: 10px 6px; border-radius: 12px;
  border: 1px solid var(--border-color-primary); background: var(--block-background-fill); }
.nap-card b { font-size: 30px; line-height: 1.1; } .nap-card span { font-size: 14px; color: var(--body-text-color-subdued); text-align: center; }
.nap-note { font-size: 14px; line-height: 1.55; color: var(--body-text-color-subdued); overflow-wrap: anywhere; }
.nap-note code, .nap-cmd { font-family: var(--font-mono); font-size: 13px; }
.nap-cmd { display: block; margin-top: 4px; padding: 6px 10px; border-radius: 8px; background: var(--background-fill-secondary);
  color: var(--body-text-color); user-select: all; }
@media (max-width: 600px) {
  #nap-btns button { flex: 1 1 100% !important; }
  #nap-cancel { margin-left: 0; }
  .nap-cards { grid-template-columns: 1fr; }
  .nap-card { flex-direction: row; justify-content: space-between; padding: 8px 14px; }
  #nap-list .grid-container { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
  #nap-list .thumbnail-item { height: auto !important; aspect-ratio: 1; }
}
"""

PAGE_JS = r"""() => {
  if (window.__m28Keys) { return; }
  window.__m28Keys = true;
  const TEXT = ['text', 'search', 'number', 'email', 'password', 'url', 'tel'];
  const BY_KEY = { n: 'btn-nhan', g: 'btn-gantay', b: 'btn-bo', z: 'btn-undo', k: 'btn-cakho' };
  const BY_CODE = { KeyN: 'btn-nhan', KeyS: 'btn-gantay', KeyG: 'btn-gantay', KeyB: 'btn-bo', KeyZ: 'btn-undo', KeyK: 'btn-cakho' };   // S = Sửa nhãn; G (tên cũ Gán tay) vẫn dùng được
  const DECIDE = '#btn-nhan, #btn-gantay, #btn-bo';
  const press = (id) => { const b = document.getElementById(id); if (b && !b.disabled) { b.click(); } };
  const typing = (t) => {
    if (!t || !t.tagName) { return false; }
    if (t.isContentEditable) { return true; }
    if (t.tagName === 'TEXTAREA' || t.tagName === 'SELECT') { return true; }
    if (t.tagName === 'INPUT') { return TEXT.indexOf((t.getAttribute('type') || 'text').toLowerCase()) >= 0; }
    return false;
  };
  const onDecide = (t) => !!(t && t.closest && t.closest(DECIDE));
  document.addEventListener('keydown', (e) => {
    // Phím tắt chỉ chạy khi tab "Rà soát" đang hiện (tab "Nạp ảnh" có ô gõ tên lượt, ô thả file, nút riêng).
    const mainEl = document.getElementById('main');
    if (!mainEl || mainEl.offsetParent === null) { return; }
    if (document.querySelector('.m28-modal')) { return; }          // hộp xác nhận đang mở: không phím tắt nào ngoài Esc/Tab/Enter của hộp
    if (e.repeat || e.ctrlKey || e.altKey || e.metaKey || typing(e.target)) { return; }
    // Đã đóng (lớp phủ .m28-closed): chặn hết. Sau Xong (dải xanh .m28-done-bar): các phím tắt dưới đây không còn tác dụng ở tab Rà soát
    // (nút đã khoá), còn phím khác (Tab, Enter trên nút Push to CVAT, gõ chữ...) đi qua bình thường.
    if (document.querySelector('.m28-closed')) { e.preventDefault(); return; }
    const locked = !!document.querySelector('.m28-done-bar');
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      if (!locked) { press(e.key === 'ArrowLeft' ? 'btn-prev' : 'btn-next'); }
      return;
    }
    if ((e.key === 'Enter' || e.key === ' ') && onDecide(e.target)) { e.preventDefault(); return; }
    const k = e.key.length === 1 ? e.key.toLowerCase() : '';       // e.code là dự phòng khi bộ gõ/bố cục phím làm e.key lạ
    const id = BY_KEY[k] || BY_CODE[e.code];
    if (id) { e.preventDefault(); if (!locked) { press(id); } return; }
    const m = /^[0-8]$/.test(k) ? [k, k] : /^(?:Digit|Numpad)([0-8])$/.exec(e.code || '');
    if (m && locked) { e.preventDefault(); return; }
    if (m) {
      const radios = document.querySelectorAll('#reason input[type=radio]');
      const r = radios[parseInt(m[1], 10)];
      if (r && !r.disabled) { e.preventDefault(); r.click(); }
    }
  });
  document.addEventListener('keyup', (e) => {
    if (e.key === ' ' && onDecide(e.target)) { e.preventDefault(); }
  });
  // Đánh dấu ảnh nhỏ của mặt đang xem. Gradio bỏ qua selected_index=None khi lưới đổi trang nên để lại viền cũ sai chỗ,
  // vì vậy viền xanh dương tự vẽ bằng lớp m28-cur (CSS ẩn viền .selected của Gradio).
  let queued = false;
  let stripCur = '';
  const mark = () => {
    queued = false;
    const el = document.querySelector('#info .face-name');
    const cur = el ? el.textContent.trim().replace(/\.png$/i, '') : '';
    document.querySelectorAll('#grid .thumbnail-item').forEach((t) => {
      const img = t.querySelector('img');
      const alt = img ? (img.getAttribute('alt') || '') : '';
      const on = !!cur && (alt === cur || alt.indexOf(cur + ' ') === 0);
      t.classList.toggle('m28-cur', on);
      const box = on && cur !== stripCur ? t.closest('.grid-container') : null;
      if (on) { stripCur = cur; }
      if (box && box.scrollWidth > box.clientWidth) {
        const r = t.getBoundingClientRect(), br = box.getBoundingClientRect();
        if (r.left < br.left || r.right > br.right) { box.scrollLeft += (r.left - br.left) - (br.width - r.width) / 2; }
      }
    });
  };

  const applyConfGroup = (targetGrp) => {
    const grp = targetGrp || window._m28_selected_conf_group || 'tat_ca';
    const container = document.getElementById('conf-group-cards');
    if (container && !container.querySelector('.conf-group-card[data-group="' + grp + '"]')) {
      if (grp !== 'tat_ca') { applyConfGroup('tat_ca'); }
      return;
    }
    window._m28_selected_conf_group = grp;
    if (container) {
      container.querySelectorAll('.conf-group-card').forEach((c) => { c.classList.toggle('active', c.getAttribute('data-group') === grp); });
    }
    document.querySelectorAll('.conf-table tbody tr[data-group]').forEach((r) => {
      r.style.display = (grp === 'tat_ca' || r.getAttribute('data-group') === grp) ? '' : 'none';
    });
  };

  document.addEventListener('click', (e) => {
    const card = e.target && e.target.closest ? e.target.closest('.conf-group-card') : null;
    if (card && card.getAttribute('data-group')) { applyConfGroup(card.getAttribute('data-group')); }
  });

  const syncConfCards = () => {
    if (document.getElementById('conf-group-cards')) { applyConfGroup(window._m28_selected_conf_group || 'tat_ca'); }
  };

  new MutationObserver(() => {
    if (!queued) {
      queued = true;
      requestAnimationFrame(() => {
        mark();
        syncConfCards();
      });
    }
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
  mark();
  syncConfCards();
}"""
ZOOM_JS = r"""
  // Phóng to ảnh lớn (#big): lăn chuột phóng/thu tại con trỏ, kéo để dịch, nhấp đúp hoặc nút 1:1 để về cỡ vừa. Chỉ là CSS transform trên <img>
  // (không đụng ảnh gốc, không gửi gì về server); đổi sang mặt khác thì tự về cỡ vừa.
  const Z = { z: 1, x: 0, y: 0, src: '', drag: null };
  const ZMAX = 6;
  // Chọn điểm cho Ca khó: bật "Pick points" (góc trái ảnh lớn) rồi bấm gần một chấm để chọn / bỏ chọn; danh sách tên điểm (theo thứ tự điểm) ghi vào
  // ô ẩn #ck-pts, nút Ca khó (K) điền sẵn vào "Điểm liên quan". Đổi sang mặt khác thì bỏ chọn. Chỉ ở trình duyệt, không ghi gì cho tới khi Save ca khó.
  const PK = { on: false, sel: new Set(), face: '', down: null };
  // Biểu tượng nét (24 × 24, currentColor): bàn tay = kéo ảnh, khung nét đứt + con trỏ = chọn điểm
  const PK_SVG = (d) => '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + '</svg>';
  const PK_HAND = PK_SVG('<path d="M18 11V6a2 2 0 0 0-4 0"/><path d="M14 10V4a2 2 0 0 0-4 0v2"/><path d="M10 10.5V6a2 2 0 0 0-4 0v8"/>'
    + '<path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>');
  const PK_ICON = PK_SVG('<path d="M4 9V5a1 1 0 0 1 1-1h4"/><path d="M15 4h4a1 1 0 0 1 1 1v4"/><path d="M4 15v4a1 1 0 0 0 1 1h4"/>'
    + '<path d="M12.5 12.5l8 3-3.4 1.3-1.3 3.4z"/>');
  const KB_ICON = PK_SVG('<rect width="20" height="16" x="2" y="4" rx="2"/><path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M8 12h.01M12 12h.01M16 12h.01M7 16h10"/>');
  const PK_HIT = 14;                                       // px màn hình: bấm trong bán kính này quanh tâm chấm là trúng chấm gần nhất
  const pkFace = () => { const el = document.querySelector('#info .face-name'); return el ? el.textContent.trim() : ''; };
  const pkPts = () => {
    const a = document.getElementById('m28-pts');
    if (!a || !a.value) { return null; }
    try { return JSON.parse(a.value); } catch (e) { return null; }
  };
  const pkSync = () => {
    const pts = pkPts() || [];
    const names = pts.filter((p) => p.n && PK.sel.has(p.n)).map((p) => p.n);
    const b = bigEl();
    if (b) {
      const t = b.querySelector('.m28-pick [data-pk="toggle"]');
      if (t && t.getAttribute('aria-pressed') !== String(PK.on)) { t.setAttribute('aria-pressed', String(PK.on)); }
      const hd = b.querySelector('.m28-pick [data-pk="hand"]');
      if (hd && hd.getAttribute('aria-pressed') !== String(!PK.on)) { hd.setAttribute('aria-pressed', String(!PK.on)); }
      const bar = b.querySelector('.m28-pick');
      if (bar && bar.classList.contains('has-sel') !== names.length > 0) { bar.classList.toggle('has-sel', names.length > 0); }      // nút ✕ chỉ hiện khi đã chọn điểm
      const n = b.querySelector('.m28-pick-n');
      if (n && n.textContent !== String(names.length)) { n.textContent = String(names.length); n.setAttribute('data-n', String(names.length)); }
      if (b.classList.contains('m28-picking') !== PK.on) { b.classList.toggle('m28-picking', PK.on); }
      const svg = b.querySelector('.m28-svg-overlay');
      if (svg) { svg.__m28Key = ''; }
    }
    const box = document.querySelector('#ck-pts textarea, #ck-pts input');
    const v = names.join(';');
    if (box && box.value !== v) {
      const proto = box.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(box, v);
      box.dispatchEvent(new Event('input', { bubbles: true }));
    }
    zRenderOverlay();
  };
  const confScrollTo = (row) => {                         // cuộn khung bảng Độ tin cậy (không kéo cả trang) để dòng nằm giữa khung, rồi nháy sáng dòng đó
    const box = row.closest('.conf-scroll-box');
    if (box) {
      const rr = row.getBoundingClientRect(), br = box.getBoundingClientRect();
      box.scrollTo({ top: box.scrollTop + rr.top - br.top - (box.clientHeight - rr.height) / 2, behavior: 'smooth' });
      if (br.top + box.clientHeight / 2 > window.innerHeight - 24) {             // khung bảng gần như khuất dưới màn hình: cuộn trang vừa đủ thấy cả khung
        window.scrollBy({ top: Math.min(br.bottom - window.innerHeight + 16, br.top - 16), behavior: 'smooth' });
      }
    }
    row.classList.remove('hl-flash');
    void row.offsetWidth;                                   // chạy lại hiệu ứng khi bấm cùng điểm lần nữa
    row.classList.add('hl-flash');
  };
  const bigEl = () => document.getElementById('big');
  const bigImg = () => { const b = bigEl(); return b ? b.querySelector('img') : null; };
  const zBlocked = () => !!(document.querySelector('.m28-modal') || document.querySelector('.m28-closed'));
  const zApply = () => {
    const b = bigEl();
    if (!b) { return; }
    // Gradio có thể vẽ lại class/style của #big khi cập nhật: ghi lại mỗi lần, nhưng chỉ ghi khi khác để không tự gây thêm thay đổi.
    const setv = (k, v) => { if (b.style.getPropertyValue(k) !== v) { b.style.setProperty(k, v); } };
    setv('--zz', String(Z.z));
    setv('--zx', Z.x + 'px');
    setv('--zy', Z.y + 'px');
    const on = Z.z > 1.001;
    if (b.classList.contains('m28-zoomed') !== on) { b.classList.toggle('m28-zoomed', on); }
    const lbl = b.querySelector('.m28-zoom-lbl');
    const txt = Math.round(Z.z * 100) + '%';
    if (lbl && lbl.textContent !== txt) { lbl.textContent = txt; }
    const sr = b.querySelector('.m28-zoom-sr');          // trình đọc màn hình: báo một lần sau khi thôi lăn, không báo từng nấc
    if (sr) {
      clearTimeout(Z.srT);
      Z.srT = setTimeout(() => {
        const t2 = 'Thu phóng ' + Math.round(Z.z * 100) + '%';
        if (sr.textContent !== t2 && (sr.textContent || Z.z !== 1)) { sr.textContent = t2; }      // mở trang / đổi ảnh ở 100%: không đọc gì
      }, 400);
    }
    zRenderOverlay();
  };
  const zClamp = () => {
    const b = bigEl();
    if (!b) { return; }
    const r = b.getBoundingClientRect();
    Z.x = Math.min(0, Math.max(r.width * (1 - Z.z), Z.x));
    Z.y = Math.min(0, Math.max(r.height * (1 - Z.z), Z.y));
  };
  const zAt = (z2, px, py) => {                       // px, py: toạ độ trong khung #big; điểm dưới con trỏ đứng yên
    z2 = Math.min(ZMAX, Math.max(1, z2));
    const k = z2 / Z.z;
    Z.x = px - (px - Z.x) * k;
    Z.y = py - (py - Z.y) * k;
    Z.z = z2;
    if (Z.z <= 1.001) { Z.z = 1; Z.x = 0; Z.y = 0; }
    zClamp();
    zApply();
  };
  const zReset = () => { Z.z = 1; Z.x = 0; Z.y = 0; zApply(); };
  const M28_EDGES = [[0,1],[1,2],[2,3],[3,4],[5,6],[6,7],[7,8],[8,9],[10,11],[11,12],[12,13],
    [14,15],[15,16],[16,17],[17,18],[18,19],[19,20],[20,21],[21,14],[22,23],[23,24],[24,25],[25,26],
    [26,27],[27,28],[28,29],[29,22],[30,31],[31,32],[32,33],[33,34],[34,35],[35,36],[36,37],[37,38],
    [38,39],[39,40],[40,41],[41,30],[42,43],[43,44],[44,45],[45,46],[46,47],[47,48],[48,49],[49,42]];
  const zEnsure = () => {
    const b = bigEl();
    if (!b) { return; }
    const img = bigImg();
    const src = img ? (img.getAttribute('src') || '') : '';
    if (src !== Z.src) { Z.src = src; if (Z.z !== 1 || Z.x || Z.y) { zReset(); } }
    if (!b.querySelector('.m28-zoom')) {
      const t = document.createElement('div');
      t.className = 'm28-zoom';
      t.innerHTML = '<button type="button" data-z="in" title="Phóng to (hoặc lăn chuột lên)" aria-label="Phóng to ảnh">+</button>'
        + '<button type="button" data-z="out" title="Thu nhỏ (hoặc lăn chuột xuống)" aria-label="Thu nhỏ ảnh">\u2212</button>'
        + '<button type="button" data-z="reset" title="Về cỡ vừa (hoặc nhấp đúp vào ảnh)" aria-label="Về cỡ vừa">1:1</button>'
        + '<span class="m28-zoom-lbl" aria-hidden="true">100%</span>'
        + '<span class="m28-zoom-sr" role="status" aria-live="polite"></span>';
      b.appendChild(t);
    }
    if (!b.querySelector('.m28-help')) {                  // góc phải dưới ảnh lớn: biểu tượng bàn phím mở popup Phím tắt & quy định (CHEAT_JS, phím H)
      const t = document.createElement('div');
      t.className = 'm28-help';
      t.innerHTML = '<button type="button" data-cheat-open title="Phím tắt &amp; quy định (phím H)" aria-label="Phím tắt và quy định (phím H)">' + KB_ICON + '</button>';
      b.appendChild(t);
    }
    if (!b.querySelector('.m28-pick')) {
      const t = document.createElement('div');
      t.className = 'm28-pick';
      t.innerHTML = '<button type="button" data-pk="hand" aria-pressed="true" aria-label="Kéo ảnh" '
        + 'title="Kéo ảnh: giữ chuột trái kéo để dịch ảnh khi đã phóng to; bấm vào một chấm để xem dòng của điểm ở bảng Độ tin cậy">' + PK_HAND + '</button>'
        + '<button type="button" data-pk="toggle" aria-pressed="false" aria-label="Pick points: chọn điểm cho Ca khó" '
        + 'title="Pick points: bấm vào chấm để chọn / bỏ chọn, giữ chuột trái kéo để quét chọn nhiều điểm (Shift + kéo: bỏ chọn). Ca khó (K) lấy các điểm này">'
        + PK_ICON + '<span class="m28-pick-n" data-n="0">0</span></button>'
        + '<button type="button" data-pk="clear" title="Bỏ chọn mọi điểm" aria-label="Bỏ chọn mọi điểm">\u2715</button>';
      b.appendChild(t);
      PK.face = '';
    }
    const face = pkFace();
    if (face !== PK.face) { PK.face = face; if (PK.sel.size) { PK.sel.clear(); } pkSync(); }
    const has = !!(pkPts() || []).length;
    if (b.classList.contains('m28-haspts') !== has) { b.classList.toggle('m28-haspts', has); }
    if (!b.__m28Wheel) {                                  // lăn chuột gắn vào #big (không phải cả trang): cuộn ở chỗ khác không phải chờ
      b.__m28Wheel = true;
      b.addEventListener('wheel', zWheel, { passive: false });
    }
    if (b.classList.contains('m28-hasimg') !== !!img) { b.classList.toggle('m28-hasimg', !!img); }
    zApply();
  };
  function zRenderOverlay() {
    const b = bigEl();
    if (!b) { return; }
    const img = bigImg();
    const parent = img ? img.parentElement : null;
    let stage = parent ? parent.querySelector('.m28-stage') : null;
    const ptsArea = document.getElementById('m28-pts');
    let pts = null;
    if (ptsArea && ptsArea.value) {
      try { pts = JSON.parse(ptsArea.value); } catch (e) { pts = null; }
    }
    if (!pts || !pts.length || !img || !parent) {
      if (stage) { stage.remove(); }
      return;
    }
    const nw = img.naturalWidth, nh = img.naturalHeight;
    const cw = img.clientWidth, ch = img.clientHeight;
    if (!nw || !nh || !cw || !ch) { return; }
    if (!stage) {
      stage = document.createElement('div');
      stage.className = 'm28-stage';
      stage.innerHTML = '<svg class="m28-svg-overlay" xmlns="http://www.w3.org/2000/svg"></svg>';
      parent.appendChild(stage);
    }
    const svg = stage.querySelector('svg');
    if (svg.getAttribute('viewBox') !== '0 0 ' + nw + ' ' + nh) { svg.setAttribute('viewBox', '0 0 ' + nw + ' ' + nh); }
    const k = Math.min(cw / nw, ch / nh) * Z.z;
    // Chấm đường kính 7 px, giữ kích thước khi zoom. Điểm low_conf CÙNG CỠ như trên CVAT (không to hơn, không vòng ngoài): chỉ đổi viền tối thành viền trắng.
    const r = 3.5 / k, sw = 1 / k;
    const key = (img.getAttribute('src') || '') + '|' + ptsArea.value.length + '|' + ptsArea.value.slice(0, 64) + '|' + k.toFixed(4) + '|' + [...PK.sel].join(',');
    if (svg.__m28Key === key) { return; }
    svg.__m28Key = key;
    let h = '<g>';
    for (const [a, c] of M28_EDGES) {
      const p1 = pts[a], p2 = pts[c];
      if (p1 && p2) { h += '<line x1="' + p1.x + '" y1="' + p1.y + '" x2="' + p2.x + '" y2="' + p2.y + '" stroke="' + p1.color + '" stroke-width="' + sw + '" opacity="0.85"/>'; }
    }
    h += '</g><g>';
    for (const p of pts) {
      if (p.occ) {
        h += '<circle class="occ" cx="' + p.x + '" cy="' + p.y + '" r="' + (r * 1.4) + '" fill="none" stroke="' + p.color + '" stroke-width="' + (sw * 1.5) + '"/>';
      } else if (p.low) {
        h += '<circle class="low" cx="' + p.x + '" cy="' + p.y + '" r="' + r + '" fill="' + p.color + '" stroke="#ffffff" stroke-width="' + (sw * 1.6) + '"/>';
      } else {
        h += '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + r + '" fill="' + p.color + '" stroke="#141414" stroke-width="' + sw + '"/>';
      }
    }
    h += '</g><g class="m28-picked">';                     // điểm đã chọn cho Ca khó: vòng xanh ngoài cùng
    for (const p of pts) {
      if (p.n && PK.sel.has(p.n)) {
        h += '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + (9 / k) + '" fill="none" stroke="#0b1220" stroke-width="' + (4.5 / k) + '"/>'
           + '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + (9 / k) + '" fill="none" stroke="#22d3ee" stroke-width="' + (2.5 / k) + '"/>';
      }
    }
    svg.innerHTML = h + '</g>';
  }
  function zWheel(e) {
    const b = bigEl();
    if (!b || !bigImg() || zBlocked() || Math.abs(e.deltaX) > Math.abs(e.deltaY)) { return; }
    const z2 = Math.min(ZMAX, Math.max(1, Z.z * Math.exp(-e.deltaY * 0.0015)));
    if (Math.abs(z2 - Z.z) < 1e-3) { return; }          // đã ở 100% mà lăn xuống (hay 600% mà lăn lên): để trang cuộn bình thường
    e.preventDefault();
    const r = b.getBoundingClientRect();
    zAt(z2, e.clientX - r.left, e.clientY - r.top);
  }
  const zSrcDoi = (ms) => ms.some((m) => {               // ảnh lớn vừa đổi (Nhận/Sửa nhãn/Bỏ, Next): về 100% NGAY, không để mặt mới hiện ở mức phóng cũ
    const t = m.target;
    if (m.type === 'attributes') { return m.attributeName === 'src' && t.closest && t.closest('#big'); }
    return t.closest && t.closest('#big') && Array.from(m.addedNodes).some((n) => n.nodeName === 'IMG' || (n.querySelector && n.querySelector('img')));
  });
  let zQueued = false;
  new MutationObserver((ms) => {
    if (zSrcDoi(ms)) { zEnsure(); return; }
    if (!zQueued) { zQueued = true; setTimeout(() => { zQueued = false; zEnsure(); }, 30); }
  }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'class', 'style'] });
  zEnsure();
  window.addEventListener('resize', () => { if (Z.z > 1) { zClamp(); zApply(); } });
  const zThaKeo = () => {
    if (!Z.drag) { return; }
    Z.drag = null;
    const b = bigEl();
    if (b) { b.classList.remove('m28-panning'); }
  };
  window.addEventListener('blur', zThaKeo);                // chuyển cửa sổ giữa lúc kéo: không kẹt ở chế độ kéo
  document.addEventListener('click', (e) => {
    const btn = e.target && e.target.closest ? e.target.closest('.m28-zoom button[data-z]') : null;
    const b = bigEl();
    if (!btn || !b || zBlocked()) { return; }
    const r = b.getBoundingClientRect();
    const w = btn.getAttribute('data-z');
    if (w === 'reset') { zReset(); } else { zAt(Z.z * (w === 'in' ? 1.5 : 1 / 1.5), r.width / 2, r.height / 2); }
  });
  document.addEventListener('click', (e) => {
    const btn = e.target && e.target.closest ? e.target.closest('.m28-pick button[data-pk]') : null;
    if (btn) {
      e.preventDefault();
      if (zBlocked()) { return; }
      const w = btn.getAttribute('data-pk');
      if (w === 'toggle') { PK.on = !PK.on; } else if (w === 'hand') { PK.on = false; } else { PK.sel.clear(); }
      pkSync();
      return;
    }
    const b = bigEl();
    const img = bigImg();
    if (!b || !img || !img.naturalWidth || !b.contains(e.target) || (e.target.closest && e.target.closest('.m28-zoom, .m28-pick, .m28-help')) || zBlocked()) { return; }
    if (PK.down && Math.hypot(e.clientX - PK.down.x, e.clientY - PK.down.y) > 5) { return; }    // vừa kéo ảnh (đang phóng to): không phải bấm chọn
    const pts = pkPts();
    if (!pts) { return; }
    const r = img.getBoundingClientRect();                  // đã gồm phép phóng / dịch của ảnh
    const s = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight);
    const ox = r.left + (r.width - img.naturalWidth * s) / 2, oy = r.top + (r.height - img.naturalHeight * s) / 2;
    let best = null, bd = PK_HIT;
    for (const p of pts) {
      const d = Math.hypot(ox + p.x * s - e.clientX, oy + p.y * s - e.clientY);
      if (p.n && d < bd) { bd = d; best = p; }
    }
    if (!best) { return; }
    if (!PK.on) {                                          // không ở chế độ chọn: bấm vào chấm thì tô điểm đó và dòng của nó ở bảng Độ tin cậy (cuộn tới)
      let row = document.querySelector('.conf-row[data-pt="' + best.i + '"]');
      if (row && row.style.display === 'none') {           // bảng đang lọc theo nhóm khác: về Tất cả để thấy dòng
        const all = document.querySelector('.conf-group-card[data-group="tat_ca"]');
        if (all) { all.click(); }
        row = document.querySelector('.conf-row[data-pt="' + best.i + '"]');
      }
      if (row) { hlShow(hlOf(row)); confScrollTo(row); }
      return;
    }
    if (PK.sel.has(best.n)) { PK.sel.delete(best.n); } else { PK.sel.add(best.n); }
    pkSync();
  });
  document.addEventListener('mousedown', (e) => {
    PK.down = { x: e.clientX, y: e.clientY };
    const b = bigEl();
    // Pick points bật: giữ chuột trái và kéo để quét chọn (Shift: bỏ chọn); chặn kéo ảnh của chế độ phóng to (pha bắt, trước handler kéo ảnh)
    if (!PK.on || e.button !== 0 || !b || !bigImg() || !b.contains(e.target) || (e.target.closest && e.target.closest('.m28-zoom, .m28-pick, .m28-help')) || zBlocked()) { return; }
    e.preventDefault();
    e.stopPropagation();
    PK.box = { x0: e.clientX, y0: e.clientY, del: e.shiftKey, el: null };
  }, true);
  const pkBoxDraw = (x1, y1) => {
    const b = bigEl();
    if (!PK.box || !b) { return; }
    if (!PK.box.el) { PK.box.el = document.createElement('div'); PK.box.el.className = 'm28-pick-box' + (PK.box.del ? ' del' : ''); b.appendChild(PK.box.el); }
    const r = b.getBoundingClientRect();
    const l = Math.min(PK.box.x0, x1) - r.left, t = Math.min(PK.box.y0, y1) - r.top;
    Object.assign(PK.box.el.style, { left: l + 'px', top: t + 'px', width: Math.abs(x1 - PK.box.x0) + 'px', height: Math.abs(y1 - PK.box.y0) + 'px' });
  };
  document.addEventListener('mousemove', (e) => {
    if (!PK.box) { return; }
    if (!(e.buttons & 1)) { if (PK.box.el) { PK.box.el.remove(); } PK.box = null; return; }
    if (Math.hypot(e.clientX - PK.box.x0, e.clientY - PK.box.y0) > 5) { pkBoxDraw(e.clientX, e.clientY); }
  }, true);
  document.addEventListener('mouseup', (e) => {
    const bx = PK.box;
    if (!bx) { return; }
    PK.box = null;
    if (bx.el) { bx.el.remove(); }
    if (Math.hypot(e.clientX - bx.x0, e.clientY - bx.y0) <= 5) { return; }      // không kéo: để sự kiện click chọn / bỏ chọn từng điểm
    const img = bigImg(), pts = pkPts();
    if (!img || !img.naturalWidth || !pts) { return; }
    const r = img.getBoundingClientRect();
    const s = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight);
    const ox = r.left + (r.width - img.naturalWidth * s) / 2, oy = r.top + (r.height - img.naturalHeight * s) / 2;
    const xa = Math.min(bx.x0, e.clientX), xb = Math.max(bx.x0, e.clientX), ya = Math.min(bx.y0, e.clientY), yb = Math.max(bx.y0, e.clientY);
    for (const p of pts) {
      const x = ox + p.x * s, y = oy + p.y * s;
      if (p.n && x >= xa && x <= xb && y >= ya && y <= yb) { if (bx.del) { PK.sel.delete(p.n); } else { PK.sel.add(p.n); } }
    }
    pkSync();
  }, true);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && PK.on && !zBlocked()) { PK.on = false; pkSync(); }      // Esc: tắt chế độ chọn (giữ các điểm đã chọn)
  });
  document.addEventListener('mousedown', (e) => {
    const b = bigEl();
    if (!b || e.button !== 0 || Z.z <= 1 || !b.contains(e.target) || (e.target.closest && e.target.closest('.m28-zoom, .m28-pick, .m28-help')) || zBlocked()) { return; }
    Z.drag = { cx: e.clientX, cy: e.clientY, x: Z.x, y: Z.y };
    b.classList.add('m28-panning');
    e.preventDefault();
  });
  document.addEventListener('mousemove', (e) => {
    if (!Z.drag) { return; }
    if (!(e.buttons & 1)) { zThaKeo(); return; }        // nút chuột đã nhả ở ngoài cửa sổ
    Z.x = Z.drag.x + e.clientX - Z.drag.cx;
    Z.y = Z.drag.y + e.clientY - Z.drag.cy;
    zClamp();
    zApply();
  });
  document.addEventListener('mouseup', zThaKeo);
  document.addEventListener('dblclick', (e) => {
    const b = bigEl();
    if (!b || !bigImg() || !b.contains(e.target) || (e.target.closest && e.target.closest('.m28-zoom, .m28-pick, .m28-help')) || zBlocked()) { return; }
    if (Z.z > 1) { zReset(); return; }
    const r = b.getBoundingClientRect();
    zAt(3, e.clientX - r.left, e.clientY - r.top);
  });
"""
CAP_JS = r"""
  // Lưới Rà soát: tô màu chú thích gợi ý theo đúng chữ của review_app.caption (Cần xem: cam, Ổn: xanh, Không nháp: xám).
  const capMark = () => {
    document.querySelectorAll('#grid .caption-label').forEach((c) => {
      const t = (c.textContent || '').trim();
      const k = { 'Ổn': 'ok', 'Cần xem': 'xem', 'Không nháp': 'khong' }[t] || '';
      if ((c.getAttribute('data-cap') || '') !== k) { if (k) { c.setAttribute('data-cap', k); } else { c.removeAttribute('data-cap'); } }
    });
  };
  let capQ = false;
  new MutationObserver(() => { if (!capQ) { capQ = true; setTimeout(() => { capQ = false; capMark(); }, 40); } })
    .observe(document.body, { childList: true, subtree: true, characterData: true });
"""
SIDE_TABS_HTML = ('<div class="side-tabs" role="tablist" aria-label="Khung bên phải" data-view="conf">'
                  '<button type="button" role="tab" class="side-tab" data-side="conf" aria-selected="true" aria-controls="conf">Độ tin cậy từng điểm</button>'
                  '<button type="button" role="tab" class="side-tab" data-side="info" aria-selected="false" aria-controls="info">Thông tin ảnh'
                  '<span class="side-tab-warn" title="Có cảnh báo"></span></button></div>')

SIDE_JS = r"""
  // Công tắc cột 3: đổi data-view của thanh công tắc (HTML tĩnh, Gradio không vẽ lại) → CSS ẩn khung kia. Giữ lựa chọn khi sang mặt khác.
  document.addEventListener('click', (e) => {
    const b = e.target && e.target.closest ? e.target.closest('.side-tab') : null;
    if (!b) { return; }
    const bar = b.closest('.side-tabs');
    bar.dataset.view = b.dataset.side;
    bar.querySelectorAll('.side-tab').forEach((x) => x.setAttribute('aria-selected', x === b ? 'true' : 'false'));
  });
"""

CHEAT_JS = r"""
  // Popup Phím tắt & quy định: chỉ ở trình duyệt. Mở thì gắn lớp m28-modal (khoá phím tắt rà, Esc = Close, giữ Tab trong hộp như mọi hộp khác).
  const cheatPop = () => document.getElementById('cheat-pop');
  const cheatSet = (on) => {
    const p = cheatPop();
    if (!p) { return; }
    p.hidden = !on;
    p.classList.toggle('m28-modal', on);
    if (on) { setTimeout(() => { const c = document.getElementById('cheat-pop-cancel'); if (c) { c.focus(); } }, 60); }
  };
  document.addEventListener('click', (e) => {
    const t = e.target && e.target.closest ? e.target : null;
    if (!t) { return; }
    if (t.closest('[data-cheat-open]')) { e.preventDefault(); cheatSet(true); return; }
    if (t.closest('#cheat-pop-cancel') || t.id === 'cheat-pop') { e.preventDefault(); cheatSet(false); }
  });
  document.addEventListener('keydown', (e) => {
    if (e.code !== 'KeyH' || e.ctrlKey || e.metaKey || e.altKey || document.querySelector('.m28-modal')) { return; }
    const el = e.target;
    if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) { return; }
    e.preventDefault();
    cheatSet(true);
  });
"""
NAP_X_JS = r"""
  // Tab Nạp ảnh: nút × ở góc mỗi ảnh nhỏ (#nap-list) bỏ ảnh đó khỏi lần nạp; danh sách file của ô kéo thả đã ẩn (trùng với lưới).
  const napX = () => {
    document.querySelectorAll('#nap-list .thumbnail-item').forEach((t) => {
      if (t.querySelector('.nap-x')) { return; }
      const x = document.createElement('span');          // span (không phải button): ảnh nhỏ của Gradio đã là <button>
      x.className = 'nap-x';
      x.setAttribute('role', 'button');
      x.setAttribute('tabindex', '0');
      x.setAttribute('aria-label', 'Remove image');
      x.title = 'Bỏ ảnh này khỏi lần nạp';
      x.textContent = '\u00d7';
      t.appendChild(x);
    });
  };
  let napQ = false;
  new MutationObserver(() => { if (!napQ) { napQ = true; setTimeout(() => { napQ = false; napX(); }, 60); } })
    .observe(document.body, { childList: true, subtree: true });
  const napRemove = (x) => {
    const cap = x.closest('.thumbnail-item').querySelector('.caption-label');
    const name = cap ? cap.textContent.split(' \u00b7 ')[0].trim() : '';
    const box = document.querySelector('#nap-rm textarea, #nap-rm input');
    if (!name || !box) { return; }
    const proto = box.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(box, name + '|' + Date.now());
    box.dispatchEvent(new Event('input', { bubbles: true }));
    const go = document.getElementById('nap-rm-go');      // ô ẩn không phát sự kiện input của Gradio: bấm nút ẩn như #m28-go, #dot-act-go
    if (go) { setTimeout(() => go.click(), 40); }
    x.closest('.thumbnail-item').classList.add('nap-going');
  };
  document.addEventListener('click', (e) => {                // dòng đếm ảnh: Thêm ảnh / Bỏ hết = bấm hộ nút gốc của ô kéo thả (đang ẩn vì đã có ảnh)
    const c = e.target && e.target.closest ? e.target.closest('.nap-count [data-nap-add], .nap-count [data-nap-clear]') : null;
    if (!c) { return; }
    e.preventDefault();
    const bar = document.querySelector('#nap-drop .icon-button-wrapper');
    const btns = bar ? Array.from(bar.querySelectorAll('button.icon-button')) : [];
    if (c.hasAttribute('data-nap-add')) {
      const inp = bar ? bar.querySelector('input[type="file"]') : null;      // nút upload của Gradio: cộng thêm vào các ảnh đã chọn
      if (inp) { inp.click(); } else if (btns[0]) { btns[0].click(); }
    } else if (btns.length) {
      btns[btns.length - 1].click();                                         // nút Clear: bỏ hết, ô kéo thả hiện lại
    }
  });
  document.addEventListener('click', (e) => {                // biểu tượng cảnh báo / lỗi bên phải nút Log prepare: mở popup Log prepare
    const l = e.target && e.target.closest ? e.target.closest('#nap-log-flag [data-nap-flag]') : null;
    if (!l) { return; }
    e.preventDefault();
    const b = document.getElementById('nap-log-open'); if (b) { b.click(); }
  });
  document.addEventListener('click', (e) => {
    const x = e.target && e.target.closest ? e.target.closest('#nap-list .nap-x') : null;
    if (!x) { return; }
    e.preventDefault(); e.stopPropagation();                 // không để Gradio coi là chọn ảnh
    napRemove(x);
  }, true);
  document.addEventListener('keydown', (e) => {
    const x = e.target && e.target.closest ? e.target.closest('#nap-list .nap-x') : null;
    if (x && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); e.stopPropagation(); napRemove(x); }
  }, true);
"""
HL_JS = r"""
  const HL = { pt: null, raf: 0 };
  const hlFace = () => { const el = document.querySelector('#info .face-name'); return el ? el.textContent.trim().replace(/\.png$/i, '') : ''; };
  const hlClear = () => {
    HL.pt = null;
    if (HL.raf) { cancelAnimationFrame(HL.raf); HL.raf = 0; }
    document.querySelectorAll('#big .m28-hl').forEach((m) => m.remove());
    document.querySelectorAll('.conf-row.hl').forEach((r) => r.classList.remove('hl'));
  };
  const hlDraw = () => {
    HL.raf = 0;
    const pt = HL.pt;
    if (!pt) { return; }
    const b = document.getElementById('big');
    const img = b ? b.querySelector('img') : null;
    if (!b || !img || hlFace() !== pt.face) { hlClear(); return; }
    if (img.naturalWidth) {
      let m = b.querySelector('.m28-hl');
      if (!m) {
        m = document.createElement('div');
        m.className = 'm28-hl';
        m.innerHTML = '<i></i><span></span>';
        b.appendChild(m);
      }
      const r = img.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      const s = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight);
      const x = r.left - br.left + (r.width - img.naturalWidth * s) / 2 + pt.x * s;
      const y = r.top - br.top + (r.height - img.naturalHeight * s) / 2 + pt.y * s;
      const t = 'translate(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px)';
      if (m.style.transform !== t) { m.style.transform = t; }      // chỉ vòng sáng và nhãn: chấm của điểm đã có ở lớp SVG (hoặc ảnh chồng), không vẽ thêm chấm thứ hai
      const lb = m.querySelector('span');
      const txt = '#' + pt.idx + ' ' + pt.name;
      if (lb.textContent !== txt) { lb.textContent = txt; }
      m.classList.toggle('m28-hl-left', x > br.width - 150);
      m.classList.toggle('m28-hl-out', x < 0 || y < 0 || x > br.width || y > br.height);
    }
    document.querySelectorAll('.conf-row[data-pt]').forEach((row) => {
      const on = row.getAttribute('data-pt') === String(pt.idx) && row.getAttribute('data-face') === pt.face;
      if (row.classList.contains('hl') !== on) { row.classList.toggle('hl', on); }
    });
    HL.raf = requestAnimationFrame(hlDraw);
  };
  const hlOf = (row) => ({ face: row.getAttribute('data-face'), idx: parseInt(row.getAttribute('data-pt'), 10), name: row.getAttribute('data-name') || '',
                            x: parseFloat(row.getAttribute('data-x')), y: parseFloat(row.getAttribute('data-y')), col: row.getAttribute('data-col') });
  const hlShow = (pt) => {
    HL.pt = pt;
    if (HL.raf) { cancelAnimationFrame(HL.raf); HL.raf = 0; }
    hlDraw();
  };
  const hlPick = (row) => {
    const pt = hlOf(row);
    if (HL.pt && HL.pt.face === pt.face && HL.pt.idx === pt.idx) { hlClear(); return; }
    hlShow(pt);
  };
  const HL_ZOOM = 3;
  const hlZoom = (row) => {
    const pt = hlOf(row);
    hlShow(pt);
    const b = bigEl();
    const img = bigImg();
    if (!b || !img || !img.naturalWidth || zBlocked() || hlFace() !== pt.face) { return; }
    const r = img.getBoundingClientRect();
    const br = b.getBoundingClientRect();
    const bw = r.width / Z.z, bh = r.height / Z.z;
    const bx = r.left - br.left - Z.x, by = r.top - br.top - Z.y;
    const s0 = Math.min(bw / img.naturalWidth, bh / img.naturalHeight);
    const lx = (bw - img.naturalWidth * s0) / 2 + pt.x * s0;
    const ly = (bh - img.naturalHeight * s0) / 2 + pt.y * s0;
    Z.z = Math.min(ZMAX, Math.max(HL_ZOOM, Z.z));
    Z.x = br.width / 2 - bx - Z.z * lx;
    Z.y = br.height / 2 - by - Z.z * ly;
    zClamp();
    b.classList.add('m28-fly');
    zApply();
    clearTimeout(HL.flyT);
    HL.flyT = setTimeout(() => { const b2 = bigEl(); if (b2) { b2.classList.remove('m28-fly'); } }, 320);
  };
  document.addEventListener('click', (e) => {
    const row = e.target && e.target.closest ? e.target.closest('.conf-row[data-pt]') : null;
    if (row && e.detail < 2) { hlPick(row); }
  });
  document.addEventListener('dblclick', (e) => {
    const row = e.target && e.target.closest ? e.target.closest('.conf-row[data-pt]') : null;
    if (row) { e.preventDefault(); hlZoom(row); }
  });
  document.addEventListener('keydown', (e) => {
    const row = e.target && e.target.closest ? e.target.closest('.conf-row[data-pt]') : null;
    if (row && e.key === 'Enter' && e.shiftKey) { e.preventDefault(); e.stopPropagation(); hlZoom(row); return; }
    if (row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); e.stopPropagation(); hlPick(row); }
    if (e.key === 'Escape' && HL.pt && !document.querySelector('.m28-modal')) { hlClear(); }
  }, true);
"""

# ---------- bản demo công khai (chèn bởi patch_demo.py; chỉ có tác dụng khi M28_PUBLIC_DEMO=1) ----------
_DEMO_MODE = os.environ.get("M28_DEMO_CVAT_MODE", "fake")
_DEMO_BANNER = ("3 đợt mẫu (10, 30, 30 mặt; ảnh YawDD được phép đăng), chọn ở Switch batch. " + (
    "CVAT chạy thật trên CVAT Cloud 2.79 bằng tài khoản demo riêng; người gán được mô phỏng (job tự xong sau vài giây). " if _DEMO_MODE == "real" else
    "CVAT được mô phỏng trong máy chủ demo: không kết nối tới CVAT nào, kể cả CVAT trên máy bạn. ")
    + "Tự đặt lại khi không ai thao tác. Mã nguồn: ")
DEMO_CSS = """
#m28-tools #btn-dong, #btn-dong, #close-row { display: none !important; }
#nap-drop, #nap-count, #nap-list, #nap-meta, #nap-btns { display: none !important; }
a[href*="cvat.mo-phong.demo"] { pointer-events: none; opacity: .45; cursor: not-allowed; }
#m28-demo-banner { position: fixed; right: 12px; bottom: 12px; z-index: 9999; max-width: min(430px, calc(100vw - 24px)); padding: 8px 34px 8px 12px; font-size: 12px !important;
  border-radius: 12px; border: 1px solid #1d4ed8; background: rgba(12, 26, 51, .96); color: #bfdbfe; font: 600 12px/1.4 system-ui, sans-serif;
  box-shadow: 0 10px 30px rgba(0, 0, 0, .45); }
#m28-demo-banner b { color: #fff; } #m28-demo-x { position: absolute; right: 6px; top: 4px; border: 0; background: none; color: #93c5fd; font-size: 18px; cursor: pointer; line-height: 1; } #m28-demo-banner a { color: #93c5fd; }
"""
DEMO_JS = r"""
  if (!document.getElementById('m28-demo-banner')) {
    const d = document.createElement('div'); d.id = 'm28-demo-banner';
    const b = document.createElement('b'); b.textContent = 'Bản demo công khai (tool thật). '; d.appendChild(b);
    d.appendChild(document.createTextNode(@BANNER@));
    const g = document.createElement('a'); g.href = 'https://github.com/lofm2605/m28-landmark-studio-demo'; g.target = '_blank'; g.rel = 'noopener'; g.textContent = 'github.com/lofm2605/m28-landmark-studio-demo';
    d.appendChild(g); d.appendChild(document.createTextNode('.'));
    const x = document.createElement('button'); x.id = 'm28-demo-x'; x.type = 'button'; x.textContent = '×'; x.title = 'Đóng'; x.addEventListener('click', () => d.remove()); d.appendChild(x);
    document.body.appendChild(d);
    const lock = () => document.querySelectorAll('a.cv-btn, a.dot-btn').forEach(a => {
      if (/Open CVAT task/.test(a.textContent) && a.hasAttribute('href')) {
        a.removeAttribute('href'); a.removeAttribute('target'); a.style.pointerEvents = 'none'; a.style.opacity = '.45';
        a.title = 'Bản demo: task không mở được (CVAT mô phỏng hoặc nằm trong tài khoản demo riêng)'; }
    });
    new MutationObserver(lock).observe(document.body, { childList: true, subtree: true }); lock();
  }
""".replace("@BANNER@", json.dumps(_DEMO_BANNER))



class _DemoNoUpload:
    """ASGI: bản demo công khai không nhận file tải lên (không nạp ảnh; chặn việc đổ file rác hay dựng trang tuỳ ý lên tên miền của demo)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST" and scope.get("path", "").rstrip("/").endswith("/upload"):
            await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
            await send({"type": "http.response.body", "body": "Bản demo công khai không nhận file tải lên.".encode("utf-8")})
            return
        await self.app(scope, receive, send)

PAGE_JS = PAGE_JS[:-1] + ZOOM_JS + HL_JS + CAP_JS + CHEAT_JS + SIDE_JS + log_view.JS + ca_kho.CK_VIEW_JS + NAP_X_JS + STEPS_JS + cai_dat_ui.JS_BODY + thong_ke_ui.JS_BODY + dot_ui.JS_BODY + cvat_ui.JS_BODY + DEMO_JS + "}"          # JS của hộp xác nhận, tab Các đợt và đồng hồ chạy một lần, cùng hàm với phím tắt
CSS = CSS + DEMO_CSS + log_view.CSS + dot_ui.CSS + ca_kho.CSS + cai_dat_ui.CSS + dong_ho_ui.CSS + thong_ke_ui.CSS + loc_ui.CSS + cvat_ui.CSS + giao_dien.CSS


def prepare_env(run_dir, environ=None):
    """Đặt biến môi trường an toàn TRƯỚC khi import gradio (Gradio đọc chúng lúc import)."""
    env = os.environ if environ is None else environ
    env["GRADIO_ANALYTICS_ENABLED"] = "False"
    env["GRADIO_TEMP_DIR"] = os.path.abspath(os.path.join(run_dir, "_tmp"))
    env["HF_HUB_OFFLINE"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    for k in ("NO_PROXY", "no_proxy"):          # máy công ty có proxy: không được đưa localhost qua proxy
        have = [x.strip() for x in env.get(k, "").split(",") if x.strip()]
        env[k] = ",".join(have + [h for h in ("localhost", "127.0.0.1") if h not in have])


CHEAT_HTML = (
    '<div id="cheat-pop" class="m28-cheat-pop" hidden><div class="m28-modal-box m28-cheat-box" role="document">'
    '<div class="modal-title" id="cheat-title">Phím tắt &amp; quy định</div>'
    '<div class="m28-cheat-grid">'
    '<section><h4>Quyết định</h4>'
    '<p><b>Nhận (N)</b>: đúng dáng mặt, chỉ cần kéo nhẹ vài điểm.</p>'
    '<p><b>Sửa nhãn (S)</b>: đảo trái–phải (mắt trái nằm ở mắt phải), dồn cục, lệch cả vùng, quay/che nhiều, nhiều mặt '
    '(lên CVAT ở job riêng, điểm có cờ đánh low_conf).</p>'
    '<p><b>Bỏ ảnh (B)</b>: không mặt, sai mặt, quá mờ/nhỏ. Phân vân Nhận / Sửa nhãn thì chọn Nhận.</p>'
    '<p>Chọn <b>lý do</b> (phím <kbd>0</kbd>–<kbd>8</kbd>, <b>Khác</b> nếu không có) TRƯỚC khi bấm Sửa nhãn / Bỏ ảnh.</p></section>'
    '<section><h4>Phím tắt</h4><p class="m28-cheat-keys">'
    '<kbd>N</kbd> Nhận · <kbd>S</kbd> Sửa nhãn (<kbd>G</kbd> cũng được) · <kbd>B</kbd> Bỏ ảnh · <kbd>K</kbd> Ca khó · <kbd>Z</kbd> Undo<br>'
    '<kbd>←</kbd> <kbd>→</kbd> ảnh trước / sau · <kbd>0</kbd>–<kbd>8</kbd> lý do · <kbd>H</kbd> (hoặc biểu tượng bàn phím ở góc phải dưới ảnh lớn) mở bảng này · <kbd>Esc</kbd> đóng hộp, tắt chế độ chọn điểm</p></section>'
    '<section><h4>Ảnh lớn</h4>'
    '<p><b>+ / − / 1:1</b> (góc phải trên): phóng to, thu nhỏ, về cỡ vừa. Lăn chuột để phóng tại con trỏ, kéo để dịch ảnh khi đã phóng, nhấp đúp để phóng / về cỡ vừa.</p>'
    '<p>Góc trái có hai công cụ. <b>Bàn tay</b> (mặc định): kéo để dịch ảnh khi đã phóng, bấm vào một chấm để xem điểm đó ở bảng Độ tin cậy.</p>'
    '<p><b>Pick points</b> (khung nét đứt): bấm vào chấm để chọn / bỏ chọn, hoặc <b>giữ chuột trái và kéo</b> để quét chọn nhiều điểm '
    '(giữ <kbd>Shift</kbd> khi kéo để bỏ chọn); số bên cạnh là số điểm đã chọn, <b>\u2715</b> (chỉ hiện khi đã chọn) bỏ chọn hết. Ca khó (K) tự điền các điểm đã chọn.</p></section>'
    '<section><h4>Bảng độ tin cậy &amp; Ca khó</h4>'
    '<p>Bấm một dòng để tô điểm đó trên ảnh, nhấp đúp để phóng to tới điểm. Thẻ nhóm (Tất cả, mắt trái...) lọc bảng theo nhóm.</p>'
    '<p><b>Ca khó (K)</b>: mở hộp đánh dấu ca khó (loại, điểm liên quan, ghi chú) để đem ra họp nhóm; không đổi quyết định của ảnh.</p></section>'
    '</div><div class="m28-modal-btns"><button type="button" class="m28-cheat-close" id="cheat-pop-cancel">Close</button></div></div></div>')


def _review_tab(gr, demo, store, ctx, header):
    """Tab "Rà soát" (bố cục và sự kiện như trước khi có tab Nạp ảnh; mọi elem_id giữ nguyên). `header` là thanh #progress đặt trên các tab."""

    def apply(v, reset_reason):
        """Đổi mô hình hiển thị thành tuple cập nhật, đúng thứ tự `outs`."""
        return (v["header"],
                gr.update(choices=v["filter_choices"], value=v["filter_value"]),
                gr.update(value=v["gallery"], visible=bool(v["gallery"]),
                  selected_index=-1 if v["selected"] is None else v["selected"]),   # None bị bỏ qua: -1 = không ảnh nào
                v["page_html"], gr.update(interactive=v["page_prev"]), gr.update(interactive=v["page_next"]),
                v["big"], v["info"], v["conf"],
                gr.update(value="") if reset_reason else gr.update(),
                gr.update(interactive=v["nhan_ok"]), gr.update(interactive=v["tay_ok"]), gr.update(interactive=v["bo_ok"]),
                gr.update(interactive=v["undo_ok"]), gr.update(interactive=v["prev_ok"]),
                gr.update(interactive=v["next_ok"]),
                v["shown"], v["msg"])

    ses_state = gr.State(None)
    shown = gr.Textbox(visible="hidden", elem_id="shown")
    with gr.Row(elem_id="main", equal_height=False):
        with gr.Column(scale=3, min_width=320, elem_id="left"):
            flt = gr.Radio(choices=[(t, m) for m, t in FILTERS], value="tat_ca", label="Lọc", show_label=False,
                           elem_id="filter")
            with gr.Row(elem_id="pager"):
                b_pp = gr.Button("‹ Prev page", elem_id="btn-pageprev", size="sm")
                page_lbl = gr.HTML(elem_id="pagelbl", apply_default_css=False)
                b_pn = gr.Button("Next page ›", elem_id="btn-pagenext", size="sm")
            grid = gr.Gallery(show_label=False, allow_preview=False, columns=4, object_fit="contain", buttons=[],
                              elem_id="grid", height="auto")
            with gr.Column(elem_id="bot-cvat", elem_classes=["m28-card"]):
                gr.HTML('<div class="m28-card-head"><span class="m28-card-title">Duyệt &amp; Xuất CVAT</span>'
                        '<button type="button" class="conf-edit" data-cd-open="cvat">CVAT settings</button></div>', apply_default_css=False)
                msg = gr.HTML(elem_id="msg", apply_default_css=False)
                push_hook, _push_refresh, push_outs, push_opts, push_ok = dot_ui.push_panel(gr, demo, store, ctx)
        with gr.Column(scale=4, min_width=380, elem_id="center", elem_classes=["m28-card"]):
            big = gr.Image(type="filepath", interactive=False, buttons=[], elem_id="big",
                           show_label=False)
            with gr.Row(elem_id="decide"):
                b_nhan = gr.Button("Nhận (N)", variant="primary", elem_id="btn-nhan")
                b_tay = gr.Button("Sửa nhãn (S)", elem_id="btn-gantay")
                b_bo = gr.Button("Bỏ ảnh (B)", variant="stop", elem_id="btn-bo")
                b_cakho = gr.Button("Ca khó (K)", elem_id="btn-cakho")                       # nút thứ tư cùng hàng; panel đánh dấu dựng ở ca_kho.mark_panel
            reason = gr.Radio(choices=[(f"{i} · {t}" if c else t, c) for i, (c, t) in enumerate(REASONS)],
                              value="", label="Lý do: chọn TRƯỚC khi bấm Sửa nhãn / Bỏ ảnh (phím 0–8)", elem_id="reason")
            with gr.Row(elem_id="nav"):
                b_prev = gr.Button("← Prev", elem_id="btn-prev")
                b_undo = gr.Button("Undo (Z)", elem_id="btn-undo")
                b_next = gr.Button("Next →", elem_id="btn-next")
            ca_kho.mark_panel(gr, demo, store, ctx, shown, b_cakho)           # nút "Ca khó (K)" và panel đánh dấu (ghi runs/<lượt>/ca_kho.csv)
            gr.HTML(CHEAT_HTML, elem_id="cheat", apply_default_css=False)
        with gr.Column(scale=3, min_width=320, elem_id="side"):
            gr.HTML(SIDE_TABS_HTML, elem_id="side-tabs", apply_default_css=False)
            info = gr.HTML(elem_id="info", apply_default_css=False)
            conf = gr.HTML(elem_id="conf", apply_default_css=False)

    outs = [header, flt, grid, page_lbl, b_pp, b_pn, big, info, conf, reason, b_nhan, b_tay, b_bo, b_undo, b_prev, b_next,
            shown, msg]
    opts = dict(show_progress="hidden", api_visibility="private", concurrency_limit=1, concurrency_id="m28")

    def render(ses, m="", level="info", reset=True):
        v = make_view(store, ses, m, level)
        if level == "warn" and m:
            gr.Warning(m, title="Cảnh báo")
        return (ses,) + apply(v, reset)

    all_outs = [ses_state] + outs

    def on_load():
        return render(new_session(store))

    def on_select(ses, evt: gr.SelectData):
        ses = ensure_session(store, ses)
        m, lv = act_select(store, ses, evt.index)
        return render(ses, m, lv)

    def on_filter(mode, ses):
        ses = ensure_session(store, ses)
        m, lv = act_filter(store, ses, mode)
        return render(ses, m, lv)

    def on_page(delta):
        def h(ses):
            ses = ensure_session(store, ses)
            m, lv = act_page(store, ses, delta)
            return render(ses, m, lv, reset=False)
        return h

    def on_step(delta):
        def h(ses):
            ses = ensure_session(store, ses)
            m, lv = act_step(store, ses, delta)
            return render(ses, m, lv)
        return h

    def on_decide(decision):
        def h(why, sh, ses):
            ses = ensure_session(store, ses)
            m, lv, reset = act_decide(store, ses, decision, why, sh)
            return render(ses, m, lv, reset)
        return h

    def on_undo(sh, ses):
        ses = ensure_session(store, ses)
        m, lv, reset = act_undo(store, ses, sh)
        return render(ses, m, lv, reset)

    def on_reselect(ses):
        """Chọn lại tab Rà soát: vẽ lại (đợt có thể vừa bị xoá/khôi phục ảnh ở tab Các đợt); mặt đang xem bị xoá thì nhảy sang mặt chưa rà kế."""
        ses = ensure_session(store, ses)
        return render(ses, reset=False)

    demo.load(on_load, None, all_outs, **opts)
    grid.select(on_select, [ses_state], all_outs, **opts)
    flt.input(on_filter, [flt, ses_state], all_outs, **opts)
    events = [
        b_pp.click(on_page(-1), [ses_state], all_outs, trigger_mode="multiple", **opts),
        b_pn.click(on_page(1), [ses_state], all_outs, trigger_mode="multiple", **opts),
        b_prev.click(on_step(-1), [ses_state], all_outs, trigger_mode="multiple", **opts),
        b_next.click(on_step(1), [ses_state], all_outs, trigger_mode="multiple", **opts),
        b_nhan.click(on_decide("nhan"), [reason, shown, ses_state], all_outs, **opts),
        b_tay.click(on_decide("gan_tay"), [reason, shown, ses_state], all_outs, **opts),
        b_bo.click(on_decide("bo"), [reason, shown, ses_state], all_outs, **opts),
        b_undo.click(on_undo, [shown, ses_state], all_outs, **opts)]
    for ev in events[4:8]:                      # sau mỗi quyết định/hoàn tác vẽ lại khung Đẩy lên CVAT (còn bao nhiêu mặt chưa rà)
        push_hook(ev)
    return types.SimpleNamespace(on_reselect=on_reselect, ses_state=ses_state, all_outs=all_outs, opts=opts,
                                 push_refresh=_push_refresh, push_outs=push_outs, push_opts=push_opts, events=events, push_ok=push_ok)


NO_RUN_HTML = ('<div class="m28-empty">Chưa có lượt nào: nạp ảnh ở tab <b>Nạp ảnh</b> bằng <b>Upload &amp; Open</b> (hoặc mở đợt ở tab <b>Các đợt</b> → <b>Open batch</b>).</div>')
HEAD_NAP_HTML = ('<div class="m28-head"><div class="m28-head-ic">' + icon("layers", 20) + '</div><div class="m28-head-main"><div class="m28-top">'
                 '<span class="m28-kicker">Chưa chọn đợt rà soát</span></div>'
                 '<div class="m28-sub">Nạp ảnh mới hoặc mở một đợt có sẵn · người rà {rev}</div></div>' + HEAD_BTNS + '</div>')


def head_nap(ctx):
    """Dòng đầu trang khi chưa mở lượt nào. Chưa đặt tên thì nói rõ, không ghi tên tạm P1 như thể đó là tên thật."""
    rev = "<b>chưa đặt tên</b> (bấm Reviewer ở đầu trang)" if chua_dat_ten(ctx) else f"<b>{html.escape(ctx.reviewer)}</b>"
    return HEAD_NAP_HTML.format(rev=rev)


# Chờ trang mới (cùng cổng) dựng xong rồi tải lại: hỏi /config của Gradio, so tiêu đề với lượt mới.
NAP_SWITCH_JS = r"""(title) => {
  if (!title) { return; }
  const t0 = Date.now();
  const giveUp = () => {
    const box = document.getElementById('tab-nap') || document.body;
    const d = document.createElement('div');
    d.className = 'm28-msg m-warn';
    d.textContent = 'Chưa thấy trang mới sau 40 giây. Xem cửa sổ cmd, rồi mở lại ' + location.origin + ' để tải lại.';
    box.appendChild(d);
  };
  const tick = async () => {
    try {
      const r = await fetch('/config', { cache: 'no-store' });
      if (r.ok) {
        const j = await r.json();
        if (j && j.title === title) { location.reload(); return; }
      }
    } catch (err) { /* server cũ đã tắt, server mới chưa lên */ }
    if (Date.now() - t0 > 40000) { giveUp(); return; }
    setTimeout(tick, 500);
  };
  setTimeout(tick, 1000);
}"""


@dataclasses.dataclass
class AppCtx:
    """Phần dùng chung của một lần dựng trang: nơi chạy, người rà, job prepare, đích chuyển lượt.
    run_dir = lượt đang rà (hoặc runs/_nap khi chưa có lượt nào, chế độ --nap)."""
    reviewer: str
    run_dir: str
    nap_only: bool = False
    reviewer_auto: bool = False        # người rà không ghi ở dòng lệnh: chế độ --nap đổi `reviewer` theo tên vừa lưu ở tab Cài đặt (Save name), không phải mở lại trang
    reviewer_mac_dinh: bool = False    # tên hiện tại là tên MẶC ĐỊNH (P1) vì chưa lưu tên nào: Save name thì đồng hồ chưa lưu của tên này chuyển sang tên mới
    ten_cu_mac_dinh: object = None     # tên vừa bị thay bằng Save name (chế độ --nap tự động): after_reviewer chuyển phiên đồng hồ chưa lưu của tên đó rồi đặt lại None
    ten_cu_bo: object = None           # tên cũ có dấu _ (bản trước) bị bỏ khi đọc cài đặt: Save name cũng chuyển phiên đồng hồ chưa lưu của tên đó sang tên mới
    job: object = None
    push_job: object = None            # nap_anh.PushJob: đẩy lên CVAT bằng tiến trình con
    del_job: object = None             # nap_anh.DeleteTaskJob: xoá task trên CVAT bằng tiến trình con
    smoke_job: object = None           # nap_anh.SmokeJob: kiểm tra nhanh CVAT (cvat_smoke.py) bằng tiến trình con
    collect_job: object = None         # nap_anh.CollectJob: gộp job của task CVAT một đợt (nút Merge jobs & Finish) bằng tiến trình con
    gop: object = None                 # yêu cầu Merge jobs & Finish đang dở: dict(run, person, task, was_running, phase, force, ...) (gop_job.py)
    gop_lock: object = dataclasses.field(default=None, repr=False)        # threading.Lock: kết quả job gộp được xử lý đúng một lần dù nhiều tab cùng tick
    push_pending: object = None        # dot_anh.Pending: yêu cầu xác nhận đẩy (mã ngẫu nhiên)
    dot_pending: object = None         # dot_anh.Pending: yêu cầu xác nhận xoá ở tab Các đợt
    switch_to: object = None           # (run_dir, Store) khi chuyển lượt (Upload & Open xong, hoặc Open batch ở tab Các đợt)
    auto_open: object = None           # tên lượt vừa bấm "Upload & Open": chuẩn bị xong thì tự chuyển trang sang lượt đó (một lần)
    dot_trash_after: object = None     # Delete batch có tick xoá luôn task CVAT: dict(run, task, typed); xoá task xong thì chuyển đợt vào thùng rác (dot_ui)
    closing: bool = False              # đã xác nhận "Đóng trang rà soát" (một lần duy nhất cho mọi tab): mọi handler ghi từ chối
    close_lock: object = dataclasses.field(default_factory=threading.Lock, repr=False)
    dong_ho: object = None             # dong_ho.DongHo của thư mục dự án (dong_ho_ui.get_dh); trạng thái nằm trong file nên dựng lại ctx không mất phiên
    dh_started: object = dataclasses.field(default_factory=set, repr=False)      # lượt đã bắt đầu đồng hồ (tự chạy lúc bấm Nạp ảnh)
    dot_rong: dict = dataclasses.field(default_factory=dict, repr=False)
    jobs_job: object = None
    cvat_jobs: dict = dataclasses.field(default_factory=dict, repr=False)
    demo: object = None
    tmp_dir: str = ""
    runs_root: str = ""
    project_root: str = ""
    layout_error: object = None

    def next_reviewer(self):
        """Tên người rà cho LƯỢT MỞ TIẾP THEO (Upload & Open, chuyển đợt): tên mặc định đã lưu ở tab Cài đặt, không có thì tên của trang này.
        `reviewer` của ctx KHÔNG đổi giữa chừng: lượt đang mở vẫn ghi vào triage_<tên cũ>.csv."""
        return cai_dat.get().next_reviewer(self.reviewer)

    def begin_close(self):
        """Đặt cờ đang đóng. True đúng một lần (lần đầu), False nếu đã đóng rồi hoặc đang chuyển lượt: chống bấm hai lần / hai tab."""
        with self.close_lock:
            if self.closing or self.switch_to is not None:
                return False
            self.closing = True
            return True

    def begin_switch(self, target):
        """Đặt đích chuyển lượt (run_dir, Store) nếu chưa đóng/chưa chuyển; False nếu trang đang đóng. Đã chuyển rồi thì giữ đích cũ (True)."""
        with self.close_lock:
            if self.closing:
                return False
            if self.switch_to is None:
                self.switch_to = target
            return True

    def __post_init__(self):
        if self.job is None:
            self.job = nap_anh.PrepareJob()
        if self.push_job is None:
            self.push_job = nap_anh.PushJob()
        if self.del_job is None:
            self.del_job = nap_anh.DeleteTaskJob()
        if self.smoke_job is None:
            self.smoke_job = nap_anh.SmokeJob()
        if self.collect_job is None:
            self.collect_job = nap_anh.CollectJob()
        if self.jobs_job is None:
            self.jobs_job = nap_anh.JobsJob()
        if self.gop_lock is None:
            self.gop_lock = threading.Lock()
        if self.push_pending is None:
            self.push_pending = dot_anh.Pending()
        if self.dot_pending is None:
            self.dot_pending = dot_anh.Pending()
        self.runs_root, self.project_root, self.layout_error = nap_anh.runs_layout(self.run_dir)
        self.tmp_dir = os.environ.get("GRADIO_TEMP_DIR") or os.path.abspath(os.path.join(self.run_dir, "_tmp"))


def _nap_tab(gr, demo, store, ctx):
    """Tab "Nạp ảnh": kéo thả -> kiểm file -> tạo lượt mới -> prepare (tiến trình con) -> tự mở lượt (Upload & Open). Sự kiện dùng concurrency_id
    "nap" / "nap_tick" / "nap_huy", KHÔNG dùng "m28", để rà tiếp được trong lúc prepare chạy."""
    job = ctx.job
    thumb_dir = os.path.join(ctx.tmp_dir, "nap_thumbs")
    env = {"errs": [] if ctx.layout_error else nap_anh.preflight(ctx.project_root)}

    with gr.Row(elem_id="nap-top"):                     # khung "Đủ model và cấu hình" + nút Log prepare ở góc phải (log mở trong popup)
        env_html = gr.HTML(nap_anh.preflight_html(env["errs"], ctx.layout_error), elem_id="nap-env", apply_default_css=False)
        b_log = gr.Button("Log prepare", elem_id="nap-log-open", size="sm")
        log_flag = gr.HTML(elem_id="nap-log-flag", apply_default_css=False)          # biểu tượng cảnh báo / lỗi bên phải nút Log prepare (nap_anh.log_flag_html)
    drop = gr.File(label="Kéo thả ảnh vào đây hoặc bấm để chọn", file_count="multiple", file_types=[".jpg", ".jpeg", ".png"],
                   type="filepath", elem_id="nap-drop", height=220)
    count = gr.HTML(nap_anh.count_html(None), elem_id="nap-count", apply_default_css=False)
    gal = gr.Gallery(show_label=False, allow_preview=False, columns=6, object_fit="contain", buttons=[], elem_id="nap-list",
                     height="auto", visible=False, interactive=False)
    with gr.Row(elem_id="nap-meta"):                   # tên lượt và ghi chú cùng một hàng
        name_tb = gr.Textbox(label="Tên lượt (để trống = tự đặt)", placeholder=nap_anh.next_run_name(ctx.runs_root),
                             max_lines=1, elem_id="nap-name", scale=1, min_width=200)
        note_tb = gr.Textbox(label=f"Ghi chú (không bắt buộc, tối đa {nap_anh.NOTE_MAX} ký tự)", max_length=nap_anh.NOTE_MAX, lines=1,
                             max_lines=4, elem_id="nap-ghichu", placeholder="Ví dụ: ảnh buổi sáng, camera cửa vào", scale=2, min_width=260)
    with gr.Row(elem_id="nap-btns"):
        b_start_open = gr.Button("Upload & Open", variant="primary", elem_id="nap-start-open", interactive=False)
        b_start = gr.Button("Upload & Continue", variant="primary", elem_id="nap-start", interactive=False)
        b_cancel = gr.Button("Cancel", variant="stop", elem_id="nap-cancel", interactive=False)
        b_retry = gr.Button("Retry", elem_id="nap-retry", interactive=False)
    with gr.Column(visible=False, elem_id="nap-cvat", elem_classes=["m28-modal"]) as cvat_modal:        # chưa kết nối CVAT: hỏi rồi chuyển sang tab Cài đặt
        with gr.Column(elem_classes=["m28-modal-box"]):
            cvat_body = gr.HTML(elem_id="nap-cvat-body", apply_default_css=False)
            with gr.Row(elem_classes=["m28-modal-btns"]):
                b_cvat_ok = gr.Button("OK", variant="primary", elem_id="nap-cvat-ok")
                b_cvat_no = gr.Button("Cancel", elem_id="nap-cvat-cancel")
    msg = gr.HTML(elem_id="nap-msg", apply_default_css=False)
    prog = gr.HTML(elem_id="nap-prog", apply_default_css=False)
    with gr.Column(visible=False, elem_id="nap-log-pop", elem_classes=["m28-modal"]) as log_pop:     # prepare lỗi thì tự mở một lần (job_update)
        with gr.Column(elem_classes=["m28-modal-box", "nap-log-box"]):
            gr.HTML('<div class="lg-title-row"><div class="modal-title" id="nap-log-title">Log prepare</div>'
                    '<span class="lg-note">cắt mặt → MediaPipe → 50 điểm → cờ low_conf → ảnh chồng</span></div>', apply_default_css=False)
            rej = gr.HTML(elem_id="nap-rejected", apply_default_css=False)          # ảnh bị loại lúc chọn (trùng trong lần nạp, sai định dạng...)
            log_tb = gr.HTML(log_view.log_html([], "Chưa chạy prepare trong phiên này."), elem_id="nap-log", apply_default_css=False)
            with gr.Row(elem_classes=["m28-modal-btns"]):
                b_log_close = gr.Button("Close", elem_id="nap-log-pop-cancel")
    summary = gr.HTML(elem_id="nap-summary", apply_default_css=False)
    target = gr.Textbox(visible="hidden", elem_id="nap-target")
    rm_tb = gr.Textbox(visible="hidden", elem_id="nap-rm")          # nút × trên ảnh nhỏ (NAP_X_JS): "tên ảnh|mốc", bỏ ảnh đó khỏi lần nạp
    rm_go = gr.Button(visible="hidden", elem_id="nap-rm-go")
    timer = gr.Timer(1.0, active=False)
    plan_state = gr.State(None)

    opts = dict(show_progress="hidden", api_visibility="private", concurrency_limit=1)
    job_outs = [prog, log_tb, summary, b_start_open, b_start, b_cancel, b_retry, timer, log_pop, log_flag]

    def settle(snap):
        run, run_dir = snap.get("run"), snap.get("run_dir")
        if snap.get("state") != "xong" or not run or not run_dir:
            return None
        if run in ctx.dot_rong:
            return ctx.dot_rong[run]
        if not os.path.isfile(os.path.join(run_dir, "flags", "flags.json")):
            return None
        res = nap_anh.read_prepare_result(run_dir, _read_no_face)
        if res["n_queue"] > 0 or res["n_inbox"] == 0:
            return None
        entry, why = None, ""
        try:
            entry = dot_anh.delete_run(ctx.runs_root, run, run, active_run=store.run_dir if store is not None else None)
        except RunError as e:
            why = str(e)
        ctx.dot_rong[run] = nap_anh.empty_run_html(res, entry, why)
        if ctx.auto_open == run:
            ctx.auto_open = None
        return ctx.dot_rong[run]

    def job_update(snap, n_ok):
        """Tuple cập nhật đúng thứ tự job_outs từ ảnh chụp của job."""
        st, run_dir = snap["state"], snap["run_dir"]
        prog_v = nap_anh.job_progress(run_dir, snap["lines"]) if run_dir else None
        res, go_ok, extra = None, False, ""
        gone = settle(snap)
        if gone is not None:
            extra = gone
        elif st == "xong":
            res = nap_anh.read_prepare_result(run_dir, _read_no_face)
            go_ok = res["n_queue"] > 0
            extra = nap_anh.summary_html(res, ctx.reviewer)
            if not go_ok:
                extra += '<div class="nap-box nap-err" role="alert">Lượt này không có mặt nào để rà (xem danh sách không thấy mặt ở trên).</div>'
        elif st in ("loi", "da_huy"):
            extra = nap_anh.failure_html(snap)
        pop = gr.update()
        if st == "loi":                                     # lỗi: mở popup log MỘT lần cho lần chạy đó (đóng rồi thì không tự mở lại khi tải trang)
            key = (snap.get("run"), len(snap["lines"]), snap["lines"][-1] if snap["lines"] else "")
            if env.get("log_auto") != key:
                env["log_auto"] = key
                pop = gr.update(visible=True)
        running = st == "dang_chay"
        usable = not ctx.layout_error and not env["errs"]
        can_start = gr.update(interactive=usable and n_ok > 0 and not running)
        return (nap_anh.progress_html(snap, prog_v) if prog_v else "", log_view.log_html(snap["lines"], "Chưa chạy prepare trong phiên này."),
                extra, can_start, can_start,
                gr.update(interactive=running and not snap.get("cancelling")),
                gr.update(interactive=usable and st in ("loi", "da_huy") and not running),
                gr.Timer(active=running), pop, nap_anh.log_flag_html(env.get("n_rej", 0), snap, res))

    def box(text, level="info"):
        return f'<div class="m28-msg m-{level}" role="status">{html.escape(text)}</div>' if text else ""

    def n_ok_of(plan_st):
        return len(plan_st["plan"]["ok"]) if plan_st else 0

    def on_load(plan_st):
        env["errs"] = [] if ctx.layout_error else nap_anh.preflight(ctx.project_root)
        return ((nap_anh.preflight_html(env["errs"], ctx.layout_error),
                 gr.update(placeholder=nap_anh.next_run_name(ctx.runs_root))) + job_update(job.snapshot(), n_ok_of(plan_st)))

    def paths_of(files):
        if not files:
            return []
        return [f if isinstance(f, str) else getattr(f, "name", str(f)) for f in (files if isinstance(files, list) else [files])]

    def plan_for(files, plan_st):
        paths = tuple(paths_of(files))
        if plan_st and plan_st.get("key") == paths:
            return plan_st
        return dict(key=paths, plan=nap_anh.plan_upload(list(paths)))

    def on_files(files, plan_st):
        plan_st = plan_for(files, plan_st) if files else None
        plan = plan_st["plan"] if plan_st else None
        items = nap_anh.gallery_items(plan, thumb_dir)
        usable = not ctx.layout_error and not env["errs"]
        can_start = gr.update(interactive=usable and bool(plan and plan["ok"]) and not job.running)
        env["n_rej"] = len(plan["rejected"]) if plan else 0
        snap = job.snapshot()
        res = nap_anh.read_prepare_result(snap["run_dir"], _read_no_face) if snap["state"] == "xong" and snap.get("run_dir") else None
        return (plan_st, gr.update(value=items, visible=bool(items)), nap_anh.rejected_html(plan), nap_anh.count_html(plan), can_start, can_start,
                nap_anh.log_flag_html(env["n_rej"], snap, res))

    def on_remove(raw, files, plan_st):
        """Nút × trên ảnh nhỏ của lưới #nap-list (danh sách file của ô kéo thả đã ẩn): bỏ ảnh có tên mới đó khỏi các file đã chọn."""
        name = (raw or "").split("|", 1)[0]
        cur = plan_for(files, plan_st) if files else None
        src = next((it["src"] for it in (cur["plan"]["ok"] if cur else []) if nap_anh.new_name(it) == name), None)
        if src is None:
            return (gr.update(),) + on_files(files, plan_st)
        left = [x for x in paths_of(files) if x != src]
        return (gr.update(value=left or None),) + on_files(left, None)

    def cvat_thieu_html(thieu_ten, thieu_cvat):
        """Nội dung hộp "chưa đủ cài đặt" của tab Nạp ảnh: chưa đặt tên người rà và/hoặc chưa kết nối CVAT (thiếu link, token, hay link sai); bấm OK sang tab Cài đặt.
        Không in giá trị token."""
        muc = []
        if thieu_ten:
            muc.append(f"Bạn chưa đặt <b>tên người rà</b> (đang là tên mặc định {html.escape(ctx.reviewer)}): gõ tên của bạn ở mục Người rà rồi bấm <b>Save name</b>. "
                       "Tên đi vào file kết quả và file nhãn gộp; mọi người cùng để mặc định thì thống kê gộp họ thành một người.")
        if thieu_cvat:
            e = cai_dat.cvat_env()
            cv = day_cvat.env_state()
            thieu = [t for t, v in (("link CVAT (CVAT_URL, ví dụ http://localhost:8080)", e["url"]), ("token CVAT (Personal Access Token)", e["token"])) if not v]
            muc.append(html.escape(("Bạn đang thiếu " + " và ".join(thieu) + ".") if thieu else (cv["reason"] or "Cài đặt CVAT chưa hợp lệ.")))
        tieu = "Chưa đặt tên người rà" if thieu_ten and not thieu_cvat else ("Chưa kết nối CVAT" if not thieu_ten else "Chưa đặt tên người rà và chưa kết nối CVAT")
        return (f'<div class="modal-title" id="nap-cvat-title">{tieu}</div>'
                + "".join(f'<div class="nap-box nap-warn" role="alert">{m}</div>' for m in muc)
                + '<div class="nap-note">Cần điền trước khi nạp ảnh. Bấm <b>OK</b> để mở hộp điền ngay tại đây, bấm <b>Cancel</b> để đóng. Chưa nạp ảnh nào.</div>')

    def start(files, name, note, plan_st, open_after):
        """Bọc _start: chưa đặt tên người rà (đang là tên mặc định) hoặc chưa có link/token CVAT thì KHÔNG nạp, mở hộp OK / Cancel (OK sang tab Cài đặt).
        Đủ rồi thì chạy _start như cũ."""
        thieu_ten, thieu_cvat = chua_dat_ten(ctx), not day_cvat.env_state()["ok"]
        if not ctx.closing and (thieu_ten or thieu_cvat):
            return ((gr.update(), plan_st, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
                    + job_update(job.snapshot(), n_ok_of(plan_st)) + (gr.update(visible=True), cvat_thieu_html(thieu_ten, thieu_cvat)))
        return _start(files, name, note, plan_st, open_after) + (gr.update(), gr.update())

    def _start(files, name, note, plan_st, open_after):
        """Chung cho Upload & Continue (open_after=False) và Upload & Open (True: chuẩn bị xong thì tự mở trang rà soát, xem on_auto_open)."""
        def refuse(text):
            gr.Warning(text, title="Chưa bắt đầu được")
            return ((gr.update(), plan_st, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), box(text, "warn"))
                    + job_update(job.snapshot(), n_ok_of(plan_st)))
        if ctx.closing:
            return refuse(nap_anh.CLOSING_MSG)
        if job.running:
            return refuse(f"Đang chuẩn bị lượt {job.run}: chờ xong hoặc bấm Cancel.")
        if ctx.layout_error:
            return refuse(ctx.layout_error)
        if open_after:                                                  # Upload & Open sẽ chuyển trang (ctx mới): yêu cầu Merge jobs & Finish còn dở thì mất
            why = gop_job.block_reason(ctx, dong_ho_ui.get_dh(ctx), "bấm Upload & Open (hoặc bấm Upload & Continue: không chuyển trang)",
                                       again="Bấm Upload & Open lại.")
            if why:
                return refuse(why)
        env["errs"] = nap_anh.preflight(ctx.project_root)
        if env["errs"]:
            return refuse("Thiếu model hoặc cấu hình, xem khung đỏ ở đầu tab: " + env["errs"][0])
        try:
            plan_st = plan_for(files, plan_st)
            run = nap_anh.check_run_name(name, ctx.runs_root) if (name or "").strip() else nap_anh.next_run_name(ctx.runs_root)
            nap_anh.stage_upload(ctx.runs_root, run, plan_st["plan"], cleanup_root=ctx.tmp_dir, note=note, reviewer=ctx.reviewer)
            job.start(run, ctx.runs_root, ctx.project_root)
        except RunError as e:
            return refuse(str(e))
        ctx.auto_open = run if open_after else None
        env["n_rej"] = 0                                                # ảnh đã chọn được nạp: bỏ cảnh báo "ảnh bị loại" của lần chọn đó
        text = (f"Đã nạp {len(plan_st['plan']['ok'])} ảnh vào {os.path.join('runs', run, 'inbox')} và bắt đầu prepare (tiến độ ở dưới)"   # lời này không đổi khi prepare xong: không ghi "đang chạy"
                + (": xong thì trang tự mở rà soát lượt này." if open_after else "."))
        return ((gr.update(value=None), None, gr.update(value=[], visible=False), "", nap_anh.count_html(None),
                 gr.update(value="", placeholder=nap_anh.next_run_name(ctx.runs_root)), gr.update(value=""), box(text, "ok"))
                + job_update(job.snapshot(), 0))

    def on_start(files, name, note, plan_st):
        return start(files, name, note, plan_st, False)

    def on_start_open(files, name, note, plan_st):
        return start(files, name, note, plan_st, True)

    def on_retry(plan_st):
        def refuse(text):
            gr.Warning(text, title="Chưa chạy lại được")
            return (box(text, "warn"),) + job_update(job.snapshot(), n_ok_of(plan_st))
        if ctx.closing:
            return refuse(nap_anh.CLOSING_MSG)
        if job.running:
            return refuse(f"Đang chuẩn bị lượt {job.run}: chờ xong hoặc bấm Cancel.")
        if job.state not in ("loi", "da_huy") or not job.run:
            return refuse("Chưa có lượt nào bị lỗi hoặc bị huỷ để thử lại.")
        env["errs"] = nap_anh.preflight(ctx.project_root)
        if env["errs"]:
            return refuse("Thiếu model hoặc cấu hình, xem khung đỏ ở đầu tab: " + env["errs"][0])
        try:
            job.start(job.run, ctx.runs_root, ctx.project_root)
        except RunError as e:
            return refuse(str(e))
        return (box(f"Chạy lại lượt {job.run} (bước đã xong được bỏ qua).", "ok"),) + job_update(job.snapshot(), n_ok_of(plan_st))

    def on_tick(plan_st):
        return job_update(job.snapshot(), n_ok_of(plan_st))

    def on_cancel(plan_st):
        job.cancel()
        ctx.auto_open = None
        return (box("Đã huỷ prepare." if job.state == "da_huy" else "", "warn"),) + job_update(job.snapshot(), n_ok_of(plan_st))

    def on_go(plan_st):
        def refuse(text):
            gr.Warning(text, title="Chưa chuyển được")
            return box(text, "warn"), ""
        if ctx.closing:
            return refuse(nap_anh.CLOSING_MSG)
        if ctx.switch_to is not None:
            return box("Đang chuyển sang lượt mới…", "ok"), "Rà soát M28 · " + run_name(ctx.switch_to[0])
        snap = job.snapshot()
        if ctx.push_job.running or ctx.del_job.running:
            busy = ctx.push_job if ctx.push_job.running else ctx.del_job
            return refuse(f"Đang làm việc với CVAT cho lượt {busy.run}: chờ xong rồi chuyển lượt.")
        if ctx.smoke_job.running:
            return refuse("Đang chạy kiểm tra nhanh CVAT (popup CVAT): chờ xong rồi chuyển lượt.")
        later = f"Mở lượt {snap['run']} ở tab Các đợt → Open batch." if snap.get("run") else ""
        if ctx.collect_job.running:
            return refuse(f"Đang gộp job CVAT của lượt {ctx.collect_job.run} (tab Các đợt): chờ xong hoặc bấm Cancel ở khung gộp job của tab Các đợt "
                          f"rồi mới chuyển lượt. {later}".strip())
        why = gop_job.block_reason(ctx, dong_ho_ui.get_dh(ctx), "chuyển lượt", again=later)
        if why:                                                         # chuyển lượt dựng ctx mới: yêu cầu Merge jobs & Finish còn dở (hộp Merge anyway / Cancel) sẽ mất
            return refuse(why if ctx.gop is None else f"{why} {later}".strip())
        if snap["state"] == "dang_chay":
            return refuse(f"Đang chuẩn bị lượt {snap['run']}: chờ xong hoặc bấm Cancel (tab Nạp ảnh).")
        if snap["state"] != "xong":
            return refuse("Chưa chuẩn bị xong lượt nào: bấm Upload & Open hoặc Upload & Continue (hoặc Retry) và chờ xong.")
        res = nap_anh.read_prepare_result(snap["run_dir"], _read_no_face)
        if not res["n_queue"]:
            return refuse("Lượt này không có mặt nào để rà.")
        try:
            new_store = Store(snap["run_dir"], ctx.next_reviewer())    # tên người rà cho lượt kế tiếp (tab Cài đặt); dựng TRƯỚC: lỗi thì báo ở đây
        except RunError as e:
            return refuse(str(e))
        if not ctx.begin_switch((snap["run_dir"], new_store)):
            return refuse(nap_anh.CLOSING_MSG)
        threading.Timer(0.8, lambda: demo.close(verbose=False)).start()
        return box(f"Đang chuyển sang lượt {snap['run']}: trang mất kết nối 1–3 giây rồi tự tải lại.", "ok"), "Rà soát M28 · " + snap["run"]

    def on_auto_open(plan_st):
        """Chạy mỗi nhịp của đồng hồ: lượt vừa bấm Upload & Open chuẩn bị xong thì chuyển trang sang lượt đó (on_go: mọi kiểm tra vẫn nguyên). Một lần duy nhất;
        lỗi, huỷ hoặc không có mặt nào để rà thì thôi (mở tay ở tab Các đợt → Open batch khi cần)."""
        snap = job.snapshot()
        if settle(snap) is not None:
            ctx.auto_open = None
            return gr.skip(), ""
        act = nap_anh.auto_open_action(ctx.auto_open, snap)
        if act in ("none", "wait"):
            return gr.skip(), ""
        ctx.auto_open = None
        return on_go(plan_st) if act == "go" else (gr.skip(), "")

    start_outs = [drop, plan_state, gal, rej, count, name_tb, note_tb, msg] + job_outs + [cvat_modal, cvat_body]
    nap = dict(opts, concurrency_id="nap")
    nap_load = (on_load, [plan_state], [env_html, name_tb] + job_outs, dict(opts, concurrency_id="nap"))
    demo.load(nap_load[0], nap_load[1], nap_load[2], **nap_load[3])
    drop.change(on_files, [drop, plan_state], [plan_state, gal, rej, count, b_start_open, b_start, log_flag], **nap)
    rm_go.click(on_remove, [rm_tb, drop, plan_state], [drop, plan_state, gal, rej, count, b_start_open, b_start, log_flag], **nap)
    b_start.click(on_start, [drop, name_tb, note_tb, plan_state], start_outs, **nap)
    b_start_open.click(on_start_open, [drop, name_tb, note_tb, plan_state], start_outs, **nap)
    hide_cvat = gr.update(visible=False)
    b_cvat_no.click(lambda: hide_cvat, None, cvat_modal, **dict(opts, concurrency_id="nap_cvat"))
    b_cvat_ok.click(lambda: hide_cvat, None, cvat_modal, **dict(opts, concurrency_id="nap_cvat"))
    ctx.nap_cvat_ok = b_cvat_ok                                        # build_ui nối thêm: chuyển sang tab Cài đặt (server) rồi đưa con trỏ vào ô còn thiếu
    b_retry.click(on_retry, [plan_state], [msg] + job_outs, **nap)
    b_cancel.click(on_cancel, [plan_state], [msg] + job_outs, **dict(opts, concurrency_id="nap_huy"))
    timer.tick(on_tick, [plan_state], job_outs, **dict(opts, concurrency_id="nap_tick"))
    b_log.click(lambda: gr.update(visible=True), None, log_pop, **dict(opts, concurrency_id="nap_log"))
    b_log_close.click(lambda: gr.update(visible=False), None, log_pop, **dict(opts, concurrency_id="nap_log"))
    timer.tick(on_auto_open, [plan_state], [msg, target], **dict(opts, concurrency_id="nap_tick")).then(None, [target], None, js=NAP_SWITCH_JS)
    return nap_load                         # build_ui gọi lại khi chọn tab Nạp ảnh: model/cấu hình vừa cài ở tab Cài đặt có hiệu lực ngay


def _close_bar(gr, demo, store, ctx):
    """Hàng 'Close page' (đứng giữa thanh #progress và các tab nên thấy ở mọi tab, cả chế độ --nap) + hộp xác nhận + lớp phủ 'đã đóng'.
    Đây là chỗ DUY NHẤT tắt server (ngoài Ctrl+C và chuyển lượt): bấm nút -> kiểm việc đang chạy -> hộp xác nhận -> kiểm lại ->
    đặt cờ ctx.closing (một lần) -> lớp phủ -> demo.close() sau ~1 giây để phản hồi kịp tới trình duyệt."""
    with gr.Row(elem_id="close-row"):
        b_dong = gr.Button("Close page", elem_id="btn-dong", size="sm")
        msg = gr.HTML(elem_id="close-msg", apply_default_css=False)
    closed = gr.HTML(elem_id="close-closed", apply_default_css=False)
    with gr.Column(visible=False, elem_id="close-confirm", elem_classes=["m28-modal"]) as modal:
        with gr.Column(elem_classes=["m28-modal-box"]):
            body = gr.HTML(elem_id="close-body", apply_default_css=False)
            with gr.Row(elem_classes=["m28-modal-btns"]):
                b_ok = gr.Button("Close page", variant="stop", elem_id="close-confirm-ok")
                b_no = gr.Button("Cancel", elem_id="close-confirm-cancel")
    opts = dict(show_progress="hidden", api_visibility="private", concurrency_limit=1, concurrency_id="dong")
    outs = [modal, body, msg, closed]
    hide = gr.update(visible=False)

    def refuse(text, level):
        if level == "warn":
            gr.Warning(text, title="Chưa đóng được")
        return hide, "", f'<div class="m28-msg m-{level}" role="status">{html.escape(text)}</div>', gr.update()

    def on_open():
        ok, text, level = close_check(store, ctx)
        if not ok:
            return refuse(text, level)
        return gr.update(visible=True), close_body_html(store), "", gr.update()

    def on_confirm():
        ok, text, level = close_check(store, ctx)               # job có thể vừa bắt đầu khi hộp đang mở: kiểm lại
        if not ok and ctx.closing:
            return hide, "", "", CLOSED_HTML                       # tab thứ hai: trang đã đóng rồi, cũng hiện lớp phủ
        if not ok:
            return refuse(text, level)
        if os.environ.get("M28_PUBLIC_DEMO") == "1":
            return refuse("Đây là bản demo công khai: không đóng được trang.", "info")
        if not ctx.begin_close():
            return refuse("Trang đang đóng hoặc đang chuyển lượt.", "info")
        if store is not None:
            if not store.finished and not os.path.exists(store.done_path) and store.can_finish():
                try:
                    store.write_done()
                    store.finished = True
                except (ValueError, OSError):
                    pass
            store.closed = True
        dong_ho_ui.tu_tam_dung(ctx)                                 # đồng hồ đang chạy thì tự tạm dừng (rồi từ chối mọi thao tác ghi)
        threading.Timer(1.0, lambda: demo.close(verbose=False)).start()
        return hide, "", "", CLOSED_HTML

    def on_cancel():
        return hide, "", "", gr.update()

    b_dong.click(on_open, None, outs, **opts)
    b_ok.click(on_confirm, None, outs, **opts)
    b_no.click(on_cancel, None, outs, **opts)
    return types.SimpleNamespace(button=b_dong, modal=modal)


LEAD_LABEL = {False: "Team lead: off", True: "Team lead: on"}
STEP_OPTS = dict(show_progress="hidden", api_visibility="private", concurrency_limit=1, concurrency_id="steps")
LEAD_TABS = ("hop", "thongke", "loc")
LEAD_SAVE_JS = """() => {
  const b = document.getElementById('btn-lead');
  const on = !!b && /: on$/.test(b.textContent.trim());
  try { localStorage.setItem('m28_lead', on ? '1' : '0'); } catch (e) { }
  const from = window.__m28LeadFrom || '';
  window.__m28LeadFrom = '';
  if (on || !from) { return; }                  // chỉ khi tắt lúc đang ở tab của Team lead (tab đó vừa ẩn): về trang của bước; tab khác thì đứng yên
  const box = document.querySelector('#m28-go textarea, #m28-go input');
  const btn = document.getElementById('m28-go-btn');
  if (!box || !btn) { return; }
  const proto = box.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(box, 'home');
  box.dispatchEvent(new Event('input', { bubbles: true }));
  setTimeout(() => btn.click(), 40);
}"""
LEAD_LOAD_JS = """() => {
  let on = false;
  try { on = localStorage.getItem('m28_lead') === '1'; } catch (e) { return; }
  if (!on) { return; }
  const t0 = Date.now();
  const go = () => {
    const b = document.getElementById('btn-lead');
    if (b && /: off$/.test(b.textContent.trim())) { b.click(); return; }
    if (!b && Date.now() - t0 < 3000) { setTimeout(go, 100); }
  };
  setTimeout(go, 300);
}"""


# Thang cỡ chữ của cả trang: chữ thường 15px, nhỏ nhất 13px (nhãn ô nhập, nút size="sm", chú thích của Gradio dùng sm/xs/xxs). CSS riêng của tool theo cùng thang.
TEXT_SIZE = dict(xxs="13px", xs="13px", sm="13px", md="15px", lg="16px", xl="20px", xxl="24px")


def build_ui(store, ctx=None):
    """Dựng Blocks. Chỉ gọi sau khi đã đặt biến môi trường an toàn (xem prepare_env).
    store=None: chưa có lượt nào (chế độ --nap), tab Rà soát chỉ có lời nhắc."""
    import gradio as gr

    if ctx is None:
        ctx = AppCtx(reviewer=store.reviewer, run_dir=store.run_dir)
    title = f"Rà soát M28 · {run_name(store.run_dir)}" if store is not None else "Rà soát M28 · Nạp ảnh"
    theme = gr.themes.Soft(primary_hue="blue", neutral_hue="slate", text_size=gr.themes.Size(**TEXT_SIZE),
                           font=["Plus Jakarta Sans", "Inter", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
                           font_mono=["JetBrains Mono", "ui-monospace", "Consolas", "monospace"])
    with gr.Blocks(title=title, fill_width=True) as demo:
        ctx.demo = demo
        with gr.Row(elem_id="m28-appbar"):
            gr.HTML(BRAND_HTML, elem_id="m28-brand-wrap", apply_default_css=False)
            with gr.Row(elem_id="m28-right"):                              # cụm đợt đứng ngay trước nút Reviewer (P1)
                batch = gr.HTML(batch_pill_html(store, ctx), elem_id="m28-batch", apply_default_css=False)
                with gr.Row(elem_id="m28-tools"):
                    bar = cai_dat_ui.settings_bar(gr)
                    b_lead = gr.Button(LEAD_LABEL[False], elem_id="btn-lead", size="sm")
                    close_ui = _close_bar(gr, demo, store, ctx)
        steps = gr.HTML(steps_html(store, ctx), elem_id="m28-steps", apply_default_css=False)
        header = gr.HTML(head_nap(ctx) if store is None else "", elem_id="progress",
                         apply_default_css=False)
        go_tb = gr.Textbox(visible="hidden", elem_id="m28-go")
        go_btn = gr.Button(visible="hidden", elem_id="m28-go-btn")
        lead_state = gr.State(False)
        steps_timer = gr.Timer(4.0)
        with gr.Tabs(elem_id="tabs", selected=landing_tab(store, ctx)) as tabs:
            with gr.Tab("Rà soát", id="ra", elem_id="tab-ra") as tab_ra:
                if store is None:
                    gr.HTML(NO_RUN_HTML, apply_default_css=False)
                    review = None
                else:
                    review = _review_tab(gr, demo, store, ctx, header)
            with gr.Tab("Sửa trên CVAT", id="cvat", elem_id="tab-cvat") as tab_cvat:
                cv_fn, cv_outs, cv_opts = cvat_ui.cvat_tab(gr, demo, store, ctx)
            with gr.Tab("Nạp ảnh", id="nap", elem_id="tab-nap") as tab_nap:
                nap_load = _nap_tab(gr, demo, store, ctx)
                nap_ok = getattr(ctx, "nap_cvat_ok", None)
            with gr.Tab("Các đợt", id="dot", elem_id="tab-dot") as tab_dot:
                refresh, dot_ses, dot_outs, dot_opts, dot_go = dot_ui.dot_tab(
                    gr, demo, store, ctx, dict(Store=Store, switch_js=NAP_SWITCH_JS, run_name=run_name, step_of=lambda: current_step(store, ctx)))
            with gr.Tab("Ca khó", id="cakho", elem_id="tab-cakho") as tab_ck:
                ck_fn, ck_in, ck_out, ck_opts = ca_kho.member_tab(gr, demo, store, ctx)
            with gr.Tab("Họp team", id="hop", elem_id="tab-hop", visible=False) as tab_hop:
                ca_kho.meeting_tab(gr, demo, ctx)
            with gr.Tab("Thống kê", id="thongke", elem_id="tab-thongke", visible=False) as tab_tk:
                tk_fn, tk_in, tk_out, tk_opts = thong_ke_ui.stats_tab(gr, demo, store, ctx)
            with gr.Tab("Lọc dữ liệu", id="loc", elem_id="tab-loc", visible=False) as tab_loc:
                lc_fn, lc_in, lc_out, lc_opts = loc_ui.loc_tab(gr, demo, store, ctx)

        def on_steps():
            return steps_html(store, ctx), batch_pill_html(store, ctx)

        def after_cvat(ev):
            if review is not None:
                ev.then(review.push_refresh, None, review.push_outs, **dict(review.push_opts, concurrency_id="push_view"))
            ev.then(refresh, [dot_ses], dot_outs, **dot_opts)
            ev.then(on_steps, None, [steps, batch], **STEP_OPTS)

        def after_model(ev):
            ev.then(nap_load[0], nap_load[1], nap_load[2], **nap_load[3])

        def after_reviewer(ev):
            ev.then(on_steps, None, [steps, batch], **STEP_OPTS)
            if store is None:
                ev.then(lambda: head_nap(ctx), None, header, show_progress="hidden", api_visibility="private")
        pops = cai_dat_ui.settings_popups(gr, demo, store, ctx, bar, after_cvat, run_name, after_model, after_reviewer)


        def on_go(where):
            if where == "home":                                            # tắt Team lead lúc đang ở tab của Team lead: về trang của bước hiện tại
                return gr.Tabs(selected=landing_tab(store, ctx))
            tab = GO_TAB.get(where)
            return gr.Tabs(selected=tab) if tab else gr.update()

        def on_lead(on):
            """Chỉ bật/tắt các tab của Team lead, KHÔNG đổi tab đang xem (trước đây tắt là luôn nhảy về trang của bước, đợt đã đẩy thì sang Sửa trên CVAT).
            Đang đứng ở tab Team lead mà tắt thì LEAD_SAVE_JS gửi 'home' qua nút ẩn m28-go."""
            on = not on
            vis = gr.update(visible=on)
            return on, gr.update(value=LEAD_LABEL[on], variant="primary" if on else "secondary"), vis, vis, vis

        steps_timer.tick(on_steps, None, [steps, batch], **STEP_OPTS)
        demo.load(on_steps, None, [steps, batch], **STEP_OPTS)
        tabs.select(on_steps, None, [steps, batch], **STEP_OPTS)
        # trước khi đổi tab: tab Các đợt chọn trang (danh sách đợt cho 'dot', Gộp & kết thúc cho 'gop') hoặc đóng popup quản lý đợt khi đi tab khác
        go_btn.click(dot_go, [go_tb, dot_ses], dot_outs, **dot_opts).then(on_go, [go_tb], tabs, show_progress="hidden", api_visibility="private")
        b_lead.click(on_lead, [lead_state], [lead_state, b_lead, tab_hop, tab_tk, tab_loc], show_progress="hidden",
                     api_visibility="private").then(None, None, None, js=LEAD_SAVE_JS)
        demo.load(None, None, None, js=LEAD_LOAD_JS)
        tab_ck.select(ck_fn, ck_in, ck_out, **ck_opts)                      # tab Ca khó tự làm mới khi chọn (ca vừa đánh dấu ở tab Rà soát)
        tab_dot.select(refresh, [dot_ses], dot_outs, **dot_opts)           # tự làm mới khi chọn tab (không quét lại mỗi giây)
        demo.load(refresh, [dot_ses], dot_outs, **dot_opts)                # trang mở thẳng ở bước 4 (đợt đã gộp, job xong hết): không có sự kiện chọn tab
        tab_tk.select(tk_fn, tk_in, tk_out, **tk_opts)                      # Thống kê: tính khi chọn tab, không tính lúc mở trang
        tab_loc.select(lc_fn, lc_in, lc_out, **lc_opts)                     # Lọc dữ liệu: làm mới danh sách lượt/người rà/cấu hình khi chọn tab
        tab_nap.select(nap_load[0], nap_load[1], nap_load[2], **nap_load[3])
        tab_cvat.select(cv_fn, None, cv_outs, **cv_opts)
        if nap_ok is not None:
            def on_nap_ok():
                return pops.show("reviewer" if chua_dat_ten(ctx) else "cvat")

            nap_ok.click(on_nap_ok, None, pops.outs, **pops.opts).then(None, None, None, js=cai_dat_ui.FOCUS_JS)
        if review is not None:                                             # chọn lại tab Rà soát: vẽ lại (ảnh vừa xoá/khôi phục ở tab Các đợt)
            n_outs = len(review.all_outs)

            def on_tab(ses, evt: gr.SelectData):
                if evt.value != "Rà soát":
                    return (gr.update(),) * n_outs
                return review.on_reselect(ses)
            tabs.select(on_tab, [review.ses_state], review.all_outs, **review.opts)
            tabs.select(review.push_refresh, None, review.push_outs, **dict(review.push_opts, concurrency_id="push_view"))
            for ev in review.events:
                ev.then(on_steps, None, [steps, batch], **STEP_OPTS)

            def on_pushed():
                go = ctx.push_job.running and ctx.push_job.run == run_name(store.run_dir)
                return gr.Tabs(selected="cvat") if go else gr.update()
            pushed = review.push_ok.then(on_pushed, None, tabs, show_progress="hidden", api_visibility="private")
            pushed.then(cv_fn, None, cv_outs, **cv_opts)
            pushed.then(on_steps, None, [steps, batch], **STEP_OPTS)
    demo.queue(default_concurrency_limit=1)
    soft_queue_poll(demo)
    return demo, theme


QUEUE_POLL_S = 0.01


def soft_queue_poll(demo, poll_s=QUEUE_POLL_S):
    """Hàng đợi Gradio tự hỏi lại mỗi 1 ms trên Linux (0,05 giây trên Windows): một app rỗng cũng tốn ~5% CPU lúc rảnh. Nâng lên 10 ms thì CPU rảnh còn ~1%
    mà độ trễ bấm nút không đổi (đo ~68 ms cả hai). Chỉ nâng, không bao giờ hạ (Windows giữ 0,05). Là thuộc tính nội bộ của Gradio:
    không có hoặc không phải số thì bỏ qua, trang vẫn chạy như cũ. Trả về True nếu đã nâng."""
    q = getattr(demo, "_queue", None)
    cur = getattr(q, "sleep_when_free", None)
    if isinstance(cur, (int, float)) and not isinstance(cur, bool) and cur < poll_s:
        q.sleep_when_free = poll_s
        return True
    return False


def parse_argv(argv):
    """("run", thư mục lượt, người rà) | ("nap", None, người rà) | None nếu sai cú pháp. Người rà có thể bỏ trống (None): main dùng tên đã lưu ở tab Cài đặt, chưa lưu thì P1."""
    if len(argv) not in (1, 2) or (argv[0] == "--nap" and len(argv) > 2):
        return None
    who = argv[1] if len(argv) == 2 else None
    return ("nap", None, who) if argv[0] == "--nap" else ("run", argv[0], who)


def _launch(demo, theme, ctx, port, allowed, inbrowser, retry_s=0):
    """launch như cũ; retry_s > 0 (chuyển lượt cùng cổng): thử lại khi cổng chưa kịp nhả."""
    from starlette.middleware import Middleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    # Chỉ nhận Host là localhost/127.0.0.1: chặn DNS rebinding từ trang web lạ đọc ảnh mặt qua 127.0.0.1.
    PUBLIC = os.environ.get("M28_PUBLIC_DEMO") == "1"
    guard = [Middleware(TrustedHostMiddleware, allowed_hosts=["*"] if PUBLIC else ["127.0.0.1", "localhost"])]
    if PUBLIC:
        guard.append(Middleware(_DemoNoUpload))
    t_end = time.time() + retry_s
    while True:
        try:
            # share=False và 127.0.0.1: chỉ máy này vào được. Gradio có in dòng gợi ý tạo public link: KHÔNG làm theo,
            # nên quiet=True để tắt dòng đó và tự in địa chỉ bằng tiếng Việt.
            return demo.launch(server_name="0.0.0.0" if PUBLIC else "127.0.0.1", server_port=port, state_session_capacity=30 if PUBLIC else 10000, share=False, ssr_mode=False,
                               mcp_server=False, pwa=False, enable_monitoring=False, footer_links=[],
                               show_error=True, quiet=True, allowed_paths=allowed, inbrowser=inbrowser,
                               theme=theme, css=CSS, js=PAGE_JS, head=giao_dien.HEAD, prevent_thread_lock=True, max_file_size="25mb",
                               app_kwargs={"middleware": guard})
        except OSError:
            if time.time() >= t_end:
                raise
            time.sleep(0.5)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")      # cmd Windows không chết vì chữ có dấu
        except (AttributeError, ValueError):
            pass
    dang_chay.mark_owner()       # tiến trình con (push, xoá task) nhận ra khoá do trang giữ, kể cả khi python.exe của .venv là bộ khởi chạy (Windows)
    argv = sys.argv[1:] if argv is None else list(argv)
    parsed = parse_argv(argv)
    if parsed is None:
        print(VI_USAGE, file=sys.stderr)
        return 2
    mode, run_dir, reviewer = parsed
    tu_dong = reviewer is None                         # không ghi người rà ở dòng lệnh (menu chay.sh/chay.bat): lấy tên đã lưu ở tab Cài đặt
    mac_dinh = False
    if tu_dong:
        reviewer = cai_dat.get().default_reviewer()
        mac_dinh = not reviewer
        reviewer = reviewer or DEFAULT_REVIEWER
        if mac_dinh and mode == "run":                 # mở thẳng một đợt mà chưa có tên: không rà dưới tên mặc định P1 (triage_P1.csv lệch với tên đã rà trước đó)
            print(f"Chưa đặt tên người rà nên chưa mở đợt {run_name(run_dir)}: mở trang chính. Bấm nút Reviewer ở đầu trang, gõ tên của bạn rồi bấm Save name, "
                  f"sau đó mở đợt {run_name(run_dir)} ở tab Các đợt → Open batch.", flush=True)
            mode, run_dir = "nap", None
    try:
        check_reviewer(reviewer)
        bad = notebook_env()
        if bad:
            raise RunError(bad)
        if mode == "nap":
            run_dir, store = os.path.join("runs", nap_anh.NAP_DIR), None
            os.makedirs("runs", exist_ok=True)
        else:
            store = Store(run_dir, reviewer)
        prepare_env(run_dir)
    except RunError as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Lỗi: không tạo được thư mục runs ({e}).", file=sys.stderr)
        return 2
    inbrowser = os.environ.get("M28_NO_BROWSER") != "1"
    try:                                                  # cổng cố định: bản thứ hai không tự nhảy sang cổng khác
        port = int(os.environ.get("GRADIO_SERVER_PORT") or DEFAULT_PORT)
    except ValueError:
        print(f"Lỗi: GRADIO_SERVER_PORT={os.environ.get('GRADIO_SERVER_PORT')!r} không phải số.", file=sys.stderr)
        return 2
    ctx = AppCtx(reviewer=reviewer, run_dir=run_dir, nap_only=store is None, reviewer_auto=tu_dong, reviewer_mac_dinh=mac_dinh)
    demo, first = None, True
    try:
        while True:
            demo, theme = build_ui(store, ctx)
            # Chỉ phát file của lượt đang rà (overlays, crop/images, _tmp); không bao giờ inbox/ hay cả runs/.
            allowed = [os.path.abspath(os.path.join(ctx.run_dir, d)) for d in ("overlays", os.path.join("crop", "images"), "_tmp")]
            allowed.append(os.path.abspath(ca_kho.serve_dir(ctx.project_root)))        # chỉ outputs/ca_kho (gói họp, phiên họp), không cả outputs/
            allowed.append(os.path.abspath(thong_ke_ui.serve_dir(ctx.project_root)))   # chỉ outputs/thong_ke (bản xuất thống kê để tải)
            allowed.append(os.path.abspath(loc_ui.serve_dir(ctx.project_root)))        # chỉ outputs/train_sets (file .zip bộ dữ liệu để tải)
            try:
                _app, url, _share = _launch(demo, theme, ctx, port, allowed, inbrowser and first, 0 if first else 10)
            except OSError as e:
                print(f"Lỗi: không mở được trang rà soát ({e}). Cổng {port} bận: có thể trang rà soát cũ còn mở (đóng nó trước, "
                      "tránh hai bản cùng ghi một file) hoặc chương trình khác dùng cổng; đổi cổng bằng set GRADIO_SERVER_PORT=7861.",
                      file=sys.stderr)
                return 2
            if store is None:
                ai = "chưa đặt tên (bấm nút Reviewer ở đầu trang)" if chua_dat_ten(ctx) else reviewer
                print(f"Trang rà soát (chưa có lượt nào), người rà {ai}: nạp ảnh ở tab Nạp ảnh.\n"
                      f"Mở {url} nếu trình duyệt chưa tự mở (chỉ máy này vào được). Ctrl+C để đóng.", flush=True)
            else:
                p = store.progress()
                print(f"Trang rà soát lượt {run_name(ctx.run_dir)}, người rà {reviewer}: còn {p['remaining']}/{p['total']} mặt chưa rà.\n"
                      f"Mở {url} nếu trình duyệt chưa tự mở (chỉ máy này vào được).\n"
                      "Rà xong bấm Push to CVAT (tự chốt lượt) rồi theo dõi ở bước Sửa trên CVAT; xong việc bấm 'Close page'; "
                      "Ctrl+C để đóng giữa chừng (gõ lại đúng lệnh để làm tiếp).", flush=True)
            while demo.is_running:                    # nút 'Close page' (hoặc chuyển lượt) gọi demo.close() và vòng này kết thúc; Xong không tắt gì
                time.sleep(0.2)
            if ctx.switch_to is None:
                if store is None:
                    print("Đã đóng trang rà soát (chưa có lượt nào).", flush=True)
                elif os.path.exists(store.done_path):
                    print(f"Đã đóng trang rà soát: lượt {run_name(store.run_dir)} đã chốt ({_shown(store.done_path)}).", flush=True)
                else:
                    print(f"Đã đóng trang rà soát mà chưa chốt (lượt {run_name(store.run_dir)}, còn "
                          f"{store.progress()['remaining']} mặt chưa rà): gõ lại đúng lệnh để làm tiếp.", flush=True)
                return 0
            new_dir, new_store = ctx.switch_to
            if store is not None:
                left = store.progress()["remaining"]
                print(f"Chuyển sang lượt {run_name(new_dir)}. Lượt {run_name(store.run_dir)} còn {left} mặt chưa rà "
                      f"(các lần bấm đã lưu); mở lại bằng: {nap_anh.reopen_command(store.run_dir, store.reviewer)}", flush=True)
            else:
                print(f"Chuyển sang lượt {run_name(new_dir)}.", flush=True)
            store, first = new_store, False
            ctx = AppCtx(reviewer=new_store.reviewer, run_dir=new_dir)      # job mới, ctx mới; tên người rà là tên của lượt mới (cài đặt ở tab Cài đặt)
            reviewer = ctx.reviewer
    except KeyboardInterrupt:
        dong_ho_ui.tu_tam_dung(ctx)                       # Ctrl+C: đồng hồ đang chạy tự tạm dừng, không mất số đo
        if store is not None and os.path.exists(store.done_path):
            print(f"Đã đóng trang rà soát bằng Ctrl+C: lượt {run_name(store.run_dir)} đã chốt ({_shown(store.done_path)}).", flush=True)
        else:
            print("Đã đóng trang rà soát (chưa chốt lượt).", flush=True)
        if demo is not None:
            demo.close(verbose=False)
        return 0
    finally:
        for j in (ctx.job, ctx.push_job, ctx.del_job, ctx.smoke_job, ctx.collect_job):
            if j.running:
                if j is ctx.smoke_job:
                    print("Đóng trang khi kiểm tra nhanh CVAT còn chạy: đã dừng; lần chạy sau (python tool\\cvat_smoke.py) tự dọn task demo-smoke "
                          "còn dở nhờ runs\\_smoke\\dang_mo.json.", flush=True)
                elif j is ctx.collect_job:
                    print(f"Đóng trang khi đang gộp job CVAT của lượt {j.run}: đã dừng (đồng hồ của đợt đang tạm dừng, chưa lưu). Mở lại trang, bấm Merge jobs & Finish "
                          f"ở thẻ đợt (tab Các đợt), hoặc chạy python tool\\m28.py collect --task {j.task} --reviewer {j.person} --overwrite.", flush=True)
                elif j is not ctx.job:
                    print(f"Đóng trang khi còn việc CVAT đang chạy cho lượt {j.run}: đã dừng; xem runs\\{j.run}\\push.json và chạy "
                          f"python tool\\m28.py push --run {j.run} --resume hoặc --cleanup nếu task đã tạo dở.", flush=True)
                j.cancel()


if __name__ == "__main__":
    sys.exit(main())
