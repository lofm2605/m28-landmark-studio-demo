"""Đặt tên người cho từng gói kết quả (nhóm trưởng, tab Thống kê): biết gói nào của ai khi báo cáo.

Mỗi gói có mã phiên (`phien`, duy nhất) và tên người do máy của người làm đặt (thường là mặc định P1 nếu quên đổi). Nhóm trưởng gán lại tên người cho từng gói; bảng đặt
tên nằm ở outputs/ten_nguoi.json: {mã phiên: {"ten": tên mới, "goi": tên file gói, "goc": tên người gốc}}. Thống kê (thong_ke.tinh, tong_ket.py) dùng tên mới
cho mọi số theo người; file gói gốc KHÔNG bị sửa. Hai gói được đặt cùng một tên thì tính là một người. Tên theo quy tắc của tên người rà: chỉ chữ không dấu, số và dấu -, bắt đầu bằng chữ hoặc số, tối đa 32 ký tự.
"""
import json
import os
import re

from m28core import cvat_io, goi_kq

FILE_REL = os.path.join("outputs", "ten_nguoi.json")          # KHÔNG để trong outputs/thong_ke: thư mục đó trang phát qua URL (bản xuất để tải)
FILE_REL_CU = os.path.join("outputs", "thong_ke", "ten_nguoi.json")  # chỗ cũ (bản đầu): còn đọc khi chưa có file mới, ghi lần sau thì chuyển hẳn


TEN_CU_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")          # đọc: nhận cả tên đặt bằng bản đầu (có "_", ví dụ Lan_2); tên chỉ để hiển thị trong thống kê, không vào tên file


class TenNguoiLoi(ValueError):
    pass


def _path(project_root):
    return os.path.join(project_root, FILE_REL)


def doc(project_root):
    """{mã phiên: {ten, goi, goc}}; thiếu file, file hỏng hay dòng sai thì bỏ (không bao giờ ném lỗi)."""
    p = _path(project_root)
    if not os.path.exists(p) and os.path.exists(os.path.join(project_root, FILE_REL_CU)):
        p = os.path.join(project_root, FILE_REL_CU)
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for ph, v in (raw.get("ten") if isinstance(raw, dict) and isinstance(raw.get("ten"), dict) else {}).items():
        if isinstance(ph, str) and goi_kq.PHIEN_RE.fullmatch(ph) and isinstance(v, dict) and isinstance(v.get("ten"), str) and TEN_CU_RE.fullmatch(v["ten"]):
            out[ph] = dict(ten=v["ten"], goi=str(v.get("goi") or "")[:160], goc=str(v.get("goc") or "")[:32])
    return out


def _ghi(project_root, m):
    p = _path(project_root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    cvat_io.atomic_write_json(p, {"phien_ban": 1, "ten": m})
    cu = os.path.join(project_root, FILE_REL_CU)
    if os.path.exists(cu):
        try:
            os.remove(cu)                                  # đã chép sang chỗ mới (không bị trang phát qua URL)
        except OSError:
            pass


def dat(project_root, phien, ten, goi="", goc=""):
    """Gán tên người `ten` cho gói có mã phiên `phien`. Trả tên đã chuẩn hoá. Sai thì TenNguoiLoi, không ghi gì."""
    ten = (ten or "").strip() if isinstance(ten, str) else ""
    if not isinstance(phien, str) or not goi_kq.PHIEN_RE.fullmatch(phien):
        raise TenNguoiLoi("Chưa chọn gói để đặt tên.")
    if not goi_kq.NGUOI_RE.fullmatch(ten):
        raise TenNguoiLoi("Tên người chỉ chữ không dấu, số và dấu -, bắt đầu bằng chữ hoặc số, tối đa 32 ký tự (ví dụ Cuong, P2, Lan-2).")
    m = doc(project_root)
    m[phien] = dict(ten=ten, goi=str(goi or "")[:160], goc=str(goc or "")[:32])
    _ghi(project_root, m)
    return ten


def bo(project_root, phien):
    """Bỏ tên đã đặt của gói (về lại tên người gốc trong gói). Trả True nếu có bỏ."""
    m = doc(project_root)
    if phien not in m:
        return False
    del m[phien]
    _ghi(project_root, m)
    return True


def ap_dung(goi_ok, m):
    """goi_ok: [(tên file, nội dung gói)]; trả bản mới với nd['nguoi'] đổi theo bảng `m` (không sửa đối tượng cũ), cộng [(tên file, tên gốc, tên mới)] cho các gói bị đổi."""
    out, doi = [], []
    for t, nd in goi_ok:
        e = m.get(nd.get("phien"))
        if e and e["ten"] != nd.get("nguoi"):
            doi.append((t, nd.get("nguoi"), e["ten"]))
            nd = dict(nd, nguoi=e["ten"], nguoi_goc=nd.get("nguoi"))
        out.append((t, nd))
    return out, doi
