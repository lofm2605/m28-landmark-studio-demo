"""Tab "Lọc dữ liệu" của trang rà soát M28 (dựng theo mẫu ca_kho.member_tab): chọn tiêu chí, xem trước số lượng (= --dry-run, không ghi gì), lưu/nạp cấu hình, tạo bộ dữ liệu.

Chỉ CHUẨN BỊ dữ liệu cho một model landmark khác sau này: không train gì. Logic lọc, kiểm cấu hình, ghi gói nằm ở loc_du_lieu.py (cùng CLI); file này chỉ nối giao diện.
Quy ước (giống ca_kho.py):
  * Đầu module KHÔNG nạp gradio (nhận `gr`); không gọi mạng. Tab KHÔNG hiện ảnh mặt (chỉ số) nhưng có cảnh báo ảnh nhạy cảm ở đầu tab.
  * Chỉ ghi dưới outputs\\train_sets\\<tên>\\ (gói) và outputs\\<tên>.json (cấu hình lọc); tên và đường dẫn kiểm ở server; ghi đè bộ cũ cần xác nhận.
  * Handler: api_visibility="private", concurrency_id riêng, một lần ghi tại một thời điểm, từ chối khi trang đang đóng (ctx.closing), dùng được cả ở chế độ --nap.
"""
import html
import json
import os
import re
import sys
import threading

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import ca_kho  # noqa: E402  (_atomic_write)
import dot_anh  # noqa: E402
import loc_du_lieu as ld  # noqa: E402
import nap_anh  # noqa: E402
import thong_ke_ui  # noqa: E402
from m28core import bang_mat, mau_nhom  # noqa: E402

SERVE_REL = ("outputs", "train_sets")
CFG_RE = re.compile(r"[A-Za-z0-9_-]{1,40}\.json")
MAU = ("config", "loc_mau.json")
_LOCK = threading.Lock()                                    # một lần ghi tại một thời điểm
FLAG_CHOICES = [("Bất kỳ", ""), ("Không (0)", "0"), ("Có (1)", "1")]
CAMERAS, GLASSES = ("dash", "mirror", "drivface"), ("none", "glasses", "sunglasses", "unknown")
CSS = """
#loc-filters, #loc-rows, #loc-btns { gap: 10px; flex-wrap: wrap; align-items: flex-end; }
#loc-filters > *, #loc-rows > * { min-width: 150px !important; }
#loc-btns button { min-width: 0 !important; flex: 1 1 150px !important; }
#loc-preview, #loc-create, #loc-save-cfg { font-weight: 800; } #loc-overwrite-ok { background: #dc2626 !important; border-color: #b91c1c !important; color: #fff !important; }
#loc-msg, #loc-result, #loc-note { padding: 0 !important; } #tab-loc { padding: 8px 0 0 !important; gap: 10px; max-width: 1120px; margin: 0 auto; width: 100%; }
"""


def serve_dir(project_root):
    """<project>\\outputs\\train_sets (tạo nếu chưa có; lỗi tạo thì vẫn trả đường dẫn)."""
    p = os.path.join(project_root, *SERVE_REL)
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        pass
    return p


def e(x):
    return html.escape("" if x is None else str(x), quote=True)


def msg_html(text, level="info"):
    return f'<div class="m28-msg m-{e(level)}" role="status">{e(text)}</div>' if text else ""


# ---------- giá trị điều khiển <-> cấu hình lọc (thuần, test không cần gradio) ----------
KEYS = (["luot", "luot_nhap", "nguon", "quyet_dinh", "nguoi_ra", "set_goc", "co_nguon", "t_flip", "co_tong_min", "co_tong_max", "nme_min", "nme_max",
         "pose", "expression", "occlusion", "illumination", "blur", "camera", "glasses", "thieu_diem", "low_conf_nhan", "lech_nhan", "giu_mat", "loc_tap_danh_gia",
         "kem_anh", "zip", "ten"] + [f"nhom_{g}_{m}" for g in mau_nhom.GROUP_COLOR for m in ("min", "max")]
        + [f"vung_{g}_{m}" for g in ("brow", "nose", "eye", "lip") for m in ("min", "max")])


