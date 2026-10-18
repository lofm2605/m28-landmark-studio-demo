"""Sinh config/m28_config.json (BẢN NHÁP, P3 chốt), config/map_mp50.json và (khi cần) config/mp_mirror478.json: 50 điểm "DMS" đặt TRỰC TIẾP lên đỉnh MediaPipe.

    python tool\\make_config.py                     (sinh lại file từ bảng SPEC dưới đây, giữ số đã có: flip_width, tmpl, t_flip, tolerance, status)
    python tool\\make_config.py --run INC3_ALL --manifest data\\manifest.csv     (ước lượng lại flip_width, tmpl từ dữ liệu thật; KHÔNG ghi đè hoán vị gương)
    python tool\\make_config.py --run INC3_ALL --manifest data\\manifest.csv --learn-mirror     (học lại và GHI ĐÈ hoán vị gương, chỉ khi thật cần)

Config version 3 (QĐ-003, 7/10/2026: định nghĩa 50 điểm DMS thay hẳn 50 điểm version 2; phương pháp chọn đỉnh trực tiếp của QĐ-002 giữ nguyên):
  * 50 điểm chia 7 nhóm (`group`), KHÔNG có viền hàm/cằm, KHÔNG có khung đầu:
        longmaytrai 5 | longmayphai 5 | songmui 4 | mattrai 8 | matphai 8 | moingoai 12 | moitrong 8
    Tên điểm `<nhóm>_<k>` (k từ 1, không đệm số 0), thứ tự nhóm trong config và trong CVAT đúng như dòng trên. Chú ý so chuỗi: `moingoai_10` < `moingoai_2`
    theo chữ cái; mọi chỗ cần thứ tự dùng thứ tự trong config, không sắp theo chữ (eval50.eye_openness chọn một điểm của cặp bằng chỉ số trong config).
  * QUY ƯỚC BÊN THEO BỨC ẢNH, không soi gương, NGƯỢC với version 2: `*trai` nằm ở nửa TRÁI của ảnh (theo người xem), `*phai` ở nửa PHẢI. Version 2 gọi
    theo người trong ảnh (R = nửa trái ảnh). Mã `side` giữ nguyên R/L/M nhưng nghĩa mới: R = nửa phải ảnh (`*phai`), L = nửa trái ảnh (`*trai`), M = trên trục.
    Config có trường `side_convention: "image"`; công cụ từ chối config thiếu trường này (config version 2 cũ). Khi mặt thẳng, ảnh không lật:
    `mattrai`/`longmaytrai` là mắt/mày PHẢI CỦA NGƯỜI (đỉnh MediaPipe 33, 133..., 70, 107...), `matphai`/`longmayphai` là mắt/mày TRÁI CỦA NGƯỜI (263, 362..., 300, 336...).
  * Thứ tự trong nhóm đi theo vòng hoặc dọc đường để `make_label.edges_of` (nối điểm liền nhau cùng `line`, nối kín khi `closed`) vẽ đúng khung:
      - lông mày (5): `_1` đầu mày (gần sống mũi) -> `_5` đuôi mày, cả hai bên theo giải phẫu, nên `longmaytrai_k` <-> `longmayphai_k` là cặp gương;
      - sống mũi (4, side M): `_1` giữa hai mắt (gốc mũi) -> `_4` chóp mũi;
      - mắt (8), vòng kín: `_1` khoé ngoài, `_2.._4` mí trên từ ngoài vào trong, `_5` khoé trong, `_6.._8` mí dưới từ trong ra ngoài; `mattrai_k` <-> `matphai_k`;
        `coincide` (mí trên/dưới khi nhắm): `_2`<->`_8`, `_3`<->`_7`, `_4`<->`_6`;
      - môi ngoài (12), vòng kín: `_1` khoé TRÁI ảnh, `_2.._6` mép trên từ trái sang phải ảnh, `_7` khoé PHẢI ảnh, `_8.._12` mép dưới từ phải sang trái; cặp gương
        1<->7, 2<->6, 3<->5, 8<->12, 9<->11, còn `_4`, `_10` tự đối xứng (side M);
      - môi trong (8), vòng kín: `_1` khoé trái ảnh, `_2.._4` mép trên trái -> phải, `_5` khoé phải, `_6.._8` mép dưới phải -> trái; cặp 1<->5, 2<->4, 6<->8, `_3`, `_7` side M;
        `coincide` (môi khép): `_2`<->`_8`, `_3`<->`_7`, `_4`<->`_6`.
    Môi đánh số theo ảnh (trái -> phải) vì môi là MỘT nhóm nằm giữa mặt, còn mắt và mày tách hai nhóm trái/phải nên đánh số theo giải phẫu (ngoài/trong,
    đầu/đuôi): nhờ đó `_k` của hai bên luôn là cặp gương, không cần tra bảng.
  * Các trường (giữ khung version 2, thêm `group`): `name`, `group`, `region` (vùng thô brow/nose/eye/lip, để cột `reg_<vùng>` của nme_per_face.csv giữ nghĩa với P5;
    không còn `jaw`), `side`, `flip`, `mp_idx`, `type` (E: điểm mốc đo điểm-điểm; C: điểm trên đường cong), `curve` (danh sách TÊN điểm dọc đường, có chứa chính điểm; E: null;
    mọi tên của curve nằm trong cùng `line` với điểm, không còn ngoại lệ môi trong), `line` (= tên nhóm), `anchor`, `coincide`, `tmpl`.
    `anchor` giữ nghĩa version 2 (kế hoạch P3): 1 = điểm MỐC, đặt trước rồi mới chia đều các điểm còn lại. Quy tắc version 3: hai đầu của đường hở (đầu/đuôi mày, gốc/chóp mũi),
    hai khoé mắt, khoé môi ngoài và trong, và điểm giữa môi (`moingoai_4`, `_10`, `moitrong_3`, `_7`); các điểm còn lại (mí trên/dưới, điểm trung gian) là 0.
    `lines`: mattrai, matphai, moingoai, moitrong closed = true; longmaytrai, longmayphai, songmui closed = false. `iod_points` = hai khoé mắt ngoài [mattrai_1, matphai_1]
    (thứ tự: trái ảnh, phải ảnh). `t_flip` và `tolerance` vẫn null, `status` bắt đầu bằng NHAP (P2 chốt t_flip 12/10, P3 tolerance 10/10).
  * `tmpl` = trung bình 50 điểm (toạ độ ảnh cắt 512) do CHÍNH ánh xạ dự đoán trên các mặt F thẳng (pose = 0 và |yaw| <= --max-yaw, mặc định 12 độ). Không có đáp án nên
    dùng dự đoán; chỉ để dựng khuôn skeleton CVAT (make_label.py), không dùng để đo gì. `keep_existing` chỉ mang số cũ sang khi CÙNG version và CÙNG tên điểm, nên
    config version 2 không mang `tmpl`/`t_flip` sang version 3.

Trình tự cho P3 (mọi lệnh chạy từ source-tool\\m28-prelabel, cmd):
  1. python tool\\m28.py prepare --run <run> --images data\\frames --set F Tdev --box auto   (người chỉ có gói: --images data\\crops --box crop)
  2. python tool\\make_config.py --run <run> --manifest data\\manifest.csv        (không ghi đè hoán vị gương; thêm --learn-mirror nếu thật sự cần học lại)
  3. python tool\\make_label.py
  4. python tool\\m28.py prepare --run <run> --force map50 flags autoqc overlays
  5. python tool\\check_flip.py --run <run>

Bảng đỉnh MediaPipe (k = 1.. theo thứ tự trong nhóm). Chọn theo topology Face Mesh rồi KIỂM BẰNG MẮT trên 46 mặt tài xế thật của F, G, P, X, D (thẳng, quay hai phía, kính, kính râm,
ngáp, nhắm mắt, tối/sáng gắt, camera Dash và Mirror, hai tài xế DrivFace; không dùng Tdev, Ttest để chọn). Không dùng đáp án có sẵn nào.
    longmaytrai  107  66 105  63  70                          (mép TRÊN lông mày nửa trái ảnh, đầu mày -> đuôi mày)
    longmayphai  336 296 334 293 300                          (gương của nhóm trên)
    songmui      168 197   5   1                              (gốc mũi giữa hai mắt -> chóp mũi)
    mattrai       33 160 159 158 133 153 145 144              (khoé ngoài, mí trên ngoài -> trong, khoé trong, mí dưới trong -> ngoài)
    matphai      263 387 386 385 362 380 374 373
    moingoai      61  40  37   0 267 270 291 321 314  17  84  91   (khoé trái ảnh, mép trên trái -> phải, khoé phải ảnh, mép dưới phải -> trái)
    moitrong      78  81  13 311 308 402  14 178
Lý do chọn:
  * mày: mép trên (v2 cũng dùng). So với mép dưới (55 65 52 53 46) trên 12 mặt: mép trên nằm trên biên trên của lông mày, mép dưới thường rơi xuống da giữa mày và mắt khi
    mày thưa hoặc có gọng kính. Hai mép cách nhau ~7% IOD nên đường GIỮA lông mày (nơi người gán đặt điểm) cách điểm nháp ~3-4% IOD: người sửa thường kéo điểm xuống vài pixel;
  * sống mũi: 168 chỉ cao hơn đường nối hai khoé mắt trong ~2% IOD (nên đúng "giữa hai mắt"), chóp = 1 (đỉnh 2, chân giữa, thấp hơn 4% IOD và không còn trong 50 điểm). 197 và 5 ở 36% và
    67% chiều dài từ 168 tới 1 (chia đều 1/3, 2/3);
  * mắt: bộ 6 đỉnh EAR chuẩn (33, 160, 158, 133, 153, 144 và gương) cộng đỉnh giữa mí (159/145, 386/374): cặp dọc 160-144, 159-145, 158-153 khớp ba cặp `coincide` và cho EAR chuẩn;
  * môi ngoài: khoé 61/291; mép trên 40, 37, 0, 267, 270 và dưới 321, 314, 17, 84, 91 chia đều theo cung (40 ở 31%, 37 ở 77% cung khoé -> giữa); giữa môi 0 và 17 nằm trên trục gương;
  * môi trong: khoé 78/308; 81 và 178 cùng ở 54% cung khoé -> giữa nên mỗi cặp trên/dưới (81-178, 13-14, 311-402) thẳng đứng và trùng nhau khi môi khép, còn bộ 82/312/317/87 (gợi ý ban
    đầu) dồn vào giữa miệng hơn nên không dùng. 13 và 14 nằm trên trục gương.
Điểm đổi so với gợi ý ban đầu trong kế hoạch: chỉ môi trong (81/311 và 402/178 thay cho 82/312 và 317/87, lý do trên). Còn lại giữ đúng gợi ý.
Điểm YẾU đã thấy (xem ảnh kiểm ở báo cáo): (1) mặt quay mạnh (|yaw| >= 30): các điểm của mắt, mày, môi phía XA cụm lại sát sống mũi/khoé miệng và nằm trên bề mặt 3D bị che, không trên
    biên nhìn thấy; (2) kính râm hoặc gọng kính: mắt và mày chỉ là "đoán" của MediaPipe; (3) mày chọn mép trên: cao hơn đường giữa vài pixel; (4) môi trong khi ngáp rộng hoặc khi tay che miệng;
    mắt nhắm: mí trên/dưới trùng nhau theo `coincide`; (5) mặt tối (luma < 70): điểm hợp lý nhưng chỉ là đoán; (6) chóp mũi khi đầu cúi/ngẩng nhiều và mặt nghiêng profile.
"""
import argparse
import csv
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m28core import mirror as mirror_mod  # noqa: E402
from m28core.mapping import apply_map  # noqa: E402

