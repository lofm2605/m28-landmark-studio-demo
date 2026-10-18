"""Nhập tay của nhóm trưởng (tab Thống kê, mục "Nhập tay"; QĐ-006): người nhóm MANUAL gán tay thẳng trong CVAT, KHÔNG dùng tool, nên không có đồng hồ ở đầu trang và
không có gói kết quả. Nhóm trưởng nhập cho từng người: người (tên bất kỳ), nhóm, đợt/bộ ảnh, thời gian làm (gõ tay), ngày làm và file nhãn xuất từ CVAT ("CVAT for images 1.1",
.xml hoặc .zip không kèm ảnh; nhiều file được, ví dụ mỗi job một file, gộp theo tên ảnh). Module dựng một gói kết quả BÌNH THƯỜNG (goi_kq, định dạng m28-ketqua bản 1, thêm
trường nguon_nhap="nhap_tay") và ghi vào outputs\\goi_nhom, nên thong_ke.tinh (tab Thống kê) và tool\\tong_ket.py tính nó y như gói do đồng hồ ghi: giây/mặt = thời gian gõ ÷ số
ảnh có nhãn (ước lượng chia đều), nhãn của nhóm manual là đáp án để đo NME của nháp.

  * Mã phiên tất định theo đầu vào (người, đợt, nội dung file nhãn, nhóm, thời gian): bấm hai lần không thành hai gói (ghi lại đúng gói đó). Cùng người mà đã có gói của
    PHIÊN KHÁC (gói của đồng hồ hay bản nhập tay khác) cùng đợt, HOẶC trùng dù chỉ một tên ảnh (một người không gán một ảnh hai lần trong thí nghiệm, nên trùng ảnh dưới tên
    đợt khác vẫn là cùng một lần làm) thì từ chối, vì thời gian sẽ bị tính hai lần: gỡ gói kia trước.
  * Nhóm assisted: nháp lấy ở runs\\<đợt>\\xml\\prelabel.xml, nên đợt phải là TÊN LƯỢT đã dựng nháp (ví dụ bo200), không phải tên bộ ảnh; máy không có nháp đó thì vẫn ghi
    gói (nhãn cuối + thời gian) nhưng ghi chú nói rõ NME của nháp và tỉ lệ sửa sẽ thiếu mặt của người này. Bộ ảnh (bo_anh) lấy ở config khi có, ghi chú nêu khi khác đợt.
  * Gỡ (bo) là xoá MỀM: chuyển file vào outputs\\goi_nhom\\_da_bo\\ (thống kê chỉ đọc cấp 1 của thư mục), không bao giờ xoá.
  * Gói không có ảnh, token, email, đường dẫn tuyệt đối (goi_kq.kiem_rieng_tu); phần <meta> của file CVAT (có email người tạo task) không bao giờ vào gói hay thông báo.
Chỉ thư viện chuẩn; eval50 (numpy) và cvat_io nạp lười như goi_kq. Lỗi người dùng sửa được: NhapTayLoi (thông báo tiếng Việt, không traceback, không đường dẫn tuyệt đối).
"""
import datetime
import hashlib
import os
import re
import threading
import unicodedata
import zipfile
import zlib

from m28core import goi_kq
from m28core import ten_nguoi

THU_MUC = os.path.join("outputs", "goi_nhom")
THU_MUC_BO = "_da_bo"                                       # thư mục con của outputs\goi_nhom: bản đã gỡ (thống kê không đọc)
THU_MUC_DOC = (goi_kq.THU_MUC, THU_MUC, os.path.join("outputs", "goi_da_nap"))       # = thong_ke.THU_MUC_GOI: các thư mục gói mà thống kê đọc mặc định
NGUON = "nhap_tay"
DOT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")    # giống dong_ho.DOT_RE (và tên lượt của goi_kq.nhap_cua_dot)
TASK_RE = re.compile(r"[A-Za-z0-9_.-]{0,64}")
GIAY_TOI_DA = 24 * 3600
MAX_BYTE = goi_kq.MAX_BYTE                                  # một file nhãn (hoặc annotations.xml trong zip) lớn hơn: không đọc
MAX_FILE = 50
MAX_MUC_ZIP = 64
GHI_CHU_MAX = 200
GIAY_MAT_NGHI = (10.0, 20 * 60.0)                           # giây/mặt ngoài khoảng này: nhắc kiểm lại (không chặn)
ANH_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_HMS = re.compile(r"(\d{1,3}):(\d{1,2}):(\d{1,2})")
_MS = re.compile(r"(\d{1,4}):(\d{1,2})")
_PHUT = re.compile(r"(\d{1,5}(?:[.,]\d+)?)\s*(?:phút|phut|ph|p|min|m)?\.?")
_GOI_Y_GIO = "gõ h:mm:ss (1:25:30), mm:ss (85:30) hoặc số phút (85, 85,5, 85 phút)"
_LOCK = threading.Lock()                                    # kiểm trùng + ghi + gỡ: một thao tác tại một thời điểm


