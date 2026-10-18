"""Đồng hồ bấm giờ gán nhãn ở ĐẦU trang rà soát (logic ở dong_ho.py; không import gradio ở đầu module). Không còn tab riêng.

MỖI ĐỢT MỘT ĐỒNG HỒ (QĐ-007): giờ của đợt này không lẫn vào đợt khác. Một chip thấy ở mọi tab: ⏱ mm:ss · trạng thái · người · đợt, kèm MỘT nút Pause/Resume (Start với đợt đang chờ).
Chip theo ĐỢT CỦA TRANG (đang chạy thì theo phiên đang chạy); chip không liệt kê các đợt khác (xem giờ từng đợt ở tab Các đợt). Đồng hồ tự chạy khi bấm Nạp ảnh (auto_start) hoặc Open batch sang đợt chưa có đồng hồ (theo_trang): người là người rà
của trang (tên chữ/số/_/-), nhóm lấy từ config/nhom_thi_nghiem.json, không có thì assisted. Upload & Open: đồng hồ chuyển sang đợt mới; Upload & Continue lúc đang có đồng hồ ở đợt khác: đợt mới
chờ ở 00:00. Chuyển trang sang đợt khác (Open batch...) thì đồng hồ đang chạy đi theo trang (theo_trang). mm:ss chạy mượt bằng JS ở trình duyệt (không gọi server mỗi giây); nguồn sự
thật là đồng hồ phía server, `gr.Timer(15)` chỉ đồng bộ lại. Save timing (timing_<Pk>.csv và gói kết quả của MỘT đợt) hoặc Discard session nằm trong hộp "Đóng trang rà soát?" khi
đang có phiên; có nhiều đợt thì chọn đợt ở ô "Đợt cần lưu / bỏ". Không ảnh mặt, không mạng, không token, không phát file nào (không thêm allowed_paths).
"""
import html
import os
import sys
import types
import uuid

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import cai_dat  # noqa: E402
import dong_ho  # noqa: E402
import dot_anh  # noqa: E402
import nap_anh  # noqa: E402
from dong_ho import DongHo, DongHoLoi, fmt_giay  # noqa: E402
from m28core import nhom as nhom_mod  # noqa: E402

TRANG_THAI_VI = {"chay": "▶ Đang chạy", "tam_dung": "⏸ Tạm dừng", "du_mat": "■ Đủ mặt, chờ lưu", "chua": "• Chưa có phiên"}
DIEU_KIEN_MAC_DINH = "assisted"
OPTS = dict(show_progress="hidden", api_visibility="private", concurrency_limit=1, concurrency_id="dongho")
NUT_DUNG, NUT_TIEP, NUT_BAT_DAU = "Pause", "Resume", "Start"
NUT_BO, NUT_BO_LAN_2 = "Discard session (not saved)", "Click again to discard (not saved)"

CSS = """
/* ---------- chip đồng hồ ở đầu trang (màu lấy từ biến theme) ---------- */
#dh-bar.m28-dh-hide { display: none !important; }
#dh-bar { gap: 6px; flex-wrap: nowrap !important; align-items: center; margin: 2px 0 4px; }
#dh-mini-wrap { padding: 0 !important; min-height: 0 !important; flex: 0 1 auto !important; min-width: 0 !important; width: auto !important; }
.dh-mini { display: inline-flex; align-items: center; gap: 8px; padding: 4px 12px; border-radius: 999px; font-size: 15px; color: var(--body-text-color);
  border: 1px solid var(--border-color-primary); background: var(--block-background-fill); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.dh-mini b { font-size: 16px; white-space: nowrap; flex: none; }
.dh-mini > span { min-width: 0; }
@media (max-width: 600px) { #dh-bar { flex-wrap: wrap !important; } .dh-mini { border-radius: 16px; flex-wrap: wrap; } }
.dh-mini.s-chay { border-color: #16a34a; background: color-mix(in srgb, #16a34a 14%, transparent); }
.dh-mini.s-tam_dung, .dh-mini.s-du_mat { border-color: #d97706; background: color-mix(in srgb, #d97706 16%, transparent); }
.dh-mini.s-chua { opacity: .85; border-style: dashed; }
#dh-mini-btn { flex: 0 0 auto !important; width: auto !important; min-width: 84px !important; min-height: 34px !important; font-weight: 800; }
#dh-luu-btn, #dh-bo-btn { font-weight: 800; }
#dh-dot-dd { flex: 1 1 100% !important; min-width: 100% !important; }
.form:has(> #dh-dot-dd) { order: -1; flex: 1 1 100% !important; min-width: 100% !important; }      /* ô chọn đợt lên dòng đầu của hàng nút (Gradio bọc nó trong .form) */
"""

