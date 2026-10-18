"""Áp bản vá "demo công khai" lên MỘT BẢN SAO của tool (không đụng mã nguồn gốc): bật bằng biến môi trường M28_PUBLIC_DEMO=1.
  - mở cho mọi Host và lắng nghe 0.0.0.0 (chạy sau proxy của nơi lưu trữ), thay vì chỉ 127.0.0.1;
  - không cho đóng trang, không nạp ảnh mới (CPU nhỏ, và để người lạ không đưa ảnh vào); tab Nạp ảnh nói rõ điều đó;
  - banner "bản demo" cố định ở góc dưới (lời khác nhau khi CVAT mô phỏng hay CVAT thật);
  - nút "Open CVAT task" bị khoá (người xem không mở được task);
  - CVAT mô phỏng (chỉ khi dùng gói cvat_sdk giả): job tự chuyển Mới -> Đang sửa -> Xong theo thời gian kể từ lúc tạo task.
  python patch_demo.py <thư mục tool> <cvat_sdk giả/__init__.py> [demo_block.py]"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def sub(path, old, new, count=1):
    s = open(path, encoding="utf-8").read()
    assert s.count(old) == count, (path, old[:70], s.count(old))
    open(path, "w", encoding="utf-8").write(s.replace(old, new))


def patch_tool(tool, block_path):
    ra = os.path.join(tool, "review_app.py")
    sub(ra, 'guard = [Middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])]',
        'PUBLIC = os.environ.get("M28_PUBLIC_DEMO") == "1"\n'
        '    guard = [Middleware(TrustedHostMiddleware, allowed_hosts=["*"] if PUBLIC else ["127.0.0.1", "localhost"])]\n'
        '    if PUBLIC:\n'
        '        guard.append(Middleware(_DemoNoUpload))')
    sub(ra, 'return demo.launch(server_name="127.0.0.1", server_port=port,',
        'return demo.launch(server_name="0.0.0.0" if PUBLIC else "127.0.0.1", server_port=port, state_session_capacity=30 if PUBLIC else 10000,')
    sub(ra, '        if not ctx.begin_close():\n            return refuse("Trang đang đóng hoặc đang chuyển lượt.", "info")',
        '        if os.environ.get("M28_PUBLIC_DEMO") == "1":\n'
        '            return refuse("Đây là bản demo công khai: không đóng được trang.", "info")\n'
        '        if not ctx.begin_close():\n            return refuse("Trang đang đóng hoặc đang chuyển lượt.", "info")')
    sub(ra, 'cvat_ui.JS_BODY + "}"', 'cvat_ui.JS_BODY + DEMO_JS + "}"')
    sub(ra, 'CSS = CSS + log_view.CSS', 'CSS = CSS + DEMO_CSS + log_view.CSS')
    marker = 'PAGE_JS = PAGE_JS[:-1] + ZOOM_JS'
    s = open(ra, encoding="utf-8").read()
    assert s.count(marker) == 1
    block = open(block_path, encoding="utf-8").read()
    open(ra, "w", encoding="utf-8").write(s.replace(marker, block + marker))
    du = os.path.join(tool, "dot_ui.py")
    sub(du, '        if act == "delimg":\n            return _ask_delimg(a, s)',
        '        if os.environ.get("M28_PUBLIC_DEMO") == "1" and act in ("delimg", "restore", "empty", "delrun", "restore_run", "purge_run", "openfolder"):\n'
        '            return render(s, "Bản demo công khai không xoá, khôi phục ảnh và đợt, cũng không mở thư mục trên máy chủ.", "info")\n'
        '        if act == "delimg":\n            return _ask_delimg(a, s)')
    cd = os.path.join(tool, "cai_dat.py")
    sub(cd, 'return "••••" + token[-4:] if len(token) >= 8 else "••••"',
        'return "••••" if os.environ.get("M28_PUBLIC_DEMO") == "1" else ("••••" + token[-4:] if len(token) >= 8 else "••••")')
    _no = 'dict(ok=False, level="warn", stale=False, msg="Bản demo công khai dùng chung một cài đặt cho mọi người nên không đổi được (CVAT, tên người rà, đường dẫn, ngưỡng).")'
    guard = '        if os.environ.get("M28_PUBLIC_DEMO") == "1":\n            return ' + _no + '\n'
    sub(cd, '    def save_cvat(self, url, token, org, remember, rev=None):\n', '    def save_cvat(self, url, token, org, remember, rev=None):\n' + guard)
    sub(cd, '    def forget_cvat(self, rev=None):\n', '    def forget_cvat(self, rev=None):\n' + guard)
    sub(cd, '    def set_reviewer(self, name, rev=None):\n', '    def set_reviewer(self, name, rev=None):\n' + guard)
    sub(cd, '    def set_path(self, kind, value, rev=None):\n', '    def set_path(self, kind, value, rev=None):\n' + guard.replace('stale=False,', 'stale=False, check=None,'))
    sub(cd, 'def write_t_flip(config_path, value):\n', 'def write_t_flip(config_path, value):\n    if os.environ.get("M28_PUBLIC_DEMO") == "1":\n        raise RunError("Bản demo công khai không đổi ngưỡng low_conf.")\n')
    na = os.path.join(tool, "nap_anh.py")
    sub(na, '        """Chạy prepare cho lượt `run` (thư mục runs_root/run đã có inbox/). Đang chạy thì RunError."""\n        with self._lock:',
        '        """Chạy prepare cho lượt `run` (thư mục runs_root/run đã có inbox/). Đang chạy thì RunError."""\n'
        '        if os.environ.get("M28_PUBLIC_DEMO") == "1":\n'
        '            raise RunError("Bản demo công khai không nạp ảnh mới: dùng đợt mẫu NAP_001. Cài tool về máy để nạp ảnh của bạn.")\n'
        '        with self._lock:')
    sub(na, "def preflight_html(errors, layout_error=None):\n",
        "def preflight_html(errors, layout_error=None):\n"
        "    if os.environ.get(\"M28_PUBLIC_DEMO\") == \"1\":          # demo công khai: không có model, không nạp ảnh; nói rõ thay vì báo lỗi thiếu file\n"
        "        return ('<div class=\"nap-box nap-warn\" role=\"status\"><b>Bản demo công khai không nạp ảnh mới.</b> Dùng đợt mẫu NAP_001 (10 mặt đã qua MediaPipe) '\n"
        "                'ở bước 2 Rà soát. Cài tool về máy để nạp ảnh của bạn (hướng dẫn ở GitHub).</div>')\n")


def patch_fake_cvat(init_py):
    sub(init_py, "    def get_jobs(self):\n        return [Job(j) for j in self._rec()[\"jobs\"]]",
        "    def get_jobs(self):\n"
        "        rec = self._rec()\n"
        "        if os.environ.get('M28_DEMO_AUTO_JOBS') == '1':       # demo công khai: job tự được 'người gán' sửa xong theo thời gian\n"
        "            age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(rec['created'])).total_seconds()\n"
        "            out = []\n"
        "            for i, j in enumerate(rec['jobs']):\n"
        "                j = dict(j)\n"
        "                if age >= 12 + 6 * i:\n"
        "                    j['state'], j['stage'] = 'completed', 'acceptance'\n"
        "                elif age >= 3 + i:\n"
        "                    j['state'] = 'in progress'\n"
        "                out.append(Job(j))\n"
        "            return out\n"
        "        return [Job(j) for j in rec[\"jobs\"]]")


if __name__ == "__main__":
    patch_tool(sys.argv[1], sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "demo_block.py"))
    patch_fake_cvat(sys.argv[2])
    print("đã vá")
