"""Gói kết quả của MỘT phiên bấm giờ (đồng hồ ở đầu trang rà soát, nút "Save timing" trong hộp Đóng trang) để gửi nhóm trưởng tổng kết (QĐ-006).

Ghi `outputs/ket_qua/ketqua_<Pk>_<DDMM>_<đợt>.zip` (+ bản `.json` đọc được) NGOÀI git (outputs/ bị .gitignore chặn). Nội dung:
  người, nhóm (manual/assisted), đợt và bộ ảnh, số mặt, giây phiên (không tính lúc tạm dừng), số lần tạm dừng, giờ bắt đầu/kết thúc, giây từng mặt nếu có bấm
  từng mặt (không thì ghi `uoc_luong_chia_deu`), và KẾT QUẢ theo mặt: tên ảnh (không đường dẫn), nhãn cuối 50 điểm (toạ độ) nếu có, và với nhóm assisted thêm nháp
  50 điểm, điểm đã sửa và NME nháp-so-nhãn-cuối.
KHÔNG chứa ảnh, token, email, tên máy, đường dẫn tuyệt đối; có `sha256` của phần nội dung và số phiên bản định dạng. `doc_goi` kiểm lại tất cả (sha256, cấu trúc,
rò rỉ riêng tư) trước khi tin; `quet` gộp nhiều gói, loại gói hỏng/trùng với lý do rõ. Nhãn lấy từ file nhãn đã xuất (raw\\<task>\\<task>_<người>_<DDMM>.xml) và nháp từ
runs\\<đợt>\\xml\\prelabel.xml (đúng toạ độ đã nhập vào CVAT). Numpy chỉ nạp lười ở các hàm cần đo (cùng eval50).
Bản NHẬP TAY của nhóm trưởng cho người nhóm manual gán thẳng trong CVAT (m28core/nhap_tay.py, mục "Nhập tay" của tab Thống kê) là gói cùng định dạng, thêm trường
nguon_nhap="nhap_tay", ghi vào outputs/goi_nhom (ghi_goi(..., thu_muc=...)).
"""
import datetime
import hashlib
import io
import json
import os
import re
import socket
import zipfile
import zlib

