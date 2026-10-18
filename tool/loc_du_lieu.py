"""Bộ lọc dữ liệu train/finetune cho một model landmark KHÁC sau này (MediaPipe không train được; chưa có bước train trong repo, file này KHÔNG train gì).

    python tool\\loc_du_lieu.py --cau-hinh config\\loc_mau.json --dry-run
    python tool\\loc_du_lieu.py --cau-hinh outputs\\loc_cua_toi.json --ten finetune_v1 [--ghi-de] [--zip]

Nguồn: ảnh đã có nhãn 50 điểm sửa tay (raw\\, final\\) do bảng mặt (m28core.bang_mat) đọc. Mỗi mặt đi qua các tiêu chí theo thứ tự cố định; bộ lọc chỉ ĐỌC runs\\, raw\\,
final\\, data\\ và chỉ GHI dưới outputs\\train_sets\\<tên>\\ (ngoài git). --dry-run in bảng số lượng (vào, bị loại theo lý do, còn lại) và không ghi file nào.
Mã thoát: 0 xong, 1 không còn mặt nào, 2 lỗi cấu hình/dữ liệu (kể cả một tài xế nằm ở hai phần train/val/test: không ghi gì).

LUẬT CỨNG (không tắt được): mặt nguồn không rõ (khong_ro: lượt Nạp ảnh hoặc không khớp manifest, có thể là ảnh khách hàng) luôn bị loại; mặt xoá mềm luôn bị loại; mặt
chưa có nhãn sửa tay không vào bộ train; mặt `Bỏ` bị loại; mặt thiếu mã người (subject) không kiểm được rò rỉ. triage_auto (máy tự quyết) không phải quyết định của người.
Chia train/val/test theo tập gốc của manifest (cách chia theo người của inc_ingest.py: F, Tdev, Ttest đôi một không chung người; G, P, X, D không chung người với nhóm A),
rồi KIỂM LẠI trên chính bộ xuất bằng cột subject. Mặc định tiêu chí "chọn ca khó" (cờ, NME nháp, cờ manifest, quyết định, điều kiện, low_conf trong nhãn, độ lệch hai
nhãn) chỉ áp lên train; val/test chỉ qua luật cứng và vệ sinh nhãn (đủ điểm). Ttest là tập đo một lần của đề tài: không dùng số trên Ttest để chỉnh ngưỡng lọc.
"""
import argparse
import copy
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import ca_kho  # noqa: E402  (_formula_safe, csv_text, _atomic_write: chỉ thư viện chuẩn)
import nap_anh  # noqa: E402
from m28core import bang_mat  # noqa: E402

TEN_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")
SERVE_REL = ("outputs", "train_sets")
PHAN = ("train", "val", "test")
QUYET_DINH = ("nhan", "gan_tay", "bo")
NGUON = ("yawdd", "drivface")
DIEU_KIEN = ("manual", "assisted", "khong_ro_dieu_kien")
LOAI_MAT = ("nhan", "gan_tay_co_nhap", "gan_tay_trong")
CO_NGUON = ("flags_json", "tinh_lai")
SET_CHIA_MAC_DINH = {"train": ["F", "G", "P", "X", "D"], "val": ["Tdev"], "test": ["Ttest"]}     # cách chia của inc_ingest.py
FLAGS_MANIFEST = bang_mat.FLAGS_MANIFEST
CHUOI_MANIFEST = ("camera", "glasses", "state", "gender")

MAC_DINH = {
    "ten": "bo_loc",
    "nguon_nhan": {"luot": [], "file_nhan": [], "luot_nhap": None, "uu_tien": list(bang_mat.UU_TIEN_MAC_DINH)},
    "nguon_du_lieu": list(NGUON),
    "set_goc": [],
    "quyet_dinh": ["nhan", "gan_tay"],
    "nguoi_ra": [],
    "co": {"nguon": "flags_json", "t_flip": None, "tong": {"toi_thieu": None, "toi_da": None}, "theo_nhom": {}, "theo_vung": {}},
    "nme_nhap": {"toi_thieu": None, "toi_da": None},
    "manifest": {k: None for k in FLAGS_MANIFEST + ("camera", "glasses", "state")},
    "nhan": {"so_diem_thieu_toi_da": 0, "low_conf_trong_nhan_toi_da": None, "lech_nhan_toi_da": None, "dieu_kien": [], "loai_mat": []},
    "giu_mat_khong_nhap": False,
    "chia": {"train": SET_CHIA_MAC_DINH["train"], "val": SET_CHIA_MAC_DINH["val"], "test": SET_CHIA_MAC_DINH["test"], "loc_tap_danh_gia": False},
    "kem_anh": True,
    "zip": False,
}

# (mã, tên tiếng Việt) theo ĐÚNG thứ tự thác nước
LY_DO = [
    ("khong_ro", "Nguồn không rõ (có thể là ảnh khách hàng) — luật cứng"),
    ("xoa_mem", "Đã xoá mềm — luật cứng"),
    ("khong_co_nhan", "Chưa có nhãn sửa tay — luật cứng"),
    ("thieu_subject", "Thiếu mã người (subject) nên không kiểm được rò rỉ — luật cứng"),
    ("bo_anh", "Quyết định Bỏ ảnh"),
    ("anh_thieu", "Không có ảnh cắt để đưa vào gói"),
    ("nguon", "Ngoài nguồn dữ liệu đã chọn"),
    ("set_goc", "Ngoài các tập gốc (set) đã chọn"),
    ("set_ngoai_chia", "Tập gốc không thuộc phần train/val/test nào"),
    ("thieu_diem", "Nhãn thiếu quá nhiều điểm"),
    ("quyet_dinh", "Quyết định/người rà không đạt"),
    ("dieu_kien", "Điều kiện/loại mặt của nhãn không đạt"),
    ("co_khong_do_duoc", "Cờ low_conf: không đo được (không có nháp/cờ)"),
    ("co_ngoai_khoang", "Cờ low_conf ngoài khoảng cho phép"),
    ("nme_khong_do_duoc", "NME nháp: không đo được (không có nháp hoặc không chấm được)"),
    ("nme_ngoai_khoang", "NME nháp ngoài khoảng cho phép"),
    ("manifest", "Cờ/thuộc tính manifest không đạt"),
    ("low_conf_nhan", "Còn nhiều low_conf bật trong nhãn đã sửa"),
    ("lech_nhan", "Hai nhãn người lệch nhau quá nhiều"),
    ("trung_mat", "Trùng mặt (cùng tên manifest ở lượt/nhãn khác, đã giữ bản tốt hơn)"),
]
LY_DO_VI = dict(LY_DO)
CODES = [c for c, _ in LY_DO]
CUNG = {"khong_ro", "xoa_mem", "khong_co_nhan", "thieu_subject", "bo_anh", "anh_thieu", "nguon", "set_goc", "set_ngoai_chia", "thieu_diem"}   # áp cho mọi phần
CHI_TRAIN = set(CODES) - CUNG - {"trung_mat"}


