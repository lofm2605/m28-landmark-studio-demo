"""Bảng mặt: MỘT lớp ĐỌC dữ liệu dùng chung cho bộ lọc dữ liệu train (loc_du_lieu.py) và trang Thống kê (thong_ke.py).

Mỗi dòng là một (lượt, mặt): định danh, thông tin manifest (nguồn, người, tập gốc, các cờ), nháp của máy và cờ low_conf, kết quả rà soát của từng người,
các nhãn sửa tay (raw\\, final\\) ghép được vào mặt đó, và sai số của nháp so với nhãn (eval50). Chỉ ĐỌC: không ghi, không sửa runs\\, raw\\, final\\, data\\.

Quy ước:
  * Đầu module chỉ thư viện chuẩn (và các module tool/ cũng chỉ thư viện chuẩn); numpy, eval50, flag_eval, steps nạp lười trong hàm.
    Không import gradio, torch, cv2, mediapipe, cvat_sdk; không gọi mạng.
  * Tái dùng hàm có sẵn: dot_anh (đợt, push.json, mp50, cờ), loai_tru (xoá mềm), phan_loai (nháp hợp lệ, no_face), ca_kho.run_source (nguồn của lượt),
    collect (tên file raw, mới nhất mỗi người), cvat_io (đọc nhãn), eval50 (sai số), flag_eval (điểm số lật), steps (tên ảnh CVAT, hệ toạ độ).
  * Thứ tự 50 điểm LUÔN theo config (moingoai_10 đứng sau moingoai_9, không sắp theo chữ cái).

Nguồn nhãn sửa tay (xem TAI-LIEU-CHI-TIET.md, mục Thống kê và lọc dữ liệu train):
  1. Lượt có push.json (task demo-...): nhãn = raw\\<task>\\<task>_<người>_<DDMM>.xml mới nhất của mỗi người; có final\\ cùng mẫu tên thì final\\ ưu tiên.
     Mặt Nhận -> loai_mat "nhan" (dieu_kien assisted); Sửa nhãn có nháp -> "gan_tay_co_nhap" (assisted); Sửa nhãn còn lại -> "gan_tay_trong" (manual).
  2. File nhãn không gắn push.json (task thí nghiệm m28-manual, m28-assisted, m28-pilot-*, m28-gold-*): điều kiện suy từ tên task
     (manual/gold -> manual, assisted -> assisted; practice/check/smoke bị bỏ qua; không rõ -> khong_ro_dieu_kien). Chỉ có nháp khi người dùng nêu `luot_nhap`.
  3. Một mặt có nhiều nhãn: giữ hết; chọn một nhãn theo ưu tiên final > manual > assisted, rồi mới nhất.
"""
import csv
import glob
import io
import json
import os
import re
import sys
import threading

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import ca_kho  # noqa: E402  (run_source, _formula_safe: chỉ thư viện chuẩn)
import dot_anh  # noqa: E402
import nap_anh  # noqa: E402
from m28core import collect, cvat_io, loai_tru, phan_loai  # noqa: E402

NGUON_OK = ("yawdd", "drivface")                               # nguồn là bộ nghiên cứu đã chọn (QĐ-001)
KHONG_RO = "khong_ro"
FLAGS_MANIFEST = ("pose", "expression", "illumination", "makeup", "occlusion", "blur")
SO_MANIFEST = ("yaw", "pitch", "roll", "jaw_open", "luma", "contrast", "lap_var")
TEXT_MANIFEST = ("set", "camera", "subject", "gender", "glasses", "state", "block", "seq", "video")
BO_QUA_TASK = ("practice", "check", "smoke")                  # task thử, không phải nhãn thí nghiệm
DIEU_KIEN_KHONG_RO = "khong_ro_dieu_kien"
GIAY_TOI_DA_MAT = 120.0                                        # > ngần này giây/mặt: có thể nghỉ giữa chừng (dùng ở thong_ke)
UU_TIEN_MAC_DINH = ("final", "manual", "assisted")
AUTO = "auto"                                                  # triage_auto.csv: máy tự quyết, KHÔNG phải người rà


class BangLoi(Exception):
    """Lỗi người dùng sửa được (thiếu config, đường dẫn sai...). Thông điệp tiếng Việt."""


# ---------- tiện ích ----------
def _num(v):
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def _int01(v):
    x = _num(v)
    return None if x is None else int(x != 0)


