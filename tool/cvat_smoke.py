"""Kiểm tra nhanh CVAT THẬT: chạy đúng đường code của push / collect / xoá task trên dữ liệu giả (ảnh xám, KHÔNG phải ảnh mặt), rồi dọn.

    python tool\\cvat_smoke.py [--dry-run] [--url URL] [--org ORG] [--giu-task] [--giu-project] [--timeout GIAY]

Dùng để từng người chạy trên máy có CVAT thật (2.77, hoặc 2.78 như máy chủ repo: cùng tập bản mà cvat_io.check_version của push/collect nhận, tức
cvat_io.ban_chap_nhan(cvat_version của config\\pipeline.json)), xem phần nào chạy được, và gửi báo cáo cho P4 khi có HỎNG. Token CHỈ lấy từ biến
môi trường CVAT_ACCESS_TOKEN hoặc từ cấu hình tab Cài đặt (đã bật "Nhớ trên máy này"); KHÔNG có cờ --token. Link CVAT_URL cũng lấy từ đó
(--url / --org chỉ ghi đè link / tổ chức, token giữ nguyên nguồn). Chỉ gọi tới đúng link đó.

Các bước (mã cố định; in `[k/12] <tên bước>: ...`; kết quả ĐẠT / HỎNG / BỎ QUA; bước hỏng làm bước phụ thuộc BỎ QUA nhưng dọn dẹp luôn chạy):
   1 Cấu hình cục bộ   2 XML nháp cục bộ   3 Link và token   4 Kết nối và phiên bản   5 Project và label skeleton   6 Dọn demo-smoke cũ
   7 Tạo task và job   8 Nhập XML nháp   9 Xuất và đọc lại (collect thật)   10 Bảo vệ an toàn   11 Xoá task demo-smoke   12 Project sau khi chạy
Không gọi lại logic của push/collect: bước 7-9, 11 gọi push.push, collect.collect, push.delete_task; bước 5 gọi push.get_project_id.
Bước 9 còn thử hai cờ của nút Merge jobs & Finish trên server thật (không thêm lời gọi SDK nào): --require-completed với job còn mới phải thoát mã 3
và không ghi gì; --overwrite phải xuất lại, chuyển bản cũ vào raw\\_cu và đọc state/stage/type của job về dạng chữ thường (ví dụ new).

Dữ liệu giả (sinh trong runs/_smoke/<giờ>/): 4 ảnh PNG xám/nhiễu kích thước khác nhau (hai ảnh Nhận, một Sửa nhãn CÓ nháp, một Sửa nhãn TRỐNG).
Hai ảnh Nhận (không phải một) và pipeline tạm job_size=1 để có ba job (Nhận, Nhận, Sửa nhãn) và thử luôn thứ tự frame qua nhiều job.
Sửa nhãn có nháp theo hợp đồng "Sửa nhãn giữ nháp": có <image> trong XML (cờ low_conf đọc được, ở đây mọi điểm true); ảnh trống không có trong XML.

An toàn: chỉ task tên `demo-smoke`; chỉ xoá đúng id lấy từ push.json (không tìm theo tên để xoá); chỉ xoá project m28 khi CHÍNH lần chạy này
tạo ra nó và nó đang rỗng. Đánh dấu runs/_smoke/dang_mo.json giữ id task chưa dọn xong (lần chạy sau tự dọn). Token không bao giờ vào
stdout, báo cáo, push.json, dang_mo.json hay đối số tiến trình con (báo cáo được đọc lại để kiểm).

--timeout (5-600, mặc định 60): timeout của TỪNG yêu cầu mạng (socket.setdefaulttimeout) và của tiền kiểm; không phải tổng thời gian.
Mã thoát: 0 = không bước nào HỎNG; 1 = có HỎNG; 2 = sai đối số. Dòng cuối stdout: `SMOKE_JSON: <đường dẫn báo cáo .json>`.
Chỉ thư viện chuẩn + cvat_sdk (nạp lười) + module trong tool/ (bước 2 cần numpy vì steps.image_xml nằm trong steps.py, có sẵn trong .venv).
"""
import argparse
import contextlib
import datetime
import importlib.metadata
import json
import math
import os
import platform
import random
import re
import socket
import struct
import sys
import time
import traceback
import types
import zlib

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
from m28core import cvat_io, dang_chay, push  # noqa: E402
import cai_dat  # noqa: E402
import cai_dat_thu  # noqa: E402
import make_label  # noqa: E402

TASK = "demo-smoke"
REVIEWER = "SMOKE"
# label trên CVAT: MỘT skeleton cho mỗi nhóm (tên label = tên nhóm, QĐ-004); label face50 một skeleton là bản CŨ
SMOKE_DIR = "_smoke"
MARKER = "dang_mo.json"
SDK_PIN = cvat_io.DEFAULT_PIPELINE["cvat_version"]     # bản cvat-sdk của nhóm (QĐ-009 giữ 2.77.0); cvat_version nhận được = ban_chap_nhan(SDK_PIN)
TOL_PX = 0.05
DAT, HONG, BO = "ĐẠT", "HỎNG", "BỎ QUA"
NAMES = {1: "Cấu hình cục bộ", 2: "XML nháp cục bộ", 3: "Link và token", 4: "Kết nối và phiên bản", 5: "Project và label skeleton",
         6: "Dọn demo-smoke cũ", 7: "Tạo task và job", 8: "Nhập XML nháp", 9: "Xuất và đọc lại (collect)", 10: "Bảo vệ an toàn",
         11: "Xoá task demo-smoke", 12: "Project sau khi chạy"}
N = len(NAMES)
KIND_VI = {"bad_url": "sai link", "bad_token": "sai token", "server_down": "server tắt hoặc sai link", "version_mismatch": "khác phiên bản",
           "redirect": "link bị chuyển hướng", "timeout": "server không trả lời", "no_sdk": "thiếu cvat-sdk", "other": "lỗi khác"}
# (tên file, (rộng, cao), vai): hai Nhận, một Sửa nhãn có nháp, một Sửa nhãn trống
IMAGES = [("smoke_A.png", (320, 240), "nhan"), ("smoke_B.png", (240, 360), "nhan"),
          ("smoke_C.png", (256, 256), "tay_nhap"), ("smoke_D.png", (200, 300), "tay_trong")]
JOB_STATES, JOB_STAGES = ("new", "in progress", "rejected", "completed"), ("annotation", "validation", "acceptance")     # giá trị chữ của CVAT 2.77/2.78
S = cvat_io.scrub


def ban_text(want):
    """Các bản server mà push/collect nhận với cvat_version `want` (đúng cvat_io.ban_chap_nhan), dạng chữ: "2.77.x, 2.78.x"."""
    return ", ".join(f"{a}.{b}.x" for a, b in sorted(cvat_io.ban_chap_nhan(want))) or "(không đọc được bản)"