class NhapTayLoi(Exception):
    """Từ chối bản nhập tay (lỗi người dùng sửa được). Thông báo tiếng Việt, không đường dẫn tuyệt đối."""


def fmt_giay(s):
    """mm:ss (>= 60 phút: h:mm:ss), như dong_ho.fmt_giay."""
    s = max(0, int(round(float(s or 0))))
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


GIAY_MOI_MAT_NGHI = 5.0                 # giây/mặt dưới ngần này: gần như chắc gõ nhầm thời gian (gán 50 điểm một mặt mất cỡ phút)


def gio_bang_chu(s):
    """'1 giờ 25 phút 30 giây' (bỏ phần bằng 0 ở đầu) để người nhập thấy đúng ý mình: '1:30' là 1 phút 30 giây, không phải 1 giờ 30 phút."""
    s = max(0, int(round(float(s or 0))))
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    parts = ([f"{h} giờ"] if h else []) + ([f"{m} phút"] if (h or m) else []) + [f"{sec} giây"]
    return " ".join(parts)


# ---------- thời gian, ngày ----------
def doc_thoi_gian(text):
    """Thời gian làm -> giây (float): 'h:mm:ss', 'mm:ss' (phút được quá 59: '85:30'), hoặc số trơn = PHÚT ('85', '85,5', '85 phút', '85p'). Phải > 0 và <= 24 giờ."""
    t = unicodedata.normalize("NFC", str(text if text is not None else "")).strip().lower()
    if not t:
        raise NhapTayLoi(f"Chưa nhập thời gian làm: {_GOI_Y_GIO}.")
    m3, m2, mp = _HMS.fullmatch(t), _MS.fullmatch(t), _PHUT.fullmatch(t)
    if m3:
        h, mi, s = (int(x) for x in m3.groups())
        if mi >= 60 or s >= 60:
            raise NhapTayLoi(f"Thời gian {t!r}: phút và giây phải nhỏ hơn 60 ({_GOI_Y_GIO}).")
        giay = h * 3600 + mi * 60 + s
    elif m2:
        mi, s = (int(x) for x in m2.groups())
        if s >= 60:
            raise NhapTayLoi(f"Thời gian {t!r}: giây phải nhỏ hơn 60 ({_GOI_Y_GIO}).")
        giay = mi * 60 + s
    elif mp:
        giay = float(mp.group(1).replace(",", ".")) * 60
    else:
        raise NhapTayLoi(f"Không đọc được thời gian {t[:40]!r}: {_GOI_Y_GIO}.")
    if giay <= 0:
        raise NhapTayLoi("Thời gian làm phải lớn hơn 0.")
    if giay > GIAY_TOI_DA:
        raise NhapTayLoi(f"Thời gian {fmt_giay(giay)} quá 24 giờ: kiểm lại (số trơn là PHÚT, không phải giây).")
    return float(giay)


def doc_ngay(text, now=None):
    """Ngày làm -> datetime.date: '' = hôm nay, 'dd/mm/yyyy', 'dd/mm' (năm nay), 'yyyy-mm-dd'. Ngày không có thật hoặc ở tương lai: NhapTayLoi."""
    now = now or datetime.datetime.now().astimezone()
    t = str(text if text is not None else "").strip()
    if not t:
        return now.date()
    m1 = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", t)
    m2 = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    m3 = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})", t)
    try:
        if m1:
            d = datetime.date(int(m1.group(3)), int(m1.group(2)), int(m1.group(1)))
        elif m2:
            d = datetime.date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
        elif m3:
            d = datetime.date(now.year, int(m3.group(2)), int(m3.group(1)))
        else:
            raise NhapTayLoi(f"Không đọc được ngày {t[:40]!r}: để trống (hôm nay) hoặc gõ dd/mm/yyyy, ví dụ 14/10/2026.")
    except ValueError:
        raise NhapTayLoi(f"Ngày {t!r} không có thật: gõ dd/mm/yyyy, ví dụ 14/10/2026.")
    if d > now.date():
        raise NhapTayLoi(f"Ngày làm {d:%d/%m/%Y} ở tương lai: kiểm lại (để trống là hôm nay).")
    return d


