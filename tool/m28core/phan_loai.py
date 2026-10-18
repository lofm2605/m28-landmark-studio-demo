"""Phân loại mặt của một lượt thành Nhận / Sửa nhãn / Bỏ / Đã xoá: MỘT hàm thuần dùng chung cho steps.push và trang rà soát
(hộp xác nhận "Đẩy lên CVAT" đếm bằng đúng hàm này, không viết lại logic). Chỉ thư viện chuẩn, không đọc file.

Cũng chứa các hàm đọc thuần dùng chung (read_triage, read_no_face) để trang rà soát và steps đọc đúng như nhau.
"""
import csv
import io
import math
import os

DECISIONS = ("nhan", "gan_tay", "bo")
IMG_EXT = (".png", ".jpg", ".jpeg")


def stem(name):
    """Tên không đuôi ảnh (đuôi .png/.jpg/.jpeg); tên khác giữ nguyên."""
    base, ext = os.path.splitext(str(name).strip())
    return base if ext.lower() in IMG_EXT else str(name).strip()


def read_triage(path):
    """{tên không đuôi: (quyết định, lý do)}. Chịu BOM, dấu ; của Excel, có/không dòng tiêu đề; dòng sau đè dòng trước."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    first = text.splitlines()[0] if text.strip() else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    ci, di, ri = 0, 1, 2
    if rows and "decision" in [c.strip().lower() for c in rows[0]]:
        h = [c.strip().lower() for c in rows.pop(0)]
        ci, di, ri = h.index("name") if "name" in h else 0, h.index("decision"), h.index("reason") if "reason" in h else -1
    latest = {}
    for r in rows:
        if r[0].strip().lower() == "name":
            continue
        get = lambda i: r[i].strip() if 0 <= i < len(r) else ""      # noqa: E731
        latest[stem(r[ci])] = (get(di).lower(), get(ri))
    return latest


def read_no_face(run_dir):
    """{tên: lý do} từ no_face.csv (một tên chỉ một dòng, dù nằm ở bước nào), CHƯA trừ mặt xoá mềm."""
    path = os.path.join(run_dir, "no_face.csv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return {r["name"]: r["reason"] for r in reversed(rows)}


def _hai_so_huu_han(v):
    """True khi v là danh sách/bộ đúng 2 số hữu hạn (không bool, không None, không NaN/inf)."""
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        return False
    return all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in v)


def nhap_hop_le(entry, point_names=None):
    """Nháp của máy (một phần tử của mp50.json) có dùng được cho mặt Sửa nhãn không: `entry` là dict có "orig" là dict, có đủ mọi tên
    trong point_names (None thì đòi đúng 50 khoá), mỗi giá trị là 2 số hữu hạn. Chỉ thư viện chuẩn."""
    if not isinstance(entry, dict) or not isinstance(entry.get("orig"), dict):
        return False
    orig = entry["orig"]
    if point_names is None:
        if len(orig) != 50:
            return False
        keys = list(orig)
    else:
        keys = list(point_names)
        if not keys or any(k not in orig for k in keys):
            return False
    return all(_hai_so_huu_han(orig[k]) for k in keys)


def classify(triage, meta, mp50, no_face, excluded=frozenset(), point_names=None):
    """triage {tên: (quyết định, lý do)}; meta/mp50 chứa khoá tên (đúng thứ tự meta.json); no_face {tên: lý do}; excluded: tên bị xoá mềm.

    Trả dict:
      nhan      mặt chọn Nhận và có nháp (mp50), theo thứ tự meta
      tay       mặt chọn Sửa nhãn, và mặt chọn Nhận nhưng không có nháp (đưa sang Sửa nhãn), theo thứ tự: tay_nhap rồi tay_trong
      tay_nhap  Sửa nhãn CÓ nháp hợp lệ (nhap_hop_le): lên CVAT kèm nháp 50 điểm, low_conf=true ở điểm có cờ (steps.tay_low_conf), theo thứ tự meta
      tay_trong Sửa nhãn ẢNH TRỐNG (không có nháp, hoặc nháp không hợp lệ; gồm cả nhan_khong_nhap), theo thứ tự meta
      nhan_khong_nhap  tên các mặt chọn Nhận nhưng không có nháp (cảnh báo)
      lost      mặt chọn Sửa nhãn nhưng không có ảnh cắt (không tải lên được)
      rejected  [(tên, lý do)] mặt Bỏ (kèm mặt no_face chưa có quyết định)
      removed   [(tên, "da_xoa")] mặt bị xoá mềm (không tải lên)
    Mặt bị xoá mềm không bao giờ nằm trong nhan/tay/lost/rejected."""
    excluded = set(excluded)
    dec = lambda n: triage.get(n, ("", ""))[0]                    # noqa: E731
    names = [n for n in meta if n not in excluded]
    nhan = [n for n in names if dec(n) == "nhan" and n in mp50]
    tay_all = [n for n in names if dec(n) == "gan_tay" or (dec(n) == "nhan" and n not in mp50)]
    tay_nhap = [n for n in tay_all if n in mp50 and nhap_hop_le(mp50[n], point_names)]
    co_nhap = set(tay_nhap)
    tay_trong = [n for n in tay_all if n not in co_nhap]
    tay = tay_nhap + tay_trong
    no_draft = [n for n in names if dec(n) == "nhan" and n not in mp50]
    lost = [n for n in no_face if n not in meta and n not in excluded and dec(n) == "gan_tay"]
    rejected = [(n, triage[n][1]) for n in triage if dec(n) == "bo" and n not in excluded] + \
               [(n, why) for n, why in no_face.items() if dec(n) not in DECISIONS and n not in excluded]
    universe = set(meta) | set(no_face) | set(triage)
    removed = [(n, "da_xoa") for n in sorted(excluded & universe)]
    return dict(nhan=nhan, tay=tay, tay_nhap=tay_nhap, tay_trong=tay_trong, nhan_khong_nhap=no_draft, lost=lost, rejected=rejected, removed=removed)


def n_jobs(n_nhan, n_tay, job_size=0):
    """Số job dự kiến: một job cho tất cả mặt Nhận (job_size=0) hoặc các nhóm job_size mặt Nhận, + một job Sửa nhãn riêng (nếu có)."""
    n_nhan_jobs = (-(-n_nhan // job_size) if job_size else (1 if n_nhan else 0))
    return n_nhan_jobs + (1 if n_tay else 0)