def _n(v, nguyen=False):
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ld.CauHinhLoi(f"Giá trị {v!r} không phải số.")
    return int(x) if nguyen and x == int(x) else x


def _flag(v):
    return None if v in (None, "") else int(v)


def to_cfg(v):
    """dict giá trị điều khiển (theo KEYS) -> cấu hình lọc dạng JSON (chưa kiểm: loc_du_lieu.kiem_cau_hinh kiểm). Số nhập sai kiểu -> CauHinhLoi."""
    kd = lambda mn, mx, ng=False: {"toi_thieu": _n(v.get(mn), ng), "toi_da": _n(v.get(mx), ng)}                    # noqa: E731
    return {
        "ten": "bo_loc" if v.get("ten") is None else str(v["ten"]).strip(),
        "nguon_nhan": {"luot": list(v.get("luot") or []), "file_nhan": [], "luot_nhap": v.get("luot_nhap") or None, "uu_tien": ["final", "manual", "assisted"]},
        "nguon_du_lieu": list(v.get("nguon") or []), "set_goc": [s.strip() for s in str(v.get("set_goc") or "").replace(";", ",").split(",") if s.strip()],
        "quyet_dinh": list(v.get("quyet_dinh") or []), "nguoi_ra": list(v.get("nguoi_ra") or []),
        "co": {"nguon": v.get("co_nguon") or "flags_json", "t_flip": _n(v.get("t_flip")), "tong": kd("co_tong_min", "co_tong_max", True),
               "theo_nhom": {g: kd(f"nhom_{g}_min", f"nhom_{g}_max", True) for g in mau_nhom.GROUP_COLOR
                             if v.get(f"nhom_{g}_min") not in (None, "") or v.get(f"nhom_{g}_max") not in (None, "")},
               "theo_vung": {g: kd(f"vung_{g}_min", f"vung_{g}_max", True) for g in ("brow", "nose", "eye", "lip")
                             if v.get(f"vung_{g}_min") not in (None, "") or v.get(f"vung_{g}_max") not in (None, "")}},
        "nme_nhap": kd("nme_min", "nme_max"),
        "manifest": {"pose": _flag(v.get("pose")), "expression": _flag(v.get("expression")), "occlusion": _flag(v.get("occlusion")), "illumination": _flag(v.get("illumination")),
                     "blur": _flag(v.get("blur")), "makeup": None, "camera": list(v.get("camera") or []) or None, "glasses": list(v.get("glasses") or []) or None, "state": None},
        "nhan": {"so_diem_thieu_toi_da": _n(v.get("thieu_diem"), True) if v.get("thieu_diem") not in (None, "") else 0,
                 "low_conf_trong_nhan_toi_da": _n(v.get("low_conf_nhan"), True), "lech_nhan_toi_da": _n(v.get("lech_nhan")), "dieu_kien": [], "loai_mat": []},
        "giu_mat_khong_nhap": bool(v.get("giu_mat")),
        "chia": {**{k: list(x) for k, x in ld.SET_CHIA_MAC_DINH.items()}, "loc_tap_danh_gia": bool(v.get("loc_tap_danh_gia"))},
        "kem_anh": bool(v.get("kem_anh")), "zip": bool(v.get("zip")),
    }


