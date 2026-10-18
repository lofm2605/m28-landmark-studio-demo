"""Tab "Thống kê" của trang rà soát M28 (dựng theo mẫu ca_kho.member_tab): CHỈ BA CHỈ SỐ của thí nghiệm hai nhóm độc lập (QĐ-006): NME của nháp so với nhãn manual,
tỉ lệ điểm phải sửa, so sánh thời gian manual với assisted. Tab "Lọc dữ liệu" (loc_ui.py) là việc khác và giữ nguyên.

Mục "Nhập tay" (accordion, đóng sẵn; m28core\\nhap_tay.py): người nhóm MANUAL gán thẳng trong CVAT không dùng tool nên không có gói của đồng hồ; nhóm trưởng nhập cho từng người
người, nhóm, đợt/bộ ảnh, thời gian làm (gõ tay), ngày làm và file nhãn xuất từ CVAT ("CVAT for images 1.1", .xml/.zip không kèm ảnh). Mỗi bản là một gói kết quả bình thường
(outputs\\goi_nhom\\ketqua_<Pk>_<DDMM>_<đợt>.zip, nguon_nhap="nhap_tay") nên tính vào ba chỉ số y như gói của đồng hồ; bấm hai lần không nhân đôi; cùng người đã có gói
khác cùng đợt, hoặc trùng tên ảnh dù khác đợt, thì từ chối; "Remove entry" chỉ chuyển file vào outputs\\goi_nhom\\_da_bo (không xoá). Nhóm assisted: đợt phải là tên lượt
(runs\\<lượt>) đã dựng nháp; máy không có nháp đó thì vẫn thêm nhưng thông báo là cảnh báo (NME của nháp và tỉ lệ sửa thiếu mặt của người đó).

Quy ước (giống ca_kho.py):
  * Đầu module KHÔNG nạp gradio (nhận `gr` làm tham số); chỉ thư viện chuẩn và các module tool/ chỉ thư viện chuẩn + numpy nạp lười. Không gọi mạng, không đọc token.
  * Tính KHI CHỌN TAB (tab.select) hoặc bấm Load & Calculate (đọc các gói ở ô nạp rồi tính), không tính lúc mở trang; chỉ ĐỌC runs\\, raw\\, data\\, outputs\\. Chỉ ghi khi bấm "Export CSV + HTML" (chỉ dưới outputs\\thong_ke)
    và khi bấm "Add manual entry" / "Remove entry" của mục Nhập tay (chỉ dưới outputs\\goi_nhom). Chỉ tải gói lên (ô "Nạp các gói...") hay chọn tab thì không ghi gì;
    bấm "Load & Calculate" thì gói hợp lệ ở ô nạp được CHÉP nguyên byte vào outputs\\goi_da_nap (mở lại trang vẫn còn; "Remove package" chuyển vào goi_da_nap\\_da_bo,
    không xoá). "Set name" / "Clear name" ghi outputs\\ten_nguoi.json (không nằm trong thư mục trang phát qua URL).
  * Giá trị từ trình duyệt (lượt chứa nháp, đường dẫn bấm giờ) được kiểm lại ở server: lượt phải là phần tử của danh sách do server tính; đường dẫn bấm giờ phải nằm trong thư mục dự án;
    gói kết quả tải lên (ô "Nạp các gói kết quả của nhóm") được đọc từ file tạm của Gradio, kiểm sha256 và cấu trúc trước khi tin (gói hỏng không được lưu).
  * Handler: api_visibility="private", concurrency_id riêng (thongke, thongke_xuat, thongke_tay), không chặn tab khác; lỗi -> gr.Warning và thông báo tiếng Việt, không traceback
    lên trang; trang đang đóng (Close page) thì từ chối ghi.
  * Trang không hiện ảnh mặt (chỉ số); bản xuất tĩnh cũng không có ảnh mặt, không mã tài xế.
"""
import datetime
import glob
import html
import os
import re
import sys
import threading

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import dot_anh  # noqa: E402
import nap_anh  # noqa: E402
import thong_ke  # noqa: E402
import thong_ke_html  # noqa: E402
from m28core import bang_mat, nhap_tay, nhom as nhom_mod, ten_nguoi, toc_do  # noqa: E402

