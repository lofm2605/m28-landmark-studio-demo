"""Kiểm phép lật của ánh xạ 50 điểm DMS (P3, tiêu chí 7/10), KHÔNG cần đáp án. Chạy sau make_config.py, cần runs\\<run> có pred478 cho tập F, Tdev.

    python tool\\check_flip.py --run <run> [--manifest data\\manifest.csv] [--config config\\m28_config.json] [--map config\\map_mp50.json] [--mirror config\\mp_mirror478.json]

(1) Lật hai lần: lấy 50 điểm dự đoán của một mặt, lật theo cặp `flip` và x -> w - x hai lần: phải về đúng chỗ cũ (lệch <= 0,01 px); và hoán vị
    gương 478 đỉnh là phép đối hợp.
(2) Cặp `flip` của config trùng hoán vị gương đỉnh (perm[mp_idx(p)] == mp_idx(flip(p)); điểm side M nằm trên trục).
(3) Lệch gốc/lật d_flip trên mặt thẳng (pose = 0): mỗi mặt lấy trung bình lệch của 50 điểm / IOD DỰ ĐOÁN (hai điểm `iod_points` = hai khoé mắt ngoài của ảnh gốc), rồi TRUNG VỊ
    trên mặt. Tiêu chí kế hoạch: 20 mặt thẳng F đầu tiên < 3% IOD. In thêm mọi mặt thẳng F, Tdev, và với mỗi tập: theo NHÓM (7: longmaytrai, longmayphai, songmui, mattrai,
    matphai, moingoai, moitrong) và theo vùng thô (brow, nose, eye, lip). Nhóm và vùng đọc từ config (`group`, `region`), không cứng tên điểm.
(4) Đối chứng: quên đổi tên theo cặp thì lệch phải lớn hơn hẳn (> 10% IOD).
(5) Kiểm bên THEO ẢNH (config version 3, quy ước ngược version 2): trên mặt thẳng F, x(iod_points[0]) < x(iod_points[1]) (`mattrai_1` ở nửa trái ảnh hơn `matphai_1`) và
    x(điểm cuối nhóm lông mày trái ảnh) < x(điểm tương ứng nhóm lông mày phải ảnh) (`longmaytrai_5` < `longmayphai_5`; không còn viền hàm): báo số mặt đạt; đạt khi >= 98% mặt.
Thoát mã 1 khi (1), (2), tiêu chí 20 mặt, đối chứng hoặc kiểm bên không đạt. Config thiếu `side_convention: "image"` (config version 2) bị từ chối ngay.

Lưu ý: hoán vị gương của config/mp_mirror478.json được học trên chính các mặt F (make_config.py --run), nên d_flip trên F lạc quan hơn một chút;
d_flip trên Tdev (không dùng để học) mới là số trung thực. Lệch d_flip còn gồm cả sai khác thật của MediaPipe giữa ảnh gốc và ảnh lật.
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m28core import mirror  # noqa: E402
from m28core.mapping import apply_map, check_side_convention  # noqa: E402

CRITERION = 3.0          # % IOD, 20 mặt thẳng F đầu tiên
CONTROL_MIN = 10.0       # % IOD, đối chứng quên đổi tên phải vượt số này
SIDE_MIN = 0.98


def d_flip_detail(orig478, flip478, cfg, mp_map, rename=True):
    """dict(mean, region, group) của một mặt: mean = lệch trung bình 50 điểm / IOD dự đoán * 100; region, group = {tên: lệch trung bình % IOD}.
    rename=False: đối chứng quên đổi tên theo cặp."""
    names = [p["name"] for p in cfg["points"]]
    o = apply_map(orig478, mp_map, cfg)
    if rename:
        u = apply_map(flip478, mp_map, cfg, flipped=True)
    else:                                                       # bỏ lật (w - x) nhưng quên đổi tên: điểm n lấy đỉnh của chính n trên ảnh lật
        w = float(mp_map.get("flip_width", 512.0))
        raw = apply_map(flip478, mp_map, cfg)
        u = {n: [w - raw[n][0], raw[n][1]] for n in names}
    e1, e2 = cfg["iod_points"]
    iod = float(np.linalg.norm(np.asarray(o[e1]) - np.asarray(o[e2]))) or 1.0
    d = {n: float(np.linalg.norm(np.asarray(o[n]) - np.asarray(u[n]))) / iod * 100 for n in names}
    reg, grp = {}, {}
    for p in cfg["points"]:
        reg.setdefault(p["region"], []).append(d[p["name"]])
        grp.setdefault(p["group"], []).append(d[p["name"]])
    return dict(mean=float(np.mean(list(d.values()))), region={r: float(np.mean(v)) for r, v in reg.items()},
                group={g: float(np.mean(v)) for g, v in grp.items()})


def d_flip_face(orig478, flip478, cfg, mp_map, rename=True):
    """(lệch trung bình 50 điểm / IOD dự đoán * 100, {vùng: lệch trung bình % IOD}) của một mặt. rename=False: đối chứng quên đổi tên theo cặp."""
    r = d_flip_detail(orig478, flip478, cfg, mp_map, rename)
    return r["mean"], r["region"]


def double_flip_error(pts50, cfg, w):
    """Lật hai lần theo cặp flip và x -> w - x: lệch lớn nhất (px) so với ban đầu."""
    flip = {p["name"]: p["flip"] for p in cfg["points"]}
    once = {flip[n]: [w - v[0], v[1]] for n, v in pts50.items()}
    twice = {flip[n]: [w - v[0], v[1]] for n, v in once.items()}
    if set(once) != set(pts50) or set(twice) != set(pts50):                  # cặp flip không phải song ánh: lật không về được
        return float("inf")
    return float(max(np.linalg.norm(np.asarray(twice[n]) - np.asarray(pts50[n])) for n in pts50))


def perm_errors(cfg, perm):
    """Lỗi (danh sách chuỗi) khi cặp flip của config không khớp hoán vị gương, hoặc điểm side M không nằm trên trục."""
    err = []
    by = {p["name"]: p for p in cfg["points"]}
    for p in cfg["points"]:
        q = by.get(p["flip"])
        if q is None:
            err.append(f"{p['name']}: flip {p['flip']} không có trong config")
            continue
        if perm[p["mp_idx"]] != q["mp_idx"]:
            err.append(f"{p['name']} (đỉnh {p['mp_idx']}): hoán vị gương cho {perm[p['mp_idx']]}, flip {q['name']} dùng {q['mp_idx']}")
        if p["side"] == "M" and perm[p["mp_idx"]] != p["mp_idx"]:
            err.append(f"{p['name']}: side M nhưng đỉnh {p['mp_idx']} không nằm trên trục")
    return err


def side_pairs(cfg):
    """[(điểm nửa TRÁI ảnh, điểm nửa PHẢI ảnh)] dùng cho kiểm bên: hai điểm `iod_points` (khoé mắt ngoài) và cặp ĐUÔI lông mày (điểm cuối của nhóm lông mày
    có side L và điểm đối xứng của nó). Đọc từ config (region, side, flip), không cứng tên: config version 3 cho (mattrai_1, matphai_1) và (longmaytrai_5, longmayphai_5)."""
    by = {p["name"]: p for p in cfg["points"]}
    pairs = [tuple(cfg["iod_points"])]
    brow_l = [p for p in cfg["points"] if p["region"] == "brow" and p["side"] == "L"]
    if brow_l:
        tail = brow_l[-1]
        pairs.append((tail["name"], by[tail["flip"]]["name"]))
    return pairs


def side_ok(orig478, cfg, mp_map):
    """Mặt thẳng, ảnh không lật: nhóm *trai nằm nửa TRÁI ảnh, *phai nửa PHẢI ảnh (quy ước theo ảnh): x(mattrai_1) < x(matphai_1) và x(longmaytrai_5) < x(longmayphai_5)."""
    o = apply_map(orig478, mp_map, cfg)
    return all(o[l][0] < o[r][0] for l, r in side_pairs(cfg))


def select(rows, pred, set_name, pose0=True):
    out = []
    for r in rows:
        n = r["file"][:-4] if r["file"].lower().endswith(".png") else r["file"]
        if r.get("set") == set_name and (r.get("pose") == "0" or not pose0) and n in pred and pred[n].get("flip"):
            out.append(n)
    return out


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Kiểm phép lật của ánh xạ 50 điểm (không cần đáp án)")
    ap.add_argument("--run", required=True)
    ap.add_argument("--manifest", default=os.path.join("data", "manifest.csv"))
    ap.add_argument("--config", default=os.path.join("config", "m28_config.json"))
    ap.add_argument("--map", default=os.path.join("config", "map_mp50.json"))
    ap.add_argument("--mirror", default=os.path.join("config", "mp_mirror478.json"))
    a = ap.parse_args(argv)
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(a.map, encoding="utf-8") as f:
        mp_map = json.load(f)
    try:
        check_side_convention(cfg)
    except ValueError as e:
        sys.exit(str(e))
    mir = mirror.load_mirror(a.mirror)
    with open(os.path.join("runs", a.run, "mediapipe", "pred478.json"), encoding="utf-8") as f:
        pred = json.load(f)
    with open(a.manifest, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    ok = True
    F, T = select(rows, pred, "F"), select(rows, pred, "Tdev")
    if not F:
        sys.exit("Không có mặt F thẳng (pose = 0) có cả ảnh gốc và ảnh lật trong lượt này: chạy prepare --set F Tdev trước.")
    # (1)
    w = float(mp_map.get("flip_width", 512.0))
    p50 = apply_map(pred[F[0]]["orig"], mp_map, cfg)
    err = double_flip_error(p50, cfg, w)
    inv = mirror.check_involution(mir["perm"])
    good = err <= 0.01 and not inv
    print(f"(1) lật 50 điểm hai lần: lệch tối đa {err:.2e} px; hoán vị gương 478 đỉnh là phép đối hợp: {'có' if not inv else 'KHÔNG ' + str(inv)} ->",
          "đạt" if good else "KHÔNG ĐẠT")
    ok &= good
    # (2)
    pe = perm_errors(cfg, mir["perm"])
    n_fixed = len(mir["fixed"])
    print(f"(2) cặp flip của config trùng hoán vị gương ({len(cfg['points'])} điểm; hoán vị có {n_fixed} đỉnh trên trục): "
          + ("đạt" if not pe else "KHÔNG ĐẠT: " + "; ".join(pe[:3])))
    ok &= not pe
    # (3)
    sets = (("20 mặt thẳng F đầu tiên (tiêu chí kế hoạch)", F[:20]), ("mọi mặt thẳng F", F), ("mọi mặt thẳng Tdev", T))
    m20 = None
    groups = list(dict.fromkeys(p["group"] for p in cfg["points"]))            # thứ tự nhóm và vùng theo config
    regs = list(dict.fromkeys(p["region"] for p in cfg["points"]))
    for label, files in sets:
        if not files:
            continue
        res = [d_flip_detail(pred[f]["orig"], pred[f]["flip"], cfg, mp_map) for f in files]
        v = np.array([r["mean"] for r in res])
        by_reg = {g: float(np.median([r["region"][g] for r in res])) for g in regs}
        by_grp = {g: float(np.median([r["group"][g] for r in res])) for g in groups}
        print(f"(3) lệch gốc/lật, {label}: n={len(files)}, trung vị {np.median(v):.2f}% IOD (trung bình {v.mean():.2f}%, p90 {np.percentile(v, 90):.2f}%)")
        print("      theo nhóm (trung vị): " + ", ".join(f"{g} {by_grp[g]:.2f}" for g in groups))
        print("      theo vùng (trung vị): " + ", ".join(f"{g} {by_reg[g]:.2f}" for g in regs))
        if label.startswith("20 mặt"):
            m20 = float(np.median(v))
    if m20 is not None:
        good = m20 < CRITERION
        print(f"    tiêu chí 20 mặt đầu < {CRITERION:g}% IOD: {m20:.2f}% ->", "đạt" if good else "KHÔNG ĐẠT")
        ok &= good
        ctrl = float(np.median([d_flip_face(pred[f]["orig"], pred[f]["flip"], cfg, mp_map, rename=False)[0] for f in F[:20]]))
        good = ctrl > CONTROL_MIN
        print(f"(4) đối chứng quên đổi tên theo cặp: trung vị {ctrl:.1f}% IOD (phải > {CONTROL_MIN:g}%) ->", "đạt" if good else "KHÔNG ĐẠT")
        ok &= good
    # (5)
    n_side = sum(side_ok(pred[f]["orig"], cfg, mp_map) for f in F)
    good = n_side >= SIDE_MIN * len(F)
    print("(5) kiểm bên theo ảnh: " + " và ".join(f"{l} ở nửa trái hơn {r}" for l, r in side_pairs(cfg)) + f" trên {n_side}/{len(F)} mặt thẳng F ->",
          "đạt" if good else "KHÔNG ĐẠT")
    ok &= good
    print("KẾT QUẢ:", "đạt" if ok else "KHÔNG ĐẠT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
