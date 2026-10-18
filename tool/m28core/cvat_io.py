"""Hàm dùng chung của push.py và collect.py: biến môi trường CVAT, lọc token, kết nối, dịch lỗi, đọc annotations.xml.

Chỉ thư viện chuẩn; `cvat_sdk` nạp LƯỜI trong connect() nên import module này (và test) không cần cài SDK. Không numpy/gradio/torch.
Token chỉ đọc từ CVAT_ACCESS_TOKEN (tiến trình con push/collect nhận nó qua môi trường; trang rà soát có thể giữ token do người dùng nhập
ở tab Cài đặt, xem tool/cai_dat.py, và đăng ký bằng register_secret()), không bao giờ in/ghi/log: mọi chuỗi đi ra ngoài (thông báo lỗi,
push.json, log) qua scrub().
"""
import datetime
import io
import json
import os
import re
import socket
import threading
import zipfile
import xml.etree.ElementTree as ET

ENV_URL, ENV_TOKEN, ENV_ORG = "CVAT_URL", "CVAT_ACCESS_TOKEN", "CVAT_ORG"
DEFAULT_PIPELINE = {"project": "m28", "prefix": "", "cvat_version": "2.77.0", "job_size": 0}
SAFE_PREFIX = "demo-"                      # tên task kiểu cũ (thời thí nghiệm): task demo-… vẫn là task của tool
RESERVED_PREFIX = "m28-"                   # task chung của nhóm (m28-gold…): tool KHÔNG BAO GIỜ tạo, nhập, xuất hay xoá
TASK_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}[A-Za-z0-9_]")     # 2–101 ký tự, đầu là chữ/số, cuối không phải "-" (demo- trống bị từ chối)


def task_name_for(person, run, prefix=""):
    """Tên task mới (QĐ-021): <người>-<đợt>, ví dụ Kien-NAP_005; mỗi máy tự đặt NAP_001, NAP_002… nên có tên người thì task của hai người không trùng.
    prefix (pipeline.json, mặc định rỗng) đứng trước; không có tên người thì chỉ <đợt>."""
    return f"{prefix}{person}-{run}" if person else f"{prefix}{run}"


def is_reserved(name):
    """Tên thuộc task chung của nhóm (m28-…, không phân biệt hoa thường)."""
    return isinstance(name, str) and name.lower().startswith(RESERVED_PREFIX)


def tool_task_name_ok(name):
    """Tên task tool được tạo / gộp / xoá: chữ không dấu, số, _ và -, bắt đầu bằng chữ hoặc số; không phải task chung m28-…
    Lớp an toàn chính khi xoá / gộp là id và tên ghi trong push.json (chính tool ghi lúc tạo task), không phải tiền tố của tên."""
    return isinstance(name, str) and bool(TASK_NAME_RE.fullmatch(name)) and not is_reserved(name)
FORMAT_IMPORT = "CVAT 1.1"
FORMAT_EXPORT = "CVAT for images 1.1"
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
MAX_XML = 200 * 1024 * 1024
NO_CVAT_MSG = ("Đặt CVAT_URL (ghi rõ http://, ví dụ set CVAT_URL=http://localhost:8080) và CVAT_ACCESS_TOKEN "
               "(set CVAT_ACCESS_TOKEN=<token của bạn>) trong CÙNG cửa sổ cmd rồi chạy lại. Không dán token vào file hay chat.")


# ---------- môi trường, token ----------
def read_env(environ=None):
    e = os.environ if environ is None else environ
    return dict(url=(e.get(ENV_URL) or "").strip(), token=(e.get(ENV_TOKEN) or "").strip(), org=(e.get(ENV_ORG) or "").strip())