def _ghi_chu(text):
    """Ghi chú sạch: NFC, bỏ ký tự điều khiển, tối đa GHI_CHU_MAX ký tự; có đường dẫn, email, tên máy, chuỗi giống token thì từ chối."""
    s = unicodedata.normalize("NFC", "" if text is None else str(text)).replace("\r\n", "\n").replace("\r", "\n")
    s = _CTRL.sub(" ", s).strip()
    if len(s) > GHI_CHU_MAX:
        raise NhapTayLoi(f"Ghi chú dài {len(s)} ký tự, tối đa {GHI_CHU_MAX}.")
    probs = goi_kq.kiem_rieng_tu([s]) if s else []
    if probs:
        raise NhapTayLoi("Ghi chú bị chặn vì " + ", ".join(probs) + ": bỏ phần đó (gói gửi nhóm phải sạch thông tin riêng tư) rồi thêm lại. Không ghi gì.")
    return s


# ---------- file nhãn xuất từ CVAT ----------
def _ten_hien(paths):
    """Tên hiển thị của từng file: tên file (không thư mục); hai file cùng tên thì thêm số thứ tự."""
    base = [os.path.basename(str(p))[:100] or "file" for p in paths]
    return [b if base.count(b) == 1 else f"{b} (file thứ {i + 1})" for i, b in enumerate(base)]


def _sach(msg, path, ten):
    """Thông báo của bộ đọc với đường dẫn (file tạm của Gradio) thay bằng tên hiển thị: không lộ đường dẫn tuyệt đối."""
    s = str(msg)
    p = str(path)
    for x in sorted({p, os.path.abspath(p), os.path.realpath(p)}, key=len, reverse=True):
        s = s.replace(x, ten)
    for x in sorted({os.path.dirname(os.path.abspath(p)), os.path.dirname(os.path.realpath(p))}, key=len, reverse=True):
        if len(x) > 3:
            s = s.replace(x, "")
    return s[:300]


def _doc_xml(path, ten):
    """Bytes của annotations.xml: chính file .xml, hoặc annotations.xml ở GỐC file .zip xuất từ CVAT (đọc trong bộ nhớ, không giải nén ra đĩa; tên lạ hay kèm ảnh: từ chối)."""
    ext = os.path.splitext(str(path))[1].lower()
    if ext not in (".xml", ".zip"):
        raise NhapTayLoi(f"{ten}: chỉ nhận file .xml hoặc .zip xuất từ CVAT (định dạng 'CVAT for images 1.1').")
    try:
        size = os.path.getsize(path)
    except OSError as e:
        raise NhapTayLoi(f"Không đọc được {ten} ({type(e).__name__}): chọn lại file.")
    if size > MAX_BYTE:
        raise NhapTayLoi(f"{ten} quá lớn (hơn {MAX_BYTE // (1024 * 1024)} MB): file nhãn không kèm ảnh chỉ vài MB; xuất lại từ CVAT không tích 'Save images'.")
    try:
        if ext == ".xml":
            with open(path, "rb") as f:
                return f.read()
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > MAX_MUC_ZIP:
                raise NhapTayLoi(f"{ten}: zip có {len(infos)} file (có kèm ảnh?): chỉ cần annotations.xml; xuất lại 'CVAT for images 1.1' không tích 'Save images'.")
            for i in infos:
                n = i.filename.replace("\\", "/")
                if n.startswith("/") or re.match(r"[A-Za-z]:", n) or ".." in n.split("/"):
                    raise NhapTayLoi(f"{ten}: tên file trong zip có đường dẫn lạ (nghi ngờ): từ chối.")
                if n.lower().endswith(ANH_EXT):
                    raise NhapTayLoi(f"{ten}: zip có kèm ảnh. Chỉ cần nhãn: xuất lại 'CVAT for images 1.1' KHÔNG tích 'Save images' (hoặc chọn riêng annotations.xml).")
            try:
                info = z.getinfo("annotations.xml")
            except KeyError:
                raise NhapTayLoi(f"{ten}: zip không có annotations.xml ở gốc (đã xuất đúng định dạng 'CVAT for images 1.1' chưa?).")
            if info.file_size > MAX_BYTE:
                raise NhapTayLoi(f"{ten}: annotations.xml trong zip quá lớn: từ chối.")
            return z.read(info)
    except zipfile.BadZipFile:
        raise NhapTayLoi(f"{ten}: không phải file zip hợp lệ (tải về dở hoặc hỏng).")
    except (OSError, RuntimeError, EOFError, zlib.error) as e:
        raise NhapTayLoi(f"Không đọc được {ten} ({type(e).__name__}): xuất lại từ CVAT.")


