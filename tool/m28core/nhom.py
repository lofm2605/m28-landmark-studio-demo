"""Nhóm thí nghiệm (QĐ-006): mỗi người thuộc MỘT nhóm, hai nhóm ĐỘC LẬP (không ghép cặp theo người).

    manual    gán tay hoàn toàn (không có nháp)
    assisted  dùng tool: sửa nháp 50 điểm

File `config/nhom_thi_nghiem.json`: {"nhom": {"P1": "manual" | "assisted", ...}, "bo_anh": "<tên bộ ảnh chung>"}.
File mẫu trong repo để TRỐNG (không đoán ai ở nhóm nào); điền khi cả đội chốt. Hai nhóm phải làm CÙNG bộ ảnh (cùng tên ảnh): `bo_anh` ghi tên đợt/lượt
chung, và phần thống kê kiểm tên ảnh của hai nhóm có khớp không (báo nếu lệch). Chỉ thư viện chuẩn; lỗi file không làm sập: trả danh sách `loi` bằng tiếng Việt.
"""
import json
import os
import re

CONDITIONS = ("manual", "assisted")
NGUOI_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,31}")      # tên người rà bất kỳ (= dong_ho.NGUOI_RE)
FILE_REL = os.path.join("config", "nhom_thi_nghiem.json")
VI = {"manual": "Gán tay hoàn toàn (manual)", "assisted": "Dùng tool, sửa nháp (assisted)"}
BO_ANH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def doc(project_root="."):
    """dict(nhom={người: điều kiện}, bo_anh, co_file, loi=[...]). Thiếu file hoặc file mẫu trống: nhom rỗng, không lỗi. Người hay nhóm sai thì bỏ dòng đó và ghi vào `loi`."""
    path = os.path.join(project_root, FILE_REL)
    out = dict(nhom={}, bo_anh="", co_file=False, loi=[], duong_dan=FILE_REL)
    if not os.path.isfile(path):
        return out
    out["co_file"] = True
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        out["loi"].append(f"{FILE_REL} không đọc được ({type(e).__name__}): sửa cho đúng JSON hoặc chép lại từ file mẫu.")
        return out
    if not isinstance(raw, dict):
        out["loi"].append(f"{FILE_REL} sai định dạng (cần đối tượng JSON có khoá nhom và bo_anh).")
        return out
    nhom = raw.get("nhom")
    if nhom is not None and not isinstance(nhom, dict):
        out["loi"].append(f"{FILE_REL}: khoá nhom phải là đối tượng {{\"P1\": \"manual\", ...}}.")
        nhom = {}
    for ng, cd in (nhom or {}).items():
        if not isinstance(ng, str) or not (NGUOI_RE.fullmatch(ng) or re.fullmatch(r"[A-Za-z0-9_-]{1,32}", ng)):     # cả tên cũ có dấu _ (bản trước): không bỏ dòng đã ghi
            out["loi"].append(f"{FILE_REL}: người {ng!r} không hợp lệ (chỉ chữ không dấu, số và dấu -, bắt đầu bằng chữ hoặc số, tối đa 32 ký tự), bỏ dòng này.")
        elif cd not in CONDITIONS:
            out["loi"].append(f"{FILE_REL}: nhóm {cd!r} của {ng} không hợp lệ (chỉ manual hoặc assisted), bỏ dòng này.")
        else:
            out["nhom"][ng] = cd
    ba = raw.get("bo_anh")
    if ba not in (None, ""):
        if isinstance(ba, str) and BO_ANH_RE.fullmatch(ba):
            out["bo_anh"] = ba
        else:
            out["loi"].append(f"{FILE_REL}: bo_anh {ba!r} không hợp lệ (chữ không dấu, số, _ - . , tối đa 64 ký tự), bỏ qua.")
    return out


def nhom_cua(cfg, nguoi):
    """Nhóm của người theo file cấu hình, hoặc None nếu chưa có."""
    return (cfg or {}).get("nhom", {}).get(nguoi)


def dem_nguoi(cfg):
    """{manual: n, assisted: n} số người đã được xếp nhóm trong file cấu hình."""
    out = {c: 0 for c in CONDITIONS}
    for cd in (cfg or {}).get("nhom", {}).values():
        out[cd] += 1
    return out
