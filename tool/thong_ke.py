"""Thống kê M28: CHỈ BA CHỈ SỐ của thí nghiệm hai nhóm độc lập (QĐ-006). Đọc dữ liệu đã có; KHÔNG ghi vào runs\\, raw\\, final\\, data\\.

    python tool\\thong_ke.py [--luot-nhap <lượt>] [--nguong-sua 2] [--tat-ca-task] [--moi-bo-anh] [--gom-ttest] [--timing <thư mục|file>] [--goi <thư mục|file> ...]
        [--chi-goi] [--out outputs\\thong_ke]

Ghi outputs\\thong_ke\\<YYYYMMDD-HHMM>\\: thong_ke.html (một file tự chứa, sáng/tối theo hệ điều hành, không ảnh) + CSV (utf-8-sig, ô chữ an toàn công thức, dấu chấm thập phân):
  nme.csv, nme_nhap.csv (theo mặt), nme_nhan_cuoi.csv, ti_le_sua.csv, thoi_gian.csv, thoi_gian_nguoi.csv, ngoai_lai.csv.
Hai nhóm: manual (gán tay hoàn toàn) và assisted (dùng tool, sửa nháp); mỗi người một nhóm (config\\nhom_thi_nghiem.json, hoặc ghi trong gói kết quả); cả hai làm CÙNG bộ ảnh.
  (1) NME của nháp: đáp án = nhãn gán tay của nhóm MANUAL trên cùng ảnh (nhiều người thì trung bình theo tên điểm; ảnh chưa có nhãn manual thì "chưa có đáp án");
      thêm NME của nhãn cuối nhóm ASSISTED so với cùng đáp án (kiểm "nhanh hơn mà nhãn không kém đi").
  (2) Tỉ lệ điểm phải sửa (chỉ nhóm assisted, ngưỡng mặc định 2% IOD; điểm xoá/ẩn tính là đã sửa).
  (3) Thời gian: giây/mặt mỗi nhóm (trung vị, trung bình nhân), % nhanh hơn của assisted so với manual (mục tiêu >= 20%), KTC 90% bằng cluster bootstrap (bốc người rồi bốc mặt,
      seed 28, 2.000 lần); mỗi nhóm < 2 người thì chỉ có kết quả mô tả.
Nguồn: gói kết quả (outputs\\ket_qua, outputs\\goi_nhom, --goi; gồm cả BẢN NHẬP TAY của nhóm trưởng cho người nhóm manual gán thẳng trong CVAT không qua tool, m28core\\nhap_tay.py,
tính y như gói của đồng hồ) + file nhãn raw\\ + dòng bấm giờ timing_P*.csv (bản của đồng hồ ở đầu trang hay facetimer). Phần tính ở m28core\\so_sanh.py,
dùng chung với tool\\tong_ket.py (nhóm trưởng chỉ cần gói của các thành viên). Quy tắc: ô số kèm n; n < 5 ghi "n quá nhỏ"; chưa có dữ liệu thì khung trống nói rõ cần file nào, ai làm ra,
không bao giờ hiện 0 hay số mẫu; Ttest ẩn mặc định; mặt xoá mềm không vào số đo; HTML xuất không ảnh mặt, không mã tài xế, không đường dẫn tuyệt đối.
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import ca_kho  # noqa: E402
import nap_anh  # noqa: E402
from m28core import bang_mat, collect, goi_kq, loai_tru, nhom as nhom_mod, so_sanh, tach_job, ten_nguoi, toc_do  # noqa: E402

N_NHO = so_sanh.N_NHO
MUC_TIEU_NHANH_HON = so_sanh.MUC_TIEU_NHANH_HON
MUC_TIEU_MAT_HONG = 10.0                 # % IOD (eval50.BAD)
NGUONG_SUA = so_sanh.NGUONG_SUA_MAC_DINH
NGUONG_SUA_MIN, NGUONG_SUA_MAX = 0.5, 10.0
DIEU_KIEN_VI = {"manual": "Gán tay hoàn toàn (manual)", "assisted": "Dùng tool, sửa nháp (assisted)"}
THU_MUC_DA_NAP = os.path.join("outputs", "goi_da_nap")                 # gói của người khác nhóm trưởng đã nạp ở tab Thống kê: lưu lại để mở trang lần sau vẫn còn
THU_MUC_GOI = (os.path.join("outputs", "ket_qua"), os.path.join("outputs", "goi_nhom"), THU_MUC_DA_NAP)
_KHOA_GOI_NAP = threading.RLock()                                            # Load & Calculate và Remove package chạy ở hai hàng đợi khác nhau: không chuyển file chồng nhau
THU_MUC_DA_NAP_BO = "_da_bo"                                                # thư mục con: gói đã gỡ (không xoá; thống kê không đọc thư mục con)
_TEN_GOI_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,150}\.(?:zip|json)", re.I)


def _chuyen_vao(src, d, ten, copy=True):
    """Chép (copy=True) hoặc chuyển file `src` vào thư mục `d` với tên `ten`; trùng tên thì thêm _2, _3... Ghi qua file tạm rồi đổi tên. Trả tên đã dùng."""
    os.makedirs(d, exist_ok=True)
    stem, ext = os.path.splitext(ten)
    cand, k = ten, 1
    while os.path.exists(os.path.join(d, cand)):
        k += 1
        cand = f"{stem}_{k}{ext}"
    dst = os.path.join(d, cand)
    if copy:
        tmp = dst + ".tmp"
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    else:
        os.replace(src, dst)
    return cand


_moi_hon = goi_kq.moi_hon                       # một cách so "mới hơn" cho cả lúc lưu gói và lúc quét (goi_kq.quet)


def luu_goi_nap(project_root, paths, names=None):
    """Lưu các gói tải lên ở tab Thống kê vào outputs\\goi_da_nap (giữ nguyên byte, file gói không bị sửa) để lần mở trang sau vẫn còn. Gói hỏng thì không lưu.
    Cùng mã phiên với gói đã có trong các thư mục gói mặc định (outputs\\ket_qua, goi_nhom, goi_da_nap): nội dung giống hệt, hoặc bản tải lên cũ hơn/bằng (tao_luc),
    thì không chép thêm (co_san); bản tải lên MỚI HƠN (ví dụ xuất lại gói có kèm nhãn) thì lưu (moi_hon) và chuyển bản cũ của phiên đó trong goi_da_nap vào _da_bo.
    Trả dict(luu=[tên], moi_hon=[tên], da_bo=[tên file bản cũ đã chuyển vào _da_bo], co_san=[tên], loi=[(tên file tải lên, lý do)],
    chua_luu=[tên file tải lên hợp lệ mà không chép được: ô nạp nên giữ để bấm lại])."""
    with _KHOA_GOI_NAP:
        return _luu_goi_nap(project_root, paths, names)


def _luu_goi_nap(project_root, paths, names):
    out = dict(luu=[], moi_hon=[], da_bo=[], co_san=[], loi=[], chua_luu=[])
    da_co = {nd["phien"]: nd for _t, nd in goi_kq.quet([os.path.join(project_root, x) for x in THU_MUC_GOI], names)["tot"]}
    d = os.path.join(project_root, THU_MUC_DA_NAP)
    for p in paths or ():
        ten = os.path.basename(p)
        try:
            nd, _w = goi_kq.doc_goi(p, names)
        except goi_kq.GoiLoi as e:
            out["loi"].append((ten, str(e)))
            continue
        cu = da_co.get(nd["phien"])
        moi_hon = False
        if cu is not None:
            if goi_kq.sha256_noi_dung(cu) == goi_kq.sha256_noi_dung(nd) or not _moi_hon(nd, cu):
                out["co_san"].append(ten)
                continue
            moi_hon = True
        if not _TEN_GOI_RE.fullmatch(ten):
            ten = "ketqua_" + re.sub(r"[^A-Za-z0-9_.-]", "_", nd["phien"]) + os.path.splitext(p)[1].lower()
        try:
            out["moi_hon" if moi_hon else "luu"].append(_chuyen_vao(p, d, ten))     # chép bản mới TRƯỚC: lỗi thì bản cũ vẫn còn nguyên chỗ
        except OSError as e:
            out["loi"].append((os.path.basename(p), f"không lưu được vào {THU_MUC_DA_NAP} ({type(e).__name__})"))   # tên file tải lên: tab vẫn tính từ file đó
            out["chua_luu"].append(os.path.basename(p))
            continue
        if moi_hon:
            try:
                out["da_bo"] += _bo_ban_cu(project_root, nd, names)
            except OSError:
                pass                                                           # bản cũ còn lại: quet vẫn chọn bản mới hơn theo tao_luc
        da_co[nd["phien"]] = nd
    return out


def _bo_ban_cu(project_root, nd_moi, names=None):
    """Chuyển (không xoá) các file trong outputs\\goi_da_nap cùng mã phiên với `nd_moi` nhưng khác nội dung vào goi_da_nap\\_da_bo (bản cũ của một gói vừa có bản mới hơn)."""
    d = os.path.join(project_root, THU_MUC_DA_NAP)
    if not os.path.isdir(d):
        return []
    sha_moi, out = goi_kq.sha256_noi_dung(nd_moi), []
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if not os.path.isfile(p) or not f.lower().endswith((".zip", ".json")):
            continue
        try:
            nd, _w = goi_kq.doc_goi(p, names)
        except goi_kq.GoiLoi:
            continue
        if nd["phien"] == nd_moi["phien"] and goi_kq.sha256_noi_dung(nd) != sha_moi:
            out.append(_chuyen_vao(p, os.path.join(d, THU_MUC_DA_NAP_BO), f, copy=False))
    return out


def bo_goi_nap(project_root, phien, names=None):
    """Gỡ gói có mã phiên `phien` khỏi outputs\\goi_da_nap: CHUYỂN (không xoá) mọi file của phiên đó (.zip và .json) vào outputs\\goi_da_nap\\_da_bo.
    Chỉ đụng thư mục goi_da_nap (gói của chính máy này trong outputs\\ket_qua và bản nhập tay trong goi_nhom không gỡ ở đây). Trả [tên file đã chuyển]."""
    with _KHOA_GOI_NAP:
        return _bo_goi_nap(project_root, phien, names)


def _bo_goi_nap(project_root, phien, names):
    d = os.path.join(project_root, THU_MUC_DA_NAP)
    if not phien or not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if not os.path.isfile(p) or not f.lower().endswith((".zip", ".json")):
            continue
        try:
            nd, _w = goi_kq.doc_goi(p, names)
        except goi_kq.GoiLoi:
            continue
        if nd["phien"] == phien:
            out.append(_chuyen_vao(p, os.path.join(d, THU_MUC_DA_NAP_BO), f, copy=False))
    return out
NGUON_NHAP_TAY = "nhap_tay"              # gói do nhóm trưởng nhập tay (m28core\\nhap_tay.py) cho người nhóm manual gán thẳng trong CVAT: tính như gói của đồng hồ
TIMING_UU_TIEN = os.path.join("outputs", "timing")
HAN_CHE = ("Thiết kế hai nhóm độc lập: tốc độ từng người khác nhau lẫn vào kết quả (nên có một đợt khởi động chung hoặc chia nhóm cân tốc độ); ít người mỗi nhóm thì khoảng tin cậy rất rộng.",
           "Đồng hồ đo cả PHIÊN: giây/mặt là ước lượng chia đều (cả phiên ÷ số mặt) trừ khi người gán bấm từng mặt; bootstrap theo mặt trong người khi đó không thêm thông tin.",
           "NME của nháp so với nhãn gán tay của nhóm manual: đáp án cũng là nhãn người (có sai số), nên NME là cận trên của sai số thật của nháp khi đáp án nhiễu.")


def _trong(ly_do, can, ai):
    return dict(ly_do=ly_do, can=can, ai=ai)


def _git_commit(project_root):
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=project_root, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "không rõ"
    except (OSError, subprocess.SubprocessError):
        return "không rõ"


def _stem(name):
    import eval50
    return eval50.stem(name)


# ---------- đọc nguồn ----------
def hang_thoi_gian_goi(nd, ten):
    """Các dòng thời gian của một gói: từng mặt nếu có mat_do, không thì ước lượng chia đều (giây phiên / số mặt)."""
    out = []
    base = dict(person=nd["nguoi"], condition=nd["nhom"], task=nd.get("task", ""), dot=nd.get("dot", ""), bo_anh=nd.get("bo_anh", ""), phien=nd["phien"],
                sua_tay=int(bool(nd.get("sua_tay"))), canh_bao=",".join(nd.get("canh_bao") or []), nguon="goi", file=ten, date=str(nd.get("bat_dau", ""))[:10])
    if nd.get("mat_do"):
        for m in nd["mat_do"]:
            out.append(dict(base, seconds=float(m["giay"]), face_id=m.get("face_id", ""), warmup=int(m.get("warmup", 0)), interrupted=int(m.get("so_lan_tam_dung", 0) > 0), uoc_luong=False,
                            seq=m.get("seq")))
    elif nd.get("so_mat", 0) > 0 and nd.get("giay_phien", 0) > 0:
        each = nd["giay_phien"] / nd["so_mat"]
        for i in range(nd["so_mat"]):
            out.append(dict(base, seconds=each, face_id=f"{nd.get('dot', '') or 'X'}_{i + 1:02d}", warmup=0, interrupted=0, uoc_luong=True, seq=i + 1))
    return out


def doc_nguon_goi(project_root, goi, names, mac_dinh=True):
    """Kết quả goi_kq.quet: gói trong outputs\\ket_qua, outputs\\goi_nhom (nếu mac_dinh) và các đường dẫn `goi` thêm (thư mục hoặc file)."""
    nguon = ([os.path.join(project_root, d) for d in THU_MUC_GOI] if mac_dinh else []) + [g for g in (goi or ()) if g]
    return goi_kq.quet(nguon, names)


def doc_timing(project_root, timing, phien_goi):
    """(rows, files, loi, trung): dòng bấm giờ từ timing_P*.csv. Dòng cùng mã phiên với một gói thì bỏ (gói thắng). Thiếu cột: bỏ file đó, báo tên cột, file khác vẫn đọc.
    Trùng khoá (người, task, khối, seq): giữ dòng của đồng hồ ở đầu trang (outputs\\timing) rồi dòng đọc trước; liệt kê, không lặng lẽ."""
    paths = toc_do.tim_file(project_root, timing)
    paths.sort(key=lambda p: (0 if os.path.realpath(os.path.dirname(p)) == os.path.realpath(os.path.join(project_root, TIMING_UU_TIEN)) else 1, os.path.basename(p), p))
    rows, files, loi, trung, seen = [], [], [], [], {}
    for p in paths:
        ten = bang_mat.rel(project_root, p)
        try:
            rs = toc_do.doc_file(p, ten)
        except toc_do.TocDoLoi as e:
            loi.append(str(e))
            continue
        files.append(ten)
        for r in rs:
            if r.get("phien") and r["phien"] in phien_goi:
                continue
            k = (r["person"], r["task"], r["block"], r["seq"])
            if k in seen and r["seq"] is not None:
                trung.append(f"{r['person']} {r['task']} {r['block']} seq {r['seq']}: {ten} trùng với {seen[k]}")
                continue
            seen[k] = ten
            rows.append(dict(r, nguon="csv"))
    return rows, files, loi, trung


def _luot_cua_task(project_root, task):
    """Lượt trong runs\\*\\push.json có `task` trùng tên (chưa xoá task), mới nhất theo cap_nhat; '' nếu không có. Chỉ đọc."""
    best = None
    for p in glob.glob(os.path.join(glob.escape(os.path.join(project_root, "runs")), "*", "push.json")):
        try:
            with open(p, encoding="utf-8") as f:
                j = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(j, dict) and j.get("task") == task and j.get("trang_thai") != "task_deleted":
            key = str(j.get("cap_nhat") or "")
            if best is None or key > best[0]:
                best = (key, os.path.basename(os.path.dirname(p)))
    return best[1] if best else ""


def kiem_hop_ly_nhap(mats, cfg, nguong):
    """Cảnh báo khi nháp có vẻ KHÔNG phải nháp của người đó: với nhóm assisted điểm người không sửa gần như trùng toạ độ nháp (<= 0,05 px sau làm tròn XML); một người mà
    không có điểm nào trùng, hoặc hơn 80% điểm lệch quá ngưỡng, thì có thể chọn sai lượt nháp hoặc sai hệ toạ độ. Trả [chuỗi cảnh báo]."""
    by = {}
    for m in mats:
        r = so_sanh.diem_sua(m["nhap"], m["nhan"], cfg, nguong)
        if not r["ok"]:
            continue
        e = by.setdefault(m["nguoi"], dict(n=0, trung=0, lech=0))
        e["n"] += r["n_nhap"]
        e["lech"] += len(r["sua"]) + len(r["xoa"])
        e["trung"] += sum(1 for d in r["khoang_cach"].values() if d * (r["iod"] or 1) / 100.0 <= so_sanh.SAI_SO_DIEM)
    out = []
    for p, e in sorted(by.items()):
        if e["n"] and (e["trung"] == 0 or e["lech"] > 0.8 * e["n"]):
            out.append(f"{p}: " + ("không có điểm nào giữ nguyên toạ độ nháp" if e["trung"] == 0 else f"{e['lech']}/{e['n']} điểm lệch quá ngưỡng sửa")
                       + ": có thể chọn sai lượt nháp hoặc sai hệ toạ độ (kiểm 'Lượt chứa nháp').")
    return out


def _job_only_groups(raw_dir, done):
    """{tên gốc: [file job]} cho các file `<task>_<người>_<DDMM>_job<id>.xml` (trong raw\\ hoặc raw\\<task>\\) không có file cả task cùng gốc (`done`)."""
    by = {}
    for d, f in collect.raw_listing(raw_dir):
        m = tach_job.JOB_RE.match(f)
        if m and (m.group("goc") + ".xml") not in done:
            by.setdefault(m.group("goc"), []).append(os.path.join(d, f))
    return by


def doc_nhan_raw(project_root, cfg, nhom_cfg, luot_nhap, tat_ca_task, mat_phien_goi):
    """Nhãn từ raw\\: [(dict mặt)], files, ghi_chu, canh_bao. Điều kiện của nhãn = nhóm của người (config\\nhom_thi_nghiem.json), không có thì suy từ tên task (m28-manual,
    m28-assisted...), không rõ thì đếm riêng. Nháp của nhóm assisted: lượt chứa nháp (luot_nhap) hoặc lượt trong push.json của task demo-…. Chỉ ĐỌC raw\\, không final\\."""
    import eval50
    raw_dir = os.path.join(project_root, "raw")
    faces, files, notes, warns = [], [], [], []
    if not os.path.isdir(raw_dir):
        return faces, files, notes, warns
    names = sorted(f for _d, f in collect.raw_listing(raw_dir))         # raw\\<task>\\ (cách lưu hiện nay) và raw\\ (bản cũ)
    tasks = sorted({m.group("task") for m in (collect.RAW_RE.match(f) for f in names) if m})
    items = []                                                         # (task, who, day, [đường dẫn])
    for t in tasks:
        for who, p in collect.latest_raw_files(t, raw_dir).items():
            items.append((t, who, collect.RAW_RE.match(os.path.basename(p)).group("day"), [p], False))
    for goc, ps in _job_only_groups(raw_dir, set(names)).items():
        m = collect.RAW_RE.match(goc + ".xml")
        if m:
            items.append((m.group("task"), m.group("who"), m.group("day"), ps, True))
    for task, who, day, paths, from_jobs in items:
        cond_task, why = bang_mat.dieu_kien_tu_task(task)
        if cond_task == "bo_qua" and not tat_ca_task:                      # task thử (practice/check/smoke) không phải nhãn thí nghiệm, bất kể người nào gán
            notes.append(dict(file=bang_mat.rel(project_root, paths[0]), task=task, nguoi=who, ghi_chu="bỏ qua: " + why + " (bật 'Mọi task' để đưa vào)"))
            continue
        cond = nhom_cfg["nhom"].get(who)
        if cond is None:
            cond = bang_mat.DIEU_KIEN_KHONG_RO if cond_task == "bo_qua" else cond_task
        if cond not in ("manual", "assisted"):
            notes.append(dict(file=bang_mat.rel(project_root, paths[0]), task=task, nguoi=who, dieu_kien=cond,
                              ghi_chu=f"không rõ nhóm của {who}: điền config\\nhom_thi_nghiem.json hoặc dùng gói kết quả; đếm riêng, không vào số theo nhóm"))
            continue
        labels, seen_job = {}, {}
        for p in sorted(paths, key=lambda x: int((tach_job.JOB_RE.match(os.path.basename(x)) or collect.RAW_RE.match(os.path.basename(x))).groupdict().get("job") or 0)):
            msgs = []
            try:
                got = eval50.read_labels(p, cfg, warn=msgs.append)
            except (SystemExit, OSError) as e:
                warns.append(f"{os.path.basename(p)}: không đọc được ({type(e).__name__})")
                continue
            if any("CŨ" in x for x in msgs):
                notes.append(dict(file=bang_mat.rel(project_root, p), task=task, nguoi=who, dieu_kien=cond, ghi_chu="nhãn cũ (label face50 một skeleton): không dùng"))
            for k, v in got.items():
                if k in labels:
                    warns.append(f"ảnh {k} có ở hai file job của {task}/{who}: giữ job có id nhỏ")
                    continue
                labels[k] = v
        run, draft = "", None
        if cond == "assisted":
            run = luot_nhap or _luot_cua_task(project_root, task)
            draft = goi_kq.nhap_cua_dot(project_root, run, cfg) if run else None
            if not draft:
                notes.append(dict(file=bang_mat.rel(project_root, paths[0]), task=task, nguoi=who, dieu_kien=cond,
                                  ghi_chu="không có nháp liên kết: chọn 'Lượt chứa nháp' đã dùng để dựng task (không đoán lượt)"))
        ten_file = f"{task}_{who}_{day}.xml"                           # tên file nhãn (bản gộp job cũng mang tên này)
        for stem, pts in labels.items():
            if (who, stem) in mat_phien_goi or (who, stem, ten_file) in mat_phien_goi:
                continue
            faces.append(dict(nguoi=who, dieu_kien=cond, anh=stem, nhan=pts, nhap=(draft or {}).get(stem), nguon="raw", task=task, dot=run))
        files.append(dict(file=", ".join(bang_mat.rel(project_root, p) for p in paths) if from_jobs else bang_mat.rel(project_root, paths[0]), task=task, nguoi=who, dieu_kien=cond,
                          n_anh=len(labels), ghi_chu="ghép từ các file theo job" if from_jobs else ""))
    return faces, files, notes, warns


def mat_tu_goi(nd):
    out = []
    for r in nd.get("ket_qua", []):
        out.append(dict(nguoi=nd["nguoi"], dieu_kien=nd["nhom"], anh=r["anh"], nhan=r.get("nhan_cuoi") or None, nhap=r.get("nhap"), nguon="goi", task=nd.get("task", ""),
                        dot=nd.get("dot", "")))
    return out


# ---------- tổng hợp ----------
def _thong_bao_trong_nme(co_manual, co_nhap_assisted, co_assisted):
    if not co_manual:
        return _trong("Chưa có nhãn gán tay của nhóm manual: đây là ĐÁP ÁN để đo nháp (cả hai nhóm làm cùng bộ ảnh).",
                      "gói kết quả của người nhóm manual (outputs\\ket_qua\\ketqua_<Pk>_*.zip), bản nhập tay (mục Nhập tay ở tab Thống kê: thời gian + file nhãn xuất từ CVAT) "
                      "hoặc raw\\<task>\\<task>_<Pk>_<DDMM>.xml; điền config\\nhom_thi_nghiem.json",
                      "người nhóm manual (gán thẳng trong CVAT: gửi nhóm trưởng file nhãn xuất 'CVAT for images 1.1' và thời gian làm để nhập tay)")
    if not co_assisted:
        return _trong("Chưa có nháp của nhóm assisted để đo.", "gói kết quả của người nhóm assisted (có nháp và nhãn cuối)", "người nhóm assisted")
    if not co_nhap_assisted:
        return _trong("Có nhãn nhóm assisted nhưng chưa nhãn nào ghép được với nháp (không có nháp liên kết).",
                      "gói kết quả có nháp (assisted, đã có runs\\<đợt>\\xml\\prelabel.xml lúc Xong) hoặc chọn 'Lượt chứa nháp' cho nhãn trong raw\\", "người nhóm assisted")
    return None


def _canh_bao_trung_anh(goi_ok):
    """Cảnh báo khi hai gói của CÙNG người nhưng KHÁC đợt có tên ảnh chung: một người không gán một ảnh hai lần trong thí nghiệm, nên đó là cùng một lần làm ghi dưới hai tên đợt
    (ví dụ bản nhập tay gõ tên bộ ảnh rồi thêm lại với tên lượt): giờ bị tính hai lần, mặt trùng chỉ lấy ở gói đầu. Cùng đợt thì cảnh báo 'cùng đợt' của tinh đã nói, không lặp.
    Chỉ nêu số ảnh trùng, không nêu tên ảnh."""
    by, out = {}, []
    for t, nd in goi_ok:
        by.setdefault(nd["nguoi"], []).append((t, str(nd.get("dot") or ""), {r["anh"] for r in nd.get("ket_qua", []) if isinstance(r, dict) and r.get("anh")}))
    for ng, gs in sorted(by.items()):
        for i, (ta, da, aa) in enumerate(gs):
            for tb, db, ab in gs[i + 1:]:
                n = len(aa & ab)
                if n and da != db:
                    out.append(f"{ng} có {n} ảnh trùng tên ở hai gói khác đợt ({ta}: đợt {da or '(không tên)'}; {tb}: đợt {db or '(không tên)'}): một người không gán một ảnh "
                               "hai lần trong thí nghiệm, nên nhiều khả năng là cùng một lần làm ghi hai lần: thời gian bị tính hai lần và mặt trùng chỉ lấy ở gói đầu (có thể mất nháp); "
                               "bỏ gói thừa (nhập tay: Remove entry).")
    return out


def tinh(project_root, luot_nhap=None, nguong_sua=NGUONG_SUA, tat_ca_task=False, gom_ttest=False, timing=None, goi=(), chi_bo_anh=True, chi_goi=False, now=None):
    """Thống kê ba chỉ số (dict st). Tính khi cần (tab chọn / CLI), không tính lúc mở trang. Chỉ đọc. Lỗi người dùng sửa được: bang_mat.BangLoi / toc_do.TocDoLoi.
    chi_goi=True và có `goi`: CHỈ đọc các gói đã nêu (không outputs\\ket_qua, không raw\\, không timing): đúng việc của tool\\tong_ket.py."""
    import eval50
    try:
        nguong = float(nguong_sua)
    except (TypeError, ValueError):
        raise bang_mat.BangLoi("Ngưỡng sửa phải là một số (% IOD).")
    if not NGUONG_SUA_MIN <= nguong <= NGUONG_SUA_MAX:
        raise bang_mat.BangLoi(f"Ngưỡng sửa phải từ {NGUONG_SUA_MIN:g} đến {NGUONG_SUA_MAX:g} % IOD.")
    cfg = bang_mat.load_cfg(project_root)
    names = [p["name"] for p in cfg["points"]]
    nhom_cfg = nhom_mod.doc(project_root)
    now = now or datetime.datetime.now().astimezone()
    quet = doc_nguon_goi(project_root, goi, set(names), mac_dinh=not (chi_goi and goi))
    goi_ok, doi_ten = ten_nguoi.ap_dung(quet["tot"], ten_nguoi.doc(project_root))             # nhóm trưởng đặt lại tên người cho từng gói (tab Thống kê)
    phien_goi = {nd["phien"] for _t, nd in goi_ok}
    mat_goi = {(nd["nguoi"], r["anh"]) for _t, nd in goi_ok for r in nd.get("ket_qua", [])}
    for _t, nd in goi_ok:                           # gói đã đặt tên: nhãn raw\\ theo TÊN GỐC chỉ bị bỏ khi đúng là file nhãn gói đã dùng (nhan_file), vì tên gốc
        goc = nd.get("nguoi_goc")                   # hay là P1 mặc định mà người P1 thật cũng có file raw riêng
        if goc and goc != nd["nguoi"] and nd.get("nhan_file"):
            for r in nd.get("ket_qua", []):
                mat_goi.add((goc, r["anh"], nd["nhan_file"]))
    faces = [m for _t, nd in goi_ok for m in mat_tu_goi(nd)]
    rows_t = [r for t, nd in goi_ok for r in hang_thoi_gian_goi(nd, t)]
    files_raw, notes_raw, warns, files_timing, loi_timing, trung_timing = [], [], [], [], [], []
    if not chi_goi:
        f2, files_raw, notes_raw, w2 = doc_nhan_raw(project_root, cfg, nhom_cfg, luot_nhap, tat_ca_task, mat_goi)
        faces += f2
        warns += w2
        rt, files_timing, loi_timing, trung_timing = doc_timing(project_root, timing, phien_goi)
        rows_t += rt
    man = bang_mat.read_manifest(project_root)
    seen, uniq, n_ttest, n_xoa_mem, bo_dup = set(), [], 0, 0, 0
    excl_cache = {}
    for m in faces:
        k = (m["nguoi"], m["anh"])
        if k in seen:
            bo_dup += 1
            continue
        seen.add(k)
        if m.get("dot") and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", m["dot"]):
            ex = excl_cache.setdefault(m["dot"], loai_tru.read_excluded(os.path.join(project_root, "runs", m["dot"])))
            if m["anh"] in ex:
                n_xoa_mem += 1
                continue
        if (man.get(m["anh"]) or {}).get("set") == "Ttest" and not gom_ttest:
            n_ttest += 1
            continue
        uniq.append(m)
    faces = uniq
    manual = [m for m in faces if m["dieu_kien"] == "manual" and m["nhan"]]
    assisted = [m for m in faces if m["dieu_kien"] == "assisted" and m["nhan"]]
    ref = so_sanh.tham_chieu(manual, cfg)
    st = dict(meta=dict(ngay=now.strftime("%d/%m/%Y %H:%M"), ngay_ts=now.strftime("%Y%m%d-%H%M"), commit=_git_commit(project_root),
                        config_version=cfg.get("version", cfg.get("config_version", "?")), nguong_sua=nguong, gom_ttest=bool(gom_ttest), ttest_an=n_ttest, co_manifest=bool(man),
                        tat_ca_task=bool(tat_ca_task), chi_bo_anh=bool(chi_bo_anh), luot_nhap=luot_nhap or "", chi_goi=bool(chi_goi), n_xoa_mem=n_xoa_mem, n_mat_trung=bo_dup,
                        canh_bao=list(warns)),
              nguon=dict(goi=[t for t, _n in goi_ok], goi_hong=quet["hong"], goi_trung=quet["trung"], doi_ten=doi_ten, nhan_raw=files_raw, nhan_bo_qua=notes_raw, timing=files_timing,
                         timing_loi=loi_timing, timing_trung=trung_timing, goi_nhap_tay=[t for t, nd in goi_ok if nd.get("nguon_nhap") == NGUON_NHAP_TAY]),
              nhom=dict(cau_hinh=nhom_cfg["nhom"], bo_anh=nhom_cfg["bo_anh"], co_file=nhom_cfg["co_file"], loi=nhom_cfg["loi"],
                        nguoi={c: sorted({r["nguoi"] for r in faces if r["dieu_kien"] == c} | {r["person"] for r in rows_t if r["condition"] == c}) for c in so_sanh.CONDITIONS}))
    cap = {}
    for t, nd in goi_ok:                                                   # cùng người + đợt ở nhiều gói (đồng hồ và nhập tay, hoặc gửi trùng): giờ có thể bị tính hai lần
        cap.setdefault((nd["nguoi"], str(nd.get("dot") or "")), []).append(t)
    for (ng, dt), ts in sorted(cap.items()):
        if len(ts) > 1:
            st["meta"]["canh_bao"].append(f"{ng} có {len(ts)} gói cho cùng đợt {dt or '(không tên)'} ({', '.join(ts)}): nếu là cùng một lần làm thì thời gian bị "
                                          "tính nhiều lần; bỏ gói thừa (nhập tay: Remove entry).")
    st["meta"]["canh_bao"] += _canh_bao_trung_anh(goi_ok)
    if st["meta"]["ttest_an"] and not gom_ttest:
        st["meta"]["canh_bao"].append(f"Ttest đang ẩn ({n_ttest} mặt): Ttest là tập đo một lần của đề tài; chỉ bật 'Gồm Ttest' đúng buổi đo.")
    if not man:
        st["meta"]["canh_bao"].append("Chưa có data\\manifest.csv nên không biết mặt nào thuộc Ttest (không ẩn được).")
    # kiểm hai nhóm làm cùng bộ ảnh
    a_m, a_a = {m["anh"] for m in manual}, {m["anh"] for m in assisted}
    st["kiem"] = dict(n_manual=len(a_m), n_assisted=len(a_a), chung=len(a_m & a_a), chi_manual=len(a_m - a_a), chi_assisted=len(a_a - a_m),
                      vi_du_lech=sorted((a_m ^ a_a))[:5], lech=bool(a_m and a_a and (a_m != a_a)))
    if st["kiem"]["lech"]:
        st["meta"]["canh_bao"].append(f"Hai nhóm KHÔNG làm cùng bộ ảnh: {st['kiem']['chung']} ảnh chung, {st['kiem']['chi_manual']} chỉ nhóm manual có, {st['kiem']['chi_assisted']} chỉ nhóm assisted có "
                                      f"(ví dụ {', '.join(st['kiem']['vi_du_lech'][:3])}). Chỉ ảnh chung/có đáp án được chấm NME.")
    for r in rows_t:
        g = nhom_cfg["nhom"].get(r["person"])
        if g and r["condition"] in so_sanh.CONDITIONS and g != r["condition"]:
            st["meta"]["canh_bao"].append(f"{r['person']} ghi nhóm {r['condition']} nhưng config\\nhom_thi_nghiem.json xếp {g}: kiểm lại (một lần báo).")
            break
    # (1) NME
    ass_nhap = []
    seen_a, dr = set(), {}
    for m in assisted:
        if m["nhap"] and m["anh"] not in seen_a:
            seen_a.add(m["anh"])
            dr[m["anh"]] = m["nhap"]
            ass_nhap.append(dict(nguoi=m["nguoi"], anh=m["anh"], diem=m["nhap"]))
        elif m["nhap"] and m["anh"] in dr:
            if any(abs(a - b) > so_sanh.SAI_SO_DIEM for k, v in m["nhap"].items() if k in dr[m["anh"]] for a, b in zip(v, dr[m["anh"]][k])):
                st["meta"]["canh_bao"].append(f"Ảnh {m['anh']}: nháp của hai người assisted khác nhau (> {so_sanh.SAI_SO_DIEM} px): lấy nháp của người đầu; có thể hai người dùng hai lượt nháp khác nhau.")
    st["nme"] = dict(trong=_thong_bao_trong_nme(bool(manual), bool(ass_nhap), bool(assisted)))
    st["nme"].update(n_manual_mat=len(a_m), n_nguoi_manual=len({m["nguoi"] for m in manual}), n_nguoi_ref=sorted({r["n_nguoi"] for r in ref.values()}))
    if st["nme"]["trong"] is None:
        st["nme"]["nhap"] = so_sanh.nme_nhom(ass_nhap, ref, cfg, MUC_TIEU_MAT_HONG)
        st["nme"]["nhan_cuoi"] = so_sanh.nme_nhom([dict(nguoi=m["nguoi"], anh=m["anh"], diem=m["nhan"]) for m in assisted], ref, cfg, MUC_TIEU_MAT_HONG)
        if not st["nme"]["nhap"]["mat"]:
            st["nme"]["trong"] = _trong("Có nháp và đáp án manual nhưng chưa ảnh nào có CẢ hai (hai nhóm chưa làm chung ảnh, hoặc đáp án thiếu khoảng cách hai khoé mắt).",
                                        "hai nhóm làm cùng bộ ảnh (cùng tên ảnh)", "nhóm trưởng kiểm bộ ảnh của hai nhóm")
    # (2) tỉ lệ sửa
    cap = [dict(nguoi=m["nguoi"], anh=m["anh"], nhap=m["nhap"], nhan=m["nhan"]) for m in assisted if m["nhap"]]
    if not cap:
        st["sua"] = dict(trong=_trong("Chưa có mặt nào của nhóm assisted có CẢ nháp đã nhập và nhãn cuối.",
                                      "gói kết quả nhóm assisted có nháp (Save timing ở hộp Đóng trang, sau khi collect), hoặc raw\\<task>\\<task>_<Pk>_<DDMM>.xml của task demo-… cùng lượt trong runs\\", "người nhóm assisted"))
    else:
        st["sua"] = dict(trong=None, **so_sanh.ti_le_sua(cap, cfg, nguong))
        st["meta"]["canh_bao"] += kiem_hop_ly_nhap(cap, cfg, nguong)
        by = {}
        for m in cap:
            by.setdefault(m["nguoi"], []).append(m)
        st["sua"]["theo_nguoi"] = [dict(nguoi=p, **{k: v for k, v in so_sanh.ti_le_sua(ms, cfg, nguong).items() if k in ("n_mat", "n_diem", "n_sua", "n_xoa", "ti_le", "ti_le_mat")})
                                   for p, ms in sorted(by.items())]
    # (3) thời gian
    valid = [r for r in rows_t if r.get("seconds") is not None and r["seconds"] > 0 and r.get("condition") in so_sanh.CONDITIONS]
    st["tg_loc"] = dict(tong=len(rows_t), bo_giay=len(rows_t) - len([r for r in rows_t if r.get("seconds") is not None and r["seconds"] > 0]),
                        khoi_dong=sum(1 for r in valid if r.get("warmup")), ngoai_dieu_kien=len([r for r in rows_t if r.get("condition") not in so_sanh.CONDITIONS]),
                        ngoai_bo_anh=0, khong_ro_bo_anh=0)
    t = [r for r in valid if not r.get("warmup")]
    bo_cfg = nhom_cfg["bo_anh"]
    if chi_bo_anh and bo_cfg:
        trong_bo = [r for r in t if r.get("bo_anh") == bo_cfg or r.get("dot") == bo_cfg]
        st["tg_loc"]["khong_ro_bo_anh"] = sum(1 for r in t if not (r.get("bo_anh") or r.get("dot")))
        st["tg_loc"]["ngoai_bo_anh"] = len(t) - len(trong_bo) - st["tg_loc"]["khong_ro_bo_anh"]
        t = trong_bo
    st["tg_loc"]["dung"] = len(t)
    st["thoi_gian"] = so_sanh.thoi_gian(t)
    if not t:
        st["thoi_gian"]["trong"] = _trong("Chưa có dòng bấm giờ nào dùng được (đã bỏ khởi động, giây trống/≤ 0" + (f", dòng ngoài bộ ảnh {bo_cfg}" if chi_bo_anh and bo_cfg else "") + ").",
                                          "gói kết quả (hộp Đóng trang: Save timing) hoặc outputs\\timing\\timing_<Pk>.csv", "mọi thành viên (đo bằng đồng hồ ở đầu trang)")
    else:
        st["thoi_gian"]["trong"] = None
    st["thoi_gian"]["n_dong_goi"] = sum(1 for r in t if r.get("nguon") == "goi")
    st["thoi_gian"]["n_dong_csv"] = sum(1 for r in t if r.get("nguon") == "csv")
    st["tg_rows"] = t
    st["han_che"] = list(HAN_CHE)
    return st


# ---------- bảng CSV ----------
def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:.1f}"
    return v


def nme_cols(cfg_regions, groups):
    return ["face_id", "condition", "nme", "nme_eye", "nme_p2p"] + [f"reg_{g}" for g in cfg_regions] + ["eye_open_err", "n_missing", "nguoi", "n_nguoi_dap_an", "hong"] + [f"nhom_{g}" for g in groups]


def nme_mat_rows(rows, cond, regions, groups):
    """Các dòng nme_nhap.csv / nme_nhan_cuoi.csv: cột đầu TRÙNG tên và nghĩa với nme_per_face.csv của eval50; cột thêm chỉ nối ở cuối."""
    out = []
    for r in rows:
        d = dict(face_id=r["anh"], condition=cond, nme=r["nme"], nme_eye=r["nme_eye"], nme_p2p=r["nme_p2p"])
        for g in regions:
            d[f"reg_{g}"] = r["vung"].get(g)
        d.update(eye_open_err=r["eye_open_err"], n_missing=r["n_missing"], nguoi=r["nguoi"], n_nguoi_dap_an=r["n_ref"], hong=int(r["nme"] >= MUC_TIEU_MAT_HONG))
        for g in groups:
            d[f"nhom_{g}"] = r["nhom"].get(g)
        out.append(d)
    return out


def bang_csv(st, project_root=None):
    """{tên file (không đuôi): (cột, [dict])}."""
    T = {}
    nme = st["nme"]
    if nme.get("trong") is None:
        cols = ["pham_vi", "nhom_diem", "n", "tb", "trung_vi", "n_hong", "pct_hong"]
        rows = []
        for key, ten in (("nhap", "nhap_so_voi_manual"), ("nhan_cuoi", "nhan_cuoi_assisted_so_voi_manual")):
            r = nme[key]
            rows.append(dict(pham_vi=ten, nhom_diem="tong", n=r["tong"]["n"], tb=r["tong"]["tb"], trung_vi=r["tong"]["trung_vi"], n_hong=r["tong"]["n_hong"], pct_hong=r["tong"]["ti_le_hong"]))
            rows += [dict(pham_vi=ten, nhom_diem=g, n=v["n"], tb=v["tb"], trung_vi=v["trung_vi"], n_hong=v["n_hong"], pct_hong=v["ti_le_hong"]) for g, v in r["nhom"].items()]
        T["nme"] = (cols, rows)
        regions = sorted({k for r in nme["nhap"]["mat"] + nme["nhan_cuoi"]["mat"] for k in r["vung"]})
        groups = list(nme["nhap"]["nhom"])
        T["nme_nhap"] = (nme_cols(regions, groups), nme_mat_rows(nme["nhap"]["mat"], "assisted", regions, groups))
        T["nme_nhan_cuoi"] = (nme_cols(regions, groups), nme_mat_rows(nme["nhan_cuoi"]["mat"], "assisted_nhan_cuoi", regions, groups))
    sua = st["sua"]
    if sua.get("trong") is None:
        rows = [dict(pham_vi="tong", nhom_diem="tong", n_mat=sua["n_mat"], n_diem=sua["n_diem"], n_sua=sua["n_sua"], n_xoa_an=sua["n_xoa"], ti_le_pct=sua["ti_le"], n_mat_phai_sua=sua["n_mat_phai_sua"],
                     ti_le_mat_pct=sua["ti_le_mat"], nguong_pct_iod=sua["nguong"])]
        rows += [dict(pham_vi="nhom", nhom_diem=g, n_diem=v["n_diem"], n_sua=v["n_sua"], ti_le_pct=v["ti_le"], nguong_pct_iod=sua["nguong"]) for g, v in sua["nhom"].items()]
        rows += [dict(pham_vi="nguoi", nhom_diem=p["nguoi"], n_mat=p["n_mat"], n_diem=p["n_diem"], n_sua=p["n_sua"], n_xoa_an=p["n_xoa"], ti_le_pct=p["ti_le"], n_mat_phai_sua=0,
                      ti_le_mat_pct=p["ti_le_mat"], nguong_pct_iod=sua["nguong"]) for p in sua["theo_nguoi"]]
        T["ti_le_sua"] = (["pham_vi", "nhom_diem", "n_mat", "n_diem", "n_sua", "n_xoa_an", "ti_le_pct", "n_mat_phai_sua", "ti_le_mat_pct", "nguong_pct_iod"], rows)
    tg = st["thoi_gian"]
    if tg.get("trong") is None:
        rows = [dict(nhom=c, n_nguoi=v["n_nguoi"], n_mat=v["n_mat"], trung_vi_giay=v["trung_vi"], tb_nhan_giay=v["tb_nhan"], tb_cong_giay=v["tb_cong"]) for c, v in tg["nhom"].items()]
        T["thoi_gian"] = (["nhom", "n_nguoi", "n_mat", "trung_vi_giay", "tb_nhan_giay", "tb_cong_giay"], rows)
        kl = [dict(chi_so="nhanh_hon_pct_tb_nhan", gia_tri=tg["nhanh_hon_pct"], ktc90_duoi=(tg["ktc90_pct"] or (None, None))[0], ktc90_tren=(tg["ktc90_pct"] or (None, None))[1],
                   ket_luan=tg["ket_luan"], n_boot=tg["n_boot"], muc_tieu_pct=tg["muc_tieu"], ghi_chu=tg["ly_do"]),
              dict(chi_so="nhanh_hon_pct_trung_vi", gia_tri=tg["nhanh_hon_trung_vi_pct"]),
              dict(chi_so="do_nhay_bo_ngoai_lai_pct", gia_tri=(tg["do_nhay"] or {}).get("nhanh_hon_pct"), ghi_chu=f"bỏ {(tg['do_nhay'] or {}).get('n_bo', 0)} dòng")]
        T["thoi_gian_chi_so"] = (["chi_so", "gia_tri", "ktc90_duoi", "ktc90_tren", "ket_luan", "n_boot", "muc_tieu_pct", "ghi_chu"], kl)
        T["thoi_gian_nguoi"] = (["nhom", "nguoi", "n_mat", "trung_vi_giay", "tb_nhan_giay"],
                                [dict(nhom=c, nguoi=p, n_mat=e["n_mat"], trung_vi_giay=e["trung_vi"], tb_nhan_giay=e["tb_nhan"]) for c, v in tg["nhom"].items() for p, e in v["nguoi"].items()])
        T["ngoai_lai"] = (["person", "condition", "face_id", "seconds", "ly_do"],
                          [dict(person=o["person"], condition=o["condition"], face_id=o["face_id"], seconds=o["seconds"], ly_do=f"vượt Q3 + 3·IQR (ngưỡng {o['nguong']:.1f})") for o in tg["ngoai_lai"]]
                          + [dict(d) for d in tg["danh_dau"]])
    return T


def csv_bytes(cols, rows):
    rows = [{c: _fmt(r.get(c)) for c in cols} for r in rows]
    return ca_kho.csv_text(cols, rows, safe=True).encode("utf-8-sig")


# ---------- xuất tĩnh ----------
def xuat(project_root, st, out_root=None, trong_du_an=True, tieu_de=None):
    """Ghi outputs\\thong_ke\\<YYYYMMDD-HHMM>\\ (hoặc out_root\\...). Trả (thư mục, [tên file]). Chỉ ghi dưới thư mục đó. trong_du_an=True (giao diện): out_root phải nằm
    trong thư mục dự án (realpath + commonpath); CLI cho người dùng tự chọn nơi ghi."""
    import thong_ke_html
    base = os.path.join(project_root, "outputs", "thong_ke")
    if out_root:
        base = out_root if os.path.isabs(out_root) else os.path.join(project_root, out_root)
        if trong_du_an and not nap_anh._inside(base, project_root):
            raise ValueError("Thư mục xuất nằm ngoài thư mục dự án: từ chối.")
    d = os.path.join(base, st["meta"]["ngay_ts"])
    n = 1
    while os.path.exists(d):
        n += 1
        d = os.path.join(base, f"{st['meta']['ngay_ts']}-{n}")
    files = {"thong_ke.html": thong_ke_html.trang_tinh(st, tieu_de).encode("utf-8")}
    for name, (cols, rows) in bang_csv(st).items():
        files[name + ".csv"] = csv_bytes(cols, rows)
    tmp = d + f".tmp{os.getpid()}"
    os.makedirs(tmp)
    try:
        for fn, data in files.items():
            with open(os.path.join(tmp, fn), "wb") as f:
                f.write(data)
        os.replace(tmp, d)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return d, sorted(files)


def in_tom_tat(st, ra=print):
    """Tóm tắt ra màn hình (CLI): mỗi chỉ số một dòng; trống thì nói thiếu gì. Số theo kiểu Việt (dấu phẩy thập phân)."""
    import thong_ke_html
    n = thong_ke_html.num
    for k, ten in (("nme", "NME của nháp"), ("sua", "Tỉ lệ điểm phải sửa"), ("thoi_gian", "Thời gian")):
        t = st[k].get("trong")
        if t:
            ra(f"{ten}: chưa có số — {t['ly_do']} Cần: {t['can']} ({t['ai']}).")
    if st["nme"].get("trong") is None:
        t = st["nme"]["nhap"]["tong"]
        ra(f"NME của nháp so với nhãn manual: {t['n']} mặt, trung bình {n(t['tb'], 2)}% IOD, trung vị {n(t['trung_vi'], 2)}%, hỏng (>= 10%): {t['n_hong']}.")
    if st["sua"].get("trong") is None:
        s = st["sua"]
        ra(f"Tỉ lệ điểm phải sửa (ngưỡng {n(s['nguong'], 1)}% IOD): {n(s['ti_le'], 1)}% ({s['n_sua']}/{s['n_diem']} điểm, {s['n_mat']} mặt); "
           f"{n(s['ti_le_mat'], 0)}% mặt phải sửa ít nhất một điểm.")
    tg = st["thoi_gian"]
    if tg.get("trong") is None:
        a, m = tg["nhom"]["assisted"], tg["nhom"]["manual"]
        ra(f"Thời gian: manual {m['n_nguoi']} người / {m['n_mat']} mặt, assisted {a['n_nguoi']} người / {a['n_mat']} mặt.")
        if tg["nhanh_hon_pct"] is not None:
            kt = f", KTC 90% [{n(tg['ktc90_pct'][0], 1)}; {n(tg['ktc90_pct'][1], 1)}]%" if tg["ktc90_pct"] else ""
            ra(f"  assisted nhanh hơn manual {n(tg['nhanh_hon_pct'], 1)}% (trung bình nhân){kt} → {so_sanh.KET_LUAN_VI[tg['ket_luan']]}")
        if tg["ket_luan"] == "chi_mo_ta":
            ra("  " + tg["ly_do"])


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Thống kê M28 (ba chỉ số, thiết kế hai nhóm độc lập): NME của nháp, tỉ lệ điểm phải sửa, so sánh thời gian manual với assisted. "
                                 "Xuất CSV + HTML tĩnh (không ảnh mặt) vào outputs\\thong_ke\\<ngày-giờ>\\. Chỉ đọc dữ liệu.")
    ap.add_argument("--luot-nhap", default=None, help="lượt chứa NHÁP cho nhãn trong raw\\ không có push.json (không đoán lượt)")
    ap.add_argument("--nguong-sua", type=float, default=NGUONG_SUA, help=f"ngưỡng điểm 'đã sửa' (%% IOD, {NGUONG_SUA_MIN:g}–{NGUONG_SUA_MAX:g}, mặc định {NGUONG_SUA:g})")
    ap.add_argument("--tat-ca-task", action="store_true", help="gồm cả task practice/check/smoke (mặc định bỏ)")
    ap.add_argument("--moi-bo-anh", action="store_true", help="tính thời gian của mọi bộ ảnh (mặc định chỉ bo_anh trong config\\nhom_thi_nghiem.json nếu có)")
    ap.add_argument("--gom-ttest", action="store_true", help="gồm cả Ttest (tập đo một lần; mặc định ẩn)")
    ap.add_argument("--timing", default=None, help="thư mục hoặc file timing_P*.csv thêm (trong thư mục dự án); mặc định tìm ở m28-prelabel\\, outputs\\, outputs\\timing\\, raw\\, final\\")
    ap.add_argument("--goi", nargs="*", default=None, help="thêm thư mục hoặc file gói kết quả (ketqua_*.zip/.json); mặc định đọc outputs\\ket_qua và outputs\\goi_nhom")
    ap.add_argument("--chi-goi", action="store_true", help="chỉ dùng gói kết quả, không đọc raw\\ và timing")
    ap.add_argument("--out", default=None, help="thư mục gốc xuất (mặc định outputs\\thong_ke)")
    ap.add_argument("--project", default=bang_mat.mac_dinh_du_an(), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        st = tinh(a.project, a.luot_nhap, a.nguong_sua, a.tat_ca_task, a.gom_ttest, a.timing, a.goi or (), not a.moi_bo_anh, a.chi_goi)
        d, files = xuat(a.project, st, a.out, trong_du_an=False)
    except (bang_mat.BangLoi, toc_do.TocDoLoi, ValueError, OSError) as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 2
    print(f"Đã ghi {bang_mat.rel(a.project, d)} ({len(files)} file: thong_ke.html và {len(files) - 1} bảng CSV)")
    for w in st["meta"]["canh_bao"]:
        print("Cảnh báo:", w)
    in_tom_tat(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