def doc_file_nhan(paths, cfg):
    """Đọc các file nhãn xuất từ CVAT ("CVAT for images 1.1": .xml, hoặc .zip chỉ cần annotations.xml ở gốc). Nhiều file (ví dụ mỗi job một file) gộp theo tên ảnh không đuôi;
    cùng tên ảnh ở hai file: NhapTayLoi nêu cả hai file. Trả (labels {tên ảnh: {điểm: [x, y]}}, info dict(file=[tên file], theo_file=[(tên, số ảnh có nhãn, số ảnh trong file)],
    n_anh, sha256=[sha256 nội dung XML từng file], canh_bao=[chuỗi])). Từ chối: bản 'CVAT for video' (không có <image>), file không có skeleton nào của bảy nhóm, XML hỏng
    (SystemExit/ValueError/OSError của bộ đọc đổi thành NhapTayLoi). Không bao giờ đưa nội dung <meta> ra ngoài."""
    import eval50
    from m28core import cvat_io
    paths = [str(p) for p in (paths or []) if p]
    if not paths:
        raise NhapTayLoi("Chưa chọn file nhãn xuất từ CVAT (.xml hoặc .zip, định dạng 'CVAT for images 1.1', không kèm ảnh).")
    if len(paths) > MAX_FILE:
        raise NhapTayLoi(f"Chọn {len(paths)} file: tối đa {MAX_FILE} file nhãn mỗi lần nhập.")
    groups = []
    for p in cfg["points"]:
        g = p.get("group") or cvat_io.group_of_name(p["name"])
        if g not in groups:
            groups.append(g)
    labels, nguon, seen = {}, {}, {}
    info = dict(file=[], theo_file=[], n_anh=0, sha256=[], canh_bao=[])
    for path, ten in zip(paths, _ten_hien(paths)):
        data = _doc_xml(path, ten)
        h = hashlib.sha256(data).hexdigest()
        if h in seen:
            raise NhapTayLoi(f"{seen[h]} và {ten} là cùng một file nhãn (chọn hai lần): bỏ bớt một file.")
        seen[h] = ten
        try:
            ann = cvat_io.parse_annotations(data, [p["name"] for p in cfg["points"]])
        except (SystemExit, ValueError, OSError) as e:
            raise NhapTayLoi(f"{ten}: {_sach(e, path, ten)}")
        if not ann:
            if b"<track" in data:
                raise NhapTayLoi(f"{ten} là file xuất 'CVAT for video 1.1' (nhãn theo track, không có ảnh <image>): xuất lại bằng định dạng 'CVAT for images 1.1'.")
            raise NhapTayLoi(f"{ten} không có ảnh nào (<image>): không phải file 'CVAT for images 1.1' xuất từ CVAT.")
        msgs = []
        try:
            got = eval50.read_labels(path, cfg, warn=msgs.append)
        except (SystemExit, ValueError, OSError) as e:
            raise NhapTayLoi(f"{ten}: {_sach(e, path, ten)}")
        msgs = [_sach(m, path, ten) for m in msgs]
        if not got:
            cu = any("CŨ" in m for m in msgs)
            raise NhapTayLoi(f"{ten}: không có skeleton nào của bảy nhóm điểm ({', '.join(groups)}): "
                             + ("nhãn dùng label face50 CŨ (một skeleton), không đo được bằng config hiện tại." if cu else
                                "ảnh chưa được gán, hoặc xuất nhầm task/project (cần task dựng từ config\\m28_config.json)."))
        for k in got:
            if k in labels:
                raise NhapTayLoi(f"Ảnh {k} có trong cả {nguon[k]} và {ten}: mỗi ảnh chỉ được nằm trong một file (bỏ file trùng, hoặc xuất các job không chồng ảnh).")
        for k, v in got.items():
            labels[k], nguon[k] = v, ten
        info["file"].append(os.path.basename(path)[:100])
        info["theo_file"].append((ten, len(got), len(ann)))
        info["n_anh"] += len(ann)
        info["sha256"].append(h)
        info["canh_bao"] += [m.replace("Cảnh báo: ", "") for m in msgs if "CŨ" not in m][:5]
    return labels, info


# ---------- dựng gói ----------
def _iso(dt):
    return dt.isoformat(timespec="seconds")


def luot_co_nhap(project_root):
    """Tên các lượt trong runs\\ của máy này có nháp (xml\\prelabel.xml hoặc map50\\, như goi_kq.nhap_cua_dot), để gợi ý đợt đúng cho nhóm assisted. Chỉ đọc."""
    runs = os.path.join(project_root, "runs")
    try:
        names = sorted(os.listdir(runs))
    except OSError:
        return []
    return [n for n in names if DOT_RE.fullmatch(n) and (os.path.isfile(os.path.join(runs, n, "xml", "prelabel.xml")) or os.path.isdir(os.path.join(runs, n, "map50")))]