VERSION = 3
STATUS = "NHAP - cho P3 chot, dong bang 12/10"
SIDE_CONVENTION = "image"
SIDE_NOTE = ("side theo BUC ANH (khong soi guong): R = nua PHAI anh (nhom *phai), L = nua TRAI anh (nhom *trai), M = tren truc. "
             "Nguoc voi config version 2 (side theo nguoi trong anh).")

# nhóm, vùng thô, vòng kín?, số điểm. Thứ tự = thứ tự nhóm trong config (và trong CVAT).
GROUPS = (("longmaytrai", "brow", False, 5), ("longmayphai", "brow", False, 5), ("songmui", "nose", False, 4),
          ("mattrai", "eye", True, 8), ("matphai", "eye", True, 8), ("moingoai", "lip", True, 12), ("moitrong", "lip", True, 8))
GROUP_NAMES = tuple(g[0] for g in GROUPS)
REGIONS = ("brow", "nose", "eye", "lip")

# Đỉnh MediaPipe của từng điểm (k = 1.. theo thứ tự trong nhóm, xem docstring). Nhóm trái ảnh chọn trước, nhóm phải ảnh là gương qua mp_mirror478.json.
VERTS = {
    "longmaytrai": (107, 66, 105, 63, 70),
    "longmayphai": (336, 296, 334, 293, 300),
    "songmui": (168, 197, 5, 1),
    "mattrai": (33, 160, 159, 158, 133, 153, 145, 144),
    "matphai": (263, 387, 386, 385, 362, 380, 374, 373),
    "moingoai": (61, 40, 37, 0, 267, 270, 291, 321, 314, 17, 84, 91),
    "moitrong": (78, 81, 13, 311, 308, 402, 14, 178),
}

