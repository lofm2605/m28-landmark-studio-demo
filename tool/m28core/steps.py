"""Các bước của m28. Mỗi hàm nhận (args, out) và trả True chỉ khi xong thật.

Phần của P1 (crop, mediapipe, flags, overlays, review auto/excel, ghi XML) viết ở đây.
Phần của người khác gọi qua module riêng, thiếu thì báo rõ tên module cần:
  m28core.mapping.apply_map   (P3)  — 478 điểm → {tên điểm: [x, y]} ảnh cắt 512 (chọn đỉnh MediaPipe trực tiếp theo `mp_idx` của config; config version 3 = 50 điểm DMS, QĐ-003)
  m28core.autoqc.run          (P4, tuỳ chọn) — QC 5 kiểm; thiếu thì chạy kiểm tối thiểu
  m28core.push.push           (P4)  — tạo task CVAT và nhập XML
  m28core.collect.collect     (P4)  — xuất nhãn từ task
  review_app.py               (P2)  — trang rà soát Gradio (--review ui)
Không import torch ở bất cứ đâu trong tool/.
"""
import csv
import glob
import importlib
import io
import json
import os
import re
import subprocess
import sys
from xml.sax.saxutils import quoteattr

import numpy as np

from m28core import co_v2, loai_tru, mau_nhom, phan_loai  # noqa: E402
from m28core.cat_mat import SIDE_SCALE, square_crop  # noqa: F401

OUT = 512
IMG_EXT = (".png", ".jpg", ".jpeg")
NEN_GAN_TAY = ("guong", "don_cuc", "diem_khong_hop_le")   # mã lỗi autoqc làm gợi ý "nên gán tay" (giả định, chờ P4)
DECISIONS = phan_loai.DECISIONS
DEFAULT_PIPELINE_PATH = os.path.join("config", "pipeline.json")
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"


# ---------- tiện ích ----------
def _jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _jsave(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _run_dir(args):
    return os.path.join("runs", args.run)


def _excluded(args):
    """Mặt bị xoá mềm của lượt (runs/<lượt>/excluded.txt): mọi chỗ đọc mặt của lượt phải trừ tập này."""
    return loai_tru.read_excluded(_run_dir(args)) if getattr(args, "run", None) else set()


def _keep_old(args, path, new):
    """Chạy lại một bước (--force) chỉ ghi mặt còn sống; mặt bị xoá mềm giữ nguyên mục cũ trong file kết quả
    (file kết quả không bị sửa vì xoá mềm, nên khôi phục là gỡ tên khỏi excluded.txt)."""
    gone = _excluded(args)
    if gone and os.path.exists(path):
        try:
            old = _jload(path)
        except (OSError, ValueError):
            return new
        for n in gone:
            if n in old and n not in new:
                new[n] = old[n]
    return new


def _alive(d, args):
    """Bỏ khỏi dict/danh sách các mặt đã xoá mềm (không sửa file kết quả: chỉ là bộ lọc lúc đọc)."""
    return loai_tru.keep(d, _excluded(args))


def _need(module, why):
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as e:
        if e.name != module:
            raise
        raise SystemExit(f"Thiếu {module} ({why}). Chưa có thì chờ người phụ trách commit.")


def _need_file(path, why):
    if not os.path.exists(path):
        raise SystemExit(f"Thiếu file {path} ({why}).")
    return path


def make_landmarker(model_path, num_faces=5, outputs=False):
    """outputs=True: lấy thêm ma trận biến đổi mặt và blendshapes (inc_ingest.py dùng để đo tư thế, độ há miệng).
    Mặc định False: cùng hành vi như trước."""
    alt = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), os.path.basename(model_path))
    if not os.path.exists(model_path) and os.path.exists(alt):      # gói giao khách: model nằm cạnh m28.py
        model_path = alt
    _need_file(model_path, f"tải từ {MODEL_URL}")
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    opts = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.IMAGE, num_faces=num_faces,
        output_face_blendshapes=outputs, output_facial_transformation_matrixes=outputs)
    return vision.FaceLandmarker.create_from_options(opts)


def run_mp(lm, rgb):
    """478 điểm theo pixel, hoặc None nếu không thấy mặt."""
    import mediapipe as mp
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
    res = lm.detect(img)
    if not res.face_landmarks:
        return None
    h, w = rgb.shape[:2]
    faces = [[[p.x * w, p.y * h] for p in face] for face in res.face_landmarks]
    return max(faces, key=lambda f: np.ptp(np.asarray(f), axis=0).prod())   # mặt lớn nhất


def run_mp_padded(lm, rgb, run=None):
    """Như run_mp; không thấy mặt thì thêm viền xám (cạnh dài / 4) rồi thử lại, toạ độ trả về theo ảnh gốc."""
    run = run or run_mp                 # tra tên lúc gọi để test thay được run_mp
    pts = run(lm, rgb)
    if pts is not None:
        return pts
    pad = max(rgb.shape[:2]) // 4
    padded = np.full((rgb.shape[0] + 2 * pad, rgb.shape[1] + 2 * pad, 3), 128, np.uint8)
    padded[pad:pad + rgb.shape[0], pad:pad + rgb.shape[1]] = rgb
    pts = run(lm, padded)
    return None if pts is None else (np.asarray(pts, float) - pad).tolist()