def tao_noi_dung(project_root, cfg, nguoi, nhom, dot, giay, label_paths, bo_anh="", ngay=None, ghi_chu="", task="", now=None, thong_bao=None):
    """Nội dung gói kết quả của MỘT bản nhập tay (qua được goi_kq.kiem_cau_truc và goi_kq.kiem_rieng_tu). `giay`: số giây hoặc chuỗi như ô "Thời gian làm" (doc_thoi_gian);
    `ngay`: date, chuỗi như ô "Ngày làm" (doc_ngay) hoặc None = hôm nay. bat_dau = ket_thuc = ngày làm + giờ lúc nhập. Mã phiên tất định:
    <Pk>-tay-<đợt>-<8 ký tự sha256 của (nội dung các file nhãn, nhóm, giây)>. Nhóm assisted: có runs/<đợt>/xml/prelabel.xml trên máy này thì kèm nháp, điểm đã sửa,
    NME nháp-so-nhãn-cuối (goi_kq.ket_qua_tu_nhan); không có thì vẫn dựng gói (co_nhap=False) và ghi chú cảnh báo đợt phải là tên lượt. Đợt giữ đúng như gõ; bo_anh = tham số,
    không có thì bo_anh của config\\nhom_thi_nghiem.json (khác đợt thì ghi chú nêu), không có nữa thì = đợt. `thong_bao` (list, tuỳ chọn) nhận các ghi chú tiếng Việt cho
    người nhập. Sai: NhapTayLoi."""
    from m28core import nhom as nhom_mod
    now = now or datetime.datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    if not isinstance(nguoi, str) or not goi_kq.NGUOI_RE.fullmatch(nguoi):
        raise NhapTayLoi("Chưa chọn người hoặc tên không hợp lệ (chỉ chữ không dấu, số và dấu -, bắt đầu bằng chữ hoặc số, tối đa 32 ký tự).")
    if nhom not in goi_kq.CONDITIONS:
        raise NhapTayLoi("Nhóm phải là manual hoặc assisted.")
    dot = str(dot or "").strip()
    if not dot:
        raise NhapTayLoi("Chưa nhập đợt / bộ ảnh (tên chung của bộ ảnh hai nhóm cùng làm, ví dụ NAP_001).")
    if not DOT_RE.fullmatch(dot):
        raise NhapTayLoi(f"Đợt {dot[:70]!r} không hợp lệ: chỉ chữ không dấu, số, _ - . (tối đa 64 ký tự), ví dụ NAP_001.")
    giay = doc_thoi_gian(giay) if isinstance(giay, str) else giay
    if not isinstance(giay, (int, float)) or isinstance(giay, bool) or giay != giay or not 0 < giay <= GIAY_TOI_DA:
        raise NhapTayLoi("Thời gian làm phải lớn hơn 0 và không quá 24 giờ.")
    if isinstance(ngay, str):
        ngay = doc_ngay(ngay, now)
    if isinstance(ngay, datetime.datetime):
        ngay = ngay.date()
    ngay = ngay or now.date()
    if ngay > now.date():
        raise NhapTayLoi(f"Ngày làm {ngay:%d/%m/%Y} ở tương lai: kiểm lại.")
    ghi_chu = _ghi_chu(ghi_chu)
    task = str(task or "").strip()
    if not TASK_RE.fullmatch(task):
        raise NhapTayLoi("Tên task chỉ gồm chữ không dấu, số, _ - . (tối đa 64 ký tự).")
    bo_anh = str(bo_anh or "").strip()
    bo_cfg = "" if bo_anh else nhom_mod.doc(project_root)["bo_anh"]
    bo_anh = bo_anh or bo_cfg or dot
    if not DOT_RE.fullmatch(bo_anh):
        raise NhapTayLoi(f"Bộ ảnh {bo_anh[:70]!r} không hợp lệ: chỉ chữ không dấu, số, _ - . (tối đa 64 ký tự).")
    labels, info = doc_file_nhan(label_paths, cfg)
    if not labels:
        raise NhapTayLoi("File nhãn không có ảnh nào có nhãn: chưa thêm.")
    nhap_hong = False
    try:
        ket_qua, _co_draft = goi_kq.ket_qua_tu_nhan(project_root, cfg, nhom, dot, labels)
    except (SystemExit, ValueError, OSError):                          # nháp runs\<đợt>\xml\prelabel.xml hỏng: vẫn nhận nhãn và thời gian, không kèm nháp
        nhap_hong = True
        ket_qua, _co_draft = goi_kq.ket_qua_tu_nhan(project_root, cfg, "manual", dot, labels)
    so_mat = len(labels)
    n_nhap = sum(1 for r in ket_qua if r.get("nhap") is not None)
    khoa = "|".join(sorted(info["sha256"]) + [nhom, f"{float(giay):.1f}"])
    phien = f"{nguoi}-tay-{goi_kq.lam_sach_ten(dot)}-{hashlib.sha256(khoa.encode('utf-8')).hexdigest()[:8]}"
    luc = datetime.datetime.combine(ngay, now.timetz().replace(microsecond=0))
    nd = dict(phien=phien, nguoi=nguoi, nhom=nhom, dot=dot, bo_anh=bo_anh, task=task, job="", so_mat=so_mat, giay_phien=round(float(giay), 1), giay_tam_dung=0.0,
              so_lan_tam_dung=0, bat_dau=_iso(luc), ket_thuc=_iso(luc), uoc_luong_chia_deu=True, mat_do=[], canh_bao=[], ghi_chu=ghi_chu, sua_tay=0, tao_luc=_iso(now),
              nhan_file="; ".join(info["file"]), co_nhan=True, co_nhap=bool(n_nhap), cau_hinh=dict(so_diem=len(cfg["points"]), nguong_sua=goi_kq.NGUONG_SUA_MAC_DINH),
              ket_qua=ket_qua, nguon_nhap=NGUON)
    probs = goi_kq.kiem_cau_truc(nd, {p["name"] for p in cfg["points"]})
    if probs:
        raise NhapTayLoi("Bản nhập tay không hợp lệ: " + "; ".join(probs[:3]) + ".")
    leak = goi_kq.kiem_rieng_tu(nd)
    if leak:
        raise NhapTayLoi("Bản nhập tay bị chặn vì " + ", ".join(leak) + " (trong tên file nhãn hoặc tên ảnh): đổi tên file rồi thêm lại. Không ghi gì.")
    if thong_bao is not None:
        for ten, n, n_anh in info["theo_file"]:
            thong_bao.append(f"{ten}: {n} ảnh có nhãn" + (f" trên {n_anh} ảnh trong file (ảnh chưa gán không tính)." if n != n_anh else "."))
        thong_bao += info["canh_bao"][:5]
        if bo_cfg and bo_cfg != dot:
            thong_bao.append(f"Bộ ảnh ghi trong gói: {bo_cfg} (bo_anh của config\\nhom_thi_nghiem.json); đợt giữ đúng như gõ: {dot}.")
        if nhom == "assisted" and n_nhap:
            thong_bao.append(f"Có nháp của đợt {dot} cho {n_nhap}/{so_mat} mặt.")
        elif nhom == "assisted":
            co = [x for x in luot_co_nhap(project_root) if x != dot]
            thong_bao.append(f"CHÚ Ý: nhóm assisted nhưng máy này không có nháp của đợt {dot} (runs\\{dot}\\xml\\prelabel.xml" + (" không đọc được" if nhap_hong else "")
                             + "): gói vẫn ghi nhãn cuối và thời gian, nhưng mặt của người này KHÔNG có nháp nên không vào NME của nháp và tỉ lệ điểm phải sửa. "
                             "Với nhóm assisted, đợt phải là TÊN LƯỢT đã dựng nháp (thư mục runs\\<lượt>, ví dụ bo200), không phải tên bộ ảnh"
                             + (f"; máy này có nháp ở: {', '.join(co[:5])}" + (" ..." if len(co) > 5 else "") if co else "")
                             + ". Gõ nhầm thì Remove entry rồi thêm lại với đúng tên lượt.")
        gm = float(giay) / so_mat
        if not GIAY_MAT_NGHI[0] <= gm <= GIAY_MAT_NGHI[1]:
            thong_bao.append(f"Giây/mặt = {gm:.1f}".replace(".", ",") + ": kiểm lại thời gian (số trơn là PHÚT) và file nhãn (đủ ảnh chưa).")
    return nd