JS_BODY = r"""
  // ---- Chip đồng hồ ở đầu trang: mm:ss chạy mượt ở trình duyệt, KHÔNG gọi server mỗi giây. HTML mang data-* (giây server lúc dựng, đang chạy hay không, mã lần dựng);
  //      thấy mã mới thì lấy mốc performance.now() (đồng hồ đơn điệu của trình duyệt, không dùng giờ hệ thống nên không lệch khi giờ máy đổi), rồi hiển thị giây_server + (now - mốc)/1000. ----
  if (!window.__m28Dh) {
    window.__m28Dh = { mini: { ver: null, t0: 0, g: 0 } };
    const p2 = (n) => String(n).padStart(2, '0');
    const fmt = (s) => {
      s = Math.max(0, Math.round(s));
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
      return h ? h + ':' + p2(m) + ':' + p2(x) : p2(m) + ':' + p2(x);
    };
    setInterval(() => {
      const el = document.getElementById('dh-mini-time');
      if (!el) { return; }
      const st = window.__m28Dh.mini;
      if (el.dataset.ver !== st.ver) { st.ver = el.dataset.ver; st.t0 = performance.now(); st.g = parseFloat(el.dataset.giay) || 0; }
      if (el.dataset.chay !== '1') { return; }
      const a = fmt(st.g + (performance.now() - st.t0) / 1000);
      if (el.textContent !== a) { el.textContent = a; }
    }, 250);
  }
  // ---- Thanh đồng hồ (#dh-bar: chip + nút Pause/Resume) chỉ hiện ở ba tab Rà soát, Nạp ảnh, Các đợt; tab khác ẩn thanh (đồng hồ vẫn chạy ngầm, không dừng). ----
  if (!window.__m28DhTab) {
    window.__m28DhTab = true;
    const SHOW = ['Rà soát', 'Nạp ảnh', 'Các đợt'];
    let queued = false;
    const sync = () => {
      queued = false;
      const bar = document.getElementById('dh-bar');
      if (!bar) { return; }
      const sel = document.querySelector('#tabs button[role="tab"][aria-selected="true"]');
      const name = sel ? sel.textContent.trim() : '';
      const hide = !!name && SHOW.indexOf(name) < 0;                       // không tìm được tab đang chọn (tab nằm trong menu thu gọn...): cứ hiện
      if (bar.classList.contains('m28-dh-hide') !== hide) { bar.classList.toggle('m28-dh-hide', hide); }
    };
    new MutationObserver(() => { if (!queued) { queued = true; setTimeout(sync, 30); } })
      .observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-selected', 'class'] });
    document.addEventListener('click', () => setTimeout(sync, 80));
    sync();
  }
"""


def e(x):
    return html.escape("" if x is None else str(x), quote=True)


# ---------- HTML thuần (test không cần gradio) ----------
def mini_html(v, ver=None, ly_do="", dot_trang=None):
    """Chip: đang có phiên thì mm:ss của ĐỢT đó (chạy mượt bằng JS) + trạng thái + người + đợt; chưa có thì nói đồng hồ tự chạy khi bấm Nạp ảnh (hoặc lý do chưa chạy được).
    dot_trang: đợt trang đang mở, để nói rõ 'chưa chạy cho đợt X'."""
    ver = ver or uuid.uuid4().hex[:8]
    if not v.get("co_phien"):
        if v.get("hong"):
            ly_do = ly_do or "File trạng thái đồng hồ bị hỏng (đổi tên outputs/timing/dang_chay_<người>.json rồi nạp lại trang)"
        text = ly_do or (f"Đồng hồ chưa chạy cho đợt {dot_trang} · tự chạy khi bấm Nạp ảnh hoặc Open batch" if dot_trang else "Đồng hồ chưa chạy · tự chạy khi bấm Nạp ảnh hoặc Open batch")
        return f'<div id="dh-mini" class="dh-mini s-chua" role="status"><span aria-hidden="true">⏱</span><span>{e(text)}</span></div>'
    st = v["trang_thai"]
    nhan = "⏸ Chờ bắt đầu" if v.get("cho") else TRANG_THAI_VI[st]
    return (f'<div id="dh-mini" class="dh-mini s-{e(st)}" role="status"><span aria-hidden="true">⏱</span>'
            f'<b id="dh-mini-time" data-ver="{ver}" data-giay="{v["giay_phien"]:.3f}" data-chay="{1 if st == "chay" else 0}">{fmt_giay(v["giay_phien"])}</b>'
            f'<span>{e(nhan)} · {e(v["nguoi"])} · {e(v.get("dot") or v.get("task") or "")}</span></div>')


def summary_html(r, nguoi):
    """Tóm tắt sau khi lưu số đo: số mặt, tổng, giây/mặt, đường dẫn tương đối (không đường dẫn tuyệt đối)."""
    t = r["tom_tat"]
    est = " (ước lượng chia đều)" if t["uoc_luong"] else ""
    dot = t.get("dot") or ""
    lines = [f'<b>Đã lưu phiên của {e(nguoi)}{(" (đợt " + e(dot) + ")") if dot else ""}.</b> {t["n_mat"]} mặt ({t["n_tinh_gio"]} mặt tính giờ), tổng {fmt_giay(t["giay_tong"])}, '
             f'{"" if t["giay_moi_mat"] is None else str(t["giay_moi_mat"]).replace(".", ",") + " giây/mặt"}{est}; {t["so_lan_tam_dung"]} lần tạm dừng.',
             f'Dòng bấm giờ: <code>{e(r["csv"])}</code>',
             f'<b>Gói kết quả gửi nhóm trưởng:</b> <code>{e(r["goi"]["zip"])}</code> (kèm <code>{e(os.path.basename(r["goi"]["json"]))}</code> đọc được)']
    if t.get("co_nhan"):
        lines.append(f'Gói có nhãn cuối của {t["n_ket_qua"]} mặt (từ <code>{e(t.get("nhan_file", ""))}</code>)' + (", kèm nháp và điểm đã sửa" if t.get("co_nhap") else "") + ".")
    if r.get("canh_bao"):
        lines.append("Cảnh báo đã ghi kèm: " + e(", ".join(r["canh_bao"])))
    lines += [e(x) for x in r.get("thong_bao", [])]
    return '<div class="dh-ok" role="status">' + "<br>".join(lines) + "</div>"