def rel(project_root, path):
    """Đường dẫn tương đối (dấu /) của path so với thư mục dự án; ngoài dự án thì chỉ tên file. Không bao giờ lộ đường dẫn tuyệt đối của máy."""
    try:
        p, b = os.path.realpath(path), os.path.realpath(project_root)
        if os.path.commonpath([p, b]) == b:
            return os.path.relpath(p, b).replace(os.sep, "/")
    except ValueError:
        pass
    return os.path.basename(path)


def mac_dinh_du_an():
    """Thư mục gốc dự án mặc định của các CLI: thư mục hiện tại nếu có config\\m28_config.json (chạy từ source-tool\\m28-prelabel hoặc một thư mục chạy riêng), không thì thư mục
    chứa tool\\ (bản m28-prelabel đang chạy)."""
    cwd = os.getcwd()
    return cwd if os.path.isfile(os.path.join(cwd, "config", "m28_config.json")) else os.path.dirname(TOOL_DIR)


def load_cfg(project_root):
    p = os.path.join(project_root, "config", "m28_config.json")
    try:
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
        [pt["name"] for pt in cfg["points"]]
        cfg["iod_points"]
        return cfg
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise BangLoi(f"Không đọc được config\\m28_config.json ({type(e).__name__}): chạy từ thư mục source-tool\\m28-prelabel.")


def groups_of(cfg):
    """Nhóm theo thứ tự xuất hiện trong config."""
    return list(dict.fromkeys(p.get("group") or cvat_io.group_of_name(p["name"]) for p in cfg["points"]))


def regions_of(cfg):
    return list(dict.fromkeys(p["region"] for p in cfg["points"]))


def group_idx(cfg):
    """{nhóm: [chỉ số điểm]} theo thứ tự config."""
    out = {}
    for i, p in enumerate(cfg["points"]):
        out.setdefault(p.get("group") or cvat_io.group_of_name(p["name"]), []).append(i)
    return out


def region_idx(cfg):
    out = {}
    for i, p in enumerate(cfg["points"]):
        out.setdefault(p["region"], []).append(i)
    return out


# ---------- manifest ----------
_MAN = {}
_MAN_LOCK = threading.Lock()


def read_manifest(project_root):
    """{tên mặt không đuôi: dict các cột (chuỗi)} từ data\\manifest.csv; không có hoặc hỏng thì {} (đọc lại khi file đổi)."""
    p = os.path.join(project_root, "data", "manifest.csv")
    try:
        st = os.stat(p)
    except OSError:
        return {}
    key = (st.st_mtime_ns, st.st_size)
    with _MAN_LOCK:
        c = _MAN.get(p)
        if c and c[0] == key:
            return c[1]
    out = {}
    try:
        with open(p, encoding="utf-8-sig", newline="") as f:
            text = f.read()
        for r in csv.DictReader(io.StringIO(text), delimiter=ca_kho._delim(text)):
            name = (r.get("file") or "").strip()
            if name:
                out[name[:-4] if name.lower().endswith(".png") else name] = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
    except (OSError, csv.Error, UnicodeDecodeError):
        out = {}
    with _MAN_LOCK:
        _MAN[p] = (key, out)
    return out


def man_fields(m):
    """Trường manifest của một mặt (None/'' nếu thiếu)."""
    r = {"trong_manifest": bool(m)}
    for c in TEXT_MANIFEST:
        r[c] = (m or {}).get(c, "")
    r["set"] = (m or {}).get("set", "")
    for c in FLAGS_MANIFEST:
        r[c] = _int01((m or {}).get(c))
    for c in SO_MANIFEST:
        r[c] = _num((m or {}).get(c))
    return r


def nguon_mat(m):
    s = ((m or {}).get("source") or "").strip().lower()
    return s if s in NGUON_OK else KHONG_RO


# ---------- hệ toạ độ ----------
def den_khung_cat(pts, src, dst):
    """Đổi điểm [(x, y) | None] từ khung `src` sang khung `dst`. Khung = (left, top, k): cắt = (p - [left, top]) * k, tính từ ảnh vào;
    ảnh vào = (0, 0, 1). Đổi qua toạ độ ảnh vào: p = cắt / k + [left, top]. Giữ None."""
    (l1, t1, k1), (l2, t2, k2) = src, dst
    out = []
    for p in pts:
        if p is None:
            out.append(None)
            continue
        x, y = p[0] / k1 + l1, p[1] / k1 + t1
        out.append([(x - l2) * k2, (y - t2) * k2])
    return out


def _frame(m):
    try:
        return float(m["left"]), float(m["top"]), float(m["k"])
    except (KeyError, TypeError, ValueError):
        return None