SERVE_REL = ("outputs", "thong_ke")
NGUOI_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")
_LOCK = threading.Lock()                                    # một lần xuất tại một thời điểm
CSS = thong_ke_html.CSS + """
#tk-filters { gap: 10px; flex-wrap: wrap; align-items: flex-end; }
#tk-filters > * { min-width: 160px !important; }
#tk-btns { gap: 8px; flex-wrap: wrap; } #tk-btns button { min-width: 0 !important; flex: 1 1 140px !important; }
#tk-refresh, #tk-export { font-weight: 800; }
#tk-view, #tk-msg { padding: 0 !important; } #tab-thongke { padding: 8px 0 0 !important; gap: 10px; max-width: 1120px; margin: 0 auto; width: 100%; }
#tk-msg:not(:has(.html-container > div > *)) { display: none; }
#tk-tay-row, #tk-tay-bo { gap: 10px; flex-wrap: wrap; align-items: flex-end; } #tk-tay-row > * { min-width: 150px !important; }
#tk-tay-bo > * { min-width: 200px !important; } #tk-tay-remove { flex: 0 1 160px !important; min-width: 0 !important; }
#tk-log-view { padding: 0 !important; }
#tk-log-panel { position: fixed !important; top: 7vh; left: 50%; transform: translateX(-50%); width: min(940px, 94vw); max-height: 84vh; overflow: auto; z-index: 45;
  padding: 14px 16px !important; border: 1px solid var(--border-color-primary); border-radius: 12px; background: var(--background-fill-primary); box-shadow: 0 12px 40px rgba(0,0,0,.45); }
#tk-log-head { align-items: center; justify-content: space-between; } #tk-log-head button { flex: 0 0 auto !important; width: auto !important; min-width: 90px !important; }
#tk-ten-msg, #tk-ten-list, #tk-tay-msg, #tk-tay-list { padding: 0 !important; } #tk-tay-msg:not(:has(.html-container > div > *)) { display: none; }
"""


def serve_dir(project_root):
    """<project>\\outputs\\thong_ke (tạo nếu chưa có; lỗi tạo thì vẫn trả đường dẫn)."""
    p = os.path.join(project_root, *SERVE_REL)
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        pass
    return p


def msg_html(text, level="info"):
    return f'<div class="m28-msg m-{html.escape(level)}" role="status">{html.escape(text)}</div>' if text else ""


JS_BODY = r"""
  // Tab "Thống kê": Esc tắt hộp Log đang mở (nút Close làm đúng việc đó).
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') { return; }
    const p = document.getElementById('tk-log-panel');
    const c = document.getElementById('tk-log-close');
    const t = e.target;
    const loai = (t && t.tagName === 'INPUT') ? (t.getAttribute('type') || 'text').toLowerCase() : '';
    const go = t && (t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable
                     || (t.tagName === 'INPUT' && ['checkbox', 'radio', 'range', 'button', 'submit', 'file'].indexOf(loai) < 0));   // Esc trong ô gõ chữ (đóng dropdown...): không đóng Log; ô tick, thanh trượt thì vẫn đóng
    if (p && c && !go && p.getClientRects().length > 0 && !document.querySelector('.m28-modal')) { e.preventDefault(); c.click(); }      // panel position:fixed nên offsetParent luôn null: dùng getClientRects
  });
"""
LOG_MO_JS = r"""() => {
  // Mở hộp Log: nhãn cho trình đọc màn hình và đưa con trỏ bàn phím vào nút Close (Esc hoặc Enter để đóng).
  setTimeout(() => {
    const p = document.getElementById('tk-log-panel');
    if (p) { p.setAttribute('role', 'dialog'); p.setAttribute('aria-label', 'Log của thống kê'); }
    const c = document.getElementById('tk-log-close');
    if (c) { c.focus(); }
  }, 120);
}"""
LOG_DONG_JS = r"""() => {
  setTimeout(() => { const b = document.getElementById('tk-log-open'); if (b) { b.focus(); } }, 80);          // trả con trỏ về nút Log
}"""
LOG_TRONG = '<div class="tk-root"><div class="tk-note">Chưa tính: bấm Load &amp; Calculate rồi mở lại Log.</div></div>'


def nap_note(r, files, tinh_xong=True):
    """Câu báo sau khi bấm Load & Calculate với các file ở ô nạp: (chữ, mức) hoặc ("", "info") khi ô nạp trống hay không làm gì (trang đang đóng).
    r = thong_ke.luu_goi_nap(...). tinh_xong=False: tính lỗi sau khi đã lưu, không nói "số liệu đã tính lại"."""
    if not goi_paths(files):
        return "", "info"
    parts = []
    if r["luu"]:
        parts.append(f"Đã lưu {len(r['luu'])} gói vào outputs\\goi_da_nap, mở lại trang vẫn còn ({', '.join(r['luu'])})")
    if r.get("moi_hon"):
        parts.append(f"{len(r['moi_hon'])} gói là bản MỚI HƠN của gói đã có (cùng mã phiên), đã lưu và thống kê dùng bản mới ({', '.join(r['moi_hon'])})"
                     + (f"; bản cũ chuyển vào outputs\\goi_da_nap\\_da_bo ({', '.join(r['da_bo'])})" if r.get("da_bo") else ""))
    if r["co_san"]:
        parts.append(f"{len(r['co_san'])} file đã có sẵn (cùng mã phiên với gói đã lưu, giống hệt hoặc cũ hơn: không chép thêm: {', '.join(r['co_san'])})")
    if r["loi"]:
        parts.append(f"{len(r['loi'])} file lỗi, không lưu: " + "; ".join(f"{t}: {w}" for t, w in r["loi"][:3]))
    if not parts:
        return "", "info"
    duoi = ((". Số liệu ở dưới đã tính lại, kể cả gói chưa lưu được (còn trong ô nạp: bấm lại để lưu)." if r.get("chua_luu")
             else ". Số liệu ở dưới đã tính lại với các gói đã lưu.") if tinh_xong else ".")
    return "; ".join(parts) + duoi, ("warn" if r["loi"] else "ok")