def from_cfg(cfg):
    """Cấu hình lọc ĐÃ KIỂM -> dict giá trị điều khiển (theo KEYS)."""
    v = {"luot": cfg["nguon_nhan"]["luot"], "luot_nhap": cfg["nguon_nhan"]["luot_nhap"] or "", "nguon": cfg["nguon_du_lieu"], "quyet_dinh": cfg["quyet_dinh"],
         "nguoi_ra": cfg["nguoi_ra"], "set_goc": ", ".join(cfg["set_goc"]), "co_nguon": cfg["co"]["nguon"], "t_flip": cfg["co"]["t_flip"],
         "co_tong_min": cfg["co"]["tong"]["toi_thieu"], "co_tong_max": cfg["co"]["tong"]["toi_da"], "nme_min": cfg["nme_nhap"]["toi_thieu"], "nme_max": cfg["nme_nhap"]["toi_da"],
         "thieu_diem": cfg["nhan"]["so_diem_thieu_toi_da"], "low_conf_nhan": cfg["nhan"]["low_conf_trong_nhan_toi_da"], "lech_nhan": cfg["nhan"]["lech_nhan_toi_da"],
         "giu_mat": cfg["giu_mat_khong_nhap"], "loc_tap_danh_gia": cfg["chia"]["loc_tap_danh_gia"], "kem_anh": cfg["kem_anh"], "zip": cfg["zip"], "ten": cfg["ten"]}
    for k in ("pose", "expression", "occlusion", "illumination", "blur"):
        x = cfg["manifest"].get(k)
        v[k] = "" if not x or len(x) != 1 else str(x[0])
    v["camera"] = cfg["manifest"].get("camera") or []
    v["glasses"] = cfg["manifest"].get("glasses") or []
    for g in mau_nhom.GROUP_COLOR:
        kh = cfg["co"]["theo_nhom"].get(g, {})
        v[f"nhom_{g}_min"], v[f"nhom_{g}_max"] = kh.get("toi_thieu"), kh.get("toi_da")
    for g in ("brow", "nose", "eye", "lip"):
        kh = cfg["co"]["theo_vung"].get(g, {})
        v[f"vung_{g}_min"], v[f"vung_{g}_max"] = kh.get("toi_thieu"), kh.get("toi_da")
    return v


NUM_KEYS = {"t_flip", "co_tong_min", "co_tong_max", "nme_min", "nme_max", "thieu_diem", "low_conf_nhan", "lech_nhan"} | \
           {f"{a}_{g}_{m}" for a in ("nhom", "vung") for g in list(mau_nhom.GROUP_COLOR) + ["brow", "nose", "eye", "lip"] for m in ("min", "max")}
# Ô số tuỳ chọn là ô CHỮ (trống = không giới hạn): gr.Number(value=None) hiện và có thể gửi 0, làm bộ lọc loại hết mặt (đã gặp trên trình duyệt thật).


def groups_regions(project_root):
    cfg = bang_mat.load_cfg(project_root)
    return bang_mat.groups_of(cfg), bang_mat.regions_of(cfg)


def cfg_from_values(project_root, v):
    """Giá trị điều khiển -> cấu hình lọc đã kiểm. Sai thì CauHinhLoi/BangLoi."""
    groups, regions = groups_regions(project_root)
    return ld.kiem_cau_hinh(to_cfg(v), groups, regions)


# ---------- HTML kết quả ----------
def _tr(cells, head=False):
    tag = "th" if head else "td"
    return "<tr>" + "".join("<" + tag + (' class="tk-r"' if i else "") + ">" + c + "</" + tag + ">" for i, c in enumerate(cells)) + "</tr>"


def _table(head, rows):
    return ('<div class="tk-tw"><table class="tk-table"><thead>' + _tr([e(h) for h in head], True) + "</thead><tbody>" + "".join(_tr(r) for r in rows) + "</tbody></table></div>")