def detect_box(lm, rgb, run=None):
    """Khung bao 478 điểm. Không thấy thì thêm viền xám rồi thử lại. Trả (x0, y0, x1, y1) hoặc None."""
    run = run or run_mp                 # tra tên lúc gọi để test thay được run_mp
    pts = run(lm, rgb)
    pad = 0
    if pts is None:
        pad = max(rgb.shape[:2]) // 4
        padded = np.full((rgb.shape[0] + 2 * pad, rgb.shape[1] + 2 * pad, 3), 128, np.uint8)
        padded[pad:pad + rgb.shape[0], pad:pad + rgb.shape[1]] = rgb
        pts = run(lm, padded)
        if pts is None:
            return None
    a = np.asarray(pts, float) - pad
    return (*a.min(0), *a.max(0))


def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:      # utf-8-sig: file Excel có BOM
        return list(csv.DictReader(f))


def _ident(row):
    """Khoá một mặt trong CSV: (image, face_idx)."""
    if "image" in row and "face_idx" in row:
        return row["image"], int(row["face_idx"])
    raise SystemExit("CSV cần cột image, face_idx.")


def _crop_only_box(m):
    """Hộp mặt theo toạ độ ẢNH CẮT 512 từ manifest: ((x0-left)*k, (y0-top)*k, (x1-left)*k, (y1-top)*k)."""
    left, top, k = float(m["left"]), float(m["top"]), float(m["k"])
    return ((float(m["x0"]) - left) * k, (float(m["y0"]) - top) * k,
            (float(m["x1"]) - left) * k, (float(m["y1"]) - top) * k)


def load_items(args):
    """Danh sách mặt của lượt chạy: dict(name, path, rel, box|None). rel = đường dẫn ảnh gốc tính từ --images.

    Người trong đội chỉ có gói (ảnh cắt data/crops + manifest, không có khung gốc): khi <images>/<image> không có mà
    <images>/<file> có, dùng chính ảnh cắt (rel = file) và với --box crop đổi hộp sang toạ độ ảnh cắt."""
    manifest = {}
    if os.path.exists(args.manifest):
        for m in _read_csv(args.manifest):
            manifest[_ident(m)] = m
    if args.list:
        wanted = [_ident(r) for r in _read_csv(args.list)]
    elif args.set:
        if not manifest:
            raise SystemExit(f"--set cần {args.manifest} (không thấy file)")
        wanted = list(manifest)
    elif args.images:
        if args.box == "crop":
            raise SystemExit("--box crop cần --list (hoặc --set) để lấy hộp mặt từ manifest.csv")
        files = sorted(g for ext in ("jpg", "jpeg", "png")
                       for g in glob.glob(os.path.join(args.images, "**", f"*.{ext}"), recursive=True))
        gone = _excluded(args)
        return _unique([it for it in (dict(name=os.path.splitext(os.path.basename(p))[0], path=p, box=None,
                                           rel=os.path.relpath(p, args.images).replace(os.sep, "/")) for p in files)
                        if it["name"] not in gone])
    else:
        raise SystemExit("Cần --images (thư mục ảnh), hoặc --list kèm --images, hoặc --set.")
    if not args.images:
        raise SystemExit("Cần --images (thư mục ảnh gốc, hoặc data\\crops nếu chỉ có gói).")
    items, gone = [], _excluded(args)
    for key in wanted:
        m = manifest.get(key)
        if args.set and (m is None or m["set"] not in args.set):
            continue
        if args.box == "crop" and m is None:
            raise SystemExit(f"--box crop cần {args.manifest} có dòng {key}")
        name = m["file"][:-4] if m else os.path.splitext(os.path.basename(key[0]))[0]
        if name in gone:
            continue
        path = os.path.join(args.images, *key[0].split("/"))
        rel = key[0]
        box = tuple(float(m[c]) for c in ("x0", "y0", "x1", "y1")) if m else None
        if m and not os.path.exists(path) and os.path.exists(os.path.join(args.images, m["file"])):
            path, rel = os.path.join(args.images, m["file"]), m["file"]       # chỉ có gói: dùng ảnh cắt
            box = _crop_only_box(m) if all(c in m for c in ("left", "top", "k")) else None
        items.append(dict(name=name, path=path, box=box, rel=rel))
    return _unique(items)


def _unique(items):
    seen = {}
    for it in items:
        if it["name"] in seen:
            raise SystemExit(f"Hai mặt cùng tên {it['name']!r} ({seen[it['name']]} và {it['rel']}): ảnh cắt sẽ đè nhau. "
                             "Dùng --list có manifest.csv (tên F_001…) hoặc đổi tên ảnh.")
        seen[it["name"]] = it["rel"]
    return items


def _stem(name):
    base, ext = os.path.splitext(name.strip())
    return base if ext.lower() in IMG_EXT else name.strip()


def _base(path):
    return re.split(r"[\\/]", path)[-1]