def reviewers(runs_root):
    """Tên người rà có file triage_<người>.csv ở bất kỳ lượt nào (trừ auto: máy tự quyết, không phải người rà). Dùng chung với tab Lọc dữ liệu (loc_ui.py)."""
    out = set()
    for r in dot_anh.list_runs(runs_root):
        for p in glob.glob(os.path.join(glob.escape(os.path.join(runs_root, r, "review")), "triage_*.csv")):
            who = os.path.basename(p)[len("triage_"):-len(".csv")]
            if who and who != bang_mat.AUTO and NGUOI_RE.fullmatch(who):
                out.add(who)
    return sorted(out)


def clean_args(runs_root, luot_nhap):
    """Kiểm giá trị từ trình duyệt: lượt chứa nháp phải có trong danh sách server. Trả luot_nhap|None; sai thì RunError."""
    runs = dot_anh.list_runs(runs_root)
    if luot_nhap and luot_nhap not in runs:
        raise nap_anh.RunError(f"Lượt chứa nháp {luot_nhap!r} không có trong danh sách lượt: bấm Load & Calculate.")
    return luot_nhap or None


def _paths(files, exts):
    out = []
    for f in files or []:
        p = f if isinstance(f, str) else getattr(f, "name", None)
        if p and os.path.isfile(p) and p.lower().endswith(exts):
            out.append(p)
    return out


def goi_paths(files):
    """Đường dẫn các gói tải lên (gr.File trả list đường dẫn hoặc đối tượng có .name)."""
    return _paths(files, (".zip", ".json"))


def nhan_paths(files):
    """Đường dẫn các file nhãn CVAT tải lên ở mục Nhập tay (.xml hoặc .zip); nhap_tay.doc_file_nhan kiểm nội dung."""
    return _paths(files, (".xml", ".zip"))


def tay_list_html(rows):
    """Bảng các bản nhập tay (nhap_tay.liet_ke). Không ảnh, không đường dẫn."""
    if not rows:
        return '<div class="tk-root"><div class="tk-note">Chưa có bản nhập tay nào trong outputs\\goi_nhom.</div></div>'
    cols = [("Người", "nguoi", "l"), ("Nhóm", lambda r: thong_ke_html.COND_VI.get(r["nhom"], r["nhom"]), "l"), ("Đợt", "dot", "l"), ("Ngày làm", "ngay", "l"), ("Mặt", "so_mat", "r"),
            ("Thời gian", lambda r: nhap_tay.fmt_giay(r["giay"]), "r"), ("Giây/mặt", lambda r: thong_ke_html.num(r["giay"] / r["so_mat"], 1) if r["so_mat"] else "—", "r"),
            ("Gói", "ten", "l")]
    return f'<div class="tk-root"><h5>Bản nhập tay đang được tính ({len(rows)})</h5>' + thong_ke_html.bang(cols, rows) + "</div>"


def tay_choices(rows):
    return [(f'{r["nguoi"]} · {r["dot"]} · {r["ngay"]} ({r["ten"]})', r["ten"]) for r in rows]