# Luật theo nhóm: bên (k -> R/L/M), điểm đối xứng (k -> (nhóm, k)), E (k của điểm mốc), anchor (k), curve(k) -> danh sách k hoặc None.
_E, _C = "E", "C"


def _swap(group):
    return {"longmaytrai": "longmayphai", "longmayphai": "longmaytrai", "mattrai": "matphai", "matphai": "mattrai"}[group]


def _rule_pair(group, n):
    """Cặp trái/phải theo giải phẫu: nhóm trái ảnh (L) <-> nhóm phải ảnh (R), cùng k. n = số điểm của nhóm."""
    side = "L" if group.endswith("trai") else "R"
    return dict(side={k: side for k in range(1, n + 1)}, flip={k: (_swap(group), k) for k in range(1, n + 1)})


def _lip(group, side, partner):
    return dict(side=side, flip={k: (group, partner[k]) for k in partner})


_RULES = {
    "longmaytrai": dict(_rule_pair("longmaytrai", 5), E=(1, 5), anchor=(1, 5), curve=lambda k: [1, 2, 3, 4, 5]),
    "longmayphai": dict(_rule_pair("longmayphai", 5), E=(1, 5), anchor=(1, 5), curve=lambda k: [1, 2, 3, 4, 5]),
    "songmui": dict(side={k: "M" for k in range(1, 5)}, flip={k: ("songmui", k) for k in range(1, 5)}, E=(1, 4), anchor=(1, 4),
                    curve=lambda k: [1, 2, 3, 4]),
    "mattrai": dict(_rule_pair("mattrai", 8), E=(1, 5), anchor=(1, 5), curve=lambda k: [1, 2, 3, 4, 5] if k <= 4 else [5, 6, 7, 8, 1]),
    "matphai": dict(_rule_pair("matphai", 8), E=(1, 5), anchor=(1, 5), curve=lambda k: [1, 2, 3, 4, 5] if k <= 4 else [5, 6, 7, 8, 1]),
    "moingoai": dict(_lip("moingoai", {1: "L", 2: "L", 3: "L", 4: "M", 5: "R", 6: "R", 7: "R", 8: "R", 9: "R", 10: "M", 11: "L", 12: "L"},
                         {1: 7, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1, 8: 12, 9: 11, 10: 10, 11: 9, 12: 8}),
                     E=(1, 7), anchor=(1, 4, 7, 10), curve=lambda k: [1, 2, 3, 4, 5, 6, 7] if k <= 7 else [7, 8, 9, 10, 11, 12, 1]),
    "moitrong": dict(_lip("moitrong", {1: "L", 2: "L", 3: "M", 4: "R", 5: "R", 6: "R", 7: "M", 8: "L"}, {1: 5, 2: 4, 3: 3, 4: 2, 5: 1, 6: 8, 7: 7, 8: 6}),
                     E=(1, 5), anchor=(1, 3, 5, 7), curve=lambda k: [1, 2, 3, 4, 5] if k <= 5 else [5, 6, 7, 8, 1]),
}
COINCIDE_K = (("mattrai", 2, 8), ("mattrai", 3, 7), ("mattrai", 4, 6), ("matphai", 2, 8), ("matphai", 3, 7), ("matphai", 4, 6),
              ("moitrong", 2, 8), ("moitrong", 3, 7), ("moitrong", 4, 6))      # mí trên/dưới khi nhắm, môi trong khi khép
