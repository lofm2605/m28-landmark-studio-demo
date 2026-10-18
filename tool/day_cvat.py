"""Nút "Đẩy lên CVAT" và "Xoá task trên CVAT" của trang rà soát M28: logic thuần (khi nào bật, hộp xác nhận, tiến độ, kết quả, lỗi).

Quy ước (giống nap_anh.py):
  * Chỉ thư viện chuẩn. Không import gradio, numpy, steps, torch, cvat_sdk. TRANG KHÔNG GỌI MẠNG: chỉ tiến trình con
    (`m28.py push ...`, xem nap_anh.PushJob/DeleteTaskJob) gọi CVAT. Link/token/tổ chức lấy từ cai_dat.py (một nguồn: giá trị vừa Save ở
    tab Cài đặt > biến môi trường CVAT_URL + CVAT_ACCESS_TOKEN > file đã lưu; đọc lại mỗi lần vẽ). Khung "Đẩy lên CVAT" không có ô nhập
    token (ô nhập chỉ nằm ở tab Cài đặt); token KHÔNG bao giờ hiện lên trang, không đi qua đối số dòng lệnh.
  * Số Nhận / Sửa nhãn / Bỏ trong hộp xác nhận tính bằng ĐÚNG hàm m28core.phan_loai.classify mà steps.push dùng.
"""
import html
import json
import os
import re
import sys

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import dot_anh  # noqa: E402
import cai_dat  # noqa: E402  (nguồn link/token CVAT; chỉ thư viện chuẩn, không mạng)
from m28core import cvat_io, loai_tru, phan_loai  # noqa: E402

PHASES = ["kiểm tra", "kết nối", "project", "tải ảnh", "nhập nhãn", "xuất kiểm"]
PHASE_RE = re.compile(r"^\[(\d)/6\]")
STATE_VI = {"dang_chay": "Đang chạy", "xong": "Xong", "loi": "Lỗi", "da_huy": "Đã huỷ", "chua": ""}
ENV_HELP = ("Bấm nút <b>CVAT</b> ở đầu trang, nhập link <code>http://localhost:8080</code> và token CVAT của bạn, bấm <b>Save</b> (không cần đóng trang). "
            '<button type="button" class="cd-link-btn" data-cd-open="cvat">Open CVAT settings</button> '
            "Cách khác: đóng trang (Ctrl+C), trong <b>cùng cửa sổ cmd</b> gõ <code>set CVAT_URL=http://localhost:8080</code> và "
            "<code>set CVAT_ACCESS_TOKEN=&lt;token của bạn&gt;</code> rồi mở lại trang. Không dán token vào chat hay file.")


def _e(x):
    return html.escape(str(x), quote=True)


# ---------- môi trường ----------
def env_state(environ=None):
    """dict(ok, url, org, source, reason|None). environ=None: lấy từ cài đặt của trang (cai_dat: vừa Save > biến môi trường > file), đọc lại
    mỗi lần gọi; truyền environ (test) thì chỉ đọc đúng dict đó. reason KHÔNG chứa giá trị token."""
    env = cai_dat.cvat_env(environ)
    source = "env" if environ is not None else cai_dat.get().effective()["source"]
    bad = cvat_io.env_problem(env)
    reason = None
    if bad:
        if not env["url"] or not env["token"]:
            miss = " và ".join(n for n, v in (("CVAT_URL", env["url"]), ("CVAT_ACCESS_TOKEN", env["token"])) if not v)
            reason = f"Thiếu {miss}."
        elif not env["url"].startswith(("http://", "https://")):
            reason = f"CVAT_URL phải bắt đầu bằng http:// (đang là {env['url']})."
        else:
            reason = "CVAT_URL không được chứa tên đăng nhập hay mật khẩu."
    return dict(ok=bad is None, url=cvat_io.norm_url(env["url"]), org=env["org"], source=source, reason=reason)


def pipeline_of(project_root):
    """{project, prefix, job_size, cvat_version} đọc config/pipeline.json; hỏng/thiếu thì mặc định (trang không vỡ)."""
    try:
        return cvat_io.load_pipeline(os.path.join(project_root, "config", "pipeline.json"))
    except SystemExit:
        return dict(cvat_io.DEFAULT_PIPELINE)