def stats_tab(gr, demo, store, ctx):
    """Tab "Thống kê". Trả (hàm làm mới, inputs, outputs, opts) để build_ui nối vào tab.select."""
    opts = dict(show_progress="minimal", api_visibility="private", concurrency_limit=1, concurrency_id="thongke")
    with gr.Row(elem_id="tk-filters"):
        d_nhap = gr.Dropdown(choices=[("(không)", "")], value="", label="Lượt chứa nháp (cho nhãn trong raw\\ không có push.json)", elem_id="tk-luotnhap")
        s_nguong = gr.Slider(minimum=thong_ke.NGUONG_SUA_MIN, maximum=thong_ke.NGUONG_SUA_MAX, step=0.5, value=thong_ke.NGUONG_SUA, label="Ngưỡng điểm 'đã sửa' (% IOD)", elem_id="tk-nguong")
        c_task = gr.Checkbox(value=False, label="Mọi task", info="gồm cả practice/check/smoke (mặc định bỏ)", elem_id="tk-tatca")
        c_bo = gr.Checkbox(value=True, label="Chỉ bộ ảnh thí nghiệm", info="theo bo_anh trong config\\nhom_thi_nghiem.json (nếu có)", elem_id="tk-chibo")
        c_ttest = gr.Checkbox(value=False, label="Gồm Ttest", info="Ttest là tập đo một lần của đề tài", elem_id="tk-ttest")
        t_timing = gr.Textbox(value="", label="Thư mục/file bấm giờ thêm (trong thư mục dự án, tuỳ chọn)", elem_id="tk-timing")
    f_goi = gr.File(label="Nạp các gói kết quả của nhóm (ketqua_*.zip hoặc .json); bấm Load & Calculate để lưu vào outputs\\goi_da_nap và tính, mở lại trang vẫn còn", file_count="multiple", file_types=[".zip", ".json"], type="filepath",
                    elem_id="tk-goi", height=120)
    with gr.Accordion("Nhập tay: nhóm gán tay trực tiếp trong CVAT (không dùng tool)", open=False, elem_id="tk-tay") as acc_tay:
        with gr.Row(elem_id="tk-tay-row"):
            d_nguoi = gr.Dropdown(choices=sorted(nhom_mod.doc(ctx.project_root)["nhom"]), value=None, allow_custom_value=True, label="Người", elem_id="tk-tay-nguoi")
            r_nhom = gr.Radio(choices=[("manual (gán tay)", "manual"), ("assisted (dùng tool)", "assisted")], value="manual", label="Nhóm", elem_id="tk-tay-nhom")
            t_dot = gr.Textbox(value=nhom_mod.doc(ctx.project_root)["bo_anh"], label="Đợt / bộ ảnh (hai nhóm phải dùng cùng tên ảnh)", placeholder="ví dụ NAP_001",
                               info="nhóm assisted: gõ tên lượt đã dựng nháp (thư mục runs\\bo200 thì gõ bo200)", elem_id="tk-tay-dot")
            t_gio = gr.Textbox(value="", label="Thời gian làm", placeholder="1:25:30 · 85:30 · 85 (phút)", elem_id="tk-tay-gio")
            t_ngay = gr.Textbox(value="", label="Ngày làm", placeholder="trống = hôm nay; dd/mm/yyyy", elem_id="tk-tay-ngay")
        f_nhan = gr.File(label="File nhãn xuất từ CVAT (CVAT for images 1.1, không kèm ảnh)", file_count="multiple", file_types=[".xml", ".zip"], type="filepath",
                         elem_id="tk-tay-file", height=110)
        t_ghichu = gr.Textbox(value="", label="Ghi chú (tuỳ chọn; không ghi email, đường dẫn)", max_lines=2, elem_id="tk-tay-ghichu")
        b_tay_add = gr.Button("Add manual entry", variant="primary", elem_id="tk-tay-add")
        tay_msg = gr.HTML(elem_id="tk-tay-msg", apply_default_css=False)
        tay_list = gr.HTML(elem_id="tk-tay-list", apply_default_css=False)
        with gr.Row(elem_id="tk-tay-bo"):
            d_tay_bo = gr.Dropdown(choices=[], value=None, label="Bản nhập tay (gỡ thì chuyển vào outputs\\goi_nhom\\_da_bo, không xoá)", elem_id="tk-tay-chon")
            b_tay_bo = gr.Button("Remove entry", elem_id="tk-tay-remove")
    with gr.Accordion("Gói đã nạp: đặt tên người, gỡ gói (nhóm trưởng)", open=False, elem_id="tk-ten") as acc_ten:
        with gr.Row(elem_id="tk-ten-row"):
            d_ten_goi = gr.Dropdown(choices=[], value=None, allow_custom_value=True, label="Gói (đã lưu trong outputs\\goi_da_nap, outputs\\ket_qua, outputs\\goi_nhom, hoặc đang ở ô nạp)", elem_id="tk-ten-goi")
            t_ten = gr.Textbox(value="", label="Tên người", placeholder="ví dụ Cuong", max_lines=1, elem_id="tk-ten-ten")
        with gr.Row(elem_id="tk-ten-btns"):
            b_ten = gr.Button("Set name", variant="primary", elem_id="tk-ten-set")
            b_ten_xoa = gr.Button("Clear name", elem_id="tk-ten-clear")
            b_goi_bo = gr.Button("Remove package", elem_id="tk-goi-remove")
        ten_msg = gr.HTML(elem_id="tk-ten-msg", apply_default_css=False)
        ten_list = gr.HTML(elem_id="tk-ten-list", apply_default_css=False)
    with gr.Row(elem_id="tk-btns"):
        b_refresh = gr.Button("Load & Calculate", variant="primary", elem_id="tk-refresh")
        b_log = gr.Button("Log", elem_id="tk-log-open")
        b_export = gr.Button("Export CSV + HTML", elem_id="tk-export")
    with gr.Column(visible=False, elem_id="tk-log-panel") as log_panel:                  # hộp Log: nguồn dữ liệu, cảnh báo, bản trùng, hạn chế; bấm Close hoặc Esc để tắt
        with gr.Row(elem_id="tk-log-head"):
            gr.HTML('<div class="tk-root"><b>Log</b>: nguồn dữ liệu, cảnh báo, bản trùng và hạn chế của lần tính gần nhất</div>', apply_default_css=False)
            b_log_close = gr.Button("Close", elem_id="tk-log-close")
        log_view = gr.HTML(LOG_TRONG, elem_id="tk-log-view", apply_default_css=False)
    msg = gr.HTML(elem_id="tk-msg", apply_default_css=False)
    download = gr.DownloadButton("Download thong_ke.html", visible=False, elem_id="tk-download")
    view = gr.HTML(elem_id="tk-view", apply_default_css=False, elem_classes=["tk-root"])
    inputs = [d_nhap, s_nguong, c_task, c_bo, c_ttest, t_timing, f_goi]
    outs = [d_nhap, msg, view, log_view, f_goi]

    def compute(luot_nhap, nguong, tat_ca, chi_bo, ttest, timing, files):
        luot_nhap = clean_args(ctx.runs_root, luot_nhap)
        return thong_ke.tinh(ctx.project_root, luot_nhap, nguong if nguong is not None else thong_ke.NGUONG_SUA, bool(tat_ca), bool(ttest), (timing or "").strip() or None,
                             goi_paths(files), bool(chi_bo))

    def on_refresh(luot_nhap, nguong, tat_ca, chi_bo, ttest, timing, files):
        """Tính lại (chọn tab, sau Set name, sau Add manual entry...): KHÔNG lưu gì; file ở ô nạp chỉ được đọc như trước. Lưu gói là việc của nút Load & Calculate."""
        return _tinh_va_ve(luot_nhap, nguong, tat_ca, chi_bo, ttest, timing, files, luu=False)

    def on_load_calc(luot_nhap, nguong, tat_ca, chi_bo, ttest, timing, files):
        """Nút Load & Calculate: các gói ở ô nạp được LƯU vào outputs\\goi_da_nap (gói hỏng thì không), ô nạp được làm trống, rồi tính từ các thư mục gói đã lưu."""
        return _tinh_va_ve(luot_nhap, nguong, tat_ca, chi_bo, ttest, timing, files, luu=True)

    def _tinh_va_ve(luot_nhap, nguong, tat_ca, chi_bo, ttest, timing, files, luu):
        """Không lưu được (lỗi đĩa) thì vẫn tính trực tiếp từ file tải lên như trước."""
        runs = dot_anh.list_runs(ctx.runs_root)
        luot_nhap = luot_nhap if luot_nhap in runs else ""
        up = gr.update(choices=[("(không)", "")] + [(r, r) for r in runs], value=luot_nhap)
        paths, keep = goi_paths(files), gr.update()
        r = dict(luu=[], moi_hon=[], da_bo=[], co_san=[], loi=[])
        if paths and luu and not ctx.closing:
            try:
                r = thong_ke.luu_goi_nap(ctx.project_root, paths, {p["name"] for p in bang_mat.load_cfg(ctx.project_root)["points"]})
                tinh_tu = [p for p in paths if os.path.basename(p) in {t for t, _w in r["loi"]}]                 # file lỗi: vẫn đưa vào để Log nêu lý do
                keep = gr.update() if r.get("chua_luu") else gr.update(value=None)                                # chép lỗi (đĩa đầy...): giữ ô nạp để bấm lại
            except (bang_mat.BangLoi, OSError) as ex:
                r, tinh_tu = dict(luu=[], moi_hon=[], da_bo=[], co_san=[], loi=[("(lưu gói)", str(ex))]), paths
        else:
            tinh_tu = paths
        try:
            st = compute(luot_nhap, nguong, tat_ca, chi_bo, ttest, timing, tinh_tu)
        except (nap_anh.RunError, bang_mat.BangLoi, toc_do.TocDoLoi, OSError) as ex:
            gr.Warning(str(ex), title="Chưa tính được thống kê")
            da_luu = nap_note(r, files, tinh_xong=False)[0] if luu else ""          # gói đã lưu rồi: vẫn nói, kẻo tưởng mất
            return up, msg_html((da_luu + " " if da_luu else "") + "Chưa tính được thống kê: " + str(ex), "warn"), "", gr.update(), keep
        note, level = nap_note(r, files) if luu else ("", "info")
        chinh, log = thong_ke_html.noi_dung_gon(st)
        return up, msg_html(note, level), f'<div class="tk-root">{chinh}</div>', f'<div class="tk-root">{log}</div>', keep

    def on_export(luot_nhap, nguong, tat_ca, chi_bo, ttest, timing, files):
        if ctx.closing:
            return msg_html(nap_anh.CLOSING_MSG, "warn"), gr.update(visible=False)
        with _LOCK:
            try:
                st = compute(luot_nhap, nguong, tat_ca, chi_bo, ttest, timing, files)
                d, fl = thong_ke.xuat(ctx.project_root, st)
            except (nap_anh.RunError, bang_mat.BangLoi, toc_do.TocDoLoi, ValueError, OSError) as ex:
                gr.Warning(str(ex), title="Chưa xuất được")
                return msg_html(str(ex), "warn"), gr.update(visible=False)
        rel = bang_mat.rel(ctx.project_root, d)
        return (msg_html(f"Đã xuất {rel} ({len(fl)} file: thong_ke.html và {len(fl) - 1} bảng CSV). Không có ảnh mặt trong bản xuất.", "ok"),
                gr.update(value=os.path.join(d, "thong_ke.html"), visible=True))

    # ---------- mục Nhập tay (nhóm manual gán thẳng trong CVAT) ----------
    tay_opts = dict(opts, concurrency_id="thongke_tay")

    def tay_ds():
        try:
            rows = nhap_tay.liet_ke(ctx.project_root)
        except OSError:
            rows = []
        return tay_list_html(rows), gr.update(choices=tay_choices(rows), value=None)

    def on_tay_list():
        return tay_ds()

    def on_tay_open(dot):
        bo_anh = nhom_mod.doc(ctx.project_root)["bo_anh"]
        return (gr.update(value=bo_anh) if bo_anh and not (dot or "").strip() else gr.update(),) + tay_ds()

    def on_tay_add(nguoi, nhom, dot, gio, ngay, files, ghi_chu, goi_files):
        if ctx.closing:
            return (msg_html(nap_anh.CLOSING_MSG, "warn"),) + tay_ds()
        notes = []
        try:
            cfg = bang_mat.load_cfg(ctx.project_root)
            nd = nhap_tay.tao_noi_dung(ctx.project_root, cfg, nguoi, nhom, dot, str(gio or ""), nhan_paths(files), ngay=str(ngay or "").strip(),
                                       ghi_chu=ghi_chu, now=datetime.datetime.now().astimezone(), thong_bao=notes)
            r = nhap_tay.them(ctx.project_root, nd, nguon_them=goi_paths(goi_files))
        except (nhap_tay.NhapTayLoi, bang_mat.BangLoi, OSError) as ex:
            gr.Warning(str(ex), title="Chưa thêm được bản nhập tay")
            return (msg_html(str(ex), "warn"),) + tay_ds()
        bd = nd["bat_dau"]
        moi_mat = nd["giay_phien"] / nd["so_mat"]
        text = (f"Đã thêm {r['ten']} vào outputs\\goi_nhom: {nd['nguoi']}, nhóm {nd['nhom']}, đợt {nd['dot']}, ngày làm {bd[8:10]}/{bd[5:7]}/{bd[:4]}, {nd['so_mat']} mặt, "
                f"{nhap_tay.fmt_giay(nd['giay_phien'])} = {nhap_tay.gio_bang_chu(nd['giay_phien'])} ({thong_ke_html.num(moi_mat, 1)} giây/mặt). "
                "Thống kê bên dưới đã tính cả bản này." + ("" if not notes else " " + " ".join(notes)))
        canh = []
        if moi_mat < nhap_tay.GIAY_MOI_MAT_NGHI:                            # '1:30' (1 phút 30 giây) gõ thay cho 1 giờ 30 phút: giây/mặt vô lý, thống kê sẽ lệch hẳn
            canh.append(f"Chỉ {thong_ke_html.num(moi_mat, 1)} giây/mặt: gần như chắc gõ nhầm thời gian (1:30 là 1 phút 30 giây; 1 giờ 30 phút thì gõ 1:30:00 hoặc 90). "
                        "Kiểm lại, sai thì Remove entry rồi thêm lại.")
        cau_hinh = nhom_mod.nhom_cua(nhom_mod.doc(ctx.project_root), nd["nguoi"])
        if cau_hinh and cau_hinh != nd["nhom"]:
            canh.append(f"config\\nhom_thi_nghiem.json ghi {nd['nguoi']} ở nhóm {cau_hinh}, bản này lại là nhóm {nd['nhom']}: kiểm lại, sai thì Remove entry rồi thêm lại.")
        if canh:
            text += " " + " ".join(canh)
            gr.Warning(" ".join(canh), title="Đã thêm, nhưng kiểm lại")
            return (msg_html(text, "warn"),) + tay_ds()
        if nd["nhom"] == "assisted" and not nd.get("co_nhap"):                # đã ghi gói nhưng thiếu nháp: thông báo là cảnh báo, không phải "ok"
            gr.Warning(f"Bản nhập tay assisted của {nd['nguoi']} không có nháp của đợt {nd['dot']}: NME của nháp và tỉ lệ điểm phải sửa sẽ thiếu mặt của người này. "
                       "Đợt phải là tên lượt đã dựng nháp (thư mục runs\\bo200 thì đợt là bo200).", title="Đã thêm nhưng thiếu nháp")
            return (msg_html(text, "warn"),) + tay_ds()
        return (msg_html(text, "ok"),) + tay_ds()

    def on_tay_remove(ten):
        if ctx.closing:
            return (msg_html(nap_anh.CLOSING_MSG, "warn"),) + tay_ds()
        try:
            r = nhap_tay.bo(ctx.project_root, ten)
        except (nhap_tay.NhapTayLoi, OSError) as ex:
            gr.Warning(str(ex), title="Chưa gỡ được")
            return (msg_html(str(ex), "warn"),) + tay_ds()
        return (msg_html(f"Đã gỡ {r['ten']}: chuyển vào outputs\\goi_nhom\\_da_bo (không xoá; thống kê không đọc thư mục đó, muốn tính lại thì chép file về outputs\\goi_nhom).",
                         "ok"),) + tay_ds()

    # ---------- mục Đặt tên người cho gói (nhóm trưởng) ----------
    ten_opts = dict(opts, concurrency_id="thongke_ten")

    def ten_goi_ds(files):
        """Các gói đang đọc được (outputs\\ket_qua, outputs\\goi_nhom, và ô nạp): (danh sách lựa chọn [(nhãn, mã phiên)], HTML bảng tên đã đặt)."""
        names = {p["name"] for p in bang_mat.load_cfg(ctx.project_root)["points"]}
        quet = thong_ke.doc_nguon_goi(ctx.project_root, goi_paths(files), names)
        m = ten_nguoi.doc(ctx.project_root)
        ch, seen, rows = [], set(), []
        for t, nd in quet["tot"]:
            ph = nd["phien"]
            if ph in seen:
                continue
            seen.add(ph)
            e = m.get(ph)
            bd = str(nd.get("bat_dau") or "")
            bd = f"{bd[8:10]}/{bd[5:7]} {bd[11:16]}" if len(bd) >= 16 else "?"
            chi_tiet = f'{nd.get("nhom") or "?"} · {nd.get("so_mat") or len(nd.get("ket_qua") or [])} mặt · bắt đầu {bd}'
            ch.append((f'{t} · đợt {nd.get("dot") or "-"} · người {e["ten"] + " (đã đặt, gốc " + nd["nguoi"] + ")" if e else nd["nguoi"]} · {chi_tiet}', ph))
            rows.append(f'<tr><td>{html.escape(t)}</td><td>{html.escape(str(nd.get("dot") or "-"))}</td><td>{html.escape(nd["nguoi"])}</td>'
                        f'<td>{html.escape(chi_tiet)}</td><td><b>{html.escape(e["ten"]) if e else "—"}</b></td></tr>')
        table = ('<div class="tk-root"><table class="tk-table"><tr><th>Gói</th><th>Đợt</th><th>Tên trong gói</th><th>Nhóm · số mặt · bắt đầu</th><th>Tên nhóm trưởng đặt</th></tr>'
                 + "".join(rows) + "</table></div>") if rows else \
            '<div class="tk-root"><div class="tk-note">Chưa đọc được gói nào (chọn gói ở ô nạp phía trên hoặc đặt gói vào outputs\\ket_qua).</div></div>'
        return ch, table

    def ds_an_toan(files):
        """ten_goi_ds nhưng không bao giờ ném lỗi (thiếu/hỏng config, file bị khoá): ([], cập nhật trống)."""
        try:
            return ten_goi_ds(files)
        except (bang_mat.BangLoi, OSError):
            return [], gr.update()

    def on_ten_open(files):
        ch, table = ds_an_toan(files)
        return gr.update(choices=ch), table

    def _ten_label(files, phien):
        ch, _t = ten_goi_ds(files)
        return next(((lab, ph) for lab, ph in ch if ph == phien), None), ch

    def on_ten_set(phien, ten, files):
        if ctx.closing:
            return msg_html(nap_anh.CLOSING_MSG, "warn"), gr.update(), gr.update()
        try:
            hit, ch = _ten_label(files, phien)
            if hit is None:
                raise ten_nguoi.TenNguoiLoi("Chưa chọn gói, hoặc gói đó không còn đọc được: chọn lại.")
            nd = next(nd for _t, nd in thong_ke.doc_nguon_goi(ctx.project_root, goi_paths(files), {p["name"] for p in bang_mat.load_cfg(ctx.project_root)["points"]})["tot"]
                      if nd["phien"] == phien)
            moi = ten_nguoi.dat(ctx.project_root, phien, ten, goi=hit[0].split(" · ")[0], goc=nd["nguoi"])
        except (ten_nguoi.TenNguoiLoi, bang_mat.BangLoi, OSError) as ex:
            gr.Warning(str(ex), title="Chưa đặt được tên")
            return msg_html(str(ex), "warn"), gr.update(), ds_an_toan(files)[1]
        ch, table = ds_an_toan(files)
        return msg_html(f"Đã đặt tên {moi} cho gói {hit[0].split(' · ')[0]}; thống kê tính lại bên dưới. File gói gốc không bị sửa.", "ok"), gr.update(choices=ch), table

    def on_ten_clear(phien, files):
        if ctx.closing:
            return msg_html(nap_anh.CLOSING_MSG, "warn"), gr.update(), gr.update()
        try:
            co = ten_nguoi.bo(ctx.project_root, phien) if phien else False
        except OSError as ex:
            gr.Warning(str(ex), title="Chưa bỏ được tên")
            return msg_html(str(ex), "warn"), gr.update(), gr.update()
        ch, table = ds_an_toan(files)
        return (msg_html("Đã bỏ tên đã đặt: gói dùng lại tên người gốc trong gói." if co else "Gói này chưa được đặt tên.", "ok" if co else "info"), gr.update(choices=ch), table)

    def on_goi_bo(phien, files):
        if ctx.closing:
            return msg_html(nap_anh.CLOSING_MSG, "warn"), gr.update(), gr.update()
        try:
            moved = thong_ke.bo_goi_nap(ctx.project_root, phien, {p["name"] for p in bang_mat.load_cfg(ctx.project_root)["points"]}) if phien else []
        except (bang_mat.BangLoi, OSError) as ex:
            gr.Warning(str(ex), title="Chưa gỡ được gói")
            return msg_html(str(ex), "warn"), gr.update(), gr.update()
        ch, table = ds_an_toan(files)
        if not phien:
            return msg_html("Chưa chọn gói.", "warn"), gr.update(choices=ch), table
        if not moved:
            return (msg_html("Gói này không nằm trong outputs\\goi_da_nap (gói của chính máy này trong outputs\\ket_qua, hoặc bản nhập tay: gỡ ở mục Nhập tay), "
                             "hoặc chỉ đang ở ô nạp chưa lưu: không gỡ gì.", "warn"), gr.update(choices=ch, value=None), table)
        con = any(v == phien for _l, v in ch)
        return (msg_html(f"Đã gỡ {', '.join(moved)}: chuyển vào outputs\\goi_da_nap\\_da_bo (không xoá; muốn tính lại thì chép về outputs\\goi_da_nap)."
                         + (" Gói cùng mã phiên vẫn còn ở outputs\\ket_qua hoặc outputs\\goi_nhom (hoặc ở ô nạp) nên thống kê VẪN tính bản đó." if con else ""),
                         "warn" if con else "ok"), gr.update(choices=ch, value=None), table)

    ten_out = [ten_msg, d_ten_goi, ten_list]
    b_goi_bo.click(on_goi_bo, [d_ten_goi, f_goi], ten_out, **ten_opts).then(on_refresh, inputs, outs, **opts)
    b_ten.click(on_ten_set, [d_ten_goi, t_ten, f_goi], ten_out, **ten_opts).then(on_refresh, inputs, outs, **opts)
    b_ten_xoa.click(on_ten_clear, [d_ten_goi, f_goi], ten_out, **ten_opts).then(on_refresh, inputs, outs, **opts)
    acc_ten.expand(on_ten_open, [f_goi], [d_ten_goi, ten_list], **ten_opts)
    f_goi.change(on_ten_open, [f_goi], [d_ten_goi, ten_list], **ten_opts)               # chọn hay bỏ file ở ô nạp: danh sách gói để đặt tên cập nhật theo

    tay_out = [tay_msg, tay_list, d_tay_bo]
    b_tay_add.click(on_tay_add, [d_nguoi, r_nhom, t_dot, t_gio, t_ngay, f_nhan, t_ghichu, f_goi], tay_out, **tay_opts).then(on_refresh, inputs, outs, **opts)
    b_tay_bo.click(on_tay_remove, [d_tay_bo], tay_out, **tay_opts).then(on_refresh, inputs, outs, **opts)
    acc_tay.expand(on_tay_open, [t_dot], [t_dot, tay_list, d_tay_bo], **tay_opts)

    log_opts = dict(show_progress="hidden", api_visibility="private", concurrency_limit=None)
    b_log.click(lambda: gr.update(visible=True), None, log_panel, **log_opts).then(None, None, None, js=LOG_MO_JS)
    b_log_close.click(lambda: gr.update(visible=False), None, log_panel, **log_opts).then(None, None, None, js=LOG_DONG_JS)
    b_refresh.click(on_load_calc, inputs, outs, **opts).then(on_tay_list, None, [tay_list, d_tay_bo], **tay_opts)
    b_export.click(on_export, inputs, [msg, download], **dict(opts, concurrency_id="thongke_xuat"))
    return on_refresh, inputs, outs, opts