# ---------- ghi, liệt kê, gỡ ----------
def _doc_nhap_tay(project_root):
    """[(tên gói không đuôi, nội dung, [tên file .zip/.json])] của các bản nhập tay (nguon_nhap == nhap_tay) ở CẤP 1 của outputs\\goi_nhom. Gói hỏng hay gói của đồng hồ: bỏ qua."""
    d = os.path.join(project_root, THU_MUC)
    if not os.path.isdir(d):
        return []
    by = {}
    for f in sorted(os.listdir(d)):
        b, ext = os.path.splitext(f)
        if ext.lower() in (".zip", ".json") and not f.startswith(".") and os.path.isfile(os.path.join(d, f)):
            by.setdefault(b, []).append(f)
    out = []
    for ten, fs in sorted(by.items()):
        for f in sorted(fs, key=lambda x: not x.lower().endswith(".json")):          # .json đọc nhanh hơn; hỏng thì thử .zip
            try:
                nd, _w = goi_kq.doc_goi(os.path.join(d, f))
            except goi_kq.GoiLoi:
                continue
            if nd.get("nguon_nhap") == NGUON:
                out.append((ten, nd, fs))
            break
    return out


def liet_ke(project_root):
    """Các bản nhập tay trong outputs\\goi_nhom: [dict(ten, nguoi, nhom, dot, giay, so_mat, tao_luc, ngay)] (ngay = dd/mm/yyyy của ngày làm). Chỉ đọc."""
    out = []
    for ten, nd, _fs in _doc_nhap_tay(project_root):
        bd = str(nd.get("bat_dau") or "")
        ngay = f"{bd[8:10]}/{bd[5:7]}/{bd[:4]}" if re.match(r"\d{4}-\d{2}-\d{2}", bd) else ""
        out.append(dict(ten=ten, nguoi=nd["nguoi"], nhom=nd["nhom"], dot=nd.get("dot", ""), giay=nd["giay_phien"], so_mat=nd["so_mat"], tao_luc=nd.get("tao_luc", ""), ngay=ngay))
    out.sort(key=lambda r: (r["nguoi"], r["dot"], r["ten"]))
    return out


