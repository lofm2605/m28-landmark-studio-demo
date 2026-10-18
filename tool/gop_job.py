"""Nút "Merge jobs & Finish" trên thẻ đợt (tab Các đợt) của trang rà soát M28: logic thuần (không gradio, không mạng; phần Gradio ở dot_ui.py).

Một bấm làm trọn việc cuối của đợt: gộp MỌI job của task CVAT của đợt thành MỘT file raw/<task>/<task>_<Pk>_<DDMM>.xml, rồi DỪNG và LƯU đồng hồ của đợt
(dòng outputs/timing/timing_<Pk>.csv + gói outputs/ket_qua/ketqua_<Pk>_<DDMM>_<đợt>.zip gửi nhóm trưởng). Bản xuất cả task của CVAT đã chứa mọi job, nên file
collect ghi ra CHÍNH LÀ file gộp.

Luồng:
  1. Bấm nút -> finish_model (đã đẩy xong? link/token? đúng server đã đẩy? tên người rà hợp lệ? không việc nào đang chạy?) -> hộp xác nhận (confirm_html).
  2. OK -> begin: đồng hồ của đợt đang chạy thì TẠM DỪNG ngay (thời gian xuất và quyết định không tính), ghi ctx.gop, chạy nap_anh.CollectJob
     (`m28.py collect --task T --reviewer Pk --overwrite --no-per-job --require-completed`; tiến trình con là nơi DUY NHẤT gọi CVAT, token đi qua môi trường
     của nó, không qua đối số).
  3. Job dừng -> poll (ĐÚNG MỘT LẦN dù nhiều tab cùng hỏi: ctx.gop_lock + ctx.gop["phase"]) -> finalize:
       * có file gộp: đếm ảnh có nhãn (eval50.read_labels), xong_luu (cảnh báo của đồng hồ đã chấp nhận ở hộp xác nhận nên lưu luôn), ghi
         runs/<đợt>/gop_job.json; không còn phiên mà đợt có gói đã lưu thì gắn nhãn vào gói đó (xuat_lai_goi); file gộp không có nhãn nào (chưa Save
         trong CVAT) thì không lưu gì, đồng hồ chạy lại như lúc bấm;
       * còn job chưa completed (mã thoát 3): hỏi lần hai (pending_html): Merge anyway (force) hoặc Cancel = quay lại CVAT (đồng hồ chạy lại);
       * lỗi khác / huỷ (nút Cancel ở khung gộp job của tab Các đợt gọi collect_job.cancel()): đồng hồ chạy lại nếu lúc bấm đang chạy, báo dòng lỗi cuối
         (đã lọc token).
  ctx.gop chỉ sống trong bộ nhớ của trang (chuyển đợt dựng ctx mới là mất): còn ctx.gop thì trang từ chối chuyển đợt, Upload & Open và xoá đợt/task/ảnh
  của đợt đó (block_reason, guard_text); poll không bao giờ để ctx.gop kẹt (lỗi lúc cho đồng hồ chạy lại chỉ được báo).
ctx (AppCtx của review_app hoặc đồ giả trong test) cần: collect_job, gop, gop_lock, runs_root, project_root.
Không ảnh mặt, không token, không đường dẫn tuyệt đối trong thông báo.
"""
import html
import json
import os
import re
import sys

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import day_cvat  # noqa: E402
import dong_ho  # noqa: E402
import dong_ho_ui  # noqa: E402  (summary_html, vi_hop; không import gradio ở đầu module)
import dot_anh  # noqa: E402
import nap_anh  # noqa: E402
from dong_ho import DongHoLoi, fmt_giay  # noqa: E402
from m28core import cvat_io  # noqa: E402
from nap_anh import RunError  # noqa: E402

GOP_FILE = dot_anh.GOP_FILE
PHASE_CHAY, PHASE_XU_LY, PHASE_HOI = "chay", "xu_ly", "hoi"     # job đang chạy | một tab đang xử lý kết quả | chờ người dùng chọn Merge anyway / Cancel
NHAC_SAVE = "Nhớ bấm Save trong từng job CVAT (nhãn chưa Save không được xuất)."


def _e(x):
    return html.escape("" if x is None else str(x), quote=True)


def _raw_win(name, task=""):
    """raw\\<task>\\<tên> (mỗi task một thư mục con của raw\\); không có task thì raw\\<tên>."""
    return "raw\\" + (task + "\\" if task else "") + name


