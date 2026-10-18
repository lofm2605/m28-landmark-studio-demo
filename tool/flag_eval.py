"""Đo cờ low_conf (P2, 8/10 và 10/10). Chỉ dùng numpy; không bao giờ chạy trên Ttest (Ttest chỉ chạy một lần ngày 20/10).

Điểm số nghi sai của mỗi điểm = lệch giữa ảnh gốc và ảnh lật đã bỏ lật / khoảng cách hai điểm `iod_points` (hai khoé mắt ngoài) DỰ ĐOÁN (giống steps.flags). Cờ bật khi điểm số > t_flip.
Báo theo NHÓM (7 nhóm của config version 3: longmaytrai, longmayphai, songmui, mattrai, matphai, moingoai, moitrong) và theo vùng thô (brow, nose, eye, lip); không còn vùng jaw.
Hai chế độ:

(a) KHÔNG đáp án (dùng ngay, chưa cần nhãn gán tay):
        python tool\\flag_eval.py --run <run đã chạy prepare cho Tdev> --set Tdev [--manifest data\\manifest.csv]
    In phân bố điểm số theo nhóm và theo vùng (trung vị, phân vị 0,85 và 0,95), với từng ngưỡng (phân vị 0,5 ... 0,95) tỉ lệ điểm bị cờ và số cờ/mặt, và ĐỀ XUẤT
    t_flip = phân vị 0,85 của điểm số trên Tdev (cờ ~ 15% số điểm, ~7 cờ/mặt trên 50 điểm; kế hoạch P2: cờ <= 15% số điểm) để P2 chốt ngày 12/10.
    So với đề xuất của định nghĩa 50 điểm CŨ (version 2, có viền hàm): 0,0464, không còn hiệu lực sau QĐ-003 (xem V2_T_FLIP).
    Không ghi vào config (P2 tự ghi ở tab Cài đặt hoặc make_config.py --t-flip). Không có AUROC vì chưa biết điểm nào sai.

(b) CÓ đáp án (khi nhóm đã gán tay xong tập G/X, nhãn ở raw\\*.xml):
        python tool\\flag_eval.py --run <run> --gt raw\\<đáp án>.xml [--tol 3.0]
    Lỗi từng điểm lấy từ eval50.point_errors (E điểm-điểm, C tới đường gấp khúc đáp án), ghép theo tên ảnh và tên điểm. "Điểm sai" = lỗi > sai số chấp nhận
    (config.tolerance theo vùng nếu có, không thì --tol, mặc định 3% IOD). Báo % điểm sai, AUROC toàn bộ, THEO VÙNG và THEO NHÓM, và với từng ngưỡng: % điểm bị cờ,
    % điểm sai bị bắt, độ chính xác, cờ/mặt. Mặt thuộc Ttest (theo manifest) bị bỏ.
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

QUANTILES = (0.5, 0.7, 0.8, 0.85, 0.9, 0.95)
SUGGEST_Q = 0.85
V2_T_FLIP = 0.0464        # đề xuất t_flip (phân vị 0,85 trên Tdev) của định nghĩa 50 điểm CŨ (version 2, có viền hàm, 6/10/2026): chỉ để so, không còn hiệu lực


def auroc(score, bad):
    """Xác suất điểm sai có điểm số cao hơn điểm đúng (có xử lý hoà). Không cần scipy."""
    score, bad = np.asarray(score, float), np.asarray(bad, bool)
    n1, n0 = int(bad.sum()), int((~bad).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score))
    s = score[order]
    i = 0
    while i < len(s):                       # hạng trung bình cho các điểm hoà
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return float((ranks[bad].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def flip_scores_g(mp50_face, cfg):
    """Điểm số nghi sai của từng điểm của một mặt: [(vùng, điểm số, nhóm)] theo thứ tự config; None nếu mặt không có ảnh lật.
    mp50_face = {'orig': {tên: [x, y]}, 'flip': {...} | None} (flip đã bỏ lật, như map50\\mp50.json)."""
    if not mp50_face.get("flip"):
        return None
    names = [p["name"] for p in cfg["points"]]
    e1, e2 = cfg["iod_points"]
    o = np.array([mp50_face["orig"][n] for n in names], float)
    f = np.array([mp50_face["flip"][n] for n in names], float)
    iod = float(np.linalg.norm(np.array(mp50_face["orig"][e1]) - np.array(mp50_face["orig"][e2]))) or 1.0
    s = np.linalg.norm(o - f, axis=1) / iod
    return [(p["region"], float(v), p.get("group", p["region"])) for p, v in zip(cfg["points"], s)]


def flip_scores(mp50_face, cfg):
    """Như flip_scores_g nhưng chỉ [(vùng, điểm số)]."""
    sc = flip_scores_g(mp50_face, cfg)
    return None if sc is None else [(r, v) for r, v, _ in sc]


def collect_scores(files, mp50, cfg):
    """Chế độ (a): [(vùng, điểm số, tên mặt, nhóm)] của các mặt có ảnh lật; trả thêm số mặt bị bỏ vì thiếu ảnh lật."""
    rows, skipped = [], 0
    for fn in files:
        sc = flip_scores_g(mp50[fn], cfg)
        if sc is None:
            skipped += 1
            continue
        rows += [(r, v, fn, g) for r, v, g in sc]
    return rows, skipped


def threshold_table(score, nface, out=print):
    """Với từng phân vị: ngưỡng, % điểm bị cờ, số cờ/mặt. Trả list (q, t, % cờ, cờ/mặt)."""
    out("phân vị  ngưỡng t_flip  điểm bị cờ  cờ/mặt")
    table = []
    for q in QUANTILES:
        t = float(np.quantile(score, q))
        flag = score > t
        table.append((q, t, float(flag.mean() * 100), float(flag.sum() / max(nface, 1))))
        out(f"{q:7.2f}  {t:12.4f}  {flag.mean() * 100:9.1f}%  {flag.sum() / max(nface, 1):6.1f}")
    return table


def report_unlabelled(rows, out=print):
    """Chế độ (a). Trả dict(t_flip, flags_per_face, flagged_pct, table, by_region, by_group). rows: (vùng, điểm số, tên mặt[, nhóm])."""
    reg = np.array([r[0] for r in rows])
    grp = np.array([r[3] if len(r) > 3 else r[0] for r in rows])
    score = np.array([r[1] for r in rows])
    faces = sorted(set(r[2] for r in rows))
    out(f"{len(faces)} mặt, {len(rows)} điểm (KHÔNG có đáp án: không tính được AUROC; AUROC cần nhãn gán tay G/X, dùng chế độ --gt)")
    stat = lambda v: f"{np.median(v):.4f}/{np.quantile(v, 0.85):.4f}/{np.quantile(v, 0.95):.4f}"            # noqa: E731
    gorder = list(dict.fromkeys(grp))                                                                         # thứ tự nhóm = thứ tự xuất hiện (thứ tự config)
    out("điểm số theo nhóm (trung vị / phân vị 0,85 / phân vị 0,95): " + ", ".join(f"{g} {stat(score[grp == g])}" for g in gorder))
    out("điểm số theo vùng (trung vị / phân vị 0,85 / phân vị 0,95): " + ", ".join(f"{g} {stat(score[reg == g])}" for g in sorted(set(reg))))
    table = threshold_table(score, len(faces), out)
    t = round(float(np.quantile(score, SUGGEST_Q)), 4)
    flagged = score > t
    per_face = float(flagged.sum() / len(faces))
    by_reg = {g: float((flagged[reg == g]).mean() * 100) for g in sorted(set(reg))}
    by_grp = {g: float((flagged[grp == g]).mean() * 100) for g in gorder}
    out(f"ĐỀ XUẤT t_flip = {t:g} (phân vị {SUGGEST_Q:g} trên {len(faces)} mặt): {100 * flagged.mean():.1f}% điểm bị cờ, {per_face:.1f} cờ/mặt; "
        "theo nhóm: " + ", ".join(f"{g} {v:.0f}%" for g, v in by_grp.items()) + "; theo vùng: " + ", ".join(f"{g} {v:.0f}%" for g, v in by_reg.items()))
    out(f"(so với đề xuất {V2_T_FLIP:g} của định nghĩa 50 điểm cũ version 2, có viền hàm, không còn hiệu lực sau QĐ-003)")
    out("(chỉ đề xuất cho P2 chốt ngày 12/10; chưa ghi vào config)")
    return dict(t_flip=t, flags_per_face=per_face, flagged_pct=float(100 * flagged.mean()), table=table, by_region=by_reg, by_group=by_grp)


def tolerance_for(cfg, region, tol):
    """Sai số chấp nhận (% IOD) của một vùng: config.tolerance (dict theo vùng hoặc một số) nếu có, không thì tol."""
    t = cfg.get("tolerance")
    if isinstance(t, dict):
        v = t.get(region)
        return float(v) if v is not None else tol
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return float(t)
    return tol


def collect_points(files, mp50, cfg, gt, pred_upload, tol):
    """Chế độ (b): [(vùng, điểm số, lỗi % IOD, tên mặt, nhóm)]. files: {tên mặt trong run: tên ảnh không đuôi trong nhãn}. pred_upload: dự đoán theo toạ độ nhãn."""
    import eval50
    rows = []
    for fn, key in files.items():
        sc = flip_scores_g(mp50[fn], cfg)
        if sc is None or key not in gt or key not in pred_upload:
            continue
        err, _missing, d = eval50.point_errors(pred_upload[key], gt[key], cfg)
        if d is None:
            continue
        for p, (reg, v, grp) in zip(cfg["points"], sc):
            if p["name"] in err:
                rows.append((reg, v, err[p["name"]], fn, grp))
    return rows


def _mang(rows, tol, cfg=None):
    """rows -> (vùng, nhóm, điểm số, lỗi, điểm sai) dạng mảng; điểm sai = lỗi > sai số chấp nhận (config.tolerance theo vùng nếu truyền cfg)."""
    reg = np.array([r[0] for r in rows])
    grp = np.array([r[4] if len(r) > 4 else r[0] for r in rows])
    score = np.array([r[1] for r in rows])
    err = np.array([r[2] for r in rows])
    tols = np.array([tolerance_for(cfg, g, tol) if cfg else tol for g in reg])
    return reg, grp, score, err, err > tols


def at_threshold(score, bad, t, nface):
    """Số liệu của cờ tại ngưỡng t (cờ bật khi điểm số > t): % điểm bị cờ, % điểm sai bị bắt (recall), độ chính xác (precision), cờ/mặt."""
    flag = np.asarray(score, float) > t
    bad = np.asarray(bad, bool)
    return dict(t=float(t), flagged_pct=float(flag.mean() * 100), caught=float((flag & bad).sum() / max(bad.sum(), 1) * 100),
                precision=float((flag & bad).sum() / max(flag.sum(), 1) * 100), per_face=float(flag.sum() / max(nface, 1)))


def analyze(rows, tol, cfg=None, t_flip=None):
    """Chế độ (b) trả dict thay vì in: rows = [(vùng, điểm số, lỗi % IOD, tên mặt[, nhóm])].
    Khoá: n_faces, n_points, tol, n_bad, bad_pct, auroc, by_region/by_group {tên: dict(auroc, n, n_bad, bad_pct)} (by_group None nếu rows không có nhóm),
    table [(q, t, % điểm bị cờ, % điểm sai bị bắt, độ chính xác, cờ/mặt) theo phân vị], at_t (at_threshold tại t_flip nếu t_flip không None)."""
    reg, grp, score, err, bad = _mang(rows, tol, cfg)
    nface = len(set(r[3] for r in rows))

    def part(mask):
        return dict(auroc=auroc(score[mask], bad[mask]), n=int(mask.sum()), n_bad=int(bad[mask].sum()), bad_pct=float(100 * bad[mask].mean()))

    table = []
    for q in QUANTILES:
        t = float(np.quantile(score, q))
        m = at_threshold(score, bad, t, nface)
        table.append((q, t, m["flagged_pct"], m["caught"], m["precision"], m["per_face"]))
    return dict(n_faces=nface, n_points=len(rows), tol=tol, n_bad=int(bad.sum()), bad_pct=float(100 * bad.mean()), auroc=auroc(score, bad),
                by_region={r: part(reg == r) for r in sorted(set(reg))},
                by_group={g: part(grp == g) for g in dict.fromkeys(grp)} if len(rows[0]) > 4 else None,
                table=table, at_t=None if t_flip is None else at_threshold(score, bad, float(t_flip), nface))


def report(rows, tol, out=print, cfg=None):
    """Chế độ (b): rows = [(vùng, điểm số, lỗi % IOD, tên mặt[, nhóm])]; điểm sai = lỗi > tol (hoặc config.tolerance theo vùng nếu truyền cfg)."""
    a = analyze(rows, tol, cfg)
    out(f"{a['n_faces']} mặt, {a['n_points']} điểm; điểm sai (lỗi > sai số chấp nhận, mặc định {tol:g}% IOD): {a['bad_pct']:.1f}%")
    out(f"AUROC toàn bộ: {a['auroc']:.3f}   (0,5 = cờ không có tác dụng; 1 = hoàn hảo)")
    out("AUROC theo vùng: " + ", ".join(f"{r} {v['auroc']:.3f} (sai {v['bad_pct']:.0f}%)" for r, v in a["by_region"].items()))
    if a["by_group"] is not None:
        out("AUROC theo nhóm: " + ", ".join(f"{g} {v['auroc']:.3f} (sai {v['bad_pct']:.0f}%)" for g, v in a["by_group"].items()))
    out("phân vị  ngưỡng t_flip  điểm bị cờ  % điểm sai bị bắt  độ chính xác  cờ/mặt")
    table = []
    for q, t, flagged, caught, prec, per_face in a["table"]:
        table.append((q, t, flagged, caught, prec, per_face))
        out(f"{q:7.2f}  {t:12.4f}  {flagged:9.1f}%  {caught:16.1f}%  {prec:11.1f}%  {per_face:6.1f}")
    return table


def _faces_of_set(manifest, sets):
    with open(manifest, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return {r["file"][:-4]: r["set"] for r in rows}, [r["file"][:-4] for r in rows if r["set"] in sets]


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Đo cờ low_conf: chế độ (a) không đáp án, (b) có đáp án (--gt)")
    ap.add_argument("--run", required=True)
    ap.add_argument("--set", default="Tdev", choices=["Tdev", "F", "D", "G", "X", "P"], help="Ttest không được phép (chỉ chạy một lần ngày 20/10)")
    ap.add_argument("--gt", help="nhãn gán tay (annotations.xml, raw\\*.xml hoặc zip CVAT): bật chế độ (b)")
    ap.add_argument("--tol", type=float, default=3.0, help="chế độ (b): sai số chấp nhận (%% IOD) khi config.tolerance chưa có")
    ap.add_argument("--manifest", default=os.path.join("data", "manifest.csv"))
    ap.add_argument("--config", default=os.path.join("config", "m28_config.json"))
    a = ap.parse_args(argv)
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    mp50_path = os.path.join("runs", a.run, "map50", "mp50.json")
    if not os.path.exists(mp50_path):
        sys.exit(f"Không thấy {mp50_path}: chạy prepare (map50) cho lượt này trước.")
    with open(mp50_path, encoding="utf-8") as f:
        mp50 = json.load(f)
    if a.gt:
        import eval50
        gt = eval50.read_labels(a.gt, cfg)
        from m28core import steps
        meta = steps._jload(os.path.join("runs", a.run, "crop", "meta.json"))
        box = os.path.join("runs", a.run, "crop", "box.txt")
        mode = steps.read_box_mode(box, "crop")
        keys = {n: eval50.stem(steps._file_name(n, meta[n], mode)) for n in mp50 if n in meta}
        if os.path.exists(a.manifest):
            sets, _ = _faces_of_set(a.manifest, {a.set})
            dropped = [n for n in keys if sets.get(n) == "Ttest"]
            for n in dropped:
                del keys[n]
            if dropped:
                print(f"Bỏ {len(dropped)} mặt thuộc Ttest (không dùng để chọn ngưỡng).")
        pred_up = eval50.read_run_pred(a.run, cfg)
        rows = collect_points(keys, mp50, cfg, gt, pred_up, a.tol)
        if not rows:
            sys.exit("Không ghép được mặt nào giữa nhãn và lượt chạy (tên ảnh khác nhau? thiếu ảnh lật?).")
        report(rows, a.tol, cfg=cfg)
        return 0
    if not os.path.exists(a.manifest):
        sys.exit(f"Cần {a.manifest} để chọn mặt của tập {a.set}.")
    _, files = _faces_of_set(a.manifest, {a.set})
    files = [f for f in files if f in mp50]
    if not files:
        sys.exit(f"Không có mặt nào của tập {a.set} trong {mp50_path}. Chạy prepare --set {a.set} trước.")
    rows, skipped = collect_scores(files, mp50, cfg)
    if skipped:
        print(f"Bỏ {skipped} mặt không có ảnh lật.")
    report_unlabelled(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
