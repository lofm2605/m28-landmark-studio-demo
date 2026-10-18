"""Đo sai số 50 điểm so với nhãn gán tay (đáp án là nhãn của nhóm trong CVAT). Chỉ numpy + thư viện chuẩn.

    python tool\\eval50.py --gt raw\\<đáp án>.xml --pred runs\\<run>\\xml\\prelabel.xml [--condition manual|assisted] [--out outputs\\nme_per_face.csv] [--append]
    python tool\\eval50.py --gt raw\\<đáp án>.xml --run <run>                      (dự đoán lấy từ runs\\<run>: map50\\mp50.json + crop\\meta.json + crop\\box.txt)

Đầu vào: file "CVAT for images 1.1" (annotations.xml, file .xml trong raw\\, hoặc zip xuất từ CVAT). Mỗi ảnh bảy skeleton (mỗi nhóm một, label = tên nhóm); nhóm có nhiều hơn một skeleton thì báo và bỏ ảnh
đó. Ghép dự đoán và đáp án THEO TÊN ẢNH (bỏ đuôi) và TÊN ĐIỂM, không theo id hay thứ tự. Dự đoán có hai nguồn:
  (a) một file XML khác cùng hệ toạ độ và tên ảnh (cách khuyến nghị: runs\\<run>\\xml\\prelabel.xml của `push`, đúng file đã tải lên CVAT);
  (b) --run <run>: đọc dự đoán từ runs rồi đổi sang hệ toạ độ và tên ảnh tải lên CVAT bằng ĐÚNG logic steps._file_name/_face_pts của push.

Chỉ số (theo kế hoạch P3, mục 3, sửa cho đáp án 50 điểm):
  * IOD = khoảng cách hai điểm `iod_points` (hai khoé mắt ngoài `mattrai_1`, `matphai_1`) của ĐÁP ÁN 50 điểm; thiếu một trong hai thì mặt không chấm được (báo).
  * chỉ số CHÍNH: điểm E đo điểm-điểm; điểm C đo khoảng cách tới ĐƯỜNG GẤP KHÚC nối các điểm đáp án theo `curve` (danh sách tên trong config). Điểm đáp án
    thiếu (không có hoặc outside="1") bị bỏ khỏi đường gấp khúc và khỏi phép đo (đếm riêng); đường chỉ còn một điểm thì đo tới điểm đó.
  * chỉ số PHỤ: điểm-điểm cả 50 điểm.
  * LƯU Ý đường gấp khúc thưa: curve của điểm C nằm TRONG nhóm của nó (config version 3, QĐ-003: không còn viền hàm, không còn ngoại lệ môi trong). Với điểm C ở giữa
    (ví dụ giữa mí trên `mattrai_3`, curve [mattrai_1 .. mattrai_5]) lỗi dọc đường gần như bằng 0 khi dự đoán trượt dọc theo mí, và đường nối chỉ vài điểm đáp án nên lỗi
    chỉ thật sự nhỏ quanh điểm đáp án; ở môi (`moingoai_*`, `moitrong_*`) lỗi trượt ngang dọc mép được tha còn lỗi vuông góc với mép vẫn tính. Đó là chủ ý (người gán tay
    không đặt "đúng giữa" tới từng pixel), nhưng nghĩa là NME chính <= NME phụ.
  * NME mặt = trung bình chỉ số chính trên các điểm đo được, % IOD. Mặt hỏng: NME >= 10%. nme_eye: cùng chỉ số trên vùng mắt (region eye = đủ 16 điểm của `mattrai`, `matphai`).
  * độ mở mắt = khoảng cách mí trên-dưới / IOD theo ba cặp `coincide` của mỗi mắt (`_2`-`_8`, `_3`-`_7`, `_4`-`_6`; sáu cặp hai mắt); so dự đoán với đáp án
    (lệch tuyệt đối trung bình các cặp, % IOD).

nme_per_face.csv (cột P5 đã hẹn): face_id, condition, nme, nme_eye; sau đó nme_p2p, các cột theo vùng thô (reg_brow, reg_eye, reg_lip, reg_nose = trung bình chỉ số chính
của vùng; reg_eye trùng nme_eye về số; version 3 KHÔNG còn reg_jaw vì không còn viền hàm, các cột còn lại giữ nghĩa), eye_open_err, n_missing. Số liệu tổng hợp in ra màn hình:
trung bình, trung vị, % mặt hỏng, theo vùng.
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BAD = 10.0                      # mặt hỏng: NME >= 10% IOD
IMG_EXT = (".png", ".jpg", ".jpeg")


def point_to_curve(p, curve):
    """Khoảng cách ngắn nhất từ điểm p tới đường gấp khúc curve (m, 2); đoạn dài 0 không chia cho 0; curve một điểm thì là khoảng cách tới điểm đó."""
    p, curve = np.asarray(p, float), np.asarray(curve, float)
    if len(curve) == 1:
        return float(np.linalg.norm(p - curve[0]))
    a, ab = curve[:-1], curve[1:] - curve[:-1]
    u = ((p - a) * ab).sum(1) / np.maximum((ab ** 2).sum(1), 1e-9)
    return float(np.linalg.norm(a + np.clip(u, 0, 1)[:, None] * ab - p, axis=1).min())


def _have(d, n):
    v = d.get(n)
    return v is not None and v[0] is not None and v[1] is not None and np.isfinite(v).all()


def iod(gt, cfg):
    """Khoảng cách hai điểm iod_points của đáp án 50 điểm; None nếu thiếu một điểm hoặc hai điểm trùng."""
    a, b = cfg["iod_points"]
    if not (_have(gt, a) and _have(gt, b)):
        return None
    d = float(np.linalg.norm(np.asarray(gt[a], float) - np.asarray(gt[b], float)))
    return d if d > 1e-9 else None


def point_errors(pred, gt, cfg):
    """{tên điểm: lỗi chính % IOD} cho các điểm có cả dự đoán và đáp án (E điểm-điểm, C tới đường gấp khúc đáp án theo curve).
    Trả (errors, missing, d): missing = tên điểm bị bỏ (thiếu ở đáp án hoặc dự đoán); d = IOD đáp án; d None thì errors rỗng (mặt không chấm được)."""
    d = iod(gt, cfg)
    if d is None:
        return {}, [p["name"] for p in cfg["points"]], None
    err, missing = {}, []
    for p in cfg["points"]:
        n = p["name"]
        if not (_have(gt, n) and _have(pred, n)):
            missing.append(n)
            continue
        pt = np.asarray(pred[n], float)
        if p["type"] == "E" or not p.get("curve"):
            e = float(np.linalg.norm(pt - np.asarray(gt[n], float)))
        else:
            line = [gt[c] for c in p["curve"] if _have(gt, c)]
            e = point_to_curve(pt, np.asarray(line, float)) if line else float(np.linalg.norm(pt - np.asarray(gt[n], float)))
        err[n] = e / d * 100
    return err, missing, d


def p2p_errors(pred, gt, cfg):
    """{tên điểm: lỗi điểm-điểm % IOD} (chỉ số phụ)."""
    d = iod(gt, cfg)
    if d is None:
        return {}
    return {p["name"]: float(np.linalg.norm(np.asarray(pred[p["name"]], float) - np.asarray(gt[p["name"]], float))) / d * 100
            for p in cfg["points"] if _have(gt, p["name"]) and _have(pred, p["name"])}


def eye_openness(pts, cfg, d):
    """Độ mở hai mắt (khoảng mí trên-dưới / IOD, %) theo cặp coincide của vùng mắt (ba cặp mỗi mắt); {} nếu thiếu.
    Mỗi cặp lấy một lần, ở điểm đứng TRƯỚC trong config (so theo thứ tự config chứ không theo chữ cái: `moingoai_10` < `moingoai_2` theo chữ)."""
    out = {}
    order = {p["name"]: i for i, p in enumerate(cfg["points"])}
    for p in cfg["points"]:
        if p["region"] == "eye" and p.get("coincide") and order[p["name"]] < order.get(p["coincide"], -1):
            a, b = p["name"], p["coincide"]
            if _have(pts, a) and _have(pts, b) and d:
                out[a] = float(np.linalg.norm(np.asarray(pts[a], float) - np.asarray(pts[b], float))) / d * 100
    return out


def face_scores(pred, gt, cfg):
    """Một mặt: dict(ok, reason, nme, nme_p2p, nme_eye, region{vùng: trung bình lỗi chính}, eye_open_err, n_missing, errors{tên: lỗi})."""
    err, missing, d = point_errors(pred, gt, cfg)
    if d is None:
        return dict(ok=False, reason="đáp án thiếu khoảng cách hai khoé mắt ngoài (iod_points)", n_missing=len(missing))
    if not err:
        return dict(ok=False, reason="không có điểm nào đo được", n_missing=len(missing))
    p2p = p2p_errors(pred, gt, cfg)
    reg = {}
    for p in cfg["points"]:
        if p["name"] in err:
            reg.setdefault(p["region"], []).append(err[p["name"]])
    regm = {r: float(np.mean(v)) for r, v in reg.items()}
    og, op = eye_openness(gt, cfg, d), eye_openness(pred, cfg, d)
    oerr = [abs(op[k] - og[k]) for k in og if k in op]
    return dict(ok=True, reason="", nme=float(np.mean(list(err.values()))), nme_p2p=float(np.mean(list(p2p.values()))),
                nme_eye=regm.get("eye"), region=regm, eye_open_err=float(np.mean(oerr)) if oerr else None,
                n_missing=len(missing), errors=err, iod=d)


# ---------- đọc nhãn ----------
def stem(name):
    base = os.path.basename(str(name).replace("\\", "/"))
    b, ext = os.path.splitext(base)
    return b if ext.lower() in IMG_EXT else base


def read_labels(path, cfg, warn=print):
    """{tên ảnh không đuôi: {tên điểm: [x, y]}} từ annotations.xml / file .xml / zip xuất của CVAT. Điểm outside="1" hoặc thiếu toạ độ bị bỏ.
    Mỗi mặt có BẢY skeleton, mỗi nhóm một (label = tên nhóm, QĐ-004); điểm của các skeleton được gộp lại theo tên điểm. Ảnh có nhiều hơn một skeleton cùng nhóm bị báo
    và bỏ; ảnh không có skeleton nào của bảy nhóm thì không có trong kết quả (có skeleton lạ, ví dụ label face50 CŨ của bản một-skeleton, thì báo một lần)."""
    from m28core import cvat_io
    if str(path).lower().endswith(".zip"):
        data = cvat_io.read_zip_annotations(path)
    else:
        with open(path, "rb") as f:
            data = f.read()
    ann = cvat_io.parse_annotations(data, [p["name"] for p in cfg["points"]])           # nhãn số 1..50 của CVAT đổi về tên config
    groups = {}
    for p in cfg["points"]:
        groups.setdefault(p.get("group") or cvat_io.group_of_name(p["name"]), set()).add(p["name"])
    out, stale_warned = {}, False
    for name, im in ann.items():
        sk = [s for s in im["skeletons"] if s["label"] in groups]
        if not sk:
            if im["skeletons"] and not stale_warned:
                stale_warned = True
                warn(f"Cảnh báo: nhãn có skeleton label {im['skeletons'][0]['label']!r}, không thuộc bảy nhóm của config ({', '.join(groups)}): nhãn dùng label face50 CŨ "
                     "(một skeleton: định nghĩa 50 điểm version 2 hoặc bản đầu của version 3, trước QĐ-004) hoặc config không đúng version. Nhãn cũ không đo được bằng config hiện tại.")
            continue
        dup = [g for g in groups if sum(1 for s in sk if s["label"] == g) > 1]
        if dup:
            warn(f"Cảnh báo: ảnh {name} có nhiều hơn một skeleton nhóm {dup[0]} (mong đúng một mỗi nhóm): bỏ ảnh này.")
            continue
        pts = {}
        for s in sk:
            for n, p in s["points"].items():
                if n in groups[s["label"]] and p["x"] is not None and str(p.get("outside")) != "1":
                    pts[n] = [p["x"], p["y"]]
        key = stem(name)
        if key in out:
            warn(f"Cảnh báo: tên ảnh {key} xuất hiện hai lần trong {path}: giữ ảnh đầu.")
            continue
        out[key] = pts
    return out


def read_run_pred(run, cfg, runs_dir="runs"):
    """Dự đoán của lượt run theo hệ toạ độ và tên ảnh tải lên CVAT, dùng đúng steps._file_name và steps._face_pts của push."""
    from m28core import steps
    rd = os.path.join(runs_dir, run)
    names = [p["name"] for p in cfg["points"]]
    meta = steps._jload(os.path.join(rd, "crop", "meta.json"))
    mp50 = steps._jload(os.path.join(rd, "map50", "mp50.json"))
    box = os.path.join(rd, "crop", "box.txt")
    mode = steps.read_box_mode(box, "crop")
    out = {}
    for n in mp50:
        if n not in meta:
            continue
        pts, _w, _h = steps._face_pts(mode, n, meta, mp50, names)
        out[stem(steps._file_name(n, meta[n], mode))] = {nm: [float(x), float(y)] for nm, (x, y) in zip(names, pts)}
    return out


# ---------- tổng hợp ----------
def evaluate(pred, gt, cfg, condition="assisted"):
    """pred, gt: {tên ảnh không đuôi: {tên điểm: [x, y]}}. Trả dict(rows, skipped, missing_pred, extra_pred, summary)."""
    rows, skipped = [], []
    common = [k for k in gt if k in pred]
    for k in common:
        s = face_scores(pred[k], gt[k], cfg)
        if not s["ok"]:
            skipped.append((k, s["reason"]))
            continue
        rows.append(dict(face_id=k, condition=condition, **s))
    missing_pred = [k for k in gt if k not in pred]
    extra_pred = [k for k in pred if k not in gt]
    return dict(rows=rows, skipped=skipped, missing_pred=missing_pred, extra_pred=extra_pred, summary=summarize(rows, cfg))


def summarize(rows, cfg):
    if not rows:
        return dict(n_faces=0)
    nme = np.array([r["nme"] for r in rows])
    p2p = np.array([r["nme_p2p"] for r in rows])
    regions = sorted({r2 for r in rows for r2 in r["region"]})
    out = dict(n_faces=len(rows), nme_mean=float(nme.mean()), nme_median=float(np.median(nme)), frac_bad=float((nme >= BAD).mean()),
               n_bad=int((nme >= BAD).sum()), nme_p2p_mean=float(p2p.mean()), nme_p2p_median=float(np.median(p2p)),
               region_mean={g: float(np.mean([r["region"][g] for r in rows if g in r["region"]])) for g in regions},
               region_median={g: float(np.median([r["region"][g] for r in rows if g in r["region"]])) for g in regions})
    eo = [r["eye_open_err"] for r in rows if r["eye_open_err"] is not None]
    out["eye_open_err_mean"] = float(np.mean(eo)) if eo else None
    out["n_missing_points"] = int(sum(r["n_missing"] for r in rows))
    return out


def format_summary(res, cfg):
    s = res["summary"]
    if not s["n_faces"]:
        return "Không có mặt nào chấm được."
    lines = [f"{s['n_faces']} mặt chấm được; NME chính (E điểm-điểm, C tới đường gấp khúc đáp án): trung bình {s['nme_mean']:.2f}%, trung vị "
             f"{s['nme_median']:.2f}% IOD; mặt hỏng (>= {BAD:g}%): {s['n_bad']} ({100 * s['frac_bad']:.1f}%)",
             f"NME phụ (điểm-điểm 50 điểm): trung bình {s['nme_p2p_mean']:.2f}%, trung vị {s['nme_p2p_median']:.2f}%",
             "Theo vùng (trung bình / trung vị): " + ", ".join(f"{g} {s['region_mean'][g]:.2f}/{s['region_median'][g]:.2f}" for g in s["region_mean"])]
    if s["eye_open_err_mean"] is not None:
        lines.append(f"Độ mở mắt: lệch tuyệt đối trung bình {s['eye_open_err_mean']:.2f}% IOD")
    if s["n_missing_points"]:
        lines.append(f"Điểm bị bỏ vì thiếu ở đáp án/dự đoán: {s['n_missing_points']}")
    if res["skipped"]:
        lines.append(f"Mặt không chấm được: {len(res['skipped'])}, ví dụ {res['skipped'][:3]}")
    if res["missing_pred"]:
        lines.append(f"Ảnh có đáp án mà không có dự đoán: {len(res['missing_pred'])}, ví dụ {res['missing_pred'][:3]}")
    if res["extra_pred"]:
        lines.append(f"Ảnh có dự đoán mà không có đáp án (bỏ qua): {len(res['extra_pred'])}")
    return "\n".join(lines)


def write_csv(path, rows, cfg, append=False):
    regions = sorted({p["region"] for p in cfg["points"]})
    cols = ["face_id", "condition", "nme", "nme_eye", "nme_p2p"] + [f"reg_{g}" for g in regions] + ["eye_open_err", "n_missing"]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    new = not (append and os.path.exists(path) and os.path.getsize(path) > 0)
    with open(path, "a" if append else "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(cols)
        for r in rows:
            w.writerow([r["face_id"], r["condition"], f"{r['nme']:.4f}", "" if r["nme_eye"] is None else f"{r['nme_eye']:.4f}", f"{r['nme_p2p']:.4f}"]
                       + [("" if g not in r["region"] else f"{r['region'][g]:.4f}") for g in regions]
                       + ["" if r["eye_open_err"] is None else f"{r['eye_open_err']:.4f}", r["n_missing"]])


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Đo NME 50 điểm so với nhãn gán tay (CVAT for images 1.1)")
    ap.add_argument("--gt", required=True, help="đáp án: annotations.xml, raw\\*.xml hoặc zip xuất từ CVAT")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pred", help="dự đoán: một file XML cùng hệ toạ độ và tên ảnh (ví dụ runs\\<run>\\xml\\prelabel.xml hoặc nhãn đã sửa)")
    g.add_argument("--run", help="dự đoán đọc từ runs\\<run> (map50, crop), đổi sang toạ độ và tên ảnh tải lên CVAT")
    ap.add_argument("--condition", default="assisted", choices=["manual", "assisted"], help="cột condition của nme_per_face.csv")
    ap.add_argument("--config", default=os.path.join("config", "m28_config.json"))
    ap.add_argument("--out", default=os.path.join("outputs", "nme_per_face.csv"))
    ap.add_argument("--append", action="store_true", help="nối vào file có sẵn (chạy lần lượt manual rồi assisted)")
    a = ap.parse_args(argv)
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    gt = read_labels(a.gt, cfg)
    pred = read_labels(a.pred, cfg) if a.pred else read_run_pred(a.run, cfg)
    res = evaluate(pred, gt, cfg, a.condition)
    print(format_summary(res, cfg))
    if res["rows"]:
        write_csv(a.out, res["rows"], cfg, a.append)
        print(f"Đã ghi {a.out} ({len(res['rows'])} mặt, condition={a.condition})")
    return 0 if res["rows"] else 1


if __name__ == "__main__":
    sys.exit(main())