def vi_hop(text):
    """Thông báo của dong_ho.py viết cho các nút cũ của tab; ở hộp Đóng trang nút tên khác: đổi chữ cho khớp."""
    text = text.replace("Chọn Sửa thời gian / Giữ nguyên, hoặc bấm Xong (lưu) thêm một lần nữa để lưu kèm cảnh báo.", "Bấm Save timing thêm một lần nữa để lưu kèm cảnh báo.")
    return text.replace("dùng Xong hoặc", "dùng Save timing hoặc").replace("Hủy phiên", "Discard session").replace("Xong (lưu)", "Save timing")


def box_html(text, level="warn"):
    return f'<div class="nap-box nap-{"err" if level == "err" else "warn"}" role="alert">{e(text)}</div>'


# ---------- dùng chung với review_app ----------
def get_dh(ctx):
    """DongHo của thư mục dự án (tạo lười, giữ trong ctx)."""
    d = getattr(ctx, "dong_ho", None)
    if d is None or d.root != os.path.abspath(ctx.project_root):
        d = DongHo(ctx.project_root)
        ctx.dong_ho = d
    return d


def default_person(ctx):
    for cand in (ctx.reviewer, cai_dat.get().next_reviewer(ctx.reviewer)):
        if dong_ho.nguoi_hop_le(cand):
            return cand
    return None


def dot_cua_trang(ctx):
    """Tên đợt mà trang đang mở; None khi chưa mở đợt nào (chế độ --nap)."""
    if getattr(ctx, "nap_only", False):
        return None
    return os.path.basename(os.path.normpath(ctx.run_dir)) or None


def phien_cua(ctx):
    """(người, xem) của phiên mà chip theo dõi. Người rà của trang trước: phiên ĐANG CHẠY của người đó; không có thì phiên của ĐỢT TRANG ĐANG MỞ (không mượn phiên của đợt khác, để
    khỏi tính giờ nhầm đợt; xem['cac_dot'] cho biết đợt khác nào có đồng hồ). Người rà của trang chưa có phiên nào thì xem người nào khác đang có phiên; không ai thì (người rà mặc định, xem rỗng)."""
    d = get_dh(ctx)
    mac = default_person(ctx)
    dot_t = dot_cua_trang(ctx)
    for p in ([mac] if mac else []) + [x for x in d.cac_nguoi() if x != mac]:
        try:
            v = d.xem_theo_trang(p, dot_t)
        except Exception:
            continue
        if v.get("co_phien") or v.get("hong") or (p == mac and v.get("cac_dot")):
            return p, v
    return mac, (dict(co_phien=False) if mac is None else d.xem_theo_trang(mac, dot_t))


def cac_phien(ctx):
    """(người, [xem của MỌI phiên của người đó, mỗi đợt một]) cho hộp Đóng trang. Người = người của chip (phien_cua); chưa có phiên nào thì (người, [])."""
    p, _v = phien_cua(ctx)
    if p is None:
        return None, []
    try:
        return p, get_dh(ctx).liet_ke(p)
    except Exception:
        return p, []


def gio_cac_dot(ctx):
    """{đợt: [dict(nguoi, giay, tt)]} cho thẻ đợt ở tab Các đợt: giờ RIÊNG của từng đợt (đợt này không lẫn giờ đợt khác). tt: 'chay' | 'tam_dung' | 'cho' (phiên đang mở, từ file
    trạng thái) hoặc 'da_luu' (phiên đã Save timing, từ timing_<Pk>.csv). Chỉ đọc; người nào lỗi đọc thì bỏ qua."""
    out = {}
    try:
        d = get_dh(ctx)
    except Exception:
        return out
    for p in d.cac_nguoi():
        try:
            for s in d.liet_ke(p):
                out.setdefault(s["dot"], []).append(dict(nguoi=p, giay=s["giay_phien"], tt="chay" if s["chay"] else ("cho" if s["cho"] else "tam_dung")))
            for g in d.gan_day(p, 500):
                if g.get("dot"):
                    out.setdefault(g["dot"], []).append(dict(nguoi=p, giay=g["giay_tong"], tt="da_luu"))
        except Exception:
            continue
    return out


def tu_tam_dung(ctx):
    """Gọi khi đóng trang / Ctrl+C: tự tạm dừng mọi đồng hồ đang chạy, đặt cờ đóng, in một dòng ra terminal cho mỗi phiên. Trả danh sách (người, giờ, đợt)."""
    try:
        d = get_dh(ctx)
        got = d.tu_tam_dung_tat_ca()
        d.closing = True
    except Exception:
        return []
    for nguoi, gio, dot in got:
        print(f"Đồng hồ của {nguoi} đã tạm dừng lúc {gio}{(' (đợt ' + dot + ')') if dot else ''}: mở lại trang rà soát để bấm Resume (hoặc Save timing ở hộp Đóng trang).", flush=True)
    return got