# ---------- mô hình nút ----------
def goi_cua_dot(dh, person, run):
    """Tên gói đã lưu (mới nhất) của `person` cho đợt `run` trong outputs/ket_qua, hoặc None."""
    try:
        for ten, nd in dh.goi_da_luu(person):
            if str(nd.get("dot") or "") == run:
                return ten
    except Exception:                                                   # thư mục gói hỏng: coi như không có
        return None
    return None


def finish_model(run_dir, project_root, person, dh, *, environ=None, job_running=False):
    """Mô hình nút Merge jobs & Finish cho một đợt: dict(enabled, reason, run, task, task_id, person, url, env, push, gop, co_phien, trang_thai, giay_phien, rev,
    cho, hong, canh_bao_chua_xu_ly [chữ], goi_da_luu tên|None, tam_thoi). enabled chỉ khi mọi điều kiện an toàn đã thoả (tiến trình con còn kiểm lại với CVAT thật).
    tam_thoi=True: chỉ bị chặn vì việc khác đang chạy (chờ là hết); mọi lý do khác (đẩy/task đã xoá, link, người rà...) là thay đổi lâu dài.
    person: người rà của trang (dong_ho_ui.default_person); environ: test truyền dict môi trường, None thì lấy từ tab Cài đặt."""
    run = os.path.basename(os.path.normpath(run_dir))
    ps = dot_anh.read_push(run_dir)
    st = (ps or {}).get("trang_thai")
    task = (ps or {}).get("task") if isinstance((ps or {}).get("task"), str) else ""
    env = day_cvat.env_state(environ)
    m = dict(enabled=False, reason="", run=run, task=task, task_id=(ps or {}).get("task_id"), person=person, url=cvat_io.norm_url((ps or {}).get("cvat_url")),
             env=env, push=ps, gop=dot_anh.read_gop(run_dir), co_phien=False, trang_thai="", giay_phien=0.0, rev=0, cho=False, hong=False,
             canh_bao_chua_xu_ly=[], goi_da_luu=None, tam_thoi=False)
    if dong_ho.nguoi_hop_le(person) and dh is not None:
        v = dh.xem(person, run)
        m["hong"] = bool(v.get("hong"))
        if v.get("co_phien"):
            m.update(co_phien=True, trang_thai=v["trang_thai"], giay_phien=float(v["giay_phien"]), rev=v["rev"], cho=bool(v.get("cho")),
                     canh_bao_chua_xu_ly=[c["text"] for c in v.get("canh_bao", []) if not c.get("xu_ly")])
        else:
            m["goi_da_luu"] = goi_cua_dot(dh, person, run)
    busy = dot_anh.run_busy(run_dir)
    if ps is None:
        m["reason"] = "Đợt này chưa đẩy lên CVAT (chưa có push.json): bấm Push to CVAT, sửa nhãn trong CVAT rồi mới gộp job."
    elif st == "task_deleted":
        m["reason"] = "Task trên CVAT của đợt này đã xoá: không còn job nào để gộp (đẩy lại nếu cần)."
    elif st != "xong":
        m["reason"] = f"Lần đẩy lên CVAT của đợt này chưa xong (push.json: {st}): làm nốt hoặc xoá task dở trước (xem khung CVAT của đợt)."
    elif not nap_anh.task_ok(task):
        m["reason"] = f"Tên task trong push.json ({task!r}) không phải tên task của tool (hoặc là task chung m28-…): từ chối."
    elif not env["ok"]:
        m["reason"] = env["reason"] + " Bấm nút CVAT ở đầu trang để nhập link và token (hoặc đặt biến môi trường CVAT_URL, CVAT_ACCESS_TOKEN rồi mở lại trang)."
    elif env["url"] != m["url"]:
        m["reason"] = (f"Task này nằm ở {m['url'] or '(push.json không ghi địa chỉ CVAT)'} nhưng CVAT_URL đang là {env['url']}: "
                       "chỉ gộp được trên đúng server đã đẩy.")
    elif not dong_ho.nguoi_hop_le(person):
        m["reason"] = (f"Người rà của trang là {person or '(chưa đặt)'}: tên chỉ chữ không dấu, số và dấu -, bắt đầu bằng chữ hoặc số, tối đa 32 ký tự (đặt tên bằng nút Reviewer ở đầu trang).")
    elif job_running or busy:
        m["reason"] = "Đang có việc chạy" + (f" cho đợt này ({busy[0]})" if busy else " (chuẩn bị, đẩy, xoá task hoặc gộp job)") + ": chờ xong rồi gộp job."
        m["tam_thoi"] = True                                            # lý do tạm thời: chờ là hết (Merge anyway giữ yêu cầu đang chờ, không bỏ)
    else:
        m["enabled"] = True
    return m


