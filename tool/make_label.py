"""Sinh config/face50_label.json: BẢY label skeleton (mỗi nhóm của 50 điểm DMS một label) để tạo project m28 trên CVAT.

    python tool\\make_label.py [--config config\\m28_config.json] [--out config\\face50_label.json]

Nguồn duy nhất là config/m28_config.json (points[].name/group/side/line/tmpl, lines{tên: {closed}}). Chạy hai lần ra cùng byte. Tên file giữ `face50_label.json` (50 điểm của mặt).

Phương án CVAT (QĐ-004, thay "một skeleton face50" của QĐ-003): mỗi nhóm là MỘT label skeleton tên đúng tên nhóm (`longmaytrai`, `longmayphai`, `songmui`, `mattrai`, `matphai`,
`moingoai`, `moitrong`), nên mục "Draw new skeleton" của CVAT liệt kê bảy label riêng, mỗi label một màu (GROUP_COLOR, đúng bảng màu hình minh hoạ DMS của chủ repo).
Tên sublabel trên CVAT là SỐ 1..50 (kiểu "so": CVAT hiện điểm đúng số như trên ảnh chồng của tool); tên điểm trong config vẫn là
`<nhóm>_<k>` và là tên duy nhất cho nhãn, ánh xạ, đánh giá: push đổi nhãn sang số khi nhập vào CVAT, và cvat_io.parse_annotations đổi số về tên config khi đọc XML từ CVAT
(project dựng trước ngày này giữ tên cũ kiểu "cu" vẫn dùng được: push nhận ra kiểu của project). `--ten cu` sinh lại file với tên cũ. Mỗi mặt có bảy skeleton, mỗi nhóm đúng một; mỗi skeleton chỉ có điểm của nhóm
mình, khuôn svg tính riêng cho nhóm (tmpl của nhóm co giãn vào khung 0-100), cạnh nối theo `line` = tên nhóm (mắt và môi nối kín). `low_conf` vẫn là thuộc tính của từng điểm.
Cái giá: người gán vẽ bảy skeleton mỗi mặt thay vì một (thời gian gán tay thay đổi, P5 cần biết); push, collect, cvat_io, eval50, cvat_smoke đã đổi theo. Màu chỉ có hiệu lực khi label
được TẠO (CVAT lưu màu trong label), nên project dựng từ label cũ (một skeleton face50, bản v2 hoặc bản đầu của v3) phải dựng lại.
Config thiếu `side_convention: "image"` (config version 2, side theo người trong ảnh) bị từ chối: label sinh từ nó sẽ gán nhóm/bên ngược.
Định dạng bám mã nguồn CVAT v2.77.0 (đã đọc, xem README mục Rủi ro), CHƯA thử trên server CVAT thật:
  * Label: type "skeleton", svg, sublabels (type "points"); không có khoá "id" ở đâu cả (server tự cấp).
  * svg: khung vẽ viewBox 0 0 100 100 (cvat-ui skeleton-configurator). Mỗi điểm một <circle> có data-type="element node",
    data-element-id, data-node-id (cùng số 1..50 theo thứ tự config) và data-label-name="<tên điểm>". KHÔNG có data-label-id:
    khi tạo project, server tự đổi data-label-name="<tên>" thành data-label-id="<id mới>" (serializers.py, create_labels),
    nên project tạo trên máy khác vẫn nối đúng nút với điểm. Cạnh: <line> data-type="edge" data-node-from/data-node-to.
  * Chỉ dùng các thuộc tính mà cvat-core cho phép khi đọc svg (cx, cy, r, x1, y1, x2, y2, data-*), vì phần còn lại bị lọc.
  * Toạ độ khuôn = hình trung bình `tmpl` của NHÓM (ảnh cắt 512x512) co giãn đều vào khung 0-100, chừa lề; mỗi label có data-node-id, data-element-id đếm từ 1 trong nhóm.
  * Mỗi điểm có một thuộc tính checkbox low_conf (mutable, mặc định false) để đánh dấu điểm đáng ngờ.
"""
import argparse
import json
import os
import sys

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
# Màu từng nhóm, lấy từ hình minh hoạ DMS của chủ repo (bảng màu Flat UI): mắt phải-ảnh tím, lông mày trái-ảnh đỏ, sống mũi xanh lá, lông mày phải-ảnh xanh dương,
# môi trong vàng, mắt trái-ảnh cam, môi ngoài xanh ngọc. Mỗi nhóm đúng một màu, bảy màu khác nhau. Bảng nằm ở m28core/mau_nhom.py để ảnh chồng (overlays) và trang rà soát
# dùng đúng màu này: màu trên trang giống màu trong CVAT.
from m28core.mau_nhom import GROUP_COLOR  # noqa: E402

