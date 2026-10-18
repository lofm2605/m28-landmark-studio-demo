"""LƯU Ý (QĐ-006): trang Thống kê KHÔNG còn dùng giao thức ghép cặp này (thiết kế đổi sang hai nhóm độc lập, xem m28core/so_sanh.py); module giữ lại để đối chiếu với đoạn
code pandas gốc của P5 và vì bộ đọc `doc_file`/`tim_file` còn được dùng. Các hàm phan_tich/_ri/_bootstrap/tom_tat_giay chỉ còn test gọi; xoá khi P5 và mentor chốt thiết kế hai nhóm.

Tốc độ gán nhãn theo ĐÚNG giao thức của P5 (de-tai-m28/p5-thi-nghiem.md, mục "Thời gian"): chỉ numpy + thư viện chuẩn (không pandas), chỉ ĐỌC.

Đầu vào: timing_P*.csv do facetimer.py ghi, 12 cột `date, person, condition, task, job, block, seq, face_id, seconds, warmup, interrupted, note`.
Định dạng đã có nên KHÔNG đặt định dạng mới. Cách tính (khớp đoạn code P5 bằng pandas, có test so sánh khi máy có pandas):
  * chỉ dòng warmup = 0 và task thí nghiệm (`m28-manual`, `m28-assisted`); r_i = giây trung bình mỗi mặt assisted ÷ manual của từng người;
  * chỉ số chính = TRUNG BÌNH NHÂN các r_i; % nhanh hơn = (1 − TB nhân) × 100; mục tiêu: TB nhân ≤ 0,80 (nhanh hơn ≥ 20%) và ≥ 4/5 người có r_i < 1;
  * KTC 90% bằng bootstrap bốc lại seq trong từng khối (chung cho hai cách gán), 2.000 lần, seed 28 (rng = default_rng(28), cùng thứ tự gọi như code P5);
  * bảng kiểu M24 (ngày, người, điều kiện: số ảnh, số phút) trên mọi dòng warmup = 0; giờ tiết kiệm/1.000 mặt = (TB giây manual − TB giây assisted) × 1000 / 3600,
    chung và riêng hai nhóm mặt nghiêng/che (manifest pose | occlusion = 1) và còn lại.
Thêm (không có trong code P5, nên KHÔNG đổi chỉ số chính): dòng seconds trống/<= 0 bị bỏ và đếm; dòng interrupted = 1 và dòng vượt Q3 + 3·IQR trong (người, điều kiện)
được ĐÁNH DẤU và liệt kê nhưng vẫn nằm trong chỉ số chính; thêm một dòng độ nhạy "bỏ ngoại lai". Người thiếu một điều kiện thì không có r_i (ghi lý do);
< 3 người có đủ hai điều kiện thì không kết luận. "Không đạt" theo đề xuất của P5: cận dưới KTC 90% > 0,80 (quy tắc chốt ở họp 12/10 có thể khác).
"""
import csv
import glob
import io
import os

TIMING_COLS = ["date", "person", "condition", "task", "job", "block", "seq", "face_id", "seconds", "warmup", "interrupted", "note"]
TASKS_TN = ("m28-manual", "m28-assisted")
CONDITIONS = ("manual", "assisted")
N_BOOT = 2000
SEED = 28
MUC_TIEU_TB_NHAN = 0.80          # TB nhân <= 0,80 <=> nhanh hơn >= 20%
MIN_NGUOI = 3                    # dưới ngần này người có đủ hai điều kiện: không kết luận
TY_LE_NGUOI_NHANH = 0.8          # >= 4/5 người có r_i < 1
SAI_SO_SO = 1e-9                 # so sánh với 0,80 / 4/5 không bị lệch bởi sai số dấu phẩy động (exp(mean(log 0,8)) = 0,8000000000000002)
HE_SO_IQR = 3.0                  # ngoại lai: > Q3 + 3·IQR
TIMING_DIRS = ("", "outputs", os.path.join("outputs", "timing"), "raw", "final")
KET_LUAN_VI = {"dat": "Đạt", "khong_dat": "Không đạt", "chua_ket_luan": "Chưa kết luận", "chua_du_du_lieu": "Chưa đủ dữ liệu"}


class TocDoLoi(Exception):
    """File bấm giờ sai (thiếu cột, không đọc được): thông điệp tiếng Việt nói rõ file nào, cột nào."""


