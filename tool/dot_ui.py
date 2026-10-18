"""Phần Gradio của khung "Đẩy lên CVAT" (tab Rà soát) và tab "Các đợt" (quản lý đợt, xoá mềm, xoá task, Merge jobs & Finish) của trang rà soát M28.

Không import gradio ở đầu module (gradio chỉ đến từ tham số `gr`, như _nap_tab/_review_tab trong review_app.py), nên import module này
không kéo gradio hay torch. Logic thuần nằm ở dot_anh.py (đợt, ảnh, xoá mềm), day_cvat.py (nút đẩy, xác nhận, tiến độ) và gop_job.py (gộp job,
dừng và lưu đồng hồ của đợt); ở đây chỉ nối chúng với Gradio.

An toàn:
  * TRANG KHÔNG GỌI MẠNG: push, xoá task và gộp job chạy bằng tiến trình con (nap_anh.PushJob/DeleteTaskJob/CollectJob); link/token lấy từ cai_dat.py (tab
    Cài đặt hoặc biến môi trường) và chỉ vào tiến trình con qua môi trường của nó. Khung này và tab Các đợt không có ô nhập token;
    token không bao giờ hiện trên trang.
  * Merge jobs & Finish: kết quả của job gộp được xử lý ĐÚNG MỘT LẦN (gop_job.poll: ctx.gop_lock + phase) dù nhiều tab cùng đang tick; nhịp của tab còn
    chạy đến khi kết quả được xử lý (gop_job.needs_poll); nút Cancel ở khung gộp job huỷ tiến trình con (đồng hồ chạy lại như lúc bấm). Còn yêu cầu gộp dở
    (ctx.gop) thì không chuyển đợt, không xoá đợt/task/ảnh của đợt đó (chuyển đợt dựng ctx mới là mất yêu cầu).
  * Tên đợt/ảnh từ trình duyệt chỉ dùng khi là phần tử của danh sách do server tính; mọi lần xoá phải qua hộp xác nhận kèm mã ngẫu nhiên
    (dot_anh.Pending): bấm xác nhận của hộp cũ/trễ không xoá nhầm.
  * Nút Cancel của hộp xác nhận là nút mặc định (có focus khi hộp mở), Esc = Cancel; xoá task phải gõ lại đúng tên và tick ô hiểu hậu quả.
"""
import html
import json
import os
import threading

import cvat_ui
import day_cvat
import dong_ho_ui
import dot_anh
import gop_job
import log_view
import nap_anh
from nap_anh import RunError

ACT_KEYS = ("act", "run", "name", "page", "trash", "entry", "folder", "cvat")
ACTS = {"open", "back", "page", "ra", "delimg", "restore", "empty", "delrun", "restore_run", "purge_run", "finish", "openfolder"}
VIEWS = {"dot": "list", "gop": "gop"}             # nút ẩn m28-go: 'dot' (nút đợt, Switch batch) -> danh sách thẻ; 'gop' (bước 4) -> Gộp & kết thúc của đợt đang mở