# ---------- HTML ----------
def _clock_text(m):
    if not m["co_phien"]:
        return "không có phiên đang mở" + (" (file trạng thái đồng hồ hỏng)" if m.get("hong") else "")
    if m["cho"]:
        return "⏸ chờ bắt đầu (chưa tính giờ)"
    if m["trang_thai"] == "chay":
        return f"▶ <b>{fmt_giay(m['giay_phien'])}</b>, đang chạy: tạm dừng ngay khi bấm Merge jobs &amp; Finish"
    if m["trang_thai"] == "du_mat":
        return f"■ <b>{fmt_giay(m['giay_phien'])}</b>, đủ mặt, chờ lưu"
    return f"⏸ <b>{fmt_giay(m['giay_phien'])}</b>, đang tạm dừng"


def confirm_html(m):
    """Nội dung hộp xác nhận (hộp thứ nhất) của Merge jobs & Finish."""
    run, task, p = m["run"], m["task"], m["person"]
    file_ = _raw_win(f"{task}_{p}_<DDMM>.xml", task)
    rows = [("Đợt", f"<b>{_e(run)}</b>"), ("Task CVAT", f"<b>{_e(task)}</b>" + (f" (id {_e(m['task_id'])})" if m.get("task_id") else "")),
            ("Địa chỉ CVAT", f"<code>{_e(m['url'])}</code>"), ("Người", f"<b>{_e(p)}</b>")]
    if m["co_phien"]:
        rows.append(("Đồng hồ của đợt", _clock_text(m)))
    table = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    gom = (f"Tool sẽ xuất cả task từ CVAT thành MỘT file <code>{_e(file_)}</code> (gộp mọi job; bản cũ cùng ngày chuyển vào <code>raw\\_cu\\</code>)")
    if m["co_phien"]:
        what = f'<div class="nap-note">{gom}, rồi <b>DỪNG</b> đồng hồ của đợt và lưu dòng bấm giờ + gói kết quả gửi nhóm trưởng.</div>'
        if m["cho"]:
            what += ('<div class="m28-warn">Đồng hồ của đợt này còn đang chờ bắt đầu (chưa tính giây nào) nên sẽ không lưu được dòng bấm giờ; '
                     'file gộp vẫn được xuất.</div>')
    else:
        extra = (f'; gói kết quả đã lưu <b>{_e(m["goi_da_luu"])}</b> của đợt này sẽ được gắn nhãn từ file gộp (gửi lại gói đó cho nhóm trưởng).'
                 if m.get("goi_da_luu") else ".")
        what = f'<div class="nap-note">{gom}{extra}</div>'
    warn = ""
    if m["co_phien"] and m["canh_bao_chua_xu_ly"]:
        items = "".join(f"<li>{_e(t)}</li>" for t in m["canh_bao_chua_xu_ly"])
        warn = (f'<div class="nap-box nap-warn" role="alert"><b>Cảnh báo của đồng hồ</b> (bấm Merge jobs &amp; Finish là đồng ý lưu kèm cảnh báo):'
                f'<ul>{items}</ul></div>')
    old = ""
    g = m.get("gop")
    if isinstance(g, dict) and g.get("xml"):
        old = (f'<div class="nap-note">Đợt này đã gộp lúc {_e(dot_anh.fmt_date(str(g.get("luc", ""))))} ({_e(str(g["xml"]).replace(chr(92), "/"))}): '
               'gộp lại sẽ xuất nhãn mới nhất trên CVAT.</div>')
    return ('<div class="modal-title modal-finish" id="dot-modal-title">Gộp job và kết thúc đợt ' + _e(run) + '?</div>'
            f'<table class="m28-info">{table}</table>{what}{warn}{old}<div class="m28-warn"><b>{_e(NHAC_SAVE)}</b></div>')


def _job_rows(jobs):
    rows = "".join(f'<tr><td>job {_e(j.get("id"))}</td><td>frame {_e(j.get("start", "?"))}–{_e(j.get("stop", "?"))}</td>'
                   f'<td>{_e(j.get("stage", ""))}/{_e(j.get("state", ""))}</td></tr>' for j in jobs)
    return f'<table class="m28-info"><tr><th>Job</th><th>Frame</th><th>Stage/state</th></tr>{rows}</table>'