N_POINTS = 50
SIDES = ("R", "L", "M")                                           # R = nửa PHẢI ảnh (*phai), L = nửa TRÁI ảnh (*trai), M = trên trục (quy ước theo ảnh, QĐ-003)
CANVAS = 100.0                                                    # viewBox 0 0 100 100 của cvat-ui
MARGIN = 6.0
NODE_R = 0.75                                                     # bán kính nút như cvat-ui vẽ (r: 0.75)
LOW_CONF = "low_conf"


def check_config(cfg):
    """Sai thì SystemExit tiếng Việt."""
    pts = cfg.get("points") if isinstance(cfg, dict) else None
    if not isinstance(pts, list) or len(pts) != N_POINTS:
        raise SystemExit(f"Config phải có đúng {N_POINTS} điểm trong 'points' (đang có "
                         f"{len(pts) if isinstance(pts, list) else 'không có'}).")
    if cfg.get("side_convention") != "image":
        raise SystemExit('Config không có side_convention = "image": đây là config cũ (version 2, side theo người trong ảnh, 50 điểm pNN_vùng_bên) trước QĐ-003; '
                         "chạy lại python tool\\make_config.py để sinh config version 3 (50 điểm DMS) rồi mới sinh label.")
    seen = set()
    lines = cfg.get("lines") or {}
    for i, p in enumerate(pts, 1):
        name = p.get("name") if isinstance(p, dict) else None
        if not isinstance(name, str) or not name.strip() or len(name) > 64 or '"' in name or "<" in name or "&" in name:
            raise SystemExit(f"Điểm số {i}: tên {name!r} không hợp lệ (cần chữ không rỗng, tối đa 64 ký tự, không có \" < &).")
        if name in seen:
            raise SystemExit(f"Tên điểm trùng trong config: {name}. CVAT nối nút với điểm theo tên nên mỗi tên chỉ một lần.")
        seen.add(name)
        if p.get("side") not in SIDES:
            raise SystemExit(f"Điểm {name}: side {p.get('side')!r} không hợp lệ (chỉ R, L hoặc M).")
        if p.get("group") not in GROUP_COLOR:
            raise SystemExit(f"Điểm {name}: group {p.get('group')!r} không hợp lệ (chỉ {', '.join(GROUP_COLOR)}); không có màu để tô sublabel.")
        t = p.get("tmpl")
        if not (isinstance(t, (list, tuple)) and len(t) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in t)):
            raise SystemExit(f"Điểm {name}: thiếu 'tmpl' [x, y] (hình trung bình 512x512), không dựng được khuôn skeleton.")
        ln = p.get("line")
        if ln and ln not in lines:
            raise SystemExit(f"Điểm {name}: line {ln!r} không có trong 'lines' của config.")


def _canvas_coords(points):
    """Co giãn đều hình trung bình vào khung 0-100 (chừa lề), giữ tỉ lệ, đặt giữa khung."""
    xs = [p["tmpl"][0] for p in points]
    ys = [p["tmpl"][1] for p in points]
    x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    k = (CANVAS - 2 * MARGIN) / max(w, h, 1e-9)
    ox, oy = (CANVAS - k * w) / 2, (CANVAS - k * h) / 2
    return [(ox + k * (p["tmpl"][0] - x0), oy + k * (p["tmpl"][1] - y0)) for p in points]


def groups_of(points):
    """{nhóm: [điểm của nhóm theo thứ tự config]}, nhóm theo thứ tự xuất hiện trong config."""
    out = {}
    for p in points:
        out.setdefault(p["group"], []).append(p)
    return out


def edge_names(points, lines):
    """Tập cạnh theo TÊN điểm (frozenset hai tên) của cả 50 điểm: mỗi nhóm nối theo `line` của nó (xem edges_of)."""
    out = set()
    for pts in groups_of(points).values():
        names = [p["name"] for p in pts]
        out |= {frozenset((names[a - 1], names[b - 1])) for a, b in edges_of(pts, lines)}
    return out


def edges_of(points, lines):
    """Danh sách cạnh (số nút từ, số nút đến), nút đánh số 1..n theo thứ tự trong `points` (một nhóm: 1..n của label đó). Chỉ nối hai điểm liền nhau trong
    cùng `line`; line closed thì nối thêm điểm cuối về điểm đầu; điểm không có line thì không có cạnh."""
    groups = {}
    for i, p in enumerate(points, 1):
        if p.get("line"):
            groups.setdefault(p["line"], []).append(i)
    out = []
    for name, ids in groups.items():
        out += list(zip(ids, ids[1:]))
        if len(ids) > 2 and (lines.get(name) or {}).get("closed"):
            out.append((ids[-1], ids[0]))
    return out