def task_name(run, pipe, person=None):
    """Tên task khi đẩy (QĐ-021): <người rà>-<đợt>, ví dụ Kien-NAP_005 (prefix của pipeline.json, mặc định rỗng, đứng trước)."""
    return cvat_io.task_name_for(person, run, pipe.get("prefix", ""))


# ---------- kế hoạch đẩy (cùng hàm phân loại với steps.push) ----------
def _no_face(run_dir):
    return phan_loai.read_no_face(run_dir)


def _under_images(images_dir, rel):
    """<images_dir>/<rel> (rel dạng a/b.jpg như steps._upload_path), hoặc None nếu thiếu một trong hai hay rel thoát khỏi thư mục."""
    if not images_dir or not isinstance(rel, str) or not rel:
        return None
    parts = rel.split("/")
    if any(x in ("", "..") or os.path.isabs(x) or "\\" in x or ":" in x for x in parts):
        return None
    return os.path.join(images_dir, *parts)


def _point_names(project_root):
    """Tên 50 điểm từ <project_root>/config/m28_config.json; đọc lỗi hoặc không có project_root thì None (classify rơi về kiểm đúng 50 khoá)."""
    if not project_root:
        return None
    try:
        with open(os.path.join(project_root, "config", "m28_config.json"), encoding="utf-8") as f:
            names = [p["name"] for p in json.load(f)["points"]]
        return names or None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def plan_counts(run_dir, reviewer, project_root=None, pipe=None, images_dir=None):
    """Số Nhận / Sửa nhãn (tách có nháp / ảnh trống) / Bỏ / xoá mềm sẽ đẩy, số job dự kiến, số mặt chưa rà, ảnh thiếu. Cùng hàm với steps.push.
    images_dir (thư mục ảnh đã cài ở tab Cài đặt): ảnh gốc không còn ở đường dẫn ghi trong meta nhưng có ở <images_dir>/<rel> thì
    KHÔNG tính là thiếu, và `via_images` đếm số ảnh như vậy (lúc đó lệnh push phải kèm --images, xem push_model)."""
    pipe = pipe or dict(cvat_io.DEFAULT_PIPELINE)
    excluded = loai_tru.read_excluded(run_dir)
    names, unusable = dot_anh.queue_names(run_dir, excluded)
    tri, err = dot_anh.triage_of(run_dir, reviewer)
    meta_all = dot_anh.read_meta(run_dir)
    meta = {k: v for k, v in meta_all.items() if k not in excluded}      # chỉ để kiểm ảnh thiếu; classify nhận meta đầy đủ
    mp50 = {n: v for n, v in dot_anh.read_mp50(run_dir).items() if n not in excluded}       # nháp thật: classify kiểm Sửa nhãn có nháp hợp lệ
    pl = phan_loai.classify(tri, meta_all, mp50, _no_face(run_dir), excluded, _point_names(project_root))
    remaining = sum(1 for n in names if tri.get(n, ("", ""))[0] not in phan_loai.DECISIONS)
    mode = "auto"
    try:
        with open(os.path.join(run_dir, "crop", "box.txt"), encoding="utf-8") as f:
            text = f.read().strip()
        mode = "auto" if text in ("", "auto") else "crop"      # như steps.read_box_mode: giá trị khác auto = ảnh cắt
    except OSError:
        pass
    missing, via_images = [], 0
    for n in pl["nhan"] + pl["tay"]:
        m = meta.get(n) or {}
        path = (os.path.join(run_dir, "crop", "images", n + ".png") if mode == "crop" else m.get("src"))
        if not path or not os.path.exists(path):
            alt = _under_images(images_dir, m.get("rel")) if mode != "crop" else None
            if alt and os.path.exists(alt):
                via_images += 1
            else:
                missing.append(n)
    return dict(nhan=len(pl["nhan"]), tay=len(pl["tay"]), tay_nhap=len(pl["tay_nhap"]), tay_trong=len(pl["tay_trong"]), bo=len(pl["rejected"]), xoa=len(pl["removed"]), lost=len(pl["lost"]),
                nhan_khong_nhap=len(pl["nhan_khong_nhap"]), jobs=phan_loai.n_jobs(len(pl["nhan"]), len(pl["tay"]), pipe["job_size"]),
                remaining=remaining, missing=missing, via_images=via_images, loi_triage=err)


