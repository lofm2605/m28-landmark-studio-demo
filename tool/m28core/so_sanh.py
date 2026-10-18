"""Phần TÍNH của ba chỉ số thí nghiệm theo thiết kế HAI NHÓM ĐỘC LẬP (QĐ-006): numpy + thư viện chuẩn, chỉ đọc, không pandas.

Hai nhóm: manual (gán tay hoàn toàn) và assisted (dùng tool, sửa nháp); mỗi người thuộc đúng một nhóm, KHÔNG ghép cặp theo người. Cả hai nhóm làm CÙNG bộ ảnh.
  (1) NME của nháp: đáp án = nhãn gán tay của nhóm MANUAL trên cùng ảnh (nhiều nhãn manual thì lấy trung bình theo tên điểm; ảnh chưa có nhãn manual thì
      không chấm). Thêm NME của NHÃN CUỐI nhóm assisted so với cùng đáp án (kiểm "nhanh hơn mà nhãn không kém đi"). Dùng eval50.face_scores (% IOD của đáp án).
  (2) Tỉ lệ điểm phải sửa (chỉ nhóm assisted có nháp): khoảng cách điểm-điểm nháp ↔ nhãn cuối / IOD nhãn cuối > ngưỡng (mặc định 2% IOD); điểm có trong nháp mà
      thiếu/outside trong nhãn cuối tính là đã sửa (đếm riêng là xoá/ẩn).
  (3) Thời gian: giây/mặt mỗi nhóm (trung vị, trung bình nhân), % nhanh hơn của assisted so với manual = (1 − TB nhân assisted ÷ TB nhân manual) × 100 (mục tiêu
      >= 20%), khoảng tin cậy 90% bằng CLUSTER BOOTSTRAP (bốc lại NGƯỜI trong nhóm, rồi bốc lại MẶT trong từng người đã bốc; seed 28, 2.000 lần). Mỗi nhóm < 2 người
      thì chỉ có kết quả mô tả, chưa kết luận được. Dòng bấm giờ ước lượng chia đều (cả phiên / số mặt) được gắn cờ và vẫn tính; dòng gián đoạn, sửa tay, có cảnh báo,
      vượt Q3 + 3·IQR trong (người, nhóm) được ĐÁNH DẤU và vẫn nằm trong chỉ số chính, kèm một dòng độ nhạy bỏ chúng.
Hạn chế của thiết kế hai nhóm (phải nói trên trang): tốc độ từng người khác nhau lẫn vào kết quả; ít người mỗi nhóm thì khoảng tin cậy rất rộng.
"""
import math

N_BOOT = 2000
SEED = 28
MUC_TIEU_NHANH_HON = 20.0          # % nhanh hơn của assisted so với manual
MIN_NGUOI_MOI_NHOM = 2             # dưới ngần này người mỗi nhóm: chỉ mô tả
N_NHO = 5                          # n nhỏ hơn: ghi "n quá nhỏ"
HE_SO_IQR = 3.0                    # ngoại lai: > Q3 + 3·IQR
NGUONG_SUA_MAC_DINH = 2.0          # % IOD
SAI_SO_DIEM = 0.05                 # px: hai bản nháp của cùng một ảnh coi là giống nhau nếu lệch không quá ngần này
CONDITIONS = ("manual", "assisted")
KET_LUAN_VI = {"dat": "Đạt", "khong_dat": "Không đạt", "chua_ket_luan": "Chưa kết luận", "chi_mo_ta": "Chỉ có kết quả mô tả, chưa kết luận được",
               "chua_du_du_lieu": "Chưa đủ dữ liệu"}


def _np():
    import numpy as np
    return np


def _have(d, n):
    v = d.get(n) if d else None
    return v is not None and len(v) == 2 and v[0] is not None and v[1] is not None and math.isfinite(v[0]) and math.isfinite(v[1])


