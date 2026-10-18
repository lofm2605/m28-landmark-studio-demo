"""Khung log trong popup của trang rà soát M28 (Log prepare ở tab Nạp ảnh, Log push ở khung Duyệt & Xuất CVAT): logic thuần, chỉ thư viện chuẩn.

  * Ẩn dòng thông báo nội bộ của MediaPipe / TensorFlow (glog W/I, "Created TensorFlow Lite XNNPACK delegate"...): không phải việc của annotator,
    chỉ đếm số dòng đã ẩn. Nút Copy chép NGUYÊN log (cả dòng đã ẩn) để gửi khi cần hỏi.
  * Mỗi dòng một kiểu: tiêu đề lần chạy (=== ... ===), bước [k/n], dòng "tên bước: kết quả", dòng thụt lề (chi tiết), cảnh báo, lỗi.
  * Khung cuộn dùng flex-direction: column-reverse nên mở ra là thấy dòng cuối, có dòng mới cũng vẫn ở cuối (không cần JS).
Dòng vào đây đã lọc token ở tiến trình con (nap_anh.ChildJob); ở đây chỉ escape HTML.
"""
import html
import re

_e = html.escape

NOISE = re.compile(r"(?:[WI]\d{4} \d\d:\d\d:\d+\.\d+\s+\d+\s+\S+:\d+\]"            # glog W/I của MediaPipe (W0000 00:00:1792232039.86 13147 file.cc:180] ...)
                   r"|WARNING: Logging before InitGoogle\(\)"
                   r"|WARNING: All log messages before absl::InitializeLog\(\)"
                   r"|INFO: Created TensorFlow Lite)")
RUN = re.compile(r"=== (.+?) ===$")
STEP = re.compile(r"\[(\d+)/(\d+)\]\s*(.*)$")
KV = re.compile(r"([A-Za-z][A-Za-z0-9_]{0,23}):\s+(.*)$")
ERR = re.compile(r"(?:Lỗi|LỖI|Error|ERROR|Traceback)\b|[A-Za-z]*Error:|E\d{4} \d\d:\d\d:\d+\.\d+")
WARN = re.compile(r"(?:Cảnh báo|CẢNH BÁO|Lưu ý|WARNING|Warning)\b")


def split(lines):
    """(dòng giữ lại, số dòng nhiễu đã ẩn)."""
    kept, hidden = [], 0
    for ln in lines or ():
        if NOISE.match(ln.strip()):
            hidden += 1
        else:
            kept.append(ln)
    return kept, hidden


def kind(line):
    s = line.strip()
    if not s:
        return "blank"
    if ERR.match(s):
        return "err"
    if WARN.match(s):
        return "warn"
    if RUN.match(s):
        return "run"
    if line[:1].isspace():
        return "sub"
    if STEP.match(s):
        return "step"
    if KV.match(s):
        return "kv"
    return "text"


def _row(line):
    k, s = kind(line), line.strip()
    if k == "blank":
        return ""
    if k == "run":
        return f'<div class="lg-run"><span>{_e(RUN.match(s).group(1))}</span></div>'
    if k == "step":
        m = STEP.match(s)
        return f'<div class="lg-l lg-step"><span class="lg-k">{m.group(1)}/{m.group(2)}</span><span class="lg-v">{_e(m.group(3))}</span></div>'
    if k == "kv":
        m = KV.match(s)
        return f'<div class="lg-l lg-kv"><span class="lg-k">{_e(m.group(1))}</span><span class="lg-v">{_e(m.group(2))}</span></div>'
    return f'<div class="lg-l lg-{k}"><span class="lg-v">{_e(s)}</span></div>'


def log_html(lines, empty="Chưa có log trong phiên này."):
    """HTML khung log: dòng tóm tắt (số dòng, cảnh báo, lỗi, số dòng đã ẩn, nút Copy) + khung cuộn. lines: danh sách dòng (đã lọc token)."""
    kept, hidden = split(lines)
    if not any(ln.strip() for ln in kept):
        note = f' <span class="lg-muted">(ẩn {hidden} dòng thông báo của MediaPipe / TensorFlow)</span>' if hidden else ""
        return f'<div class="m28-lg lg-empty">{_e(empty)}{note}</div>'
    kinds = [kind(ln) for ln in kept]
    n_warn, n_err = kinds.count("warn"), kinds.count("err")
    n_lines = sum(1 for k in kinds if k not in ("blank", "run"))
    chips = [f'<span class="lg-chip">{n_lines} dòng</span>']
    if n_err:
        chips.append(f'<span class="lg-chip lg-chip-err">{n_err} lỗi</span>')
    if n_warn:
        chips.append(f'<span class="lg-chip lg-chip-warn">{n_warn} cảnh báo</span>')
    if hidden:
        chips.append(f'<span class="lg-muted">ẩn {hidden} dòng thông báo của MediaPipe / TensorFlow</span>')
    rows = "".join(_row(ln) for ln in kept)
    raw = "\n".join(lines)
    return (f'<div class="m28-lg"><div class="lg-head">{"".join(chips)}'
            f'<button type="button" class="lg-copy" data-lg-copy title="Chép toàn bộ log (cả các dòng đã ẩn)">Copy log</button></div>'
            f'<div class="lg-body"><div class="lg-lines">{rows}</div></div>'
            f'<textarea class="lg-raw" readonly tabindex="-1" aria-hidden="true">{_e(raw)}</textarea></div>')