def kq_html(kq):
    """Bảng số lượng của một lần lọc (dùng cho Preview và sau khi tạo): vào, thác nước, từng tiêu chí, còn lại theo phần/nguồn/lượt, cảnh báo. KHÔNG hiện ảnh mặt."""
    out = ['<div class="tk-root">',
           f'<div class="tk-tiles"><div class="tk-tile"><div class="tk-tv">{kq.tong}</div><div class="tk-tl">mặt vào ((lượt, mặt))</div><div class="tk-tn">{kq.bang.mat_duy_nhat()} mặt duy nhất</div></div>'
           f'<div class="tk-tile"><div class="tk-tv">{len(kq.giu)}</div><div class="tk-tl">mặt còn lại</div></div>'
           + "".join(f'<div class="tk-tile"><div class="tk-tv">{sum(1 for m in kq.giu if m["dg"]["phan"] == ph)}</div><div class="tk-tl">{ph}</div></div>' for ph in ld.PHAN) + "</div>"]
    if kq.ro_ri:
        s = next(iter(kq.ro_ri))
        out.append(f'<div class="tk-note tk-warn"><b>LỖI: rò rỉ người.</b> {len(kq.ro_ri)} tài xế (subject) nằm ở hơn một phần train/val/test (ví dụ {e(s)}: {e(", ".join(kq.ro_ri[s]))}). '
                   'Không tạo được bộ dữ liệu cho tới khi sửa cách chia.</div>')
    for w in kq.canh_bao:
        out.append(f'<div class="tk-note tk-warn">{e(w)}</div>')
    out.append("<h5>Bị loại theo thứ tự tiêu chí (thác nước: tổng các bước = vào − còn lại)</h5>"
               + _table(["Lý do", "Số mặt"], [[e(vi), str(kq.thac[c])] for c, vi in ld.LY_DO if kq.thac[c]] + [["<b>Còn lại</b>", f"<b>{len(kq.giu)}</b>"]]))
    out.append("<h5>Số mặt không đạt TỪNG tiêu chí (chồng lấn)</h5>" + _table(["Tiêu chí", "Số mặt"], [[e(vi), str(kq.tung_tieu_chi[c])] for c, vi in ld.LY_DO if kq.tung_tieu_chi[c]] or [["(không có)", ""]]))
    for key, ten in (("nguon", "Nguồn"), ("luot", "Lượt")):
        rows = [[e(k or "(chỉ có nhãn)")] + [str(d.get(ph, 0)) for ph in ld.PHAN] + [str(sum(d.values()))] for k, d in sorted(ld.dem_theo(kq, key).items())]
        out.append(f"<h5>Còn lại theo {ten.lower()} và phần</h5>" + _table([ten] + list(ld.PHAN) + ["Tổng"], rows or [["(không còn mặt nào)"] + [""] * 4]))
    out.append("</div>")
    return "".join(out)


def cfg_files(project_root):
    """Tên file cấu hình lọc cho ô nạp: config\\loc_mau.json (mẫu) và outputs\\*.json hợp lệ về tên. [(nhãn, giá trị)]."""
    out = [("config\\loc_mau.json (mẫu)", "config/loc_mau.json")]
    d = os.path.join(project_root, "outputs")
    try:
        names = sorted(f for f in os.listdir(d) if CFG_RE.fullmatch(f) and os.path.isfile(os.path.join(d, f)))
    except OSError:
        names = []
    return out + [(f"outputs\\{n}", f"outputs/{n}") for n in names]


def resolve_cfg(project_root, value):
    """Đường dẫn file cấu hình từ giá trị trong danh sách (phải là phần tử của cfg_files do server tính); sai thì RunError."""
    if value not in [v for _l, v in cfg_files(project_root)]:
        raise nap_anh.RunError("File cấu hình không có trong danh sách: bấm Refresh.")
    p = os.path.join(project_root, *value.split("/"))
    if not nap_anh._inside(p, project_root):
        raise nap_anh.RunError("File cấu hình nằm ngoài thư mục dự án: từ chối.")
    return p