# ---------- mô hình nút Đẩy ----------
def push_model(run_dir, reviewer, project_root, *, remaining=None, environ=None, job_running=False, images_dir=None):
    """Mô hình của khung "Đẩy lên CVAT" cho một lượt.
    remaining: số mặt chưa rà theo trang (đợt đang rà); None thì tính từ triage_<người rà>.csv.
    images_dir: thư mục ảnh; None thì lấy từ cài đặt (chỉ khi environ=None, tức chạy thật trên trang).
    Trả dict(kind: "done"|"button", enabled, reason, task, plan, env, push, pipe, images_dir) trong đó images_dir chỉ có giá trị khi lượt
    CẦN --images (ảnh gốc ở đường dẫn cũ không còn nhưng có trong thư mục đã cài)."""
    pipe = pipeline_of(project_root)
    run = os.path.basename(os.path.normpath(run_dir))
    env = env_state(environ)
    ps = dot_anh.read_push(run_dir)
    st = (ps or {}).get("trang_thai")
    if images_dir is None and environ is None:
        images_dir = cai_dat.get().images_dir()
    plan = plan_counts(run_dir, reviewer, project_root, pipe, images_dir)
    rem = plan["remaining"] if remaining is None else remaining
    m = dict(kind="button", enabled=False, reason="", task=task_name(run, pipe, reviewer), plan=plan, env=env, push=ps, pipe=pipe, run=run, remaining=rem,
             images_dir=images_dir if plan["via_images"] else None)
    if st == "xong":
        m["kind"] = "done"
        return m
    busy = dot_anh.run_busy(run_dir)
    if job_running or busy:
        m["reason"] = "Đang có việc chạy cho lượt này (" + (busy[0] if busy else "đẩy lên CVAT") + "): chờ xong."
    elif st in ("dang_tao", "da_tao", "da_nhap", "hong"):
        m["reason"] = {"dang_tao": "Lần đẩy trước dừng giữa lúc tạo task (chưa có id).", "da_tao": "Lần đẩy trước dừng sau khi đã tạo task, chưa nhập nhãn.",
                       "da_nhap": "Lần đẩy trước đã nhập nhãn nhưng chưa kiểm xong.", "hong": "push.json bị hỏng."}[st]
        m["partial"] = True
    elif rem > 0:
        m["reason"] = f"Còn {rem} mặt chưa rà."
    elif plan["nhan"] + plan["tay"] == 0:
        m["reason"] = "Không có mặt nào để đẩy (cả Nhận và Sửa nhãn đều trống)."
    elif plan["missing"]:
        m["reason"] = (f"Không thấy {len(plan['missing'])} ảnh để tải lên (ví dụ {plan['missing'][0]}): ảnh gốc đã bị chuyển đi? "
                       "Nếu ảnh gốc đã chuyển chỗ, chọn thư mục ảnh bằng nút Paths ở đầu trang.")
    elif not env["ok"]:
        m["reason"] = env["reason"]
        m["env_help"] = True
    else:
        m["enabled"] = True
    return m


def push_command(run, reviewer, task, images_dir=None):
    """Lệnh cmd tương đương (để người dùng chạy tay nếu muốn). Chạy ở cmd thì phải tự set CVAT_URL / CVAT_ACCESS_TOKEN (tool không đọc cài đặt của trang)."""
    return f"python tool\\m28.py push --run {run} --reviewer {reviewer} --task {task}" + (f' --images "{images_dir}"' if images_dir else "")


def panel_html(m):
    """Nội dung khung (trên nút Đẩy): lý do khoá, hướng dẫn set, hoặc thẻ kết quả khi đã đẩy."""
    if m["kind"] == "done":
        return result_html(m["push"], m["run"], compact=True)
    out = []
    if m["reason"]:
        out.append(f'<div class="m28-warn push-why" role="status">{_e(m["reason"])}</div>')
    if m.get("env_help"):
        out.append(f'<div class="nap-note push-envhelp">{ENV_HELP}</div>')
    if m.get("partial"):
        run, ps = m["run"], m["push"] or {}
        out.append('<div class="nap-note">Xem lại bằng một trong hai lệnh (cmd): '
                   f'<code>python tool\\m28.py push --run {_e(run)} --resume</code> làm nốt trên đúng task đã tạo, hoặc xoá task dở rồi đẩy lại bằng nút '
                   '<b>Delete CVAT task</b> ở tab Các đợt.</div>')
        if ps.get("loi"):
            out.append(f'<div class="m28-warn">{_e(ps["loi"])}</div>')
    if m["enabled"]:
        p = m["plan"]
        out.append(f'<div class="nap-note">Sẵn sàng đẩy: <b>{p["nhan"]}</b> Nhận, <b>{p["tay"]}</b> Sửa nhãn '
                   f'({p["tay_nhap"]} có nháp, {p["tay_trong"]} ảnh trống), <b>{p["bo"]}</b> Bỏ (task <b>{_e(m["task"])}</b>).</div>')
    return "".join(out)