CLOSED = {g: closed for g, _r, closed, _n in GROUPS}


def _name(group, k):
    return f"{group}_{k}"


def spec():
    """[(tên, nhóm, k, mp_idx, vùng, side, tên điểm đối xứng, type, curve [tên] hoặc None, line, anchor)] theo thứ tự config."""
    rows = []
    for group, region, _closed, n in GROUPS:
        rule, verts = _RULES[group], VERTS[group]
        assert len(verts) == n, f"{group}: cần {n} đỉnh, có {len(verts)}"
        for k in range(1, n + 1):
            fg, fk = rule["flip"][k]
            typ = _E if k in rule["E"] else _C
            curve = None if typ == _E else [_name(group, c) for c in rule["curve"](k)]
            rows.append((_name(group, k), group, k, verts[k - 1], region, rule["side"][k], _name(fg, fk), typ, curve, group, int(k in rule["anchor"])))
    return rows


def build_config(tmpl=None, t_flip=None, perm=None):
    """Config version 3. perm: hoán vị gương 478 đỉnh (config/mp_mirror478.json); có thì kiểm nhất quán với cặp flip và điểm side M."""
    rows = spec()
    assert [(g, n) for g, _r, _c, n in GROUPS] == [(g, sum(1 for r in rows if r[1] == g)) for g in GROUP_NAMES], "số điểm mỗi nhóm lệch bảng GROUPS"
    assert len(rows) == 50, f"phải đủ 50 điểm, có {len(rows)}"
    idx = [r[3] for r in rows]
    assert len(set(idx)) == 50 and all(0 <= i < 478 for i in idx), "mp_idx phải là 50 đỉnh khác nhau trong 0-477"
    by_row = {r[0]: r for r in rows}
    pts = []
    for name, group, k, mp, region, side, flip, typ, curve, line, anchor in rows:
        assert by_row[flip][6] == name, f"cặp flip của {name} không đối xứng ({flip} không trỏ ngược lại)"
        assert (flip == name) == (side == "M"), f"{name}: side {side} không khớp với flip (M khi và chỉ khi tự đối xứng)"
        assert (curve is None) == (typ == _E), f"{name}: type {typ} và curve không khớp"
        if curve is not None:
            assert name in curve, f"{name}: curve phải chứa chính điểm đó"
            assert all(c in by_row and by_row[c][9] == line for c in curve), f"{name}: curve ra ngoài line {line}"
        if side != "M":
            assert by_row[flip][5] != side, f"{name}: hai điểm của cặp flip phải khác bên"
        pts.append({"name": name, "group": group, "region": region, "side": side, "flip": flip, "mp_idx": mp, "type": typ,
                    "curve": curve, "line": line, "anchor": anchor, "coincide": None, "tmpl": None})
    by = {p["name"]: p for p in pts}
    for group, a, b in COINCIDE_K:
        by[_name(group, a)]["coincide"], by[_name(group, b)]["coincide"] = _name(group, b), _name(group, a)
    if perm is not None:
        check_perm(pts, perm)
    if tmpl is not None:
        tmpl = np.asarray(tmpl, float)
        assert tmpl.shape == (len(pts), 2), f"tmpl phải có hình ({len(pts)}, 2), nhận {tmpl.shape}"
        for p, t in zip(pts, tmpl):
            p["tmpl"] = [round(float(t[0]), 2), round(float(t[1]), 2)]
    return {"version": VERSION, "status": STATUS, "side_convention": SIDE_CONVENTION, "side_note": SIDE_NOTE, "n_points": len(pts), "points": pts,
            "lines": {k: {"closed": v} for k, v in CLOSED.items()},
            "iod_points": [_name("mattrai", 1), _name("matphai", 1)], "t_flip": t_flip, "tolerance": None}