# ---------- ảnh PNG xám và XML nháp (chỉ thư viện chuẩn) ----------
def png_gray(w, h, seed):
    """PNG xám 8 bit toàn nhiễu ngẫu nhiên (seed cố định), bằng zlib+struct."""
    rnd = random.Random(seed)
    raw = b"".join(b"\x00" + bytes(rnd.randrange(60, 200) for _ in range(w)) for _ in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def smoke_points(w, h, idx):
    """50 điểm tất định (hai chữ số thập phân, khác nhau, nằm trong ảnh): elip quanh tâm, pha khác nhau theo ảnh."""
    ph = 0.15 * (idx + 1)
    out = []
    for k in range(50):
        a = 2 * math.pi * k / 50 + ph
        out.append((float(f"{w / 2 + 0.4 * w * math.cos(a):.2f}"), float(f"{h / 2 + 0.4 * h * math.sin(a):.2f}")))
    return out


def smoke_low(role, idx):
    if role == "tay_nhap":
        return [True] * 50                                   # dữ liệu thử: Sửa nhãn có nháp đánh mọi điểm true (push nhận cờ bất kỳ)
    return [(k % (2 + idx)) == 0 for k in range(50)]         # xen kẽ true/false


def _text(v):
    """Giá trị enum của SDK thật (InputTypeEnum...) hoặc chuỗi/dict của gói giả -> chuỗi thường."""
    return str(getattr(v, "value", v) if v is not None else "").lower()


def compare_ann(ann, expect, names, local=False):
    """So nhãn đọc từ XML (parse_annotations) với dữ liệu đã sinh. Trả (danh sách vấn đề, sai số toạ độ lớn nhất)."""
    bad, worst = [], 0.0
    for name, e in expect.items():
        im = ann.get(name)
        if e["role"] == "tay_trong":
            if im is not None and im["n_shapes"]:
                bad.append(f"{name}: ảnh Sửa nhãn trống lại có {im['n_shapes']} nhãn")
            elif im is None and not local:
                bad.append(f"{name}: không có trong file xuất")
            continue
        if im is None:
            bad.append(f"{name}: không có trong XML")
            continue
        try:
            got_size = (int(im["width"]), int(im["height"]))
        except (TypeError, ValueError):
            got_size = None
        if got_size != e["size"]:
            bad.append(f"{name}: kích thước {got_size} khác ảnh đã sinh {e['size']}")
        pts, why = cvat_io.merged_face(im, cvat_io.groups_from_names(names))
        if pts is None:
            bad.append(f"{name}: {len(im['skeletons'])} skeleton, " + "; ".join(why[:2]))
            continue
        if list(pts) != names:
            bad.append(f"{name}: tên/thứ tự điểm khác ({len(pts)} điểm, thiếu {len(set(names) - set(pts))})")
        wrong_low = 0
        for n, (x, y), low in zip(names, e["pts"], e["low"]):
            p = pts.get(n)
            if p is None or p["x"] is None:
                continue
            worst = max(worst, abs(p["x"] - x), abs(p["y"] - y))
            if abs(p["x"] - x) > TOL_PX or abs(p["y"] - y) > TOL_PX:
                bad.append(f"{name}/{n}: toạ độ ({p['x']},{p['y']}) lệch ({x},{y})")
            wrong_low += p["low_conf"] != ("true" if low else "false")
        if wrong_low:
            bad.append(f"{name}: {wrong_low} điểm không giữ nguyên low_conf")
    return bad[:6], worst


def check_svg(svg, sub_ids, names, want_edges):
    """Vấn đề của svg label (nút đúng tên, đúng cặp cạnh); nút nối với điểm qua data-label-name hoặc data-label-id (server thật đổi sang id)."""
    if not isinstance(svg, str) or not svg.strip():
        return ["label không có svg (không có hình khung xương)"]
    tags = [(k, dict(re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', a))) for k, a in re.findall(r"<(line|circle)\b([^>]*)>", svg)]
    id2name = {str(i): n for i, n in sub_ids.items()}
    nodes = {}
    for kind, a in tags:
        if kind == "circle" and "data-node-id" in a:
            nodes[a["data-node-id"]] = a.get("data-label-name") or id2name.get(a.get("data-label-id", ""))
    bad = []
    if len(nodes) != len(names) or set(nodes.values()) != set(names):
        bad.append(f"svg có {len(nodes)} nút nối được với {len(set(nodes.values()) & set(names))}/{len(names)} điểm")
    edges = [frozenset((nodes.get(a.get("data-node-from")), nodes.get(a.get("data-node-to")))) for k, a in tags if k == "line"]
    if len(edges) != len(want_edges) or set(edges) != want_edges:
        bad.append(f"svg có {len(edges)} cạnh, cần {len(want_edges)}; cặp cạnh khác config: {len(set(edges) ^ want_edges)} cạnh lệch")
    return bad


# ---------- chạy ----------
class _Tee:
    """Ghi vào `out` (đã lọc token) và giữ bản sao để đọc lại các dòng [k/6] của push."""

    def __init__(self, out):
        self.out, self.buf = out, []

    def write(self, s):
        self.buf.append(s)
        self.out.write(S(s))
        return len(s)

    def flush(self):
        self.out.flush()

    def text(self):
        return "".join(self.buf)


def validate(o):
    """Lý do tiếng Việt nếu đối số sai, không thì None."""
    if not isinstance(o.timeout, (int, float)) or isinstance(o.timeout, bool) or not 5 <= o.timeout <= 600:
        return "--timeout phải từ 5 đến 600 giây."
    if o.url:
        u = cai_dat.check_url(o.url)
        if not u["ok"]:
            return "--url: " + u["error"]
    if o.org:
        _o, why = cai_dat.check_org(o.org)
        if why:
            return "--org: " + why
    return None


class Smoke:
    def __init__(self, o, out):
        self.o, self.out = o, out
        self.root = os.path.abspath(o.root or os.path.join(TOOL_DIR, ".."))
        self.smoke_root = os.path.join(self.root, "runs", SMOKE_DIR)
        self.res, self.by, self.goc = [], {}, {}                  # goc[mã bước bị bỏ qua] = mã bước hỏng gây ra
        self.env = self.client = self.pipe = self.pipe_path = None
        self.names = self.labels = self.cfg = self.expect = None
        self.source = ""
        self.server_version = self.username = ""
        self.project_name = "m28"
        self.project_existed = None
        self.project_created = False
        self.project_id = None
        self.project_note = ""
        self.task_id = None
        self.task_deleted = False
        self.baseline = None
        self.interrupted = False
        self.old_environ = {}

    # --- in ra, ghi kết quả ---
    def say(self, text, err=False):
        print(S(text), file=sys.stderr if err else self.out, flush=True)

    def record(self, code, status, note, secs=0.0, sub=None):
        r = dict(ma=code, ten=NAMES[code], ket_qua=status, ghi_chu=S(note), giay=round(secs, 1), con=[S(x) for x in (sub or [])])
        self.res = [x for x in self.res if x["ma"] != code] + [r]
        self.by[code] = r
        self.say(f"[{code}/{N}] {NAMES[code]}: {status}. {note}")
        for x in r["con"]:
            self.say(f"      - {x}")

    def ok(self, code):
        return self.by.get(code, {}).get("ket_qua") == DAT

    def why_not(self, deps):
        """Lý do bỏ qua nếu một bước phụ thuộc không ĐẠT, không thì None."""
        for d in deps:
            r = self.by.get(d)
            if r is None or r["ket_qua"] != DAT:
                root = d if r and r["ket_qua"] == HONG else self.goc.get(d)
                return f"vì bước {root} hỏng" if root else f"vì bước {d} bị bỏ qua"
        return None

    DOING = {3: "kiểm link và token", 4: "kiểm kết nối", 5: "tạo hoặc đọc project", 6: "dọn task cũ", 7: "tạo task", 8: "nhập nhãn nháp",
             9: "xuất nhãn và thu bằng collect", 10: "kiểm lớp bảo vệ", 11: "xoá task demo-smoke", 12: "dọn project"}

    def explain(self, e, doing):
        msg = cvat_io.translate_error(e, self.env or {}, doing)
        if msg is None:
            self.say(traceback.format_exc(), err=True)
            msg = f"Lỗi không lường trước khi {doing}: {type(e).__name__}: {S(e)[:300]}"
        return S(msg)

    def run_step(self, code, fn, deps=()):
        """Chạy một bước: fn() -> (trạng thái, ghi chú[, các dòng con]). Mọi lỗi (kể cả lạ) thành HỎNG; Ctrl+C đánh dấu bị ngắt."""
        if self.interrupted:
            return self.record(code, BO, "vì bị ngắt (Ctrl+C)")
        if self.o.dry_run and code >= 4:
            return self.record(code, BO, "chạy thử (--dry-run): không gọi mạng")
        why = self.why_not(deps)
        if why:
            m = re.search(r"bước (\d+) hỏng", why)
            if m:
                self.goc[code] = int(m.group(1))
            return self.record(code, BO, why)
        self.say(f"[{code}/{N}] {NAMES[code]}: đang chạy…")
        t0 = time.time()
        try:
            r = fn()
            self.record(code, r[0], r[1], time.time() - t0, r[2] if len(r) > 2 else None)
        except KeyboardInterrupt:
            self.interrupted = True
            self.record(code, HONG, "bị ngắt (Ctrl+C); dọn dẹp vẫn chạy", time.time() - t0)
        except SystemExit as e:
            self.record(code, HONG, S(e.code if isinstance(e.code, str) else f"dừng (mã {e.code})"), time.time() - t0)
        except Exception as e:      # noqa: BLE001 - bước nào cũng phải báo HỎNG tiếng Việt, không traceback chưa lọc
            self.record(code, HONG, self.explain(e, self.DOING.get(code, NAMES[code].lower())), time.time() - t0)

    def get_client(self):
        if self.client is None:
            self.client = cvat_io.connect(self.env)
        return self.client

    # --- đánh dấu task dở ---
    @property
    def marker_path(self):
        return os.path.join(self.smoke_root, MARKER)

    def write_marker(self):
        cvat_io.atomic_write_json(self.marker_path, dict(
            tool="cvat_smoke", task=TASK, task_id=self.task_id, project=self.project_name, project_id=self.project_id,
            cvat_url=cvat_io.norm_url(self.env["url"]), run=os.path.basename(self.run_dir), run_dir=self.run_dir, tao_luc=cvat_io.now_iso()))

    def drop_marker(self):
        try:
            os.remove(self.marker_path)
        except FileNotFoundError:
            pass

    # --- bước 1 ---
    def s1(self):
        cfg_dir = os.path.join(self.root, "config")
        self.pipe_path = os.path.join(cfg_dir, "pipeline.json")
        self.pipe = cvat_io.load_pipeline(self.pipe_path)
        self.project_name = self.pipe["project"]
        self.label_json = os.path.join(cfg_dir, "face50_label.json")
        self.labels, self.names = push.load_label_names(self.label_json)
        with open(os.path.join(cfg_dir, "m28_config.json"), encoding="utf-8") as f:
            self.cfg = json.load(f)
        want = json.loads(json.dumps(make_label.build_labels(self.cfg)))
        if want != self.labels:
            return HONG, "config\\face50_label.json khác bản sinh từ config\\m28_config.json: chạy python tool\\make_label.py rồi chạy lại."
        if [p["name"] for p in self.cfg["points"]] != self.names:
            return HONG, "tên/thứ tự 50 điểm trong face50_label.json khác m28_config.json: chạy python tool\\make_label.py."
        low = [s for lb in self.labels for s in lb["sublabels"] if any(a["name"] == "low_conf" and a["input_type"] == "checkbox" for a in s["attributes"])]
        self.want_edges = make_label.edge_names(self.cfg["points"], self.cfg.get("lines") or {})
        n_edge = len(self.want_edges)
        n_svg = sum(lb["svg"].count('data-type="edge"') for lb in self.labels)
        if len(self.labels) != 7 or len(low) != 50 or n_svg != n_edge:
            return HONG, f"{len(self.labels)} label (cần 7), {len(low)}/50 sublabel kèm low_conf, {n_svg} cạnh (cần {n_edge})."
        if cvat_io._mm(self.pipe["cvat_version"]) not in cvat_io.ban_chap_nhan(SDK_PIN):
            return HONG, (f"cvat_version trong config\\pipeline.json là {self.pipe['cvat_version']}, ngoài các bản cvat-sdk {SDK_PIN} của nhóm hỗ trợ "
                          f"({ban_text(SDK_PIN)}): trả về {SDK_PIN} (QĐ-009; server 2.78 vẫn chạy được với bản này).")
        return DAT, f"{len(self.labels)} label skeleton theo nhóm: 50 điểm kèm low_conf, {n_edge} cạnh khớp m28_config.json; cvat_version {self.pipe['cvat_version']}."

    # --- bước 2 ---
    def s2(self):
        try:
            from m28core import steps
        except ImportError as e:
            return HONG, f"Không nạp được m28core.steps ({e}): cần numpy trong .venv (python -m pip install numpy)."
        stamp = time.strftime("%Y%m%d_%H%M%S")
        n = 1
        self.run_dir = os.path.join(self.smoke_root, stamp)
        while os.path.exists(self.run_dir):
            n += 1
            self.run_dir = os.path.join(self.smoke_root, f"{stamp}_{n}")
        os.makedirs(os.path.join(self.run_dir, "imgs"))
        self.expect, parts, fid = {}, ['<?xml version="1.0" encoding="utf-8"?>', "<annotations>", "  <version>1.1</version>"], 0
        self.nhan_imgs, self.tay_imgs = [], []
        for i, (name, (w, h), role) in enumerate(IMAGES):
            path = os.path.join(self.run_dir, "imgs", name)
            with open(path, "wb") as f:
                f.write(png_gray(w, h, seed=1000 + i))
            (self.nhan_imgs if role == "nhan" else self.tay_imgs).append(path)
            e = dict(role=role, size=(w, h), pts=smoke_points(w, h, i), low=smoke_low(role, i))
            self.expect[name] = e
            if role != "tay_trong":                          # id: Nhận 0.., rồi Sửa nhãn có nháp (đúng như steps.build_xml)
                parts.append(steps.image_xml(fid, name, self.names, e["pts"], e["low"], w, h))
                fid += 1
        parts.append("</annotations>")
        self.xml = os.path.join(self.run_dir, "xml", "prelabel.xml")
        os.makedirs(os.path.dirname(self.xml))
        with open(self.xml, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        self.pipe_smoke = os.path.join(self.run_dir, "pipeline.json")
        cvat_io.atomic_write_json(self.pipe_smoke, dict(self.pipe, job_size=1))
        with open(self.xml, "rb") as f:
            ann = cvat_io.parse_annotations(f.read(), self.names)
        bad, worst = compare_ann(ann, self.expect, self.names, local=True)
        if bad or sorted(ann) != sorted(n for n, _s, r in IMAGES if r != "tay_trong"):
            return HONG, "XML nháp sinh ra không đọc lại đúng: " + "; ".join(bad or ["sai danh sách ảnh"])
        flags = {p["low_conf"] for im in ann.values() for sk in im["skeletons"] for p in sk["points"].values()}
        if flags != {"true", "false"}:
            return HONG, f"low_conf trong XML nháp chỉ có {sorted(flags)} (cần cả true và false)."
        return DAT, (f"{len(IMAGES)} ảnh PNG xám giả (2 Nhận, 1 Sửa nhãn có nháp, 1 Sửa nhãn trống), XML 3 mặt x 50 điểm đọc lại khớp "
                     f"(sai số {worst:.2f}px); thư mục {os.path.relpath(self.run_dir, self.root)}.")

    # --- bước 3 ---
    def s3(self):
        S_ = cai_dat.get()
        eff = S_.effective()
        self.source = cai_dat.SOURCE_LABEL.get(eff["source"], "") or "(không có)"
        url, token, org = eff["url"], eff["token"], eff["org"]
        cvat_io.register_secret(token)
        warn = ""
        if self.o.url:
            if eff["url"] and token and cvat_io.norm_url(self.o.url) != cvat_io.norm_url(eff["url"]):
                warn = (f" CẢNH BÁO: token lấy từ nguồn '{self.source}' (link {cvat_io.norm_url(eff['url'])}) sẽ được gửi tới "
                        f"{cvat_io.norm_url(self.o.url)} vì --url.")
                self.say(warn.strip())
            url = self.o.url
        if self.o.org:
            org = self.o.org
        chk = cai_dat.check_url(url)
        env = dict(url=chk["url"] if chk["ok"] else (url or ""), token=token, org=(org or "").strip())
        if self.o.dry_run and (not env["url"] or not env["token"]):
            self.env = env
            return BO, "chạy thử (--dry-run) và chưa có link/token: chỉ kiểm cục bộ, không gọi mạng."
        bad = cvat_io.env_problem(env)
        if not bad and not chk["ok"]:
            bad = chk["error"]
        if not bad:
            _t, why = cai_dat.check_token(token)
            bad = why
        if not bad:
            _o, bad = cai_dat.check_org(env["org"])
        if bad:
            if not env["url"] or not env["token"]:
                bad += (" Hoặc mở trang rà soát, bấm nút CVAT ở đầu trang, nhập link và token, TICK \"Nhớ trên máy này\" rồi Save: lệnh này chạy ở "
                        "tiến trình riêng nên không thấy token chỉ nhập trong phiên của trang.")
            return HONG, S(bad)
        self.env = env
        self.url = env["url"]
        if not self.o.dry_run:
            for k, v in (("CVAT_URL", env["url"]), ("CVAT_ACCESS_TOKEN", env["token"]), ("CVAT_ORG", env["org"])):
                self.old_environ.setdefault(k, os.environ.get(k))
                if v:
                    os.environ[k] = v
                else:
                    os.environ.pop(k, None)
        extra = f" {chk['warning']}" if chk.get("warning") else ""
        return DAT, f"link {env['url']}; nguồn: {self.source}; token: có" + (f"; tổ chức {env['org']}" if env["org"] else "") + "." + warn + extra

    # --- bước 4 ---
    def s4(self):
        want = self.pipe["cvat_version"]
        with contextlib.redirect_stdout(_Tee(self.out)):          # dòng "Lưu ý: server … mới hơn" của check_version in cùng chỗ (đã lọc token)
            res = cai_dat_thu.check(self.env, want, self.pipe["project"], probe_timeout=float(self.o.timeout))
        self.server_version, self.username = res["server_version"], res["username"]
        if not res["ok"]:
            return HONG, f"{KIND_VI.get(res['error_kind'], 'lỗi khác')}: {res['message']}"
        got = cvat_io._mm(self.server_version)
        if got not in cvat_io.ban_chap_nhan(want):                # đúng tập bản mà check_version của push/collect nhận
            return HONG, (f"server là bản {self.server_version}; với cvat_version {want} của config\\pipeline.json, push/collect chỉ nhận {ban_text(want)}: "
                          "dùng đúng CVAT của nhóm.")
        sdk = sdk_version()
        mm = cvat_io._mm(want)
        newer = (f" (mới hơn cvat_version {want} của config\\pipeline.json một bậc minor: cvat-sdk {mm[0]}.{mm[1]} khai hỗ trợ bản này nên được nhận, "
                 "push/collect chạy như với bản cùng minor; cả đội nên dùng cùng một bản CVAT)") if got != mm else ""
        return DAT, (f"server CVAT {self.server_version}{newer}, cvat-sdk {sdk}, tài khoản {self.username or '?'}"
                     + (f", tổ chức {self.env['org']}" if self.env["org"] else ", không dùng tổ chức") + ".")

    # --- bước 5 ---
    def s5(self):
        client = self.get_client()
        name = self.project_name
        existed = push.find_project(client, name) is not None
        self.project_existed = existed
        try:
            self.project_id = push.get_project_id(client, name, self.labels, self.names)
        except BaseException as e:
            p = push.find_project(client, name) if not existed else None
            if p is not None:                               # tạo xong rồi mới hỏng ở khâu kiểm: vẫn là project của lần chạy này
                self.project_created, self.project_id = True, p.id
            if existed and isinstance(e, SystemExit) and isinstance(e.code, str):
                raise SystemExit(e.code + " (Project có sẵn: tool KHÔNG sửa, KHÔNG xoá nó.)")
            raise
        self.project_created = not existed
        project = client.projects.retrieve(self.project_id)           # đọc lại từ server
        labels = list(project.get_labels())
        top = [lb for lb in labels if _text(push._lget(lb, "type")) == "skeleton"]
        want = {lb["name"]: [s["name"] for s in lb["sublabels"]] for lb in self.labels}
        keep = "" if self.project_created else " (project có sẵn: KHÔNG sửa, KHÔNG xoá)."
        got_labels = [push._lget(lb, "name") for lb in top]
        if sorted(got_labels) != sorted(want):
            return HONG, f"project {name} có label skeleton {got_labels} (cần đúng {list(want)}, mỗi nhóm một)" + keep, None
        bad = []
        if got_labels != list(want):
            bad.append("thứ tự LABEL khác config (CVAT liệt kê label theo thứ tự này trong 'Draw new skeleton'; collect đọc theo tên nên dữ liệu không hỏng: báo P4)")
        for lb in top:
            g = push._lget(lb, "name")
            subs = push._lget(lb, "sublabels") or [s for s in labels if push._lget(s, "has_parent") and push._lget(s, "parent_id") == push._lget(lb, "id")]
            got = [push._lget(s, "name") for s in subs]
            if len(got) != len(want[g]):
                bad.append(f"{g}: có {len(got)} sublabel (cần {len(want[g])})")
            elif got != want[g]:
                bad.append(f"{g}: tên đủ nhưng THỨ TỰ sublabel khác config (collect đọc theo tên nên dữ liệu không hỏng, nhưng CVAT hiển thị khác: báo P4)"
                           if sorted(got) == sorted(want[g]) else f"{g}: tên sublabel khác config ({len(set(want[g]) - set(got))} tên thiếu)")
            no_low = [push._lget(s, "name") for s in subs if not any(
                push._lget(a, "name") == "low_conf" and _text(push._lget(a, "input_type")) == "checkbox" for a in (push._lget(s, "attributes") or []))]
            if no_low:
                bad.append(f"{g}: {len(no_low)} sublabel không có thuộc tính low_conf kiểu checkbox (ví dụ {no_low[:2]})")
            cfg_g = set(cvat_io.groups_from_names(self.names).get(g, ()))           # tên config của nhóm; sublabel trên server có thể là số 1..50 (kiểu so)
            sub_of = cvat_io.ten_so(self.names) if cvat_io.kieu_labels(self.labels) == cvat_io.KIEU_SO else {n: n for n in self.names}
            gedges = {frozenset(sub_of[x] for x in e) for e in self.want_edges if e <= cfg_g}
            bad += [f"{g}: {b}" for b in check_svg(push._lget(lb, "svg"), {push._lget(s, "id"): push._lget(s, "name") for s in subs if push._lget(s, "id") is not None},
                                                 want[g], gedges)]
        if bad:
            return HONG, "label trên server sai: " + "; ".join(bad[:5]) + keep, None
        return DAT, (f"project {name} id {self.project_id} " + ("TẠO MỚI lần này" if self.project_created else "có sẵn")
                     + f"; server nhận {len(top)} label skeleton ({', '.join(got_labels)}): 50 sublabel đúng tên và thứ tự, low_conf checkbox, {len(self.want_edges)} cạnh đúng cặp.")

    # --- bước 6 ---
    def s6(self):
        client = self.get_client()
        notes = []
        if os.path.exists(self.marker_path):
            try:
                with open(self.marker_path, encoding="utf-8") as f:
                    mk = json.load(f)
                assert isinstance(mk, dict) and mk.get("tool") == "cvat_smoke" and mk.get("task") == TASK
                run = str(mk["run"])
                assert re.fullmatch(r"\d{8}_\d{6}(_\d+)?", run)
            except (OSError, ValueError, KeyError, AssertionError):
                return HONG, f"{MARKER} hỏng hoặc không phải của tool này: mở {self.marker_path} xem, xoá tay nếu đã dọn task trong CVAT."
            if cvat_io.norm_url(mk.get("cvat_url")) != cvat_io.norm_url(self.env["url"]):
                return HONG, (f"còn đánh dấu task dở ở CVAT khác ({mk.get('cvat_url')}): không đụng. Chạy lại với link đó để dọn, "
                              f"hoặc xoá {MARKER} nếu đã dọn tay.")
            old = os.path.join(self.smoke_root, run)
            if os.path.exists(push.pj_path(old)):
                tee = _Tee(types.SimpleNamespace(write=lambda s: None, flush=lambda: None))
                with contextlib.redirect_stdout(tee):
                    push.delete_task(old, confirm_name=TASK, prefix=cvat_io.SAFE_PREFIX, project=self.project_name, pipeline=self.pipe_smoke)
                notes.append(f"đã dọn task {TASK} id {mk.get('task_id')} còn dở từ lần trước")
            elif mk.get("task_id") is None:
                notes.append("lần trước dừng trước khi tạo task (không có gì để dọn)")
            else:
                return HONG, (f"{MARKER} ghi task id {mk.get('task_id')} nhưng không còn {os.path.join('runs', SMOKE_DIR, run, 'push.json')}: xoá task đó "
                              f"trong giao diện CVAT ({cvat_io.task_url(self.env['url'], mk.get('task_id'))}) rồi xoá {MARKER}.")
            self.drop_marker()
        tasks = list(client.tasks.list())
        same = [t for t in tasks if t.name == TASK]
        if same:
            return HONG, (f"trên CVAT có {len(same)} task tên {TASK} (id {[t.id for t in same][:3]}) mà tool không có dấu hiệu đã tạo: KHÔNG xoá. "
                          f"Tự xoá trong giao diện CVAT ({cvat_io.task_url(self.env['url'], same[0].id)}) rồi chạy lại.")
        self.baseline = sorted((t.id, t.name, t.project_id) for t in tasks)
        return DAT, ("; ".join(notes) + "; " if notes else "") + f"không có task {TASK} nào; ghi nhận {len(self.baseline)} task khác để đối chiếu cuối bài."

    # --- bước 7-9 ---
    def read_pj(self):
        try:
            return push.read_state(self.run_dir)
        except SystemExit:
            return None

    def s7(self):
        os.makedirs(self.run_dir, exist_ok=True)
        self.write_marker()                                 # trước khi push: chết giữa chừng vẫn biết có thể còn task
        tee = _Tee(self.out)
        err = None
        with contextlib.redirect_stdout(tee):
            try:
                push.push(self.run_dir, TASK, self.nhan_imgs, self.tay_imgs, self.xml, project=self.project_name, prefix=cvat_io.SAFE_PREFIX,
                          label_json=self.label_json, pipeline=self.pipe_smoke)
            except SystemExit as e:
                err = S(e.code) if isinstance(e.code, str) else f"dừng (mã {e.code})"
        self.push_out = tee.text()
        self.pj = self.read_pj() or {}
        if isinstance(self.pj.get("task_id"), int):
            self.task_id = self.pj["task_id"]
            self.write_marker()
        phases = re.findall(r"^\[(\d)/6\] ([^:]+):", self.push_out, re.M)
        last = f"pha {phases[-1][0]}/6 ({phases[-1][1]})" if phases else "trước pha 1"
        self.push_err = err
        if self.task_id is None:
            return HONG, f"push dừng ở {last}, chưa có task: {err or 'không rõ lý do'}"
        want_groups, want_kinds = push.plan_jobs(self.nhan_imgs, self.tay_imgs, 1)
        want = [(k, len(g)) for k, g in zip(want_kinds, want_groups)]
        got = [(j["kind"], j["n"]) for j in self.pj.get("jobs", [])]
        bad = []
        if got != want:
            bad.append(f"job trên server {got} khác kế hoạch {want} (job_file_mapping)")
        frames = push._frame_names(self.get_client().tasks.retrieve(self.task_id))
        flat = [n for g in want_groups for n in g]
        if frames != flat:
            bad.append(f"thứ tự frame trên server {frames} khác thứ tự đã tải {flat}")
        if self.pj.get("canh_bao"):
            bad.append(str(self.pj["canh_bao"][0]))
        if bad:
            return HONG, f"task id {self.task_id}: " + "; ".join(bad)
        return DAT, f"task {TASK} id {self.task_id}: {len(got)} job {got} đúng kế hoạch, {len(frames)} frame đúng thứ tự (Nhận trước, Sửa nhãn sau)."

    def s8(self):
        st = (self.pj or {}).get("trang_thai")
        n = len(re.findall(r"^\[5/6\] nhập nhãn: nhập \d+ Nhận", self.push_out, re.M))
        if st in (push.S_DA_NHAP, push.S_XONG) and n == 1:
            return DAT, "push.json qua da_nhap; XML nháp nhập 1 lần theo log của push (CVAT thật không cho đếm lời gọi)."
        if st in (push.S_DA_NHAP, push.S_XONG):
            return HONG, f"push.json qua da_nhap nhưng log ghi {n} lần nhập (cần đúng 1)."
        return HONG, f"nhập XML nháp lỗi (push.json: {st}): {self.push_err or (self.pj or {}).get('loi') or 'không rõ'}"

    def s9(self):
        sub, bad = [], []
        chk = (self.pj or {}).get("check")
        if not chk:
            bad.append("push chưa xuất kiểm xong" + (f": {self.push_err}" if self.push_err else ""))
        elif not chk.get("ok"):
            bad.append(f"push tự kiểm KHÔNG đạt: {self.push_err or chk}")
        else:
            sub.append(f"push tự kiểm: {chk['n_day_du']}/{chk['n_nhan']} mặt Nhận đủ điểm, {chk['n_tay_nhap_day_du']}/{chk['n_tay_nhap']} Sửa nhãn có nháp "
                       "đủ điểm kèm low_conf, Sửa nhãn trống không có nhãn")
        args = self.collect_args()
        from m28core import collect
        cwd = os.getcwd()
        tee = _Tee(self.out)
        os.chdir(self.run_dir)                                # collect ghi raw/ và outputs/ tương đối thư mục chạy: giữ trong runs\_smoke
        try:
            with contextlib.redirect_stdout(tee):
                collect.collect(args)
        finally:
            os.chdir(cwd)
        raw_dir = os.path.join(self.run_dir, "raw", TASK)                  # collect ghi vào raw/<task>/ (mỗi task một thư mục)
        names_raw = os.listdir(raw_dir) if os.path.isdir(raw_dir) else []
        raws = [p for p in names_raw if p.startswith(f"{TASK}_{REVIEWER}_") and collect.RAW_RE.match(p)]      # file cả task; file _job<id> không tính
        if len(raws) != 1:
            return HONG, f"collect không ghi đúng 1 file raw (thấy {raws}); " + "; ".join(bad)
        xml_path = os.path.join(raw_dir, raws[0])
        with open(xml_path, "rb") as f:
            data = f.read()
        ann = cvat_io.parse_annotations(data, self.names)
        probs, worst = compare_ann(ann, self.expect, self.names)
        bad += probs
        st = collect.analyze(data, self.names)
        if (st["n_images"], st["n_face"], st["n_full"], st["n_missing"]) != (len(IMAGES), 3, 3, 0):
            bad.append(f"collect.analyze: {st['n_images']} ảnh, {st['n_face']} mặt, {st['n_full']} đủ điểm, {st['n_missing']} điểm thiếu (cần 4, 3, 3, 0)")
        jobs = collect._jobs_from_txt(xml_path[:-4] + ".txt")
        want_jobs = [1, 1, 2]
        if jobs is None or [j["n"] for j in jobs] != want_jobs:
            bad.append(f"file .txt của collect ghi job {jobs and [j['n'] for j in jobs]} (cần {want_jobs} frame)")
        bad += self.s9_jobs(raw_dir, names_raw, raws[0], jobs, want_jobs)
        if not os.path.exists(os.path.join(self.run_dir, "outputs", f"collect_{TASK}.md")):
            bad.append(f"collect không ghi outputs\\collect_{TASK}.md")
        bad_co, sub_co = self.s9_flags(raw_dir, raws[0], jobs) if jobs else ([], [])     # sau mọi kiểm ở trên: --overwrite dời file cũ
        if bad or bad_co:
            parts = (["nhãn xuất ra khác nhãn đã nhập: " + "; ".join(bad)] if bad else []) + \
                    (["cờ collect của nút Merge jobs & Finish: " + "; ".join(bad_co)] if bad_co else [])
            return HONG, "; ".join(parts), sub + sub_co
        sub.append(f"collect ghi {raws[0]} (+ .txt, {len(jobs)} job) và báo cáo collect_{TASK}.md")
        sub.append(f"tách theo job (offline, từ file cả task): {len(jobs)} file _job<id>.xml với số ảnh {want_jobs}, job cuối chứa đúng ảnh Sửa nhãn; "
                   "id ảnh trong file xuất = số frame trong task (giả định của tach_job)")
        return DAT, (f"3 mặt x 50 điểm đúng tên, đúng thứ tự, low_conf giữ nguyên, sai số toạ độ lớn nhất {worst:.3f}px (cho phép {TOL_PX}), "
                     "kích thước và tên ảnh khớp, Sửa nhãn trống không có nhãn."), sub + sub_co

    def collect_args(self, **flags):
        """Đối số của collect.collect cho task demo-smoke (giống m28.py collect --task demo-smoke --reviewer SMOKE), thêm cờ theo flags."""
        d = dict(task=[TASK], reviewer=REVIEWER, skip_export=False, dry_run=False, pipeline=self.pipe_smoke,
                 config=os.path.join(self.root, "config", "m28_config.json"), tag=None)
        d.update(flags)
        return types.SimpleNamespace(**d)

    def collect_quiet(self, **flags):
        """Chạy collect.collect trong runs\\_smoke\\<giờ> với cờ, không in ra màn hình (giữ chữ để đọc dòng máy đọc). Trả (mã SystemExit | None, chữ)."""
        from m28core import collect
        tee = _Tee(types.SimpleNamespace(write=lambda s: None, flush=lambda: None))
        cwd, code = os.getcwd(), None
        os.chdir(self.run_dir)
        try:
            with contextlib.redirect_stdout(tee):
                collect.collect(self.collect_args(**flags))
        except SystemExit as e:
            code = e.code if e.code is not None else 0
        finally:
            os.chdir(cwd)
        return code, tee.text()

    @staticmethod
    def machine_lines(text, prefix):
        """Các dòng `<prefix>{JSON}` của collect: dict, hoặc None cho dòng JSON hỏng."""
        out = []
        for ln in text.splitlines():
            if ln.startswith(prefix):
                try:
                    d = json.loads(ln[len(prefix):])
                except ValueError:
                    d = None
                out.append(d if isinstance(d, dict) else None)
        return out

    @staticmethod
    def job_text_problems(jobs, tag):
        """Job trong dòng máy đọc phải có state/stage/type là CHỮ THƯỜNG của CVAT (không phải repr của enum SDK), loại annotation, chưa completed."""
        if not isinstance(jobs, list) or not jobs:
            return [f"{tag} dòng máy đọc không có danh sách job"]
        bad = []
        for j in jobs:
            if not isinstance(j, dict):
                bad.append(f"{tag} job không phải đối tượng JSON: {j!r}")
                continue
            st, sg, ty = j.get("state"), j.get("stage"), j.get("type")
            if not isinstance(st, str) or st not in JOB_STATES or not isinstance(sg, str) or sg not in JOB_STAGES:
                bad.append(f"{tag} job {j.get('id')}: state {st!r} / stage {sg!r} không phải chữ thường của CVAT ({'/'.join(JOB_STATES)})")
            elif st == "completed":
                bad.append(f"{tag} job {j.get('id')} của task smoke lại ở state completed (smoke không bấm Finish the job)")
            if ty != "annotation":
                bad.append(f"{tag} job {j.get('id')}: type {ty!r} (cần 'annotation')")
        return bad[:6]

    def s9_flags(self, raw_dir, xml_name, jobs):
        """Hai cờ của collect mà nút Merge jobs & Finish dùng, thử trên CVAT THẬT (chỉ tasks.list, get_jobs, export_dataset như collect thường):
        (a) --require-completed khi job còn mới: thoát mã 3 (EXIT_CHUA_XONG), không ghi/đổi file nào trong raw\\ và outputs\\, đúng 1 dòng
            COLLECT_JOBS_PENDING là JSON hợp lệ liệt kê đủ job;
        (b) --overwrite: xuất lại; bản cũ (.xml, .txt, file job) chuyển vào raw\\_cu (bản .xml cũ còn nguyên byte), bản mới ghi đúng chỗ và khớp nhãn
            đã nhập; dòng COLLECT_XML moi=true có state/stage/type của job là chữ thường (ví dụ new).
        Trả (danh sách vấn đề, các dòng con)."""
        from m28core import collect
        bad, sub = [], []
        ids = sorted(j["id"] for j in jobs)
        stem = xml_name[:-4]
        xml_path = os.path.join(raw_dir, xml_name)
        cu_dir = os.path.join(os.path.dirname(raw_dir), collect.CU)       # bản cũ chuyển vào raw/_cu/ (chung cho mọi task)

        def snap():
            out = []
            for d in ("raw", "outputs"):
                for dp, _dn, fn in os.walk(os.path.join(self.run_dir, d)):
                    for f in fn:
                        st = os.stat(os.path.join(dp, f))
                        out.append((os.path.relpath(os.path.join(dp, f), self.run_dir), st.st_size, st.st_mtime_ns))
            return sorted(out)

        def why(code):
            return "collect chạy hết, không chặn" if code is None else f"collect dừng: {S(code)[:200]}" if isinstance(code, str) else f"collect thoát mã {code}"

        # (a) --require-completed
        before = snap()
        code, text = self.collect_quiet(require_completed=True)
        pend = self.machine_lines(text, collect.DONG_CHUA_XONG)
        if code != collect.EXIT_CHUA_XONG:
            bad.append(f"(a) --require-completed khi job còn mới: {why(code)} (cần thoát mã {collect.EXIT_CHUA_XONG})")
        elif snap() != before:
            bad.append("(a) --require-completed đã chặn nhưng vẫn ghi hoặc đổi file trong raw\\ hay outputs\\")
        elif len(pend) != 1 or pend[0] is None or pend[0].get("task") != TASK:
            bad.append(f"(a) cần đúng 1 dòng {collect.DONG_CHUA_XONG.rstrip(": ")} JSON hợp lệ của {TASK}, thấy {len(pend)} dòng")
        elif sorted(i for i in (pend[0].get("pending") if isinstance(pend[0].get("pending"), list) else []) if isinstance(i, int)) != ids:
            bad.append(f"(a) pending {pend[0].get('pending')} khác các job của task {ids} (job mới đều chưa completed)")
        else:
            probs = self.job_text_problems(pend[0].get("jobs"), "(a)")
            bad += probs
            if not probs:
                sub.append(f"(a) --require-completed: {len(ids)} job chưa completed nên thoát mã {collect.EXIT_CHUA_XONG}, không ghi file nào; "
                           f"dòng {collect.DONG_CHUA_XONG.rstrip(": ")} liệt kê đủ job (state {', '.join(j['state'] for j in pend[0]['jobs'])})")
        # (b) --overwrite
        with open(xml_path, "rb") as f:
            old_data = f.read()
        olds = sorted(p for p in os.listdir(raw_dir) if p in (xml_name, stem + ".txt") or p.startswith(stem + "_job"))
        cu_before = set(os.listdir(cu_dir)) if os.path.isdir(cu_dir) else set()
        code, text = self.collect_quiet(overwrite=True)
        if code is not None:
            bad.append(f"(b) --overwrite: {why(code)}")
            return bad, sub
        cu_new = sorted(set(os.listdir(cu_dir)) - cu_before) if os.path.isdir(cu_dir) else []

        def moved(p):
            s, e = os.path.splitext(p)
            return [q for q in cu_new if re.fullmatch(re.escape(s) + r"\.cu\d{6}(-\d+)?" + re.escape(e), q)]
        not_moved = [p for p in olds if len(moved(p)) != 1]
        if not_moved:
            bad.append(f"(b) --overwrite không chuyển {not_moved} vào raw\\_cu (mới thấy trong raw\\_cu: {cu_new[:6]})")
        else:
            with open(os.path.join(cu_dir, moved(xml_name)[0]), "rb") as f:
                if f.read() != old_data:
                    bad.append(f"(b) bản cũ trong raw\\_cu ({moved(xml_name)[0]}) không còn nguyên byte như {xml_name}")
        if not os.path.isfile(xml_path) or not os.path.isfile(xml_path[:-4] + ".txt"):
            bad.append(f"(b) --overwrite không ghi lại {xml_name} (+ .txt) sau khi dời bản cũ")
        else:
            with open(xml_path, "rb") as f:
                probs, _w = compare_ann(cvat_io.parse_annotations(f.read(), self.names), self.expect, self.names)
            bad += [f"(b) bản xuất lại: {p}" for p in probs]
            txt_jobs = collect._jobs_from_txt(xml_path[:-4] + ".txt") or []          # .txt chỉ giữ từ đầu của state ("in progress" -> "in")
            if sorted(j["id"] for j in txt_jobs) != ids or any(not re.fullmatch(r"[a-z][a-z ]*", j["state"]) for j in txt_jobs):
                bad.append(f"(b) .txt mới ghi job {[(j['id'], j['state']) for j in txt_jobs]} (cần job {ids}, state là chữ thường của CVAT)")
        lines = [d for d in self.machine_lines(text, collect.DONG_XML) if d is None or (d.get("task") == TASK and d.get("nguoi") == REVIEWER)]
        if len(lines) != 1 or lines[0] is None or lines[0].get("moi") is not True or lines[0].get("xml") != f"raw/{TASK}/{xml_name}":
            bad.append(f"(b) cần đúng 1 dòng {collect.DONG_XML.rstrip(": ")} JSON hợp lệ với moi=true và xml=raw/{TASK}/{xml_name} (thấy "
                       f"{[d and (d.get('xml'), d.get('moi')) for d in lines]}; nếu vừa qua nửa đêm thì chạy lại)")
        else:
            got = lines[0].get("jobs")
            probs = self.job_text_problems(got, "(b)")
            got_ids = sorted(j["id"] for j in got if isinstance(j, dict) and isinstance(j.get("id"), int)) if isinstance(got, list) else None
            if not probs and got_ids != ids:
                probs.append(f"(b) jobs của dòng {collect.DONG_XML.rstrip(": ")} ({got_ids}) khác các job của task {ids}")
            bad += probs
            if not probs and not not_moved:
                sub.append(f"(b) --overwrite: xuất lại; bản cũ ({len(olds)} file: .xml, .txt, file job) chuyển vào raw\\_cu còn nguyên, bản mới ghi lại "
                           f"đúng chỗ và khớp nhãn đã nhập; dòng {collect.DONG_XML.rstrip(": ")} moi=true, job đọc về dạng chữ: "
                           + ", ".join(f"{j['id']} {j['stage']}/{j['state']}/{j['type']}" for j in got))
        return bad, sub

    def s9_jobs(self, raw_dir, names_raw, xml_name, jobs, want_jobs):
        """Kiểm file job do collect tách (mặc định bật cho demo-…): đúng số file, số ảnh [1, 1, 2], job cuối chứa đúng ảnh Sửa nhãn, id ảnh = số frame của task.
        Đây là chỗ duy nhất kiểm được giả định 'id ảnh trong file xuất = số frame trong task' trên CVAT THẬT. Trả danh sách vấn đề."""
        from m28core import tach_job
        bad = []
        if not jobs or len(jobs) != len(want_jobs):
            return bad                                                  # lỗi job đã báo ở trên
        stem = xml_name[:-4]
        files = [f"{stem}_job{j['id']}.xml" for j in jobs]
        extra = sorted(p for p in names_raw if tach_job.JOB_RE.match(p) and p.startswith(stem + "_job") and p not in files)
        absent = [f for f in files if f not in names_raw]
        if absent or extra:
            return [f"tách job: thiếu file {absent} hoặc thừa file {extra} (cần đúng {len(jobs)} file _job<id>.xml)"]
        tay = {n for n, _s, r in IMAGES if r != "nhan"}

        def names_in(fname):
            with open(os.path.join(raw_dir, fname), "rb") as fh:
                return sorted(cvat_io.parse_annotations(fh.read()))

        joined = []
        for j, f, want_n in zip(jobs, files, want_jobs):
            names = names_in(f)
            joined += names
            last = j is jobs[-1]
            if len(names) != want_n:
                bad.append(f"tách job: {f} có {len(names)} ảnh (cần {want_n})")
            elif last and set(names) != tay:
                bad.append(f"tách job: job cuối ({f}) phải chứa đúng ảnh Sửa nhãn {sorted(tay)}, thấy {names}")
            elif not last and set(names) & tay:
                bad.append(f"tách job: {f} (job Nhận) lại chứa ảnh Sửa nhãn {sorted(set(names) & tay)}")
        whole = names_in(xml_name)
        if sorted(joined) != whole:
            bad.append(f"tách job: gộp các file job ({len(joined)} ảnh) khác file cả task ({len(whole)} ảnh)")
        return bad

    # --- bước 10 ---
    def others_now(self):
        return sorted((t.id, t.name, t.project_id) for t in self.get_client().tasks.list() if t.name != TASK)

    def s10(self):
        sub, bad = [], []
        client = self.get_client()
        n_before = sum(1 for t in client.tasks.list() if t.name == TASK)
        sink = _Tee(types.SimpleNamespace(write=lambda s: None, flush=lambda: None))
        try:                                                  # (a) push lần hai trên cùng lượt
            with contextlib.redirect_stdout(sink):
                push.push(self.run_dir, TASK, self.nhan_imgs, self.tay_imgs, self.xml, project=self.project_name, prefix=cvat_io.SAFE_PREFIX,
                          label_json=self.label_json, pipeline=self.pipe_smoke)
            bad.append("(a) push lần hai trên cùng lượt KHÔNG bị từ chối")
        except SystemExit:
            n_after = sum(1 for t in client.tasks.list() if t.name == TASK)
            if n_after != n_before or n_after != 1:
                bad.append(f"(a) push lần hai bị từ chối nhưng số task {TASK} là {n_after} (cần 1)")
            else:
                sub.append("(a) push lần hai trên cùng lượt bị từ chối, vẫn đúng 1 task demo-smoke")
        try:                                                  # (b) tên không có prefix demo-
            push.check_task_name("m28-smoke", cvat_io.SAFE_PREFIX)
            bad.append("(b) check_task_name chấp nhận m28-smoke")
        except SystemExit:
            tmp = os.path.join(self.run_dir, "kiem_prefix")
            try:
                with contextlib.redirect_stdout(sink):
                    push.push(tmp, "smoke-khong-prefix", self.nhan_imgs, self.tay_imgs, self.xml, project=self.project_name,
                              prefix=cvat_io.SAFE_PREFIX, label_json=self.label_json, pipeline=self.pipe_smoke)
                bad.append("(b) push với tên không prefix KHÔNG bị từ chối")
            except SystemExit:
                if os.path.exists(push.pj_path(tmp)) or any(t.name == "smoke-khong-prefix" for t in client.tasks.list()):
                    bad.append("(b) tên không prefix bị từ chối nhưng đã có push.json hoặc task mới")
                else:
                    sub.append("(b) m28-smoke và smoke-khong-prefix bị từ chối trước khi kết nối: không push.json, không task mới")
        if self.baseline is not None:                          # (c) task khác nguyên vẹn (kiểm lại sau bước 11)
            if self.others_now() != [b for b in self.baseline]:
                bad.append("(c) danh sách task khác đã thay đổi so với trước bước 6")
            else:
                sub.append(f"(c) {len(self.baseline)} task khác giống hệt trước bước 6 (kiểm lại sau bước 11)")
        if bad:
            return HONG, "; ".join(bad), sub
        return DAT, "mọi lớp bảo vệ chạy đúng.", sub

    # --- bước 11, 12 (dọn dẹp, luôn chạy) ---
    def s11(self):
        if self.task_id is None:
            return BO, "chưa tạo task nào nên không có gì để xoá."
        link = cvat_io.task_url(self.env["url"], self.task_id)
        if self.o.giu_task:
            return BO, (f"--giu-task: giữ task {TASK} id {self.task_id} để xem bằng mắt: {link}. Lần chạy sau tự dọn; hoặc xoá tay trong CVAT "
                        f"(file {MARKER} giữ lại).")
        sink = _Tee(types.SimpleNamespace(write=lambda s: None, flush=lambda: None))
        try:
            with contextlib.redirect_stdout(sink):
                push.delete_task(self.run_dir, confirm_name=TASK, prefix=cvat_io.SAFE_PREFIX, project=self.project_name, pipeline=self.pipe_smoke)
        except SystemExit as e:
            return HONG, f"không xoá được task id {self.task_id}: {S(e.code)} Tự xoá ở {link}; {MARKER} giữ lại, lần chạy sau sẽ thử dọn lại."
        try:
            self.get_client().tasks.retrieve(self.task_id)
            return HONG, f"đã gọi xoá nhưng task id {self.task_id} vẫn còn trên server: {link}"
        except Exception as e:                                  # noqa: BLE001
            if getattr(e, "status", None) != 404:
                return HONG, f"không kiểm được task đã mất chưa: {self.explain(e, 'kiểm task đã xoá')}"
        self.task_deleted = True
        self.drop_marker()
        if self.baseline is not None and self.others_now() != self.baseline:
            if 10 in self.by and self.by[10]["ket_qua"] == DAT:
                self.by[10].update(ket_qua=HONG, ghi_chu="(c) danh sách task khác đã thay đổi sau khi xoá demo-smoke: " + self.by[10]["ghi_chu"])
            return HONG, f"task id {self.task_id} đã xoá (retrieve trả 404) NHƯNG danh sách task khác thay đổi so với trước bước 6: kiểm lại trên CVAT."
        return DAT, f"đã xoá task id {self.task_id} (kiểm theo id, tên, project, link) và retrieve trả 404; task khác nguyên vẹn."

    def s12(self):
        if not self.project_created and not self.project_existed:
            return BO, "không có project nào được tạo hay đụng tới."
        name = self.project_name
        if not self.project_created:
            self.project_note = "giữ nguyên (có từ trước)"
            return DAT, f"project {name} {self.project_note}."
        if self.o.giu_project:
            self.project_note = "giữ theo --giu-project"
            return BO, f"đã tạo project {name} (id {self.project_id}) trong lần chạy này, giữ theo --giu-project."
        client = self.get_client()
        try:
            proj = client.projects.retrieve(self.project_id)
        except Exception as e:                                  # noqa: BLE001
            if getattr(e, "status", None) == 404:
                self.project_note = "đã mất sẵn"
                return DAT, f"project {name} id {self.project_id} không còn trên server."
            raise
        left = list(proj.get_tasks())
        if proj.name != name or left:
            self.project_note = "giữ lại (còn task)" if left else "giữ lại (tên không khớp)"
            return DAT, (f"project {name} (id {self.project_id}) do lần chạy này tạo, GIỮ LẠI vì "
                         + (f"còn {len(left)} task trong đó" if left else f"tên trên server là {proj.name!r}") + " (không xoá project có task).")
        proj.remove()
        try:
            client.projects.retrieve(self.project_id)
            return HONG, f"đã gọi xoá project {name} id {self.project_id} nhưng nó vẫn còn trên server."
        except Exception as e:                                  # noqa: BLE001
            if getattr(e, "status", None) != 404:
                raise
        self.project_note = "đã xoá (do lần này tạo, đang rỗng)"
        return DAT, f"đã xoá project {name} id {self.project_id} (do lần chạy này tạo, đang rỗng). Project có sẵn của bạn không bị đụng."

    def cleanup(self):
        for code, fn in ((11, self.s11), (12, self.s12)):
            if self.o.dry_run:
                self.record(code, BO, "chạy thử (--dry-run): không gọi mạng")
                continue
            self.interrupted = False                            # dọn dẹp luôn chạy, kể cả sau Ctrl+C
            self.run_step(code, fn)


def sdk_version():
    try:
        return importlib.metadata.version("cvat-sdk")
    except importlib.metadata.PackageNotFoundError:
        return str(getattr(sys.modules.get("cvat_sdk"), "__version__", "không rõ"))


def scrub_obj(o):
    if isinstance(o, str):
        return S(o)
    if isinstance(o, dict):
        return {k: scrub_obj(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [scrub_obj(v) for v in o]
    return o


def table(sm):
    rows = [(f"{r['ma']}. {r['ten']}", r["ket_qua"], r["ghi_chu"]) for r in sorted(sm.res, key=lambda r: r["ma"])]
    w1, w2 = max(len("Bước"), *(len(r[0]) for r in rows)), max(len("Kết quả"), *(len(r[1]) for r in rows))
    lines = [f"{'Bước'.ljust(w1)} | {'Kết quả'.ljust(w2)} | Ghi chú", f"{'-' * w1}-+-{'-' * w2}-+-{'-' * 20}"]
    for (a, b, c), r in zip(rows, sorted(sm.res, key=lambda r: r["ma"])):
        lines.append(f"{a.ljust(w1)} | {b.ljust(w2)} | {c}")
        lines += [f"{' ' * w1} | {' ' * w2} |   - {x}" for x in r["con"]]
    return lines


def write_report(sm, started, code):
    """Ghi bao_cao_<giờ>.txt/.json (không ghi đè), đọc lại kiểm không có token. Trả (đường dẫn json hoặc None, danh sách cảnh báo)."""
    n_bad = sum(1 for r in sm.res if r["ket_qua"] == HONG)
    rep = dict(
        thoi_gian=started.isoformat(timespec="seconds"), may=dict(he_dieu_hanh=platform.platform(), python=platform.python_version()),
        cvat_sdk=sdk_version(), cvat_url=cvat_io.norm_url(sm.env["url"]) if sm.env else "", nguon_token=sm.source,
        to_chuc=(sm.env or {}).get("org", ""), ban_server=sm.server_version, tai_khoan=sm.username,
        project=dict(ten=sm.project_name, co_san=sm.project_existed, da_tao_lan_nay=sm.project_created, id=sm.project_id, ket_cuc=sm.project_note),
        task_id=sm.task_id, task_da_xoa=sm.task_deleted,
        buoc=[dict(ma=r["ma"], ten=r["ten"], ket_qua=r["ket_qua"], ghi_chu=r["ghi_chu"], giay=r["giay"], con=r["con"]) for r in sorted(sm.res, key=lambda r: r["ma"])],
        co=dict(dry_run=sm.o.dry_run, url=bool(sm.o.url), org=bool(sm.o.org), giu_task=sm.o.giu_task, giu_project=sm.o.giu_project, timeout=sm.o.timeout),
        tong="Tất cả ĐẠT" if not n_bad else f"Có {n_bad} bước HỎNG", ma_thoat=code)
    rep = scrub_obj(rep)
    stamp = started.strftime("%Y%m%d_%H%M%S")
    base, k = os.path.join(sm.smoke_root, f"bao_cao_{stamp}"), 1
    while os.path.exists(base + ".json") or os.path.exists(base + ".txt"):
        k += 1
        base = os.path.join(sm.smoke_root, f"bao_cao_{stamp}_{k}")
    head = [f"Kiểm tra nhanh CVAT (cvat_smoke) lúc {rep['thoi_gian']}", f"Máy: {rep['may']['he_dieu_hanh']}; Python {rep['may']['python']}; cvat-sdk {rep['cvat_sdk']}",
            f"CVAT: {rep['cvat_url'] or '(chưa có)'}; nguồn token: {rep['nguon_token'] or '(không có)'}; tổ chức: {rep['to_chuc'] or '(không)'}; "
            f"bản server: {rep['ban_server'] or '?'}; tài khoản: {rep['tai_khoan'] or '?'}",
            f"Project {rep['project']['ten']}: " + (rep["project"]["ket_cuc"] or ("chưa chạm tới" if sm.project_existed is None else "")),
            f"Task id: {rep['task_id']}" + (" (đã xoá)" if sm.task_deleted else ""), ""]
    text = "\n".join(head + [S(x) for x in table(sm)] + ["", rep["tong"]]) + "\n"
    os.makedirs(sm.smoke_root, exist_ok=True)
    with open(base + ".txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    cvat_io.atomic_write_json(base + ".json", rep)
    secrets_ = {(sm.env or {}).get("token", ""), os.environ.get("CVAT_ACCESS_TOKEN", ""), *getattr(cvat_io, "_SECRETS", ())}
    secrets_ = {t for t in secrets_ if t and len(t) >= 4}
    for p in (base + ".txt", base + ".json"):
        with open(p, encoding="utf-8") as f:
            body = f.read()
        if any(t in body or json.dumps(t)[1:-1] in body for t in secrets_):
            for q in (base + ".txt", base + ".json"):
                os.remove(q)
            return None, ["báo cáo chứa token nên đã bị xoá (lỗi của công cụ, KHÔNG gửi gì)"]
    return base + ".json", []


def run(o, *, out=None):
    """Chạy bài kiểm tra. Trả (mã thoát, dict báo cáo). out: nơi in (mặc định sys.stdout lúc gọi; tránh gắn cứng lúc import để test bắt được)."""
    out = out or sys.stdout
    why = validate(o)
    if why:
        print(why, file=sys.stderr)
        return 2, {"loi": why}
    sm = Smoke(o, out)
    started = datetime.datetime.now().astimezone()
    old_timeout = socket.getdefaulttimeout()
    try:
        with dang_chay.Guard(sm.smoke_root, "smoke", "chạy lại kiểm tra nhanh"):
            socket.setdefaulttimeout(float(o.timeout))
            try:
                try:
                    sm.run_step(1, sm.s1)
                    sm.run_step(2, sm.s2, deps=(1,))
                    sm.run_step(3, sm.s3)
                    if o.dry_run:
                        for c in range(4, 11):
                            sm.run_step(c, lambda: (BO, ""))
                    else:
                        sm.run_step(4, sm.s4, deps=(1, 3))
                        sm.run_step(5, sm.s5, deps=(4,))
                        sm.run_step(6, sm.s6, deps=(5,))
                        sm.run_step(7, sm.s7, deps=(2, 6))
                        sm.run_step(8, sm.s8, deps=(7,))
                        sm.run_step(9, sm.s9, deps=(8,))
                        sm.run_step(10, sm.s10, deps=(7,))
                finally:
                    sm.cleanup()                                  # bước 11 và 12: luôn chạy
            finally:
                if sm.client is not None:
                    with contextlib.suppress(Exception):
                        sm.client.close()
                socket.setdefaulttimeout(old_timeout)
                for k, v in sm.old_environ.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
    except SystemExit as e:                                       # khoá runs\_smoke của lần chạy khác
        msg = S(e.code) if isinstance(e.code, str) else "không chạy được"
        print(msg, file=sys.stderr)
        return 1, {"loi": msg}
    n_bad = sum(1 for r in sm.res if r["ket_qua"] == HONG)
    code = 1 if n_bad else 0
    sm.say("")
    for ln in table(sm):
        sm.say(ln)
    sm.say("")
    sm.say("Tất cả ĐẠT" if not n_bad else f"Có {n_bad} bước HỎNG")
    json_path, warns = write_report(sm, started, code)
    for w in warns:
        sm.say("LỖI: " + w)
        code = 1
        n_bad = n_bad or 1
    if json_path:
        txt = json_path[:-5] + ".txt"
        if n_bad:
            sm.say(f"Gửi cho P4 file runs\\_smoke\\{os.path.basename(txt)} (không gửi token, không gửi ảnh)")
        sm.say(f"Báo cáo: {os.path.relpath(txt, sm.root)}")
        sm.say(f"SMOKE_JSON: {json_path}")
        with open(json_path, encoding="utf-8") as f:
            return code, json.load(f)
    return code, {}


def build_parser():
    ap = argparse.ArgumentParser(description="Kiểm tra nhanh CVAT thật: tạo task demo-smoke (ảnh xám giả), nhập nhãn, xuất lại, rồi xoá.")
    ap.add_argument("--dry-run", action="store_true", help="chỉ kiểm cục bộ (bước 1-3), không gọi mạng")
    ap.add_argument("--url", help="ghi đè link CVAT (token giữ nguyên nguồn)")
    ap.add_argument("--org", help="ghi đè tổ chức CVAT")
    ap.add_argument("--giu-task", action="store_true", help="không xoá task demo-smoke (để xem bằng mắt); lần chạy sau tự dọn")
    ap.add_argument("--giu-project", action="store_true", help="không xoá project m28 do lần chạy này tạo")
    ap.add_argument("--timeout", type=float, default=60, help="giây cho mỗi yêu cầu mạng (5-600, mặc định 60)")
    ap.add_argument("--root", default=None, help=argparse.SUPPRESS)          # thư mục m28-prelabel (chỉ test)
    return ap


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = build_parser()
    o = ap.parse_args(argv)
    why = validate(o)
    if why:
        ap.error(why)
    try:
        code, _rep = run(o)
    except KeyboardInterrupt:
        print("Đã ngắt.", file=sys.stderr)
        return 1
    except Exception:                                             # noqa: BLE001 - không bao giờ in traceback chưa lọc
        print(S(traceback.format_exc()), file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