# ---------- prepare ----------
def crop(args, out, landmarker_factory=None):
    import cv2
    items = load_items(args)
    os.makedirs(os.path.join(out, "images"), exist_ok=True)
    meta, no_face = {}, []
    lm = (landmarker_factory or make_landmarker)(args.model) if args.box == "auto" else None
    try:
        for it in items:
            bgr = cv2.imread(it["path"])
            if bgr is None:
                no_face.append((it["name"], "khong_doc_duoc_anh"))
                continue
            box = it["box"] if args.box == "crop" else detect_box(lm, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            if box is None:
                no_face.append((it["name"], "khong_thay_mat"))
                continue
            img, _, (left, top, k), _ = square_crop(bgr, box, np.zeros((1, 2), np.float32))
            cv2.imwrite(os.path.join(out, "images", it["name"] + ".png"), img)
            meta[it["name"]] = dict(src=os.path.abspath(it["path"]), rel=it["rel"], left=left, top=top, k=k,
                                    w=bgr.shape[1], h=bgr.shape[0])
    finally:
        if lm is not None and hasattr(lm, "close"):
            lm.close()
    _jsave(os.path.join(out, "meta.json"), _keep_old(args, os.path.join(out, "meta.json"), meta))
    with open(os.path.join(out, "box.txt"), "w", encoding="utf-8") as f:      # push cần biết XML theo ảnh cắt hay ảnh gốc
        f.write(args.box)
    _write_no_face(args, no_face, "crop")
    print(f"crop: {len(meta)} mặt, {len(no_face)} không dùng được")
    return True


def _write_no_face(args, rows, step):
    path = os.path.join(_run_dir(args), "no_face.csv")
    old = []
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            old = [r for r in csv.reader(f) if r and r[0] != "name" and r[2:3] != [step]]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "reason", "step"])
        w.writerows(old)
        w.writerows([n, why, step] for n, why in rows)


def mediapipe(args, out, landmarker_factory=None):
    import cv2
    rd = _run_dir(args)
    meta = _alive(_jload(os.path.join(rd, "crop", "meta.json")), args)
    pred, no_face = {}, []
    lm = (landmarker_factory or make_landmarker)(args.model)
    try:
        for name in meta:
            rgb = cv2.cvtColor(cv2.imread(os.path.join(rd, "crop", "images", name + ".png")), cv2.COLOR_BGR2RGB)
            orig = run_mp_padded(lm, rgb)
            if orig is None:
                no_face.append((name, "khong_thay_mat"))
                continue
            pred[name] = dict(orig=orig, flip=run_mp_padded(lm, rgb[:, ::-1]))   # flip: toạ độ ảnh lật, chưa bỏ lật
    finally:
        if hasattr(lm, "close"):
            lm.close()
    _jsave(os.path.join(out, "pred478.json"), _keep_old(args, os.path.join(out, "pred478.json"), pred))
    _write_no_face(args, no_face, "mediapipe")
    print(f"mediapipe: {len(pred)} mặt, {len(no_face)} không thấy mặt")
    return True


def map50(args, out):
    mapping = _need("m28core.mapping", "P3: apply_map(pts478, map, config, flipped=False)")
    cfg = _jload(_need_file(args.config, "m28_config.json của P3, đóng băng 12/10"))
    mp_map = _jload(_need_file(args.map, "map_mp50.json của P3"))
    names = [p["name"] for p in cfg["points"]]
    pred = _alive(_jload(os.path.join(_run_dir(args), "mediapipe", "pred478.json")), args)

    def conv(pts, flipped):
        r = mapping.apply_map(np.asarray(pts, float), mp_map, cfg, flipped=flipped)
        miss = [n for n in names if n not in r]
        if miss:
            raise SystemExit(f"apply_map thiếu điểm {miss[:3]}… so với config")
        return {n: [float(r[n][0]), float(r[n][1])] for n in names}

    che_khuat = _need("m28core.che_khuat", "điểm bị che")
    rd = _run_dir(args)

    def occ_of(n, pts):
        gray = None
        try:
            import cv2
            img = cv2.imread(os.path.join(rd, "crop", "images", n + ".png"), cv2.IMREAD_GRAYSCALE)
            gray = img if img is not None and img.ndim == 2 else None            # không đọc được ảnh cắt thì chỉ xét mặt nghiêng
        except Exception:
            gray = None
        return che_khuat.diem_bi_che(pts, cfg, gray)

    res = {n: dict(orig=conv(p["orig"], False), flip=conv(p["flip"], True) if p["flip"] else None, occ=occ_of(n, p["orig"]))
           for n, p in pred.items()}
    _jsave(os.path.join(out, "mp50.json"), _keep_old(args, os.path.join(out, "mp50.json"), res))
    print(f"map50: {len(res)} mặt")
    return True


def _need_current_names(mp50, names, args):
    """mp50.json của lượt phải có đúng tên điểm của config. Lượt chạy bằng config CŨ (version 2, tên pNN_vùng_bên, trước QĐ-003) không đọc được bằng config version 3:
    báo rõ cách xử lý thay vì KeyError khó hiểu."""
    for n, p in mp50.items():
        orig = p.get("orig") or {}
        miss = [x for x in names if x not in orig]
        if miss:
            old = [k for k in orig if re.match(r"p\d\d_", k)]
            raise SystemExit(f"{_run_dir(args)}{os.sep}map50{os.sep}mp50.json (mặt {n}) thiếu điểm {miss[0]} của config hiện tại"
                             + (f": lượt này chạy bằng định nghĩa 50 điểm CŨ (version 2, tên {old[0]}, trước QĐ-003)." if old else ".")
                             + f" Chạy lại bước map50 và các bước sau bằng config hiện tại: python tool\\m28.py prepare --run {args.run} --force map50 flags autoqc overlays")
    return mp50