# ---------- tên task, điều kiện ----------
def dieu_kien_tu_task(task):
    """('manual'|'assisted'|'bo_qua'|'khong_ro_dieu_kien', lý do). Dựa trên các mẩu chữ của tên task (tách ở - và _)."""
    toks = set(re.split(r"[-_.]+", str(task).lower()))
    if toks & set(BO_QUA_TASK):
        return "bo_qua", "task thử (practice/check/smoke), không phải nhãn thí nghiệm"
    man, ass = bool(toks & {"manual", "gold"}), "assisted" in toks
    if man and not ass:
        return "manual", ""
    if ass and not man:
        return "assisted", ""
    return DIEU_KIEN_KHONG_RO, "tên task không nói rõ manual hay assisted"


# ---------- đọc nhãn ----------
def tim_file_nhan(project_root, file_nhan=()):
    """[dict(task, who, day, path, kind, rel)] mỗi (task, người) một file: final\\ ưu tiên hơn raw\\, trong cùng thư mục thì mới nhất theo ngày (collect.latest_raw_files).
    file_nhan: đường dẫn thêm (trong dự án); tên không khớp mẫu raw thì task = tên file, người = '?'."""
    got = {}
    for kind in ("raw", "final"):
        d = os.path.join(project_root, kind)
        if not os.path.isdir(d):
            continue
        tasks = sorted({m.group("task") for m in (collect.RAW_RE.match(f) for _d, f in collect.raw_listing(d)) if m})      # <d>\\<task>\\ và <d>\\
        for t in tasks:
            for who, p in collect.latest_raw_files(t, d).items():
                got.setdefault((t, who), {})[kind] = p
    out = []
    for (t, who), kinds in sorted(got.items()):
        kind = "final" if "final" in kinds else "raw"
        p = kinds[kind]
        out.append(dict(task=t, who=who, day=collect.RAW_RE.match(os.path.basename(p)).group("day"), path=p, kind=kind))
    seen = {o["path"] for o in out}
    for x in file_nhan or ():
        p = x if os.path.isabs(x) else os.path.join(project_root, x)
        if not nap_anh._inside(p, project_root):
            raise BangLoi(f"File nhãn {x!r} nằm ngoài thư mục dự án: từ chối.")
        if not os.path.isfile(p):
            raise BangLoi(f"Không thấy file nhãn {x!r}.")
        if p in seen:
            continue
        m = collect.RAW_RE.match(os.path.basename(p))
        out.append(dict(task=m.group("task") if m else os.path.splitext(os.path.basename(p))[0], who=m.group("who") if m else "?",
                        day=m.group("day") if m else "", path=p, kind="khac"))
        seen.add(p)
    for o in out:
        o["rel"] = rel(project_root, o["path"])
    return out


def _doc_nhan(path, cfg):
    """({tên ảnh không đuôi: {tên điểm: [x, y]}}, {tên ảnh: {tên điểm: low_conf bool|None}}, số ảnh nhãn cũ, cảnh báo, lỗi|None)."""
    import eval50
    warns = []
    try:
        pts = eval50.read_labels(path, cfg, warn=warns.append)
        if str(path).lower().endswith(".zip"):
            raw = cvat_io.read_zip_annotations(path)
        else:
            with open(path, "rb") as f:
                raw = f.read()
        ann = cvat_io.parse_annotations(raw, [p["name"] for p in cfg["points"]])
    except (SystemExit, OSError) as e:
        return {}, {}, 0, warns, str(e) or type(e).__name__
    groups = {g: set(v) for g, v in cvat_io.groups_from_names([p["name"] for p in cfg["points"]]).items()}
    low, n_cu = {}, 0
    for name, im in ann.items():
        key = eval50.stem(name)
        sk = [s for s in im["skeletons"] if s["label"] in groups]
        if im["skeletons"] and not any(set(s["points"]) & groups[s["label"]] for s in sk):
            n_cu += 1                                   # label face50 cũ hoặc tên điểm v2: không dùng được với config hiện tại
            continue
        d = {}
        for s in sk:
            for n, p in s["points"].items():
                if n in groups[s["label"]]:
                    d[n] = None if p.get("low_conf") is None else p.get("low_conf") == "true"
        low[key] = d
    return pts, low, n_cu, warns, None


# ---------- một lượt ----------
def _jc(path):
    return dot_anh._cached(path, dot_anh._jload)