FORMAT = "m28-ketqua"
PHIEN_BAN_DINH_DANG = 1
THU_MUC = os.path.join("outputs", "ket_qua")
JSON_TRONG_ZIP = "ketqua.json"
DOC_TOI = "DOC-TOI.txt"
MAX_BYTE = 64 * 1024 * 1024            # gói lớn hơn: không đọc
MAX_MAT = 20000
NGUONG_SUA_MAC_DINH = 2.0              # % IOD: điểm nháp lệch nhãn cuối hơn ngần này là "đã sửa"
CONDITIONS = ("manual", "assisted")
NGUOI_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,31}")      # tên người rà bất kỳ (= dong_ho.NGUOI_RE)
NGUOI_CU_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")            # luật tên của bản trước (có dấu _): gói đã làm bằng bản đó vẫn đọc được (= dong_ho.NGUOI_CU_RE)
PHIEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}")
TEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_ABS_PATH = re.compile(r"(?:^|[\s\"'(=:,;])(?:/(?:home|tmp|users|var|mnt|root|etc|opt|media|srv)/|[a-z]:[\\/]|\\\\[a-z0-9_.-]+\\)", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


class GoiLoi(Exception):
    """Lỗi người dùng sửa được (gói hỏng, không ghi được...). Thông báo tiếng Việt."""


# ---------- nội dung, sha256 ----------
def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_noi_dung(noi_dung):
    return hashlib.sha256(canonical(noi_dung)).hexdigest()


def dong_goi(noi_dung):
    """Vỏ gói: định dạng, số phiên bản định dạng, sha256 của nội dung, nội dung."""
    return dict(dinh_dang=FORMAT, phien_ban_dinh_dang=PHIEN_BAN_DINH_DANG, sha256=sha256_noi_dung(noi_dung), noi_dung=noi_dung)


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def kiem_rieng_tu(obj, token=None):
    """Danh sách vấn đề riêng tư trong mọi chuỗi của `obj`: đường dẫn tuyệt đối, email, tên máy, token. Rỗng = sạch."""
    from m28core import cvat_io
    host = ""
    try:
        host = (socket.gethostname() or "").strip().lower()
    except OSError:
        pass
    probs = set()
    for s in _strings(obj):
        if _ABS_PATH.search(s):
            probs.add("có đường dẫn tuyệt đối")
        if _EMAIL.search(s):
            probs.add("có địa chỉ email")
        if len(host) >= 4 and host not in ("localhost", "ubuntu", "debian") and host in s.lower():
            probs.add("có tên máy")
        if cvat_io.scrub(s, token) != s:
            probs.add("có chuỗi giống token")
    return sorted(probs)


# ---------- tên file, ghi ----------
def lam_sach_ten(text, maxlen=40):
    t = re.sub(r"[^A-Za-z0-9_-]+", "-", str(text or "").strip()).strip("-_")
    return (t or "dot")[:maxlen]


def ten_goi(nguoi, ddmm, dot):
    return f"ketqua_{nguoi}_{ddmm}_{lam_sach_ten(dot)}"


def _atomic_write(path, data):
    tmp = path + f".tmp{os.getpid()}"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _zip_bytes(vo, nd):
    buf = io.BytesIO()
    doc = (f"Gói kết quả M28 (định dạng {FORMAT} bản {PHIEN_BAN_DINH_DANG}) của {nd.get('nguoi')}, nhóm {nd.get('nhom')}, đợt {nd.get('dot')}.\n"
           "Không chứa ảnh, token, email hay đường dẫn tuyệt đối. Gửi cho nhóm trưởng; nhóm trưởng chạy: python tool/tong_ket.py --vao <thư mục chứa các gói>.\n"
           "Chỉ dùng nội bộ nhóm (phi thương mại), không đăng công khai.\n")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(JSON_TRONG_ZIP, json.dumps(vo, ensure_ascii=False, indent=1, sort_keys=True))
        z.writestr(DOC_TOI, doc)
    return buf.getvalue()


def _cung_phien(path, phien):
    """File gói đã có và cùng `phien` (ghi lại lần hai của đúng phiên đó)?"""
    try:
        nd, _p = doc_goi(path)
    except GoiLoi:
        return False
    return bool(nd and nd.get("phien") == phien)


def ghi_goi(project_root, noi_dung, ddmm=None, thu_muc=THU_MUC):
    """Ghi gói (zip + json) vào <project>/<thu_muc>/ (mặc định outputs/ket_qua; bản nhập tay của nhóm trưởng ghi vào outputs/goi_nhom). Tên: ketqua_<Pk>_<DDMM>_<đợt>;
    đã có gói của PHIÊN KHÁC cùng tên thì thêm -2, -3...; đã có gói của đúng phiên này thì ghi lại (chạy lại "Xong" khi lần trước hỏng giữa chừng). Từ chối nếu nội dung rò
    riêng tư. Trả dict(ten, zip, json) (đường dẫn tương đối)."""
    probs = kiem_rieng_tu(noi_dung)
    if probs:
        raise GoiLoi("Gói kết quả bị chặn vì " + ", ".join(probs) + " (ví dụ trong ghi chú): sửa ghi chú rồi lưu lại. Không ghi gì.")
    vo = dong_goi(noi_dung)
    d = os.path.join(project_root, thu_muc)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError as e:
        raise GoiLoi(f"Không tạo được thư mục {thu_muc} ({type(e).__name__}).")
    ddmm = ddmm or datetime.datetime.now().strftime("%d%m")
    base = ten_goi(noi_dung["nguoi"], ddmm, noi_dung.get("dot"))
    ten, k = base, 1
    while True:
        pz, pj = os.path.join(d, ten + ".zip"), os.path.join(d, ten + ".json")
        den = [p for p in (pz, pj) if os.path.exists(p)]
        if not den or all(_cung_phien(p, noi_dung["phien"]) for p in den):
            break
        k += 1
        ten = f"{base}-{k}"
    try:
        _atomic_write(pz, _zip_bytes(vo, noi_dung))
        _atomic_write(pj, json.dumps(vo, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"))
    except OSError as e:
        raise GoiLoi(f"Không ghi được gói kết quả vào {thu_muc} ({type(e).__name__}: file đang mở ở chương trình khác, hết chỗ hoặc không có quyền?).")
    rel = lambda p: os.path.join(thu_muc, os.path.basename(p))      # noqa: E731
    return dict(ten=ten, zip=rel(pz), json=rel(pj))


# ---------- đọc, kiểm ----------
def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _diem_ok(d, names):
    if not isinstance(d, dict):
        return False
    for k, v in d.items():
        if (names is not None and k not in names) or not (isinstance(v, list) and len(v) == 2 and _is_num(v[0]) and _is_num(v[1])):
            return False
    return True


def kiem_cau_truc(nd, names=None):
    """Danh sách vấn đề về cấu trúc của phần nội dung (rỗng = hợp lệ)."""
    p = []
    if not isinstance(nd, dict):
        return ["nội dung không phải đối tượng JSON"]
    if not isinstance(nd.get("phien"), str) or not PHIEN_RE.fullmatch(nd["phien"]):
        p.append("thiếu hoặc sai mã phiên")
    if not isinstance(nd.get("nguoi"), str) or not (NGUOI_RE.fullmatch(nd["nguoi"]) or NGUOI_CU_RE.fullmatch(nd["nguoi"])):   # tạo mới đã kiểm luật mới ở nơi tạo
        p.append("tên người không hợp lệ (chỉ chữ không dấu, số và dấu -, bắt đầu bằng chữ hoặc số, tối đa 32 ký tự)")
    if nd.get("nhom") not in CONDITIONS:
        p.append("nhóm không phải manual hoặc assisted")
    for k in ("dot", "task", "bo_anh", "job"):
        if k in nd and nd[k] is not None and (not isinstance(nd[k], str) or len(nd[k]) > 200):
            p.append(f"trường {k} sai kiểu")
    for k in ("so_mat", "so_lan_tam_dung"):
        if not isinstance(nd.get(k), int) or isinstance(nd.get(k), bool) or nd[k] < 0 or nd[k] > MAX_MAT:
            p.append(f"trường {k} không hợp lệ")
    for k in ("giay_phien", "giay_tam_dung"):
        if not _is_num(nd.get(k)) or nd[k] < 0:
            p.append(f"trường {k} không hợp lệ")
    if not isinstance(nd.get("uoc_luong_chia_deu"), bool):
        p.append("thiếu uoc_luong_chia_deu")
    mat = nd.get("mat_do", [])
    if not isinstance(mat, list) or len(mat) > MAX_MAT or not all(isinstance(m, dict) and _is_num(m.get("giay")) and m["giay"] > 0 for m in mat):
        p.append("mat_do (giây từng mặt) không hợp lệ")
    kq = nd.get("ket_qua", [])
    if not isinstance(kq, list) or len(kq) > MAX_MAT:
        p.append("ket_qua không hợp lệ")
    else:
        seen = set()
        for r in kq:
            if not isinstance(r, dict) or not isinstance(r.get("anh"), str) or not r["anh"] or len(r["anh"]) > 200 or "/" in r["anh"] or "\\" in r["anh"]:
                p.append("một mặt trong ket_qua thiếu tên ảnh hoặc tên có đường dẫn")
                break
            if r["anh"] in seen:
                p.append(f"tên ảnh {r['anh']} lặp lại trong gói")
                break
            seen.add(r["anh"])
            if not _diem_ok(r.get("nhan_cuoi"), names) or (r.get("nhap") is not None and not _diem_ok(r.get("nhap"), names)):
                p.append(f"nhãn hoặc nháp của {r['anh']} sai định dạng")
                break
            if r.get("nhap") is not None and nd.get("nhom") != "assisted":
                p.append(f"mặt {r['anh']} có nháp nhưng gói không phải nhóm assisted")
                break
    return p


def _doc_bytes(data, ten):
    if len(data) > MAX_BYTE:
        raise GoiLoi(f"{ten} quá lớn (hơn {MAX_BYTE // (1024 * 1024)} MB): không đọc.")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GoiLoi(f"{ten} không phải JSON hợp lệ.")


def doc_bytes(data, ten, names=None):
    """Đọc và kiểm một gói từ bytes (zip hoặc json): (nội dung, [cảnh báo]). Hỏng thì GoiLoi với lý do rõ."""
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                infos = z.infolist()
                if len(infos) > 4 or any(("/" in i.filename or "\\" in i.filename or ".." in i.filename) for i in infos):
                    raise GoiLoi(f"{ten}: zip có quá nhiều file hoặc tên file có đường dẫn (nghi ngờ): từ chối.")
                try:
                    info = z.getinfo(JSON_TRONG_ZIP)
                except KeyError:
                    raise GoiLoi(f"{ten}: zip không có {JSON_TRONG_ZIP} (không phải gói kết quả M28).")
                if info.file_size > MAX_BYTE:
                    raise GoiLoi(f"{ten}: {JSON_TRONG_ZIP} trong zip quá lớn: từ chối.")
                data = z.read(info)
        except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError, ValueError):     # dữ liệu nén hỏng, zip có mật khẩu, kiểu nén lạ
            raise GoiLoi(f"{ten}: không phải file zip hợp lệ (tải về dở, hỏng, có mật khẩu hoặc kiểu nén lạ).")
    vo = _doc_bytes(data, ten)
    if not isinstance(vo, dict) or vo.get("dinh_dang") != FORMAT:
        raise GoiLoi(f"{ten}: không phải gói kết quả M28 (thiếu dinh_dang={FORMAT}).")
    pb = vo.get("phien_ban_dinh_dang")
    if not isinstance(pb, int) or isinstance(pb, bool):
        raise GoiLoi(f"{ten}: thiếu số phiên bản định dạng.")
    if pb > PHIEN_BAN_DINH_DANG:
        raise GoiLoi(f"{ten}: định dạng bản {pb} mới hơn bản {PHIEN_BAN_DINH_DANG} mà công cụ này đọc được: cập nhật công cụ (git pull).")
    nd = vo.get("noi_dung")
    if not isinstance(nd, dict):
        raise GoiLoi(f"{ten}: thiếu phần nội dung.")
    if vo.get("sha256") != sha256_noi_dung(nd):
        raise GoiLoi(f"{ten}: sha256 không khớp (file bị sửa hoặc hỏng khi chép): xin người gửi xuất lại.")
    probs = kiem_cau_truc(nd, names)
    if probs:
        raise GoiLoi(f"{ten}: " + "; ".join(probs[:3]) + ".")
    leak = kiem_rieng_tu(nd)
    if leak:
        raise GoiLoi(f"{ten}: bị loại vì " + ", ".join(leak) + " (gói phải sạch thông tin riêng tư).")
    return nd, []


def doc_goi(path, names=None):
    """Đọc và kiểm một file gói (.zip hoặc .json): (nội dung, [cảnh báo]). Hỏng thì GoiLoi."""
    ten = os.path.basename(path)
    try:
        if os.path.getsize(path) > MAX_BYTE:
            raise GoiLoi(f"{ten} quá lớn (hơn {MAX_BYTE // (1024 * 1024)} MB): không đọc.")
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise GoiLoi(f"Không đọc được {ten} ({type(e).__name__}).")
    return doc_bytes(data, ten, names)


def _liet_ke(nguon):
    """Danh sách file gói: thư mục (file .zip/.json trong đó, cấp 1) hoặc đường dẫn file."""
    out = []
    for p in nguon:
        if os.path.isdir(p):
            out += sorted(os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith((".zip", ".json")) and not f.startswith("."))
        elif os.path.isfile(p):
            out.append(p)
    return out


def moi_hon(nd, cu):
    """Gói `nd` có tao_luc MỚI HƠN gói `cu` không: so theo thời điểm thật (ISO có múi giờ); thiếu ở cả hai hay không đọc được thì so chuỗi;
    chỉ một bên có tao_luc thì bên có là mới hơn."""
    def moc(v):
        try:
            t = datetime.datetime.fromisoformat(str(v))
            return t.timestamp() if t.tzinfo else None
        except (TypeError, ValueError):
            return None
    a, b = moc(nd.get("tao_luc")), moc(cu.get("tao_luc"))
    if a is not None and b is not None:
        return a > b
    if a is not None or b is not None:
        return a is not None
    return str(nd.get("tao_luc") or "") > str(cu.get("tao_luc") or "")


def quet(nguon, names=None, doc=None):
    """Gộp các gói từ danh sách thư mục/file. `doc` (mặc định doc_goi) đọc một đường dẫn. Trả dict(tot=[(tên, nội dung)], hong=[(tên, lý do)], trung=[(tên, lý do)]).
    Trùng = cùng mã phiên (hai file của một phiên, hoặc chép hai lần): giữ bản có tao_luc mới hơn, tên chuẩn ketqua_… trước, .zip trước .json; lý do nói rõ. Hai gói khác `phien` nhưng
    cùng (người, đợt, giờ bắt đầu) cũng bị coi là trùng."""
    doc = doc or (lambda p: doc_goi(p, names))
    by, hong, trung = {}, [], []
    for p in sorted(_liet_ke(nguon), key=lambda x: (not os.path.basename(x).startswith("ketqua_"), os.path.basename(x).lower().endswith(".json"), os.path.basename(x))):
        ten = os.path.basename(p)
        try:
            nd, _w = doc(p)
        except GoiLoi as e:
            hong.append((ten, str(e)))
            continue
        k = nd["phien"]
        cu = by.get(k)
        if cu is None:
            by[k] = (ten, nd)
        elif sha256_noi_dung(cu[1]) == sha256_noi_dung(nd):
            trung.append((ten, f"trùng nội dung với {cu[0]} (cùng phiên {k}): chỉ tính một lần"))
        elif moi_hon(nd, cu[1]):                        # so theo thời điểm thật: hai máy khác múi giờ (WSL để UTC) vẫn đúng
            trung.append((cu[0], f"cùng phiên {k} với {ten} nhưng cũ hơn: dùng {ten}"))
            by[k] = (ten, nd)
        else:
            trung.append((ten, f"cùng phiên {k} với {cu[0]} nhưng cũ hơn hoặc bằng: bỏ"))
    tot, seen = [], {}
    for _k, (ten, nd) in by.items():
        sig = (nd["nguoi"], nd.get("dot"), nd.get("bat_dau"))
        if sig in seen:
            trung.append((ten, f"cùng người, đợt và giờ bắt đầu với {seen[sig]}: coi là chép trùng"))
            continue
        seen[sig] = ten
        tot.append((ten, nd))
    tot.sort(key=lambda x: (x[1]["nguoi"], str(x[1].get("bat_dau")), x[0]))
    return dict(tot=tot, hong=hong, trung=trung)


# ---------- dựng kết quả theo mặt từ file nhãn và nháp ----------
def nhap_cua_dot(project_root, dot, cfg):
    """Nháp 50 điểm của đợt: {tên ảnh không đuôi: {tên điểm: [x, y]}} đọc từ runs/<đợt>/xml/prelabel.xml (đúng toạ độ đã nhập vào CVAT); thiếu thì thử
    eval50.read_run_pred. None nếu không có lượt đó."""
    import eval50
    if not dot or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", str(dot)):
        return None
    runs = os.path.join(project_root, "runs")
    xml = os.path.join(runs, dot, "xml", "prelabel.xml")
    if os.path.isfile(xml):
        return eval50.read_labels(xml, cfg, warn=lambda *_a: None)
    if os.path.isdir(os.path.join(runs, dot, "map50")):
        try:
            return eval50.read_run_pred(dot, cfg, runs)
        except Exception:                                                  # lượt thiếu file: coi như không có nháp
            return None
    return None


def _r2(pt):
    return [round(float(pt[0]), 2), round(float(pt[1]), 2)]


def xay_ket_qua(project_root, cfg, dieu_kien, dot, label_path=None, nguong_sua=NGUONG_SUA_MAC_DINH):
    """Kết quả theo mặt của một người. Trả (list mặt, dict thông tin: co_nhan, co_nhap, nhan_file (chỉ tên file), canh_bao=[chuỗi]).
    Mỗi mặt: anh, nhan_cuoi {điểm: [x, y]} (điểm outside/thiếu không có mặt), và với assisted có nháp: nhap, diem_da_sua [tên điểm], nme_nhap_so_nhan_cuoi (% IOD)."""
    import eval50
    info = dict(co_nhan=False, co_nhap=False, nhan_file="", canh_bao=[])
    if not label_path or not os.path.isfile(label_path):
        info["canh_bao"].append("chua_co_nhan")
        return [], info
    msgs = []
    labels = eval50.read_labels(label_path, cfg, warn=msgs.append)
    info.update(co_nhan=bool(labels), nhan_file=os.path.basename(label_path))
    if not labels:
        info["canh_bao"].append("nhan_rong")
        return [], info
    out, co_nhap = ket_qua_tu_nhan(project_root, cfg, dieu_kien, dot, labels, nguong_sua)
    info["co_nhap"] = co_nhap
    if dieu_kien == "assisted" and not co_nhap:
        info["canh_bao"].append("thieu_nhap")
    return out, info


def ket_qua_tu_nhan(project_root, cfg, dieu_kien, dot, labels, nguong_sua=NGUONG_SUA_MAC_DINH):
    """Phần dựng của xay_ket_qua từ nhãn ĐÃ ĐỌC ({tên ảnh không đuôi: {điểm: [x, y]}}, ví dụ gộp từ nhiều file theo job của mục Nhập tay). Trả (list mặt, co_nhap):
    nhóm assisted thì nháp lấy ở runs/<đợt>/ của máy này (nhap_cua_dot); không có nháp thì các mặt chỉ có nhãn cuối."""
    import eval50
    from m28core import so_sanh
    draft = nhap_cua_dot(project_root, dot, cfg) if dieu_kien == "assisted" else None
    names = {p["name"] for p in cfg["points"]}
    out = []
    for stem in sorted(labels):
        fin = {k: _r2(v) for k, v in labels[stem].items() if k in names}
        r = dict(anh=stem, nhan_cuoi=fin)
        nh = (draft or {}).get(stem)
        if dieu_kien == "assisted" and nh:
            r["nhap"] = {k: _r2(v) for k, v in nh.items() if k in names}
            sua = so_sanh.diem_sua(r["nhap"], fin, cfg, nguong_sua)
            r["diem_da_sua"] = sorted(sua["sua"] | sua["xoa"], key=lambda n: [p["name"] for p in cfg["points"]].index(n))
            sc = eval50.face_scores(r["nhap"], fin, cfg)
            r["nme_nhap_so_nhan_cuoi"] = round(sc["nme"], 4) if sc.get("ok") else None
        out.append(r)
    return out, bool(draft)