# ---------- CSS / JS thêm vào CSS và PAGE_JS của review_app ----------
CSS = """
/* ---------- khung Đẩy lên CVAT (tab Rà soát) ---------- */
#push-panel, #push-msg, #push-prog, #push-result, #dot-root, #dot-msg, #dot-job { padding: 0 !important; }
#btn-push { min-height: 48px; font-size: 16px; font-weight: 800; }
#btn-push:not(:disabled) { background: #2563eb !important; border-color: #1d4ed8 !important; color: #fff !important; opacity: 1 !important; }
#btn-push:disabled { opacity: .5; cursor: not-allowed; }
.push-why { margin-top: 0; }
.push-cause { margin-top: 6px; overflow-wrap: anywhere; }
.push-open { margin: 8px 0 2px; }
.push-open-btn { display: inline-flex; align-items: center; justify-content: center; min-height: 44px; padding: 0 22px; border-radius: 8px; font-size: 16px;
  font-weight: 700; text-decoration: none !important; color: #fff !important; background: #1677ff; border: 1px solid #0f5fd1; cursor: pointer; }
.push-open-btn:hover { background: #0f5fd1; }
.push-open-btn:focus-visible { outline: 3px solid #1677ff; outline-offset: 2px; }
#push-log, #push-log-row { padding: 0 !important; }
#push-log-row { justify-content: flex-end; }
.push-done .m28-info { margin: 6px 0; }
/* ---------- hộp xác nhận (modal) ---------- */
#side { z-index: 2; }                                  /* modal nằm trong cột này: phải nổi trên ảnh nhỏ được chọn (z-index 1) của cột trái */
#center:has(.m28-modal), #side:has(.m28-modal) { z-index: 100001 !important; }   /* cột sticky tạo lớp riêng: đang có hộp (Ca khó, Push to CVAT...) thì cả cột lên trên cùng, phủ cả thanh trên */
.m28-modal { position: fixed !important; inset: 0 !important; z-index: 100001 !important; display: flex !important; align-items: center;
  justify-content: center; padding: 12px !important; overflow: auto; background: rgba(0, 0, 0, .55) !important; border: 0 !important; }
.m28-modal-box { flex: 0 0 auto !important; width: min(560px, 100%) !important; height: auto !important; min-height: 0 !important;
  max-height: calc(100vh - 24px); overflow: auto; gap: 10px !important; padding: 16px !important; box-sizing: border-box;
  background: var(--block-background-fill) !important; border: 1px solid var(--border-color-primary) !important; border-radius: 14px !important;
  box-shadow: 0 12px 40px rgba(0, 0, 0, .35); }
.m28-modal-box > * { flex-shrink: 0 !important; }      /* hộp cao quá màn hình thì cuộn; không co các khối con (Firefox co và cắt mất nội dung, ví dụ Ca khó khi chọn ~20 điểm) */
.modal-title { font-size: 19px; font-weight: 800; overflow-wrap: anywhere; }
.modal-danger { color: #dc2626; }
.m28-modal-btns { gap: 10px; flex-wrap: wrap; margin: 0 !important; width: 100% !important; }
.m28-modal-btns button { min-height: 46px; font-weight: 800; min-width: 120px !important; }
.m28-modal-btns button:focus-visible { outline: 3px solid #2563eb; outline-offset: 2px; }
#push-confirm-ok:not(:disabled) { background: #2563eb !important; border-color: #1d4ed8 !important; color: #fff !important; }
#dot-modal-ok:not(:disabled) { background: #dc2626 !important; border-color: #b91c1c !important; color: #fff !important; }
#dot-modal:has(.modal-finish) #dot-modal-ok:not(:disabled) { background: #0f766e !important; border-color: #115e59 !important; }   /* Merge jobs & Finish: không phải nút xoá */
#dot-modal-ok:disabled { opacity: .45; cursor: not-allowed; }
#push-confirm-title, #dot-modal-title { margin: 0; }
#push-confirm-body, #dot-modal-body { padding: 0 !important; }
.m28-modal-btns button:focus { outline: 3px solid #2563eb; outline-offset: 2px; }
@media (max-width: 600px) { .m28-modal-btns button { flex: 1 1 100% !important; } }
/* ---------- tab Các đợt ---------- */
#tab-dot { padding: 8px 0 0 !important; max-width: 1240px; margin: 0 auto; width: 100%; gap: 10px; }
.dot-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.dot-card { display: flex; flex-direction: column; gap: 6px; padding: 12px 14px; border-radius: 12px; background: var(--block-background-fill);
  border: 1px solid var(--border-color-primary); }
.dot-card-head { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; }
.dot-name { all: unset; cursor: pointer; font-size: 20px; font-weight: 800; color: var(--body-text-color); text-decoration: underline;
  text-decoration-color: var(--border-color-primary); text-underline-offset: 3px; }
.dot-name:hover:not(:disabled), .dot-name:focus-visible { text-decoration-color: #2563eb; outline: 2px solid #2563eb; outline-offset: 2px; border-radius: 4px; }
.dot-name:disabled { cursor: default; text-decoration: none; }
.dot-state { margin-left: auto; font-size: 14px; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--cc, #9ca3af);
  background: color-mix(in srgb, var(--cc, #9ca3af) 17%, transparent); overflow-wrap: anywhere; }
.dot-state.st-ok { --cc: #16a34a; } .dot-state.st-warn { --cc: #d97706; } .dot-state.st-info { --cc: #2563eb; }
.dot-active { font-size: 13px; padding: 1px 8px; border-radius: 999px; background: #2563eb; color: #fff; }
.dot-meta, .dot-extra, .dot-muted { font-size: 14px; color: var(--body-text-color-subdued); }
.dot-note { font-size: 15px; padding: 6px 8px; border-left: 4px solid #9ca3af; background: var(--background-fill-secondary); overflow-wrap: anywhere;
  white-space: pre-wrap; }
.dot-counts { display: flex; flex-wrap: wrap; gap: 6px; }
.dot-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
.dot-btn { cursor: pointer; padding: 7px 14px; min-height: 36px; font-size: 15px; font-weight: 700; border-radius: 8px; color: var(--body-text-color);
  background: var(--background-fill-secondary); border: 1px solid var(--border-color-primary); }
.dot-btn:hover:not(:disabled) { filter: brightness(.95); }
.dot-btn:disabled { opacity: .45; cursor: not-allowed; }
.dot-btn-ra:not(:disabled) { background: #16a34a; border-color: #15803d; color: #fff; }
.dot-btn-push:not(:disabled) { background: #2563eb; border-color: #1d4ed8; color: #fff; }
.dot-btn-finish:not(:disabled) { background: #0f766e; border-color: #115e59; color: #fff; }
.dot-btn-icon { display: inline-flex; align-items: center; justify-content: center; width: 40px; padding: 0; }
.dot-pop { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: flex-start; justify-content: center; padding: 28px 12px; overflow: auto;
  background: rgba(0, 0, 0, .6); }
.dot-pop-box { width: min(1100px, 100%); box-sizing: border-box; padding: 16px 18px; border-radius: 14px; background: var(--block-background-fill);
  border: 1px solid var(--border-color-primary); box-shadow: 0 12px 40px rgba(0, 0, 0, .45); }
.dot-pop .dot-gridtitle { display: inline-flex; align-items: center; gap: 8px; }
.dot-pop-x { margin-left: auto; }
.dot-gop-view { display: flex; flex-direction: column; gap: 10px; max-width: 760px; padding: 14px 16px; border-radius: 12px;
  background: var(--block-background-fill); border: 1px solid var(--border-color-primary); }
.dot-gop-view .dot-gridtitle { font-size: 19px; }
.gop-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.gop-row { display: flex; gap: 10px; align-items: baseline; font-size: 15px; overflow-wrap: anywhere; }
.gop-mark { flex: none; width: 20px; text-align: center; font-weight: 800; }
.gop-ok .gop-mark { color: #16a34a; } .gop-todo { color: var(--body-text-color-subdued); }
.gop-note { font-size: 15px; line-height: 1.5; }                 /* chỉ dẫn việc tiếp theo: KHÔNG dùng .dot-muted (giao_dien ẩn mọi ghi chú xám) */
a.dot-btn { display: inline-flex; align-items: center; text-decoration: none; }
.dot-btn-folder { display: inline-flex; align-items: center; gap: 6px; }
.dot-btn-folder .dot-ic { flex: none; }
.dot-gop { font-size: 14px; padding: 4px 8px; border-radius: 8px; border: 1px solid #0f766e; overflow-wrap: anywhere;
  background: color-mix(in srgb, #0f766e 10%, transparent); }
.gop-done .dh-ok { margin-top: 8px; }
.gop-folders { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px; }
.gop-warn { color: #d97706; }
.dot-btn-danger { color: #dc2626; border-color: #dc2626; background: color-mix(in srgb, #dc2626 8%, transparent); }
.dot-btn:focus-visible, .dot-trash:focus-visible { outline: 3px solid #2563eb; outline-offset: 2px; }
.dot-gridhead { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin-bottom: 6px; }
.dot-gridtitle { font-size: 17px; }
.dot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin: 10px 0; }
.dot-thumb { position: relative; border-radius: 10px; overflow: hidden; border: 3px solid var(--tc, #9ca3af); background: var(--background-fill-secondary); }
.dot-thumb.st-nhan { --tc: #16a34a; } .dot-thumb.st-gan_tay { --tc: #d97706; } .dot-thumb.st-bo { --tc: #dc2626; }
.dot-thumb.st-khong_thay_mat, .dot-thumb.st-khong_dung_duoc { --tc: #6b7280; }
.dot-thumb img { display: block; width: 100%; aspect-ratio: 1; object-fit: cover; }
.dot-badge { position: absolute; left: 4px; top: 4px; font-size: 13px; font-weight: 800; padding: 1px 7px; border-radius: 6px; color: #fff;
  background: var(--tc, #6b7280); }
.dot-cap { padding: 3px 6px 5px; font-size: 13px; line-height: 1.25; overflow-wrap: anywhere; }
.dot-orig { color: var(--body-text-color-subdued); }
.dot-trash { position: absolute; right: 5px; top: 5px; display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
  border-radius: 8px; border: 0; cursor: pointer; background: #dc2626; color: #fff; opacity: 0; transition: opacity .12s; }
.dot-thumb:hover .dot-trash, .dot-thumb:focus-within .dot-trash, .dot-trash:focus-visible { opacity: 1; }
@media (hover: none) { .dot-trash { opacity: 1; } }
.dot-pager { display: flex; align-items: center; justify-content: center; gap: 12px; margin: 6px 0 10px; }
.dot-section { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; padding: 10px 12px; border-radius: 10px;
  border: 1px solid var(--border-color-primary); background: var(--block-background-fill); }
.dot-section-title { font-weight: 800; font-size: 15px; }
.dot-cvat { border-color: #2563eb; }
.dot-del-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 12px; font-size: 15px; overflow-wrap: anywhere; }
.dot-del-row > span:last-child { display: flex; gap: 8px; }
.dot-cvat-row, .dot-del-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; }
.dot-cvat .dot-del-bar { padding-top: 10px; border-top: 1px dashed var(--border-color-primary); }
.dot-del-opt { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; cursor: pointer; overflow-wrap: anywhere; }
.dot-del-opt input { width: 16px; height: 16px; flex: none; accent-color: #dc2626; cursor: inherit; }
.dot-del-opt.off { opacity: .5; cursor: not-allowed; }
.dot-pop .dot-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }       /* 6 cột × 3 hàng mỗi trang (dot_anh.GRID_COLS, GRID_ROWS) */
@media (max-width: 900px) { .dot-pop .dot-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
#dot-gop-cancel { max-width: 160px; min-height: 40px; font-weight: 800; }
#dot-job:not(:has(.html-container > div > *)), #dot-msg:not(:has(.html-container > div > *)), #push-msg:not(:has(.html-container > div > *)), #push-prog:not(:has(.html-container > div > *)),
#push-result:not(:has(.html-container > div > *)), #push-panel:not(:has(.html-container > div > *)) { display: none; }
@media (max-width: 600px) { .dot-cards { grid-template-columns: 1fr; } .dot-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dot-state { margin-left: 0; } }
"""

