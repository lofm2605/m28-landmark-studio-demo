"""Đo cờ low_conf và sai số của nháp chung (bộ 200 ảnh in-cabin + bộ phụ 100 ảnh) so với nhãn gán tay của thí nghiệm 14-15/10 (QĐ-023).

Nháp gửi cho người làm hôm đó chưa có cờ (t_flip chưa chốt, mọi low_conf = false), nên cờ được tính lại từ map50\\mp50.json bằng đúng phép đo của
bước flags (lệch ảnh gốc / ảnh lật đã bỏ lật ÷ khoảng cách hai khoé mắt ngoài) với t_flip trong config. Lỗi từng điểm lấy từ eval50.point_errors
(E điểm-điểm, C tới đường gấp khúc của đáp án), số đo cờ lấy từ flag_eval.analyze. Chỉ đọc file, không ghi gì.

    python tool\\do_co_thi_nghiem.py --nhap <thư mục giải nén gói nháp> --gt bo200=<annotations.xml hoặc zip CVAT> [--gt bo200=...] --gt wflw100=<...>

Thư mục --nhap chứa data\\<bộ>\\prelabel.xml và runs\\<bộ>\\map50\\mp50.json (gói m28_bo200_B_part00_meta.zip, m28_wflw100_nhap_chung.zip).
Một ảnh có nhãn ở nhiều file thì lấy file đầu tiên; ảnh có dưới 40 điểm trong file (chưa gán) bị bỏ.
--cai-thien: thử hướng cải thiện cờ (chỉ đo, không đổi cờ của tool): chia đôi số mặt (seed 7), chọn cách tính và ngưỡng trên nửa dev, chấm trên nửa test.
Ba cách: điểm số lệch ảnh lật (như hiện tại); thêm điểm số trung bình của cả mặt; thêm phân vị 0,9 của cả mặt và nhóm điểm (hồi quy logistic, numpy).
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eval50  # noqa: E402
import flag_eval  # noqa: E402
from m28core import co_v2  # noqa: E402

TOLS = (2.0, 3.0, 5.0)
BINS = ((0, 0), (1, 3), (4, 7), (8, 15), (16, 50))


def load(nhap, gt_args, cfg):
    """(rows, faces, n_gt, n_dup): rows như flag_eval (vùng, điểm số, lỗi % IOD, mặt, nhóm); faces [dict(id, nflag, err, nme)]."""
    quiet = lambda *a, **k: None                                                    # noqa: E731
    t = float(cfg["t_flip"])
    gt, dup = {}, 0
    for item in gt_args:
        bo, path = item.split("=", 1)
        for k, v in eval50.read_labels(path, cfg, warn=quiet).items():
            if len(v) < 40:
                continue
            if (bo, k) in gt:
                dup += 1
                continue
            gt[(bo, k)] = v
    draft, mp50 = {}, {}
    for bo in sorted({b for b, _ in gt}):
        draft[bo] = eval50.read_labels(os.path.join(nhap, "data", bo, "prelabel.xml"), cfg, warn=quiet)
        with open(os.path.join(nhap, "runs", bo, "map50", "mp50.json"), encoding="utf-8") as f:
            mp50[bo] = json.load(f)
    rows, faces = [], []
    for (bo, k), g in sorted(gt.items()):
        if k not in draft[bo] or k not in mp50[bo]:
            continue
        sc = flag_eval.flip_scores_g(mp50[bo][k], cfg)
        err, _miss, d = eval50.point_errors(draft[bo][k], g, cfg)
        if sc is None or d is None:
            continue
        fid, nflag = f"{bo}/{k}", 0
        for p, (reg, v, grp) in zip(cfg["points"], sc):
            if p["name"] in err:
                rows.append((reg, v, err[p["name"]], fid, grp))
                nflag += v > t
        faces.append(dict(id=fid, nflag=int(nflag), err=list(err.values()), nme=float(np.mean(list(err.values()))),
                          errn=dict(err), mp=mp50[bo][k]))
    return rows, faces, len(gt), dup


def report(rows, faces, cfg, out=print):
    t = float(cfg["t_flip"])
    tol = flag_eval.tolerance_for(cfg, "", 3.0)
    out(f"{len(faces)} mặt, {len(rows)} điểm; t_flip {t:g}; sai số chấp nhận chốt {tol:g}% IOD")
    for tl in TOLS:
        a = flag_eval.analyze(rows, tl, None, t_flip=t)
        at = a["at_t"]
        out(f"[{tl:g}% IOD] điểm nháp trong sai số {100 - a['bad_pct']:.1f}%; AUROC {a['auroc']:.3f}; cờ {at['flagged_pct']:.1f}% điểm, "
            f"bắt {at['caught']:.1f}% điểm sai, độ chính xác {at['precision']:.1f}%, {at['per_face']:.1f} cờ/mặt")
    a = flag_eval.analyze(rows, tol, None, t_flip=t)
    out("AUROC theo nhóm: " + ", ".join(f"{g} {v['auroc']:.3f} (sai {v['bad_pct']:.0f}%)" for g, v in a["by_group"].items()))
    for q, th, flg, caught, prec, pf in a["table"]:
        out(f"  phân vị {q:.2f} (ngưỡng {th:.4f}): cờ {flg:.1f}%, bắt {caught:.1f}% điểm sai, độ chính xác {prec:.1f}%, {pf:.1f} cờ/mặt")
    nf = np.array([f["nflag"] for f in faces])
    nme = np.array([f["nme"] for f in faces])
    out(f"Mức mặt (mặt xấu = NME > {tol:g}% IOD: {int((nme > tol).sum())}/{len(faces)} mặt): AUROC theo số cờ {flag_eval.auroc(nf, nme > tol):.3f}")
    for lo, hi in BINS:
        sel = (nf >= lo) & (nf <= hi)
        if sel.any():
            e = np.concatenate([np.array(f["err"]) for f, s in zip(faces, sel) if s])
            out(f"  {lo}-{hi} cờ: {int(sel.sum())} mặt ({100 * sel.mean():.0f}%), NME trung bình {nme[sel].mean():.2f}%, "
                f"điểm sai {100 * (e > tol).mean():.1f}%, mặt NME > {tol:g}%: {int((nme[sel] > tol).sum())}")
    for k in (1, 8, 16):
        sel, bad = nf >= k, nme > tol
        out(f"  từ {k} cờ: {int(sel.sum())} mặt, gồm {100 * (sel & bad).sum() / max(bad.sum(), 1):.0f}% số mặt xấu, "
            f"{100 * (sel & bad).sum() / max(sel.sum(), 1):.0f}% mặt được chọn là mặt xấu")
    return a


def _fit(X, y, it=4000, lr=0.1, l2=1e-3):
    """Hồi quy logistic (numpy, chuẩn hoá cột); trả hàm chấm điểm."""
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Z.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-Z @ w))
        w -= lr * (Z.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]])
    return lambda X2: np.c_[np.ones(len(X2)), (X2 - mu) / sd] @ w


def cai_thien(rows, cfg, out=print, seed=7):
    """Hướng cải thiện cờ, đo trên nửa test: [(cách, AUROC test, [(ngân sách, % cờ, % bắt, % chính xác)], % cờ cần để bắt 50%)]."""
    tol = flag_eval.tolerance_for(cfg, "", 3.0)
    s = np.array([r[1] for r in rows])
    bad = np.array([r[2] for r in rows]) > tol
    fid = np.array([r[3] for r in rows])
    grp = np.array([r[4] for r in rows])
    groups = list(dict.fromkeys(grp))
    mean_f = {f: s[fid == f].mean() for f in set(fid)}
    q90_f = {f: np.quantile(s[fid == f], 0.9) for f in set(fid)}
    m = np.array([mean_f[f] for f in fid])
    q90 = np.array([q90_f[f] for f in fid])
    faces = sorted(set(fid))
    np.random.RandomState(seed).shuffle(faces)
    dev = np.isin(fid, faces[:len(faces) // 2])
    te = ~dev
    out(f"{len(faces)} mặt: chọn trên {len(faces) // 2} mặt (dev), chấm trên {len(faces) - len(faces) // 2} mặt (test); "
        f"điểm sai (> {tol:g}% IOD) dev {100 * bad[dev].mean():.1f}%, test {100 * bad[te].mean():.1f}%")
    feats = {"lệch ảnh lật (hiện tại)": np.c_[np.log(s + 1e-4)],
             "+ trung bình cả mặt": np.c_[np.log(s + 1e-4), np.log(m + 1e-4)],
             "+ trung bình, phân vị 0,9 cả mặt và nhóm điểm": np.c_[np.log(s + 1e-4), np.log(m + 1e-4), np.log(q90 + 1e-4),
                                                                   np.array([[g == k for k in groups] for g in grp], float)]}
    res = []
    for name, X in feats.items():
        sc = _fit(X[dev], bad[dev].astype(float))(X)
        at = []
        for budget in (0.15, 0.20, 0.30):
            fl = sc[te] > np.quantile(sc[dev], 1 - budget)
            at.append((budget, 100 * fl.mean(), 100 * (fl & bad[te]).sum() / bad[te].sum(), 100 * (fl & bad[te]).sum() / max(fl.sum(), 1)))
        need = next((b for b in np.arange(0.05, 1.0, 0.01)
                     if ((sc[te] > np.quantile(sc[dev], 1 - b)) & bad[te]).sum() / bad[te].sum() >= 0.5), 1.0)
        res.append((name, flag_eval.auroc(sc[te], bad[te]), at, 100 * need))
        out(f"[{name}] AUROC test {res[-1][1]:.3f}; " + "; ".join(f"cờ {f:.0f}% điểm → bắt {c:.1f}%, chính xác {p:.0f}%" for _b, f, c, p in at)
            + f"; muốn bắt 50% cần cờ khoảng {100 * need:.0f}% số điểm (chọn trên dev)")
    return res


def fit_lr(X, y, it=4000, lr=0.1, l2=1e-3):
    """Hồi quy logistic (numpy): (mu, sd, w, b) theo đúng dạng co_v2.probs dùng."""
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Z.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-Z @ w))
        w -= lr * (Z.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]])
    return mu, sd, w[1:], float(w[0])


def _xy(faces, cfg, groups, tol):
    X, y, fid = [], [], []
    names = [p["name"] for p in cfg["points"]]
    for f in faces:
        s = co_v2.flip_scores(f["mp"], cfg)
        if s is None:
            continue
        F = co_v2.features(s, cfg, groups)
        for i, n in enumerate(names):
            if n in f["errn"]:
                X.append(F[i]); y.append(f["errn"][n] > tol); fid.append(f["id"])
    return np.array(X), np.array(y), np.array(fid)


def hoc_v2(faces, cfg, out=print, seed=7, target=0.55):
    """Cờ phiên bản 2: học trên nửa dev (seed 7, cùng cách chia với cai_thien), ngưỡng = mức bắt `target` điểm sai trên dev; chấm trên nửa test.
    Trả dict mô hình để ghi vào config (khoá co_v2.KEY)."""
    tol = flag_eval.tolerance_for(cfg, "", 3.0)
    groups = list(dict.fromkeys(p.get("group", p["region"]) for p in cfg["points"]))
    ids = sorted(f["id"] for f in faces)
    np.random.RandomState(seed).shuffle(ids)
    dev_ids = set(ids[:len(ids) // 2])
    X, y, fid = _xy(faces, cfg, groups, tol)
    dev = np.array([f in dev_ids for f in fid])
    te = ~dev
    mu, sd, w, b = fit_lr(X[dev], y[dev].astype(float))
    p = 1 / (1 + np.exp(-(b + ((X - mu) / sd) @ w)))
    pd_sorted = np.sort(p[dev])[::-1]
    thr = None
    for k in range(1, len(pd_sorted)):
        t = pd_sorted[k]
        if ((p[dev] > t) & y[dev]).sum() / y[dev].sum() >= target:
            thr = float(t)
            break

    def m(mask):
        fl = p[mask] > thr
        nf = len(set(fid[mask]))
        return dict(n_mat=nf, n_diem=int(mask.sum()), sai_pct=100 * y[mask].mean(), co_pct=100 * fl.mean(), co_mat=fl.sum() / max(nf, 1),
                    bat_pct=100 * (fl & y[mask]).sum() / max(y[mask].sum(), 1), chinh_xac_pct=100 * (fl & y[mask]).sum() / max(fl.sum(), 1),
                    auroc=flag_eval.auroc(p[mask], y[mask]))
    kq = {"dev": m(dev), "test": m(te), "tat_ca": m(np.ones(len(p), bool))}
    for k, v in kq.items():
        out(f"[{k}] {v['n_mat']} mặt: cờ {v['co_pct']:.1f}% điểm ({v['co_mat']:.1f} cờ/mặt), bắt {v['bat_pct']:.1f}% điểm sai, "
            f"chính xác {v['chinh_xac_pct']:.1f}%, AUROC {v['auroc']:.3f} (điểm sai {v['sai_pct']:.1f}%)")
    mdl = {"version": 2, "groups": groups, "mu": [round(float(v), 6) for v in mu], "sd": [round(float(v), 6) for v in sd],
           "w": [round(float(v), 6) for v in w], "b": round(b, 6), "threshold": round(thr, 6)}
    # gợi ý theo cả mặt (autoqc, chú thích Ổn / Cần xem): trên dev, "Ổn" = số cờ lớn nhất mà mặt xấu (NME > tol) ≤ 10%,
    # "nên sửa nhãn" = số cờ nhỏ nhất mà mặt xấu ≥ 90%
    cfg2 = dict(cfg, **{co_v2.KEY: mdl})
    for f in faces:
        f["n2"] = sum(co_v2.flags(f["mp"], cfg2))
    D = [f for f in faces if f["id"] in dev_ids]
    on_max = max((k for k in range(51) if [g for g in D if g["n2"] <= k] and np.mean([g["nme"] > tol for g in D if g["n2"] <= k]) <= 0.10), default=0)
    sua_min = min((k for k in range(51) if [g for g in D if g["n2"] >= k] and np.mean([g["nme"] > tol for g in D if g["n2"] >= k]) >= 0.90), default=51)
    for part, F in (("dev", D), ("test", [f for f in faces if f["id"] not in dev_ids])):
        on = [g for g in F if g["n2"] <= on_max]; sua = [g for g in F if g["n2"] >= sua_min]
        out(f"[{part}] Ổn (≤ {on_max} cờ): {len(on)} mặt, mặt xấu {sum(g['nme'] > tol for g in on)}; "
            f"nên sửa nhãn (≥ {sua_min} cờ): {len(sua)} mặt, mặt xấu {sum(g['nme'] > tol for g in sua)}")
    mdl.update(mat_on_max=on_max, mat_sua_min=sua_min,
               chon=f"học trên {len(dev_ids)} mặt dev (seed {seed}); ngưỡng điểm = bắt {round(100 * target)}% điểm sai > {tol:g}% IOD trên dev; "
                    f"ngưỡng mặt: Ổn khi mặt xấu ≤ 10%, nên sửa nhãn khi mặt xấu ≥ 90% (trên dev)",
               test={k: round(float(v), 4) for k, v in kq["test"].items()})
    return mdl


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Đo cờ low_conf của nháp chung so với nhãn gán tay (thí nghiệm 14-15/10)")
    ap.add_argument("--nhap", required=True, help="thư mục chứa data\\<bộ>\\prelabel.xml và runs\\<bộ>\\map50\\mp50.json")
    ap.add_argument("--gt", action="append", required=True, help="<bộ>=<annotations.xml hoặc zip CVAT>, lặp lại cho từng file")
    ap.add_argument("--config", default=os.path.join("config", "m28_config.json"))
    ap.add_argument("--cai-thien", action="store_true", help="thêm phần thử hướng cải thiện cờ (chia đôi dev / test)")
    ap.add_argument("--hoc-v2", metavar="OUT.json", help="học cờ phiên bản 2 (QĐ-025) trên nửa dev, chấm trên nửa test, ghi mô hình ra OUT.json")
    a = ap.parse_args(argv)
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    if cfg.get("t_flip") is None:
        sys.exit("config chưa có t_flip.")
    rows, faces, n_gt, dup = load(a.nhap, a.gt, cfg)
    if not rows:
        sys.exit("Không ghép được mặt nào giữa nhãn gán tay và nháp.")
    print(f"Ảnh có nhãn gán tay: {n_gt} (bỏ {dup} bản trùng); chấm được {len(faces)} mặt (có ảnh lật và đủ hai khoé mắt)")
    report(rows, faces, cfg)
    if a.hoc_v2:
        print("\nCờ phiên bản 2 (học trên nửa dev, chấm trên nửa test):")
        mdl = hoc_v2(faces, cfg)
        with open(a.hoc_v2, "w", encoding="utf-8") as f:
            json.dump(mdl, f, ensure_ascii=False, indent=1)
        print(f"đã ghi {a.hoc_v2}")
    if a.cai_thien:
        print("\nHướng cải thiện (chỉ đo, không đổi cờ của tool):")
        cai_thien(rows, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