DERIVED = ("map50", "flags", "autoqc", "overlays")          # các bước phụ thuộc tên điểm của config (crop, mediapipe thì không)


def stale_derived_steps(args):
    """Lượt đã chạy map50 bằng config KHÁC (ví dụ định nghĩa 50 điểm cũ version 2, tên pNN_vùng_bên, trước QĐ-003) thì trả DERIVED để m28.py tự tính lại các bước đó
    từ pred478.json (không phụ thuộc tên điểm, nên không chạy lại MediaPipe); lượt hợp lệ, chưa chạy hoặc không đọc được config thì trả []."""
    try:
        names = [p["name"] for p in _jload(args.config)["points"]]
        mp50 = _jload(os.path.join(_run_dir(args), "map50", "mp50.json"))
    except (OSError, ValueError, KeyError, TypeError):
        return []
    first = next(iter(mp50.values()), None)
    if not isinstance(first, dict) or not isinstance(first.get("orig"), dict):
        return []
    return list(DERIVED) if any(n not in first["orig"] for n in names) else []


def flags(args, out):
    """low_conf của từng điểm (m28core.co_v2, QĐ-025): config có `low_conf_v2` thì cờ phiên bản 2 (xác suất từ lệch ảnh lật của điểm, mức lệch
    của cả mặt và nhóm điểm > ngưỡng); không có thì phiên bản 1: lệch ảnh gốc / ảnh lật ÷ khoảng cách hai mắt > t_flip (t_flip null: mọi cờ false).
    Mặt không có ảnh lật: mọi điểm có cờ."""
    cfg = _jload(args.config)
    names = [p["name"] for p in cfg["points"]]
    v2 = co_v2.model_of(cfg) is not None
    t = cfg.get("t_flip")
    mp50 = _need_current_names(_alive(_jload(os.path.join(_run_dir(args), "map50", "mp50.json")), args), names, args)
    res = {name: co_v2.flags(p, cfg) for name, p in mp50.items()}
    _jsave(os.path.join(out, "flags.json"), _keep_old(args, os.path.join(out, "flags.json"), res))
    n = np.mean([sum(v) for v in res.values()]) if res else 0
    print(f"flags: trung bình {n:.1f} cờ/mặt" + (" (cờ phiên bản 2)" if v2 else " (t_flip = null nên mọi cờ = false)" if t is None else ""))
    return True


def autoqc(args, out):
    """Ghi autoqc.csv: name, suggestion (on / can_xem / nen_gan_tay), n_flags, decision, reason, seconds, problems.
    Ba cột decision, reason, seconds để trống: mẫu cho người rà điền bằng Excel (--review excel)."""
    qc = None
    try:
        qc = importlib.import_module("m28core.autoqc")
    except ModuleNotFoundError as e:
        if e.name != "m28core.autoqc":
            raise
    cfg = _jload(args.config)
    names = [p["name"] for p in cfg["points"]]
    rd = _run_dir(args)
    mp50 = _need_current_names(_alive(_jload(os.path.join(rd, "map50", "mp50.json")), args), names, args)
    fl = _alive(_jload(os.path.join(rd, "flags", "flags.json")), args)
    rows = []
    for name, p in mp50.items():
        a = np.array([p["orig"][n] for n in names], float)
        why = []
        if not np.isfinite(a).all():
            why.append("diem_khong_hop_le")
        elif ((a < -0.1 * OUT) | (a > 1.1 * OUT)).any():
            why.append("diem_ngoai_anh")
        if qc is not None:
            why += list(qc.run(name, a, cfg))
        nf = sum(fl[name])
        v2 = co_v2.face_suggestion(nf, cfg)                                      # cờ phiên bản 2: Ổn / Cần xem / nên sửa nhãn theo số cờ cả mặt
        if any(w.startswith(NEN_GAN_TAY) for w in why):
            sug = "nen_gan_tay"
        elif v2 is not None:
            sug = "can_xem" if why and v2 == "on" else v2
        else:
            sug = "can_xem" if why or nf else "on"
        rows.append([name + ".png", sug, nf, "", "", "", ";".join(why)])
    old_csv, gone = os.path.join(out, "autoqc.csv"), _excluded(args)
    if gone and os.path.exists(old_csv):                       # giữ dòng cũ của mặt đã xoá mềm (khôi phục thì còn gợi ý)
        have = {r[0] for r in rows}
        rows += [[r["name"], r["suggestion"], r["n_flags"], r["decision"], r["reason"], r["seconds"], r["problems"]]
                 for r in _read_csv(old_csv) if _stem(r["name"]) in gone and r["name"] not in have]
    with open(old_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "suggestion", "n_flags", "decision", "reason", "seconds", "problems"])
        w.writerows(rows)
    print(f"autoqc: {sum(1 for r in rows if r[1] != 'on')}/{len(rows)} mặt cần xem hoặc nên gán tay"
          + ("" if qc else " (chưa có m28core.autoqc của P4, chỉ kiểm tối thiểu)"))
    return True