# ---------- (2) điểm đã sửa ----------
def diem_sua(nhap, nhan, cfg, nguong=NGUONG_SUA_MAC_DINH):
    """So nháp với nhãn cuối của cùng một mặt. Trả dict(ok, ly_do, iod, n_nhap, sua=set(tên điểm lệch > nguong % IOD), xoa=set(tên điểm có trong nháp mà thiếu trong nhãn cuối),
    khoang_cach={tên điểm: % IOD}). Mặt thiếu IOD trong nhãn cuối thì ok False (không tính)."""
    import eval50
    d = eval50.iod(nhan, cfg)
    if d is None:
        return dict(ok=False, ly_do="nhãn cuối thiếu khoảng cách hai khoé mắt ngoài (iod_points)", iod=None, n_nhap=0, sua=set(), xoa=set(), khoang_cach={})
    np = _np()
    sua, xoa, kc, n = set(), set(), {}, 0
    for p in cfg["points"]:
        nm = p["name"]
        if not _have(nhap, nm):
            continue
        n += 1
        if not _have(nhan, nm):
            xoa.add(nm)
            continue
        dist = float(np.linalg.norm(np.asarray(nhap[nm], float) - np.asarray(nhan[nm], float))) / d * 100
        kc[nm] = dist
        if dist > nguong:
            sua.add(nm)
    return dict(ok=True, ly_do="", iod=d, n_nhap=n, sua=sua, xoa=xoa, khoang_cach=kc)


def ti_le_sua(mats, cfg, nguong=NGUONG_SUA_MAC_DINH):
    """mats: [dict(nguoi, anh, nhap, nhan)] của nhóm assisted có nháp. Trả dict(n_mat, n_diem, n_sua, n_xoa, ti_le, ti_le_mat, nhom{tên nhóm: dict(n_diem, n_sua, ti_le)},
    bo_qua[(anh, lý do)], n_mat_phai_sua). ti_le = điểm đã sửa (kể cả xoá/ẩn) / điểm nháp."""
    groups = {}
    for p in cfg["points"]:
        groups.setdefault(p.get("group") or p["name"].rsplit("_", 1)[0], []).append(p["name"])
    gidx = {n: g for g, ns in groups.items() for n in ns}
    tong = dict(n_mat=0, n_diem=0, n_sua=0, n_xoa=0, n_mat_phai_sua=0)
    nhom = {g: dict(n_diem=0, n_sua=0) for g in groups}
    bo = []
    for m in mats:
        r = diem_sua(m["nhap"], m["nhan"], cfg, nguong)
        if not r["ok"]:
            bo.append((m["anh"], r["ly_do"]))
            continue
        tong["n_mat"] += 1
        tong["n_diem"] += r["n_nhap"]
        tong["n_sua"] += len(r["sua"]) + len(r["xoa"])
        tong["n_xoa"] += len(r["xoa"])
        tong["n_mat_phai_sua"] += 1 if (r["sua"] or r["xoa"]) else 0
        for nm in list(m["nhap"]):
            g = gidx.get(nm)
            if g is None or not _have(m["nhap"], nm):
                continue
            nhom[g]["n_diem"] += 1
            nhom[g]["n_sua"] += 1 if (nm in r["sua"] or nm in r["xoa"]) else 0
    for g, e in nhom.items():
        e["ti_le"] = 100.0 * e["n_sua"] / e["n_diem"] if e["n_diem"] else None
    tong["nhom"] = nhom
    tong["ti_le"] = 100.0 * tong["n_sua"] / tong["n_diem"] if tong["n_diem"] else None
    tong["ti_le_mat"] = 100.0 * tong["n_mat_phai_sua"] / tong["n_mat"] if tong["n_mat"] else None
    tong["bo_qua"] = bo
    tong["nguong"] = nguong
    return tong


