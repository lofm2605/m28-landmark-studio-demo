"""Kiểm nhanh khách quan, KHÔNG cần gán tay: so 50 điểm DMS của ta với 5 điểm mốc của DrivFace (606 ảnh, 4 tài xế). Chỉ để tham khảo.

    python tool\\check_drivface.py --drivface <thư mục DrivFace> [--model face_landmarker.task] [--limit N] [--out outputs\\drivface_errors.csv]
        [--old-config <bản chép config version 2> --old-map <bản chép map version 2>]     (so định nghĩa 50 điểm CŨ với DMS trên cùng ảnh)

Chạy giống `prepare --box auto`: detect_box -> square_crop 512 -> MediaPipe trên ảnh cắt -> apply_map (ánh xạ chọn đỉnh) -> đổi về toạ độ
khung gốc (x / k + left, y / k + top). Bộ 5 điểm của DrivFace: tâm mắt RE/LE, mũi N, khoé miệng RM/LM; có định nghĩa riêng (không phải 50 điểm của ta, không phải đáp án). Vì vậy:
  * chỉ để tham khảo, không dùng thay đáp án 50 điểm, không dùng số này chỉnh đỉnh trừ lỗi thô rõ ràng;
  * tâm mắt DrivFace so với TRUNG BÌNH 8 điểm của mỗi mắt (config version 3: `mattrai` / `matphai`; version 2 chỉ có 4 điểm mỗi mắt) và với tâm iris MediaPipe (468 / 473)
    để biết sai số NỀN của chính đáp án DrivFace;
  * mũi so với `songmui_4` (chóp mũi, đỉnh 1; không còn chân mũi trong 50 điểm) và, nếu có 478 điểm, với đỉnh 2 (chân giữa) và đỉnh 4 như tham chiếu NGOÀI 50 điểm;
  * khoé miệng so với `moingoai_1` / `moingoai_7` (hai khoé môi ngoài, đỉnh 61 / 291);
  * ghép bên THEO VỊ TRÍ TRONG ẢNH, không theo chữ R/L: quy ước bên của DrivFace được kiểm bằng dữ liệu trước (RE có nằm nửa trái ảnh hơn LE trên ảnh nhìn thẳng không);
    RE/RM nằm nửa trái ảnh thì ghép với nhóm `*trai` (nửa trái ảnh), ngược lại ghép với `*phai`; không kết luận được thì dừng;
  * chuẩn hoá bằng IOD = khoảng cách hai tâm mắt CỦA DRIVFACE (khác IOD khoé mắt ngoài của eval50): ảnh nhìn trái/phải IOD co lại nên % lớn hơn.
Báo trung vị / trung bình / p90 theo điểm, theo nhóm hướng nhìn (label 1 nhìn phải, 2 thẳng, 3 nhìn trái) và theo tài xế. Có --old-config/--old-map (bản chép config + map
VERSION 2 của định nghĩa cũ, kind "vertex") thì chạy thêm trên CÙNG ảnh để so; mặc định không so.

Dữ liệu DrivFace: "free for academic usage" (liên hệ tác giả nếu dùng mục đích khác), chỉ dùng nội bộ nhóm, không đăng, không commit ảnh hay kết quả theo ảnh.
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PT_KEYS = ("RE", "LE", "N", "RM", "LM")
# điểm so sánh: (tên của ta theo BÊN CỦA ẢNH, khoá tham chiếu theo bên của ảnh). Tham chiếu: EL/ER = tâm mắt nửa trái/phải ảnh, ML/MR = khoé miệng nửa trái/phải ảnh, N = mũi.
COMPARE = (("eye_trai", "EL"), ("eye_phai", "ER"), ("iris_trai", "EL"), ("iris_phai", "ER"),
           ("nose_tip", "N"), ("nose_v2", "N"), ("nose_v4", "N"), ("mouth_trai", "ML"), ("mouth_phai", "MR"))
OLD_ONLY_SKIP = ()                          # iris và đỉnh 2/4 tính từ 478 điểm nên bản định nghĩa cũ cũng có đủ; giữ tên để mã cũ import không gãy


def image_side_ref(pts, re_left=True):
    """Đổi 5 điểm DrivFace {RE, LE, N, RM, LM} sang khoá THEO BÊN CỦA ẢNH {EL, ER, N, ML, MR}. re_left: RE/RM nằm nửa trái ảnh (đã kiểm bằng side_convention)."""
    a, b = ("RE", "LE") if re_left else ("LE", "RE")
    m, n = ("RM", "LM") if re_left else ("LM", "RM")
    return {"EL": pts[a], "ER": pts[b], "N": pts["N"], "ML": pts[m], "MR": pts[n]}


def read_drivpoints(path):
    """Đọc drivPoints.txt (CSV; cột fileName có dấu cách cuối và không có .jpg). Trả list dict(name, subject, label, ang, box, pts{RE,LE,N,RM,LM})."""
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r = {k.strip(): (v if k.strip() == "fileName" else (v or "").strip()) for k, v in r.items() if k}
            if not r.get("fileName") or not r["fileName"].strip():
                continue
            g = lambda k: float(r[k])                         # noqa: E731
            rows.append(dict(name=r["fileName"], subject=int(float(r["subject"])), label=int(float(r["label"])), ang=float(r["ang"]),
                             box=(g("xF"), g("yF"), g("wF"), g("hF")),
                             pts={"RE": (g("xRE"), g("yRE")), "LE": (g("xLE"), g("yLE")), "N": (g("xN"), g("yN")),
                                  "RM": (g("xRM"), g("yRM")), "LM": (g("xLM"), g("yLM"))}))
    return rows


def find_image(img_dir, name):
    """Ảnh của một dòng: tên trong CSV + '.jpg' (tên thật có dấu cách trước .jpg); không có thì thử bỏ/thêm dấu cách."""
    base = name.rstrip()
    for cand in (name + ".jpg", base + " .jpg", base + ".jpg"):
        p = os.path.join(img_dir, cand)
        if os.path.exists(p):
            return p
    return None


def side_convention(rows):
    """Kiểm quy ước bên của DrivFace trên ảnh nhìn thẳng (label 2): tỉ lệ ảnh có RE ở nửa trái hơn LE và RM hơn LM (gần 1: RE/RM nằm nửa TRÁI ảnh, ghép với nhóm *trai;
    gần 0: nằm nửa phải ảnh, ghép với *phai). Ghép theo vị trí trong ảnh, không theo chữ R/L."""
    fr = [r for r in rows if r["label"] == 2] or rows
    eye = np.mean([r["pts"]["RE"][0] < r["pts"]["LE"][0] for r in fr])
    mouth = np.mean([r["pts"]["RM"][0] < r["pts"]["LM"][0] for r in fr])
    return float(eye), float(mouth), len(fr)


def ours_five(pts50, cfg, pts478=None):
    """Điểm của ta tương ứng 5 điểm DrivFace (toạ độ bất kỳ, miễn cùng hệ), tên THEO BÊN CỦA ẢNH. Config version 3 (chọn theo `group`, `region`, `side`, `type`, không cứng tên):
    tâm mắt = trung bình 8 điểm của mỗi mắt (eye_trai = nhóm mắt nửa trái ảnh), mũi = chóp `songmui_4` (điểm cuối nhóm sống mũi), khoé miệng = hai điểm E của môi ngoài
    (`moingoai_1` nửa trái ảnh, `moingoai_7` nửa phải ảnh). Có pts478 thì thêm tâm iris 468/473 và đỉnh 2 (chân mũi), 4 như tham chiếu NGOÀI 50 điểm.
    Config version 2 (không có `group`) rơi về cách cũ (tâm mắt = 4 điểm, mũi p29/p31, khoé miệng p41/p45) để so v2 với v3."""
    if not cfg["points"][0].get("group"):
        return ours_five_v2(pts50, cfg, pts478)
    pts = cfg["points"]
    eye_groups = {p["side"]: p["group"] for p in pts if p["region"] == "eye" and p["side"] in ("L", "R")}
    mean_of = lambda g: np.mean([pts50[p["name"]] for p in pts if p["group"] == g], axis=0)           # noqa: E731
    nose = [p["name"] for p in pts if p["region"] == "nose"][-1]
    corners = [p["name"] for p in pts if p["region"] == "lip" and p["type"] == "E" and p["line"] == "moingoai"]
    corners.sort(key=lambda n: pts50[n][0])                                                           # trái ảnh trước
    out = {"eye_trai": mean_of(eye_groups["L"]), "eye_phai": mean_of(eye_groups["R"]), "nose_tip": np.asarray(pts50[nose], float),
           "mouth_trai": np.asarray(pts50[corners[0]], float), "mouth_phai": np.asarray(pts50[corners[-1]], float)}
    if pts478 is not None:
        out.update(extra_from_478(pts478))
    return out


def extra_from_478(pts478):
    """Điểm tham chiếu NGOÀI 50 điểm, lấy thẳng từ 478 đỉnh: tâm iris 468 (nửa trái ảnh) / 473 (nửa phải ảnh), đỉnh 2 (chân mũi) và đỉnh 4."""
    return {"iris_trai": np.asarray(pts478[468], float), "iris_phai": np.asarray(pts478[473], float),
            "nose_v2": np.asarray(pts478[2], float), "nose_v4": np.asarray(pts478[4], float)}


def ours_five_v2(pts50, cfg, pts478=None):
    """Cách của định nghĩa 50 điểm CŨ (version 2, trước QĐ-003): tâm mắt = trung bình 4 điểm mắt theo line eye_R / eye_L (R = nửa trái ảnh), mũi p29 (chóp), khoé miệng p41 / p45.
    Trả cùng tên khoá với ours_five theo bên của ảnh (eye_R -> eye_trai, p29 -> nose_tip, p41 -> mouth_trai); iris, đỉnh 2 và 4 lấy từ 478 điểm như bản mới."""
    def mean_of(line):
        return np.mean([pts50[p["name"]] for p in cfg["points"] if p["line"] == line], axis=0)
    by_num = {p["name"].split("_")[0]: p["name"] for p in cfg["points"]}
    out = {"eye_trai": mean_of("eye_R"), "eye_phai": mean_of("eye_L"), "nose_tip": np.asarray(pts50[by_num["p29"]], float),
           "mouth_trai": np.asarray(pts50[by_num["p41"]], float), "mouth_phai": np.asarray(pts50[by_num["p45"]], float)}
    if pts478 is not None:
        out.update(extra_from_478(pts478))
    return out


def point_errors(ours, ref):
    """{tên so sánh: lỗi % IOD DrivFace}, IOD = khoảng cách hai tâm mắt DrivFace (EL, ER theo bên của ảnh; xem image_side_ref)."""
    iod = float(np.hypot(ref["EL"][0] - ref["ER"][0], ref["EL"][1] - ref["ER"][1]))
    if iod <= 1e-9:
        return None
    return {n: float(np.hypot(ours[n][0] - ref[k][0], ours[n][1] - ref[k][1])) / iod * 100 for n, k in COMPARE if n in ours}


def point_offsets(ours, ref):
    """{tên: (dx, dy) % IOD DrivFace}: độ lệch CÓ DẤU (ta - DrivFace, x sang phải, y xuống) để thấy lệch hệ thống (ví dụ DrivFace đặt mốc lệch một bên)."""
    iod = float(np.hypot(ref["EL"][0] - ref["ER"][0], ref["EL"][1] - ref["ER"][1]))
    if iod <= 1e-9:
        return None
    return {n: ((ours[n][0] - ref[k][0]) / iod * 100, (ours[n][1] - ref[k][1]) / iod * 100) for n, k in COMPARE if n in ours}


def stats(values):
    v = np.asarray(values, float)
    return dict(n=len(v), median=float(np.median(v)), mean=float(v.mean()), p90=float(np.percentile(v, 90))) if len(v) else dict(n=0)


def group_table(per_image, key, point_names):
    """per_image: [dict(label, subject, err{tên: %})] -> {nhóm: {điểm: stats}}."""
    groups = {}
    for r in per_image:
        groups.setdefault(r[key], []).append(r)
    return {g: {n: stats([r["err"][n] for r in rs if n in r["err"]]) for n in point_names} for g, rs in sorted(groups.items())}


def summarize(per_image, point_names):
    return {n: stats([r["err"][n] for r in per_image if n in r["err"]]) for n in point_names}


def format_table(title, table_new, table_old, names, out=print):
    out(title)
    out("  điểm              DMS v3: trung vị  trung bình  p90   |  định nghĩa cũ: trung vị  trung bình  p90")
    for n in names:
        a = table_new[n]
        if not a["n"]:
            continue
        b = table_old.get(n) if table_old else None
        old = f"{b['median']:10.1f} {b['mean']:11.1f} {b['p90']:6.1f}" if b and b["n"] else "         -           -      -"
        out(f"  {n:<16} {a['median']:11.1f} {a['mean']:11.1f} {a['p90']:6.1f}   |  {old}")


def old_vertex_apply(pts478, old_map, old_cfg):
    """Ánh xạ định nghĩa v2 (kind vertex): điểm = đỉnh mp_idx của config cũ. Không qua mapping.apply_map (đã từ chối config/map v2 sau QĐ-003)."""
    pts = np.asarray(pts478, float)
    return {p["name"]: [float(pts[p["mp_idx"]][0]), float(pts[p["mp_idx"]][1])] for p in old_cfg["points"]}


def process(rows, img_dir, model, cfg, new_map, old_map=None, old_cfg=None, limit=None, log=print, re_left=True):
    """Chạy toàn bộ: trả (per_image mới, per_image cũ hoặc None, no_face[], thiếu ảnh[]). Cần cv2 + mediapipe. re_left: RE/RM nằm nửa trái ảnh (side_convention).
    old_map/old_cfg: bản chép map + config VERSION 2 (kind "vertex"): chạy trên CÙNG 478 điểm để so. Map kiểu khác (ví dụ bản ridge cũ có mean478) không hỗ trợ."""
    import cv2
    from m28core import steps
    from m28core.cat_mat import square_crop
    from m28core.mapping import apply_map
    old_apply = None
    if old_map is not None:
        if old_map.get("kind") != "vertex":
            raise ValueError('--old-map chỉ nhận map VERSION 2 kind "vertex" (chọn đỉnh trực tiếp); map ridge cũ (có mean478) không còn hỗ trợ theo QĐ-001.')
        old_apply = old_vertex_apply
    lm = steps.make_landmarker(model)
    new_res, old_res, no_face, no_img = [], [], [], []
    try:
        for i, r in enumerate(rows[:limit] if limit else rows):
            p = find_image(img_dir, r["name"])
            if p is None:
                no_img.append(r["name"])
                continue
            bgr = cv2.imread(p)
            box = steps.detect_box(lm, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)) if bgr is not None else None
            if box is None:
                no_face.append(r["name"])
                continue
            crop, _, (left, top, k), _ = square_crop(bgr, box, np.zeros((1, 2), np.float32))
            pts = steps.run_mp_padded(lm, cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            if pts is None:
                no_face.append(r["name"])
                continue
            pts = np.asarray(pts, float)
            to_frame = lambda a: {n: (np.asarray(v, float) / k + [left, top]) for n, v in a.items()}  # noqa: E731
            frame478 = pts / k + [left, top]
            for res, fn in ((new_res, lambda: apply_map(pts, new_map, cfg)),
                            (old_res, (lambda: old_apply(pts, old_map, old_cfg)) if old_apply else None)):
                if fn is None:
                    continue
                five = ours_five(to_frame(fn()), cfg if res is new_res else old_cfg, frame478)
                ref = image_side_ref(r["pts"], re_left)
                err = point_errors(five, ref)
                if err is not None:
                    res.append(dict(name=r["name"], label=r["label"], subject=r["subject"], err=err, off=point_offsets(five, ref)))
            if (i + 1) % 100 == 0:
                log(f"  ... {i + 1}/{len(rows)} ảnh")
    finally:
        if hasattr(lm, "close"):
            lm.close()
    return new_res, (old_res if old_apply else None), no_face, no_img


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="So 50 điểm DMS của ta với 5 điểm mốc DrivFace (chỉ để tham khảo)")
    ap.add_argument("--drivface", required=True, help="thư mục DrivFace có drivPoints.txt và imgs\\DrivImages")
    ap.add_argument("--model", default="face_landmarker.task")
    ap.add_argument("--config", default=os.path.join("config", "m28_config.json"))
    ap.add_argument("--map", default=os.path.join("config", "map_mp50.json"))
    ap.add_argument("--old-map", default="", help="bản chép map_mp50.json VERSION 2 (kind vertex) để so trên cùng ảnh ('' = không so)")
    ap.add_argument("--old-config", default="", help="bản chép m28_config.json tương ứng với --old-map")
    ap.add_argument("--limit", type=int, help="chỉ chạy N ảnh đầu (thử nhanh)")
    ap.add_argument("--out", help="ghi lỗi từng ảnh ra CSV (ví dụ outputs\\drivface_errors.csv; không commit)")
    a = ap.parse_args(argv)
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(a.map, encoding="utf-8") as f:
        new_map = json.load(f)
    from m28core.mapping import check_side_convention
    try:
        check_side_convention(cfg)
    except ValueError as e:
        sys.exit(str(e))
    old_map = old_cfg = None
    if a.old_map:
        if not (os.path.exists(a.old_map) and a.old_config and os.path.exists(a.old_config)):
            sys.exit(f"--old-map {a.old_map!r} và --old-config {a.old_config!r} phải cùng có (bản chép map + config của định nghĩa cũ).")
        with open(a.old_map, encoding="utf-8") as f:
            old_map = json.load(f)
        with open(a.old_config, encoding="utf-8") as f:
            old_cfg = json.load(f)
    pts_path = os.path.join(a.drivface, "drivPoints.txt")
    img_dir = os.path.join(a.drivface, "imgs", "DrivImages")
    if not os.path.exists(pts_path) or not os.path.isdir(img_dir):
        sys.exit(f"Không thấy {pts_path} hoặc {img_dir}: --drivface là thư mục DrivFace đã giải nén.")
    rows = read_drivpoints(pts_path)
    eye, mouth, n = side_convention(rows)
    re_left = eye > 0.9 and mouth > 0.9
    re_right = eye < 0.1 and mouth < 0.1
    verdict = ("RE/RM nằm nửa TRÁI ảnh -> ghép với nhóm *trai (nửa trái ảnh): eye_trai = mattrai, mouth_trai = moingoai_1" if re_left else
               "RE/RM nằm nửa PHẢI ảnh -> RE/RM ghép với nhóm *phai (nửa phải ảnh) và LE/LM với *trai (đổi chiều ghép so với dự kiến)" if re_right else
               "KHÔNG như dự kiến: RE/LE lẫn lộn bên trong dữ liệu, dừng, kiểm lại drivPoints.txt trước khi tin số")
    print(f"{len(rows)} dòng drivPoints. Quy ước bên theo VỊ TRÍ TRONG ẢNH (trên {n} ảnh nhìn thẳng): RE ở nửa trái hơn LE: {100 * eye:.0f}%, RM hơn LM: {100 * mouth:.0f}% -> {verdict}")
    if not (re_left or re_right):
        sys.exit(1)
    new_res, old_res, no_face, no_img = process(rows, img_dir, a.model, cfg, new_map, old_map, old_cfg, a.limit, re_left=re_left)
    print(f"Chấm được {len(new_res)} ảnh; không thấy mặt: {len(no_face)} {no_face[:3]}; không có file ảnh: {len(no_img)}")
    names = [n for n, _ in COMPARE]
    old_sum = summarize(old_res, names) if old_res else None
    format_table(f"\nTHEO ĐIỂM (% IOD DrivFace, {len(new_res)} ảnh):", summarize(new_res, names), old_sum, names)
    label_name = {1: "label 1 nhìn phải", 2: "label 2 thẳng", 3: "label 3 nhìn trái"}
    out_bias = ", ".join(f"{n} ({np.median([r['off'][n][0] for r in new_res if n in r['off']]):+.1f}, {np.median([r['off'][n][1] for r in new_res if n in r['off']]):+.1f})"
                         for n in names)
    print(f"\nLệch có dấu trung vị của ánh xạ mới (dx, dy; % IOD DrivFace; dx > 0: lệch sang phải ảnh, dy > 0: lệch xuống): {out_bias}")
    for key, title in (("label", "hướng nhìn"), ("subject", "tài xế")):
        tn, to = group_table(new_res, key, names), (group_table(old_res, key, names) if old_res else {})
        for g in tn:
            format_table(f"\nNHÓM {title} {label_name.get(g, g) if key == 'label' else 'tài xế ' + str(g)} (n={tn[g][names[0]]['n']}):", tn[g], to.get(g), names)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "label", "subject"] + [f"new_{n}" for n in names] + [f"old_{n}" for n in names])
            olds = {r["name"]: r for r in (old_res or [])}
            for r in new_res:
                o = olds.get(r["name"])
                w.writerow([r["name"].strip(), r["label"], r["subject"]] + [f"{r['err'].get(n, ''):.3f}" if n in r["err"] else "" for n in names]
                           + [f"{o['err'][n]:.3f}" if o and n in o["err"] else "" for n in names])
        print(f"Đã ghi {a.out}")
    print("\nChỉ để tham khảo: 5 điểm DrivFace có định nghĩa riêng, không thay đáp án 50 điểm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