JS_BODY = r"""
  // ---- Tab "Các đợt" và hộp xác nhận (modal): chạy một lần, uỷ quyền sự kiện vì HTML được vẽ lại ----
  if (!window.__m28Dot) {
    window.__m28Dot = true;
    const setValue = (el, v) => {
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    };
    const sendAct = (d) => {
      const cvat = d.act === 'delrun' && document.querySelector('#dot-root .dot-del-cvat:checked') ? '1' : '';   // ô tick cạnh Delete batch
      const payload = JSON.stringify({ act: d.act || '', run: d.run || '', name: d.name || '', page: d.page || '',
                                       trash: d.trash || '', entry: d.entry || '', folder: d.folder || '', cvat: cvat });
      const box = document.querySelector('#dot-act textarea, #dot-act input');
      const go = document.getElementById('dot-act-go');
      if (!box || !go) { return; }
      setValue(box, payload);
      setTimeout(() => go.click(), 40);
    };
    document.addEventListener('click', (e) => {
      const t = e.target;
      if (t && t.classList && t.classList.contains('dot-pop') && t.closest('#dot-root')) { e.preventDefault(); sendAct({ act: 'back' }); return; }   // bấm nền tối: đóng popup quản lý đợt
      const el = t && t.closest ? t.closest('#dot-root [data-act], .gop-done [data-act]') : null;
      if (!el || el.disabled) { return; }
      e.preventDefault();
      sendAct(el.dataset);
    });
    const modals = () => Array.from(document.querySelectorAll('.m28-modal'));
    const decorate = () => {
      modals().forEach((m) => {
        if (m.dataset.m28) { return; }
        m.dataset.m28 = '1';
        m.setAttribute('role', 'dialog');
        m.setAttribute('aria-modal', 'true');
        setTimeout(() => {                                  // nút Cancel là mặc định: có focus khi hộp mở (tìm sau khi con đã dựng xong)
          const t = m.querySelector('.modal-title');
          if (t && t.id) { m.setAttribute('aria-labelledby', t.id); }
          const cancel = m.querySelector('button[id$="-cancel"]');
          if (cancel) { cancel.focus(); }
        }, 120);
      });
    };
    new MutationObserver(decorate).observe(document.body, { childList: true, subtree: true });
    decorate();
    document.addEventListener('keydown', (e) => {
      const ms = modals();
      if (!ms.length) {                                    // không có hộp xác nhận: Esc đóng popup quản lý đợt (nếu đang thấy)
        const x = e.key === 'Escape' ? document.querySelector('#dot-root .dot-pop .dot-pop-x') : null;
        if (x && x.getClientRects().length) { e.preventDefault(); x.click(); }
        return;
      }
      const m = ms[ms.length - 1];
      if (e.key === 'Escape') {                            // Esc = Cancel
        e.preventDefault(); e.stopPropagation();
        const c = m.querySelector('button[id$="-cancel"]');
        if (c) { c.click(); }
        return;
      }
      if (e.key === 'Tab') {                               // giữ focus trong hộp
        const f = Array.from(m.querySelectorAll('button, input, textarea, select, [tabindex]'))
          .filter((x) => !x.disabled && x.offsetParent !== null && x.getAttribute('tabindex') !== '-1');
        if (!f.length) { return; }
        const first = f[0], last = f[f.length - 1];
        if (!m.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
        else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }, true);
  }
"""


def _e(x):
    return html.escape(str(x), quote=True)


def box(text, level="info"):
    return f'<div class="m28-msg m-{level}" role="status">{_e(text)}</div>' if text else ""


def parse_action(raw):
    """Chuỗi JSON từ trình duyệt -> dict chỉ gồm khoá ACT_KEYS (chuỗi), hoặc None nếu không hợp lệ. Giá trị chưa được tin."""
    try:
        d = json.loads(raw or "")
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("act") not in ACTS:
        return None
    return {k: (d.get(k) if isinstance(d.get(k), str) else "") for k in ACT_KEYS}


# ---------- nút "Mở thư mục" ở thẻ kết quả gộp job ----------
def raw_folder_of(project_root, run_dir):
    """Thư mục chứa file nhãn gộp của đợt (raw/<task>/ hoặc raw/) theo gop_job.json; None nếu đợt chưa gộp, đường dẫn lạ hoặc nằm ngoài raw/."""
    g = dot_anh.read_gop(run_dir)
    if not dot_anh.is_merged(g):
        return None
    parts = [x for x in g["xml"].replace("\\", "/").split("/") if x]
    if len(parts) < 2 or parts[0] != "raw" or any(x in (".", "..") for x in parts):
        return None
    raw = os.path.realpath(os.path.join(project_root, "raw"))
    d = os.path.realpath(os.path.join(project_root, *parts[:-1]))
    return d if (d == raw or d.startswith(raw + os.sep)) and os.path.isdir(d) else None


FOLDERS = {"ket_qua": os.path.join("outputs", "ket_qua"), "raw": "raw", "timing": os.path.join("outputs", "timing")}      # chỉ ba thư mục cố định của dự án; trình duyệt chỉ gửi khoá