def _draw_dot(cv2, img, x, y, rgb, low_conf, occluded=False):
    """Chấm màu nhóm (mau_nhom: cùng kiểu với trang rà soát). Ổn: chấm bán kính R_OK, viền tối mảnh. low_conf: cùng cỡ, viền trắng thay viền tối.
    occluded (điểm bị che, xem che_khuat.py): VÒNG RỖNG màu nhóm (không tô đặc) viền tối hai phía; nếu còn low_conf thì thêm một vòng trắng mảnh bên ngoài."""
    c = (int(round(x)), int(round(y)))
    bgr = (rgb[2], rgb[1], rgb[0])
    if occluded:
        r = mau_nhom.R_OCC
        if low_conf:
            cv2.circle(img, c, r + 4, mau_nhom.WHITE[::-1], 1, cv2.LINE_AA)
        cv2.circle(img, c, r + 1, mau_nhom.DARK[::-1], 3, cv2.LINE_AA)
        cv2.circle(img, c, r, bgr, 1, cv2.LINE_AA)
        return bgr
    if low_conf:
        r = mau_nhom.R_LOW
        cv2.circle(img, c, r + mau_nhom.RING_LOW, mau_nhom.WHITE[::-1], -1, cv2.LINE_AA)
    else:
        r = mau_nhom.R_OK
        cv2.circle(img, c, r + 1, mau_nhom.DARK[::-1], -1, cv2.LINE_AA)
    cv2.circle(img, c, r, bgr, -1, cv2.LINE_AA)
    return bgr


def overlays(args, out):
    """Ảnh chồng: chấm màu NHÓM của điểm (đúng màu label trên CVAT, QĐ-004) kèm số thứ tự; điểm low_conf cùng cỡ, viền trắng; điểm occluded vẽ vòng rỗng (xem mau_nhom.py)."""
    import cv2
    cfg = _jload(args.config)
    names = [p["name"] for p in cfg["points"]]
    rd = _run_dir(args)
    mp50 = _need_current_names(_alive(_jload(os.path.join(rd, "map50", "mp50.json")), args), names, args)
    fl = _alive(_jload(os.path.join(rd, "flags", "flags.json")), args)
    for name, p in mp50.items():
        img = cv2.imread(os.path.join(rd, "crop", "images", name + ".png"))
        occ = set(p.get("occ") or ())                          # điểm bị che do mặt nghiêng hoặc vật thể che mắt (m28core.che_khuat): vẽ vòng rỗng
        for i, n in enumerate(names):
            x, y = p["orig"][n]
            low = bool(fl[name][i])
            col = _draw_dot(cv2, img, x, y, mau_nhom.dot_rgb(mau_nhom.group_of(n), low), low, n in occ)
            pos = (int(x) + 4, int(y) - 3)
            cv2.putText(img, str(i + 1), pos, cv2.FONT_HERSHEY_SIMPLEX, 0.35, mau_nhom.DARK[::-1], 2, cv2.LINE_AA)    # viền tối cho số đọc được trên mọi nền
            cv2.putText(img, str(i + 1), pos, cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1, cv2.LINE_AA)
        cv2.imwrite(os.path.join(out, name + ".png"), img)
    print(f"overlays: {len(mp50)} ảnh chồng")
    return True


# ---------- review ----------
def _autoqc_rows(rd):
    """{tên không đuôi: gợi ý}; chưa có autoqc.csv thì rỗng (mọi mặt coi là Nhận)."""
    path = os.path.join(rd, "autoqc", "autoqc.csv")
    return {_stem(r["name"]): r["suggestion"] for r in _read_csv(path)} if os.path.exists(path) else {}


def _queue(args):
    rd = _run_dir(args)
    fl = _alive(_jload(os.path.join(rd, "flags", "flags.json")), args)
    sug = _autoqc_rows(rd)
    rank = {"nen_gan_tay": 0, "can_xem": 1}
    names = sorted(fl, key=lambda n: (rank.get(sug.get(n), 2), -sum(fl[n]), n))   # đáng ngờ lên đầu
    return names, fl, sug


def _no_face(args):
    """{tên: lý do} từ no_face.csv (một tên chỉ một dòng, dù nằm ở bước nào)."""
    return _alive(phan_loai.read_no_face(_run_dir(args)), args)


def triage_path(args, rd):
    """File triage: --review-file (tìm như gõ, rồi trong runs/<run>/review/), không có thì triage_<reviewer|auto>.csv."""
    rev = os.path.join(rd, "review")
    if args.review_file:
        for p in (args.review_file, os.path.join(rev, args.review_file)):
            if os.path.exists(p):
                return p
        return args.review_file if os.path.dirname(args.review_file) else os.path.join(rev, args.review_file)
    return os.path.join(rev, f"triage_{'auto' if args.review == 'auto' else args.reviewer}.csv")


def read_triage(path):
    """{tên không đuôi: (quyết định, lý do)}: dùng chung với trang rà soát và hộp xác nhận đẩy (m28core.phan_loai.read_triage)."""
    return phan_loai.read_triage(path)