def confirm_html(m):
    """Nội dung hộp xác nhận trước khi đẩy."""
    p = m["plan"]
    rows = [("Tên task", f'<b>{_e(m["task"])}</b>'), ("Mặt Nhận (có nháp 50 điểm, cờ của máy)", f'<b>{p["nhan"]}</b>'),
            ("Mặt Sửa nhãn (job riêng cuối task)",
             f'<b>{p["tay"]}</b> ({p["tay_nhap"]} có nháp — điểm có cờ đánh low_conf, kiểm kỹ cả mặt · {p["tay_trong"]} ảnh trống)'),
            ("Mặt Bỏ (không tải lên)", f'<b>{p["bo"]}</b>')]
    if p["xoa"]:
        rows.append(("Ảnh đã xoá (không tải lên)", f'<b>{p["xoa"]}</b>'))
    phan = ([(f'mỗi job Nhận {m["pipe"]["job_size"]} mặt' if m["pipe"]["job_size"] else 'một job Nhận')] if p["nhan"] else []) + (['một job Sửa nhãn riêng ở cuối'] if p["tay"] else [])
    rows += [("Số job dự kiến", f'<b>{p["jobs"]}</b>' + (f' ({" + ".join(phan)})' if phan else "")),
             ("Địa chỉ CVAT", f'<code>{_e(m["env"]["url"])}</code>' + (f' · tổ chức {_e(m["env"]["org"])}' if m["env"]["org"] else ""))]
    body = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    extra = ""
    if p["nhan_khong_nhap"]:
        extra = f'<div class="m28-warn">{p["nhan_khong_nhap"]} mặt chọn Nhận nhưng không có nháp: tự đưa sang Sửa nhãn (ảnh trống).</div>'
    return ('<div class="modal-title" id="push-confirm-title">Đẩy lên CVAT?</div>'
            f'<table class="m28-info">{body}</table>{extra}'
            f'<div class="nap-note">Chỉ tạo task <b>MỚI</b> trong project <b>{_e(m["pipe"]["project"])}</b>, nhập nhãn nháp đúng một lần rồi xuất lại để kiểm. '
            f'<b>Không đụng task {_e("m28-")}…</b> và không sửa nhãn đã có. Đẩy xong không đẩy lại lần hai được (trừ khi xoá task).</div>')


# ---------- tiến độ, kết quả, lỗi ----------
def parse_phase(lines, state="dang_chay"):
    """Pha hiện tại 1..6 theo dòng '[k/6] …' child in ra (0 = chưa có). Trả dict(k, total, frac, label)."""
    k = 0
    for ln in lines:
        mm = PHASE_RE.match(ln.strip())
        if mm:
            k = max(k, int(mm.group(1)))
    total = len(PHASES)
    if state == "xong":
        return dict(k=total, total=total, frac=1.0, label=f"Xong {total}/{total} bước")
    if k == 0:
        return dict(k=0, total=total, frac=0.0, label="Đang khởi động…")
    return dict(k=k, total=total, frac=(k - 0.5) / total, label=f"Bước {k}/{total} · {PHASES[k - 1]}")


