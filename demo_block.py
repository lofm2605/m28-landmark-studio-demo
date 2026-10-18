
# ---------- bản demo công khai (chèn bởi patch_demo.py; chỉ có tác dụng khi M28_PUBLIC_DEMO=1) ----------
_DEMO_MODE = os.environ.get("M28_DEMO_CVAT_MODE", "fake")
_DEMO_BANNER = ("3 đợt mẫu (10, 30, 30 mặt; ảnh YawDD được phép đăng), chọn ở Switch batch. " + (
    "CVAT chạy thật trên CVAT Cloud 2.79 bằng tài khoản demo riêng; người gán được mô phỏng (job tự xong sau vài giây). " if _DEMO_MODE == "real" else
    "CVAT được mô phỏng trong máy chủ demo: không kết nối tới CVAT nào, kể cả CVAT trên máy bạn. ")
    + "Tự đặt lại khi không ai thao tác. Mã nguồn: ")
DEMO_CSS = """
#m28-tools #btn-dong, #btn-dong, #close-row { display: none !important; }
#nap-drop, #nap-count, #nap-list, #nap-meta, #nap-btns { display: none !important; }
a[href*="cvat.mo-phong.demo"] { pointer-events: none; opacity: .45; cursor: not-allowed; }
#m28-demo-banner { position: fixed; right: 12px; bottom: 12px; z-index: 9999; max-width: min(430px, calc(100vw - 24px)); padding: 8px 34px 8px 12px; font-size: 12px !important;
  border-radius: 12px; border: 1px solid #1d4ed8; background: rgba(12, 26, 51, .96); color: #bfdbfe; font: 600 12px/1.4 system-ui, sans-serif;
  box-shadow: 0 10px 30px rgba(0, 0, 0, .45); }
#m28-demo-banner b { color: #fff; } #m28-demo-x { position: absolute; right: 6px; top: 4px; border: 0; background: none; color: #93c5fd; font-size: 18px; cursor: pointer; line-height: 1; } #m28-demo-banner a { color: #93c5fd; }
"""
DEMO_JS = r"""
  if (!document.getElementById('m28-demo-banner')) {
    const d = document.createElement('div'); d.id = 'm28-demo-banner';
    const b = document.createElement('b'); b.textContent = 'Bản demo công khai (tool thật). '; d.appendChild(b);
    d.appendChild(document.createTextNode(@BANNER@));
    const g = document.createElement('a'); g.href = 'https://github.com/lofm2605/m28-landmark-studio-demo'; g.target = '_blank'; g.rel = 'noopener'; g.textContent = 'github.com/lofm2605/m28-landmark-studio-demo';
    d.appendChild(g); d.appendChild(document.createTextNode('.'));
    const x = document.createElement('button'); x.id = 'm28-demo-x'; x.type = 'button'; x.textContent = '×'; x.title = 'Đóng'; x.addEventListener('click', () => d.remove()); d.appendChild(x);
    document.body.appendChild(d);
    const lock = () => document.querySelectorAll('a.cv-btn, a.dot-btn').forEach(a => {
      if (/Open CVAT task/.test(a.textContent) && a.hasAttribute('href')) {
        a.removeAttribute('href'); a.removeAttribute('target'); a.style.pointerEvents = 'none'; a.style.opacity = '.45';
        a.title = 'Bản demo: task không mở được (CVAT mô phỏng hoặc nằm trong tài khoản demo riêng)'; }
    });
    new MutationObserver(lock).observe(document.body, { childList: true, subtree: true }); lock();
  }
""".replace("@BANNER@", json.dumps(_DEMO_BANNER))



class _DemoNoUpload:
    """ASGI: bản demo công khai không nhận file tải lên (không nạp ảnh; chặn việc đổ file rác hay dựng trang tuỳ ý lên tên miền của demo)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST" and scope.get("path", "").rstrip("/").endswith("/upload"):
            await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
            await send({"type": "http.response.body", "body": "Bản demo công khai không nhận file tải lên.".encode("utf-8")})
            return
        await self.app(scope, receive, send)