def review(args, out):
    rd = _run_dir(args)
    names, fl, sug = _queue(args)
    path = triage_path(args, rd)
    if args.review == "auto":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["name", "decision", "reason", "seconds"])
            for n in names:
                w.writerow([n + ".png", "gan_tay" if sug.get(n) == "nen_gan_tay" else "nhan", "", ""])
            for n, why in _no_face(args).items():
                if n not in fl:
                    w.writerow([n + ".png", "bo", why, ""])
        print(f"review auto: theo gợi ý autoqc (chỉ để chạy thử/demo, không có người rà), ghi {path}")
        return True
    if args.review == "excel":
        if not os.path.exists(path):
            print(f"Chưa có {path}. Mở {os.path.join(rd, 'autoqc', 'autoqc.csv')} bằng Excel, điền cột decision "
                  f"(nhan / gan_tay / bo) và reason, xem ảnh chồng trong {os.path.join(rd, 'overlays')}, "
                  f"lưu dạng CSV UTF-8 thành {path}, rồi chạy lại đúng lệnh.")
            return False
        done = read_triage(path)
        missing = [n for n in names if done.get(n, ("",))[0] not in DECISIONS]
        if missing:
            print(f"Còn {len(missing)} mặt chưa có quyết định (nhan / gan_tay / bo), ví dụ: {missing[:3]}")
            return False
        return True
    app = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "review_app.py")
    _need_file(app, "trang rà soát của P2")
    if os.path.exists(os.path.join(out, "done.txt")):           # --force review: xoá done.txt cũ, chỉ tin nút Xong lần này
        os.remove(os.path.join(out, "done.txt"))
    try:
        subprocess.call([sys.executable, app, rd, args.reviewer])
    except KeyboardInterrupt:                                    # Ctrl+C: trang con tự thoát sạch, không mất dòng CSV nào
        if os.path.exists(os.path.join(out, "done.txt")):        # đã bấm Xong rồi mới Ctrl+C: m28.py bỏ qua bước có done.txt khi chạy lại
            print("Đã bấm Xong nhưng m28 dừng vì Ctrl+C (trang chưa được đóng bằng nút 'Close page'): "
                  "gõ lại đúng lệnh (không thêm --force review) để đi tiếp, bước review đã có done.txt nên được bỏ qua.")
        else:
            print("Đã đóng trang rà soát chưa bấm Xong: gõ lại đúng lệnh để làm tiếp.")
        return False
    if not os.path.exists(os.path.join(out, "done.txt")):
        print("Trang rà soát đã đóng mà chưa bấm Xong.")
        return False
    return True


# ---------- push / collect ----------
def image_xml(frame_id, name, point_names, pts, low, width, height, occ=()):
    """<image> của một mặt: MỘT <skeleton> cho mỗi nhóm (label = tên nhóm, QĐ-004) theo thứ tự nhóm xuất hiện, mỗi skeleton chỉ có điểm của nhóm.
    Nhóm của điểm suy từ tên `<nhóm>_<k>` (cvat_io.group_of_name). occ: tên các điểm bị che do mặt nghiêng (m28core.che_khuat) thì ghi occluded="1" (vẫn có toạ độ ước lượng)."""
    from m28core import cvat_io
    out = [f'<image id="{frame_id}" name={quoteattr(name)} width="{width}" height="{height}">']
    occ = set(occ or ())
    rows = list(zip(point_names, pts, low))
    for group in dict.fromkeys(cvat_io.group_of_name(n) for n in point_names):
        out.append(f'  <skeleton label="{group}">')
        for n, (x, y), f in rows:
            if cvat_io.group_of_name(n) == group:
                out.append(f'    <points label="{n}" occluded="{1 if n in occ else 0}" outside="0" points="{x:.2f},{y:.2f}">'
                           f'<attribute name="low_conf">{"true" if f else "false"}</attribute></points>')
        out.append('  </skeleton>')
    out.append('</image>')
    return "\n".join(out)


def read_box_mode(box_file, default="auto"):
    """Chế độ hộp đã ghi ở bước prepare (crop/box.txt): "auto" hoặc "crop". File thiếu thì lấy default; giá trị khác "auto"
    (kể cả file do bản công cụ cũ ghi) được hiểu là "crop" (ảnh cắt 512), nên lượt cũ vẫn đọc được."""
    if not os.path.exists(box_file):
        return default
    with open(box_file, encoding="utf-8") as f:
        return "auto" if f.read().strip() == "auto" else "crop"


def _file_name(name, m, mode):
    """Tên file ảnh tải lên CVAT = tên ảnh trong XML."""
    return name + ".png" if mode == "crop" else _base(m.get("rel") or m["src"])


def _upload_path(args, rd, name, m, mode):
    if mode == "crop":
        return os.path.abspath(os.path.join(rd, "crop", "images", name + ".png"))
    if args.images and m.get("rel"):
        p = os.path.join(args.images, *m["rel"].split("/"))
        if os.path.exists(p):
            return p
    return m["src"]


def _face_pts(mode, n, meta, mp50, names):
    """(danh sách 50 điểm, rộng, cao) của mặt n theo hệ toạ độ ảnh tải lên CVAT. crop: toạ độ ảnh cắt 512; auto: x/k + left, kẹp mép."""
    m = meta[n]
    if mode == "crop":
        return [mp50[n]["orig"][p] for p in names], OUT, OUT
    w, h = m["w"], m["h"]
    return [(min(max(mp50[n]["orig"][p][0] / m["k"] + m["left"], 0), w - 1),
             min(max(mp50[n]["orig"][p][1] / m["k"] + m["top"], 0), h - 1)) for p in names], w, h