class CauHinhLoi(Exception):
    """Cấu hình lọc sai: thông điệp tiếng Việt nói rõ khoá nào."""


class DuLieuLoi(Exception):
    """Lỗi dữ liệu (rò rỉ người giữa hai phần, đường dẫn ngoài dự án...)."""


class KhongConMat(DuLieuLoi):
    """Sau khi lọc không còn mặt nào."""


# ---------- kiểm cấu hình ----------
def _loi(khoa, msg):
    raise CauHinhLoi(f"Cấu hình lọc, khoá {khoa}: {msg}")


def _dict(v, khoa, ok):
    if not isinstance(v, dict):
        _loi(khoa, "phải là một đối tượng {...}.")
    la = sorted(set(v) - set(ok))
    if la:
        _loi(khoa, f"khoá lạ {la[0]!r} (khoá hợp lệ: {', '.join(ok)}).")
    return v


def _so(v, khoa, kieu=float, nguyen=False):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        _loi(khoa, f"phải là số hoặc null (đang là {v!r}).")
    if nguyen and float(v) != int(v):
        _loi(khoa, f"phải là số nguyên (đang là {v!r}).")
    return int(v) if nguyen else float(v)


def _khoang(v, khoa, nguyen=False, am=False):
    d = _dict(v if v is not None else {}, khoa, ("toi_thieu", "toi_da"))
    lo, hi = _so(d.get("toi_thieu"), khoa + ".toi_thieu", nguyen=nguyen), _so(d.get("toi_da"), khoa + ".toi_da", nguyen=nguyen)
    if not am and ((lo is not None and lo < 0) or (hi is not None and hi < 0)):
        _loi(khoa, "không được âm.")
    if lo is not None and hi is not None and lo > hi:
        _loi(khoa, f"toi_thieu ({lo:g}) lớn hơn toi_da ({hi:g}).")
    return {"toi_thieu": lo, "toi_da": hi}


def _list_str(v, khoa, ok=None):
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
        _loi(khoa, "phải là danh sách chuỗi.")
    if ok is not None:
        bad = [x for x in v if x not in ok]
        if bad:
            _loi(khoa, f"giá trị lạ {bad[0]!r} (hợp lệ: {', '.join(ok)}).")
    return list(dict.fromkeys(v))


def _bool(v, khoa):
    if not isinstance(v, bool):
        _loi(khoa, f"phải là true/false (đang là {v!r}).")
    return v


