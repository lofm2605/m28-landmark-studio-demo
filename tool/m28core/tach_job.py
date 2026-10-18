"""Tách file nhãn CẢ TASK (CVAT for images 1.1) thành file nhãn theo TỪNG JOB, OFFLINE.

Chỉ thư viện chuẩn (không numpy, cvat_sdk, lxml). Không gọi CVAT: chỉ đọc file đã xuất (`raw/<task>/<task>_<người>_<DDMM>.xml`) và file `.txt` cạnh nó.
Trong file xuất của một task, `<image id>` là SỐ FRAME TRONG TASK, còn job là các khoảng frame liên tiếp `start..stop`
(CVAT 2.77 tạo segment theo job_file_mapping; push.py đã dựa vào điều này ở `_xml_for_frames`). Ranh giới job lấy từ `.txt` cạnh file XML:
dòng job `job <id>: <n> frame, stage <s>, state <t> | frames <a>-<b> | loai <nhan|gan_tay|khong_ro>`. `.txt` cũ (không có `frames`) thì tính cộng dồn
từ `n` theo thứ tự các dòng job; không có `.txt` thì KHÔNG đoán.

Quy tắc:
- Kiểm trước khi ghi bất kỳ file job nào của một file XML (tất cả hoặc không): id ảnh là số nguyên, không trùng; các khoảng job không chồng nhau; MỌI ảnh
  rơi vào đúng một job. Ảnh có id ngoài mọi job, hay phần tử lạ ở gốc XML, là lỗi rõ (`TachJobLoi`), không ghi gì.
- File job: `<raw>/<tên gốc của file cả task>_job<id>.xml` (+ `.txt` cùng tên). Giữ `<version>`, giữ `<meta>` nhưng sửa số ảnh (`meta/task/size`, `meta/job/size`
  nếu có), giữ nguyên id/name ảnh gốc (không đánh lại từ 0), mọi phần tử/thuộc tính trong `<image>`. Nội dung `<meta>` không bao giờ được in ra.
- KHÔNG ghi đè: file job đã có thì giữ nguyên (đánh dấu da_co). File job chỉ để ĐỌC/ĐO (eval50, QC, xem lại), KHÔNG nhập lại vào CVAT.
- Kiểm lệch (cảnh báo, không chặn): job thiếu frame so với `n`; ảnh Sửa nhãn nằm ở job Nhận hay ngược lại (đối chiếu runs/<lượt>/push/manual_list.txt).
- `loai` của job lấy từ `.txt` (nếu đã ghi), không thì từ runs/*/push.json trùng `task` và (nếu biết) `task_id`, tra theo job id; không biết thì `khong_ro`.
"""
import copy
import datetime
import glob
import json
import os
import re
import xml.etree.ElementTree as ET

from . import cvat_io as io_

KINDS = ("nhan", "gan_tay", "khong_ro")
JOB_RE = re.compile(r"^(?P<goc>(?P<task>.+)_(?P<who>[A-Za-z0-9-]+)_(?P<day>\d{4}))_job(?P<job>\d{1,9})\.xml$")
OLD_JOB_LINE = re.compile(r"job (\d+): (\d+) frame, stage (\S+), state ([^|]*[^|\s])")      # state có thể có dấu cách ("in progress" của CVAT): lấy tới trước " |"
GHI_CHU = ("tách offline từ file cả task, không gọi CVAT; id/name ảnh giữ như file cả task; <meta> giữ nguyên trừ số ảnh; "
           "chỉ để đọc/đo, KHÔNG dùng để nhập lại vào CVAT")


class TachJobLoi(Exception):
    """Lỗi người dùng sửa được khi tách job (thiếu .txt, id ngoài mọi job...). Thông báo tiếng Việt, không chứa nội dung <meta>."""


# ---------- .txt ----------
def job_line(j):
    """Dòng job trong .txt: phần đầu giữ NGUYÊN định dạng cũ, trường mới cách bằng ` | ` (bản cũ đọc state sạch)."""
    s = f"job {j['id']}: {j['n']} frame, stage {j['stage']}, state {j['state']}"
    if j.get("start") is not None and j.get("stop") is not None:
        s += f" | frames {j['start']}-{j['stop']}"
    kind = j.get("kind") if j.get("kind") in KINDS else "khong_ro"
    return s + f" | loai {kind}"