def file_goi(project_root):
    """{tên gói: [đường dẫn các file .zip/.json của gói]} của các bản nhập tay trong outputs\\goi_nhom (cho tool\\tong_ket.py đọc thêm). Chỉ đọc."""
    d = os.path.join(project_root, THU_MUC)
    return {ten: [os.path.join(d, f) for f in fs] for ten, _nd, fs in _doc_nhap_tay(project_root)}


def _chuyen_bo(project_root, ten, files):
    """Chuyển các file của gói `ten` vào outputs\\goi_nhom\\_da_bo\\ (trùng tên ở đó thì thêm -bo2, -bo3...; không ghi đè, không xoá). Trả [đường dẫn tương đối mới]."""
    d = os.path.join(project_root, THU_MUC)
    db = os.path.join(d, THU_MUC_BO)
    try:
        os.makedirs(db, exist_ok=True)
        base, k = ten, 1
        while any(os.path.exists(os.path.join(db, base + os.path.splitext(f)[1])) for f in files):
            k += 1
            base = f"{ten}-bo{k}"
        moi = []
        for f in files:
            os.replace(os.path.join(d, f), os.path.join(db, base + os.path.splitext(f)[1]))
            moi.append(os.path.join(THU_MUC, THU_MUC_BO, base + os.path.splitext(f)[1]))
    except OSError as e:
        raise NhapTayLoi(f"Không chuyển được {ten} vào {os.path.join(THU_MUC, THU_MUC_BO)} ({type(e).__name__}: file đang mở ở chương trình khác hoặc không có quyền?).")
    return moi


def _anh_cua(nd):
    """Tên các ảnh (không đuôi) trong ket_qua của một gói."""
    return {r["anh"] for r in nd.get("ket_qua") or () if isinstance(r, dict) and isinstance(r.get("anh"), str)}


def _loai_va_cach_go(ten, x, tay):
    """(loại gói, cách gỡ) của gói `ten` đang chặn bản nhập tay; `tay` = tên các bản nhập tay trong outputs\\goi_nhom (gỡ được bằng Remove entry)."""
    la_tay = x.get("nguon_nhap") == NGUON and os.path.splitext(ten)[0] in tay
    return (("bản nhập tay khác" if x.get("nguon_nhap") == NGUON else "gói của đồng hồ"),
            ("Remove entry ở danh sách bản nhập tay" if la_tay
             else "gói đã nạp: Remove package ở mục Gói đã nạp (tab Thống kê); gói khác: chuyển file đó ra khỏi outputs\\ket_qua và outputs\\goi_nhom, hoặc bỏ nó khỏi ô tải lên"))