def flags_tinh_lai(diem_lat, t_flip, n=50):
    """Cờ của n điểm tính lại từ điểm số lật, ĐÚNG luật steps.flags: t_flip None -> mọi cờ false; mặt không có ảnh lật (diem_lat None) -> mọi cờ true;
    còn lại điểm số > t_flip."""
    if t_flip is None:
        return [False] * n
    if diem_lat is None:
        return [True] * n
    return [bool(s > float(t_flip)) for s in diem_lat]


def read_triage_run(run_dir):
    """{người: {tên mặt: dict(quyet_dinh, ly_do, giay, n_doi, n_dong)}} của mọi review\\triage_<người>.csv (kể cả auto).
    Dòng sau đè dòng trước; quyết định không thuộc nhan/gan_tay/bo (dòng Hoàn tác, trống) = chưa rà. giay = tổng các ô giây có giá trị của mặt;
    n_doi = số lần đổi ý (hai quyết định hợp lệ liên tiếp khác nhau)."""
    import review_app
    out = {}
    for p in sorted(glob.glob(os.path.join(glob.escape(os.path.join(run_dir, "review")), "triage_*.csv"))):
        who = os.path.basename(p)[len("triage_"):-len(".csv")]
        if not who:
            continue
        try:
            rows = review_app.read_rows(p)
        except (OSError, UnicodeDecodeError, ValueError, csv.Error):
            continue
        per = {}
        for r in rows:
            d = per.setdefault(r["name"], dict(quyet_dinh="", ly_do="", giay=None, n_doi=0, n_dong=0, _last=""))
            d["n_dong"] += 1
            dec = r["decision"] if r["decision"] in phan_loai.DECISIONS else ""
            if dec and d["_last"] and dec != d["_last"]:
                d["n_doi"] += 1
            if dec:
                d["_last"] = dec
            d["quyet_dinh"], d["ly_do"] = dec, r["reason"]
            s = _num(r["seconds"])
            if s is not None and s >= 0:
                d["giay"] = (d["giay"] or 0.0) + s
        for d in per.values():
            d.pop("_last", None)
        out[who] = per
    return out


class Bang:
    """Kết quả dựng bảng. rows: list dict (luot, mat, ...). labels: tóm tắt từng file nhãn. runs: tóm tắt từng lượt. warnings: cảnh báo cho người dùng."""

    def __init__(self, project_root, cfg, runs_root=None):
        self.project_root, self.cfg = project_root, cfg
        self.runs_root = runs_root or os.path.join(project_root, "runs")
        self.names = [p["name"] for p in cfg["points"]]
        self.groups = groups_of(cfg)
        self.regions = regions_of(cfg)
        self.rows, self.labels, self.runs, self.warnings = [], [], {}, []
        self.luot_bo_qua = {}          # lượt -> lý do không đọc được
        self.khong_ghep = []           # (file nhãn, tên ảnh, lý do)
        self.t_flip = cfg.get("t_flip")
        self.tolerance = cfg.get("tolerance")
        self.config_version = cfg.get("version")

    def mat_duy_nhat(self, rows=None):
        """Số mặt duy nhất: khoá = tên manifest; mặt không có trong manifest tính theo (lượt, mặt)."""
        return len({(r["mat"] if r["trong_manifest"] else (r["luot"], r["mat"])) for r in (self.rows if rows is None else rows)})