def open_folder(path, platform=None, popen=None, startfile=None):
    """Mở thư mục `path` bằng trình quản lý file của máy (trang chỉ chạy ở 127.0.0.1 nên là máy của chính người dùng). Trả (ok, câu nói). Không bao giờ ném lỗi."""
    import subprocess
    import sys as _sys
    plat = platform or _sys.platform
    try:
        if plat.startswith("win"):
            (startfile or os.startfile)(path)                                      # noqa: S606 (đường dẫn do server tính, không do trình duyệt gửi)
        else:
            cmd = ["open", path] if plat == "darwin" else ["xdg-open", path]
            (popen or subprocess.Popen)(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True, f"Đang mở thư mục {path} bằng trình quản lý file của máy."
    except (OSError, AttributeError) as e:
        return False, f"Không mở được thư mục tự động ({type(e).__name__}). Mở tay: {path}"


# ---------- khung "Đẩy lên CVAT" trong tab Rà soát ----------
def chan_khi_chua_dat_ten(ctx, viec):
    """Trang mở không ghi tên và chưa lưu tên nào (tên mặc định P1): từ chối `viec`, vì tên đi vào file kết quả, đồng hồ và gói gửi nhóm trưởng."""
    import cai_dat                                          # nạp lười (chỉ thư viện chuẩn)
    if getattr(ctx, "reviewer_auto", False) and not cai_dat.get().default_reviewer():
        raise RunError(f"Chưa đặt tên người rà (đang là tên mặc định {ctx.reviewer}): bấm nút Reviewer ở đầu trang, gõ tên của bạn rồi bấm Save name, "
                       f"sau đó {viec} lại. Tên đi vào file kết quả và file nhãn gộp.")


def chot_luot(store):
    if store.finished:
        return False
    store.write_done()
    store.finished = True
    return True


def push_panel(gr, demo, store, ctx):
    """Dựng khung Đẩy lên CVAT TRONG ngữ cảnh hiện tại (cột phải, dưới nút Xong). Trả hàm hook(event) để chạy lại khung sau mỗi sự kiện rà,
    và (hàm làm mới, danh sách output) để tab.select gọi."""
    job, dj = ctx.push_job, ctx.del_job
    pending = ctx.push_pending

    panel = gr.HTML(elem_id="push-panel", apply_default_css=False)
    b_push = gr.Button("Push to CVAT", elem_id="btn-push", interactive=False)
    msg = gr.HTML(elem_id="push-msg", apply_default_css=False)
    prog = gr.HTML(elem_id="push-prog", apply_default_css=False)
    with gr.Row(elem_id="push-log-row"):                # log đẩy lên CVAT mở trong popup như Log prepare của tab Nạp ảnh
        b_log = gr.Button("Log push", elem_id="push-log-open", size="sm", visible=False)
    with gr.Column(visible=False, elem_id="push-log-pop", elem_classes=["m28-modal"]) as log_pop:
        with gr.Column(elem_classes=["m28-modal-box", "nap-log-box"]):
            gr.HTML('<div class="lg-title-row"><div class="modal-title">Log đẩy lên CVAT</div><span class="lg-note">token đã được lọc khỏi log</span></div>',
                    apply_default_css=False)
            log_tb = gr.HTML(elem_id="push-log", apply_default_css=False)
            with gr.Row(elem_classes=["m28-modal-btns"]):
                b_log_close = gr.Button("Close", elem_id="push-log-pop-cancel")
    b_cancel = gr.Button("Cancel", variant="stop", elem_id="push-cancel", visible=False)
    result = gr.HTML(elem_id="push-result", apply_default_css=False)
    token_tb = gr.Textbox(visible="hidden", elem_id="push-token")
    with gr.Column(visible=False, elem_id="push-confirm", elem_classes=["m28-modal"]) as modal:
        with gr.Column(elem_classes=["m28-modal-box"]):
            confirm_body = gr.HTML(elem_id="push-confirm-body", apply_default_css=False)
            with gr.Row(elem_classes=["m28-modal-btns"]):
                b_ok = gr.Button("Push to CVAT", variant="primary", elem_id="push-confirm-ok")
                b_no = gr.Button("Cancel", elem_id="push-confirm-cancel")
    timer = gr.Timer(1.0, active=False)
    outs = [panel, b_push, msg, prog, log_tb, b_log, b_cancel, result, timer]
    run = os.path.basename(os.path.normpath(store.run_dir))

    def any_running():
        return ctx.push_job.running or ctx.del_job.running or ctx.job.running or ctx.smoke_job.running or ctx.collect_job.running

    def model():
        return day_cvat.push_model(store.run_dir, store.reviewer, ctx.project_root, remaining=store.progress()["remaining"],
                                   job_running=any_running())

    def render(note=""):
        m = model()
        snap = job.snapshot()
        mine = snap["run"] == run and snap["state"] != "chua"
        other = ""
        for j, what in ((job, "Đang đẩy"), (dj, "Đang xoá task của"), (ctx.collect_job, "Đang gộp job CVAT của")):
            s = j.snapshot()
            if s["state"] == "dang_chay" and (s["run"] != run or j is ctx.collect_job):
                other = box(f"{what} lượt {s['run']}: xem tab Các đợt.", "info")
        res = ""
        if mine and snap["state"] == "loi":
            res = day_cvat.error_html(snap, dot_anh.read_push(store.run_dir), run)
        elif mine and snap["state"] == "da_huy":
            res = day_cvat.cancelled_html(dot_anh.read_push(store.run_dir), run)
        running = snap["state"] == "dang_chay" and snap["run"] == run
        lines = list(snap["lines"]) if mine else []
        return (day_cvat.panel_html(m), gr.update(interactive=m["enabled"] and not running, visible=m["kind"] != "done" and not running),
                (note and box(note, "warn")) or other, day_cvat.progress_html(snap) if mine else "",
                log_view.log_html(lines, "Chưa có log đẩy lên CVAT trong phiên này."), gr.update(visible=bool(lines)),
                gr.update(visible=running, interactive=running and not snap.get("cancelling")),
                res, gr.Timer(active=job.running))

    def on_refresh():
        return render()

    def on_click():
        m = model()
        if ctx.closing:
            return render(nap_anh.CLOSING_MSG) + (gr.update(visible=False), "", "")
        if not m["enabled"]:
            gr.Warning(m["reason"] or "Chưa đẩy được.", title="Chưa đẩy được")
            return render(m["reason"]) + (gr.update(visible=False), "", "")
        try:
            chan_khi_chua_dat_ten(ctx, "bấm Push to CVAT")
        except RunError as e:
            gr.Warning(str(e), title="Chưa đặt tên")
            return render(str(e)) + (gr.update(visible=False), "", "")
        it = pending.open(kind="push", run=run)
        return render() + (gr.update(visible=True), day_cvat.confirm_html(m), it["token"])

    def on_confirm(token):
        it = pending.take(token)
        close = (gr.update(visible=False), "", "")
        if ctx.closing:
            return render(nap_anh.CLOSING_MSG) + close
        if it is None or it.get("run") != run:
            return render("Yêu cầu xác nhận đã cũ hoặc không còn hiệu lực: bấm Push to CVAT lại.") + close
        m = model()
        if not m["enabled"]:
            return render(m["reason"] or "Chưa đẩy được.") + close
        if ctx.switch_to is not None:
            return render("Trang đang chuyển sang đợt khác.") + close
        try:
            chot_luot(store)
        except (ValueError, OSError) as e:
            return render(f"Chưa chốt được lượt này nên chưa đẩy: {e}") + close
        try:
            job.start(run, ctx.runs_root, ctx.project_root, store.reviewer, m["task"], images=m.get("images_dir"))
        except RunError as e:
            return render(str(e)) + close
        return render() + close

    def on_dismiss():
        pending.cancel()
        return render() + (gr.update(visible=False), "", "")

    def on_job_cancel():
        job.cancel()
        return render("Đã huỷ việc đẩy lên CVAT.")

    opts = dict(show_progress="hidden", api_visibility="private", concurrency_limit=1)
    modal_outs = outs + [modal, confirm_body, token_tb]
    b_push.click(on_click, None, modal_outs, **dict(opts, concurrency_id="push"))
    ev_ok = b_ok.click(on_confirm, [token_tb], modal_outs, **dict(opts, concurrency_id="push"))
    b_no.click(on_dismiss, None, modal_outs, **dict(opts, concurrency_id="push"))
    b_cancel.click(on_job_cancel, None, outs, **dict(opts, concurrency_id="push_huy"))
    b_log.click(lambda: gr.update(visible=True), None, log_pop, **dict(opts, concurrency_id="push_log"))
    b_log_close.click(lambda: gr.update(visible=False), None, log_pop, **dict(opts, concurrency_id="push_log"))
    timer.tick(on_refresh, None, outs, **dict(opts, concurrency_id="push_tick"))
    demo.load(on_refresh, None, outs, **dict(opts, concurrency_id="push_view"))

    def hook(ev):
        ev.then(on_refresh, None, outs, **dict(opts, concurrency_id="push_view"))
    return hook, on_refresh, outs, opts, ev_ok


# ---------- tab "Các đợt" ----------
def dot_tab(gr, demo, store, ctx, deps):
    """Dựng NỘI DUNG tab Các đợt (gọi trong `with gr.Tab(...)`). deps: dict(Store, switch_js, run_name[, dh]); dh = chip đồng hồ (dong_ho_ui.chip) để
    chip cập nhật ngay sau mỗi sự kiện của tab (Merge jobs & Finish dừng và lưu đồng hồ). Trả (hàm làm mới, outputs, opts) để tab.select làm mới danh sách."""
    Store, switch_js, run_name = deps["Store"], deps["switch_js"], deps["run_name"]
    step_of = deps.get("step_of") or (lambda: "ra")      # bước đợt đang mở đang ở (review_app.current_step): 'gop' thì tab mở ở trang Gộp & kết thúc
    dh = deps.get("dh")
    pending = ctx.dot_pending
    active_dir = store.run_dir if store is not None else None

    job_html = gr.HTML(elem_id="dot-job", apply_default_css=False)
    b_gop_cancel = gr.Button("Cancel", variant="stop", elem_id="dot-gop-cancel", size="sm", visible=False)     # huỷ job gộp đang chạy (Merge jobs & Finish)
    msg = gr.HTML(elem_id="dot-msg", apply_default_css=False)
    root = gr.HTML(elem_id="dot-root", apply_default_css=False)
    act_tb = gr.Textbox(visible="hidden", elem_id="dot-act")
    act_go = gr.Button(visible="hidden", elem_id="dot-act-go")
    target = gr.Textbox(visible="hidden", elem_id="dot-target")
    token_tb = gr.Textbox(visible="hidden", elem_id="dot-modal-token")
    ses = gr.State(None)
    timer = gr.Timer(1.0, active=False)
    with gr.Column(visible=False, elem_id="dot-modal", elem_classes=["m28-modal"]) as modal:
        with gr.Column(elem_classes=["m28-modal-box"]):
            body = gr.HTML(elem_id="dot-modal-body", apply_default_css=False)
            typed = gr.Textbox(label="Gõ lại đúng tên để xác nhận", elem_id="dot-modal-typed", visible=False, max_lines=1)
            check = gr.Checkbox(label="Tôi hiểu nhãn đã sửa trong CVAT sẽ mất", elem_id="dot-modal-check", visible=False)
            with gr.Row(elem_classes=["m28-modal-btns"]):
                b_ok = gr.Button("Delete", variant="stop", elem_id="dot-modal-ok")
                b_no = gr.Button("Cancel", elem_id="dot-modal-cancel")

    outs = [root, ses, msg, job_html, timer, modal, body, typed, check, b_ok, token_tb, target, b_gop_cancel]
    opts = dict(show_progress="hidden", api_visibility="private", concurrency_limit=1)

    def new_ses():
        return dict(view="gop" if store is not None and step_of() == "gop" else "list", run=None, page=0, was_running=False)

    def ensure(s):
        return s if isinstance(s, dict) and "view" in s else new_ses()

    def any_running():
        return ctx.push_job.running or ctx.del_job.running or ctx.job.running or ctx.smoke_job.running or ctx.collect_job.running

    def timer_on(running=None):
        """Nhịp của tab chạy khi có việc chạy, VÀ khi job gộp đã dừng mà kết quả chưa xử lý (tiến trình con có thể thoát ngay trước một lần vẽ)."""
        return (any_running() if running is None else running) or gop_job.needs_poll(ctx) or bool(getattr(ctx, "dot_trash_after", None))

    def gop_cancel_update():
        s = ctx.collect_job.snapshot()
        running = s["state"] == "dang_chay"
        return gr.update(visible=running, interactive=running and not s.get("cancelling"))

    def is_active(run):
        return bool(active_dir) and os.path.realpath(os.path.join(ctx.runs_root, run)) == os.path.realpath(active_dir)

    def job_banner():
        out = []
        for j, what in ((ctx.push_job, "Đẩy lên CVAT"), (ctx.del_job, "Xoá task trên CVAT")):
            s = j.snapshot()
            if s["state"] == "chua":
                continue
            out.append(day_cvat.progress_html(s, what))
            if s["state"] == "loi":
                out.append(day_cvat.error_html(s, dot_anh.read_push(s["run_dir"]) if s["run_dir"] else None, s["run"]))
            elif s["state"] == "da_huy":
                out.append(day_cvat.cancelled_html(dot_anh.read_push(s["run_dir"]) if s["run_dir"] else None, s["run"], kind=s.get("kind") or "push"))
        s = ctx.collect_job.snapshot()
        if s["state"] == "dang_chay":                       # gộp job: chỉ hiện khi đang chạy, kèm nút Cancel (#dot-gop-cancel) ngay dưới; kết quả, lỗi hiện ở #dot-msg
            label, frac = gop_job.progress(s["lines"])
            out.append(day_cvat.progress_html(s, "Gộp job", label=label, frac=frac))
        return "".join(out[-3:])

    def gop_view():
        """Trang Gộp & kết thúc: chỉ đợt đang mở (đợt đã bị xoá ngoài trang thì như chưa mở đợt nào)."""
        if not active_dir or not os.path.isdir(active_dir):
            return dot_anh.gop_view_html(None)
        info = dot_anh.run_info(active_dir, ctx.reviewer)
        m = cvat_ui.model(store, ctx) if store is not None else {}
        jobs = dict(done=m["done"], total=m["total"], all_done=m["all_done"]) if m.get("kind") == "theo_doi" else None
        return dot_anh.gop_view_html(info, jobs)

    def build_root(s):
        if s["view"] == "gop":
            return gop_view()
        pop = ""
        if s["view"] == "grid" and s["run"]:                # popup quản lý đợt (nút bánh răng) đè lên danh sách thẻ
            try:
                run_dir = dot_anh.valid_run(ctx.runs_root, s["run"])
            except RunError:
                s["view"], s["run"] = "list", None
            else:
                info = dot_anh.run_info(run_dir, ctx.reviewer)
                pop = dot_anh.grid_html(info, dot_anh.image_rows(run_dir, ctx.reviewer), s["page"], dot_anh.list_trash(run_dir),
                                        active=is_active(s["run"]))
        infos = [dot_anh.run_info(os.path.join(ctx.runs_root, r), ctx.reviewer) for r in dot_anh.list_runs(ctx.runs_root)]
        gio = dong_ho_ui.gio_cac_dot(ctx)                   # giờ RIÊNG của từng đợt (đồng hồ ở đầu trang tính mỗi đợt một phiên)
        for i in infos:
            i["gio"] = gio.get(i["name"], [])
        return dot_anh.list_html(infos, run_name(active_dir) if active_dir else None, dot_anh.list_deleted_runs(ctx.runs_root)) + pop

    NO_MODAL = (gr.update(visible=False), "", gr.update(visible=False, value=""), gr.update(visible=False, value=False),
                gr.update(interactive=True), "")

    def render(s, note="", level="info", modal=None, switch="", msg_html=None):
        s = ensure(s)
        s["was_running"] = any_running()                    # lần tick đầu thấy việc đã xong thì vẫn vẽ lại danh sách
        if modal is None:
            m = NO_MODAL
        else:
            m = (gr.update(visible=True), modal["body"], gr.update(visible=modal.get("typed", False), value="", label=modal.get("typed_label", "")),
                 gr.update(visible=modal.get("check", False), value=False),
                 gr.update(interactive=modal.get("ok_enabled", True), value=modal.get("ok_label", "Delete")), modal["token"])
        return (build_root(s), s, box(note, level) if msg_html is None else msg_html, job_banner(), gr.Timer(active=timer_on()), *m, switch,
                gop_cancel_update())

    def modal_for(kind, **kw):
        it = pending.open(kind=kind, **kw)
        return it

    # ---------- Merge jobs & Finish (logic ở gop_job.py) ----------
    def dh_of():
        return dong_ho_ui.get_dh(ctx)

    def finish_model(run_dir):
        return gop_job.finish_model(run_dir, ctx.project_root, dong_ho_ui.default_person(ctx), dh_of(), job_running=any_running())

    def force_modal(s, g, note="", alert=""):
        """Hộp thứ hai (còn job chưa Finish the job trên CVAT): Merge anyway / Cancel = quay lại CVAT. alert: câu cảnh báo hiện TRONG hộp (lớp phủ che #dot-msg)."""
        it = modal_for("finish_force", run=g["run"], task=g["task"], person=g["person"])
        gop_job.remember_modal(ctx, it["token"])           # Cancel của hộp này luôn quay lại CVAT được, dù tab khác thay yêu cầu xác nhận dùng chung
        body = (f'<div class="nap-box nap-warn" role="alert">{_e(alert)}</div>' if alert else "") + gop_job.pending_html(g, g.get("pending") or [])
        return render(s, note or alert, "warn", modal=dict(body=body, token=it["token"], ok_label="Merge anyway"))

    def finish_poll(s):
        """Job gộp vừa dừng: xử lý ĐÚNG MỘT LẦN (gop_job.poll) rồi trả bộ output đã vẽ; không có gì thì None."""
        r = gop_job.poll(ctx, dh_of())
        if r is None:
            return None
        if r["kind"] == "hoi":
            g = gop_job.waiting(ctx)
            if g is not None:
                return force_modal(s, g)
            return render(s)
        if r["kind"] == "xong":
            gr.Info(f"Đã gộp job của đợt {r['run']}: raw\\{r['xml_name']}.")
        else:
            gr.Warning(r["text"], title="Gộp job chưa xong")
        return render(s, msg_html=r["html"])

    def trash_after(s):
        """Delete batch có tick 'xoá luôn task trên CVAT': job xoá task vừa dừng thì xử lý ĐÚNG MỘT LẦN: xoá xong -> chuyển đợt vào thùng rác;
        lỗi/huỷ -> giữ nguyên đợt và báo (lỗi chi tiết ở khung phía trên). Còn chạy hoặc không có yêu cầu -> None."""
        want = getattr(ctx, "dot_trash_after", None)
        if not want or ctx.del_job.running:
            return None
        ctx.dot_trash_after = None
        snap = ctx.del_job.snapshot()
        if snap.get("run") != want["run"] or snap["state"] != "xong":
            return render(s, f"Chưa xoá được task {want['task']} trên CVAT nên đợt {want['run']} vẫn giữ nguyên (xem khung phía trên).", "warn")
        try:
            entry = dot_anh.delete_run(ctx.runs_root, want["run"], want["typed"], active_run=active_dir)
        except RunError as e:
            return render(s, f"Đã xoá task {want['task']} trên CVAT nhưng chưa chuyển được đợt {want['run']} vào thùng rác: {e}", "warn")
        s.update(view="list", run=None, page=0)
        return render(s, f"Đã xoá task {want['task']} trên CVAT và chuyển đợt {want['run']} vào runs\\_trash\\{entry} (khôi phục được ở khu Đợt đã xoá).", "ok")

    def on_load_or_refresh(s):
        s = ensure(s)
        fx = finish_poll(s) or trash_after(s)                                 # tải/làm mới tab: job gộp đã dừng mà chưa ai xử lý thì xử lý ở đây
        if fx is not None:
            return fx
        g = gop_job.waiting(ctx)
        if g is not None:
            return render(s, f"Đợt {g['run']} còn job chưa Finish the job trên CVAT và đang chờ bạn chọn: bấm Merge jobs & Finish ở thẻ đợt đó để chọn "
                             "Merge anyway hoặc Cancel (đồng hồ của đợt, nếu có, vẫn đang tạm dừng).", "warn")
        return render(s)

    def on_tick(s):
        s = ensure(s)
        fx = finish_poll(s) or trash_after(s)
        if fx is not None:
            return fx
        running = any_running()
        was = s.get("was_running", False)
        s["was_running"] = running
        if was and not running:                             # việc vừa xong: vẽ lại danh sách
            g = gop_job.waiting(ctx)
            if g is not None:                               # yêu cầu gộp còn chờ chọn (ví dụ Merge anyway vừa bị từ chối vì việc kia): mở lại hộp, không để nó biến mất
                return force_modal(s, g, alert="Việc kia đã xong: bấm Merge anyway để gộp ngay, hoặc Cancel để quay lại CVAT sửa tiếp.")
            return render(s)
        return (gr.update(), s, gr.update(), job_banner(), gr.Timer(active=timer_on(running)), gr.update(), gr.update(), gr.update(), gr.update(),
                gr.update(), gr.update(), gr.update(), gop_cancel_update())

    def on_gop_cancel(s):
        """Nút Cancel ở khung gộp job: huỷ tiến trình con của Merge jobs & Finish; kết quả 'huỷ' được xử lý ngay (đồng hồ chạy lại nếu lúc bấm đang chạy)."""
        s = ensure(s)
        run = ctx.collect_job.run
        stopped = ctx.collect_job.cancel()                  # terminate, chờ, kill: tiến trình con là nơi duy nhất gọi CVAT
        fx = finish_poll(s)
        if fx is not None:
            return fx
        if not stopped:
            return render(s, "Không có job gộp nào đang chạy để huỷ.", "info")
        return render(s, f"Đã huỷ gộp job của đợt {run}.", "warn")

    def run_of(a):
        """Tên đợt hợp lệ từ hành động (phải nằm trong danh sách đợt do server tính) -> đường dẫn."""
        return dot_anh.valid_run(ctx.runs_root, a["run"])

    def gop_guard(run, what):
        """Đợt `run` còn yêu cầu Merge jobs & Finish dở (đang gộp hoặc chờ chọn Merge anyway / Cancel): từ chối `what` (xoá đợt, task, ảnh), vì xoá rồi thì
        yêu cầu không giải quyết được nữa (nút Merge jobs & Finish biến mất, đồng hồ kẹt ở tạm dừng)."""
        g = ctx.gop
        if g is not None and g.get("run") == run:
            raise RunError(gop_job.guard_text(g, what))

    def do_act(raw, s):
        s = ensure(s)
        a = parse_action(raw)
        if a is None:
            return render(s, "Hành động không hợp lệ (bỏ qua).", "warn")
        if ctx.closing and a["act"] not in ("back", "open", "page", "openfolder"):      # trang đang đóng: chỉ xem được, không ghi/đẩy/chuyển gì
            return render(s, nap_anh.CLOSING_MSG, "warn")
        try:
            return _dispatch(a, s)
        except RunError as e:
            gr.Warning(str(e), title="Chưa làm được")
            return render(s, str(e), "warn")

    def _dispatch(a, s):
        act = a["act"]
        if act == "back":
            s.update(view="list", run=None, page=0)
            return render(s)
        if act == "open":
            run_of(a)
            s.update(view="grid", run=a["run"], page=0)
            return render(s)
        if act == "page":
            run_of(a)
            try:
                s["page"] = max(0, int(a["page"]))
            except ValueError:
                s["page"] = 0
            return render(s)
        if act == "openfolder":
            rel = FOLDERS.get(a["folder"])
            path = os.path.join(ctx.project_root, rel) if rel else ""
            if a["folder"] == "raw" and a["run"]:                       # file nhãn gộp của đợt: mở đúng thư mục raw/<task>/ ghi trong gop_job.json
                try:
                    sub = raw_folder_of(ctx.project_root, run_of(a))
                except RunError:                                         # đợt đã vào thùng rác / không còn trong danh sách: mở raw/ như cũ
                    sub = None
                if sub:
                    path = sub
                    try:
                        rel = os.path.relpath(sub, os.path.realpath(ctx.project_root))
                    except ValueError:                                   # Windows: ổ mạng / subst, realpath ra đường dẫn UNC khác ổ
                        rel = sub
            if rel is None or not os.path.isdir(path):
                gr.Warning("Thư mục không hợp lệ (bỏ qua)." if rel is None else f"Chưa có thư mục {rel.replace(os.sep, '/')} (chưa lưu gì vào đó).", title="Mở thư mục")
                return render(s, msg_html=gr.update())                   # không xoá thẻ kết quả gộp job
            ok, text = open_folder(os.path.abspath(path))
            (gr.Info(text, title="Mở thư mục") if ok else gr.Warning(text, title="Mở thư mục"))
            return render(s, msg_html=gr.update())                       # giữ nguyên thẻ kết quả gộp job ở #dot-msg (thẻ chỉ dựng một lần), báo bằng thông báo góc trang
        if act == "ra":
            return _switch(a, s)
        if act == "finish":
            return _ask_finish(a, s)
        if os.environ.get("M28_PUBLIC_DEMO") == "1" and act in ("delimg", "restore", "empty", "delrun", "restore_run", "purge_run", "openfolder"):
            return render(s, "Bản demo công khai không xoá, khôi phục ảnh và đợt, cũng không mở thư mục trên máy chủ.", "info")
        if act == "delimg":
            return _ask_delimg(a, s)
        if act == "restore":
            return _restore(a, s)
        if act == "empty":
            run_dir = run_of(a)
            n = len(dot_anh.list_trash(run_dir))
            if not n:
                return render(s, "Thùng rác của đợt đang trống.", "info")
            it = modal_for("empty", run=a["run"])
            body = (f'<div class="modal-title modal-danger" id="dot-modal-title">Dọn thùng rác của đợt {_e(a["run"])}?</div>'
                    f'<div class="nap-box nap-err" role="alert"><b>Xoá vĩnh viễn {n} ảnh trong thùng rác, KHÔNG khôi phục được.</b></div>'
                    '<div class="nap-note">Tên các ảnh này vẫn bị loại khỏi đợt (nằm trong excluded.txt).</div>')
            return render(s, modal=dict(body=body, token=it["token"], ok_label="Delete permanently"))
        if act == "delrun":
            return _ask_delrun(a, s)
        if act == "restore_run":
            name = dot_anh.restore_run(ctx.runs_root, a["entry"])
            return render(s, f"Đã khôi phục đợt {name}.", "ok")
        if act == "purge_run":
            return _ask_purge(a, s)
        return render(s)

    def chan_chua_dat_ten(viec):
        chan_khi_chua_dat_ten(ctx, viec)

    def _switch(a, s):
        run_dir = run_of(a)
        chan_chua_dat_ten("bấm Open batch")
        if ctx.switch_to is not None:
            return render(s, "Đang chuyển sang đợt khác…", "info")
        if any_running():
            raise RunError("Đang có việc chạy (chuẩn bị, đẩy, xoá task hoặc gộp job): chờ xong rồi chuyển đợt.")
        fx = finish_poll(s)                                 # job gộp đã dừng mà chưa xử lý: xử lý và cho thấy kết quả (hoặc hộp thứ hai) trước, chưa chuyển
        if fx is not None:
            return fx
        g = gop_job.waiting(ctx)
        if g is not None:                                   # chuyển đợt dựng ctx mới: yêu cầu đang chờ sẽ mất, đồng hồ của đợt kẹt ở tạm dừng
            return force_modal(s, g, alert=f"Chọn Merge anyway hoặc Cancel cho đợt {g['run']} trước rồi mới chuyển đợt.")
        if ctx.gop is not None:
            raise RunError(gop_job.guard_text(ctx.gop, "chuyển đợt"))
        if is_active(a["run"]):
            raise RunError(f"Đợt {a['run']} đang mở ở tab Rà soát.")
        if not os.path.isfile(os.path.join(run_dir, "flags", "flags.json")):
            raise RunError(f"Đợt {a['run']} chưa có flags.json (prepare chưa xong): chạy lại ở tab Nạp ảnh hoặc bằng python tool\\m28.py prepare.")
        if dot_anh.run_busy(run_dir):
            raise RunError(f"Đợt {a['run']} đang có việc chạy: chờ xong.")
        new_store = Store(run_dir, ctx.next_reviewer())                        # tên người rà cho lượt kế tiếp (tab Cài đặt); dựng TRƯỚC: lỗi thì báo ở đây
        if not ctx.begin_switch((run_dir, new_store)):
            raise RunError(nap_anh.CLOSING_MSG)
        threading.Timer(0.8, lambda: demo.close(verbose=False)).start()
        return render(s, f"Đang chuyển sang đợt {a['run']}: trang mất kết nối 1–3 giây rồi tự tải lại.", "ok", switch="Rà soát M28 · " + a["run"])

    def _ask_finish(a, s):
        run_dir = run_of(a)
        chan_chua_dat_ten("bấm Merge jobs & Finish")
        fx = finish_poll(s)                                 # lần gộp trước đã dừng mà chưa tab nào xử lý (tab đã đóng...): xử lý và báo trước
        if fx is not None:
            return fx
        g = gop_job.waiting(ctx)
        if g is not None:                                   # đang chờ chọn Merge anyway / Cancel (hộp đã đóng do tải lại trang...): mở lại hộp đó
            return force_modal(s, g, "" if g["run"] == a["run"] else f"Đợt {g['run']} đang chờ bạn chọn trước.")
        if ctx.gop is not None:
            raise RunError(f"Đang gộp job của đợt {ctx.gop['run']}: chờ xong.")
        m = finish_model(run_dir)
        if not m["enabled"]:
            raise RunError(m["reason"] or "Chưa gộp job được.")
        it = modal_for("finish", run=a["run"], task=m["task"], person=m["person"])
        return render(s, modal=dict(body=gop_job.confirm_html(m), token=it["token"], ok_label="Merge jobs & Finish", ok_enabled=True))

    def _ask_delimg(a, s):
        run_dir = run_of(a)
        gop_guard(a["run"], "xoá ảnh của đợt")
        names = dot_anh.image_names(run_dir)
        if a["name"] not in names:
            raise RunError(f"Ảnh {a['name']!r} không có trong đợt (có thể đã xoá) (danh sách đã làm mới).")
        busy = dot_anh.run_busy(run_dir)
        if busy:
            raise RunError(f"Đợt {a['run']} đang có việc chạy ({busy[0]}): chờ xong rồi xoá.")
        if is_active(a["run"]) and store is not None and len(store.faces) <= 1 and a["name"] in store.by_name:
            raise RunError("Đợt đang rà chỉ còn một mặt: không xoá được (hàng đợi không được rỗng). Chuyển sang đợt khác rồi xoá cả đợt.")
        rows = {r["name"]: r for r in dot_anh.image_rows(run_dir, ctx.reviewer)}
        r = rows[a["name"]]
        ps = dot_anh.read_push(run_dir) or {}
        pushed = ps.get("trang_thai") in ("xong", "da_tao", "da_nhap")
        it = modal_for("delimg", run=a["run"], name=a["name"], decision=r["status"], pushed=ps.get("task") if pushed else None)
        warn = (f'<div class="nap-box nap-err" role="alert"><b>Xoá ở đây KHÔNG xoá ảnh trong task {_e(ps.get("task"))} trên CVAT.</b> '
                'Ảnh vẫn còn trong task đó; muốn bỏ khỏi CVAT phải xoá trong CVAT.</div>') if pushed else ""
        body = (f'<div class="modal-title modal-danger" id="dot-modal-title">Xoá ảnh {_e(a["name"])}?</div>'
                '<table class="m28-info">'
                f'<tr><th>Tên ảnh</th><td><b>{_e(a["name"])}</b></td></tr><tr><th>Tên gốc</th><td>{_e(r["orig"])}</td></tr>'
                f'<tr><th>Đợt</th><td>{_e(a["run"])}</td></tr>'
                f'<tr><th>Quyết định hiện tại</th><td>{_e(dot_anh.DECISION_VI.get(r["status"], r["status_text"]))}</td></tr></table>'
                '<div class="nap-note"><b>Hậu quả:</b> ảnh rời khỏi hàng đợi rà và khỏi lần push sau; chuyển vào thùng rác của đợt, '
                f'<b>khôi phục được</b>.</div>{warn}')
        return render(s, modal=dict(body=body, token=it["token"], ok_label="Delete image"))

    def _restore(a, s):
        run_dir = run_of(a)
        res = dot_anh.restore_image(run_dir, a["trash"], reviewer=ctx.reviewer)
        if is_active(a["run"]) and store is not None:
            store.reload()
        note = f"Đã khôi phục ảnh {res['ten']}."
        if res["mo_lai"]:
            note += " Ảnh này chưa có quyết định nên lượt có lại mặt chưa rà (rà nốt rồi đẩy lại)."
        return render(s, note, "ok")

    def _ask_delrun(a, s):
        """Delete batch (popup quản lý đợt). a['cvat'] == '1' (ô tick, chỉ bật khi đợt đã có task trên CVAT): xoá luôn task trên CVAT trước,
        xoá xong mới chuyển đợt vào thùng rác (trash_after); xoá task không xong thì giữ đợt."""
        run_dir = run_of(a)
        if is_active(a["run"]):
            raise RunError(f"Đợt {a['run']} đang mở ở tab Rà soát: chuyển sang đợt khác rồi mới xoá.")
        gop_guard(a["run"], "xoá đợt")
        busy = dot_anh.run_busy(run_dir)
        if busy:
            raise RunError(f"Đợt {a['run']} đang có việc chạy ({busy[0]}): chờ xong rồi xoá.")
        task, cvat = None, ""
        if a["cvat"] == "1":
            m = day_cvat.delete_model(run_dir, ctx.project_root, job_running=any_running())
            if not m["ok"]:
                raise RunError(m["reason"] or "Chưa xoá task trên CVAT được: chưa xoá gì.")
            task, cvat = m["task"], day_cvat.delete_confirm_html(m)
        else:
            ps = dot_anh.read_push(run_dir) or {}
            if dot_anh.on_cvat(ps):
                cvat = (f'<div class="nap-box nap-warn" role="alert">Task <b>{_e(ps.get("task"))}</b> vẫn còn trên CVAT '
                        '(muốn xoá cả task thì tick ô cạnh nút Delete batch).</div>')
        it = modal_for("delrun", run=a["run"], task=task)
        title = f"Xoá cả đợt {_e(a['run'])}" + (f" và task {_e(task)} trên CVAT?" if task else "?")
        body = (f'<div class="modal-title modal-danger" id="dot-modal-title">{title}</div>'
                '<div class="nap-note"><b>Hậu quả:</b> cả thư mục đợt (ảnh, nhãn nháp, kết quả rà) chuyển vào <code>runs\\_trash</code>, '
                f'<b>khôi phục được</b> nếu tên {_e(a["run"])} chưa bị dùng lại.</div>{cvat}')
        return render(s, modal=dict(body=body, token=it["token"], typed=True, typed_label=f"Gõ lại đúng tên đợt ({a['run']}), phân biệt hoa thường",
                                    ok_label="Delete batch", ok_enabled=False))

    def _ask_purge(a, s):
        found = {d["entry"]: d for d in dot_anh.list_deleted_runs(ctx.runs_root)}
        if a["entry"] not in found:
            raise RunError("Mục này không còn trong thùng rác đợt (danh sách đã làm mới).")
        it = modal_for("purge_run", entry=a["entry"])
        body = (f'<div class="modal-title modal-danger" id="dot-modal-title">Xoá vĩnh viễn đợt {_e(found[a["entry"]]["ten"])}?</div>'
                '<div class="nap-box nap-err" role="alert"><b>Xoá hẳn khỏi ổ đĩa, KHÔNG khôi phục được</b> (ảnh, nhãn nháp, kết quả rà của đợt).</div>')
        return render(s, modal=dict(body=body, token=it["token"], ok_label="Delete permanently"))

    def on_typed(typed_v, check_v, token):
        it = pending.item
        if not it or token != it.get("token"):
            return gr.update()                                    # sự kiện của hộp cũ: không đổi gì (server vẫn kiểm lại khi xác nhận)
        if it["kind"] == "delrun":
            return gr.update(interactive=typed_v == it["run"])
        return gr.update(interactive=True)

    def on_ok(typed_v, check_v, token, s):
        s = ensure(s)
        if ctx.closing:
            pending.cancel()
            return render(s, nap_anh.CLOSING_MSG, "warn")
        it = pending.item
        if it and token == it.get("token") and it["kind"] == "delrun" and typed_v != it["run"]:
            return render(s, "Tên gõ lại chưa đúng: chưa xoá gì.", "warn")
        it = pending.take(token)
        if it is None:
            return render(s, "Yêu cầu xác nhận đã cũ hoặc không còn hiệu lực: không làm gì (không xoá, không gộp), hãy thử lại.", "warn")
        try:
            return _execute(it, typed_v, s)
        except RunError as e:
            gr.Warning(str(e), title="Chưa làm được")
            return render(s, str(e), "warn")

    def _execute(it, typed_v, s):
        kind = it["kind"]
        if kind in ("delimg", "delrun"):                    # kiểm lại lúc bấm OK: có thể vừa bấm Merge jobs & Finish ở tab khác
            gop_guard(it["run"], {"delimg": "xoá ảnh của đợt", "delrun": "xoá đợt"}[kind])
        if kind == "delimg":
            run_dir = run_of(it)
            man = dot_anh.soft_delete_image(run_dir, it["name"], reviewer=ctx.reviewer, decision=it.get("decision", ""), pushed_task=it.get("pushed"))
            if is_active(it["run"]) and store is not None:
                store.exclude(it["name"])
            return render(s, f"Đã chuyển ảnh {man['ten']} vào thùng rác của đợt (khôi phục được).", "ok")
        if kind == "empty":
            n = dot_anh.empty_trash(run_of(it))
            return render(s, f"Đã dọn thùng rác: xoá vĩnh viễn {n} ảnh.", "ok")
        if kind == "delrun" and it.get("task"):            # xoá luôn task trên CVAT: tiến trình con xoá task trước, xong mới chuyển đợt vào thùng rác
            if typed_v != it["run"]:
                raise RunError("Tên gõ lại chưa đúng: chưa xoá gì.")
            m = day_cvat.delete_model(run_of(it), ctx.project_root, job_running=any_running())
            if not m["ok"] or m["task"] != it["task"]:
                raise RunError(m["reason"] or "Thông tin task đã đổi: chưa xoá gì, hãy bấm Delete batch lại.")
            ctx.del_job.start(it["run"], ctx.runs_root, ctx.project_root, m["task"])
            ctx.dot_trash_after = dict(run=it["run"], task=m["task"], typed=typed_v)
            s.update(view="list", run=None, page=0)
            return render(s, f"Đang xoá task {m['task']} trên CVAT (theo dõi ở khung phía trên); xoá xong đợt {it['run']} tự chuyển vào thùng rác.", "ok")
        if kind == "delrun":
            entry = dot_anh.delete_run(ctx.runs_root, it["run"], typed_v, active_run=active_dir)
            s.update(view="list", run=None, page=0)
            return render(s, f"Đã chuyển đợt {it['run']} vào runs\\_trash\\{entry} (khôi phục được ở khu Đợt đã xoá).", "ok")
        if kind == "purge_run":
            name = dot_anh.purge_run(ctx.runs_root, it["entry"])
            return render(s, f"Đã xoá vĩnh viễn đợt {name}.", "ok")
        if kind == "finish":
            run_dir = run_of(it)
            m = finish_model(run_dir)                       # kiểm lại lúc bấm OK (cài đặt, phiên đồng hồ, việc khác có thể vừa đổi)
            if not m["enabled"]:
                raise RunError(m["reason"] or "Chưa gộp job được.")
            if m["task"] != it.get("task") or m["person"] != it.get("person"):
                raise RunError("Task hoặc người rà vừa đổi: chưa làm gì, bấm Merge jobs & Finish lại.")
            paused = gop_job.begin(ctx, dh_of(), m)        # đồng hồ đang chạy thì tạm dừng NGAY, rồi chạy collect (tiến trình con)
            fx = finish_poll(s)                             # tiến trình con không chạy được (lỗi ngay): xử lý luôn, không chờ nhịp
            if fx is not None:
                return fx
            return render(s, f"Đang gộp job của đợt {it['run']} trên CVAT (theo dõi ở khung phía trên)"
                          + ("; đồng hồ của đợt đã tạm dừng." if paused else "."), "ok")
        if kind == "finish_force":
            g = gop_job.waiting(ctx)
            if g is None or g["run"] != it.get("run"):
                raise RunError("Yêu cầu gộp đã cũ: bấm Merge jobs & Finish lại.")
            try:
                run_dir = run_of(it)
            except RunError as e:                           # đợt không còn (xoá ngoài trang): bỏ yêu cầu, không để nó kẹt
                raise RunError(gop_job.abandon(ctx, dh_of(), str(e)))
            m = finish_model(run_dir)
            if m["person"] != g["person"] or m["task"] != g["task"]:
                why = m["reason"] if m["reason"] and not m.get("tam_thoi") else "Task hoặc người rà vừa đổi: chưa gộp."
                raise RunError(gop_job.abandon(ctx, dh_of(), why))
            if not m["enabled"] and m.get("tam_thoi"):      # việc khác đang chạy: tạm thời, yêu cầu VẪN CHỜ, đồng hồ để nguyên
                return force_modal(s, g, alert=f"Chưa gộp được: {m['reason']} Yêu cầu gộp của đợt {g['run']} vẫn chờ (đồng hồ của đợt để nguyên): "
                                               "chờ việc kia xong rồi bấm Merge anyway lại, hoặc Cancel để quay lại CVAT.")
            if not m["enabled"]:                            # thay đổi lâu dài (task đã xoá, link/người rà đổi...): bỏ yêu cầu
                raise RunError(gop_job.abandon(ctx, dh_of(), m["reason"] or "Chưa gộp job được."))
            try:
                gop_job.force(ctx, dh_of(), it["run"])
            except RunError as e:
                g2 = gop_job.waiting(ctx)
                if g2 is not None:                          # chưa chạy được (khoá bận...): yêu cầu vẫn chờ, mở lại hộp kèm lý do
                    return force_modal(s, g2, alert=str(e))
                raise
            fx = finish_poll(s)
            if fx is not None:
                return fx
            return render(s, f"Đang gộp job của đợt {it['run']} (gộp luôn, kể cả job chưa Finish the job; theo dõi ở khung phía trên).", "ok")
        raise RunError("Yêu cầu không rõ.")

    def on_dismiss(token, s):
        it = pending.item
        mine = bool(it and token and token == it.get("token"))
        note, level = "", "info"
        if gop_job.is_force_token(ctx, token) or (mine and it.get("kind") == "finish_force"):
            # Cancel ở hộp thứ hai = quay lại CVAT sửa tiếp (đồng hồ chạy lại nếu lúc bấm đang chạy); nhận ra qua mã ghi trong ctx.gop nên vẫn đúng khi tab khác
            # đã thay hoặc bỏ yêu cầu xác nhận dùng chung
            note = gop_job.back_to_cvat(ctx, dh_of())
            if not note:
                note, level = "Yêu cầu gộp này không còn chờ (đã xử lý ở tab khác): không làm gì.", "warn"
        if mine or not token:                               # chỉ bỏ yêu cầu xác nhận của CHÍNH hộp này, không bỏ hộp đang mở ở tab khác
            pending.cancel()
        return render(s, note, level)

    do = dict(opts, concurrency_id="dot")
    evs = [act_go.click(do_act, [act_tb, ses], outs, **do)]          # không có nút Refresh: tab tự làm mới khi mở và sau mỗi thao tác
    evs[-1].then(None, [target], None, js=switch_js)
    evs.append(b_ok.click(on_ok, [typed, check, token_tb, ses], outs, **do))
    evs.append(b_no.click(on_dismiss, [token_tb, ses], outs, **do))
    typed.change(on_typed, [typed, check, token_tb], [b_ok], **dict(opts, concurrency_id="dot_typed"))
    check.change(on_typed, [typed, check, token_tb], [b_ok], **dict(opts, concurrency_id="dot_typed"))
    evs.append(timer.tick(on_tick, [ses], outs, **dict(opts, concurrency_id="dot_tick")))
    evs.append(b_gop_cancel.click(on_gop_cancel, [ses], outs, **dict(opts, concurrency_id="dot_gop_huy")))     # hàng riêng (như push_huy): không chờ sau việc khác của tab
    if dh is not None:                                      # chip đồng hồ ở đầu trang cập nhật ngay (Merge jobs & Finish tạm dừng, lưu hoặc cho chạy lại đồng hồ)
        for ev in evs:
            ev.then(dh.refresh, None, dh.outs, **dh.opts)

    def go_view(where, s):
        """Nút ẩn m28-go (build_ui gọi TRƯỚC khi đổi tab): 'dot' -> danh sách thẻ, 'gop' -> trang Gộp & kết thúc của đợt đang mở; đi sang tab khác
        thì đóng popup quản lý đợt (popup nằm trong tab này, không để nó còn mở sau lưng). Còn lại không đổi gì."""
        s = ensure(s)
        if where == "home":                                 # tên đợt / Continue ở thẻ đợt đang mở, tắt Team lead: tới bước đợt đang ở
            where = step_of()
        view = VIEWS.get(where) or ("list" if s["view"] == "grid" else None)
        if view is None:
            return (gr.update(), s) + (gr.update(),) * (len(outs) - 2)
        s.update(view=view, run=None, page=0)
        return render(s, msg_html=gr.update())               # giữ thẻ kết quả gộp job ở #dot-msg
    return on_load_or_refresh, ses, outs, dict(opts, concurrency_id="dot"), go_view