def _trang_thai_chu(s):
    return "đang chạy" if s.get("chay") else ("chờ bắt đầu, chưa tính giờ" if s.get("cho") else "đang tạm dừng")


def close_note(ctx):
    """Dòng thêm vào hộp 'Đóng trang rà soát?' khi đang có đồng hồ. Một đợt: một câu như trước; nhiều đợt: liệt kê mỗi đợt một dòng (giờ riêng). Rỗng nếu không có phiên nào."""
    try:
        p, ses = cac_phien(ctx)
    except Exception:
        return ""
    if not ses:
        return ""
    if len(ses) == 1:
        v = ses[0]
        dang = "đang chạy: đóng trang sẽ <b>tự tạm dừng</b> đồng hồ" if v["trang_thai"] == "chay" else "đang tạm dừng"
        return (f'<div class="nap-box nap-warn" role="alert">Đồng hồ của <b>{e(p)}</b> {dang} ({fmt_giay(v["giay_phien"])}, đợt {e(v.get("dot") or v.get("task") or "")}). '
                "Làm xong thì bấm <b>Save timing</b> để ghi dòng bấm giờ và gói kết quả cho nhóm trưởng; chưa xong thì cứ đóng, mở lại trang bấm Resume.</div>")
    rows = "".join(f'<li>đợt <b>{e(s.get("dot") or s.get("task") or "?")}</b>: {fmt_giay(s["giay_phien"])}, {_trang_thai_chu(s)}'
                   + (" (đóng trang sẽ <b>tự tạm dừng</b>)" if s.get("chay") else "") + "</li>" for s in ses)
    return (f'<div class="nap-box nap-warn" role="alert">Đồng hồ của <b>{e(p)}</b> có {len(ses)} đợt, <b>mỗi đợt tính giờ riêng</b>:<ul>{rows}</ul>'
            "Chọn đợt ở ô bên dưới rồi bấm <b>Save timing</b> để ghi dòng bấm giờ và gói kết quả của đợt đó (mỗi đợt một gói cho nhóm trưởng; lưu lần lượt từng đợt); "
            "chưa xong thì cứ đóng, mở lại trang bấm Resume.</div>")


def nguoi_dot_moi(ctx):
    """Tên người rà của ĐỢT MỚI nạp: tên mà trang của đợt đó sẽ dùng (Upload & Open, Open batch dựng trang mới với ctx.next_reviewer(): tên đã lưu ở tab Cài đặt,
    không có thì tên của trang này). Dùng cho đồng hồ của đợt mới để không có hai đồng hồ (tên cũ và tên mới) cho cùng một đợt."""
    for cand in (cai_dat.get().next_reviewer(ctx.reviewer), ctx.reviewer):
        if dong_ho.nguoi_hop_le(cand):
            return cand
    return None


def _dang_chay_khac(d, nguoi, dot=None):
    """[(người, phiên)] đang chạy của NGƯỜI KHÁC `nguoi` trên máy này (mỗi máy một người làm: chỉ một đồng hồ chạy tại một lúc)."""
    out = []
    for p in d.cac_nguoi():
        if p == nguoi:
            continue
        try:
            out += [(p, s) for s in d.liet_ke(p) if s["chay"]]
        except DongHoLoi:
            continue
    return out


def _dung_khac(d, ds):
    """Tạm dừng các phiên (người, phiên) trong ds; trả câu nói việc đã làm."""
    out = ""
    for p, s in ds:
        try:
            d.tam_dung(p, None, dot=s["dot"])
            out += f" Đồng hồ của {p} ở đợt {s['dot']} tạm dừng ở {fmt_giay(s['giay_phien'])}."
        except (DongHoLoi, OSError):                     # tệp bị khoá (antivirus, OneDrive): bỏ qua, không làm hỏng việc đang làm
            pass
    return out