def _run_face_rows(bang, run, man):
    """Các dòng (chưa có nhãn) của một lượt, hoặc [] nếu lượt không đọc được (ghi lý do vào bang.luot_bo_qua)."""
    from m28core import steps
    import flag_eval
    cfg, names = bang.cfg, bang.names
    rd = os.path.join(bang.runs_root, run)
    meta = dot_anh.read_meta(rd)
    mp50 = dot_anh.read_mp50(rd)
    fl = _jc(os.path.join(rd, "flags", "flags.json"))
    fl = fl if isinstance(fl, dict) else {}
    gone = loai_tru.read_excluded(rd)
    nf = phan_loai.read_no_face(rd)
    qc = steps._autoqc_rows(rd) if os.path.exists(os.path.join(rd, "autoqc", "autoqc.csv")) else {}
    tri = read_triage_run(rd)
    mode = steps.read_box_mode(os.path.join(rd, "crop", "box.txt"), "crop")
    first = next(iter(mp50.values()), None)
    if first and isinstance(first.get("orig"), dict) and any(n not in first["orig"] for n in names):
        old = [k for k in first["orig"] if re.match(r"p\d\d_", k)]
        bang.luot_bo_qua[run] = ("tên điểm cũ (version 2, pNN_…, trước QĐ-003): chạy lại prepare --force map50 flags autoqc overlays"
                                 if old else "mp50.json thiếu điểm của config hiện tại")
        return []
    nguon_run = ca_kho.run_source(rd, bang.project_root)
    universe = set(meta) | set(fl) | set(mp50) | set(nf) | set(n for per in tri.values() for n in per) | gone
    universe = {n for n in universe if n}
    nhom_idx, vung_idx = group_idx(cfg), region_idx(cfg)
    rows = []
    for n in sorted(universe):
        m = man.get(n)
        entry = mp50.get(n)
        co_nhap = bool(entry) and phan_loai.nhap_hop_le(entry, names)
        lat = None
        if co_nhap:
            try:
                sc = flag_eval.flip_scores_g(entry, cfg)
                lat = None if sc is None else [s for _r, s, _g in sc]
            except (KeyError, TypeError, ValueError):
                lat = None
        co = fl.get(n)
        co = [bool(x) for x in co] if isinstance(co, list) and len(co) == len(names) else None
        r = dict(luot=run, mat=n, anh_cvat=steps._file_name(n, meta[n], mode) if n in meta else n + ".png",
                 nguon=(nguon_mat(m) if nguon_run != KHONG_RO else KHONG_RO), nguon_luot=nguon_run, **man_fields(m),
                 co_nhap=co_nhap, co_nhap_lat=lat is not None, diem_lat=lat, no_face=nf.get(n, ""), xoa_mem=n in gone,
                 autoqc=qc.get(n, ""), co_may=co, ra={w: v[n] for w, v in tri.items() if n in v}, nhan=[], mode=mode)
        _dem_co(r, nhom_idx, vung_idx, "co_may", "")
        rows.append(r)
    allfalse = [r for r in rows if r["co_may"] is not None]
    bang.runs[run] = dict(luot=run, nguon=nguon_run, mode=mode, n_mat=len(rows), n_nhap=sum(1 for r in rows if r["co_nhap"]),
                          n_xoa_mem=len(gone & universe), co_toan_false=bool(allfalse) and not any(any(r["co_may"]) for r in allfalse),
                          co_inbox=os.path.isdir(os.path.join(rd, "inbox")), nguoi_ra=sorted(tri), meta=meta)
    return rows


def _dem_co(r, nhom_idx, vung_idx, key, suffix):
    """Thêm n_co, n_co_nhom {nhóm: n}, n_co_vung {vùng: n} cho cờ ở r[key] (None thì None)."""
    co = r.get(key)
    r["n_co" + suffix] = None if co is None else sum(co)
    r["n_co_nhom" + suffix] = None if co is None else {g: sum(co[i] for i in ix) for g, ix in nhom_idx.items()}
    r["n_co_vung" + suffix] = None if co is None else {g: sum(co[i] for i in ix) for g, ix in vung_idx.items()}


def co_cua_mat(bang, r, nguon="flags_json", t_flip=None):
    """(n_co, {nhóm: n}, {vùng: n}) theo nguồn cờ. flags_json: cờ máy ghi ở flags.json (None nếu lượt chưa có flags).
    tinh_lai: tính lại từ điểm số lật với t_flip (luật steps.flags; t_flip None -> không tính được: trả None; mặt không có nháp -> None)."""
    if nguon == "flags_json":
        return r["n_co"], r["n_co_nhom"], r["n_co_vung"]
    if not r["co_nhap"] or t_flip is None:
        return None, None, None
    d = {"c": flags_tinh_lai(r["diem_lat"], t_flip, len(bang.names))}
    _dem_co(d, group_idx(bang.cfg), region_idx(bang.cfg), "c", "")
    return d["n_co"], d["n_co_nhom"], d["n_co_vung"]


# ---------- nhãn -> dòng ----------
def _nhan_entry(bang, lf, key, low, loai, dieu_kien, pts_cat):
    low_l = [(low.get(key) or {}).get(n) for n in bang.names]
    return dict(file=lf["rel"], kind=lf["kind"], task=lf["task"], nguoi=lf["who"], ngay=lf["day"], dieu_kien=dieu_kien, loai_mat=loai,
                pts=pts_cat, low_conf=low_l, n_thieu=sum(1 for p in pts_cat if p is None),
                n_low_conf_bat=sum(1 for v in low_l if v), nme=None)


def diem_dict(names, pts):
    return {n: p for n, p in zip(names, pts) if p is not None}