def kiem_cau_hinh(raw, groups, regions):
    """Cấu hình đã kiểm + điền mặc định (bản sao). groups/regions: tên nhóm/vùng hợp lệ lấy từ config 50 điểm. Sai thì CauHinhLoi."""
    if not isinstance(raw, dict):
        raise CauHinhLoi("Cấu hình lọc phải là một đối tượng JSON {...}.")
    d = _dict(raw, "(gốc)", tuple(MAC_DINH))
    out = copy.deepcopy(MAC_DINH)
    if "ten" in d:
        if not isinstance(d["ten"], str) or not TEN_RE.fullmatch(d["ten"]):
            _loi("ten", "chỉ chữ không dấu, số, _ và -, tối đa 40 ký tự.")
        out["ten"] = d["ten"]
    if "nguon_nhan" in d:
        n = _dict(d["nguon_nhan"], "nguon_nhan", tuple(MAC_DINH["nguon_nhan"]))
        o = out["nguon_nhan"]
        o["luot"] = _list_str(n.get("luot"), "nguon_nhan.luot")
        o["file_nhan"] = _list_str(n.get("file_nhan"), "nguon_nhan.file_nhan")
        ln = n.get("luot_nhap")
        if ln is not None and (not isinstance(ln, str) or not nap_anh.RUN_RE.fullmatch(ln)):
            _loi("nguon_nhan.luot_nhap", "phải là tên lượt hợp lệ hoặc null.")
        o["luot_nhap"] = ln
        if "uu_tien" in n:
            o["uu_tien"] = _list_str(n["uu_tien"], "nguon_nhan.uu_tien", ("final", "manual", "assisted", "khong_ro_dieu_kien"))
    if "nguon_du_lieu" in d:
        out["nguon_du_lieu"] = _list_str(d["nguon_du_lieu"], "nguon_du_lieu", NGUON)
        if not out["nguon_du_lieu"]:
            _loi("nguon_du_lieu", "không được rỗng (chọn yawdd và/hoặc drivface; nguồn không rõ luôn bị loại).")
    out["set_goc"] = _list_str(d.get("set_goc"), "set_goc")
    if "quyet_dinh" in d:
        out["quyet_dinh"] = _list_str(d["quyet_dinh"], "quyet_dinh", QUYET_DINH)
    out["nguoi_ra"] = _list_str(d.get("nguoi_ra"), "nguoi_ra")
    for w in out["nguoi_ra"]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", w) or w == bang_mat.AUTO:
            _loi("nguoi_ra", f"{w!r} không phải tên người rà hợp lệ (triage_auto là máy tự quyết, không tính).")
    if "co" in d:
        c = _dict(d["co"], "co", tuple(MAC_DINH["co"]))
        o = out["co"]
        if "nguon" in c:
            if c["nguon"] not in CO_NGUON:
                _loi("co.nguon", f"phải là một trong {', '.join(CO_NGUON)}.")
            o["nguon"] = c["nguon"]
        o["t_flip"] = _so(c.get("t_flip"), "co.t_flip")
        if o["t_flip"] is not None and o["t_flip"] < 0:
            _loi("co.t_flip", "không được âm.")
        if o["nguon"] == "tinh_lai" and o["t_flip"] is None:
            _loi("co.t_flip", "nguon = tinh_lai cần đặt t_flip (số, ví dụ 0.06): tính lại cờ từ điểm số lật.")
        o["tong"] = _khoang(c.get("tong"), "co.tong", nguyen=True)
        for key, ok in (("theo_nhom", groups), ("theo_vung", regions)):
            v = c.get(key) or {}
            if not isinstance(v, dict):
                _loi(f"co.{key}", "phải là đối tượng {tên: {toi_thieu, toi_da}}.")
            bad = [k for k in v if k not in ok]
            if bad:
                _loi(f"co.{key}", f"tên lạ {bad[0]!r} (hợp lệ: {', '.join(ok)}).")
            o[key] = {k: _khoang(v[k], f"co.{key}.{k}", nguyen=True) for k in ok if k in v}
    out["nme_nhap"] = _khoang(d.get("nme_nhap"), "nme_nhap")
    if "manifest" in d:
        m = _dict(d["manifest"], "manifest", tuple(MAC_DINH["manifest"]))
        for k, v in m.items():
            if v is None:
                continue
            if k in FLAGS_MANIFEST:
                vv = v if isinstance(v, list) else [v]
                if not vv or any(isinstance(x, bool) or x not in (0, 1) for x in vv):
                    _loi(f"manifest.{k}", "phải là 0, 1, [0, 1] hoặc null.")
                out["manifest"][k] = sorted(set(int(x) for x in vv))
            else:
                out["manifest"][k] = _list_str(v if isinstance(v, list) else [v], f"manifest.{k}")
    if "nhan" in d:
        n = _dict(d["nhan"], "nhan", tuple(MAC_DINH["nhan"]))
        o = out["nhan"]
        o["so_diem_thieu_toi_da"] = _so(n.get("so_diem_thieu_toi_da", 0), "nhan.so_diem_thieu_toi_da", nguyen=True)
        o["low_conf_trong_nhan_toi_da"] = _so(n.get("low_conf_trong_nhan_toi_da"), "nhan.low_conf_trong_nhan_toi_da", nguyen=True)
        o["lech_nhan_toi_da"] = _so(n.get("lech_nhan_toi_da"), "nhan.lech_nhan_toi_da")
        for k in ("so_diem_thieu_toi_da", "low_conf_trong_nhan_toi_da", "lech_nhan_toi_da"):
            if o[k] is not None and o[k] < 0:
                _loi(f"nhan.{k}", "không được âm.")
        o["dieu_kien"] = _list_str(n.get("dieu_kien"), "nhan.dieu_kien", DIEU_KIEN)
        o["loai_mat"] = _list_str(n.get("loai_mat"), "nhan.loai_mat", LOAI_MAT)
    if "giu_mat_khong_nhap" in d:
        out["giu_mat_khong_nhap"] = _bool(d["giu_mat_khong_nhap"], "giu_mat_khong_nhap")
    if "chia" in d:
        c = _dict(d["chia"], "chia", tuple(MAC_DINH["chia"]))
        for ph in PHAN:
            if ph in c:
                out["chia"][ph] = _list_str(c[ph], f"chia.{ph}")
        if "loc_tap_danh_gia" in c:
            out["chia"]["loc_tap_danh_gia"] = _bool(c["loc_tap_danh_gia"], "chia.loc_tap_danh_gia")
        seen = {}
        for ph in PHAN:
            for s in out["chia"][ph]:
                if s in seen:
                    _loi("chia", f"tập {s!r} nằm ở cả {seen[s]} và {ph}: một tập chỉ thuộc một phần.")
                seen[s] = ph
        if not out["chia"]["train"]:
            _loi("chia.train", "không được rỗng.")
    for k in ("kem_anh", "zip"):
        if k in d:
            out[k] = _bool(d[k], k)
    return out


def doc_cau_hinh(path, groups, regions):
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f)
    except OSError as e:
        raise CauHinhLoi(f"Không đọc được file cấu hình lọc ({type(e).__name__}).")
    except ValueError as e:
        raise CauHinhLoi(f"File cấu hình lọc không phải JSON hợp lệ ({e}).")
    return kiem_cau_hinh(raw, groups, regions)


# ---------- đánh giá từng mặt ----------
def _ngoai(v, lo, hi):
    return (lo is not None and v < lo) or (hi is not None and v > hi)


def _phan_cua(cfg, set_):
    for ph in PHAN:
        if set_ in cfg["chia"][ph]:
            return ph
    return ""


def duong_anh(project_root, r):
    """Đường dẫn ảnh cắt của mặt: lượt -> runs\\<lượt>\\crop\\images\\<mặt>.png; mặt chỉ có nhãn -> data\\crops\\<mặt>.png. None nếu không có."""
    if r["luot"]:
        p = os.path.join(project_root, "runs", r["luot"], "crop", "images", r["mat"] + ".png")
    else:
        p = os.path.join(project_root, "data", "crops", r["mat"] + ".png")
    return p if os.path.isfile(p) and nap_anh._inside(p, project_root) else None