def ca_kho_points(rd):
    """{tên mặt: set(tên điểm)} = 'Điểm liên quan' đã đánh dấu Ca khó ở runs/<lượt>/ca_kho.csv (mọi người rà). Đọc như ca_kho.read_marks: file lưu lại từ
    Excel tiếng Việt dùng dấu ';' giữa các cột, tên cột không phân biệt hoa thường. Thiếu file hoặc hỏng thì {}."""
    out = {}
    try:
        with open(os.path.join(rd, "ca_kho.csv"), encoding="utf-8-sig", newline="") as f:
            text = f.read()
        first = text.splitlines()[0] if text.strip() else ""
        delim = ";" if first.count(";") > first.count(",") else ","
        for r in csv.DictReader(io.StringIO(text), delimiter=delim):
            r = {(k or "").strip().lower(): (v or "") for k, v in r.items() if k is not None}
            anh = r.get("anh", "").strip()
            if anh.endswith(".png"):
                out.setdefault(anh[:-4], set()).update(x.strip() for x in r.get("diem", "").split(";") if x.strip())
    except (OSError, csv.Error, UnicodeDecodeError):
        return {}
    return out


def tay_low_conf(tay_nhap, fl, names, ck_pts=None):
    """Cờ low_conf của mặt Sửa nhãn có nháp lên CVAT: điểm có cờ ở flags.json (cờ phiên bản 2) HOẶC điểm liên quan của ca khó; mặt không có
    điểm nào như vậy (chưa có cờ) thì mọi điểm true như trước ("kiểm hết"). Trả ({mặt: [bool]*50}, số mặt phải đánh cả 50 điểm)."""
    ck_pts = ck_pts or {}
    out, all_true = {}, 0
    for n in tay_nhap:
        f = list(fl.get(n) or [])
        extra = ck_pts.get(n, set())
        low = [bool(f[i]) if i < len(f) else False for i in range(len(names))]
        low = [v or (p in extra) for v, p in zip(low, names)]
        if not any(low):
            low, all_true = [True] * len(names), all_true + 1
        out[n] = low
    return out, all_true


def build_xml(mode, nhan, meta, mp50, fl, cfg, path, tay_nhap=(), tay_low=None):
    """mode crop: toạ độ ảnh cắt 512, tên name.png. mode auto: toạ độ ảnh gốc (x_cắt / k + left, kẹp vào mép).
    Mặt Nhận: id 0..len(nhan)-1, cờ low_conf thật (fl). Mặt Sửa nhãn có nháp (tay_nhap): nối sau, id len(nhan)+i, cờ theo tay_low (tay_low_conf:
    điểm có cờ + điểm liên quan của ca khó); không có tay_low thì mọi điểm true."""
    names = [p["name"] for p in cfg["points"]]
    parts = ['<?xml version="1.0" encoding="utf-8"?>', '<annotations>', '  <version>1.1</version>']
    tay_low = tay_low or {}
    faces = [(n, fl[n]) for n in nhan] + [(n, tay_low.get(n) or [True] * len(names)) for n in tay_nhap]
    for fid, (n, low) in enumerate(faces):
        pts, w, h = _face_pts(mode, n, meta, mp50, names)
        parts.append(image_xml(fid, _file_name(n, meta[n], mode), names, pts, low, w, h, mp50[n].get("occ", ())))
    parts.append('</annotations>')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def push_plan(triage, meta, mp50, no_face, excluded=frozenset(), point_names=None):
    """Phân loại mặt để đẩy: dùng chung với trang rà soát (xem m28core.phan_loai.classify)."""
    return phan_loai.classify(triage, meta, mp50, no_face, excluded, point_names)


KIND_CO_NHAP, KIND_ANH_TRONG = "co_nhap", "anh_trong"
_LOG_DETAIL = {}                                                  # m28.py ghi thêm vào log.txt (cột cuối) cho bước đã đăng ký ở đây


def read_manual_list(path):
    """[(tên file ảnh, loại)] từ manual_list.txt. Mỗi dòng `<tên>\t<co_nhap|anh_trong>`; dòng không có tab (định dạng cũ) là anh_trong,
    vì bản cũ luôn đẩy Sửa nhãn thành ảnh trống."""
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f.read().splitlines():
            if not ln.strip():
                continue
            name, _sep, kind = ln.partition("\t")
            kind = kind.strip()
            out.append((name.strip(), kind if kind in (KIND_CO_NHAP, KIND_ANH_TRONG) else KIND_ANH_TRONG))
    return out