# ---------- (1) NME ----------
def tham_chieu(manual_mats, cfg):
    """Đáp án từ nhãn gán tay của nhóm manual: {anh: dict(diem={tên: [x, y]}, n_nguoi)}; nhiều người thì trung bình toạ độ từng điểm (theo tên điểm)."""
    np = _np()
    by = {}
    for m in manual_mats:
        if m.get("nhan"):
            by.setdefault(m["anh"], []).append(m)
    out = {}
    names = [p["name"] for p in cfg["points"]]
    for anh, ms in by.items():
        pts = {}
        for n in names:
            v = [m["nhan"][n] for m in ms if _have(m["nhan"], n)]
            if v:
                pts[n] = [float(np.mean([a[0] for a in v])), float(np.mean([a[1] for a in v]))]
        out[anh] = dict(diem=pts, n_nguoi=len({m["nguoi"] for m in ms}))
    return out


def _nhom_cua_diem(cfg):
    groups = {}
    for p in cfg["points"]:
        groups.setdefault(p.get("group") or p["name"].rsplit("_", 1)[0], []).append(p["name"])
    return groups


def nme_mat(pred, gt, cfg):
    """dict(ok, nme, nhom{tên nhóm: lỗi chính trung bình của các điểm của nhóm trong mặt này}) hoặc dict(ok False, ly_do)."""
    import eval50
    s = eval50.face_scores(pred, gt, cfg)
    if not s.get("ok"):
        return dict(ok=False, ly_do=s.get("reason", "không chấm được"))
    np = _np()
    nhom = {}
    for g, ns in _nhom_cua_diem(cfg).items():
        v = [s["errors"][n] for n in ns if n in s["errors"]]
        if v:
            nhom[g] = float(np.mean(v))
    return dict(ok=True, nme=s["nme"], nhom=nhom, nme_eye=s.get("nme_eye"), nme_p2p=s.get("nme_p2p"), vung=dict(s.get("region") or {}),
                eye_open_err=s.get("eye_open_err"), n_missing=s.get("n_missing", 0))


def tom_tat(giatri, bad=None):
    """dict(n, tb, trung_vi, n_hong, ti_le_hong) trên danh sách số (None nếu rỗng). bad: ngưỡng mặt hỏng (% IOD)."""
    np = _np()
    v = [float(x) for x in giatri if x is not None]
    if not v:
        return dict(n=0, tb=None, trung_vi=None, n_hong=0, ti_le_hong=None)
    hong = sum(1 for x in v if bad is not None and x >= bad)
    return dict(n=len(v), tb=float(np.mean(v)), trung_vi=float(np.median(v)), n_hong=hong, ti_le_hong=(100.0 * hong / len(v)) if bad is not None else None)


def nme_nhom(mats, ref, cfg, bad):
    """NME của các mặt `mats` [dict(nguoi, anh, diem)] so với đáp án `ref` (tham_chieu). Trả dict(tong, nhom{tên nhóm: tom_tat}, mat=[dict(anh, nguoi, nme, nhom)],
    chua_co_dap_an=[anh], khong_cham_duoc=[(anh, lý do)])."""
    rows, chua, khong = [], [], []
    for m in mats:
        r = ref.get(m["anh"])
        if not r or not r["diem"]:
            chua.append(m["anh"])
            continue
        s = nme_mat(m["diem"], r["diem"], cfg)
        if not s["ok"]:
            khong.append((m["anh"], s["ly_do"]))
            continue
        rows.append(dict(anh=m["anh"], nguoi=m["nguoi"], nme=s["nme"], nhom=s["nhom"], n_ref=r["n_nguoi"], nme_eye=s["nme_eye"], nme_p2p=s["nme_p2p"], vung=s["vung"],
                         eye_open_err=s["eye_open_err"], n_missing=s["n_missing"]))
    nhom = {}
    for g in _nhom_cua_diem(cfg):
        nhom[g] = tom_tat([r["nhom"].get(g) for r in rows], bad)
    return dict(tong=tom_tat([r["nme"] for r in rows], bad), nhom=nhom, mat=rows, chua_co_dap_an=sorted(set(chua)), khong_cham_duoc=khong)


# ---------- (3) thời gian ----------
def _gm(v):
    np = _np()
    return float(np.exp(np.mean(np.log(np.asarray(v, float))))) if len(v) else None