def pending_html(g, pending):
    """Hộp thứ hai: còn job chưa bấm Finish the job trong CVAT. g = ctx.gop (run, person, task, was_running)."""
    n = len(pending)
    back = ", đồng hồ chạy lại như lúc bấm" if g.get("was_running") else ""
    return (f'<div class="modal-title modal-danger" id="dot-modal-title">Còn {n} job chưa xong trên CVAT (đợt {_e(g["run"])})</div>'
            f'<div class="nap-box nap-warn" role="alert"><b>Còn {n} job chưa bấm Finish the job trong CVAT. Gộp luôn (nhãn hiện có trên server) '
            'hay quay lại CVAT sửa tiếp?</b></div>'
            f'{_job_rows(pending)}'
            f'<div class="nap-note"><b>Merge anyway</b>: gộp ngay nhãn đang có trên server vào MỘT file (job chưa xong vẫn được xuất; nhãn chưa Save thì không có), '
            + ('dừng và lưu đồng hồ; ' if g.get("was_running") else "") + 'danh sách job chưa xong ghi vào gop_job.json. '
            f'<b>Cancel</b>: quay lại CVAT sửa tiếp{back}; xong thì bấm Merge jobs &amp; Finish lại.</div>'
            f'<div class="m28-warn">{_e(NHAC_SAVE)}</div>')


def progress(lines):
    """(nhãn, tỉ lệ) cho thanh tiến độ khi job gộp đang chạy (collect không in dòng '[k/6]' như push)."""
    lab, fr = "Đang khởi động…", 0.05
    for ln in lines or []:
        s = ln.strip()
        if s.startswith("CVAT:"):
            lab, fr = "Đang kết nối CVAT…", 0.2
        elif re.search(r": id \d+, \d+ ảnh, \d+ job", s):
            lab, fr = "Đang kiểm trạng thái các job, rồi xuất nhãn cả task (gộp mọi job)…", 0.45
        elif s.startswith(nap_anh.DONG_CHUA_XONG):
            lab, fr = "Còn job chưa xong trên CVAT", 0.9
        elif s.startswith(nap_anh.DONG_XML) or s.startswith("đã ghi") or "đã ghi " in s:
            lab, fr = "Đã ghi file gộp", 0.95
    return lab, fr


def _box(text_html, level="ok"):
    return f'<div class="nap-box nap-{level} gop-done" role="status">{text_html}</div>'


def result_html(fx):
    """Kết quả hiện ở #dot-msg sau khi gộp xong (fx = kết quả finalize với kind 'xong')."""
    run, p, n = fx["run"], fx["person"], fx["n"]
    parts = [f'<b>Đã gộp job của đợt {_e(run)}.</b> File gộp: <code>{_e(fx.get("xml_win") or _raw_win(fx["xml_name"]))}</code> ({n} ảnh có nhãn, {len(fx["jobs"])} job).']
    if fx["chua"]:
        parts.append(f'Gộp khi còn {len(fx["chua"])} job chưa Finish the job trên CVAT (job {", ".join(str(i) for i in fx["chua"])}): đã ghi vào '
                     f'runs\\{_e(run)}\\gop_job.json.')
    body = "<br>".join(parts)
    if fx.get("luu"):
        body += dong_ho_ui.summary_html(fx["luu"], p)
    elif fx.get("xuat_lai"):
        body += (f'<div class="nap-note">Không còn phiên đồng hồ đang mở (đã lưu trước đó): gói <b>{_e(fx["xuat_lai"]["ten"])}</b> đã gắn nhãn từ file gộp. '
                 f'<b>Gói kết quả gửi nhóm trưởng:</b> <code>{_e(fx["xuat_lai"]["zip"])}</code></div>')
    if fx.get("loi_luu"):
        body += f'<div class="m28-warn">{_e(fx["loi_luu"])}</div>'
    if fx.get("loi_ghi"):
        body += f'<div class="m28-warn">{_e(fx["loi_ghi"])}</div>'
    co_goi = bool(fx.get("luu") or fx.get("xuat_lai"))                    # chỉ xuất file gộp (không có phiên đồng hồ, không gói): không mời mở thư mục gói
    body += ('<div class="gop-folders">'
             + ('<button type="button" class="dot-btn dot-btn-push" data-act="openfolder" data-folder="ket_qua" title="outputs/ket_qua: gói kết quả gửi nhóm trưởng">'
                'Mở thư mục gói kết quả</button> ' if co_goi else "")
             + f'<button type="button" class="dot-btn" data-act="openfolder" data-folder="raw" data-run="{_e(fx.get("run", ""))}" '
             f'title="Thư mục chứa file nhãn gộp của task">Mở thư mục nhãn</button> '
             + ('<button type="button" class="dot-btn" data-act="openfolder" data-folder="timing" title="outputs/timing: dòng bấm giờ">Mở timing</button>' if fx.get("luu") else "")
             + '</div>')
    return _box(body, "warn" if (fx.get("loi_luu") or fx.get("loi_ghi")) else "ok")