def danh_gia_mat(bang, r, cfg, project_root):
    """dict(loi {mã: chi tiết}, phan, nhan, quyet_dinh, nguoi_ra, n_co...). `loi` gồm MỌI tiêu chí áp dụng mà mặt không đạt (để đếm chồng lấn);
    mặt bị loại ở bước đầu tiên theo thứ tự LY_DO. Tiêu chí chọn ca khó chỉ áp lên train (trừ khi chia.loc_tap_danh_gia)."""
    loi, phan = {}, _phan_cua(cfg, r["set"])
    co_mat = bang_mat.co_cua_mat(bang, r, cfg["co"]["nguon"], cfg["co"]["t_flip"])
    ap_dung_kho = phan == "train" or cfg["chia"]["loc_tap_danh_gia"]
    nhan = bang_mat.chon_nhan(r, cfg["nguon_nhan"]["uu_tien"])
    dec, who = bang_mat.quyet_dinh_cuoi(r, cfg["nguoi_ra"])
    giu = cfg["giu_mat_khong_nhap"]
    if r["nguon"] not in bang_mat.NGUON_OK:
        loi["khong_ro"] = r["nguon"]
    if r["xoa_mem"]:
        loi["xoa_mem"] = ""
    if nhan is None:
        loi["khong_co_nhan"] = ""
    if not r["subject"]:
        loi["thieu_subject"] = ""
    if dec == "bo" and ("bo" not in cfg["quyet_dinh"] or phan != "train"):        # val/test không bao giờ nhận mặt Bỏ
        loi["bo_anh"] = who
    if cfg["kem_anh"] and duong_anh(project_root, r) is None:
        loi["anh_thieu"] = ""
    if r["nguon"] in bang_mat.NGUON_OK and r["nguon"] not in cfg["nguon_du_lieu"]:
        loi["nguon"] = r["nguon"]
    if cfg["set_goc"] and r["set"] not in cfg["set_goc"]:
        loi["set_goc"] = r["set"]
    if not phan:
        loi["set_ngoai_chia"] = r["set"]
    if nhan is not None and nhan["n_thieu"] > cfg["nhan"]["so_diem_thieu_toi_da"]:
        loi["thieu_diem"] = nhan["n_thieu"]
    if ap_dung_kho:
        has_run = bool(r["luot"])
        # quyết định rà và người rà (mặt không có lượt = không có triage: không đo được)
        if cfg["quyet_dinh"] or cfg["nguoi_ra"]:
            if not has_run:
                if not giu:
                    loi["quyet_dinh"] = "không có lượt"
            elif not dec or (cfg["quyet_dinh"] and dec not in cfg["quyet_dinh"]):
                loi["quyet_dinh"] = dec or "chưa rà"
        if nhan is not None:
            if (cfg["nhan"]["dieu_kien"] and nhan["dieu_kien"] not in cfg["nhan"]["dieu_kien"]) or \
                    (cfg["nhan"]["loai_mat"] and nhan["loai_mat"] not in cfg["nhan"]["loai_mat"]):
                loi["dieu_kien"] = f"{nhan['dieu_kien']}/{nhan['loai_mat']}"
        # cờ low_conf
        co = cfg["co"]
        yeu_cau_co = co["tong"]["toi_thieu"] is not None or co["tong"]["toi_da"] is not None or co["theo_nhom"] or co["theo_vung"]
        n_co, n_nhom, n_vung = co_mat
        if yeu_cau_co:
            if n_co is None:
                if not giu:
                    loi["co_khong_do_duoc"] = ""
            else:
                bad = []
                if _ngoai(n_co, co["tong"]["toi_thieu"], co["tong"]["toi_da"]):
                    bad.append(f"tong={n_co}")
                for k, kh in co["theo_nhom"].items():
                    if _ngoai(n_nhom[k], kh["toi_thieu"], kh["toi_da"]):
                        bad.append(f"{k}={n_nhom[k]}")
                for k, kh in co["theo_vung"].items():
                    if _ngoai(n_vung[k], kh["toi_thieu"], kh["toi_da"]):
                        bad.append(f"{k}={n_vung[k]}")
                if bad:
                    loi["co_ngoai_khoang"] = ", ".join(bad)
        # NME của nháp so với nhãn
        nm = cfg["nme_nhap"]
        if nm["toi_thieu"] is not None or nm["toi_da"] is not None:
            s = nhan["nme"] if nhan is not None else None
            if not s or not s.get("ok"):
                if not giu:
                    loi["nme_khong_do_duoc"] = ""
            elif _ngoai(s["nme"], nm["toi_thieu"], nm["toi_da"]):
                loi["nme_ngoai_khoang"] = f"{s['nme']:.2f}"
        # cờ/thuộc tính manifest
        bad = []
        for k, ok in cfg["manifest"].items():
            if ok is None or (isinstance(ok, list) and not ok):
                continue
            v = r.get(k)
            if k in FLAGS_MANIFEST:
                if v is None or v not in ok:
                    bad.append(f"{k}={v}")
            elif str(v or "") not in ok:
                bad.append(f"{k}={v or ''}")
        if bad:
            loi["manifest"] = ", ".join(bad)
        if nhan is not None:
            lim = cfg["nhan"]["low_conf_trong_nhan_toi_da"]
            if lim is not None and nhan["n_low_conf_bat"] > lim:
                loi["low_conf_nhan"] = nhan["n_low_conf_bat"]
            lim = cfg["nhan"]["lech_nhan_toi_da"]
            if lim is not None and r.get("lech_nhan") is not None and r["lech_nhan"] > lim:
                loi["lech_nhan"] = f"{r['lech_nhan']:.2f}"
    return dict(loi=loi, phan=phan, nhan=nhan, quyet_dinh=dec, nguoi_ra=who, co=co_mat)