def check_perm(points, perm):
    """Với mọi điểm p: perm[mp_idx(p)] == mp_idx(flip(p)); điểm side M nằm trên trục (perm[mp_idx] == mp_idx). Sai thì AssertionError rõ ràng."""
    by = {p["name"]: p for p in points}
    for p in points:
        q = by[p["flip"]]
        assert perm[p["mp_idx"]] == q["mp_idx"], (
            f"{p['name']} (đỉnh {p['mp_idx']}) có đối xứng gương là đỉnh {perm[p['mp_idx']]} theo mp_mirror478.json, "
            f"nhưng flip {q['name']} dùng đỉnh {q['mp_idx']}: sửa SPEC hoặc học lại hoán vị gương")
        if p["side"] == "M":
            assert perm[p["mp_idx"]] == p["mp_idx"], (
                f"{p['name']} có side M nhưng đỉnh {p['mp_idx']} không nằm trên trục đối xứng (đối xứng với đỉnh {perm[p['mp_idx']]})")


def build_map(cfg, flip_width=512.0, meta=None):
    """map_mp50.json version 3 (kind vertex) từ config. Cùng cấu trúc version 2 nhưng version tăng để map của định nghĩa 50 điểm cũ bị từ chối rõ ràng."""
    return {"version": 3, "kind": "vertex", "names": [p["name"] for p in cfg["points"]],
            "points": {p["name"]: {"mp_idx": p["mp_idx"], "flip": p["flip"]} for p in cfg["points"]},
            "flip_width": float(flip_width), "meta": meta or {}}