def auto_start(gr, ctx, run, n_mat=None, mo_ngay=True):
    """Gọi từ tab Nạp ảnh ngay khi bấm Nạp: tạo đồng hồ của ĐỢT `run` (mỗi đợt một phiên riêng) cho người rà của trang. Nhóm lấy từ config/nhom_thi_nghiem.json, không có thì assisted.
      · Upload & Open (mo_ngay=True), hoặc người này chưa có đồng hồ nào: đồng hồ của đợt mới chạy ngay; đồng hồ đang chạy ở đợt khác tự tạm dừng (giữ nguyên giây của nó).
      · Upload & Continue (mo_ngay=False) lúc đã có đồng hồ ở đợt khác: đồng hồ đó giữ nguyên (bạn vẫn đang làm đợt ấy); đợt mới có phiên CHỜ ở 00:00.
      · Đợt này đã có đồng hồ (nạp lại cùng tên): giữ nguyên, không đè, không tự Resume.
    Trả thông báo (cũng hiện ở góc trang nếu có gr) hoặc None khi đang đóng trang."""
    if ctx.closing:
        return None

    def noi(text, warn=False):
        if gr is not None:
            (gr.Warning(text, title="Đồng hồ") if warn else gr.Info(text))
        return text
    try:
        d = get_dh(ctx)
        nguoi = nguoi_dot_moi(ctx)
        if nguoi is None:
            return noi("Chưa chạy đồng hồ: tên người rà không hợp lệ (chỉ chữ không dấu, số và dấu -, bắt đầu bằng chữ hoặc số, tối đa 32 ký tự). Đặt bằng nút Reviewer ở đầu trang (Save name) rồi nạp lại.", warn=True)
        ses = d.liet_ke(nguoi)
        co = {s["dot"]: s for s in ses}
        if run in co:
            tt = "đang chạy" if co[run]["chay"] else ("đang chờ bắt đầu (mở đợt này rồi bấm Start ở đầu trang)" if co[run]["cho"] else "đang tạm dừng (bấm Resume ở đầu trang)")
            return noi(f"Đồng hồ của {nguoi} cho đợt {run} {tt}, giữ nguyên.")
        cond = nhom_mod.nhom_cua(nhom_mod.doc(ctx.project_root), nguoi) or DIEU_KIEN_MAC_DINH
        khac = _dang_chay_khac(d, nguoi)
        cho = (not mo_ngay) and (bool(ses) or bool(khac))           # Upload & Continue lúc đã có đồng hồ (của tên này hay tên khác trên máy): đợt mới chờ
        d.bat_dau(nguoi, cond, dot=run, bo_anh=run, n_mat=n_mat or dong_ho.N_MAT_MAC_DINH, rev=0, cho=cho)
        ctx.dh_started = getattr(ctx, "dh_started", set()) | {run}
        chay = [s for s in ses if s["chay"]] + [s for _p, s in khac]
        if cho:
            giu = f"Đồng hồ đợt {chay[0]['dot']} giữ nguyên." if chay else "Đồng hồ các đợt khác giữ nguyên."
            return noi(f"Đợt {run} có đồng hồ riêng, đang chờ ở 00:00 ({cond}). {giu} Mở đợt {run} (Open batch) thì đồng hồ đang chạy tự chuyển sang đợt này; "
                       "nếu không thì bấm Start ở đầu trang.")
        dung = "".join(f" Đồng hồ đợt {s['dot']} tạm dừng ở {fmt_giay(s['giay_phien'])}." for s in ses if s["chay"]) + _dung_khac(d, khac)
        return noi(f"Đồng hồ của {nguoi} bắt đầu chạy (đợt {run}, {cond})." + dung)
    except DongHoLoi as ex:
        return noi(f"Chưa chạy được đồng hồ: {vi_hop(str(ex))}", warn=True)
    except OSError as ex:                               # outputs\\timing bị khoá hay chỉ đọc: báo, ảnh vẫn nạp
        return noi(f"Chưa chạy được đồng hồ: không ghi được outputs\\timing ({type(ex).__name__}: file đang mở ở chương trình khác hoặc không có quyền). "
                   "Ảnh vẫn nạp bình thường; bấm Start ở đầu trang khi ghi lại được.", warn=True)


def chuyen_ten_mac_dinh(gr, ctx):
    """Sau Save name (chế độ --nap mở bằng menu, không ghi tên ở dòng lệnh): các phiên đồng hồ chưa lưu của tên cũ (mặc định P1, hay tên vừa gõ nhầm) chuyển sang tên mới, để giờ đã đo
    không bị bỏ lại dưới tên cũ (Merge jobs & Finish, Save timing chỉ tìm theo tên mới). Trả câu nói việc đã làm ('' nếu không có gì)."""
    cac = [getattr(ctx, "ten_cu_mac_dinh", None), getattr(ctx, "ten_cu_bo", None)]      # tên mặc định/tên gõ nhầm, và tên cũ có dấu _ của bản trước
    ctx.ten_cu_mac_dinh = ctx.ten_cu_bo = None
    out = []
    for cu in dict.fromkeys(c for c in cac if c):
        if ctx.closing or cu == ctx.reviewer:
            continue
        try:
            moved = get_dh(ctx).chuyen_phien(cu, ctx.reviewer)
        except (DongHoLoi, OSError) as ex:
            loi = vi_hop(str(ex))
            text = (loi if loi.startswith("Chưa chuyển được đồng hồ") else f"Chưa chuyển được đồng hồ của {cu} sang {ctx.reviewer}: {loi}")
            tam_thoi = isinstance(ex, OSError) or loi.startswith("Chưa chuyển được đồng hồ") or "đang bận" in loi   # file bị khoá: thử lại được; tên sai thì không
            if tam_thoi and cu == cac[1]:               # giữ lại để thử lại (nhịp 15 giây của đồng hồ), không bỏ giờ đã đo dưới tên cũ
                ctx.ten_cu_bo = cu
            elif tam_thoi:
                ctx.ten_cu_mac_dinh = cu
            if tam_thoi:
                text += " Trang tự thử lại sau ít giây."
            if gr is not None:
                gr.Warning(text, title="Đồng hồ")
            out.append(text)
            continue
        if moved:
            text = f"Đồng hồ của {cu} ở đợt {', '.join(moved)} chuyển sang {ctx.reviewer} (tên vừa đặt), giữ nguyên giờ đã đo."
            if gr is not None:
                gr.Info(text, title="Đồng hồ")
            out.append(text)
    return " ".join(out)