def _mmss(sec):
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def progress_html(snap, what="Đẩy lên CVAT", label=None, frac=None):
    """Thanh tiến độ (kiểu .nap-prog) + trạng thái + thời gian. label/frac: nhãn và tỉ lệ khi đang chạy, cho việc không in dòng '[k/6]'
    (gộp job: gop_job.progress); None thì tính từ dòng '[k/6]' của push."""
    st = snap["state"]
    if st == "chua":
        return ""
    ph = parse_phase(snap["lines"], st)
    if st == "dang_chay" and label is not None:
        ph = dict(ph, label=label, frac=ph["frac"] if frac is None else max(0.0, min(1.0, float(frac))))
    pct = 100 if st == "xong" else round(100 * ph["frac"])
    label = ph["label"] if st == "dang_chay" else STATE_VI[st] + (f" (mã thoát {snap['returncode']})" if st == "loi" and snap["returncode"] is not None else "")
    if st == "dang_chay" and snap.get("cancelling"):
        label = "Đang huỷ…"
    cls = {"xong": "nap-st-ok", "loi": "nap-st-err", "da_huy": "nap-st-warn"}.get(st, "")
    return (f'<div class="nap-prog {cls}"><div class="nap-prog-top"><span class="nap-run">{_e(what)} · lượt <b>{_e(snap["run"])}</b></span>'
            f'<span class="nap-label">{_e(label)}</span><span class="nap-time">{_mmss(snap["elapsed"])}</span></div>'
            f'<div class="m28-bar" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100"><i style="width:{pct}%"></i></div></div>')


def last_message(lines):
    """Dòng cuối có nghĩa của tiến trình con (thường là dòng SystemExit tiếng Việt); bỏ dòng traceback."""
    for ln in reversed(lines):
        s = ln.strip()
        if not s or s.startswith(("File \"", "Traceback", "^", "~")) or re.match(r"^\s*(at |\.\.\.)", s):
            continue
        return s
    return ""


def result_html(ps, run, compact=False):
    """Thẻ kết quả khi push xong: tên task, id, nút mở task (tab mới), số job Nhận/Sửa nhãn, kết quả kiểm check.zip.
    Khi compact=True: giảm bớt nội dung chỉ còn tên task và số job. Không in link dạng chữ (nút Mở task trên CVAT đã làm việc đó)."""
    ps = ps or {}
    jobs = ps.get("jobs") or []
    n_nhan = sum(1 for j in jobs if j.get("kind") == "nhan")
    n_tay = sum(1 for j in jobs if j.get("kind") == "gan_tay")
    url = str(ps.get("task_url") or "")
    open_btn = dot_anh.open_task_button(url)                 # nút to ngay dưới tiêu đề: mở trang task trên CVAT ở tab mới

    chk = ps.get("check") or {}
    if compact:
        job_info = f'<b>{len(jobs)}</b>' + (f' ({n_nhan} Nhận, {n_tay} Sửa nhãn)' if jobs else "")
        bad = (f'<div class="m28-warn">Kiểm sau khi nhập KHÔNG đạt: {chk.get("n_day_du", "?")}/{chk.get("n_nhan", "?")} mặt Nhận đủ 50 điểm. '
               'Xem lại task trên CVAT trước khi sửa.</div>') if chk and not chk.get("ok") else ""
        warn = "".join(f'<div class="m28-warn">{_e(w)}</div>' for w in ps.get("canh_bao", []))
        return (f'<div class="nap-box nap-ok push-done" role="status" aria-label="Đã đẩy lên CVAT">'          # không ghi dòng "Đã đẩy lên CVAT." (khung xanh đã nói)
                + (f'<div class="push-open">{open_btn}</div>' if open_btn else "") +
                f'<table class="m28-info">'
                f'<tr><th>Tên task</th><td><b>{_e(ps.get("task", "?"))}</b></td></tr>'
                f'<tr><th>Số job</th><td>{job_info}</td></tr>'
                f'</table>{bad}{warn}<div class="nap-note push-next">{_e(FINISH_HINT)}</div></div>')

    kiem = (f'Kiểm sau khi nhập: <b>{chk.get("n_day_du", "?")}/{chk.get("n_nhan", "?")}</b> mặt Nhận có đủ 50 điểm kèm low_conf'
            + (" (đạt)" if chk.get("ok") else " (KHÔNG đạt)")) if chk else ""
    if "n_tay_nhap" in chk:                       # push.json lượt mới; lượt cũ không có khoá này nên không hiện dòng
        kiem += (f'<br>Sửa nhãn có nháp: <b>{chk.get("n_tay_nhap_day_du", "?")}/{chk.get("n_tay_nhap", "?")}</b> mặt đủ 50 điểm, mọi low_conf bật'
                 + (f' · {len(chk.get("tay_nhap_thieu") or [])} mặt sai' if chk.get("tay_nhap_thieu") else ""))
    warn = "".join(f'<div class="m28-warn">{_e(w)}</div>' for w in ps.get("canh_bao", []))
    sa = ps.get("so_anh") if isinstance(ps.get("so_anh"), dict) else {}
    gan = (f'<tr><th>Mặt Sửa nhãn</th><td><b>{sa.get("gan_tay", "?")}</b> ({sa["gan_tay_co_nhap"]} có nháp · {sa.get("gan_tay_trong", "?")} ảnh trống)</td></tr>'
           if "gan_tay_co_nhap" in sa else "")
    return (f'<div class="nap-box nap-ok push-done" role="status"><b>Đã đẩy lên CVAT.</b>'
            + (f'<div class="push-open">{open_btn}</div>' if open_btn else "") +
            f'<table class="m28-info"><tr><th>Task</th><td><b>{_e(ps.get("task", "?"))}</b> (id {_e(ps.get("task_id", "?"))})</td></tr>'
            f'<tr><th>Số job</th><td><b>{len(jobs)}</b> ({n_nhan} Nhận, {n_tay} Sửa nhãn)</td></tr>{gan}</table>{kiem}{warn}'
            f'<div class="nap-note push-next">{_e(FINISH_HINT)}</div></div>')