def gt50_template():
    """Đáp án 50 điểm nay đến từ nhãn nhóm gán tay trong CVAT (tool\\eval50.py): chỉ ghi file mẫu rỗng."""
    return {}


# ---------- ước lượng từ dữ liệu thật (cần pred478.json của một lượt chạy) ----------
def read_manifest(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def select_faces(rows, pred, set_name="F", max_yaw=None):
    """Tên mặt (không đuôi) của tập set_name có pose = 0, có cả ảnh gốc và ảnh lật trong pred. max_yaw: chỉ giữ |yaw| <= max_yaw (nếu manifest có cột yaw)."""
    out = []
    for r in rows:
        name = r["file"][:-4] if r["file"].lower().endswith(".png") else r["file"]
        if r.get("set") != set_name or r.get("pose") != "0" or name not in pred or not pred[name].get("flip"):
            continue
        if max_yaw is not None and r.get("yaw") not in (None, ""):
            if abs(float(r["yaw"])) > max_yaw:
                continue
        out.append(name)
    return out


def estimate_flip_width(origs, flips, perm, idx50=None):
    """w sao cho điểm đã bỏ lật (x' = w - x_lật) trùng điểm của ảnh gốc về trung bình (bình phương tối thiểu): w = trung bình của
    x_gốc(i) + x_lật(perm[i]). Trả dict: w (50 điểm nếu có idx50, không thì 478), trung vị, độ lệch y (trung bình có dấu và trung vị tuyệt đối),
    w trên 478 đỉnh. Không cần đáp án."""
    perm = np.asarray(perm, int)
    sel = np.arange(478) if idx50 is None else np.asarray(idx50, int)
    s_main, s_all, dy = [], [], []
    for o, f in zip(origs, flips):
        o, f = np.asarray(o, float), np.asarray(f, float)
        s_main.append(o[sel, 0] + f[perm[sel], 0])
        s_all.append(o[:, 0] + f[perm, 0])
        dy.append(o[sel, 1] - f[perm[sel], 1])
    s_main, s_all, dy = np.concatenate(s_main), np.concatenate(s_all), np.concatenate(dy)
    return {"w": float(s_main.mean()), "w_median": float(np.median(s_main)), "w_all478": float(s_all.mean()),
            "w_all478_median": float(np.median(s_all)), "w_std": float(s_main.std()),
            "dy_mean": float(dy.mean()), "dy_median_abs": float(np.median(np.abs(dy))), "n_faces": len(origs)}


def template(cfg, mp_map, origs):
    """Khuôn trung bình 50 điểm (toạ độ ảnh cắt 512) do ánh xạ dự đoán trên các mặt origs (không có đáp án)."""
    if not origs:
        raise ValueError("không có mặt F nào có pose = 0 (và ảnh lật) trong lượt chạy để lấy trung bình khuôn")
    names = [p["name"] for p in cfg["points"]]
    return np.mean([[apply_map(o, mp_map, cfg)[n] for n in names] for o in origs], axis=0)


def keep_existing(cfg, old, t_flip_given):
    """Chạy lại không được xoá số người khác đã ghi: t_flip (P2), tolerance (P3, 10/10), status, tmpl.
    Chỉ giữ khi old cùng version và cùng tên điểm (tmpl của config version 1 là hình học 98 điểm cũ, của version 2 là hình của định nghĩa 50 điểm cũ: không được mang sang)."""
    kept = []
    if old and old.get("version") == cfg["version"] and [p["name"] for p in old.get("points", [])] == [p["name"] for p in cfg["points"]]:
        if not t_flip_given and old.get("t_flip") is not None:
            cfg["t_flip"] = old["t_flip"]
            kept.append("t_flip")
        if old.get("tolerance") is not None:
            cfg["tolerance"] = old["tolerance"]
            kept.append("tolerance")
        if isinstance(old.get("low_conf_v2"), dict):                 # mô hình cờ phiên bản 2 (QĐ-025, học bằng do_co_thi_nghiem.py --hoc-v2)
            cfg["low_conf_v2"] = old["low_conf_v2"]
            kept.append("low_conf_v2")
        if not str(old.get("status", "NHAP")).startswith("NHAP"):
            cfg["status"] = old["status"]
            kept.append("status")
        if cfg["points"][0]["tmpl"] is None and old["points"][0].get("tmpl") is not None:
            for p, q in zip(cfg["points"], old["points"]):
                p["tmpl"] = q["tmpl"]
            kept.append("tmpl")
    return kept


def _load(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def _dump(path, obj, indent=1):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
        f.write("\n")
    os.replace(tmp, path)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # Windows: stdout chuyển hướng không bị cp1252
    ap = argparse.ArgumentParser(description="Sinh config version 3 (50 điểm DMS, chọn đỉnh MediaPipe), map_mp50.json; hoán vị gương chỉ ghi khi có --learn-mirror")
    ap.add_argument("--out", default=os.path.join("config", "m28_config.json"))
    ap.add_argument("--map-out", default=os.path.join("config", "map_mp50.json"))
    ap.add_argument("--mirror", default=os.path.join("config", "mp_mirror478.json"), help="hoán vị gương 478 đỉnh (đọc; chỉ ghi lại khi có --learn-mirror)")
    ap.add_argument("--run", help="lượt đã chạy crop + mediapipe cho tập F: ước lượng lại flip_width và tmpl từ dữ liệu thật (dùng hoán vị gương CÓ SẴN)")
    ap.add_argument("--learn-mirror", action="store_true",
                    help="với --run: học lại hoán vị gương từ dữ liệu và GHI ĐÈ --mirror (mặc định chỉ đọc file có sẵn; hoán vị là tính chất hình học của 478 đỉnh, không phụ thuộc tên điểm)")
    ap.add_argument("--manifest", default=os.path.join("data", "manifest.csv"))
    ap.add_argument("--max-yaw", type=float, default=12.0, help="tmpl chỉ lấy mặt F pose = 0 có |yaw| <= số này (độ); cần cột yaw của manifest")
    ap.add_argument("--no-mesh", action="store_true", help="không sửa hoán vị gương bằng lưới tam giác MediaPipe (không import mediapipe)")
    ap.add_argument("--t-flip", type=float, help="ngưỡng cờ low_conf do P2 chọn trên T-dev; bỏ trống = giữ số đã có (hoặc null)")
    ap.add_argument("--gt50", help="ghi file đáp án mẫu rỗng {} (đáp án nay đến từ nhãn gán tay trong CVAT, đo bằng tool\\eval50.py)")
    a = ap.parse_args(argv)
    if a.learn_mirror and not a.run:
        ap.error("--learn-mirror cần --run <lượt có pred478 của tập F>")

    old_cfg, old_map = _load(a.out), _load(a.map_out)
    flip_width, map_meta, tmpl, msgs = 512.0, {}, None, []
    if a.run:
        pred_path = os.path.join("runs", a.run, "mediapipe", "pred478.json")
        if not os.path.exists(pred_path):
            sys.exit(f"Không thấy {pred_path}: chạy prepare (crop, mediapipe) cho tập F trước.")
        pred = _load(pred_path)
        rows = read_manifest(a.manifest)
        names_pose0 = select_faces(rows, pred, "F")
        if len(names_pose0) < 30:
            sys.exit(f"Chỉ có {len(names_pose0)} mặt F pose = 0 có cả ảnh gốc và ảnh lật trong {pred_path} (cần >= 30): chạy prepare --set F.")
        origs = [pred[n]["orig"] for n in names_pose0]
        flips = [pred[n]["flip"] for n in names_pose0]
        edges = None if a.no_mesh else mirror_mod.tessellation_edges()
        if a.learn_mirror:
            mir = mirror_mod.learn_mirror_flip(origs, flips, 512.0, edges)
            bad = mirror_mod.sanity(mir["perm"])
            if bad:
                sys.exit("Hoán vị gương học được không đạt kiểm cứng:\n  " + "\n  ".join(bad))
            meta = mir["meta"]
            msgs.append(f"hoán vị gương HỌC LẠI và ghi đè {a.mirror}: {meta['n_faces']} mặt F pose=0, {meta['n_fixed']} đỉnh trên trục, sai số ghép trung vị "
                        f"{meta['resid_median_pct_iod']:.2f}% / lớn nhất {meta['resid_max_pct_iod']:.2f}% IOD"
                        + (f", cạnh lưới vỡ {meta['mesh_violations_before_refine']} -> {meta['mesh_violations_after_refine']}" if edges is not None else ""))
            _dump(a.mirror, {"perm": mir["perm"], "fixed": mir["fixed"], "meta": meta}, indent=None)
            perm = mir["perm"]
        else:
            if not os.path.exists(a.mirror):
                sys.exit(f"Không thấy {a.mirror}: lấy file từ repo hoặc chạy lại với --learn-mirror để học từ dữ liệu.")
            mir = mirror_mod.load_mirror(a.mirror)
            perm = mir["perm"]
            bad = mirror_mod.sanity(perm)
            if bad:
                sys.exit(f"{a.mirror} không đạt kiểm cứng:\n  " + "\n  ".join(bad))
            msgs.append(f"hoán vị gương GIỮ NGUYÊN {a.mirror} ({len(mir['fixed'])} đỉnh trên trục); không ghi đè (thêm --learn-mirror nếu thật sự cần học lại)")
            res = mirror_mod.check_against_data(perm, origs, flips, edges)
            msgs.append(f"  kiểm trên {res['n_faces']} mặt F pose=0 của lượt {a.run}: ghép gần nhất học lại khác file ở {res['n_diff']}/478 đỉnh"
                        + (f" (ví dụ {res['diff'][:6]})" if res["n_diff"] else "") + f"; sai số ghép của file trung vị {res['resid_median_pct_iod']:.2f}% / lớn nhất "
                        f"{res['resid_max_pct_iod']:.2f}% IOD")
        cfg = build_config(None, a.t_flip, perm)
        idx50 = [p["mp_idx"] for p in cfg["points"]]
        fw = estimate_flip_width(origs, flips, perm, idx50)
        flip_width = fw["w"]
        map_meta = {"flip_width_source": f"{fw['n_faces']} mặt F pose=0 của lượt {a.run} (không cần đáp án)",
                    "flip_width_median": round(fw["w_median"], 4), "flip_width_std": round(fw["w_std"], 4),
                    "flip_width_478": round(fw["w_all478"], 4), "flip_dy_mean": round(fw["dy_mean"], 4),
                    "flip_dy_median_abs": round(fw["dy_median_abs"], 4), "date": time.strftime("%Y-%m-%d"),
                    "mirror_file": os.path.basename(a.mirror), "config_version": VERSION}
        msgs.append(f"flip_width = {flip_width:.3f} (trung vị {fw['w_median']:.3f}, 478 đỉnh {fw['w_all478']:.3f}; lệch y trung bình {fw['dy_mean']:+.3f} px, "
                    f"trung vị tuyệt đối {fw['dy_median_abs']:.3f} px)")
        mp_map = build_map(cfg, flip_width, map_meta)
        straight = select_faces(rows, pred, "F", a.max_yaw)
        if len(straight) < 10:
            straight = names_pose0
            msgs.append(f"CHÚ Ý: chỉ {len(straight)} mặt có |yaw| <= {a.max_yaw:g}, tmpl lấy trên mọi mặt F pose=0")
        tmpl = template(cfg, mp_map, [pred[n]["orig"] for n in straight])
        map_meta["tmpl_faces"] = len(straight)
        cfg = build_config(tmpl, a.t_flip, perm)
        msgs.append(f"tmpl: trung bình dự đoán của {len(straight)} mặt F pose=0 (|yaw| <= {a.max_yaw:g})")
    else:
        if not os.path.exists(a.mirror):
            sys.exit(f"Không thấy {a.mirror}: chạy với --run <lượt có pred478 của tập F> --learn-mirror để học hoán vị gương, hoặc lấy file từ repo.")
        mir = mirror_mod.load_mirror(a.mirror)
        cfg = build_config(None, a.t_flip, mir["perm"])
        if old_map and old_map.get("version") == 3 and "flip_width" in old_map:
            flip_width, map_meta = float(old_map["flip_width"]), old_map.get("meta") or {}
            msgs.append(f"giữ flip_width = {flip_width:.3f} của map cũ")
        else:
            msgs.append("CHÚ Ý: chưa có flip_width ước lượng (đặt 512): chạy lại với --run")
    kept = keep_existing(cfg, old_cfg, a.t_flip is not None)
    mp_map = build_map(cfg, flip_width, map_meta)
    _dump(a.out, cfg)
    _dump(a.map_out, mp_map)
    print(f"Đã ghi {a.out}: {cfg['n_points']} điểm" + (", có khuôn tmpl" if cfg["points"][0]["tmpl"] else ", chưa có tmpl")
          + (f"; giữ lại từ file cũ: {', '.join(kept)}" if kept else "") + f"; {a.map_out}" + (f"; {a.mirror}" if a.learn_mirror else ""))
    for m in msgs:
        print("  " + m)
    if a.gt50:
        _dump(a.gt50, gt50_template())
        print(f"Đã ghi {a.gt50} (mẫu rỗng): đáp án 50 điểm nay là nhãn nhóm gán tay trong CVAT, đo bằng tool\\eval50.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