def theo_trang(ctx):
    """Gọi khi trang vừa chuyển sang một đợt khác trong cùng tiến trình (Open batch, hoặc Upload & Open xong): đồng hồ đang chạy phải đi theo trang, không được chạy tiếp ở đợt cũ.
    Người rà của trang có đồng hồ ĐANG CHẠY ở đợt khác thì tạm dừng đồng hồ đó (giữ giây); đợt của trang đã có phiên (nạp bằng Upload & Continue chẳng hạn) thì phiên đó chạy tiếp.
    Đợt của trang CHƯA có phiên (mở bằng Open batch) thì tạo phiên mới và chạy ngay, trừ khi người này đã lưu gói kết quả cho đợt đó (đã Merge jobs & Finish: không mở đồng hồ thứ hai
    cho đợt đã xong). Không có gì đang chạy và đợt đã có phiên thì không làm gì (không tự Resume). Trả câu nói việc đã làm ('' nếu không làm gì)."""
    if ctx.closing:
        return ""
    try:
        d = get_dh(ctx)
        nguoi, dot = default_person(ctx), dot_cua_trang(ctx)
        if nguoi is None or dot is None:
            return ""
        ses = {s["dot"]: s for s in d.liet_ke(nguoi)}
        dung_khac = _dung_khac(d, _dang_chay_khac(d, nguoi))        # trang mới thuộc về `nguoi`: đồng hồ của tên khác trên máy này tạm dừng (một đồng hồ chạy một lúc)
        cu = next((s for s in ses.values() if s["chay"] and s["dot"] != dot), None)
        if dot in ses and ses[dot].get("cho") and cu is None:
            d.tiep_tuc(nguoi, None, dot=dot)                                  # đợt nạp bằng Upload & Continue (đang chờ 00:00): mở đợt là bắt đầu tính giờ
            return f"Đồng hồ của {nguoi} bắt đầu chạy ở đợt {dot} (đợt đang chờ)." + dung_khac
        if dot not in ses and not any(str(nd.get("dot") or "") == dot for _t, nd in d.goi_da_luu(nguoi)):
            cond = nhom_mod.nhom_cua(nhom_mod.doc(ctx.project_root), nguoi) or DIEU_KIEN_MAC_DINH
            try:
                n_mat = len(dot_anh.image_names(ctx.run_dir)) or dong_ho.N_MAT_MAC_DINH
            except Exception:
                n_mat = dong_ho.N_MAT_MAC_DINH
            d.bat_dau(nguoi, cond, dot=dot, bo_anh=dot, n_mat=min(n_mat, dong_ho.N_MAT_MAX), rev=0)        # phiên chạy ở đợt khác tự tạm dừng
            dung = f" Đồng hồ đợt {cu['dot']} tạm dừng ở {fmt_giay(cu['giay_phien'])}." if cu else ""
            return f"Đồng hồ của {nguoi} bắt đầu chạy ở đợt {dot} ({cond})." + dung + dung_khac
        if cu is None:
            return dung_khac.strip()
        if dot in ses and not ses[dot].get("du_mat"):
            d.tiep_tuc(nguoi, None, dot=dot)                                  # phiên đang chạy ở đợt khác tự tạm dừng
            return f"Đồng hồ của {nguoi} chuyển từ đợt {cu['dot']} (tạm dừng ở {fmt_giay(cu['giay_phien'])}) sang đợt {dot}."
        d.tam_dung(nguoi, None, dot=cu["dot"])
        return (f"Đồng hồ của {nguoi} ở đợt {cu['dot']} tạm dừng ở {fmt_giay(cu['giay_phien'])}: đợt {dot} đã lưu gói kết quả, "
                "không mở đồng hồ mới.")
    except DongHoLoi as ex:
        return f"Chưa chạy được đồng hồ của đợt {dot_cua_trang(ctx)}: {vi_hop(str(ex))}"
    except Exception:
        return ""