def env_problem(env):
    """Lý do tiếng Việt nếu thiếu/sai biến môi trường CVAT, không thì None. Không bao giờ chứa giá trị token."""
    url = env["url"]
    if not url or not env["token"]:
        miss = [n for n, v in ((ENV_URL, url), (ENV_TOKEN, env["token"])) if not v]
        return f"Thiếu {' và '.join(miss)}. " + NO_CVAT_MSG
    if not url.startswith(("http://", "https://")):
        return f"CVAT_URL phải bắt đầu bằng http:// hoặc https:// (đang là {url!r}); thiếu thì cvat-sdk tự hiểu là https. " + NO_CVAT_MSG
    netloc = url.split("://", 1)[1].split("/", 1)[0]
    if "@" in netloc:
        return "CVAT_URL không được chứa tên đăng nhập hoặc mật khẩu (dạng http://user:pass@host). Dùng token ở CVAT_ACCESS_TOKEN."
    return None


def norm_url(url):
    return (url or "").strip().rstrip("/")


def task_url(url, task_id):
    return f"{norm_url(url)}/tasks/{task_id}"


def status_line(env):
    return f"CVAT: {env['url'] or '(thiếu CVAT_URL)'} | token: {'có' if env['token'] else 'thiếu'}"


_SECRETS = set()
_SECRETS_LOCK = threading.Lock()


def register_secret(token):
    """Đăng ký thêm một chuỗi bí mật (token người dùng nhập ở tab Cài đặt, không nằm trong os.environ) để scrub() cũng lọc nó.
    Chỉ giữ trong bộ nhớ của tiến trình, không bao giờ ghi ra đâu cả."""
    if isinstance(token, str) and len(token) >= 4:
        with _SECRETS_LOCK:
            _SECRETS.add(token)


def scrub(text, token=None):
    """Bỏ token (và dạng 'Authorization: Bearer/Token …') khỏi chuỗi trước khi in/ghi. Lọc: token truyền vào (hoặc CVAT_ACCESS_TOKEN
    trong os.environ) và mọi chuỗi đã register_secret()."""
    s = str(text)
    token = (token if token is not None else os.environ.get(ENV_TOKEN, "")) or ""
    with _SECRETS_LOCK:
        known = list(_SECRETS)
    for tok in sorted(set(known + ([token] if len(token) >= 4 else [])), key=len, reverse=True):
        s = s.replace(tok, "***")
    return re.sub(r"(?i)\b(authorization|bearer|token)(\s*[:=]\s*|\s+)(?!\*\*\*)([A-Za-z0-9._~+/=-]{12,})", r"\1\2***", s)