CSS = """
/* ---------- khung log trong popup (log_view.log_html): Log prepare, Log push ---------- */
.m28-modal-box.nap-log-box { width: min(920px, 100%) !important; }
#nap-rejected:not(:has(.nap-box)) { display: none !important; }
.lg-title-row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.lg-title-row .modal-title { margin: 0; }
.lg-note { font-size: 13px; color: var(--body-text-color-subdued); }
.m28-lg { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.lg-empty { padding: 26px 14px; text-align: center; font-size: 14px; color: var(--body-text-color-subdued); border-radius: 10px;
  border: 1px dashed var(--border-color-primary); }
.lg-head { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 8px; font-size: 13px; }
.lg-chip { padding: 1px 9px; border-radius: 999px; font-weight: 700; border: 1px solid var(--border-color-primary); color: var(--body-text-color); }
.lg-chip-warn { color: #fbbf24; border-color: #b45309; background: rgba(245, 158, 11, .12); }
.lg-chip-err { color: #fca5a5; border-color: #b91c1c; background: rgba(239, 68, 68, .12); }
.lg-muted { color: var(--body-text-color-subdued); }
.lg-copy { margin-left: auto; cursor: pointer; min-height: 30px; padding: 2px 12px; border-radius: 8px; font-size: 13px; font-weight: 700;
  color: var(--body-text-color); background: var(--background-fill-secondary); border: 1px solid var(--border-color-primary); }
.lg-copy:hover { border-color: #3b82f6; } .lg-copy:focus-visible { outline: 3px solid #2563eb; outline-offset: 1px; }
.lg-body { display: flex; flex-direction: column-reverse; max-height: min(52vh, 460px); min-height: 160px; overflow: auto; border-radius: 10px;
  background: #060913; border: 1px solid var(--border-color-primary); padding: 8px 0; color-scheme: dark; scrollbar-color: #334155 transparent; }
.lg-lines { display: flex; flex-direction: column; font-family: var(--font-mono); font-size: 13px; line-height: 1.5; }
.lg-l { display: flex; gap: 10px; align-items: baseline; padding: 1px 12px; overflow-wrap: anywhere; color: #cbd5e1; }
.lg-l:hover { background: rgba(148, 163, 184, .06); }
.lg-k { flex: none; min-width: 74px; font-weight: 700; color: #7dd3fc; }
.lg-step .lg-k { min-width: 34px; color: #a5b4fc; }
.lg-v { min-width: 0; }
.lg-l.lg-sub { padding-left: 96px; color: #94a3b8; }
.lg-warn { color: #fbbf24; background: rgba(245, 158, 11, .07); }
.lg-err { color: #fca5a5; background: rgba(239, 68, 68, .09); }
.lg-run { display: flex; align-items: center; gap: 10px; padding: 6px 12px 4px; font-size: 12px; color: #64748b; }
.lg-run::before, .lg-run::after { content: ""; flex: 1 1 0; height: 1px; background: #1e2b42; }
.lg-raw { position: absolute; left: -9999px; width: 1px; height: 1px; opacity: 0; }
"""

JS = r"""
  // Nút Copy log (log_view.log_html): chép toàn bộ log (cả dòng đã ẩn) từ textarea ẩn; 127.0.0.1 là ngữ cảnh an toàn nên clipboard API dùng được.
  document.addEventListener('click', (e) => {
    const b = e.target && e.target.closest ? e.target.closest('[data-lg-copy]') : null;
    if (!b) { return; }
    const ta = b.closest('.m28-lg') && b.closest('.m28-lg').querySelector('.lg-raw');
    if (!ta) { return; }
    const done = () => { b.textContent = 'Copied'; setTimeout(() => { b.textContent = 'Copy log'; }, 1500); };
    const fallback = () => { ta.select(); try { document.execCommand('copy'); done(); } catch (err) { /* không chép được: bỏ qua */ } };
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(ta.value).then(done, fallback); } else { fallback(); }
  });
  // Đang chạy thì log vẽ lại mỗi khi có dòng mới. Khung cuộn column-reverse nên mặc định đứng ở dòng cuối (scrollTop = 0, cuộn lên thì âm);
  // ai đang cuộn lên đọc thì vẽ lại vẫn giữ đúng chỗ đó (nhớ theo id của khung chứa: #nap-log, #push-log).
  const LGS = {};
  const lgHost = (b) => { const h = b.closest('[id]'); return h ? h.id : ''; };
  document.addEventListener('scroll', (e) => {
    const b = e.target;
    if (!b || !b.classList || !b.classList.contains('lg-body')) { return; }
    LGS[lgHost(b)] = { top: b.scrollTop, stick: b.scrollTop > -6 };
  }, true);
  new MutationObserver(() => {
    document.querySelectorAll('.lg-body:not([data-lg-init])').forEach((b) => {
      b.dataset.lgInit = '1';
      const st = LGS[lgHost(b)];
      if (st && !st.stick) { b.scrollTop = st.top; }
    });
  }).observe(document.body, { childList: true, subtree: true });
"""