# ---------- chip ----------
def chip(gr, demo, ctx):
    """Dựng chip + nút Pause/Resume/Start (đặt ngay dưới thanh Close page). Trả SimpleNamespace(refresh, outs, opts) để các nơi khác (Nạp ảnh, hộp Đóng trang) làm mới chip bằng .then.
    State của nút = (đợt, rev) của phiên đang hiện: nút chỉ tác động đúng phiên đó (tab cũ bấm khi chip đã chuyển sang đợt khác thì bị từ chối)."""
    d = get_dh(ctx)
    dot_t = dot_cua_trang(ctx)
    with gr.Row(elem_id="dh-bar"):
        mini = gr.HTML(mini_html(dict(co_phien=False), dot_trang=dot_t), elem_id="dh-mini-wrap", apply_default_css=False)
        btn = gr.Button(NUT_DUNG, elem_id="dh-mini-btn", size="sm", interactive=False)
    rev_st = gr.State((None, 0))
    timer = gr.Timer(15)
    outs = [mini, btn, rev_st]

    def hien():
        if ctx.closing:
            return dict(mini=mini_html(dict(co_phien=False), ly_do="Đã đóng trang"), btn=gr.update(interactive=False), rev=(None, 0))
        p, v = phien_cua(ctx)
        st = v.get("trang_thai")
        co = bool(v.get("co_phien"))
        return dict(mini=mini_html(v, ly_do="" if p else "Đồng hồ chưa chạy · tên người rà không hợp lệ (đặt bằng nút Reviewer ở đầu trang)", dot_trang=dot_t),
                    btn=gr.update(interactive=co and st in ("chay", "tam_dung"), value=NUT_BAT_DAU if v.get("cho") else (NUT_TIEP if st == "tam_dung" else NUT_DUNG),
                                  variant="primary" if st == "tam_dung" else "secondary"),
                    rev=(v.get("dot") if co else None, v.get("rev", 0)))

    def pack(up):
        return up["mini"], up["btn"], up["rev"]

    def refresh():
        return pack(hien())

    def on_tick():
        if ctx.closing:
            return gr.skip(), gr.skip(), gr.skip()
        if getattr(ctx, "ten_cu_mac_dinh", None) or getattr(ctx, "ten_cu_bo", None):
            chuyen_ten_mac_dinh(None, ctx)                 # lần chuyển đồng hồ sau Save name chưa xong (file bị khoá trên Windows): thử lại, im lặng
        p, v = phien_cua(ctx)
        if p and (v.get("co_phien") or v.get("cac_dot")):
            try:
                d.nhip(p, v.get("dot") if v.get("co_phien") else None)
            except Exception:
                pass
        return pack(hien())

    def on_btn(st_v):
        dot_v, rev_v = st_v if isinstance(st_v, (tuple, list)) and len(st_v) == 2 else (None, st_v)
        p, v = phien_cua(ctx)
        if ctx.closing:
            gr.Warning(nap_anh.CLOSING_MSG, title="Đồng hồ")
        elif not v.get("co_phien"):
            gr.Warning("Chưa có phiên đồng hồ nào cho đợt này (đồng hồ tự chạy khi bấm Nạp ảnh).", title="Đồng hồ")
        elif dot_v is not None and dot_v != v["dot"]:
            gr.Warning("Đồng hồ vừa chuyển sang đợt khác (ở tab khác hoặc do chuyển trang), đã tải lại: kiểm lại rồi bấm lại.", title="Đồng hồ")
        else:
            try:
                (d.tiep_tuc if v.get("trang_thai") == "tam_dung" else d.tam_dung)(p, rev_v or 0, dot=v["dot"])
            except DongHoLoi as ex:
                gr.Warning(str(ex), title="Đồng hồ")
        return pack(hien())

    btn.click(on_btn, [rev_st], outs, **OPTS)
    timer.tick(on_tick, None, outs, **dict(OPTS, concurrency_id="dongho_tick"))
    demo.load(refresh, None, outs, **OPTS)
    return types.SimpleNamespace(refresh=refresh, outs=outs, opts=OPTS, btn=btn, mini=mini)