def save_cfg_path(project_root, name):
    """outputs\\<tên>.json (tên kiểm theo CFG_RE; realpath + commonpath); sai thì RunError."""
    name = (name or "").strip()
    if not name.endswith(".json"):
        name += ".json"
    if not CFG_RE.fullmatch(name):
        raise nap_anh.RunError("Tên file cấu hình chỉ gồm chữ không dấu, số, _ và -, tối đa 40 ký tự trước .json (ví dụ loc_cua_toi).")
    d = os.path.join(project_root, "outputs")
    p = os.path.join(d, name)
    if not nap_anh._inside(p, d):
        raise nap_anh.RunError("Đường dẫn cấu hình nằm ngoài outputs: từ chối.")
    return p


def loc_tab(gr, demo, store, ctx):
    """Tab "Lọc dữ liệu". Trả (hàm làm mới, inputs, outputs, opts) để build_ui nối vào tab.select."""
    opts = dict(show_progress="minimal", api_visibility="private", concurrency_limit=1, concurrency_id="locdl")
    groups, regions = ([], [])
    try:
        groups, regions = groups_regions(ctx.project_root)
    except (bang_mat.BangLoi, OSError):
        pass
    with gr.Row(elem_id="loc-filters"):
        d_luot = gr.Dropdown(choices=[], value=[], multiselect=True, label="Lượt lấy nhãn (để trống = tất cả)", elem_id="loc-luot")
        d_nhap = gr.Dropdown(choices=[("(không)", "")], value="", label="Lượt chứa nháp cho nhãn thí nghiệm (luot_nhap)", elem_id="loc-luotnhap")
        g_nguon = gr.CheckboxGroup(choices=[("YawDD", "yawdd"), ("DrivFace", "drivface")], value=["yawdd", "drivface"], label="Nguồn dữ liệu (nguồn không rõ luôn bị loại)", elem_id="loc-nguon")
        g_qd = gr.CheckboxGroup(choices=[("Nhận", "nhan"), ("Sửa nhãn", "gan_tay"), ("Bỏ", "bo")], value=["nhan", "gan_tay"], label="Quyết định rà (áp lên train)", elem_id="loc-qd")
        d_nguoi = gr.Dropdown(choices=[], value=[], multiselect=True, label="Người rà (để trống = tất cả; không tính triage_auto)", elem_id="loc-nguoi")
        t_set = gr.Textbox(value="", label="Chỉ các tập gốc (set), cách nhau dấu phẩy; trống = tất cả", elem_id="loc-set")
    gr.Markdown("**Cờ low_conf** (số điểm bị cờ trên 50 điểm; áp lên train, để trống = không giới hạn)")
    with gr.Row(elem_id="loc-rows"):
        r_conguon = gr.Radio(choices=[("Cờ máy ghi ở flags.json", "flags_json"), ("Tính lại với t_flip", "tinh_lai")], value="flags_json", label="Nguồn cờ", elem_id="loc-conguon")
        n_tflip = gr.Textbox(value="", label="t_flip (chỉ khi tính lại)", elem_id="loc-tflip", placeholder="ví dụ 0.06")
        n_tmin = gr.Textbox(value="", label="Tổng cờ tối thiểu", elem_id="loc-tmin", placeholder="không giới hạn")
        n_tmax = gr.Textbox(value="", label="Tổng cờ tối đa", elem_id="loc-tmax", placeholder="không giới hạn")
    grp = {}
    with gr.Accordion("Cờ theo nhóm điểm và theo vùng", open=False):
        for g in groups:
            with gr.Row():
                grp[f"nhom_{g}_min"] = gr.Textbox(value="", label=f"{mau_nhom.GROUP_VI.get(g, g)}: tối thiểu", elem_id=f"loc-n-{g}-min", placeholder="không giới hạn")
                grp[f"nhom_{g}_max"] = gr.Textbox(value="", label=f"{mau_nhom.GROUP_VI.get(g, g)}: tối đa", elem_id=f"loc-n-{g}-max", placeholder="không giới hạn")
        vi = {"brow": "lông mày", "nose": "mũi", "eye": "mắt", "lip": "môi"}
        for g in regions:
            with gr.Row():
                grp[f"vung_{g}_min"] = gr.Textbox(value="", label=f"Vùng {vi.get(g, g)}: tối thiểu", elem_id=f"loc-v-{g}-min", placeholder="không giới hạn")
                grp[f"vung_{g}_max"] = gr.Textbox(value="", label=f"Vùng {vi.get(g, g)}: tối đa", elem_id=f"loc-v-{g}-max", placeholder="không giới hạn")
    with gr.Row(elem_id="loc-rows"):
        n_nmin = gr.Textbox(value="", label="NME nháp tối thiểu (% IOD)", elem_id="loc-nmin", placeholder="không giới hạn")
        n_nmax = gr.Textbox(value="", label="NME nháp tối đa (% IOD)", elem_id="loc-nmax", placeholder="không giới hạn")
        n_thieu = gr.Textbox(value="0", label="Nhãn thiếu tối đa (điểm)", elem_id="loc-thieu", placeholder="0 = phải đủ 50 điểm")
        n_lc = gr.Textbox(value="", label="low_conf còn bật trong nhãn, tối đa", elem_id="loc-lcnhan", placeholder="không giới hạn")
        n_lech = gr.Textbox(value="", label="Độ lệch hai nhãn người, tối đa (% IOD)", elem_id="loc-lech", placeholder="không giới hạn")
    with gr.Accordion("Cờ manifest (tư thế, biểu cảm, che, tối, mờ, camera, kính)", open=False):
        with gr.Row():
            f_pose = gr.Dropdown(choices=FLAG_CHOICES, value="", label="Tư thế (nghiêng)", elem_id="loc-pose")
            f_exp = gr.Dropdown(choices=FLAG_CHOICES, value="", label="Biểu cảm", elem_id="loc-exp")
            f_occ = gr.Dropdown(choices=FLAG_CHOICES, value="", label="Che / kính râm", elem_id="loc-occ")
            f_ill = gr.Dropdown(choices=FLAG_CHOICES, value="", label="Tối / sáng", elem_id="loc-ill")
            f_blur = gr.Dropdown(choices=FLAG_CHOICES, value="", label="Mờ", elem_id="loc-blur")
        with gr.Row():
            f_cam = gr.Dropdown(choices=list(CAMERAS), value=[], multiselect=True, label="Camera (trống = tất cả)", elem_id="loc-cam")
            f_gl = gr.Dropdown(choices=list(GLASSES), value=[], multiselect=True, label="Kính (trống = tất cả)", elem_id="loc-gl")
    with gr.Row(elem_id="loc-rows"):
        c_giu = gr.Checkbox(value=False, label="Giữ mặt không có nháp/cờ/lượt (giu_mat_khong_nhap)", elem_id="loc-giu")
        c_dg = gr.Checkbox(value=False, label="Áp tiêu chí ca khó cả lên val/test (loc_tap_danh_gia)", elem_id="loc-dg")
        c_anh = gr.Checkbox(value=True, label="Kèm ảnh cắt 512 vào gói", elem_id="loc-kemanh")
        c_zip = gr.Checkbox(value=False, label="Tạo thêm file .zip (chỉ gửi trong đội)", elem_id="loc-zip")
    comps = {"luot": d_luot, "luot_nhap": d_nhap, "nguon": g_nguon, "quyet_dinh": g_qd, "nguoi_ra": d_nguoi, "set_goc": t_set, "co_nguon": r_conguon, "t_flip": n_tflip,
             "co_tong_min": n_tmin, "co_tong_max": n_tmax, "nme_min": n_nmin, "nme_max": n_nmax, "pose": f_pose, "expression": f_exp, "occlusion": f_occ, "illumination": f_ill,
             "blur": f_blur, "camera": f_cam, "glasses": f_gl, "thieu_diem": n_thieu, "low_conf_nhan": n_lc, "lech_nhan": n_lech, "giu_mat": c_giu, "loc_tap_danh_gia": c_dg,
             "kem_anh": c_anh, "zip": c_zip, **grp}
    gr.Markdown("**Cấu hình lọc (JSON)** — nạp/lưu chỉ trong thư mục `outputs\\`")
    with gr.Row(elem_id="loc-rows"):
        d_cfg = gr.Dropdown(choices=cfg_files(ctx.project_root), value=None, label="Nạp cấu hình", elem_id="loc-cfg")
        b_load = gr.Button("Load", elem_id="loc-load-cfg")
        t_cfgname = gr.Textbox(value="", label="Lưu thành (outputs\\<tên>.json)", placeholder="loc_cua_toi", elem_id="loc-cfgname")
        b_save = gr.Button("Save config", elem_id="loc-save-cfg")
    with gr.Row(elem_id="loc-rows"):
        t_ten = gr.Textbox(value="bo_loc", label="Tên bộ dữ liệu (chữ không dấu, số, _ -; tối đa 40)", elem_id="loc-ten")
    comps["ten"] = t_ten
    with gr.Row(elem_id="loc-btns"):
        b_prev = gr.Button("Preview", variant="primary", elem_id="loc-preview")
        b_make = gr.Button("Create dataset", variant="stop", elem_id="loc-create")
    with gr.Row(visible=False, elem_id="loc-confirm") as confirm_row:
        b_ow = gr.Button("Overwrite", elem_id="loc-overwrite-ok")
        b_ow_no = gr.Button("Cancel", elem_id="loc-overwrite-cancel")
    msg = gr.HTML(elem_id="loc-msg", apply_default_css=False)
    result = gr.HTML(elem_id="loc-result", apply_default_css=False)
    download = gr.DownloadButton("Download .zip", visible=False, elem_id="loc-download")
    order = [k for k in KEYS if k in comps]
    inputs = [comps[k] for k in order]
    refresh_outs = [d_luot, d_nhap, d_nguoi, d_cfg, msg]

    def vals(*a):
        return dict(zip(order, a))

    def lists():
        return dot_anh.list_runs(ctx.runs_root), thong_ke_ui.reviewers(ctx.runs_root)

    def on_refresh(luot, nhap, nguoi, cfgsel):
        runs, who = lists()
        keep = lambda sel, ok: [x for x in (sel or []) if x in ok]                                           # noqa: E731
        return (gr.update(choices=runs, value=keep(luot, runs)), gr.update(choices=[("(không)", "")] + [(r, r) for r in runs], value=nhap if nhap in runs else ""),
                gr.update(choices=who, value=keep(nguoi, who)), gr.update(choices=cfg_files(ctx.project_root), value=cfgsel), "")

    def check_values(v):
        runs = dot_anh.list_runs(ctx.runs_root)
        for l in v.get("luot") or []:
            if l not in runs:
                raise nap_anh.RunError(f"Lượt {l!r} không có trong danh sách lượt: bấm Refresh.")
        if v.get("luot_nhap") and v["luot_nhap"] not in runs:
            raise nap_anh.RunError(f"Lượt chứa nháp {v['luot_nhap']!r} không có trong danh sách lượt: bấm Refresh.")

    def lam_loc(v):
        check_values(v)
        cfg = cfg_from_values(ctx.project_root, v)
        return cfg, ld.chay_loc(ctx.project_root, cfg)

    ERR = (nap_anh.RunError, ld.CauHinhLoi, ld.DuLieuLoi, bang_mat.BangLoi, OSError)

    def on_preview(*a):
        try:
            _cfg, kq = lam_loc(vals(*a))
        except ERR as ex:
            gr.Warning(str(ex), title="Chưa xem trước được")
            return msg_html(str(ex), "warn"), "", gr.update(visible=False), gr.update(visible=False)
        return msg_html("Preview = chạy thử (--dry-run): chưa ghi file nào.", "info"), kq_html(kq), gr.update(visible=False), gr.update(visible=False)

    def tao(a, ghi_de):
        if ctx.closing:
            return msg_html(nap_anh.CLOSING_MSG, "warn"), "", gr.update(visible=False), gr.update(visible=False)
        with _LOCK:
            try:
                v = vals(*a)
                cfg, kq = lam_loc(v)
                dest = ld.duong_goi(ctx.project_root, cfg["ten"])
                if os.path.exists(dest) and not ghi_de:
                    return (msg_html(f"Bộ {cfg['ten']!r} đã có. Bấm Overwrite để thay, hoặc đổi tên bộ.", "warn"), kq_html(kq), gr.update(visible=False),
                            gr.update(visible=True))
                info = ld.ghi_bo(kq, cfg["ten"], ghi_de=ghi_de)
            except ERR as ex:
                gr.Warning(str(ex), title="Chưa tạo được bộ dữ liệu")
                return msg_html(str(ex), "warn"), "", gr.update(visible=False), gr.update(visible=False)
        txt = (f"Đã tạo {info['rel']}: {info['so_mat']} mặt ({', '.join(f'{k} {n}' for k, n in info['theo_phan'].items())}). "
               "Gói chứa ảnh mặt người lái xe: chỉ dùng nội bộ nhóm, không đưa lên git hay dịch vụ bên ngoài.")
        if info["zip"]:
            txt += " Đã tạo cả file .zip: chỉ gửi trong đội."
        return (msg_html(txt, "ok"), kq_html(kq), gr.update(value=info["zip"], visible=True) if info["zip"] else gr.update(visible=False), gr.update(visible=False))

    def on_make(*a):
        return tao(a, False)

    def on_overwrite(*a):
        return tao(a, True)

    def on_overwrite_cancel():
        return gr.update(visible=False)

    def on_save(name, *a):
        if ctx.closing:
            return msg_html(nap_anh.CLOSING_MSG, "warn"), gr.update()
        try:
            cfg = cfg_from_values(ctx.project_root, vals(*a))
            p = save_cfg_path(ctx.project_root, name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            ca_kho._atomic_write(p, json.dumps(cfg, ensure_ascii=False, indent=1) + "\n", "w", "utf-8")
        except ERR as ex:
            gr.Warning(str(ex), title="Chưa lưu được cấu hình")
            return msg_html(str(ex), "warn"), gr.update()
        return msg_html(f"Đã lưu outputs\\{os.path.basename(p)}.", "ok"), gr.update(choices=cfg_files(ctx.project_root), value="outputs/" + os.path.basename(p))

    def on_load(sel):
        try:
            p = resolve_cfg(ctx.project_root, sel)
            cfg = ld.doc_cau_hinh(p, *groups_regions(ctx.project_root))
        except ERR as ex:
            gr.Warning(str(ex), title="Chưa nạp được cấu hình")
            return (msg_html(str(ex), "warn"),) + (gr.update(),) * len(order)
        v = from_cfg(cfg)
        shown = lambda k: ("" if v[k] is None else str(v[k])) if k in NUM_KEYS else v[k]                       # noqa: E731
        return (msg_html(f"Đã nạp {sel.replace('/', chr(92))}. Bấm Preview để kiểm.", "ok"),) + tuple(gr.update(value=shown(k)) for k in order)

    b_prev.click(on_preview, inputs, [msg, result, download, confirm_row], **opts)
    b_make.click(on_make, inputs, [msg, result, download, confirm_row], **dict(opts, concurrency_id="locdl_ghi"))
    b_ow.click(on_overwrite, inputs, [msg, result, download, confirm_row], **dict(opts, concurrency_id="locdl_ghi"))
    b_ow_no.click(on_overwrite_cancel, None, [confirm_row], **opts)
    b_save.click(on_save, [t_cfgname] + inputs, [msg, d_cfg], **dict(opts, concurrency_id="locdl_ghi"))
    b_load.click(on_load, [d_cfg], [msg] + inputs, **opts)
    return on_refresh, [d_luot, d_nhap, d_nguoi, d_cfg], refresh_outs, opts