def ngoai_lai(rows):
    """Các dòng vượt Q3 + 3·IQR trong (người, nhóm), cần >= 4 dòng: [(người, nhóm, mã mặt, giây, ngưỡng)]."""
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
        out += [(p, c, r.get("face_id", ""), r["seconds"], lim) for r in rs if r["seconds"] > lim]
    return out


def _gom(rows):
    """{nhóm: {người: [giây mỗi mặt]}}."""
    g = {c: {} for c in CONDITIONS}
    for r in rows:
        g[r["condition"]].setdefault(r["person"], []).append(float(r["seconds"]))
    return g


def _tom_tat_nhom(rows_nhom):
    np = _np()
    sec = [s for ss in rows_nhom.values() for s in ss]
    return dict(n_nguoi=len(rows_nhom), n_mat=len(sec), trung_vi=float(np.median(sec)) if sec else None, tb_nhan=_gm(sec),
                tb_cong=float(np.mean(sec)) if sec else None,
                nguoi={p: dict(n_mat=len(ss), trung_vi=float(np.median(ss)), tb_nhan=_gm(ss)) for p, ss in sorted(rows_nhom.items())})


def _nhanh_hon(a, m):
    return None if (a is None or m is None or m <= 0) else (1.0 - a / m) * 100.0


def _bootstrap(gom, n_boot=N_BOOT, seed=SEED):
    """% nhanh hơn của từng lần bốc: bốc lại NGƯỜI trong từng nhóm (có hoàn lại), rồi bốc lại MẶT trong từng người đã bốc. Thứ tự gọi rng cố định (nhóm manual rồi
    assisted; người theo tên) nên cùng seed cho cùng kết quả."""
    np = _np()
    rng = np.random.default_rng(seed)
    logs = {c: {p: np.log(np.asarray(ss, float)) for p, ss in sorted(gom[c].items())} for c in CONDITIONS}
    out, bo = [], 0
    for _ in range(n_boot):
        gm = {}
        for c in CONDITIONS:
            names = list(logs[c])
            tong, n = 0.0, 0
            for i in rng.integers(0, len(names), len(names)):
                lg = logs[c][names[i]]
                idx = rng.integers(0, len(lg), len(lg))
                tong += float(lg[idx].sum())
                n += len(lg)
            gm[c] = math.exp(tong / n) if n else None
        v = _nhanh_hon(gm["assisted"], gm["manual"])
        if v is None or v != v:
            bo += 1
            continue
        out.append(v)
    return out, bo