def parse_job_line(line):
    """dict(id, n, stage, state, start, stop, kind) từ một dòng job (cũ hoặc mới), None nếu không phải dòng job. start/stop là None khi dòng cũ."""
    ln = line.strip()
    m = OLD_JOB_LINE.match(ln)
    if not m:
        return None
    j = dict(id=int(m.group(1)), n=int(m.group(2)), stage=m.group(3), state=m.group(4), start=None, stop=None, kind="khong_ro")
    for part in ln[m.end():].split("|"):
        part = part.strip()
        mf = re.fullmatch(r"frames (\d+)-(\d+)", part)
        if mf:
            j["start"], j["stop"] = int(mf.group(1)), int(mf.group(2))
            continue
        ml = re.fullmatch(r"loai (\S+)", part)
        if ml and ml.group(1) in KINDS:
            j["kind"] = ml.group(1)
    return j


def read_txt(txt_path):
    """dict(task, task_id, jobs) từ .txt cạnh file xuất, hoặc None nếu không mở được. Mỗi job có thêm `suy_ra` (True khi `frames` không có trong
    dòng và start/stop được tính cộng dồn từ n theo thứ tự các dòng job, như .txt cũ)."""
    try:
        with open(txt_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    task, task_id, jobs = None, None, []
    for ln in lines:
        s = ln.strip()
        m = re.match(r"(task|task_id): (.*)$", s)
        if m:
            if m.group(1) == "task":
                task = m.group(2).strip() or None
            else:
                task_id = int(m.group(2)) if m.group(2).strip().isdigit() else None
            continue
        j = parse_job_line(s)
        if j:
            jobs.append(j)
    nxt = 0
    for j in jobs:
        if j["start"] is None:
            j["start"], j["stop"], j["suy_ra"] = nxt, nxt + j["n"] - 1, True
        else:
            j["suy_ra"] = False
        nxt = j["stop"] + 1
    return dict(task=task, task_id=task_id, jobs=jobs)


# ---------- push.json ----------
def push_jobs(task, runs_dir="runs", task_id=None):
    """Thông tin job của task demo-… từ runs/*/push.json (bản nào cũng có khoá `jobs` với `kind`): dict(run, run_dir, task_id, kinds={job_id: kind},
    manual=[tên ảnh Sửa nhãn] hoặc None nếu không có manual_list.txt) hoặc None. Chỉ nhận push.json có `task` trùng tên và, nếu biết task_id, `task_id` trùng
    (task xoá rồi tạo lại cùng tên có id khác); bỏ qua lượt đã xoá task. Nhiều lượt khớp thì lấy `cap_nhat` mới nhất. Chỉ đọc."""
    best = None
    for p in glob.glob(os.path.join(runs_dir, "*", "push.json")):
        try:
            with open(p, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(st, dict) or st.get("task") != task or st.get("trang_thai") == "task_deleted":
            continue
        if task_id is not None and st.get("task_id") != task_id:
            continue
        kinds = {}
        for j in st.get("jobs") if isinstance(st.get("jobs"), list) else []:
            if isinstance(j, dict) and isinstance(j.get("id"), int) and j.get("kind") in ("nhan", "gan_tay"):
                kinds[j["id"]] = j["kind"]
        if not kinds:
            continue
        key = str(st.get("cap_nhat") or "")
        if best is None or key > best[0]:
            best = (key, p, st, kinds)
    if best is None:
        return None
    _key, p, st, kinds = best
    run_dir = os.path.dirname(p)
    return dict(run=os.path.basename(run_dir), run_dir=run_dir, task_id=st.get("task_id"), kinds=kinds, manual=_read_manual_names(run_dir))


def _read_manual_names(run_dir):
    """Tên ảnh Sửa nhãn từ runs/<lượt>/push/manual_list.txt (`tên\\tloại` hoặc một-tên-mỗi-dòng của bản cũ), None nếu không đọc được."""
    path = os.path.join(run_dir, "push", "manual_list.txt")
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.partition("\t")[0].strip() for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        return None


# ---------- đọc và kiểm XML ----------
def _read_root(xml_path):
    try:
        size = os.path.getsize(xml_path)
    except OSError:
        raise TachJobLoi(f"Không mở được {xml_path}.")
    if size > io_.MAX_XML:
        raise TachJobLoi(f"{xml_path} quá lớn (hơn 200 MB): không đọc.")
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError) as e:
        raise TachJobLoi(f"{xml_path} không phải XML hợp lệ ({type(e).__name__}).")
    if root.tag != "annotations":
        raise TachJobLoi(f"{xml_path}: phần tử gốc là <{root.tag}>, cần <annotations> (xuất 'CVAT for images 1.1').")
    return root


def _fmt_ranges(jobs, limit=8):
    s = ", ".join(f"job {j['id']}: {j['start']}-{j['stop']}" for j in jobs[:limit])
    return s + (f", … (+{len(jobs) - limit})" if len(jobs) > limit else "")


def _check_jobs(jobs):
    """Khoảng job hợp lệ: start <= stop, n khớp, không chồng nhau, id job không trùng."""
    if not jobs:
        raise TachJobLoi("Không có dòng job nào trong .txt: không biết ranh giới job.")
    seen = set()
    for j in jobs:
        if j["id"] in seen:
            raise TachJobLoi(f"Job {j['id']} xuất hiện hai lần trong .txt.")
        seen.add(j["id"])
        if j["start"] < 0 or j["stop"] < j["start"] or j["stop"] - j["start"] + 1 != j["n"]:
            raise TachJobLoi(f"Dòng job {j['id']} trong .txt mâu thuẫn: {j['n']} frame nhưng frames {j['start']}-{j['stop']}.")
    srt = sorted(jobs, key=lambda j: j["start"])
    for a, b in zip(srt, srt[1:]):
        if b["start"] <= a["stop"]:
            raise TachJobLoi(f"Hai job chồng nhau trong .txt: job {a['id']} (frames {a['start']}-{a['stop']}) và job {b['id']} (frames {b['start']}-{b['stop']}).")
    return srt


def _split_images(root, jobs):
    """{job_id: [phần tử <image> theo thứ tự trong file]} sau khi kiểm: id nguyên, không trùng, mọi ảnh thuộc đúng một job; lỗi thì TachJobLoi."""
    by_job = {j["id"]: [] for j in jobs}
    srt = sorted(jobs, key=lambda j: j["start"])
    ids = {}
    for ch in root:
        if ch.tag in ("version", "meta"):
            continue
        if ch.tag != "image":
            raise TachJobLoi(f"Phần tử lạ <{ch.tag}> ở gốc file XML (chỉ có version, meta, image): không đoán, không tách.")
        name, raw = ch.get("name") or "?", ch.get("id")
        if raw is None or not re.fullmatch(r"\d{1,9}", raw.strip()):
            raise TachJobLoi(f"Ảnh {name!r} có id {raw!r} không phải số nguyên: không tách được.")
        fid = int(raw)
        if fid in ids:
            raise TachJobLoi(f"Hai ảnh trùng id {fid} ({ids[fid]!r} và {name!r}): không tách được.")
        ids[fid] = name
        owner = next((j for j in srt if j["start"] <= fid <= j["stop"]), None)
        if owner is None:
            raise TachJobLoi(f"Ảnh {name!r} có id {fid} nằm ngoài mọi job (các khoảng: {_fmt_ranges(srt)}). Kiểm .txt có đúng của file này không, "
                             "hoặc file XML có phải xuất từ đúng task đó không; chưa ghi file job nào.")
        by_job[owner["id"]].append(ch)
    return by_job


# ---------- ghi file job ----------
def job_path(xml_path, out_dir, job_id):
    """Đường dẫn file job: <out_dir>/<tên gốc của file cả task>_job<id>.xml. Tên gốc phải qua safe_file_part; đường ghi nằm trong out_dir."""
    base = os.path.basename(xml_path)
    if not base.lower().endswith(".xml"):
        raise TachJobLoi(f"{xml_path} không có đuôi .xml.")
    stem = base[:-4]
    try:
        io_.safe_file_part(stem)
    except SystemExit as e:
        raise TachJobLoi(str(e))
    path = os.path.join(out_dir, f"{stem}_job{int(job_id)}.xml")
    if not io_.inside(path, out_dir):
        raise TachJobLoi(f"Đường dẫn {path} nằm ngoài {out_dir}: từ chối.")
    return path


def _job_xml_bytes(root, imgs, n_img):
    """XML của một job: version, meta (sửa số ảnh), các <image> của job theo thứ tự gốc."""
    keep = {id(x) for x in imgs}
    new = ET.Element(root.tag, dict(root.attrib))
    new.text = root.text
    tails = [c.tail for c in root]
    kept = []
    for ch in root:
        if ch.tag in ("version", "meta") or id(ch) in keep:
            c = copy.deepcopy(ch)                                # bản sao sâu: mọi phần tử và thuộc tính con giữ nguyên
            if ch.tag == "meta":
                for path in ("task/size", "job/size"):
                    el = c.find(path)
                    if el is not None:
                        el.text = str(n_img)
            new.append(c)
            kept.append(c)
    if kept and tails:
        kept[-1].tail = tails[-1]
    return ET.tostring(new, encoding="utf-8", xml_declaration=True)


def _vn_now(now=None):
    return (now or datetime.datetime.now(io_.VN_TZ)).strftime("%Y-%m-%d %H:%M") + " (giờ Việt Nam, UTC+7)"


def _txt_text(src, meta, j, n_img, thieu, warns, now):
    lines = [f"nguon: {src}", f"task: {meta['task']}" if meta.get("task") else "task: ?", f"task_id: {meta['task_id']}" if meta.get("task_id") is not None else "task_id: ?",
             f"job_id: {j['id']}", f"loai: {j['kind']}", f"frames: {j['start']}-{j['stop']}", f"so_frame_job: {j['n']}", f"so_anh_trong_file: {n_img}"]
    if thieu:
        lines.append("frame_thieu: " + ", ".join(str(x) for x in thieu[:20]) + (f" … (+{len(thieu) - 20})" if len(thieu) > 20 else ""))
    lines += [f"stage: {j['stage']}", f"state: {j['state']}", f"tach_luc: {_vn_now(now)}", f"ghi_chu: {GHI_CHU}"]
    if j.get("suy_ra"):
        lines.append("ghi_chu_frame: frame suy ra từ số frame cộng dồn (.txt cũ không có trường frames)")
    lines += [f"canh_bao: {w}" for w in warns]
    lines.append(job_line(dict(j, n=j["n"])))                       # một dòng job đúng định dạng: _jobs_from_txt cũ lẫn mới đều đọc được
    return "\n".join(lines) + "\n"


def _write_new(path, data):
    """Ghi file qua file tạm rồi os.replace; kiểm tồn tại NGAY TRƯỚC khi thay (không ghi đè). Trả True nếu đã ghi, False nếu file đã có."""
    if os.path.exists(path):
        return False
    tmp = path + f".tmp{os.getpid()}"
    with open(tmp, "wb") as f:
        f.write(data)
    if os.path.exists(path):
        os.remove(tmp)
        return False
    os.replace(tmp, path)
    return True


# ---------- kiểm lệch ----------
def _mismatch(j, names, manual):
    """Cảnh báo ảnh lệch job: job gan_tay phải đúng các ảnh Sửa nhãn; job nhan không được có ảnh Sửa nhãn. Không biết loại/manual_list thì [] (ghi riêng)."""
    if manual is None or j["kind"] not in ("nhan", "gan_tay"):
        return []
    man = set(manual)
    if j["kind"] == "nhan":
        bad = sorted(n for n in names if n in man)
        why = "ảnh Sửa nhãn nằm trong job Nhận"
    else:
        bad = sorted(n for n in names if n not in man)
        why = "ảnh không phải Sửa nhãn nằm trong job gan_tay"
    if not bad:
        return []
    return [f"ảnh lệch job: {len(bad)} {why} (ví dụ {', '.join(bad[:3])})"]


def tach(xml_path, out_dir=None, txt_path=None, only=None, runs_dir="runs", dry_run=False, now=None):
    """Tách `xml_path` thành file theo job trong `out_dir` (mặc định thư mục chứa xml_path). Trả dict(nguon, task, task_id, jobs, kiem_lech):
    jobs = [dict(id, kind, start, stop, n, n_anh, thieu, stage, state, suy_ra, path, txt_path, da_co, canh_bao)] cho các job được chọn (`only` = tập job id,
    None = tất cả). `da_co` True nghĩa là file job đã có từ trước, KHÔNG ghi đè. dry_run: không ghi gì, `da_co` cho biết file có sẵn không.
    Lỗi người dùng sửa được thì TachJobLoi; khi lỗi, KHÔNG có file job nào được ghi."""
    out_dir = out_dir or os.path.dirname(xml_path) or "."
    txt_path = txt_path or (os.path.splitext(xml_path)[0] + ".txt")
    meta = read_txt(txt_path)
    if meta is None:
        raise TachJobLoi(f"Không biết ranh giới job: thiếu {txt_path} (file .txt do collect ghi cạnh file XML, có các dòng 'job <id>: <n> frame ...'). "
                         "Không đoán ranh giới; xuất lại bằng collect hoặc chép .txt đúng của file này về cạnh nó.")
    jobs = _check_jobs(meta["jobs"])
    push = push_jobs(meta["task"], runs_dir, meta["task_id"]) if meta.get("task") else None
    for j in jobs:
        if j["kind"] == "khong_ro" and push:
            j["kind"] = push["kinds"].get(j["id"], "khong_ro")
    ids = [j["id"] for j in jobs]
    if only:
        miss = sorted(set(only) - set(ids))
        if miss:
            raise TachJobLoi(f"Job {', '.join(str(x) for x in miss)} không có trong {os.path.basename(xml_path)}; job hợp lệ: {', '.join(str(i) for i in ids)}.")
    root = _read_root(xml_path)
    by_job = _split_images(root, jobs)
    manual = push["manual"] if push else None
    kiem = ("đã kiểm ảnh Sửa nhãn theo " + os.path.join("runs", push["run"], "push", "manual_list.txt")) if push and manual is not None else \
           "không kiểm được ảnh lệch job (không có push.json khớp hoặc manual_list.txt)"
    src = os.path.basename(xml_path)
    out = []
    pending = []
    for j in sorted(jobs, key=lambda x: x["start"]):
        if only and j["id"] not in set(only):
            continue
        imgs = by_job[j["id"]]
        n_img = len(imgs)
        have = {int(x.get("id")) for x in imgs}
        thieu = sorted(set(range(j["start"], j["stop"] + 1)) - have)
        names = [x.get("name") or "" for x in imgs]
        warns = []
        if thieu:
            warns.append(f"{n_img}/{j['n']} ảnh, thiếu frame {', '.join(str(x) for x in thieu[:10])}" + (" …" if len(thieu) > 10 else ""))
        warns += _mismatch(j, names, manual)
        path = job_path(xml_path, out_dir, j["id"])
        r = dict(id=j["id"], kind=j["kind"], start=j["start"], stop=j["stop"], n=j["n"], n_anh=n_img, thieu=thieu, stage=j["stage"], state=j["state"],
                 suy_ra=j["suy_ra"], path=path, txt_path=path[:-4] + ".txt", da_co=os.path.exists(path), canh_bao=warns, ten_anh=names)
        out.append(r)
        pending.append((r, _job_xml_bytes(root, imgs, n_img), _txt_text(src, meta, j, n_img, thieu, warns, now)))
    if not dry_run and pending:
        os.makedirs(out_dir, exist_ok=True)
        for r, data, txt in pending:                                  # mọi byte đã dựng xong trước khi ghi file đầu tiên
            wrote = _write_new(r["path"], data)
            r["da_co"] = not wrote
            if wrote:
                _write_new(r["txt_path"], txt.encode("utf-8"))
    return dict(nguon=src, task=meta.get("task"), task_id=meta.get("task_id"), jobs=out, kiem_lech=kiem)
