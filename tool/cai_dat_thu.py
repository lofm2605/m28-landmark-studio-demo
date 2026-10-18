"""Tiến trình con "Thử kết nối CVAT" của tab Cài đặt (cai_dat.test_connection chạy file này bằng subprocess). TRANG không gọi mạng; chỉ
file này gọi CVAT, và chỉ ĐỌC (không tạo, sửa, xoá gì trên CVAT).

    python -u tool\\cai_dat_thu.py --version 2.77.0 --project m28       (CVAT_URL, CVAT_ACCESS_TOKEN, [CVAT_ORG] trong MÔI TRƯỜNG)

In đúng MỘT dòng JSON ở cuối stdout: ok, error_kind, message, server_version, username, project_found, project_id, org.
error_kind: bad_url | bad_token | server_down | version_mismatch | redirect | timeout | no_sdk | other. Mọi chuỗi qua cvat_io.scrub.

Các bước:
  1. TIỀN KIỂM: GET <link>/api/server/about bằng http.client, KHÔNG theo redirect, KHÔNG mang token, timeout ~5 giây. 3xx sang địa chỉ
     khác (scheme/host/cổng) thì dừng ("không gửi token"); 404 hoặc phản hồi không giống CVAT thì báo sai link. CVAT thật LUÔN qua
     bước này. Chỉ gói cvat_sdk GIẢ của test (có thuộc tính M28_FAKE_CVAT = True, không có server HTTP) được bỏ qua bước này.
  2. cvat_io.connect (cvat_sdk.make_client(..., access_token=...)), so major.minor của server với cvat_version trong pipeline.json,
     client.users.retrieve_current_user() (kiểm token), tìm project theo tên (chỉ đọc), tổ chức (nếu CVAT_ORG đặt).
Không bật log debug của urllib3/cvat-sdk, không in traceback (có thể chứa token).
"""
import argparse
import http.client
import json
import os
import socket
import ssl
import sys
from urllib.parse import urljoin, urlsplit

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
from m28core import cvat_io  # noqa: E402

PROBE_TIMEOUT = 5.0
ABOUT_PATH = "/api/server/about"
INSTALL_SDK = "Chưa cài cvat-sdk: gõ python -m pip install cvat-sdk==2.77.0 (cùng bản với server CVAT) rồi thử lại."
START_HINT = ("Nếu CVAT chạy trên máy này: mở Ubuntu (WSL), vào thư mục cvat, gõ docker compose up -d, chờ 1-2 phút rồi thử lại")


def _result(ok, kind="", message="", **kw):
    d = dict(ok=ok, error_kind=kind, message=message, server_version="", username="", project_found=None, project_id=None, org="")
    d.update(kw)
    return d


def _origin(url):
    p = urlsplit(url)
    scheme = (p.scheme or "").lower()
    port = p.port or (443 if scheme == "https" else 80)
    return scheme, (p.hostname or "").lower(), port


def probe(url, timeout=PROBE_TIMEOUT, conn_factory=None):
    """Tiền kiểm GET <url>/api/server/about, không mang token, không theo redirect. Trả None nếu được đi tiếp, hoặc dict kết quả lỗi."""
    parts = urlsplit(url)
    scheme, host, port = _origin(url)
    path = parts.path.rstrip("/") + ABOUT_PATH
    if conn_factory is None:
        conn_factory = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
    conn = conn_factory(host, port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"Accept": "application/json", "User-Agent": "m28-cai-dat"})
        resp = conn.getresponse()
        status, location, body = resp.status, resp.getheader("Location") or "", resp.read(65536)
    except (socket.timeout, TimeoutError):
        return _result(False, "timeout", f"Server {url} không trả lời trong {int(timeout)} giây. Kiểm CVAT có đang chạy không và link đúng chưa. "
                                         + START_HINT + ".")
    except ssl.SSLError:
        return _result(False, "other", f"Kết nối https tới {url} lỗi chứng chỉ (chứng chỉ tự ký, hết hạn, hoặc tên máy không khớp). "
                                       "Nhờ người quản trị CVAT cấp chứng chỉ hợp lệ, hoặc dùng link http:// trong mạng nội bộ.")
    except (ConnectionError, socket.gaierror, OSError, http.client.HTTPException):
        return _result(False, "server_down", f"Không kết nối được tới {url}: server tắt hoặc sai link (tên máy, cổng). " + START_HINT + ".")
    finally:
        conn.close()
    if 300 <= status < 400:
        target = urljoin(f"{scheme}://{host}:{port}{path}", location) if location else ""
        try:
            same = bool(target) and _origin(target) == (scheme, host, port)
        except ValueError:
            same = False
        if not same:
            where = urlsplit(target)
            shown = f"{where.scheme}://{where.hostname}" + (f":{where.port}" if where.port else "") if where.hostname else "không rõ"
            return _result(False, "redirect", f"CVAT chuyển hướng sang địa chỉ khác ({shown}), không gửi token. Dùng đúng địa chỉ cuối cùng "
                                              "(ví dụ https://… thay vì http://…) làm link rồi thử lại.")
        return None
    if status == 404:
        return _result(False, "bad_url", f"Địa chỉ {url} trả lời 404 ở {ABOUT_PATH}: đây không phải CVAT hoặc sai đường dẫn. "
                                         "Kiểm lại link (ví dụ http://localhost:8080, không thêm đường dẫn phụ).")
    if status >= 500:
        return _result(False, "other", f"Server {url} báo lỗi {status} khi hỏi {ABOUT_PATH}: CVAT chưa khởi động xong hoặc đang lỗi. "
                                       "Chờ 1-2 phút rồi thử lại.")
    if status == 200:
        try:
            d = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            d = None
        if not isinstance(d, dict) or "version" not in d:
            return _result(False, "bad_url", f"{url} trả lời nhưng không giống CVAT (không có thông tin phiên bản): sai link? "
                                             "Link CVAT thường là http://localhost:8080.")
    return None