def them(project_root, nd, nguon_them=()):
    """Ghi một bản nhập tay (nội dung từ tao_noi_dung) vào outputs\\goi_nhom (goi_kq.ghi_goi, tên ketqua_<Pk>_<DDMM ngày làm>_<đợt>). Từ chối khi các gói mà thống kê đọc
    (outputs\\ket_qua, outputs\\goi_nhom, cộng `nguon_thêm` như các gói đang tải lên ở tab) đã có gói cùng người, PHIÊN KHÁC, mà cùng đợt hoặc trùng dù chỉ một tên ảnh
    (một người không gán một ảnh hai lần trong thí nghiệm: trùng ảnh dưới tên đợt khác vẫn là cùng một lần làm): thời gian sẽ bị tính hai lần. Thông báo nêu tên gói kia
    và cách gỡ. Cùng phiên thì ghi lại (bấm hai lần không nhân đôi); bản cũ cùng phiên mà khác tên (đổi ngày làm) được chuyển vào _da_bo. Trả dict(ten, zip, json)
    (đường dẫn tương đối)."""
    if not isinstance(nd, dict) or nd.get("nguon_nhap") != NGUON:
        raise NhapTayLoi("Chỉ thêm được bản nhập tay (dựng bằng tao_noi_dung).")
    probs = goi_kq.kiem_cau_truc(nd)
    if probs:
        raise NhapTayLoi("Bản nhập tay không hợp lệ: " + "; ".join(probs[:3]) + ".")
    with _LOCK:
        q = goi_kq.quet([os.path.join(project_root, x) for x in THU_MUC_DOC] + [p for p in (nguon_them or ()) if p])
        tay = {t for t, _nd, _fs in _doc_nhap_tay(project_root)}
        bang_ten = ten_nguoi.doc(project_root)            # so theo tên THỐNG KÊ DÙNG (nhóm trưởng có thể đã đặt tên cho gói ở mục Gói đã nạp), không theo tên gốc trong gói
        ten_moi = ten_nguoi.ap_dung([("", nd)], bang_ten)[0][0][1]["nguoi"]
        khac = [(ten, x) for ten, x in ten_nguoi.ap_dung(q["tot"], bang_ten)[0] if x["nguoi"] == ten_moi and x["phien"] != nd["phien"]]
        for ten, x in khac:
            if (x.get("dot") or "") == nd["dot"]:
                loai, cach = _loai_va_cach_go(ten, x, tay)
                raise NhapTayLoi(f"Đã có gói {ten} của {nd['nguoi']} cho đợt {nd['dot']} ({loai}): thêm nữa thì thời gian bị tính hai lần. Gỡ gói đó trước ({cach}) "
                                 "rồi thêm lại. Không ghi gì.")
        moi = _anh_cua(nd)
        for ten, x in khac:
            chung = sorted(moi & _anh_cua(x))
            if chung:
                loai, cach = _loai_va_cach_go(ten, x, tay)
                raise NhapTayLoi(f"Đã có gói {ten} của {nd['nguoi']} (đợt {x.get('dot') or '(không tên)'}, {loai}) trùng {len(chung)} ảnh với bản này "
                                 f"(ví dụ {', '.join(chung[:3])}): một người không gán một ảnh hai lần trong thí nghiệm, nên đây là cùng một lần làm dưới tên đợt khác; "
                                 f"thêm nữa thì thời gian bị tính hai lần. Gỡ gói đó trước ({cach}) rồi thêm lại với đúng tên đợt. Không ghi gì.")
        bd = str(nd.get("bat_dau") or "")
        ddmm = bd[8:10] + bd[5:7] if re.match(r"\d{4}-\d{2}-\d{2}", bd) else None
        try:
            r = goi_kq.ghi_goi(project_root, nd, ddmm=ddmm, thu_muc=THU_MUC)
        except goi_kq.GoiLoi as e:
            raise NhapTayLoi(str(e))
        for ten, cu, fs in _doc_nhap_tay(project_root):
            if ten != r["ten"] and cu.get("phien") == nd["phien"]:
                _chuyen_bo(project_root, ten, fs)
    return r


def bo(project_root, ten):
    """Gỡ MỀM một bản nhập tay: chuyển <ten>.zip/.json từ outputs\\goi_nhom vào outputs\\goi_nhom\\_da_bo\\ (không xoá; muốn tính lại thì chép về). `ten` phải là một tên
    trong liet_ke (không nhận đường dẫn). Trả dict(ten, da_bo=[đường dẫn tương đối mới])."""
    ten = str(ten or "").strip()
    with _LOCK:
        ds = {t: fs for t, _nd, fs in _doc_nhap_tay(project_root)}
        if not ten or ten not in ds:
            raise NhapTayLoi("Chọn một bản nhập tay trong danh sách (danh sách cũ thì bấm Refresh).")
        return dict(ten=ten, da_bo=_chuyen_bo(project_root, ten, ds[ten]))