# ---------- gop_job.json ----------
def write_gop(run_dir, data):
    """Ghi runs/<lượt>/gop_job.json nguyên tử (chỉ trong thư mục lượt)."""
    p = os.path.join(run_dir, GOP_FILE)
    if not nap_anh._inside(p, run_dir):
        raise OSError("gop_job.json nằm ngoài thư mục lượt")
    cvat_io.atomic_write_json(p, data)
    return p


# ---------- đồng hồ ----------
def _resume(d, person, run, was_running):
    """Đồng hồ chạy lại nếu lúc bấm nó đang chạy (đã tạm dừng ở begin). Trả câu nói việc đã làm ('' nếu không cần). Không bao giờ ném lỗi: file trạng thái
    bị khoá (antivirus, OneDrive...) hay lỗi lạ chỉ được báo, để người gọi luôn bỏ được ctx.gop."""
    if not was_running:
        return ""
    try:
        v = d.xem(person, run)
        if not v.get("co_phien"):
            return f"Đồng hồ của {person} cho đợt {run} không còn phiên đang mở (đã Save timing hoặc đã bỏ ở tab khác)."
        if v.get("trang_thai") == "chay":                                # đã bấm Resume ở chip trong lúc chờ: để nguyên
            return ""
        d.tiep_tuc(person, None, dot=run)
        return f"Đồng hồ của {person} (đợt {run}) chạy tiếp."
    except DongHoLoi as e:
        return f"Đồng hồ của {person} chưa chạy lại được ({dong_ho_ui.vi_hop(str(e))}): bấm Resume ở đầu trang."
    except Exception as e:                                              # noqa: BLE001 - OSError (file đang bị khoá) hay lỗi lạ: báo, không để ctx.gop kẹt
        return f"Đồng hồ của {person} chưa chạy lại được ({type(e).__name__}): bấm Resume ở đầu trang."


def _save(d, person, run, n, nhan):
    """xong_luu với file gộp. Cảnh báo của đồng hồ (cho=True) đã được chấp nhận ở hộp xác nhận: gọi thêm một lần ngay. Trả kết quả xong_luu."""
    so_mat = n if n >= 1 else None
    try:
        return d.xong_luu(person, None, True, so_mat, nhan, dot=run)
    except DongHoLoi as e:
        if not e.cho:
            raise
        return d.xong_luu(person, None, True, so_mat, nhan, dot=run)


def _fail(d, g, text, kind="loi", resume=True):
    """Kết quả lỗi/huỷ; đồng hồ chạy lại như lúc bấm (resume=False: không đụng đồng hồ, vì có thể đã lưu một phần)."""
    note = _resume(d, g["person"], g["run"], g.get("was_running")) if resume else ""
    level = "err" if kind == "loi" else "warn"
    return dict(kind=kind, run=g["run"], person=g["person"], text=(text + (" " + note if note else "")).strip(),
                html=_box(_e((text + (" " + note if note else "")).strip()), level))