def _cham(bang, pred_pts, label_pts):
    """Sai số của nháp (hoặc nhãn khác) so với nhãn: dict (eval50.face_scores + theo nhóm + hỏng) hoặc None nếu không chấm được (thiếu IOD...)."""
    import eval50
    s = eval50.face_scores(diem_dict(bang.names, pred_pts), diem_dict(bang.names, label_pts), bang.cfg)
    if not s["ok"]:
        return dict(ok=False, ly_do=s["reason"], n_missing=s.get("n_missing", 0))
    err = s["errors"]
    nhom = {}
    for g, ix in group_idx(bang.cfg).items():
        v = [err[bang.names[i]] for i in ix if bang.names[i] in err]
        nhom[g] = sum(v) / len(v) if v else None
    return dict(ok=True, nme=s["nme"], nme_p2p=s["nme_p2p"], nme_eye=s["nme_eye"], vung=s["region"], nhom=nhom, loi_diem=err,
                eye_open_err=s["eye_open_err"], n_missing=s["n_missing"], iod=s["iod"], hong=s["nme"] >= eval50.BAD)


def _ngay_key(d):
    """DDMM -> MMDD để so sánh theo ngày trong năm."""
    d = str(d or "")
    return d[2:] + d[:2] if len(d) == 4 and d.isdigit() else ""


def hang_nhan(e, uu_tien=UU_TIEN_MAC_DINH):
    """Hạng ưu tiên của một nhãn (số nhỏ = ưu tiên hơn): nhãn ở final\\ là 'final', còn lại theo điều kiện (manual/assisted); ngoài danh sách = cuối."""
    cat = "final" if e["kind"] == "final" else e["dieu_kien"]
    return list(uu_tien).index(cat) if cat in uu_tien else len(uu_tien)


def chon_nhan(row, uu_tien=UU_TIEN_MAC_DINH):
    """Một nhãn của mặt: theo thứ tự ưu tiên `uu_tien` (final, manual, assisted), cùng hạng thì mới nhất (ngày DDMM trong tên file, rồi tên file); None nếu không có."""
    labs = row.get("nhan") or []
    if not labs:
        return None
    best = min(hang_nhan(e, uu_tien) for e in labs)
    return max((e for e in labs if hang_nhan(e, uu_tien) == best), key=lambda e: (_ngay_key(e["ngay"]), e["file"]))


def _loai_mat(r, manual_kind, co_nhap_files):
    """(loai_mat, dieu_kien) của một mặt trong task push.json: Sửa nhãn ảnh trống -> manual; Sửa nhãn có nháp -> assisted; còn lại (Nhận) -> assisted."""
    f = r["anh_cvat"]
    if manual_kind.get(f) == "anh_trong":
        return "gan_tay_trong", "manual"
    if manual_kind.get(f) == "co_nhap" or f in co_nhap_files:
        return "gan_tay_co_nhap", "assisted"
    return "nhan", "assisted"