# ---------- chạy lọc ----------
class KetQua:
    """Kết quả một lần lọc: bang, cfg, mat (list dict gồm row + đánh giá + trạng thái), giu (list đã giữ), tong, thac, tung_tieu_chi, canh_bao, ro_ri."""


def lay_bang(project_root, cfg):
    n = cfg["nguon_nhan"]
    return bang_mat.dung_bang(project_root, runs=n["luot"] or None, luot_nhap=n["luot_nhap"], file_nhan=n["file_nhan"])


def _tot_hon(a, b, uu_tien):
    """True nếu mặt a tốt hơn b khi cùng tên manifest: nhãn ưu tiên cao hơn, rồi nhãn mới hơn, rồi lượt có tên lớn hơn (ổn định)."""
    def key(m):
        e = m["dg"]["nhan"]
        return (-bang_mat.hang_nhan(e, uu_tien), bang_mat._ngay_key(e["ngay"]), e["file"], m["row"]["luot"])
    return key(a) > key(b)


def chay_loc(project_root, cfg, bang=None):
    """Lọc. Chỉ đọc. Trả KetQua; KHÔNG ghi gì. Phát hiện rò rỉ người giữa các phần trên bộ còn lại (ro_ri: {subject: [phần...]})."""
    bang = bang or lay_bang(project_root, cfg)
    kq = KetQua()
    kq.bang, kq.cfg, kq.project_root = bang, cfg, project_root
    mat = [dict(row=r, dg=danh_gia_mat(bang, r, cfg, project_root)) for r in bang.rows]
    kq.thac = {c: 0 for c in CODES}
    kq.tung_tieu_chi = {c: 0 for c in CODES}
    for m in mat:
        m["ly_do"] = next((c for c in CODES if c in m["dg"]["loi"]), "")
        for c in m["dg"]["loi"]:
            kq.tung_tieu_chi[c] += 1
    # trùng mặt: cùng tên manifest, giữ bản tốt hơn
    best = {}
    for m in mat:
        if m["ly_do"]:
            continue
        k = m["row"]["mat"]
        if k in best:
            if _tot_hon(m, best[k], cfg["nguon_nhan"]["uu_tien"]):
                best[k]["ly_do"], best[k]["dg"]["loi"]["trung_mat"] = "trung_mat", ""
                best[k] = m
            else:
                m["ly_do"], m["dg"]["loi"]["trung_mat"] = "trung_mat", ""
        else:
            best[k] = m
    kq.tung_tieu_chi["trung_mat"] = sum(1 for m in mat if m["ly_do"] == "trung_mat")
    for m in mat:
        if m["ly_do"]:
            kq.thac[m["ly_do"]] += 1
    kq.mat = mat
    kq.giu = sorted((m for m in mat if not m["ly_do"]), key=lambda m: (m["dg"]["phan"], m["row"]["mat"]))
    kq.tong = len(mat)
    sub = {}
    for m in kq.giu:
        sub.setdefault(m["row"]["subject"], set()).add(m["dg"]["phan"])
    kq.ro_ri = {s: sorted(p) for s, p in sorted(sub.items()) if len(p) > 1}
    kq.canh_bao = list(bang.warnings)
    if cfg["co"]["nguon"] == "flags_json" and (cfg["co"]["tong"]["toi_thieu"] or any(v["toi_thieu"] for v in cfg["co"]["theo_nhom"].values())):
        allf = [r for r, i in bang.runs.items() if i["co_toan_false"]]
        if allf:
            kq.canh_bao.append(f"Tiêu chí cờ đòi toi_thieu > 0 nhưng lượt {', '.join(sorted(allf))} có mọi cờ = false (t_flip = null lúc chạy): "
                               "mặt của lượt đó sẽ bị loại hết; dùng co.nguon = tinh_lai với t_flip cụ thể.")
    if cfg["giu_mat_khong_nhap"]:
        kq.canh_bao.append("giu_mat_khong_nhap = true: mặt không có nháp/cờ/lượt được giữ dù tiêu chí cờ, NME, quyết định không đo được.")
    return kq


def dem_theo(kq, key):
    """Số mặt còn lại theo giá trị của cột `key` của hàng (nguon, luot, set...): {giá trị: {phần: n}}."""
    out = {}
    for m in kq.giu:
        d = out.setdefault(m["row"][key], {})
        d[m["dg"]["phan"]] = d.get(m["dg"]["phan"], 0) + 1
    return out


def bang_so_luong_text(kq):
    """Bảng số lượng tiếng Việt cho --dry-run và tab: vào, thác nước, từng tiêu chí, còn lại theo phần/nguồn/lượt."""
    L = [f"Vào: {kq.tong} mặt ((lượt, mặt) trong bảng; {kq.bang.mat_duy_nhat()} mặt duy nhất theo tên manifest)", "", "Bị loại theo thứ tự tiêu chí (cộng lại = vào − còn lại):"]
    for c, vi in LY_DO:
        if kq.thac[c]:
            L.append(f"  {kq.thac[c]:5d}  {vi}")
    L.append(f"  còn lại: {len(kq.giu)}")
    L += ["", "Số mặt không đạt TỪNG tiêu chí (chồng lấn, một mặt có thể không đạt nhiều tiêu chí):"]
    L += [f"  {kq.tung_tieu_chi[c]:5d}  {vi}" for c, vi in LY_DO if kq.tung_tieu_chi[c]] or ["  (không có)"]
    L += ["", "Còn lại theo phần: " + (", ".join(f"{ph} {sum(1 for m in kq.giu if m['dg']['phan'] == ph)}" for ph in PHAN)),
          "Còn lại theo nguồn: " + (", ".join(f"{k} {sum(d.values())}" for k, d in sorted(dem_theo(kq, 'nguon').items())) or "—"),
          "Còn lại theo lượt: " + (", ".join(f"{k or '(chỉ có nhãn)'} {sum(d.values())}" for k, d in sorted(dem_theo(kq, 'luot').items())) or "—")]
    if kq.ro_ri:
        L += ["", f"LỖI: {len(kq.ro_ri)} tài xế (subject) nằm ở hơn một phần train/val/test (rò rỉ người): không được ghi bộ dữ liệu."]
    for w in kq.canh_bao:
        L.append("Cảnh báo: " + w)
    return "\n".join(L)