def tim_file(project_root, extra=None):
    """Các file timing_*.csv ở thư mục dự án, outputs\\, raw\\, final\\ và `extra` (thư mục hoặc file, phải nằm trong dự án). Trả [đường dẫn tuyệt đối] sắp theo tên.
    extra ngoài dự án -> TocDoLoi."""
    root = os.path.realpath(project_root)
    found = set()
    for d in TIMING_DIRS:
        for p in glob.glob(os.path.join(glob.escape(os.path.join(root, d)), "timing_*.csv")):
            found.add(os.path.realpath(p))
    if extra:
        p = extra if os.path.isabs(extra) else os.path.join(root, extra)
        rp = os.path.realpath(p)
        try:
            inside = os.path.commonpath([rp, root]) == root
        except ValueError:
            inside = False
        if not inside:
            raise TocDoLoi("Đường dẫn file/thư mục bấm giờ nằm ngoài thư mục dự án: từ chối.")
        if os.path.isdir(rp):
            found |= {os.path.realpath(x) for x in glob.glob(os.path.join(glob.escape(rp), "timing_*.csv"))}
        elif os.path.isfile(rp):
            found.add(rp)
        else:
            raise TocDoLoi("Không thấy file/thư mục bấm giờ đã nhập.")
    return sorted(found, key=lambda x: (os.path.basename(x), x))