def _gan_nhan(bang, lf, link_run, luot_nhap_run, man, rows_by_key):
    """Ghép một file nhãn vào các dòng. link_run: lượt gắn qua push.json (hoặc None); luot_nhap_run: lượt chứa nháp do người dùng nêu (hoặc None).
    Ghép THEO TÊN ẢNH tải lên CVAT (steps._file_name, như eval50.read_run_pred); không ghép được thì ghi lý do, không đoán."""
    import eval50
    from m28core import steps
    pts_all, low, n_cu, warns, err = _doc_nhan(lf["path"], bang.cfg)
    run = link_run or luot_nhap_run
    info = dict(file=lf["rel"], task=lf["task"], nguoi=lf["who"], ngay=lf["day"], kind=lf["kind"], n_anh=len(pts_all), n_cu=n_cu, luot=run or "",
                dieu_kien="", ghi_chu="", n_khop=0, n_chi_nhan=0, n_khong_ghep=0)
    bang.labels.append(info)
    if err:
        info["ghi_chu"] = f"không đọc được: {err}"
        return
    if any("face50" in w for w in warns):
        info["ghi_chu"] = "nhãn dùng label face50 cũ hoặc tên điểm v2: không đo được bằng config hiện tại"
    elif n_cu:
        info["ghi_chu"] = f"{n_cu} ảnh dùng label/tên điểm cũ (v2): đếm riêng, không dùng"
    dk0, why = dieu_kien_tu_task(lf["task"])
    if not link_run and dk0 == "bo_qua":
        info["dieu_kien"], info["ghi_chu"] = "bo_qua", f"bỏ qua: {why}"
        return
    info["dieu_kien"] = "theo_mat" if link_run else dk0
    rd = os.path.join(bang.runs_root, run) if run else None
    meta = (bang.runs.get(run) or {}).get("meta") or {}
    mode = (bang.runs.get(run) or {}).get("mode", "crop")
    manual_kind, co_nhap_files = {}, set()
    if link_run:
        push = dot_anh.read_push(rd)
        co_nhap_files = set(push.get("gan_tay_co_nhap") or []) if isinstance(push, dict) and isinstance(push.get("gan_tay_co_nhap"), list) else set()
        mlp = os.path.join(rd, "push", "manual_list.txt")
        if os.path.exists(mlp):
            try:
                manual_kind = dict(steps.read_manual_list(mlp))
            except OSError:
                manual_kind = {}
    face_of = {}                                        # tên ảnh nhãn -> (mặt trong lượt, cách ghép)
    for n, m in meta.items():
        face_of.setdefault(eval50.stem(steps._file_name(n, m, mode)), (n, "chinh"))
    for n in meta:
        face_of.setdefault(n, (n, "theo_ten"))          # nhãn đặt tên theo tên manifest (F_001) trong khi ảnh CVAT của lượt auto là tên ảnh gốc
    for key, pd_ in sorted(pts_all.items()):
        pts_up = [pd_.get(n) for n in bang.names]
        if all(p is None for p in pts_up):
            continue
        mat, how = face_of.get(key, (None, None)) if run else (None, None)
        loai, dk = "", dk0
        if mat is None and link_run:
            bang.khong_ghep.append((lf["rel"], key, f"không có mặt nào của lượt {run} có tên ảnh CVAT này"))
            info["n_khong_ghep"] += 1
            continue
        if mat is not None:
            r = rows_by_key.get((run, mat))
            if r is None:
                continue
            m_ = meta.get(mat) or {}
            if mode != "auto":
                src = dst = (0.0, 0.0, 1.0)             # lượt crop: nhãn nằm sẵn trong hệ ảnh cắt của lượt
            else:                                       # lượt auto: nhãn ở hệ ảnh vào (hoặc hệ ảnh cắt manifest nếu ghép theo tên mặt) -> hệ ảnh cắt của lượt
                src = (_frame(man.get(mat) or {}) or (0.0, 0.0, 1.0)) if how == "theo_ten" else (0.0, 0.0, 1.0)
                dst = _frame(m_) or (0.0, 0.0, 1.0)
            pts = den_khung_cat(pts_up, src, dst)
            if link_run:
                loai, dk = _loai_mat(r, manual_kind, co_nhap_files)
        else:
            r = rows_by_key.get(("", key))
            if r is None:
                r = _row_chi_nhan(bang, key, man)
                rows_by_key[("", key)] = r
                bang.rows.append(r)
            pts = pts_up
        e = _nhan_entry(bang, lf, key, low, loai, dk, pts)
        r["nhan"].append(e)
        if mat is not None and r["co_nhap"]:
            pred = _pred_pts(bang, rd, mat)
            if pred is not None:
                e["nme"] = _cham(bang, pred, pts)
        info["n_khop" if mat is not None else "n_chi_nhan"] += 1


def _pred_pts(bang, rd, mat):
    ent = dot_anh.read_mp50(rd).get(mat)
    if not ent or "orig" not in ent:
        return None
    try:
        return [list(map(float, ent["orig"][n])) for n in bang.names]
    except (KeyError, TypeError, ValueError):
        return None


def _row_chi_nhan(bang, key, man):
    m = man.get(key)
    return dict(luot="", mat=key, anh_cvat=key + ".png", nguon=nguon_mat(m), nguon_luot="", **man_fields(m), co_nhap=False, co_nhap_lat=False,
                diem_lat=None, no_face="", xoa_mem=False, autoqc="", co_may=None, ra={}, nhan=[], mode="",
                n_co=None, n_co_nhom=None, n_co_vung=None)


def _tinh_lech_nhan(bang):
    """Mặt có >= 2 nhãn: NME giữa nhãn được chọn (đáp án) và nhãn khác (độ lệch hai người gán); lấy giá trị lớn nhất."""
    for r in bang.rows:
        if len(r["nhan"]) < 2:
            r["lech_nhan"] = None
            continue
        a = chon_nhan(r)
        v = []
        for e in r["nhan"]:
            if e is a:
                continue
            s = _cham(bang, e["pts"], a["pts"])
            if s.get("ok"):
                v.append(s["nme"])
        r["lech_nhan"] = max(v) if v else None