# ---------- ghi gói ----------
def png_size(path):
    """(rộng, cao) của ảnh PNG đọc từ IHDR; không phải PNG thì dùng PIL (nạp lười). None nếu không đọc được."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def serve_dir(project_root):
    return os.path.join(project_root, *SERVE_REL)


def duong_goi(project_root, ten):
    """outputs\\train_sets\\<tên> (kiểm tên và realpath + commonpath). Sai thì DuLieuLoi."""
    if not isinstance(ten, str) or not TEN_RE.fullmatch(ten):
        raise DuLieuLoi(f"Tên bộ {ten!r} không hợp lệ: chỉ chữ không dấu, số, _ và -, tối đa 40 ký tự (không có /, \\ hay ..).")
    base = serve_dir(project_root)
    p = os.path.join(base, ten)
    if not nap_anh._inside(p, base):
        raise DuLieuLoi("Đường dẫn bộ dữ liệu nằm ngoài outputs\\train_sets: từ chối.")
    return p


def _git_commit(project_root):
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=project_root, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "không rõ"
    except (OSError, subprocess.SubprocessError):
        return "không rõ"


def _f2(v):
    return f"{v:.2f}"


def _hang_manifest(kq, m):
    r, dg, e = m["row"], m["dg"], m["dg"]["nhan"]
    bang = kq.bang
    n_co, n_nhom, _ = dg["co"]
    d = dict(id=r["mat"], anh=f"anh/{r['mat']}.png" if kq.cfg["kem_anh"] else "", split=dg["phan"], nguon=r["nguon"], subject=r["subject"], set_goc=r["set"],
             luot=r["luot"], mat=r["mat"], task=e["task"], file_nhan=e["file"], nguoi_gan=e["nguoi"], dieu_kien=e["dieu_kien"], loai_mat=e["loai_mat"],
             quyet_dinh=dg["quyet_dinh"], nguoi_ra=dg["nguoi_ra"], n_co="" if n_co is None else n_co)
    for g in bang.groups:
        d[f"n_co_{g}"] = "" if n_nhom is None else n_nhom[g]
    d["nme_nhap"] = _f2(e["nme"]["nme"]) if e["nme"] and e["nme"].get("ok") else ""
    for k in FLAGS_MANIFEST + ("camera", "glasses", "state"):
        d[k] = "" if r.get(k) is None else r[k]
    p = duong_anh(kq.project_root, r)
    wh = png_size(p) if p else None
    d["w"], d["h"] = (wh if wh else ("", ""))
    pts = e["pts"]
    d["n_diem_thieu"] = e["n_thieu"]
    d["n_low_conf_nhan"] = e["n_low_conf_bat"]
    d["n_ngoai_anh"] = sum(1 for q in pts if q is not None and wh and not (0 <= q[0] <= wh[0] and 0 <= q[1] <= wh[1])) if wh else ""
    d["lech_nhan"] = "" if r.get("lech_nhan") is None else _f2(r["lech_nhan"])
    return d


def _bytes_csv(cols, rows):
    """CSV utf-8-sig, ô chữ an toàn công thức (ca_kho.csv_text); rows là dict hoặc list theo thứ tự cột."""
    rows = [dict(zip(cols, r)) if isinstance(r, (list, tuple)) else r for r in rows]
    return ca_kho.csv_text(cols, rows, safe=True).encode("utf-8-sig")


def ghi_bo(kq, ten, ghi_de=False, zip_=None, now=None):
    """Ghi outputs\\train_sets\\<tên>\\ (vào thư mục tạm cùng cấp rồi os.replace). Từ chối khi đã có (trừ ghi_de), khi không còn mặt nào, hoặc khi có rò rỉ người.
    Trả dict(path, rel, so_mat, theo_phan, zip). Cùng đầu vào + cùng cấu hình -> manifest.csv, nhan.*, *.txt giống hệt từng byte (ngày giờ chỉ ở README)."""
    if kq.ro_ri:
        raise DuLieuLoi(f"{len(kq.ro_ri)} tài xế (subject) nằm ở hơn một phần train/val/test (rò rỉ người), ví dụ "
                        f"{next(iter(kq.ro_ri))}: {', '.join(next(iter(kq.ro_ri.values())))}. Sửa chia.* rồi chạy lại; không ghi bộ dữ liệu.")
    if not kq.giu:
        raise KhongConMat("Không còn mặt nào sau khi lọc: nới tiêu chí hoặc kiểm nguồn nhãn (--dry-run để xem lý do).")
    cfg, project_root = kq.cfg, kq.project_root
    dest = duong_goi(project_root, ten)
    zip_ = cfg["zip"] if zip_ is None else zip_
    if os.path.exists(dest) and not ghi_de:
        raise DuLieuLoi(f"Bộ {ten!r} đã có ({os.path.join(*SERVE_REL, ten)}): đổi tên hoặc thêm --ghi-de.")
    base = serve_dir(project_root)
    os.makedirs(base, exist_ok=True)
    tmp = os.path.join(base, f".tmp_{ten}_{os.getpid()}")
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    try:
        bang = kq.bang
        manifest_rows = [_hang_manifest(kq, m) for m in kq.giu]
        cols = list(manifest_rows[0])
        files = {"manifest.csv": _bytes_csv(cols, manifest_rows)}
        names = bang.names
        anh = {}
        csv_rows = []
        for m, mr in zip(kq.giu, manifest_rows):
            e = m["dg"]["nhan"]
            anh[mr["id"]] = [None if p is None else [round(p[0], 2), round(p[1], 2)] for p in e["pts"]]
            row = {"id": mr["id"]}
            for n, p in zip(names, e["pts"]):
                row[f"x_{n}"], row[f"y_{n}"], row[f"v_{n}"] = ("", "", 0) if p is None else (_f2(p[0]), _f2(p[1]), 1)
            for n, v in zip(names, e["low_conf"]):
                row[f"low_conf_{n}"] = "" if v is None else int(bool(v))
            csv_rows.append(row)
        nhan_cols = ["id"] + [f"{k}_{n}" for n in names for k in ("x", "y", "v")] + [f"low_conf_{n}" for n in names]
        files["nhan.csv"] = _bytes_csv(nhan_cols, csv_rows)
        files["nhan.json"] = (json.dumps({"points": names, "groups": bang_mat.cvat_io.groups_from_names(names), "iod_points": bang.cfg["iod_points"],
                                          "config_version": bang.cfg.get("version"), "he_toa_do": "anh_cat_512_cua_luot", "anh": anh},
                                         ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        for ph in PHAN:
            files[f"{ph}.txt"] = "".join(f"{r['anh'] or r['id']}\n" for r in manifest_rows if r["split"] == ph).encode("utf-8")
        files["cau_hinh_loc.json"] = (json.dumps(cfg, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        md, rep_rows = bao_cao(kq)
        files["bao_cao_loc.md"] = md.encode("utf-8")
        files["bao_cao_loc.csv"] = _bytes_csv(["loai", "chi_tiet", "so_mat"], rep_rows)
        theo_phan = {ph: sum(1 for r in manifest_rows if r["split"] == ph) for ph in PHAN}
        files["README.md"] = readme(kq, ten, theo_phan, now).encode("utf-8")
        for fn, data in files.items():
            with open(os.path.join(tmp, fn), "wb") as f:
                f.write(data)
        if cfg["kem_anh"]:
            os.makedirs(os.path.join(tmp, "anh"))
            for m in kq.giu:
                shutil.copyfile(duong_anh(project_root, m["row"]), os.path.join(tmp, "anh", m["row"]["mat"] + ".png"))      # chép nguyên byte
        old = None
        if os.path.exists(dest):
            old = os.path.join(base, f".old_{ten}_{os.getpid()}")
            os.replace(dest, old)
        os.replace(tmp, dest)
        if old:
            shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    out = dict(path=dest, rel="/".join(SERVE_REL + (ten,)), so_mat=len(kq.giu), theo_phan=theo_phan, zip=None)
    if zip_:
        zp = dest + ".zip"
        tz = zp + f".tmp{os.getpid()}"
        with zipfile.ZipFile(tz, "w", zipfile.ZIP_DEFLATED) as z:
            for dp, dn, fn in os.walk(dest):
                dn.sort()
                for f in sorted(fn):
                    full = os.path.join(dp, f)
                    z.write(full, os.path.join(ten, os.path.relpath(full, dest)).replace(os.sep, "/"))
        os.replace(tz, zp)
        out["zip"] = zp
    return out


def bao_cao(kq):
    """(markdown, các dòng CSV): bao nhiêu mặt bị loại vì sao, hai cách đếm (thác nước và từng tiêu chí), theo phần/nguồn/lượt. Tất định (không có ngày giờ)."""
    rows = [["vao", "", kq.tong]]
    md = ["# Báo cáo lọc dữ liệu", "", f"Vào: **{kq.tong}** (lượt, mặt); còn lại **{len(kq.giu)}**.", "",
          "## Bị loại theo thứ tự tiêu chí (thác nước: tổng các bước = vào − còn lại)", "", "| Lý do | Số mặt |", "| --- | ---: |"]
    for c, vi in LY_DO:
        rows.append(["thac_nuoc:" + c, vi, kq.thac[c]])
        if kq.thac[c]:
            md.append(f"| {vi} | {kq.thac[c]} |")
    rows.append(["con_lai", "", len(kq.giu)])
    md += [f"| **Còn lại** | **{len(kq.giu)}** |", "", "## Số mặt không đạt từng tiêu chí (chồng lấn)", "", "| Tiêu chí | Số mặt |", "| --- | ---: |"]
    for c, vi in LY_DO:
        rows.append(["tung_tieu_chi:" + c, vi, kq.tung_tieu_chi[c]])
        if kq.tung_tieu_chi[c]:
            md.append(f"| {vi} | {kq.tung_tieu_chi[c]} |")
    md += ["", "## Còn lại theo phần, nguồn, lượt", "", "| Phần | Số mặt |", "| --- | ---: |"]
    for ph in PHAN:
        n = sum(1 for m in kq.giu if m["dg"]["phan"] == ph)
        rows.append(["theo_phan", ph, n])
        md.append(f"| {ph} | {n} |")
    for key, tieu in (("nguon", "Nguồn"), ("luot", "Lượt")):
        md += ["", f"| {tieu} | Số mặt |", "| --- | ---: |"]
        for k, d in sorted(dem_theo(kq, key).items()):
            rows.append([f"theo_{key}", k or "(chỉ có nhãn)", sum(d.values())])
            md.append(f"| {k or '(chỉ có nhãn)'} | {sum(d.values())} |")
    if kq.canh_bao:
        md += ["", "## Cảnh báo", ""] + [f"- {w}" for w in kq.canh_bao]
    return "\n".join(md) + "\n", rows


def readme(kq, ten, theo_phan, now=None):
    now = now or datetime.datetime.now().astimezone()
    cfg = kq.cfg
    return f"""# Bộ dữ liệu train/finetune `{ten}`