# ---------- hộp "Đóng trang rà soát?": Save timing / Discard session ----------
def close_buttons(gr, ctx, body, body_fn):
    """Hai nút trong hộp Đóng trang (gọi BÊN TRONG hàng nút của hộp) + ô chọn đợt (chỉ hiện khi người rà có đồng hồ ở từ hai đợt trở lên; CSS đẩy lên dòng đầu của hàng).
    body: gr.HTML của hộp; body_fn(extra_html) dựng lại nội dung hộp kèm đoạn thêm.
    Trả SimpleNamespace(show, show_outs, events): show() chạy sau khi hộp mở (chỉ hiện hai nút khi đang có phiên); events: sự kiện của hai nút để nối .then làm mới chip."""
    b_luu = gr.Button("Save timing", variant="primary", elem_id="dh-luu-btn", visible=False)
    b_bo = gr.Button(NUT_BO, variant="stop", elem_id="dh-bo-btn", visible=False)
    dd = gr.Dropdown(choices=[], value=None, label="Đợt cần lưu / bỏ", elem_id="dh-dot-dd", visible=False, interactive=True)
    ma_st = gr.State("")
    show_outs = [b_luu, b_bo, ma_st, dd]
    hide = gr.update(visible=False)

    def chon_cap_nhat(ses, chon=None):
        """Cập nhật ô chọn đợt: hiện khi từ hai đợt; mặc định đợt chip đang theo (đang chạy, không thì đợt của trang)."""
        if len(ses) < 2:
            return gr.update(visible=False, choices=[], value=None)
        ten = [s["dot"] for s in ses]
        mac = chon if chon in ten else next((s["dot"] for s in ses if s["chay"]), None) or (dot_cua_trang(ctx) if dot_cua_trang(ctx) in ten else ten[0])
        return gr.update(visible=True, choices=[(f"{s['dot'] or s['task'] or '?'} · {fmt_giay(s['giay_phien'])} · {_trang_thai_chu(s)}", s["dot"]) for s in ses], value=mac)

    def dot_da_chon(ses, dot_v):
        """Đợt người dùng chọn; chỉ một đợt thì đợt đó; nhiều đợt mà chưa chọn (hoặc chọn sai) thì đợt chip đang theo."""
        ten = [s["dot"] for s in ses]
        if len(ten) == 1:
            return ten[0]
        if dot_v in ten:
            return dot_v
        return next((s["dot"] for s in ses if s["chay"]), None) or (dot_cua_trang(ctx) if dot_cua_trang(ctx) in ten else ten[0])

    def show():
        _p, ses = cac_phien(ctx)
        co = bool(ses) and not ctx.closing
        return gr.update(visible=co), gr.update(visible=co, value=NUT_BO), "", chon_cap_nhat(ses if co else [])

    def sau_khi(ses_con, chon=None):
        """(nút Save, nút Discard, mã, ô chọn) sau một thao tác: còn phiên thì giữ nút."""
        co = bool(ses_con)
        return gr.update(visible=co), gr.update(visible=co, value=NUT_BO), "", chon_cap_nhat(ses_con, chon)

    def on_luu(dot_v=None):
        d = get_dh(ctx)
        p, ses = cac_phien(ctx)
        if ctx.closing or not ses:
            return (body_fn(box_html("Không có phiên đồng hồ nào để lưu.")),) + sau_khi([])
        dot = dot_da_chon(ses, dot_v)
        v = next(s for s in ses if s["dot"] == dot)
        if not d.tim_nhan(p, v.get("task", ""), "auto") and getattr(ctx, "dh_luu_cho", None) != (v["phien"], v["rev"]):       # chưa có nhãn xuất của đợt này: nhắc gộp job trước, bấm thêm lần nữa thì lưu chỉ thời gian
            ctx.dh_luu_cho = (v["phien"], v["rev"])
            task = v.get("task") or "<task>"
            dau = ("Chưa thấy file nhãn đã xuất của đợt " + (dot or v.get("task", "")) + " của bạn trong raw/ (" + task + "_" + p + "_<DDMM>.xml), nên gói kết quả "
                   "sẽ chỉ có thời gian. ")
            ps = dot_anh.read_push(os.path.join(ctx.runs_root, dot)) if dot and dong_ho.DOT_RE.fullmatch(dot) else None
            if isinstance(ps, dict) and ps.get("trang_thai") == "xong":          # nút Merge jobs & Finish chỉ có trên thẻ của đợt đã đẩy CVAT xong
                cach = ("Cách gọn nhất: đóng hộp này, mở tab Các đợt, bấm Merge jobs & Finish ở thẻ đợt " + (dot or task) + " (gộp các job thành một file rồi dừng "
                        "và lưu đồng hồ trong một lần bấm). Cách khác: chạy python tool\\m28.py collect --task " + task + " --reviewer " + p
                        + " --overwrite rồi bấm Save timing; hoặc bấm Save timing thêm lần nữa để lưu chỉ thời gian.")
            else:
                cach = ("Đợt " + (dot or task) + " chưa đẩy lên CVAT xong nên chưa có nhãn để gộp: đẩy lên CVAT (Push to CVAT), sửa xong rồi bấm Merge jobs & Finish ở "
                        "thẻ đợt (tab Các đợt); hoặc bấm Save timing thêm lần nữa để lưu chỉ thời gian.")
            return (body_fn(box_html(dau + cach)), gr.update(), gr.update(), "", gr.update())
        try:
            r = d.xong_luu(p, v["rev"], True, None, "auto", None, dot=dot)
        except DongHoLoi as ex:
            text = vi_hop(str(ex))
            gr.Warning(text, title="Đồng hồ")
            return (body_fn(box_html(text)), gr.update(), gr.update(), "", gr.update())
        return (body_fn(summary_html(r, p)),) + sau_khi(d.liet_ke(p))

    def on_bo(ma_v, dot_v=None):
        d = get_dh(ctx)
        p, ses = cac_phien(ctx)
        if ctx.closing or not ses:
            return (body_fn(box_html("Không có phiên đồng hồ nào để bỏ.")),) + sau_khi([])
        dot = dot_da_chon(ses, dot_v)
        v = next(s for s in ses if s["dot"] == dot)
        try:
            if not ma_v:                                                       # bấm lần một: nêu sẽ bỏ gì, đổi nhãn nút
                y = d.huy_mo(p, dot=dot)
                return (body_fn(box_html(y["tom_tat"] + " Bấm nút đỏ thêm lần nữa để bỏ phiên (không ghi gì vào timing).", "err")), gr.update(),
                        gr.update(value=NUT_BO_LAN_2), y["ma"], gr.update())
            d.huy_xac_nhan(p, ma_v, "HUY", rev=v["rev"], dot=dot)
        except DongHoLoi as ex:
            gr.Warning(vi_hop(str(ex)), title="Đồng hồ")
            return body_fn(box_html(vi_hop(str(ex)))), gr.update(), gr.update(value=NUT_BO), "", gr.update()
        return (body_fn(f'<div class="dh-ok" role="status">Đã bỏ phiên đồng hồ của {e(p)}{(" (đợt " + e(dot) + ")") if dot else ""}: không ghi dòng nào vào timing '
                        f'(nhật ký huy_{e(p)}.csv có ghi lại).</div>'),) + sau_khi(d.liet_ke(p))

    ev_luu = b_luu.click(on_luu, [dd], [body, b_luu, b_bo, ma_st, dd], **dict(OPTS, concurrency_id="dongho_luu"))
    ev_bo = b_bo.click(on_bo, [ma_st, dd], [body, b_luu, b_bo, ma_st, dd], **dict(OPTS, concurrency_id="dongho_luu"))
    return types.SimpleNamespace(show=show, show_outs=show_outs, events=[ev_luu, ev_bo])