def push(args, out):
    rd = _run_dir(args)
    cfg = _jload(args.config)
    pipe = _jload(args.pipeline) if os.path.exists(args.pipeline) else {}
    triage = read_triage(_need_file(triage_path(args, rd), "kết quả bước review"))
    meta_all = _jload(os.path.join(rd, "crop", "meta.json"))
    excluded = _excluded(args)
    meta = _alive(meta_all, args)
    mp50 = _alive(_jload(os.path.join(rd, "map50", "mp50.json")), args)
    fl = _alive(_jload(os.path.join(rd, "flags", "flags.json")), args)
    box_file = os.path.join(rd, "crop", "box.txt")
    mode = read_box_mode(box_file, args.box)
    if len(args.task) > 1:
        raise SystemExit("push chỉ nhận một --task")
    no_face = _no_face(args)
    point_names = [p["name"] for p in cfg["points"]]
    _need_current_names(mp50, point_names, args)
    plan = push_plan(triage, meta_all, mp50, phan_loai.read_no_face(rd), excluded, point_names)   # classify tự trừ mặt xoá mềm
    nhan, tay, tay_nhap, tay_trong = plan["nhan"], plan["tay"], plan["tay_nhap"], plan["tay_trong"]
    for n in plan["nhan_khong_nhap"]:
        print(f"Cảnh báo: {n} được chọn Nhận nhưng MediaPipe không thấy mặt, đưa vào Sửa nhãn.")
    lost = plan["lost"]
    if lost:
        print(f"Cảnh báo: {len(lost)} mặt chọn Sửa nhãn nhưng không có ảnh cắt (không đọc được/không thấy mặt ở bước crop), "
              f"không tải lên được: {lost[:3]}")
    rejected, removed = plan["rejected"], plan["removed"]
    if not nhan and not tay:
        raise SystemExit("Không có mặt nào để đẩy lên (cả nhóm nhận và gán tay đều trống).")
    files = {}
    for n in nhan + tay:
        files.setdefault(_file_name(n, meta[n], mode), []).append(n)
    dup = {f: v for f, v in files.items() if len(v) > 1}
    if dup:
        raise SystemExit(f"Tên ảnh trùng, CVAT không nhận hai ảnh cùng tên: {dup}. Mỗi ảnh gốc chỉ được một mặt "
                         "lên task (chuyển mặt kia sang Bỏ trong triage) hoặc dùng --box crop (ảnh cắt, tên khác nhau).")
    co_nhap = set(tay_nhap)
    with open(os.path.join(out, "manual_list.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(f"{_file_name(n, meta[n], mode)}\t{KIND_CO_NHAP if n in co_nhap else KIND_ANH_TRONG}" for n in tay))
    with open(os.path.join(out, "rejected.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "reason"])
        w.writerows(rejected + removed)                            # mặt xoá mềm ghi lý do da_xoa (không tải lên)
    xml_path = os.path.join(rd, "xml", "prelabel.xml")
    ck_pts = ca_kho_points(rd)
    tay_low, n_all = tay_low_conf(tay_nhap, fl, point_names, ck_pts)
    build_xml(mode, nhan, meta, mp50, fl, cfg, xml_path, tay_nhap, tay_low)
    print(f"push: {len(nhan)} mặt nhận, {len(tay)} mặt gán tay, {len(rejected)} bỏ"
          + (f", {len(removed)} đã xoá mềm" if removed else "") + f", XML ({mode}): {xml_path}")
    n_on = sum(sum(v) for v in tay_low.values())
    print(f"  gán tay: {len(tay_nhap)} có nháp (low_conf=true ở {n_on} điểm: điểm có cờ và điểm liên quan của ca khó"
          + (f"; {n_all} mặt chưa có cờ nên đánh cả {len(point_names)} điểm" if n_all else "") + f"), {len(tay_trong)} ảnh trống")
    _LOG_DETAIL["push"] = f"gan_tay co_nhap={len(tay_nhap)} anh_trong={len(tay_trong)}"
    if args.dry_run:
        print("Chạy thử (--dry-run): đã ghi XML, không đẩy lên CVAT.")
        return False
    nhan_imgs = [_upload_path(args, rd, n, meta[n], mode) for n in nhan]
    tay_imgs = [_upload_path(args, rd, n, meta[n], mode) for n in tay]
    gone = [p for p in nhan_imgs + tay_imgs if not os.path.exists(p)]
    if gone:
        raise SystemExit(f"Không thấy {len(gone)} ảnh để tải lên, ví dụ {gone[0]}. Thêm --images <thư mục ảnh gốc> đúng máy này.")
    mod = _need("m28core.push", "P4: push(run_dir, task_name, nhan_imgs, tay_imgs, xml_path, project, prefix, label_json)")
    from m28core import cvat_io
    task_name = args.task[0] if args.task else cvat_io.task_name_for(getattr(args, "reviewer", None), args.run, pipe.get("prefix", ""))   # <người>-<đợt>
    extra = {}                                                     # chỉ truyền khi khác mặc định (push giả trong test không nhận thêm)
    if getattr(args, "resume", False):
        extra["resume"] = True
    if args.pipeline != DEFAULT_PIPELINE_PATH:
        extra["pipeline"] = args.pipeline
    mod.push(rd, task_name, nhan_imgs, tay_imgs, xml_path, project=pipe.get("project", "m28"),
             prefix=pipe.get("prefix", ""), label_json=os.path.join("config", "face50_label.json"), **extra)
    return True


def cleanup(args):
    """push --cleanup: xoá đúng task trong push.json trên CVAT (cần --confirm-name <tên task>) rồi đánh dấu task_deleted.
    Không ghi done.txt; trả True khi không có lỗi."""
    pipe = _jload(args.pipeline) if os.path.exists(args.pipeline) else {}
    mod = _need("m28core.push", "P4: cleanup(run_dir, prefix, confirm_name=...)")
    extra = {} if args.pipeline == DEFAULT_PIPELINE_PATH else {"pipeline": args.pipeline}
    mod.cleanup(_run_dir(args), prefix=pipe.get("prefix", ""), project=pipe.get("project", "m28"),
                confirm_name=getattr(args, "confirm_name", None), **extra)
    return True


def collect(args, out):
    mod = _need("m28core.collect", "P4: collect(args)")
    return mod.collect(args)