**Dữ liệu nhạy cảm — chỉ dùng nội bộ nhóm.** Gói này chứa ảnh mặt người lái xe thật. Dự án M28 là **phi thương mại** (học tập/nghiên cứu): **không phát tán,
không đăng lại, không giao bên thứ ba**, không đưa vào git, dịch vụ bên ngoài hay báo cáo/slide công khai (trừ ảnh của video YawDD có "Allow Researchers to use picture in their paper" = Yes).

- Ngày tạo: {now.strftime('%d/%m/%Y %H:%M')} · commit git của công cụ: {_git_commit(kq.project_root)} · config 50 điểm version {kq.bang.config_version}
- Số mặt: train {theo_phan['train']}, val {theo_phan['val']}, test {theo_phan['test']} (tổng {sum(theo_phan.values())})
- Chia theo **tập gốc của manifest** (cách chia theo người của `inc_ingest.py`): train = {', '.join(cfg['chia']['train'])}; val = {', '.join(cfg['chia']['val']) or '—'};
  test = {', '.join(cfg['chia']['test']) or '—'}. Đã kiểm trên chính bộ này bằng cột `subject`: không tài xế nào nằm ở hai phần.
- Tiêu chí "chọn ca khó" {'áp cả cho val/test' if cfg['chia']['loc_tap_danh_gia'] else 'chỉ áp lên train; val/test chỉ qua luật cứng và vệ sinh nhãn (đủ điểm)'}.
  **Ttest là tập đo một lần của đề tài: không dùng số trên Ttest để chỉnh ngưỡng lọc.**