FINISH_HINT = ("Sửa trên CVAT rồi bấm Finish the job cho từng job: trang Sửa trên CVAT tự kiểm, xong hết thì tự chuyển sang Gộp & kết thúc "
               "(Merge jobs & Finish xuất file nhãn gộp vào raw\\).")


def next_step(ps, run, kind="push"):
    """Bước tiếp theo theo push.json sau khi dừng/lỗi/huỷ (tiếng Việt, kèm lệnh cmd). kind: loại job vừa dừng ('push' | 'xoa_task', = ChildJob.KIND).
    Đã đẩy xong: sau job đẩy thì nhắc nút Merge jobs & Finish (FINISH_HINT); sau job XOÁ TASK lỗi/huỷ thì KHÔNG (task vẫn còn, việc đang làm là xoá nó)."""
    st = (ps or {}).get("trang_thai")
    tname = (ps or {}).get("task") or run
    if st == "xong" and kind == "xoa_task":
        return f"Task {tname} vẫn còn trên CVAT (chưa xoá gì): sửa nguyên nhân rồi bấm lại Delete batch (tick ô xoá luôn task) ở tab Các đợt."
    if st == "xong":
        return FINISH_HINT
    if st is None or st == "task_deleted":
        return "Chưa tạo task nào trên CVAT: sửa nguyên nhân rồi bấm Push to CVAT lại."
    if st == "dang_tao":
        return (f"Dừng lúc đang tạo task, chưa có id: chạy python tool\\m28.py push --run {run} --cleanup để xem task cùng tên trên CVAT "
                "(tool không tự xoá) rồi tự xoá trong giao diện CVAT nếu thừa.")
    if st in ("da_tao", "da_nhap"):
        return (f"Task {tname} (id {ps.get('task_id')}) đã tạo trên CVAT, chưa xong: chạy python tool\\m28.py push --run {run} --resume "
                f"để làm nốt, hoặc xoá task dở bằng nút Delete CVAT task (tab Các đợt) / python tool\\m28.py push --run {run} --cleanup --confirm-name {tname}.")
    return ""


def error_html(snap, ps, run):
    """Nguyên nhân (dòng cuối của tiến trình con) + bước tiếp theo. Không hiện traceback (nằm trong push_log.txt). snap['kind'] (ChildJob.KIND) phân biệt
    job đẩy và job xoá task (khung Các đợt dùng chung hàm này cho cả hai)."""
    kind = snap.get("kind") or "push"
    xoa = kind == "xoa_task"
    cause = last_message(snap["lines"]) or ("Tiến trình xoá task kết thúc với lỗi." if xoa else "Tiến trình push kết thúc với lỗi.")
    if cause.startswith(("Exception", "ValueError", "KeyError", "TypeError", "OSError")) or "Error:" in cause[:40]:
        cause = "Lỗi không lường trước (" + cause[:160] + "). Chi tiết trong runs\\" + run + "\\push_log.txt."
    cause = cvat_io.scrub(cause)
    head = "Xoá task trên CVAT không xong." if xoa else "Đẩy lên CVAT không xong."
    return (f'<div class="nap-box nap-err" role="alert"><b>{head}</b><div class="push-cause">{_e(cause)}</div>'
            f'<div class="nap-note">{_e(next_step(ps, run, kind))}</div></div>')