def dung_bang(project_root, runs=None, luot_nhap=None, file_nhan=(), runs_root=None):
    """Dựng bảng mặt. runs: danh sách lượt (None = mọi lượt hợp lệ trong runs\\); luot_nhap: lượt chứa nháp cho nhãn thí nghiệm không có push.json;
    file_nhan: thêm file nhãn (trong dự án). Chỉ đọc."""
    cfg = load_cfg(project_root)
    bang = Bang(project_root, cfg, runs_root)
    man = read_manifest(project_root)
    if not man and os.path.exists(os.path.join(project_root, "data", "manifest.csv")):
        bang.warnings.append("Không đọc được data\\manifest.csv: các mặt coi là không rõ nguồn.")
    elif not man:
        bang.warnings.append("Không có data\\manifest.csv: mọi mặt coi là không rõ nguồn (bộ lọc loại hết); thống kê theo nguồn/người/tập không có.")
    all_runs = dot_anh.list_runs(bang.runs_root)
    use = [r for r in all_runs if runs is None or r in set(runs)]
    if runs is not None:
        miss = sorted(set(runs) - set(all_runs))
        if miss:
            bang.warnings.append(f"Lượt không có trong runs\\: {', '.join(miss)}.")
    for run in sorted(use):
        bang.rows.extend(_run_face_rows(bang, run, man))
    for run, why in bang.luot_bo_qua.items():
        bang.warnings.append(f"Lượt {run} bỏ qua: {why}.")
    for run, info in bang.runs.items():
        if info["co_toan_false"]:
            bang.warnings.append(f"Lượt {run}: mọi cờ low_conf đều false (khả năng chạy khi t_flip = null): số cờ của lượt này không dùng được; "
                                 "dùng cờ tính lại với t_flip cụ thể.")
    rows_by_key = {(r["luot"], r["mat"]): r for r in bang.rows}
    push_of = _push_task_map(bang, all_runs)
    if luot_nhap is not None and luot_nhap not in bang.runs:
        if luot_nhap in all_runs and luot_nhap not in use:
            bang.warnings.append(f"Lượt chứa nháp {luot_nhap} không nằm trong các lượt đang chọn: bỏ qua.")
        elif luot_nhap not in all_runs:
            bang.warnings.append(f"luot_nhap {luot_nhap!r} không có trong runs\\.")
        luot_nhap = None
    for lf in tim_file_nhan(bang.project_root, file_nhan):
        link = push_of.get(lf["task"])
        if link is not None and link not in bang.runs:
            if link in all_runs and link not in use:
                continue                                          # lượt gắn không nằm trong danh sách lượt đang chọn
            link = None
        _gan_nhan(bang, lf, link, luot_nhap if link is None else None, man, rows_by_key)
    for r in bang.rows:
        r.setdefault("lech_nhan", None)
    _tinh_lech_nhan(bang)
    bang.rows.sort(key=lambda r: (r["luot"], r["mat"]))
    return bang


def _push_task_map(bang, runs):
    """{task: lượt} từ runs\\*\\push.json (cập nhật gần nhất thắng); chỉ lượt có task."""
    best = {}
    for run in runs:
        ps = dot_anh.read_push(os.path.join(bang.runs_root, run))
        if isinstance(ps, dict) and isinstance(ps.get("task"), str) and ps["task"]:
            key = str(ps.get("cap_nhat") or "")
            if ps["task"] not in best or key > best[ps["task"]][0]:
                best[ps["task"]] = (key, run)
    return {t: v[1] for t, v in best.items()}


# ---------- quyết định rà ----------
def quyet_dinh_cuoi(row, nguoi_ra=()):
    """(quyết định, người rà) của mặt: xét các người rà (loại auto) trong `nguoi_ra` (rỗng = mọi người), theo tên người tăng dần, lấy người đầu có
    quyết định hợp lệ; ('', '') nếu chưa ai rà. triage_auto KHÔNG tính là người rà."""
    for who in sorted(row["ra"]):
        if who == AUTO or (nguoi_ra and who not in nguoi_ra):
            continue
        d = row["ra"][who]["quyet_dinh"]
        if d in phan_loai.DECISIONS:
            return d, who
    return "", ""


def giay_ra(row, nguoi_ra=()):
    """[(người, tổng giây có giá trị của mặt)] của các người rà (loại auto) có giây."""
    return [(w, v["giay"]) for w, v in sorted(row["ra"].items()) if w != AUTO and v["giay"] is not None and (not nguoi_ra or w in nguoi_ra)]