- Hệ toạ độ (`he_toa_do`): **ảnh cắt 512×512 của lượt** (`anh/<mặt>.png`, chép nguyên từ `runs\\<lượt>\\crop\\images`); nhãn nằm trong hệ đó, thứ tự 50 điểm theo config.
  `n_ngoai_anh` trong `manifest.csv` đếm điểm rơi ngoài ảnh (giữ nguyên toạ độ).
- Nhãn: do người sửa trong CVAT (raw\\/final\\); `nhan.csv` có `v_<điểm>` = 1 nếu có điểm, 0 nếu thiếu; `low_conf_<điểm>` lấy từ nhãn đã sửa.
- File: `manifest.csv`, `nhan.json`, `nhan.csv`, `train.txt`, `val.txt`, `test.txt`, `cau_hinh_loc.json` (cấu hình đã dùng), `bao_cao_loc.md`/`.csv` (vì sao mặt bị loại), `anh\\`.

## Nguồn và giấy phép

- **DrivFace** (UCI): "This database is free for academic usage"; mục đích khác liên hệ tác giả. Trích dẫn: Diaz-Chito, Hernández-Sabaté, López,
  *A reduced feature set for driver head pose estimation*, Applied Soft Computing 45 (2016) 98-107.
- **YawDD**: video chỉ cho mục đích phi thương mại và nghiên cứu; bắt buộc trích dẫn S. Abtahi, M. Omidyeganeh, S. Shirmohammadi, B. Hariri,
  "YawDD: A Yawning Detection Dataset", Proc. ACM Multimedia Systems, 2014; chỉ được đăng ảnh của video có "Allow Researchers to use picture in their paper" = Yes.
- Nhãn 50 điểm do nhóm gán trong CVAT; nháp ban đầu từ MediaPipe Face Landmarker (Apache-2.0).
"""


# ---------- CLI ----------
def _config_groups(project_root):
    cfg = bang_mat.load_cfg(project_root)
    return bang_mat.groups_of(cfg), bang_mat.regions_of(cfg)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Lọc dữ liệu train/finetune từ ảnh đã có nhãn sửa tay (chỉ chuẩn bị dữ liệu, KHÔNG train). "
                                             "Đọc runs\\, raw\\, final\\, data\\; chỉ ghi outputs\\train_sets\\<tên>\\.")
    ap.add_argument("--cau-hinh", required=True, help="file cấu hình lọc JSON (mẫu: config\\loc_mau.json)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in bảng số lượng (vào, bị loại theo lý do, còn lại), không ghi file nào")
    ap.add_argument("--ten", help="tên bộ dữ liệu (mặc định lấy khoá ten của cấu hình)")
    ap.add_argument("--ghi-de", action="store_true", help="cho phép ghi đè bộ cùng tên")
    ap.add_argument("--zip", action="store_true", help="thêm outputs\\train_sets\\<tên>.zip (chứa ảnh mặt: chỉ gửi trong đội)")
    ap.add_argument("--project", default=bang_mat.mac_dinh_du_an(), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        groups, regions = _config_groups(a.project)
        cfg = doc_cau_hinh(a.cau_hinh, groups, regions)
        if a.ten:
            cfg["ten"] = kiem_cau_hinh({"ten": a.ten}, groups, regions)["ten"]
        kq = chay_loc(a.project, cfg)
        print(bang_so_luong_text(kq))
        if a.dry_run:
            print("\nChạy thử (--dry-run): không ghi file nào.")
            return 0 if kq.giu and not kq.ro_ri else (2 if kq.ro_ri else 1)
        info = ghi_bo(kq, cfg["ten"], ghi_de=a.ghi_de, zip_=True if a.zip else None)
    except (CauHinhLoi, DuLieuLoi, bang_mat.BangLoi) as e:
        if isinstance(e, KhongConMat):
            print(f"\n{e}", file=sys.stderr)
            return 1
        print(f"\nLỗi: {e}", file=sys.stderr)
        return 2
    print(f"\nĐã ghi {info['rel']} ({info['so_mat']} mặt: " + ", ".join(f"{k} {v}" for k, v in info["theo_phan"].items()) + ")")
    if info["zip"]:
        print("Đã ghi " + "/".join(SERVE_REL) + f"/{cfg['ten']}.zip — chứa ảnh mặt người lái xe: chỉ gửi trong đội, không đưa lên git hay dịch vụ bên ngoài.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