def _classify(exc):
    names = [c.__name__ for c in type(exc).__mro__]
    status = getattr(exc, "status", None)
    if status in (401, 403):
        return "bad_token"
    if "IncompatibleVersionException" in names:
        return "version_mismatch"
    if isinstance(exc, (TimeoutError, socket.timeout)) or any(n in names for n in ("ReadTimeoutError", "ConnectTimeoutError", "TimeoutError")):
        return "timeout"
    if isinstance(exc, (ConnectionError, socket.gaierror)) or any(n in names for n in (
            "MaxRetryError", "NewConnectionError", "ProtocolError", "ConnectionError", "SSLError")):
        return "server_down"
    return "other"


def check(env, want_version, project, probe_first=True, probe_timeout=PROBE_TIMEOUT):
    """Chạy các bước ở docstring đầu file. env = dict(url, token, org) như cvat_io.read_env. Trả dict kết quả (xem _result)."""
    token = env.get("token")
    S = lambda x: cvat_io.scrub(x, token)             # noqa: E731
    url = cvat_io.norm_url(env.get("url"))
    try:
        import cvat_sdk
    except ImportError:
        return _result(False, "no_sdk", INSTALL_SDK)
    if probe_first and not getattr(cvat_sdk, "M28_FAKE_CVAT", False):
        pr = probe(url) if probe_timeout == PROBE_TIMEOUT else probe(url, probe_timeout)
        if pr is not None:
            return pr
    version = ""
    try:
        client = cvat_io.connect(dict(env, url=url))
        version = cvat_io.server_version(client)
        try:
            cvat_io.check_version(client, want_version)
        except SystemExit as e:
            return _result(False, "version_mismatch", S(e), server_version=version)
        user = client.users.retrieve_current_user()
        username = str(getattr(user, "username", "") or "")
        from m28core import push
        proj = push.find_project(client, project)
    except SystemExit as e:                              # connect(): thiếu cvat-sdk; find_project(): nhiều project cùng tên
        msg = S(e)
        return _result(False, "no_sdk" if "cvat-sdk" in msg and "Chưa cài" in msg else "other", msg, server_version=version)
    except Exception as exc:                             # noqa: BLE001 - mọi lỗi SDK/urllib3 đều đổi thành thông báo tiếng Việt, không traceback
        kind = _classify(exc)
        if kind == "bad_token":
            msg = ("CVAT từ chối token (401/403): token sai, đã bị thu hồi hoặc hết hạn, hoặc tài khoản không đủ quyền. "
                   "Tạo lại token trong CVAT (Settings > Security) rồi dán vào ô Token (nút CVAT ở đầu trang rà soát).")
        else:
            msg = cvat_io.translate_error(exc, dict(env, url=url), "thử kết nối")
            if not msg:
                msg = f"Lỗi không lường trước ({exc.__class__.__name__}): " + S(str(exc))[:200]
            if kind == "server_down":
                msg = f"Không kết nối được tới {url}: server tắt hoặc sai link. " + START_HINT + "."
            elif kind == "timeout":
                msg = f"Server {url} không trả lời kịp. Kiểm CVAT có đang chạy không. " + START_HINT + "."
        return _result(False, kind, S(msg), server_version=version)
    return _result(True, server_version=version, username=username, project_found=proj is not None,
                   project_id=getattr(proj, "id", None) if proj is not None else None, org=env.get("org") or "")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--project", required=True)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    env = cvat_io.read_env()
    try:
        res = check(env, a.version, a.project)
    except BaseException as e:                           # noqa: BLE001 - không để traceback (có thể chứa token) ra ngoài
        res = _result(False, "other", cvat_io.scrub(f"Lỗi không lường trước ({e.__class__.__name__}).", env.get("token")))
    print(json.dumps(res, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