def count_labelled(xml_path, project_root):
    """Số ảnh có ít nhất một điểm trong file gộp (eval50.read_labels với config/m28_config.json). Lỗi đọc thì ném lên (finalize báo lỗi)."""
    import eval50                                                       # nạp lười: eval50 kéo numpy
    with open(os.path.join(project_root, "config", "m28_config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    labels = eval50.read_labels(xml_path, cfg, warn=lambda *_a: None)
    return sum(1 for pts in labels.values() if pts)


def finalize(d, project_root, run_dir, g, snap):
    """Xử lý job gộp ĐÃ DỪNG (gọi qua poll: đúng một lần). g = ctx.gop; snap = collect_job.snapshot().
    Trả dict(kind, run, person, ...): 'xong' (có file gộp; html, n, xml_name, jobs, chua, luu, xuat_lai, gop), 'hoi' (còn job chưa completed: pending, jobs),
    'loi' / 'huy' (đồng hồ đã chạy lại nếu lúc bấm đang chạy; html, text)."""
    run, person, task = g["run"], g["person"], g["task"]
    st = snap.get("state")
    lines = snap.get("lines") or []
    if snap.get("run") != run:
        return _fail(d, g, f"Không thấy kết quả gộp của đợt {run} (job gộp đã sang việc khác): bấm Merge jobs & Finish lại.")
    if st == "da_huy":
        return _fail(d, g, f"Đã huỷ gộp job của đợt {run}: chưa lưu đồng hồ, chưa ghi gói kết quả hay gop_job.json.", kind="huy")
    res = nap_anh.read_collect_result(lines, project_root, task, person)
    if st == "loi" and snap.get("returncode") == nap_anh.EXIT_CHUA_XONG and res["pending"] and not g.get("force"):
        return dict(kind="hoi", run=run, person=person, pending=res["pending"], jobs=res["jobs"])
    if st != "xong" or not res["xml"]:
        cause = cvat_io.scrub(day_cvat.last_message(lines)) or "Tiến trình collect kết thúc mà không ghi file gộp."
        if cause.startswith(("Exception", "ValueError", "KeyError", "TypeError", "OSError")) or "Error:" in cause[:40]:
            cause = "Lỗi không lường trước (" + cause[:160] + ")."
        return _fail(d, g, f"Gộp job của đợt {run} không xong: {cause} Chi tiết trong runs\\{run}\\collect_log.txt.")
    nhan = os.path.basename(res["xml"])
    ten_win = res["xml_rel"].replace("/", "\\")                     # chỗ thật của file gộp: raw\\<task>\\<tên> (bản cũ: raw\\<tên>)
    try:
        n = count_labelled(res["xml"], project_root)
    except (SystemExit, Exception) as e:                                # file gộp hỏng / config hỏng: không lưu gì
        return _fail(d, g, f"File gộp {ten_win} không đọc được ({type(e).__name__}): chưa lưu gì.")
    if n == 0:                                                          # thường do chưa Save trong CVAT: không dừng đồng hồ, không lưu gói rỗng
        return _fail(d, g, f"File gộp {ten_win} không có nhãn nào: kiểm đã bấm Save trong từng job CVAT chưa (nhãn chưa Save không được xuất). "
                           "Chưa lưu đồng hồ, chưa ghi gói; Save xong thì bấm Merge jobs & Finish lại.", kind="huy")
    chua =[j["id"] for j in res["jobs"] if j.get("type", "annotation") == "annotation" and j.get("state") != "completed"]
    if g.get("force") and not chua and not res["jobs"]:
        chua = [j["id"] for j in (g.get("pending") or [])]
    fx = dict(kind="xong", run=run, person=person, task=task, n=n, xml_name=nhan, xml_win=ten_win, jobs=res["jobs"], chua=chua, luu=None, xuat_lai=None, loi_luu="", loi_ghi="")
    goi = ""
    v = d.xem(person, run)
    g["luu"] = True                                                     # từ đây có thể đã ghi dòng bấm giờ/gói: lỗi lạ sau này không cho đồng hồ chạy lại (poll)
    if v.get("co_phien"):
        try:
            fx["luu"] = _save(d, person, run, n, nhan)
            goi = fx["luu"]["goi"]["ten"]
        except DongHoLoi as e:
            fx["loi_luu"] = (f"Chưa lưu được đồng hồ: {dong_ho_ui.vi_hop(str(e))} Phiên vẫn còn và đang tạm dừng: sửa rồi bấm Merge jobs & Finish lại, "
                             "hoặc Save timing ở hộp Close page.")
        except Exception as e:                                          # noqa: BLE001 - OSError (file bị khoá) giữa chừng: dòng bấm giờ/gói có thể đã ghi
            fx["loi_luu"] = (f"Lưu đồng hồ chưa trọn ({type(e).__name__}): kiểm outputs\\timing\\timing_{person}.csv và outputs\\ket_qua trước khi lưu lại. "
                             "Đồng hồ không tự chạy lại; phiên (nếu còn) đang tạm dừng: bấm Merge jobs & Finish lại hoặc Save timing ở hộp Close page.")
    else:
        ten = goi_cua_dot(d, person, run)
        if ten:
            try:
                fx["xuat_lai"] = d.xuat_lai_goi(person, ten, nhan_file=nhan)
                goi = fx["xuat_lai"]["ten"]
            except DongHoLoi as e:
                fx["loi_luu"] = f"Chưa gắn được nhãn vào gói {ten}: {dong_ho_ui.vi_hop(str(e))}"
            except Exception as e:                                      # noqa: BLE001
                fx["loi_luu"] = f"Chưa gắn được nhãn vào gói {ten} ({type(e).__name__}): bấm Merge jobs & Finish lại."
    data = dict(task=task, nguoi=person, xml=res["xml_rel"].replace(os.sep, "/"), luc=d.gio.now().isoformat(timespec="seconds"), so_anh_co_nhan=n, jobs=res["jobs"],
                jobs_chua_xong=chua, goi=goi)
    try:
        write_gop(run_dir, data)
    except OSError as e:
        fx["loi_ghi"] = f"Không ghi được runs\\{run}\\{GOP_FILE} ({type(e).__name__}); file gộp và gói vẫn đã ghi."
    fx["gop"] = data
    fx["html"] = result_html(fx)
    return fx


# ---------- trạng thái dùng chung (ctx.gop + ctx.gop_lock) ----------
def begin(ctx, d, m):
    """OK ở hộp xác nhận (m = finish_model vừa kiểm lại, enabled). Đồng hồ của đợt đang chạy thì tạm dừng NGAY (giây xuất và quyết định không tính), ghi ctx.gop
    rồi chạy CollectJob (có --require-completed). Trả True nếu đã tạm dừng đồng hồ. RunError: đồng hồ chạy lại (nếu vừa dừng), ctx.gop bỏ."""
    run, person, task = m["run"], m["person"], m["task"]
    with ctx.gop_lock:
        if ctx.gop is not None:
            raise RunError(f"Đang gộp job của đợt {ctx.gop['run']}: chờ xong.")
        was = False
        if m["co_phien"] and m["trang_thai"] == "chay":
            try:
                d.tam_dung(person, m["rev"], dot=run)
            except DongHoLoi as e:
                raise RunError("Chưa tạm dừng được đồng hồ: " + dong_ho_ui.vi_hop(str(e)))
            was = True
        ctx.gop = dict(run=run, person=person, task=task, was_running=was, phase=PHASE_CHAY, force=False, pending=None, jobs=[])
        try:
            ctx.collect_job.start(run, ctx.runs_root, ctx.project_root, person, task, force=False)
        except RunError as e:
            ctx.gop = None
            note = _resume(d, person, run, was)
            raise RunError((str(e) + " " + note).strip())
    return was


def force(ctx, d, run):
    """OK ở hộp thứ hai (Merge anyway): chạy lại CollectJob KHÔNG có --require-completed. RunError nếu yêu cầu đã cũ (ctx.gop không chờ) hoặc chưa chạy được
    (job gộp khác đang chạy, khoá .dang_chay của đợt đang bận...): khi đó yêu cầu VẪN CHỜ (phase 'hoi', đồng hồ để nguyên) để bấm Merge anyway lại sau,
    hoặc Cancel để quay lại CVAT. `d` giữ cho đồng bộ chữ ký (không đụng đồng hồ ở đây)."""
    with ctx.gop_lock:
        g = ctx.gop
        if not g or g.get("phase") != PHASE_HOI or g.get("run") != run:
            raise RunError("Yêu cầu gộp đã cũ: bấm Merge jobs & Finish lại.")
        g.update(phase=PHASE_CHAY, force=True)
        try:
            ctx.collect_job.start(run, ctx.runs_root, ctx.project_root, g["person"], g["task"], force=True)
        except RunError as e:
            g.update(phase=PHASE_HOI, force=False)                     # lỗi tạm thời: giữ yêu cầu đang chờ, không bỏ, không cho đồng hồ chạy lại
            raise RunError(f"Chưa gộp được: {e} Yêu cầu gộp của đợt {run} vẫn chờ (đồng hồ của đợt để nguyên): chờ rồi bấm Merge anyway lại, "
                           "hoặc Cancel để quay lại CVAT.")


def back_to_cvat(ctx, d):
    """Cancel ở hộp thứ hai: chưa gộp, quay lại CVAT; đồng hồ chạy lại nếu lúc bấm đang chạy; ctx.gop bỏ. Trả câu báo ('' nếu không có gì đang chờ)."""
    with ctx.gop_lock:
        g = ctx.gop
        if not g or g.get("phase") != PHASE_HOI:
            return ""
        ctx.gop = None
    note = _resume(d, g["person"], g["run"], g.get("was_running"))
    return (f"Chưa gộp job của đợt {g['run']}: quay lại CVAT, bấm Finish the job cho từng job rồi bấm Merge jobs & Finish lại. " + note).strip()


def abandon(ctx, d, why=""):
    """Bỏ yêu cầu đang chờ hỏi lần hai (ví dụ điều kiện không còn thoả khi bấm Merge anyway): như back_to_cvat nhưng kèm lý do."""
    note = back_to_cvat(ctx, d)
    return (why + " " + note).strip()


def poll(ctx, d):
    """Gọi ở mỗi nhịp và khi tải/làm mới tab: ctx.gop đang chạy mà job gộp đã dừng thì xử lý ĐÚNG MỘT LẦN (ctx.gop_lock + phase), dù nhiều tab cùng gọi.
    Trả None (không có gì để làm) hoặc kết quả finalize (kind 'xong' | 'hoi' | 'loi' | 'huy'). 'hoi' giữ ctx.gop ở phase chờ; các kind khác bỏ ctx.gop."""
    with ctx.gop_lock:
        g = ctx.gop
        if not g or g.get("phase") != PHASE_CHAY or ctx.collect_job.running:
            return None
        g["phase"] = PHASE_XU_LY
        snap = ctx.collect_job.snapshot()
    r = None
    try:
        try:
            r = finalize(d, ctx.project_root, os.path.join(ctx.runs_root, g["run"]), g, snap)
        except Exception as e:                                          # noqa: BLE001 - lỗi lạ: báo; đã có thể lưu một phần thì không cho đồng hồ chạy lại
            r = _fail(d, g, f"Lỗi không lường trước khi gộp job của đợt {g['run']} ({type(e).__name__}).", resume=not g.get("luu"))
    finally:                                                            # không bao giờ để ctx.gop kẹt ở phase xử lý, kể cả khi chính _fail ném lỗi
        with ctx.gop_lock:
            if r is not None and r["kind"] == "hoi":
                g.update(phase=PHASE_HOI, pending=r["pending"], jobs=r["jobs"])
            elif ctx.gop is g:
                ctx.gop = None
    return r


def waiting(ctx):
    """ctx.gop đang chờ người dùng chọn Merge anyway / Cancel (phase 'hoi'), hoặc None."""
    g = ctx.gop
    return g if g and g.get("phase") == PHASE_HOI else None


def needs_poll(ctx):
    """True khi job gộp đã chạy (phase 'chay') mà kết quả chưa được xử lý: nhịp của tab Các đợt phải còn chạy (kể cả khi tiến trình con đã thoát) để poll."""
    g = ctx.gop
    return bool(g and g.get("phase") == PHASE_CHAY)


def remember_modal(ctx, token):
    """Ghi mã của hộp thứ hai (Merge anyway / Cancel) vào ctx.gop: Cancel của hộp đó luôn quay lại CVAT được, dù tab khác đã thay yêu cầu xác nhận dùng chung
    (dot_anh.Pending chỉ giữ MỘT yêu cầu cho mọi tab)."""
    with ctx.gop_lock:
        g = ctx.gop
        if g and g.get("phase") == PHASE_HOI and token:
            g["tokens"] = (list(g.get("tokens") or []) + [token])[-20:]


def is_force_token(ctx, token):
    """token là mã của một hộp thứ hai của yêu cầu đang chờ (remember_modal)."""
    g = waiting(ctx)
    return bool(g and token and token in (g.get("tokens") or []))


def guard_text(g, what):
    """Câu từ chối `what` (chuyển đợt, xoá đợt...) khi yêu cầu Merge jobs & Finish g = ctx.gop còn dở."""
    if g.get("phase") == PHASE_HOI:
        return (f"Đợt {g['run']} còn job chưa Finish the job trên CVAT và đang chờ bạn chọn Merge anyway hoặc Cancel: bấm Merge jobs & Finish ở thẻ đợt đó "
                f"(tab Các đợt), chọn xong rồi mới {what}.")
    if g.get("phase") == PHASE_CHAY:
        return f"Đang gộp job của đợt {g['run']} (Merge jobs & Finish): chờ xong hoặc bấm Cancel ở khung gộp job của tab Các đợt rồi mới {what}."
    return f"Đang xử lý kết quả gộp job của đợt {g['run']}: chờ vài giây rồi mới {what}."


def block_reason(ctx, d, what, again=""):
    """Lý do phải từ chối `what` (chuyển đợt, Upload & Open...) vì yêu cầu Merge jobs & Finish còn dở, hoặc '' nếu không còn gì dở.
    ctx.gop chỉ sống trong bộ nhớ của trang: chuyển đợt dựng ctx mới là MẤT yêu cầu (hộp Merge anyway / Cancel biến mất, đồng hồ của đợt kẹt ở tạm dừng).
    Job gộp đã dừng mà chưa tab nào xử lý thì xử lý ngay ở đây (poll, đúng một lần) và trả kết quả (kèm `again`: làm gì để thử lại) để người dùng thấy
    kết quả trước khi trang chuyển đi."""
    r = poll(ctx, d)
    if r is not None and r["kind"] != "hoi":
        if r["kind"] == "xong":
            goi = ((r.get("luu") or {}).get("goi") or {}).get("ten") or (r.get("xuat_lai") or {}).get("ten")
            head = (f"Đã gộp job của đợt {r['run']}: {r.get('xml_win') or _raw_win(r['xml_name'])}." + (f" Gói kết quả: {goi}." if goi else "")
                    + (" " + r["loi_luu"] if r.get("loi_luu") else ""))
        else:
            head = r["text"]
        return (head + " " + again).strip()
    g = ctx.gop
    return guard_text(g, what) if g is not None else ""