def thoi_gian(rows, n_boot=N_BOOT, seed=SEED, muc_tieu=MUC_TIEU_NHANH_HON):
    """So sánh giây/mặt của hai nhóm độc lập. rows: [dict(person, condition, seconds, face_id?, uoc_luong?, interrupted?, sua_tay?, canh_bao?)] đã lọc (warmup, giây > 0, đợt).
    Trả dict(nhom{manual, assisted}, nhanh_hon_pct, nhanh_hon_trung_vi_pct, ktc90_pct (lo, hi) hoặc None, n_boot, bo_lan, ket_luan, ly_do, ngoai_lai[...], danh_dau[...],
    do_nhay{...}, n_uoc_luong)."""
    res = dict(nhom={c: dict(n_nguoi=0, n_mat=0, trung_vi=None, tb_nhan=None, tb_cong=None, nguoi={}) for c in CONDITIONS}, nhanh_hon_pct=None, nhanh_hon_trung_vi_pct=None,
               ktc90_pct=None, n_boot=0, bo_lan=0, ket_luan="chua_du_du_lieu", ly_do="", ngoai_lai=[], danh_dau=[], do_nhay=None, n_uoc_luong=0, muc_tieu=muc_tieu)
    rows = [r for r in rows if r["condition"] in CONDITIONS and r.get("seconds") is not None and r["seconds"] > 0]
    gom = _gom(rows)
    for c in CONDITIONS:
        if gom[c]:
            res["nhom"][c] = _tom_tat_nhom(gom[c])
    miss = [c for c in CONDITIONS if not gom[c]]
    res["n_uoc_luong"] = sum(1 for r in rows if r.get("uoc_luong"))
    if miss:
        res["ly_do"] = "Chưa có dòng bấm giờ của nhóm " + " và ".join(miss) + " (cần cả hai nhóm)."
        return res
    a, m = res["nhom"]["assisted"], res["nhom"]["manual"]
    res["nhanh_hon_pct"] = _nhanh_hon(a["tb_nhan"], m["tb_nhan"])
    res["nhanh_hon_trung_vi_pct"] = _nhanh_hon(a["trung_vi"], m["trung_vi"])
    ol = ngoai_lai(rows)
    res["ngoai_lai"] = [dict(person=p, condition=c, face_id=f, seconds=s, nguong=lim) for p, c, f, s, lim in ol]
    flagged = {}
    for r in rows:
        why = []
        if r.get("interrupted"):
            why.append("bị gián đoạn (tạm dừng)")
        if r.get("sua_tay"):
            why.append("đã sửa tay thời gian")
        if r.get("canh_bao"):
            why.append("có cảnh báo: " + str(r["canh_bao"]))
        if r.get("uoc_luong"):
            why.append("ước lượng chia đều (cả phiên / số mặt)")
        if why:
            flagged[id(r)] = (r, why)
    for p, c, f, s, lim in ol:
        for r in rows:
            if r["person"] == p and r["condition"] == c and r.get("face_id", "") == f and r["seconds"] == s:
                flagged.setdefault(id(r), (r, []))[1].append("vượt Q3 + 3·IQR")
                break
    res["danh_dau"] = [dict(person=r["person"], condition=r["condition"], face_id=r.get("face_id", ""), seconds=r["seconds"], ly_do="; ".join(w))
                       for r, w in flagged.values() if any(not x.startswith("ước lượng") for x in w)]
    loai = {id(r) for r, w in flagged.values() if any(not x.startswith("ước lượng") for x in w)}
    sub = [r for r in rows if id(r) not in loai]
    g2 = _gom(sub)
    if all(g2[c] for c in CONDITIONS):
        t = {c: _tom_tat_nhom(g2[c]) for c in CONDITIONS}
        res["do_nhay"] = dict(n_bo=len(rows) - len(sub), nhanh_hon_pct=_nhanh_hon(t["assisted"]["tb_nhan"], t["manual"]["tb_nhan"]),
                              nhanh_hon_trung_vi_pct=_nhanh_hon(t["assisted"]["trung_vi"], t["manual"]["trung_vi"]),
                              n_nguoi={c: t[c]["n_nguoi"] for c in CONDITIONS})
    else:
        res["do_nhay"] = dict(n_bo=len(rows) - len(sub), nhanh_hon_pct=None, nhanh_hon_trung_vi_pct=None, n_nguoi={c: len(g2[c]) for c in CONDITIONS})
    if min(a["n_nguoi"], m["n_nguoi"]) < MIN_NGUOI_MOI_NHOM:
        res["ket_luan"] = "chi_mo_ta"
        res["ly_do"] = (f"Mỗi nhóm cần ít nhất {MIN_NGUOI_MOI_NHOM} người mới có khoảng tin cậy (hiện manual {m['n_nguoi']} người, assisted {a['n_nguoi']} người): "
                        "chỉ có kết quả mô tả, chưa kết luận được.")
        return res
    boot, bo = _bootstrap(gom, n_boot, seed)
    res["n_boot"], res["bo_lan"] = len(boot), bo
    if not boot:
        res["ket_luan"] = "chua_ket_luan"
        res["ly_do"] = "Không tính được khoảng tin cậy."
        return res
    np = _np()
    lo, hi = float(np.percentile(boot, 5)), float(np.percentile(boot, 95))
    res["ktc90_pct"] = (lo, hi)
    res["ket_luan"] = "dat" if lo >= muc_tieu else ("khong_dat" if hi < muc_tieu else "chua_ket_luan")
    return res


def n_nho(n):
    return n < N_NHO