def _f(v):
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def doc_file(path, ten=None):
    """list dict các dòng của một file timing (đã ép kiểu: seq, warmup, interrupted là int; seconds là float hoặc None). Thiếu cột -> TocDoLoi."""
    ten = ten or os.path.basename(path)
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise TocDoLoi(f"Không đọc được {ten} ({type(e).__name__}).")
    first = text.splitlines()[0] if text.strip() else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    rd = csv.DictReader(io.StringIO(text), delimiter=delim)
    head = [(h or "").strip() for h in (rd.fieldnames or [])]
    miss = [c for c in TIMING_COLS if c not in head]
    if miss:
        raise TocDoLoi(f"{ten} thiếu cột: {', '.join(miss)} (facetimer.py ghi đủ 12 cột: {', '.join(TIMING_COLS)}).")
    rows = []
    for r in rd:
        r = {(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None}
        if not any(r.values()):
            continue
        seq = _f(r["seq"])
        rows.append(dict(date=r["date"], person=r["person"], condition=r["condition"].lower(), task=r["task"], job=r["job"], block=r["block"],
                         seq=None if seq is None else int(seq), face_id=r["face_id"], seconds=_f(r["seconds"]),
                         warmup=int(_f(r["warmup"]) or 0), interrupted=int(_f(r["interrupted"]) or 0), note=r["note"], file=ten,
                         # cột thêm của đồng hồ ở đầu trang (QĐ-006); file facetimer 12 cột thì để mặc định
                         phien=r.get("phien", ""), dot=r.get("dot", ""), bo_anh=r.get("bo_anh", ""), sua_tay=int(_f(r.get("sua_tay", "")) or 0),
                         canh_bao=r.get("canh_bao", ""), uoc_luong=int(_f(r.get("uoc_luong_chia_deu", "")) or 0)))
    return rows


def doc_nhieu(paths, ten=None):
    rows = []
    for p in paths:
        rows += doc_file(p, ten(p) if ten else None)
    return rows


# ---------- tính ----------
def _np():
    import numpy as np
    return np


def _tb_theo(rows):
    """{(người, điều kiện): (tổng giây, số mặt)}."""
    d = {}
    for r in rows:
        k = (r["person"], r["condition"])
        s, n = d.get(k, (0.0, 0))
        d[k] = (s + r["seconds"], n + 1)
    return d


def _ri(rows):
    """({người: dict(manual, assisted, n_manual, n_assisted, r)}, [(người, lý do) thiếu điều kiện])."""
    d = _tb_theo(rows)
    nguoi = sorted({p for p, _c in d})
    out, thieu = {}, []
    for p in nguoi:
        e = {}
        for c in CONDITIONS:
            s, n = d.get((p, c), (0.0, 0))
            e[c], e["n_" + c] = (s / n if n else None), n
        if e["manual"] and e["assisted"]:
            e["r"] = e["assisted"] / e["manual"]
        else:
            e["r"] = None
            thieu.append((p, "thiếu " + " và ".join(c for c in CONDITIONS if not e[c]) + " (cần cả hai điều kiện, không tính warmup)"))
        out[p] = e
    return out, thieu


def _tb_nhan(r):
    np = _np()
    v = [x for x in r if x is not None]
    return float(np.exp(np.mean(np.log(v)))) if v else None


def phan_vi_ngoai_lai(rows):
    """Các dòng vượt Q3 + 3·IQR trong (người, điều kiện): [(người, điều kiện, face_id, giây, ngưỡng)]. Cần >= 4 dòng mới tính."""
    np = _np()
    out, by = [], {}
    for r in rows:
        by.setdefault((r["person"], r["condition"]), []).append(r)
    for (p, c), rs in sorted(by.items()):
        if len(rs) < 4:
            continue
        v = np.array([r["seconds"] for r in rs], float)
        q1, q3 = np.percentile(v, [25, 75])
        lim = float(q3 + HE_SO_IQR * (q3 - q1))
        out += [(p, c, r["face_id"], r["seconds"], lim) for r in rs if r["seconds"] > lim]
    return out


def _bootstrap(x, n_boot=N_BOOT, seed=SEED):
    """Danh sách TB nhân của từng lần bốc. Bốc lại seq trong từng khối (chung cho hai cách), cùng thứ tự gọi rng như code P5 (khối theo thứ tự tên)."""
    np = _np()
    sec = np.array([r["seconds"] for r in x], float)
    key = [(r["person"], r["condition"]) for r in x]
    uniq = sorted(set(key))
    kid = {k: i for i, k in enumerate(uniq)}
    kidx = np.array([kid[k] for k in key])
    blocks = {}
    for i, r in enumerate(x):
        blocks.setdefault(r["block"], []).append(i)
    plan = []
    for b in sorted(blocks):
        idx = np.array(blocks[b])
        seqs = sorted({x[i]["seq"] for i in blocks[b]})
        plan.append((idx, seqs, np.array([x[i]["seq"] for i in idx])))
    persons = sorted({p for p, _c in uniq})
    pairs = [(kid.get((p, "assisted")), kid.get((p, "manual"))) for p in persons]
    pairs = [(a, m) for a, m in pairs if a is not None and m is not None]
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        w = np.zeros(len(x))
        for idx, seqs, sq in plan:
            pick = list(rng.choice(seqs, len(seqs)))
            w[idx] = [pick.count(s) for s in sq]
        s = np.bincount(kidx, weights=sec * w, minlength=len(uniq))
        n = np.bincount(kidx, weights=w, minlength=len(uniq))
        with np.errstate(divide="ignore", invalid="ignore"):
            m = s / n
            r = np.array([m[a] / m[b] for a, b in pairs])
        r = r[np.isfinite(r) & (r > 0)]
        out.append(float(np.exp(np.log(r).mean())) if len(r) else float("nan"))
    return out


def _gio_tiet_kiem(rows):
    """(TB giây manual, TB giây assisted, giờ tiết kiệm/1.000 mặt) trên các dòng đã cho; None nếu thiếu một điều kiện."""
    sv = {}
    for c in CONDITIONS:
        v = [r["seconds"] for r in rows if r["condition"] == c]
        sv[c] = (sum(v) / len(v), len(v)) if v else (None, 0)
    if sv["manual"][0] is None or sv["assisted"][0] is None:
        return dict(manual=sv["manual"][0], assisted=sv["assisted"][0], n_manual=sv["manual"][1], n_assisted=sv["assisted"][1], gio_1000=None)
    return dict(manual=sv["manual"][0], assisted=sv["assisted"][0], n_manual=sv["manual"][1], n_assisted=sv["assisted"][1],
                gio_1000=(sv["manual"][0] - sv["assisted"][0]) * 1000 / 3600)


def phan_tich(rows, manifest=None, n_boot=N_BOOT, seed=SEED):
    """Kết quả theo giao thức P5. rows: kết quả doc_file. manifest: {tên mặt: dict} (có pose, occlusion) hoặc None.
    Khoá: ok (đủ dữ liệu để kết luận), ly_do_trong, n_dong, n_bo_giay, n_warmup, n_khong_tn, n_x, nguoi{...}, thieu[(người, lý do)], tb_nhan, nhanh_hon_pct, ktc90,
    ktc90_pct, ket_luan, n_r_nho_hon_1, n_nguoi, m24[...], ngoai_lai[...], gian_doan[...], do_nhay, gio, nhom."""
    res = dict(n_dong=len(rows), ok=False, ly_do_trong="", n_bo_giay=0, n_warmup=0, n_khong_tn=0, n_x=0, nguoi={}, thieu=[], tb_nhan=None, nhanh_hon_pct=None,
               ktc90=None, ktc90_pct=None, ket_luan="chua_du_du_lieu", n_r_nho_hon_1=0, n_nguoi=0, m24=[], ngoai_lai=[], gian_doan=[], do_nhay=None, gio=None,
               nhom=None, nhom_ly_do="")
    if not rows:
        res["ly_do_trong"] = "Chưa có dòng bấm giờ nào."
        return res
    valid = [r for r in rows if r["seconds"] is not None and r["seconds"] > 0]
    res["n_bo_giay"] = len(rows) - len(valid)
    t = [r for r in valid if r["warmup"] == 0]
    res["n_warmup"] = len(valid) - len(t)
    # bảng kiểu M24: mọi dòng warmup = 0
    m24 = {}
    for r in t:
        k = (r["date"], r["person"], r["condition"])
        a = m24.setdefault(k, [0, 0.0])
        a[0] += 1
        a[1] += r["seconds"]
    res["m24"] = [dict(date=d, person=p, condition=c, so_anh=n, so_phut=round(s / 60, 1)) for (d, p, c), (n, s) in sorted(m24.items())]
    x = [r for r in t if r["task"] in TASKS_TN and r["condition"] in CONDITIONS and r["seq"] is not None and r["block"]]
    res["n_khong_tn"] = len(t) - len(x)
    res["n_x"] = len(x)
    if not x:
        res["ly_do_trong"] = "Không có dòng nào của task thí nghiệm (m28-manual, m28-assisted) ở ngoài phần khởi động."
        return res
    res["gian_doan"] = [dict(person=r["person"], condition=r["condition"], face_id=r["face_id"], seconds=r["seconds"], block=r["block"]) for r in x if r["interrupted"]]
    res["ngoai_lai"] = [dict(person=p, condition=c, face_id=f, seconds=s, nguong=lim) for p, c, f, s, lim in phan_vi_ngoai_lai(x)]
    nguoi, thieu = _ri(x)
    res["nguoi"], res["thieu"] = nguoi, thieu
    rs = {p: e["r"] for p, e in nguoi.items() if e["r"] is not None}
    res["n_nguoi"] = len(rs)
    res["gio"] = _gio_tiet_kiem(x)
    if len(rs) < MIN_NGUOI:
        res["ly_do_trong"] = (f"Chưa đủ dữ liệu: mới có {len(rs)} người có đủ hai điều kiện manual và assisted, cần ít nhất {MIN_NGUOI} (kế hoạch: 5 người). "
                              "Bấm giờ ghép cặp là 14–15/10.")
        return res
    g = _tb_nhan(list(rs.values()))
    boot = [b for b in _bootstrap(x, n_boot, seed) if b == b]
    np = _np()
    lo, hi = (float(np.percentile(boot, 5)), float(np.percentile(boot, 95))) if boot else (None, None)
    n1 = sum(1 for v in rs.values() if v < 1)
    dat = g <= MUC_TIEU_TB_NHAN + SAI_SO_SO and n1 / len(rs) >= TY_LE_NGUOI_NHANH - SAI_SO_SO
    kl = "dat" if dat else ("khong_dat" if lo is not None and lo > MUC_TIEU_TB_NHAN + SAI_SO_SO else "chua_ket_luan")
    res.update(ok=True, tb_nhan=g, nhanh_hon_pct=(1 - g) * 100, ktc90=(lo, hi), ktc90_pct=None if lo is None else ((1 - hi) * 100, (1 - lo) * 100),
               ket_luan=kl, n_r_nho_hon_1=n1, n_boot=len(boot))
    # độ nhạy: bỏ dòng ngoại lai và dòng bị gián đoạn khỏi chỉ số (chỉ số chính vẫn giữ chúng)
    loai = {(o["person"], o["condition"], o["face_id"]) for o in res["ngoai_lai"]} | {(r["person"], r["condition"], r["face_id"]) for r in x if r["interrupted"]}
    x2 = [r for r in x if (r["person"], r["condition"], r["face_id"]) not in loai]
    nguoi2, _ = _ri(x2)
    rs2 = [e["r"] for e in nguoi2.values() if e["r"] is not None]
    if len(rs2) >= MIN_NGUOI:
        g2 = _tb_nhan(rs2)
        res["do_nhay"] = dict(n_bo=len(x) - len(x2), tb_nhan=g2, nhanh_hon_pct=(1 - g2) * 100, n_nguoi=len(rs2))
    else:
        res["do_nhay"] = dict(n_bo=len(x) - len(x2), tb_nhan=None, nhanh_hon_pct=None, n_nguoi=len(rs2))
    # hai nhóm mặt: nghiêng/che (pose | occlusion = 1) và còn lại (mặt không có trong manifest không xếp nhóm nào)
    if not manifest:
        res["nhom_ly_do"] = "Chưa có data\\manifest.csv nên không chia được nhóm nghiêng/che."
    else:
        kho = lambda r: (manifest.get(r["face_id"]) or {}).get("pose") in ("1",) or (manifest.get(r["face_id"]) or {}).get("occlusion") in ("1",)   # noqa: E731
        biet = [r for r in x if r["face_id"] in manifest]
        res["nhom"] = {"nghieng_che": _gio_tiet_kiem([r for r in biet if kho(r)]), "con_lai": _gio_tiet_kiem([r for r in biet if not kho(r)])}
        res["nhom_khong_manifest"] = len(x) - len(biet)
    return res


def pandas_tham_chieu(rows_by_file_dir, manifest_path=None):
    """Chỉ để TEST: chạy nguyên đoạn code của P5 (pandas) trên các file timing_*.csv trong thư mục; trả (r_i dict, TB nhân, [lo, hi], giờ tiết kiệm trộn).
    Gọi khi máy có pandas; không dùng trong tool\\ ở chế độ chạy thật."""
    import numpy as np
    import pandas as pd
    d = pd.concat(pd.read_csv(f) for f in sorted(glob.glob(os.path.join(rows_by_file_dir, "timing_*.csv"))))
    t = d[d.warmup == 0]
    x = t[t.task.isin(["m28-manual", "m28-assisted"])].reset_index(drop=True)

    def geo(w):
        s = (x.seconds * w).groupby([x.person, x.condition]).sum().unstack()
        n = pd.Series(w, index=x.index).groupby([x.person, x.condition]).sum().unstack()
        m = s / n
        r = m["assisted"] / m["manual"]
        return np.exp(np.log(r).mean()), r
    g, r = geo(np.ones(len(x)))
    rng, boot = np.random.default_rng(28), []
    for _ in range(N_BOOT):
        w = np.zeros(len(x))
        for b, rows in x.groupby("block").groups.items():
            seqs = sorted(x.seq.loc[rows].unique())
            pick = list(rng.choice(seqs, len(seqs)))
            w[rows] = [pick.count(s) for s in x.seq.loc[rows]]
        boot.append(geo(w)[0])
    sv = x.groupby("condition").seconds.mean()
    return r.to_dict(), float(g), [float(v) for v in np.percentile(boot, [5, 95])], float((sv["manual"] - sv["assisted"]) * 1000 / 3600)


# ---------- giây rà soát (triage) ----------
def tom_tat_giay(values, nguong=120.0):
    """Tóm tắt giây rà mỗi mặt: n (giá trị hợp lệ), trung vị, Q1, Q3, phút/100 mặt (trung vị × 100 / 60), n_ngoai_lai (> nguong, đếm riêng, không vào số khác)."""
    np = _np()
    v = [float(x) for x in values if x is not None and x >= 0]
    ngoai = [x for x in v if x > nguong]
    ok = [x for x in v if x <= nguong]
    if not ok:
        return dict(n=0, trung_vi=None, q1=None, q3=None, phut_100=None, n_ngoai_lai=len(ngoai), tong=len(v))
    q1, med, q3 = np.percentile(ok, [25, 50, 75])
    return dict(n=len(ok), trung_vi=float(med), q1=float(q1), q3=float(q3), phut_100=float(med) * 100 / 60, n_ngoai_lai=len(ngoai), tong=len(v))