def _fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def build_svg(points, lines, ten=None):
    """`ten`: {tên điểm trong config: tên sublabel} (kiểu số); không có thì tên config."""
    ten = ten or {}
    xy = _canvas_coords(points)
    parts = []
    for a, b in edges_of(points, lines):
        (x1, y1), (x2, y2) = xy[a - 1], xy[b - 1]
        parts.append(f'<line x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}" data-type="edge" '
                     f'data-node-from="{a}" data-node-to="{b}"></line>')
    for i, (p, (x, y)) in enumerate(zip(points, xy), 1):
        parts.append(f'<circle r="{NODE_R}" cx="{_fmt(x)}" cy="{_fmt(y)}" data-type="element node" data-element-id="{i}" '
                     f'data-node-id="{i}" data-label-name="{ten.get(p["name"], p["name"])}"></circle>')
    return "\n".join(parts)


def check_ten_so(points):
    """Kiểu số cần suy lại tên config từ nhãn CVAT: tên điểm phải là `<nhóm>_<k>` với k = 1..n liên tiếp trong từng nhóm, các nhóm liền nhau theo thứ tự config."""
    seen, dem = [], {}
    for p in points:
        g = p["group"]
        if not seen or seen[-1] != g:
            if g in seen:
                raise SystemExit(f"Nhóm {g} không liền nhau trong config: kiểu tên điểm SỐ trên CVAT cần các nhóm liền nhau theo thứ tự config.")
            seen.append(g)
        dem[g] = dem.get(g, 0) + 1
        if p["name"] != f"{g}_{dem[g]}":
            raise SystemExit(f"Điểm {p['name']!r} phải tên {g}_{dem[g]} (k = 1..n theo thứ tự trong nhóm) để đổi qua lại với nhãn số của CVAT.")


def build_labels(cfg, kieu="so"):
    """Danh sách label dùng làm `labels` khi tạo project: MỘT label skeleton cho mỗi nhóm (tên label = tên nhóm, thứ tự nhóm của config), màu của nhóm.
    kieu "so" (mặc định): sublabel tên SỐ 1..50 theo thứ tự config, đúng số trên ảnh chồng của tool; "cu": sublabel tên config `<nhóm>_<k>` (project dựng trước đây)."""
    check_config(cfg)
    if kieu not in ("so", "cu"):
        raise SystemExit(f"Kiểu tên sublabel {kieu!r} không hợp lệ (chỉ so hoặc cu).")
    if kieu == "so":
        check_ten_so(cfg["points"])
    ten = {p["name"]: str(i + 1) for i, p in enumerate(cfg["points"])} if kieu == "so" else {}
    lines = cfg.get("lines") or {}
    out = []
    for group, pts in groups_of(cfg["points"]).items():
        sub = [dict(name=ten.get(p["name"], p["name"]), type="points", color=GROUP_COLOR[group],
                    attributes=[dict(name=LOW_CONF, mutable=True, input_type="checkbox", default_value="false", values=["false"])])
               for p in pts]
        out.append(dict(name=group, type="skeleton", color=GROUP_COLOR[group], attributes=[], sublabels=sub, svg=build_svg(pts, lines, ten)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sinh config/face50_label.json (bảy label skeleton, mỗi nhóm một) từ config/m28_config.json")
    ap.add_argument("--config", default=os.path.join("config", "m28_config.json"))
    ap.add_argument("--out", default=os.path.join("config", "face50_label.json"))
    ap.add_argument("--ten", choices=("so", "cu"), default="so", help="tên sublabel trên CVAT: so = 1..50 (mặc định), cu = <nhóm>_<k> của bản trước")
    args = ap.parse_args(argv)
    if not os.path.isfile(args.config):
        raise SystemExit(f"Không thấy {args.config}: chạy từ thư mục source-tool\\m28-prelabel hoặc dùng --config.")
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    labels = build_labels(cfg, args.ten)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(labels, f, ensure_ascii=False, indent=1)
        f.write("\n")
    n_edge = len(edge_names(cfg["points"], cfg.get("lines") or {}))
    print(f"Đã ghi {args.out}: {len(labels)} label skeleton ({', '.join(lb['name'] for lb in labels)}), {N_POINTS} điểm, {n_edge} cạnh. Chưa thử trên server CVAT thật: "
          "tạo project m28 từ file này rồi mở CVAT, kiểm đủ bảy label, 50 điểm và cạnh nối (xem README mục Rủi ro).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