def cancelled_html(ps, run, kind="push"):
    return (f'<div class="nap-box nap-warn" role="status"><b>Đã huỷ.</b> {_e(next_step(ps, run, kind) or "Không có gì dở trên CVAT.")}</div>')


# ---------- xoá task trên CVAT ----------
def delete_model(run_dir, project_root, *, environ=None, job_running=False):
    """Mô hình nút Xoá task: dict(ok, reason, task, task_id, url, state, run). ok chỉ khi mọi điều kiện an toàn đã thoả
    (sau đó tiến trình con còn kiểm lại với CVAT thật)."""
    pipe = pipeline_of(project_root)
    run = os.path.basename(os.path.normpath(run_dir))
    ps = dot_anh.read_push(run_dir) or {}
    st, name, tid = ps.get("trang_thai"), ps.get("task"), ps.get("task_id")
    env = env_state(environ)
    m = dict(ok=False, reason="", task=name, task_id=tid, url=ps.get("cvat_url", ""), state=st, run=run, env=env, pipe=pipe)
    if st not in ("xong", "da_tao", "da_nhap"):
        m["reason"] = "Lượt này chưa có task nào của tool trên CVAT (push.json không ghi id)."
    elif not cvat_io.tool_task_name_ok(name) or not name.startswith(pipe["prefix"]):
        m["reason"] = f"Tên task trong push.json ({name!r}) không phải tên task của tool (hoặc là task chung {cvat_io.RESERVED_PREFIX}…): từ chối xoá."
    elif not isinstance(tid, int) or isinstance(tid, bool) or tid <= 0:
        m["reason"] = "push.json không có id task hợp lệ."
    elif job_running or dot_anh.run_busy(run_dir):
        m["reason"] = "Lượt đang có việc chạy (đẩy lên CVAT hoặc chuẩn bị): chờ xong rồi xoá."
    elif not env["ok"]:
        m["reason"] = env["reason"] + " " + "Bấm nút CVAT ở đầu trang để nhập link và token (hoặc đặt biến môi trường CVAT_URL, CVAT_ACCESS_TOKEN rồi mở lại trang)."
    elif env["url"] != cvat_io.norm_url(ps.get("cvat_url")):
        m["reason"] = f"Task này nằm ở {cvat_io.norm_url(ps.get('cvat_url'))} nhưng CVAT_URL đang là {env['url']}: id task chỉ có nghĩa trên đúng server đã đẩy."
    else:
        m["ok"] = True
    return m


def delete_confirm_ok(model, typed, checked):
    """Nút xác nhận chỉ bật khi gõ ĐÚNG tên task (phân biệt hoa thường, không bỏ khoảng trắng) và tick ô hiểu hậu quả."""
    return bool(model.get("ok")) and typed == model.get("task") and bool(checked)


def delete_confirm_html(m):
    from m28core.push import delete_warning
    lines = delete_warning(m["task"], m["task_id"], m["url"])
    items = "".join(f"<li>{_e(x)}</li>" for x in lines)
    return ('<div class="modal-title modal-danger" id="task-modal-title">Xoá task trên CVAT?</div>'
            f'<div class="nap-box nap-err" role="alert"><b>Không hoàn tác được.</b><ul>{items}</ul></div>'
            f'<div class="nap-note">Nếu cần giữ nhãn đã sửa: đóng hộp này, bấm <b>Merge jobs &amp; Finish</b> ở thẻ đợt (hoặc chạy '
            f'<code>python tool\\m28.py collect --task {_e(m["task"])} --reviewer {_e("<tên bạn>")} --overwrite</code>) '
            'trước, rồi quay lại xoá. Link và token lấy từ cài đặt CVAT (nút CVAT ở đầu trang) hoặc biến môi trường, không nhập ở hộp này.</div>')