# ---------- pipeline.json, ghi file ----------
def load_pipeline(path=None):
    p = dict(DEFAULT_PIPELINE)
    path = path or os.path.join("config", "pipeline.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            raise SystemExit(f"Không đọc được {path} ({e}): sửa lại cho đúng JSON hoặc xoá để dùng mặc định.")
        if not isinstance(d, dict):
            raise SystemExit(f"{path} phải là một đối tượng JSON {{...}}.")
        p.update({k: v for k, v in d.items() if k in p})
    if not isinstance(p["job_size"], int) or isinstance(p["job_size"], bool) or not 0 <= p["job_size"] <= 64:
        raise SystemExit(f"job_size trong {path} phải là số nguyên từ 0 đến 64 (0 = tất cả mặt Nhận vào MỘT job).")
    for k in ("project", "cvat_version"):
        if not isinstance(p[k], str) or not p[k].strip():
            raise SystemExit(f"{k} trong {path} phải là chuỗi không rỗng.")
    if not isinstance(p["prefix"], str) or (p["prefix"] and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", p["prefix"])) or is_reserved(p["prefix"]):
        raise SystemExit(f"prefix trong {path} phải là chuỗi rỗng (tên task <người>-<đợt>) hoặc chữ không dấu, số, _ - (tối đa 32), "
                         f"không bắt đầu bằng {RESERVED_PREFIX}.")
    return p


def atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + f".tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------- kết nối, dịch lỗi ----------
def connect(env):
    """Client đã đăng nhập bằng Personal Access Token (make_client(url, access_token=...), có từ cvat-sdk 2.77). Gọi sau env_problem()."""
    try:
        from cvat_sdk import make_client
    except ImportError:
        raise SystemExit("Chưa cài cvat-sdk: gõ python -m pip install cvat-sdk==2.77.0 (cùng bản với server CVAT).")
    client = make_client(env["url"], access_token=env["token"])
    if env["org"]:
        client.organization_slug = env["org"]
    return client


def server_version(client):
    return str(client.get_server_version())


def _mm(v):
    m = re.match(r"\s*(?:\d+!)?(\d+)\.(\d+)", str(v))
    return (int(m.group(1)), int(m.group(2))) if m else None


def ban_chap_nhan(want):
    """(major, minor) của server mà tool nhận với cvat_version `want` của pipeline.json: đúng bản đó, hoặc MỘT bậc minor mới hơn, đúng danh sách bản server
    mà chính cvat-sdk khai là hỗ trợ (Client.SUPPORTED_SERVER_VERSIONS của cvat-sdk 2.77 là 2.77 và 2.78). Không đọc được `want` thì rỗng."""
    mm = _mm(want)
    return {mm, (mm[0], mm[1] + 1)} if mm else set()


def check_version(client, want):
    """Dừng nếu bản server ngoài ban_chap_nhan(cvat_version của pipeline.json). So (major, minor); trả chuỗi bản server. Server mới hơn một bậc (ví dụ
    2.78 với cvat-sdk 2.77) vẫn chạy, kèm một dòng nhắc cả đội nên dùng cùng bản."""
    got = server_version(client)
    if _mm(got) != _mm(want) and _mm(got) in ban_chap_nhan(want):
        print(f"Lưu ý: server CVAT {got} mới hơn cvat_version {want} của config\\pipeline.json một bậc; cvat-sdk {want} hỗ trợ bản này nên vẫn chạy "
              "(cả đội nên dùng cùng một bản CVAT).", flush=True)
        return got
    if _mm(got) != _mm(want):
        raise SystemExit(f"Bản server CVAT là {got} nhưng config\\pipeline.json ghi cvat_version {want}. cvat-sdk phải cùng bản với "
                         f"server: nếu server đúng là {got}, cài python -m pip install cvat-sdk=={got} rồi sửa cvat_version trong "
                         "config\\pipeline.json (ở công ty làm đúng như vậy); nếu không thì chạy lại đúng bản CVAT của nhóm.")
    return got


def _names(exc):
    return [c.__name__ for c in type(exc).__mro__]


def body_snippet(exc, token=None, n=300):
    body = getattr(exc, "body", None)
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if not body:
        body = getattr(exc, "reason", "") or ""
    return scrub(str(body), token).replace("\n", " ")[:n]


def translate_error(exc, env, doing):
    """Đổi exception của SDK/urllib3/OSError thành thông báo tiếng Việt (nguyên nhân + cách sửa), đã lọc token.
    Trả chuỗi, hoặc None nếu không nhận ra (người gọi tự xử lý)."""
    token = env.get("token")
    names = _names(exc)
    status = getattr(exc, "status", None)
    url = env.get("url") or "CVAT"
    if isinstance(status, int):
        if status in (401, 403):
            return (f"CVAT từ chối ({status}) khi {doing}: token sai, đã bị thu hồi hoặc hết hạn, hoặc tài khoản không đủ quyền. "
                    "Tạo lại token trong CVAT (Settings > Security), set CVAT_ACCESS_TOKEN=<token mới> trong cmd rồi chạy lại.")
        if status == 404:
            return (f"CVAT báo không tìm thấy (404) khi {doing}: project/task không còn trên server này hoặc CVAT_URL/CVAT_ORG sai. "
                    f"Kiểm {url} và (nếu dùng) CVAT_ORG.")
        return f"CVAT báo lỗi {status} khi {doing}: {body_snippet(exc, token)}"
    if any(n in names for n in ("IncompatibleVersionException",)):
        return (f"cvat-sdk không cùng bản với server CVAT ({scrub(exc, token)[:200]}). Cài python -m pip install cvat-sdk==<bản của server> "
                "và sửa cvat_version trong config\\pipeline.json.")
    if isinstance(exc, (ConnectionError, TimeoutError, socket.gaierror, socket.timeout)) or any(n in names for n in (
            "MaxRetryError", "NewConnectionError", "ProtocolError", "ConnectionError", "ReadTimeoutError", "TimeoutError", "SSLError")):
        return (f"Không kết nối được tới {url} khi {doing}. Nếu CVAT chạy trên máy này: mở Ubuntu (WSL), vào thư mục cvat, "
                "gõ docker compose up -d, chờ 1-2 phút rồi thử lại; kiểm CVAT_URL đúng địa chỉ và có http://.")
    return None


# ---------- tên điểm trên CVAT: SỐ 1..50 như trong tool (kiểu "so") hay tên config `<nhóm>_<k>` (kiểu "cu", project dựng trước đây) ----------
KIEU_SO, KIEU_CU = "so", "cu"
_TEN_MAC_DINH = []


def ten_so(point_names):
    """{tên điểm trong config: nhãn trên CVAT} kiểu số: điểm thứ i (từ 1, theo thứ tự config) mang nhãn "i", đúng số trên ảnh chồng của tool."""
    return {n: str(i + 1) for i, n in enumerate(point_names)}


def ten_tu_so(point_names):
    """Ngược của ten_so: {nhãn số trên CVAT: tên điểm trong config}."""
    return {str(i + 1): n for i, n in enumerate(point_names)}


def ten_config_mac_dinh():
    """Tên 50 điểm của config/m28_config.json của bản m28-prelabel đang chạy (để đọc XML từ CVAT khi người gọi không đưa danh sách tên). Rỗng nếu không đọc được."""
    if not _TEN_MAC_DINH:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "m28_config.json")
        try:
            with open(p, encoding="utf-8") as f:
                _TEN_MAC_DINH.append([q["name"] for q in json.load(f)["points"]])
        except (OSError, ValueError, KeyError, TypeError):
            _TEN_MAC_DINH.append([])
    return _TEN_MAC_DINH[0]


def doi_nhan_diem(root, mapping):
    """Đổi nhãn các <points> trong mọi <skeleton> của cây XML `root` theo `mapping` ({nhãn cũ: nhãn mới}); nhãn không có trong mapping giữ nguyên. Sửa tại chỗ, trả số điểm đã đổi."""
    n = 0
    for sk in root.iter("skeleton"):
        for p in sk.findall("points"):
            moi = mapping.get(p.get("label") or "")
            if moi is not None and moi != p.get("label"):
                p.set("label", moi)
                n += 1
    return n


def kieu_labels(labels):
    """Kiểu tên sublabel của nội dung face50_label.json: "so" nếu các sublabel tên 1..50 theo thứ tự, ngược lại "cu"."""
    subs = [s.get("name") for lb in labels for s in lb.get("sublabels", [])]
    return KIEU_SO if subs and subs == [str(i + 1) for i in range(len(subs))] else KIEU_CU


# ---------- đọc annotations.xml (theo TÊN ảnh và TÊN điểm, không theo id) ----------
def parse_annotations(xml_bytes, names=None):
    """{tên ảnh: dict(width, height, skeletons=[{label, points={tên điểm: dict(x, y, occluded, outside, low_conf)}}], n_shapes)}.
    low_conf là 'true'/'false' hoặc None nếu điểm không có thuộc tính này.
    Tên điểm trả về LUÔN là tên trong config (`<nhóm>_<k>`): nhãn SỐ của CVAT kiểu mới ("35") được đổi lại theo `names` (danh sách 50 tên điểm theo thứ tự config; không đưa thì
    đọc từ config/m28_config.json của bản đang chạy); nhãn tên cũ giữ nguyên, nên XML của project dựng trước đây vẫn đọc được."""
    if len(xml_bytes) > MAX_XML:
        raise SystemExit("File annotations.xml quá lớn (hơn 200 MB): không đọc.")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise SystemExit(f"annotations.xml không phải XML hợp lệ ({e}).")
    names = list(names) if names else ten_config_mac_dinh()
    tu_so = ten_tu_so(names) if names else {}
    out = {}
    for im in root.iter("image"):
        name = im.get("name") or ""
        d = dict(width=im.get("width"), height=im.get("height"), skeletons=[], n_shapes=0)
        for sk in im.findall("skeleton"):
            pts = {}
            for p in sk.findall("points"):
                xy = (p.get("points") or "").split(",")
                try:
                    x, y = float(xy[0]), float(xy[1])
                except (ValueError, IndexError):
                    x = y = None
                lc = None
                for a in p.findall("attribute"):
                    if a.get("name") == "low_conf":
                        lc = (a.text or "").strip().lower()
                nhan = p.get("label") or ""
                pts[tu_so.get(nhan, nhan)] = dict(x=x, y=y, occluded=p.get("occluded"), outside=p.get("outside"), low_conf=lc)
            d["skeletons"].append(dict(label=sk.get("label"), points=pts))
        d["n_shapes"] = sum(1 for tag in ("box", "polygon", "polyline", "points", "mask", "ellipse", "cuboid", "tag")
                            for _ in im.findall(tag)) + len(d["skeletons"])
        out[name] = d
    return out


def read_zip_annotations(zip_path):
    """Đọc annotations.xml trong file zip xuất từ CVAT (không giải nén ra đĩa)."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            try:
                info = z.getinfo("annotations.xml")
            except KeyError:
                raise SystemExit(f"{zip_path} không có annotations.xml (đã xuất đúng định dạng 'CVAT for images 1.1' chưa?).")
            if info.file_size > MAX_XML:
                raise SystemExit("annotations.xml trong zip quá lớn (hơn 200 MB): không đọc.")
            return z.read(info)
    except zipfile.BadZipFile:
        raise SystemExit(f"{zip_path} không phải file zip hợp lệ (tải về dở?).")


def group_of_name(point_name):
    """Nhóm của một điểm = tên điểm bỏ `_<k>` cuối: tên điểm luôn là `<nhóm>_<k>` (make_config kiểm), và tên nhóm cũng là tên label skeleton trên CVAT (QĐ-004)."""
    return str(point_name).rsplit("_", 1)[0]


def groups_from_names(point_names):
    """{nhóm: [tên điểm của nhóm theo thứ tự]} từ danh sách tên điểm, nhóm theo thứ tự xuất hiện."""
    out = {}
    for n in point_names:
        out.setdefault(group_of_name(n), []).append(n)
    return out


def merged_face(im, groups):
    """Gộp các skeleton của ảnh thành MỘT dict điểm nếu ảnh có ĐÚNG MỘT skeleton cho mỗi nhóm trong `groups` ({nhóm: [tên điểm]}) và mỗi skeleton có đúng
    tên điểm của nhóm; trả (points, vấn đề). Không đủ nhóm, thừa skeleton cùng nhóm, hay tên điểm không khớp thì points = None và vấn đề nói rõ nhóm nào."""
    by = {}
    for s in im["skeletons"]:
        by.setdefault(s["label"], []).append(s)
    pts, bad = {}, []
    for g, names in groups.items():
        sk = by.get(g, [])
        if len(sk) != 1:
            bad.append(f"nhóm {g}: {len(sk)} skeleton (cần đúng 1)")
        elif set(sk[0]["points"]) != set(names) or len(sk[0]["points"]) != len(names):
            bad.append(f"nhóm {g}: {len(sk[0]['points'])}/{len(names)} điểm đúng tên")
        else:
            pts.update(sk[0]["points"])
    extra = sorted(set(by) - set(groups))
    if extra:
        bad.append(f"có skeleton lạ {extra[:3]} (label không thuộc 7 nhóm)")
    return (None if bad else pts), bad


def _skeleton_ok(im, groups, want_flag=None):
    """Ảnh có đúng một skeleton cho mỗi nhóm (label = tên nhóm), mỗi skeleton đủ tên điểm của nhóm; mọi low_conf thuộc ('true','false') (want_flag=None)
    hoặc đúng bằng want_flag."""
    pts, _bad = merged_face(im, groups)
    if pts is None:
        return False
    vals = pts.values()
    return all(p["low_conf"] in ("true", "false") for p in vals) if want_flag is None else all(p["low_conf"] == want_flag for p in vals)


def check_faces(ann, want_nhan, want_tay, point_names, want_tay_nhap=()):
    """So kết quả xuất với kế hoạch.
    Nhận: mỗi nhóm đúng một skeleton (label = tên nhóm) đủ điểm của nhóm, low_conf là true/false. Sửa nhãn có nháp (want_tay_nhap, một phần của want_tay): như vậy
    (low_conf true ở điểm có cờ / điểm liên quan của ca khó, false ở điểm còn lại). Sửa nhãn ảnh trống (want_tay trừ want_tay_nhap): 0 shape. Nhóm suy từ tên điểm (`<nhóm>_<k>`).
    Trả dict(ok, n_nhan, n_day_du, thieu, thieu_anh, gan_tay_co_nhan (chỉ xét ảnh trống), n_tay_nhap, n_tay_nhap_day_du, tay_nhap_thieu)."""
    need = groups_from_names(point_names)
    nt = set(want_tay_nhap)
    thieu, full, thieu_anh = [], 0, []
    for name in want_nhan:
        im = ann.get(name)
        if im is None:
            thieu_anh.append(name)
        elif _skeleton_ok(im, need):
            full += 1
        else:
            thieu.append(name)
    tay_nhap_full, tay_nhap_thieu = 0, []
    for name in want_tay:
        if name not in nt:
            continue
        im = ann.get(name)
        if im is None:
            thieu_anh.append(name)
        elif _skeleton_ok(im, need):
            tay_nhap_full += 1
        else:
            tay_nhap_thieu.append(name)
    trong = [n for n in want_tay if n not in nt]
    tay_co = [n for n in trong if n in ann and ann[n]["n_shapes"] > 0]
    thieu_anh += [n for n in trong if n not in ann]
    good = not thieu and not thieu_anh and not tay_co and not tay_nhap_thieu
    return dict(ok=good, n_nhan=len(want_nhan), n_day_du=full, thieu=thieu[:20], thieu_anh=thieu_anh[:20], gan_tay_co_nhan=tay_co[:20],
                n_tay_nhap=len(nt & set(want_tay)), n_tay_nhap_day_du=tay_nhap_full, tay_nhap_thieu=tay_nhap_thieu[:20])


def safe_file_part(text):
    """Phần tên file an toàn (task, người rà): chữ, số, _ - . ; không chứa / \\ hoặc .. ; SystemExit nếu không hợp lệ."""
    t = str(text)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", t) or ".." in t:
        raise SystemExit(f"Tên {t!r} không dùng làm tên file được (chỉ chữ không dấu, số, _ - . , tối đa 128 ký tự, không có '..').")
    return t


def inside(path, base):
    try:
        p, b = os.path.realpath(path), os.path.realpath(base)
        return os.path.commonpath([p, b]) == b
    except ValueError:
        return False


def zip_bytes_with(name, data):
    """Zip trong bộ nhớ chỉ có một file (dùng cho bản CVAT giả và test)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, data)
    return buf.getvalue()
