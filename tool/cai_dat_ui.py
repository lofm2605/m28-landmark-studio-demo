"""Tab "Cài đặt" của trang rà soát M28 (Gradio): CVAT (link, token, tổ chức, Nhớ trên máy này, nút Test CVAT connection và Forget token), người rà, đường dẫn
(thư mục ảnh, file face_landmarker.task), cờ low_conf (t_flip) và pipeline (chỉ đọc).

Không import gradio ở đầu module (gradio chỉ đến từ tham số `gr`, như dot_ui.py); phần dựng HTML thuần ở đầu file để test không cần trình duyệt.
Logic nằm ở cai_dat.py; tab này chỉ nối với Gradio. An toàn:
  * Token chỉ đi MỘT chiều vào server qua ô Token (type="password") của handler Gradio sẵn có (api_visibility="private", cổng 127.0.0.1);
    không bao giờ ở gr.State, value của Textbox, HTML, elem_classes, data-*, giá trị trả về của handler. Về trình duyệt chỉ có dạng che.
  * Mọi handler bọc try/except: lỗi lạ chỉ hiện thông báo đã lọc token, traceback (đã lọc) chỉ ra console.
  * Handler GHI từ chối khi trang đang đóng (ctx.closing); Save / Forget token còn từ chối khi đang đẩy hay xoá task trên CVAT.
  * Mỗi lần ghi tăng `rev`; tab trình duyệt giữ `rev` cũ bị từ chối nhẹ nhàng và tải lại (nhiều tab trình duyệt cùng mở).
  * Test CVAT connection chạy bằng tiến trình con (cai_dat.test_connection): trang vẫn không gọi mạng.
  * "Run CVAT quick check" chạy tool/cvat_smoke.py bằng tiến trình con (nap_anh.SmokeJob, token qua môi trường của nó): tạo task demo-smoke
    giả, nhập nhãn, xuất lại, xoá. Có hộp xác nhận (Cancel mặc định), khoá chéo với đẩy/xoá task, Save/Forget token từ chối khi đang chạy.
"""
import contextlib
import functools
import html
import os
import sys
import time
import traceback
import types

import cai_dat
import day_cvat
import dot_anh
import nap_anh
from m28core import cvat_io
from nap_anh import RunError

KIND_VI = {"bad_url": "sai link", "bad_token": "sai token", "server_down": "server tắt hoặc sai link", "version_mismatch": "khác phiên bản",
           "redirect": "link bị chuyển hướng", "timeout": "server không trả lời", "no_sdk": "thiếu cvat-sdk", "other": "lỗi khác"}

CSS = """
.cd-pop .m28-modal-box { width: min(680px, 100%) !important; }
.cd-pop .cd-sec { gap: 8px; padding: 0 !important; border: 0 !important; background: transparent !important; }
.cd-pop .modal-title { margin-bottom: 2px; }
#cd-cvat-adv { border-radius: 10px; }
.cd-next { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-top: 8px; padding: 8px 10px; border-radius: 8px; font-size: 15px;
  border: 1px solid #2563eb; background: color-mix(in srgb, #2563eb 10%, transparent); }
.cd-next-btn, .cd-link-btn { cursor: pointer; padding: 6px 14px; min-height: 34px; font-size: 15px; font-weight: 700; border-radius: 8px; color: #fff;
  background: #2563eb; border: 1px solid #1d4ed8; }
.cd-next-btn:hover, .cd-link-btn:hover { filter: brightness(.94); }
.cd-next-btn:focus-visible, .cd-link-btn:focus-visible { outline: 3px solid #2563eb; outline-offset: 2px; }
.cd-sec-title { font-size: 17px; font-weight: 800; }
.cd-tf-now { display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px 14px; }
.cd-tf-lbl { font-size: 14px; color: var(--body-text-color-subdued); }
.cd-tf-val { font-family: var(--font-mono); font-size: 26px; }
.cd-tf-what { font-size: 14px; line-height: 1.55; color: var(--body-text-color-subdued); }
.cd-tf-ex { margin-top: 2px; padding: 10px 12px 6px; border-radius: 10px; border: 1px solid var(--border-color-primary); background: #0a0f1d; }
.cd-tf-ex-title { font-size: 13px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; color: #94a3b8; }
.cd-tf-ex svg { display: block; width: 100%; height: auto; }
.cd-tf-lead { font-size: 14px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border-color-primary); background: var(--background-fill-secondary); }
body.m28-lead .cd-tf-lead { display: none; }
body:not(.m28-lead) .m28-lead-block { display: none !important; }  /* phần chỉ Team lead dùng (ô đổi t_flip); cùng cách với .m28-lead-only (giao_dien) */
.cd-tf-edit { gap: 10px !important; padding: 12px 0 0 !important; border-top: 1px solid var(--border-color-primary); }
#cd-tflip-token { display: none !important; }                      /* ô ẩn mang mã xác nhận: Gradio làm mất trạng thái ẩn khi popup đóng/mở lại */
#cd-cvat-status, #cd-cvat-msg, #cd-reviewer-info, #cd-reviewer-msg, #cd-paths-info, #cd-images-msg, #cd-model-msg, #cd-tflip-info, #cd-tflip-msg,
#cd-pipeline, #cd-remember-note, #cd-forget-body, #cd-tflip-body { padding: 0 !important; }
#cd-cvat-msg:not(:has(.html-container > div > *)), #cd-reviewer-msg:not(:has(.html-container > div > *)), #cd-images-msg:not(:has(.html-container > div > *)),
#cd-model-msg:not(:has(.html-container > div > *)), #cd-tflip-msg:not(:has(.html-container > div > *)) { display: none; }
.cd-chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 12px; border-radius: 999px; font-size: 15px; font-weight: 800;
  border: 1px solid var(--cc, #9ca3af); background: color-mix(in srgb, var(--cc, #9ca3af) 16%, transparent); overflow-wrap: anywhere; }
.cd-chip.st-ok { --cc: #16a34a; } .cd-chip.st-err { --cc: #dc2626; } .cd-chip.st-idle, .cd-chip.st-none { --cc: #9ca3af; }
.cd-kv { width: 100%; border-collapse: collapse; font-size: 15px; margin-top: 6px; }
.cd-kv th { text-align: left; font-weight: 600; color: var(--body-text-color-subdued); width: 1%; white-space: nowrap; padding: 4px 12px 4px 0;
  vertical-align: top; border: 0; background: transparent; }
.cd-kv td { padding: 4px 0; vertical-align: top; border: 0; background: transparent; overflow-wrap: anywhere; word-break: break-word; }
.cd-kv code, .cd-path { font-family: var(--font-mono); font-size: 13px; overflow-wrap: anywhere; word-break: break-all; }
#cd-token-row { align-items: flex-end; gap: 8px; flex-wrap: nowrap; }
#cd-token-row #cd-eye { flex: 0 0 auto !important; min-width: 0 !important; width: auto !important; }
#cd-cvat-btns, #cd-reviewer-btns, #cd-images-btns, #cd-model-btns, #cd-tflip-btns { gap: 8px; flex-wrap: wrap; }
#cd-cvat-btns button, #cd-reviewer-btns button, #cd-images-btns button, #cd-model-btns button, #cd-tflip-btns button { min-height: 42px; font-weight: 800;
  min-width: 110px !important; flex: 0 1 auto !important; }
#cd-save:not(:disabled), #cd-forget-ok:not(:disabled) { color: #fff !important; }
#cd-save:not(:disabled) { background: #16a34a !important; border-color: #15803d !important; }
#cd-forget-ok:not(:disabled) { background: #dc2626 !important; border-color: #b91c1c !important; }
#cd-tflip-ok:not(:disabled) { background: #d97706 !important; border-color: #b45309 !important; color: #fff !important; }
.m28-msg.m-err { border-left-color: #dc2626; }
.sm-tbl { width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 6px; }
.sm-tbl th { text-align: left; padding: 4px 8px; border-bottom: 2px solid var(--border-color-primary); white-space: nowrap; }
.sm-tbl td { padding: 4px 8px; vertical-align: top; border-bottom: 1px solid var(--border-color-primary); overflow-wrap: anywhere; }
.sm-tbl .sm-sub td { border-bottom: 0; padding-top: 0; color: var(--body-text-color-subdued); }
.sm-kq { font-weight: 800; white-space: nowrap; } .sm-kq.sm-dat { color: #16a34a; } .sm-kq.sm-hong { color: #dc2626; } .sm-kq.sm-bo { color: #6b7280; }
#cd-smoke-msg:not(:has(.html-container > div > *)), #cd-smoke-result:not(:has(.html-container > div > *)), #cd-smoke-prog:not(:has(.html-container > div > *)) { display: none; }
#cd-smoke-msg, #cd-smoke-prog, #cd-smoke-result, #cd-smoke-body { padding: 0 !important; }
.cd-note { font-size: 14px; line-height: 1.55; color: var(--body-text-color-subdued); overflow-wrap: anywhere; }
.cd-note code { font-family: var(--font-mono); font-size: 13px; }
@media (max-width: 600px) {
  #cd-token-row { flex-wrap: wrap; }
  #cd-cvat-btns button, #cd-reviewer-btns button, #cd-images-btns button, #cd-model-btns button, #cd-tflip-btns button { flex: 1 1 100% !important; }
}
"""

EYE_JS = """() => { const el = document.querySelector('#cd-token input'); if (el) { el.type = (el.type === 'password') ? 'text' : 'password'; } }"""
HIDE_JS = """() => { const el = document.querySelector('#cd-token input'); if (el) { el.type = 'password'; } }"""


def _e(x):
    return html.escape(str(x), quote=True)


def msg_html(text, level="info"):
    return f'<div class="m28-msg m-{level}" role="status">{_e(text)}</div>' if text else ""


def box_html(level, title, lines=()):
    """Khung nap-box (ok | warn | err) với tiêu đề đậm và danh sách dòng. Mọi chuỗi được escape."""
    cls = {"ok": "nap-ok", "warn": "nap-warn", "err": "nap-err"}.get(level, "")
    items = "".join(f"<li>{_e(x)}</li>" for x in lines)
    return (f'<div class="nap-box {cls}" role="{"alert" if level == "err" else "status"}"><b>{_e(title)}</b>'
            + (f"<ul>{items}</ul>" if items else "") + "</div>")


def check_html(res):
    """Kết quả check_images_dir / check_model thành khung ok/warn/err."""
    title = {"ok": "Ổn", "warn": "Dùng được, nhưng cần xem lại", "err": "Chưa dùng được"}[res["level"]]
    return box_html(res["level"], title, [res["path"]] * bool(res["path"]) + res["lines"])


def test_html(res, project, typed=False):
    """Kết quả thử kết nối. `project` là tên project trong pipeline.json. typed=True: giá trị đang gõ, chưa Save."""
    extra = ["Đây là giá trị đang gõ trong ô, chưa bấm Save."] if typed else []
    if res["ok"]:
        pf = res.get("project_found")
        proj = (f"project {project}: đã có (id {res.get('project_id')})" if pf
                else f"project {project}: chưa có (tool tạo khi đẩy lần đầu)")
        lines = [f"CVAT phiên bản {res['server_version']}", f"Đăng nhập bằng token: tài khoản {res['username'] or '?'}", proj]
        if res.get("org"):
            lines.append(f"Tổ chức: {res['org']}")
        return box_html("ok", "Kết nối được", lines + extra)
    return box_html("err", f"Chưa kết nối được ({KIND_VI.get(res['error_kind'], 'lỗi khác')})", [res["message"]] + extra)


def status_html(snap, pipe):
    """Dòng trạng thái CVAT + bảng giá trị (token chỉ dạng che). snap = cai_dat.Settings.snapshot()."""
    t = snap["test"]
    if not snap["url"] or not snap["has_token"]:
        chip, cls = "○ Chưa có link/token", "st-none"
    elif t is None:
        chip, cls = "○ Chưa thử", "st-idle"
    elif t["result"]["ok"]:
        chip, cls = f"● Đã kết nối (thử lúc {t['when']})", "st-ok"
    else:
        chip, cls = f"● Lỗi: {KIND_VI.get(t['result']['error_kind'], 'lỗi khác')} (thử lúc {t['when']})", "st-err"
    rows = [("Link", f'<code>{_e(snap["url"])}</code>' if snap["url"] else "(chưa có)"),
            ("Token", (f'<code>{_e(snap["token_mask"])}</code> · {_e(snap["source_label"])}') if snap["has_token"] else "(chưa có)")]
    if snap["url"] and not snap["has_token"]:
        rows[0] = ("Link", f'<code>{_e(snap["url"])}</code> · {_e(snap["source_label"])}')
    if snap["org"]:
        rows.append(("Tổ chức", f'<code>{_e(snap["org"])}</code>'))
    if t and t["result"]["ok"]:
        r = t["result"]
        rows.append(("Server", f"CVAT {_e(r['server_version'])} · tài khoản <b>{_e(r['username'] or '?')}</b> · project {_e(pipe['project'])}: "
                               + (f"đã có (id {_e(r.get('project_id'))})" if r.get("project_found") else "chưa có (tạo khi đẩy lần đầu)")))
    out = [f'<div><span class="cd-chip {cls}" role="status">{_e(chip)}</span></div>',
           "<table class=\"cd-kv\">" + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows) + "</table>"]
    if snap["dir_error"]:
        out.append(box_html("err", "Không lưu được ra file", [snap["dir_error"]]))
    if snap["file_status"] in ("hong", "khong_doc"):
        out.append(box_html("warn", "File cvat.json " + ("hỏng" if snap["file_status"] == "hong" else "không đọc được"),
                            [f"Đã bỏ qua file này (không hiện nội dung). Bấm Forget token để xoá, hoặc nhập lại rồi bấm Save để ghi lại: {snap['file_path']}"]))
    if snap["env"] == "partial" and snap["source"] != "env":
        out.append(f'<div class="cd-note">Biến môi trường trong cmd chỉ có một trong CVAT_URL / CVAT_ACCESS_TOKEN nên không dùng.</div>')
    if snap["source"] == "env":
        out.append('<div class="cd-note">Đang dùng biến môi trường của cmd. Nhập và bấm Save ở đây thì chỉ trang này dùng giá trị mới '
                   "(biến trong cmd không đổi).</div>")
    return "".join(out)


def reviewer_info_html(snap, ctx_reviewer, run_name, next_name):
    saved = snap["prefs"]["reviewer"]
    cur = (f"Lượt đang mở: <b>{_e(run_name)}</b>, đang ghi vào <code>triage_{_e(ctx_reviewer)}.csv</code> (tên <b>{_e(ctx_reviewer)}</b>). "
           if run_name else f"Chưa mở lượt nào (tên của trang: <b>{_e(ctx_reviewer)}</b>). ")
    out = [cur + f"Tên mặc định đã lưu: <b>{_e(saved) if saved else '(chưa lưu: dùng tên của trang)'}</b>."]
    if snap.get("ten_bo"):
        out.append(f"Tên đã lưu trước đây <b>{_e(snap['ten_bo'])}</b> không còn hợp lệ (tên chỉ gồm chữ không dấu, số và dấu -, không dùng _), nên đang dùng tên mặc định. "
                   "Gõ lại tên (ví dụ thay _ bằng -) rồi bấm Save name.")
    if next_name != ctx_reviewer:
        out.append(f"Lượt đang mở vẫn ghi vào <code>triage_{_e(ctx_reviewer)}.csv</code>; từ lượt sau dùng <b>{_e(next_name)}</b>.")
    if run_name:                                    # chưa mở lượt nào thì không có "lượt đang mở" để nói
        out.append("Đổi tên KHÔNG áp dụng ngay cho lượt đang mở vì phần rà dở nằm ở file theo tên cũ. Tên mới có hiệu lực ở lượt kế tiếp "
                   "(Upload &amp; Open ở tab Nạp ảnh, hoặc Open batch ở tab Các đợt). Mở lại trang bằng dòng lệnh thì tên là tên trong lệnh.")
    return "".join(f'<div class="cd-note">{x}</div>' for x in out)


def paths_info_html(snap, run="<lượt>"):
    imgs = snap["prefs"]["images_dir"]
    mod = snap["prefs"]["model_path"]
    ex_img = imgs or "<thư mục ảnh>"
    rows = [("Thư mục ảnh", f'<code class="cd-path">{_e(imgs)}</code>' if imgs else "(chưa cài)"),
            ("Model", f'<code class="cd-path">{_e(mod)}</code>' if mod else "(chưa cài: tìm face_landmarker.task như cũ)")]
    cmd = f'python tool\\m28.py prepare --run {run} --list data\\r_list.csv --images "{ex_img}" --box auto'
    return ("<table class=\"cd-kv\">" + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows) + "</table>"
            '<div class="cd-note">Model đã cài: tab Nạp ảnh dùng nó (thêm <code>--model</code> khi chạy prepare). Thư mục ảnh: khi đẩy một lượt '
            "chạy bằng lệnh mà ảnh gốc không còn ở đường dẫn cũ, trang thêm <code>--images</code> cho lệnh push; ảnh nạp từ tab Nạp ảnh "
            f'không cần.<br>Lệnh gợi ý (cmd): <code class="cd-path">{_e(cmd)}</code></div>')


def fmt_t(v):
    return "chưa đặt (không gắn cờ nào)" if v is None else cai_dat.fmt_vi(v)


def tflip_info_html(info):
    """Đầu popup low_conf: ngưỡng đang dùng và nó làm gì. Ô đổi ngưỡng chỉ hiện ở chế độ Team lead (.m28-lead-block); annotator thấy dòng .cd-tf-lead."""
    if not info["ok"]:
        return box_html("err", "Không đọc được cấu hình", [info["error"]])
    if info.get("v2"):
        return ('<div class="cd-tf-now"><span class="cd-tf-lbl">Đang dùng</span><b class="cd-tf-val">cờ phiên bản 2</b></div>'
                '<div class="cd-tf-what">Mỗi điểm được chấm xác suất sai từ ba thứ: độ lệch giữa ảnh gốc và ảnh lật của điểm (chia cho khoảng cách hai mắt), '
                'mức lệch chung của cả mặt, và nhóm điểm. Xác suất lớn hơn <b>' + _e(cai_dat.fmt_vi(round(info["v2_threshold"], 3))) + '</b> thì gắn cờ '
                '<b>low_conf</b> (chấm có viền trắng). Mô hình học từ 105 mặt có nhãn gán tay; trên 105 mặt khác, cờ bắt được khoảng 60% điểm sai.</div>'
                + TFLIP_EXAMPLE_SVG +
                '<div class="cd-tf-lead">Ngưỡng t_flip chỉ còn dùng khi config không có mô hình <code>low_conf_v2</code>. '
                'Đổi cờ phải học lại bằng <code>tool\\do_co_thi_nghiem.py --hoc-v2</code> (QĐ-025).</div>')
    return (f'<div class="cd-tf-now"><span class="cd-tf-lbl">Ngưỡng đang dùng</span><b class="cd-tf-val">{_e(fmt_t(info["t_flip"]))}</b></div>'
            '<div class="cd-tf-what">Điểm có độ lệch giữa ảnh gốc và ảnh lật (chia cho khoảng cách hai mắt) lớn hơn ngưỡng thì bị gắn cờ <b>low_conf</b> '
            '(chấm có viền trắng). Ngưỡng càng lớn thì càng ít điểm bị gắn cờ.</div>'
            + TFLIP_EXAMPLE_SVG +
            '<div class="cd-tf-lead">Chỉ <b>Team lead</b> đổi được ngưỡng (bật Team lead ở đầu trang), để cả nhóm dùng cùng một ngưỡng.</div>')


# Hình ví dụ của popup low_conf: trái là cách tính (chấm đặc = ảnh gốc, chấm rỗng = ảnh lật đã lật lại, lệch d chia cho khoảng cách hai mắt),
# phải là cách hai loại chấm hiện trên ảnh lớn (như lớp SVG của ảnh lớn: cùng cỡ 7 px, low_conf chỉ khác viền trắng).
TFLIP_EXAMPLE_SVG = (
    '<div class="cd-tf-ex"><div class="cd-tf-ex-title">Ví dụ</div>'
    '<svg viewBox="0 0 600 190" role="img" aria-label="Ví dụ: điểm lệch nhỏ giữa ảnh gốc và ảnh lật là bình thường, lệch lớn hơn ngưỡng thì bị cờ low_conf">'
    '<g fill="none" stroke="#475569" stroke-width="2"><path d="M42 74 Q96 40 150 74 Q96 98 42 74Z"/><path d="M210 74 Q264 40 318 74 Q264 98 210 74Z"/></g>'
    '<g stroke="#94a3b8" stroke-width="1.5"><line x1="42" y1="122" x2="318" y2="122" stroke-dasharray="5 4"/><line x1="42" y1="114" x2="42" y2="130"/>'
    '<line x1="318" y1="114" x2="318" y2="130"/></g>'
    '<text x="180" y="146" text-anchor="middle" fill="#cbd5e1" font-size="14">khoảng cách hai mắt</text>'
    '<circle cx="150" cy="74" r="5" fill="#f97316" stroke="#0b1220" stroke-width="1.5"/>'
    '<circle cx="153" cy="77" r="5" fill="none" stroke="#fdba74" stroke-width="2"/>'
    '<text x="100" y="30" text-anchor="middle" fill="#86efac" font-size="14">lệch nhỏ: bình thường</text>'
    '<line x1="122" y1="36" x2="146" y2="66" stroke="#86efac" stroke-width="1.2"/>'
    '<circle cx="264" cy="56" r="5" fill="#f97316" stroke="#0b1220" stroke-width="1.5"/>'
    '<circle cx="290" cy="34" r="5" fill="none" stroke="#fdba74" stroke-width="2"/>'
    '<line x1="268" y1="53" x2="285" y2="38" stroke="#fca5a5" stroke-width="2"/>'
    '<text x="268" y="16" text-anchor="middle" fill="#fca5a5" font-size="14">lệch d lớn: low_conf</text>'
    '<text x="180" y="176" text-anchor="middle" fill="#e2e8f0" font-size="14">d ÷ khoảng cách hai mắt &gt; ngưỡng → low_conf</text>'
    '<line x1="352" y1="12" x2="352" y2="180" stroke="#1e2b42" stroke-width="1.5"/>'
    '<text x="376" y="34" fill="#94a3b8" font-size="14">Trên ảnh lớn:</text>'
    '<circle cx="388" cy="70" r="4.5" fill="#f97316" stroke="#141414" stroke-width="1.2"/>'
    '<text x="408" y="75" fill="#e2e8f0" font-size="14">điểm bình thường</text>'
    '<circle cx="388" cy="112" r="4.5" fill="#f97316" stroke="#ffffff" stroke-width="1.8"/>'
    '<text x="408" y="117" fill="#e2e8f0" font-size="14">low_conf: viền trắng</text>'
    '<circle cx="380" cy="152" r="4.5" fill="#f97316"/><text x="392" y="157" fill="#94a3b8" font-size="13">ảnh gốc</text>'
    '<circle cx="470" cy="152" r="4.5" fill="none" stroke="#fdba74" stroke-width="2"/><text x="482" y="157" fill="#94a3b8" font-size="13">ảnh lật</text>'
    '</svg></div>')


def pipeline_html(pi):
    if not pi["ok"]:
        return box_html("warn", "config\\pipeline.json hỏng, đang dùng giá trị mặc định", [pi["error"]]) + _pipe_table(pi["pipe"])
    return _pipe_table(pi["pipe"], pi["exists"])


def _pipe_table(p, exists=True):
    rows = [("cvat_version", p["cvat_version"]), ("job_size", p["job_size"] if p["job_size"] else "0 (một job Nhận + một job Sửa nhãn)"), ("project", p["project"]), ("prefix", p["prefix"])]
    return ("<table class=\"cd-kv\">" + "".join(f"<tr><th>{k}</th><td><code>{_e(v)}</code></td></tr>" for k, v in rows) + "</table>"
            + ('<div class="cd-note">Chỉ đọc (config\\pipeline.json). ' if exists else '<div class="cd-note">Chưa có config\\pipeline.json, dùng mặc định. ')
            + "Tên task tool tạo: <code>" + _e(p["prefix"]) + "&lt;người&gt;-&lt;đợt&gt;</code>, ví dụ <code>" + _e(p["prefix"]) + "Kien-NAP_005</code>.</div>")


def tflip_confirm_html(old, new, images_dir):
    img = images_dir or "<thư mục ảnh>"
    cmd1 = "python tool\\m28.py prepare --run <lượt> --images runs\\<lượt>\\inbox --box auto --force flags autoqc overlays"
    cmd2 = f'python tool\\m28.py prepare --run <lượt> --list <danh sách> --images "{img}" --box auto --force flags autoqc overlays'
    return ('<div class="modal-title" id="cd-tflip-title">Đổi t_flip?</div>'
            f'<table class="m28-info"><tr><th>Từ</th><td><b>{_e(fmt_t(old))}</b></td></tr><tr><th>Thành</th><td><b>{_e(fmt_t(new))}</b></td></tr></table>'
            '<div class="nap-box nap-warn" role="alert"><b>Đợt đã chạy giữ cờ theo ngưỡng cũ; chỉ đợt nạp sau dùng ngưỡng mới.</b> '
            "Muốn tính lại cờ của đợt cũ thì chạy lại <code>prepare</code> với <code>--force flags autoqc overlays</code>, ví dụ:"
            f'<br><code class="cd-path">{_e(cmd1)}</code><br><code class="cd-path">{_e(cmd2)}</code></div>'
            '<div class="cd-tf-what">Đổi xong, đưa file <code>config/m28_config.json</code> lên repo để máy của cả nhóm dùng cùng ngưỡng.</div>')


def smoke_confirm_html(url):
    lines = [f"Sẽ TẠO task demo-smoke (4 ảnh xám giả, không phải ảnh mặt) trong project m28 trên {url or '(chưa có link)'}, nhập nhãn nháp, "
             "xuất lại, rồi XOÁ task đó.",
             "Nếu chưa có project m28 thì tạo rồi xoá lại khi còn trống. Không đụng task khác.",
             "Mất khoảng 1-2 phút. Bấm Cancel check giữa chừng có thể để lại task demo-smoke; lần chạy sau tự dọn nhờ runs\\_smoke\\dang_mo.json."]
    return '<div class="modal-title" id="cd-smoke-title">Chạy kiểm tra nhanh CVAT?</div>' + box_html("warn", "Sẽ làm:", lines)


def smoke_prog_html(snap, prog):
    """Thanh tiến độ của kiểm tra nhanh (cùng kiểu .nap-prog), nhãn từ dòng [k/12] của cvat_smoke.py."""
    st = snap["state"]
    if st == "chua":
        return ""
    pct = 100 if st == "xong" else round(100 * prog["frac"])
    label = prog["label"] if st == "dang_chay" else nap_anh.STATE_VI[st] + (
        f" (mã thoát {snap['returncode']})" if st == "loi" and snap["returncode"] is not None else "")
    if st == "dang_chay" and snap.get("cancelling"):
        label = "Đang huỷ…"
    cls = {"xong": "nap-st-ok", "loi": "nap-st-err", "da_huy": "nap-st-warn"}.get(st, "")
    mm = int(snap["elapsed"])
    return (f'<div class="nap-prog {cls}"><div class="nap-prog-top"><span class="nap-run">Kiểm tra nhanh <b>CVAT</b></span>'
            f'<span class="nap-label">{_e(label)}</span><span class="nap-time">{mm // 60:02d}:{mm % 60:02d}</span></div>'
            f'<div class="m28-bar" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100"><i style="width:{pct}%"></i></div></div>')


def smoke_result_html(rep, json_path=""):
    """Bảng Bước / Kết quả / Ghi chú từ báo cáo .json của cvat_smoke.py (mọi chuỗi được escape) + dòng tổng + đường dẫn báo cáo."""
    cls = {"ĐẠT": "sm-dat", "HỎNG": "sm-hong", "BỎ QUA": "sm-bo"}
    rows = []
    for b in rep.get("buoc", []):
        rows.append(f'<tr><td>{_e(b.get("ma"))}. {_e(b.get("ten"))}</td><td class="sm-kq {cls.get(b.get("ket_qua"), "")}">{_e(b.get("ket_qua"))}</td>'
                    f'<td>{_e(b.get("ghi_chu"))}</td></tr>')
        rows += [f'<tr class="sm-sub"><td></td><td></td><td>- {_e(x)}</td></tr>' for x in b.get("con", [])]
    bad = sum(1 for b in rep.get("buoc", []) if b.get("ket_qua") == "HỎNG")
    txt = os.path.basename(json_path)[:-5] + ".txt" if json_path else ""
    lines = [rep.get("tong", "")]
    if txt:
        lines.append(f"Báo cáo: runs\\_smoke\\{txt}")
    if bad and txt:
        lines.append(f"Gửi file runs\\_smoke\\{txt} cho người phụ trách kỹ thuật của nhóm (không gửi token, không gửi ảnh).")
    box = box_html("err" if bad else "ok", lines[0], lines[1:])
    return box + '<table class="sm-tbl"><tr><th>Bước</th><th>Kết quả</th><th>Ghi chú</th></tr>' + "".join(rows) + "</table>"


# ---------- popup ----------
POPS = ("reviewer", "cvat", "tflip", "paths")
POP_TITLE = {"reviewer": "Người rà", "cvat": "Kết nối CVAT", "tflip": "Cờ low_conf", "paths": "Đường dẫn ảnh và model"}

FOCUS_JS = """() => {
  const t0 = Date.now();
  const go = () => {
    const p = document.querySelector('.cd-pop');
    const ins = p ? Array.from(p.querySelectorAll('input[type=text], input[type=password], textarea')).filter((x) => x.getClientRects().length > 0) : [];
    if (ins.length) { (ins.find((x) => !x.value.trim()) || ins[0]).focus(); return; }
    if (Date.now() - t0 < 1500) { setTimeout(go, 80); }
  };
  setTimeout(go, 220);
}"""

JS_BODY = r"""
  if (!window.__m28Cd) {
    window.__m28Cd = true;
    document.addEventListener('click', (e) => {
      const el = e.target && e.target.closest ? e.target.closest('[data-cd-open]') : null;
      if (!el) { return; }
      const b = document.getElementById('cd-open-' + el.getAttribute('data-cd-open'));
      if (!b) { return; }
      e.preventDefault();
      e.stopPropagation();
      b.click();
    });
  }
"""


NEXT_CVAT_HTML = ('<div class="cd-next">Tiếp theo: nhập link và token CVAT để đẩy nhãn nháp lên. '
                  '<button type="button" class="cd-next-btn" data-cd-open="cvat">Open CVAT settings</button></div>')


def bar_labels(snap, tinfo, reviewer, unset=False):
    t = snap["test"]
    if not snap["url"] or not snap["has_token"]:
        cvat, cv = "CVAT: not set", "stop"
    elif t is None:
        cvat, cv = "CVAT: not tested", "secondary"
    elif t["result"]["ok"]:
        cvat, cv = "CVAT: connected", "primary"
    else:
        cvat, cv = "CVAT: error", "stop"
    tf = tinfo.get("t_flip") if tinfo.get("ok") else None
    return dict(reviewer=("Set name" if unset else reviewer, "stop" if unset else "secondary"),
                cvat=(cvat, cv),
                tflip=("low_conf v2" if tinfo.get("ok") and tinfo.get("v2") else "low_conf: off" if tf is None
                       else f"low_conf {cai_dat.fmt_vi(tf).replace(',', '.')}", "secondary"),
                paths=("Paths", "secondary"))


def settings_bar(gr):
    return {k: gr.Button(v, elem_id=f"cd-open-{k}", size="sm", elem_classes=["cd-open"])
            for k, v in (("reviewer", "Reviewer"), ("cvat", "CVAT"), ("tflip", "low_conf"), ("paths", "Paths"))}


def settings_popups(gr, demo, store, ctx, bar, after_cvat=None, run_name=None, after_model=None, after_reviewer=None):
    S = cai_dat.get()
    pending = dot_anh.Pending()
    run_label = run_name(store.run_dir) if (store is not None and run_name) else ""
    config_path = os.path.join(ctx.project_root or S.project_root, "config", "m28_config.json")
    pops, closers = {}, {}

    @contextlib.contextmanager
    def popup(key):
        with gr.Column(visible=False, elem_id=f"cd-pop-{key}", elem_classes=["m28-modal", "cd-pop"]) as col:
            with gr.Column(elem_classes=["m28-modal-box", "cd-pop-box"]):
                gr.HTML(f'<div class="modal-title" id="cd-pop-{key}-title">{_e(POP_TITLE[key])}</div>', apply_default_css=False)
                yield
                with gr.Row(elem_classes=["m28-modal-btns"]):
                    closers[key] = gr.Button("Close", elem_id=f"cd-pop-{key}-cancel")
        pops[key] = col

    with popup("reviewer"), gr.Column(elem_classes=["cd-sec"]):
        rev_info = gr.HTML(elem_id="cd-reviewer-info", apply_default_css=False)
        rev_tb = gr.Textbox(label="Tên người rà mặc định (dùng từ lượt sau)", max_lines=1, elem_id="cd-reviewer", placeholder="ví dụ P2")
        with gr.Row(elem_id="cd-reviewer-btns"):
            b_rev = gr.Button("Save name", variant="primary", elem_id="cd-reviewer-save")
        rev_msg = gr.HTML(elem_id="cd-reviewer-msg", apply_default_css=False)

    with popup("cvat"), gr.Column(elem_classes=["cd-sec"]):
        st_html = gr.HTML(elem_id="cd-cvat-status", apply_default_css=False)
        url_tb = gr.Textbox(label="Link CVAT (CVAT_URL)", placeholder="http://localhost:8080", max_lines=1, elem_id="cd-url")
        with gr.Row(elem_id="cd-token-row"):
            token_tb = gr.Textbox(label="Token CVAT", type="password", max_lines=1, elem_id="cd-token", scale=5)
            b_eye = gr.Button("Show / Hide", elem_id="cd-eye", size="sm")
        org_tb = gr.Textbox(label="Tổ chức (CVAT_ORG), để trống nếu không dùng", max_lines=1, elem_id="cd-org")
        remember = gr.Checkbox(label="Nhớ trên máy này", value=False, elem_id="cd-remember")
        rem_note = gr.HTML(elem_id="cd-remember-note", apply_default_css=False, visible="hidden")
        with gr.Row(elem_id="cd-cvat-btns"):
            b_save = gr.Button("Save", variant="primary", elem_id="cd-save")
            b_test = gr.Button("Test CVAT connection", elem_id="cd-test")
            b_forget = gr.Button("Forget token", variant="stop", elem_id="cd-forget")
        cvat_msg = gr.HTML(elem_id="cd-cvat-msg", apply_default_css=False)
        with gr.Accordion("Nâng cao: kiểm tra nhanh CVAT và pipeline", open=False, elem_id="cd-cvat-adv"):
            b_smoke = gr.Button("Run CVAT quick check", elem_id="cd-smoke")
            smoke_msg = gr.HTML(elem_id="cd-smoke-msg", apply_default_css=False)
            smoke_prog = gr.HTML(elem_id="cd-smoke-prog", apply_default_css=False)
            smoke_log = gr.Textbox(label="Log kiểm tra nhanh CVAT (đã lọc token)", lines=6, max_lines=12, interactive=False, autoscroll=True,
                                   elem_id="cd-smoke-log", visible=False)
            b_smoke_stop = gr.Button("Cancel check", variant="stop", elem_id="cd-smoke-stop", visible=False)
            smoke_result = gr.HTML(elem_id="cd-smoke-result", apply_default_css=False)
            pipe_html = gr.HTML(elem_id="cd-pipeline", apply_default_css=False)
        smoke_timer = gr.Timer(1.0, active=False)

    with popup("tflip"), gr.Column(elem_classes=["cd-sec"]):
        tf_info = gr.HTML(elem_id="cd-tflip-info", apply_default_css=False)
        with gr.Column(elem_classes=["m28-lead-block", "cd-tf-edit"]):    # chỉ hiện ở chế độ Team lead
            tf_tb = gr.Textbox(label="Ngưỡng mới (0 < t ≤ 1, dấu phẩy hay chấm đều được)", max_lines=1, elem_id="cd-tflip", placeholder="0,0672")
            tf_ack = gr.Checkbox(label="Nhóm đã thống nhất đổi ngưỡng (cấu hình đã chốt)", value=False, elem_id="cd-tflip-ack", visible=False)
            with gr.Row(elem_id="cd-tflip-btns"):
                b_tf_set = gr.Button("Set t_flip", variant="primary", elem_id="cd-tflip-set")
                b_tf_null = gr.Button("Clear", elem_id="cd-tflip-null")
        tf_msg = gr.HTML(elem_id="cd-tflip-msg", apply_default_css=False)
        tf_token = gr.Textbox(visible="hidden", elem_id="cd-tflip-token")   # CSS ẩn hẳn theo id: Gradio làm mất 'hidden' khi popup đóng/mở lại

    with popup("paths"), gr.Column(elem_classes=["cd-sec"]):
        paths_info = gr.HTML(elem_id="cd-paths-info", apply_default_css=False)
        img_tb = gr.Textbox(label="Thư mục ảnh", max_lines=1, elem_id="cd-images", placeholder="D:\\m28\\data\\frames")
        with gr.Row(elem_id="cd-images-btns"):
            b_img_check = gr.Button("Check", elem_id="cd-images-check")
            b_img_save = gr.Button("Save", elem_id="cd-images-save")
        img_msg = gr.HTML(elem_id="cd-images-msg", apply_default_css=False)
        mod_tb = gr.Textbox(label="File face_landmarker.task", max_lines=1, elem_id="cd-model", placeholder="D:\\m28\\face_landmarker.task")
        with gr.Row(elem_id="cd-model-btns"):
            b_mod_check = gr.Button("Check", elem_id="cd-model-check")
            b_mod_save = gr.Button("Save", elem_id="cd-model-save")
        mod_msg = gr.HTML(elem_id="cd-model-msg", apply_default_css=False)

    with gr.Column(visible=False, elem_id="cd-forget-confirm", elem_classes=["m28-modal"]) as forget_modal:
        with gr.Column(elem_classes=["m28-modal-box"]):
            forget_body = gr.HTML(elem_id="cd-forget-body", apply_default_css=False)
            with gr.Row(elem_classes=["m28-modal-btns"]):
                b_forget_ok = gr.Button("Forget token", variant="stop", elem_id="cd-forget-ok")
                b_forget_no = gr.Button("Cancel", elem_id="cd-forget-cancel")
    with gr.Column(visible=False, elem_id="cd-smoke-confirm", elem_classes=["m28-modal"]) as smoke_modal:
        with gr.Column(elem_classes=["m28-modal-box"]):
            smoke_body = gr.HTML(elem_id="cd-smoke-body", apply_default_css=False)
            smoke_keep = gr.Checkbox(label="Giữ task để xem bằng mắt (--giu-task)", value=False, elem_id="cd-smoke-keep")
            with gr.Row(elem_classes=["m28-modal-btns"]):
                b_smoke_ok = gr.Button("Run check", variant="primary", elem_id="cd-smoke-ok")
                b_smoke_no = gr.Button("Cancel", elem_id="cd-smoke-cancel")
    with gr.Column(visible=False, elem_id="cd-tflip-confirm", elem_classes=["m28-modal"]) as tf_modal:
        with gr.Column(elem_classes=["m28-modal-box"]):
            tf_body = gr.HTML(elem_id="cd-tflip-body", apply_default_css=False)
            with gr.Row(elem_classes=["m28-modal-btns"]):
                b_tf_ok = gr.Button("Change t_flip", variant="primary", elem_id="cd-tflip-ok")
                b_tf_no = gr.Button("Cancel", elem_id="cd-tflip-cancel")
    rev_state = gr.State(None)

    outs = [st_html, url_tb, token_tb, org_tb, remember, rem_note, cvat_msg, forget_modal, forget_body, rev_info, rev_tb, rev_msg, paths_info, img_tb,
            img_msg, mod_tb, mod_msg, tf_info, tf_tb, tf_ack, tf_msg, tf_modal, tf_body, tf_token, pipe_html, rev_state]
    outs += [pops[k] for k in POPS] + [bar[k] for k in POPS]
    pop_msgs = {"reviewer": [rev_msg], "cvat": [cvat_msg], "tflip": [tf_msg], "paths": [img_msg, mod_msg]}
    opts = dict(show_progress="hidden", api_visibility="private", concurrency_limit=1)

    # ---------- dựng giá trị hiển thị ----------
    def pipe_info():
        return cai_dat.pipeline_info(ctx.project_root or S.project_root)

    def ret(d):
        return tuple(d.get(c, gr.update()) for c in outs)

    def view(full=False, over=None):
        """dict {component: cập nhật} cho mọi phần hiển thị; full=True thì nạp lại cả các ô nhập từ server (ô token luôn để trống,
        chỉ có placeholder dạng che). over: ghi đè/thêm (thông báo, hộp xác nhận)."""
        snap = S.snapshot()
        pi = pipe_info()
        tinfo = cai_dat.read_t_flip(config_path)
        hint = (f"đã có token {snap['token_mask']} — để trống nếu không đổi" if snap["has_token"]
                else "dán token CVAT (Settings > Security trong CVAT)")
        d = {st_html: status_html(snap, pi["pipe"]), rem_note: "",
             rev_info: reviewer_info_html(snap, ctx.reviewer, run_label, S.next_reviewer(ctx.reviewer)),
             paths_info: paths_info_html(snap), tf_info: tflip_info_html(tinfo), pipe_html: pipeline_html(pi), rev_state: snap["rev"],
             tf_ack: gr.update(visible=bool(tinfo["frozen"])), token_tb: gr.update(placeholder=hint)}
        unset = bool(getattr(ctx, "reviewer_auto", False)) and not S.default_reviewer()
        for k, (label, variant) in bar_labels(snap, tinfo, ctx.reviewer, unset).items():
            d[bar[k]] = gr.update(value=label, variant=variant)
        if full:
            d.update({url_tb: snap["url"], token_tb: gr.update(value="", placeholder=hint), org_tb: snap["org"], remember: snap["remember"],
                      rev_tb: snap["prefs"]["reviewer"], img_tb: snap["prefs"]["images_dir"], mod_tb: snap["prefs"]["model_path"]})
        d.update(over or {})
        return d

    def refuse_why(cvat_busy=False):
        """Lý do từ chối ghi (trang đang đóng; hoặc, với cài đặt CVAT, đang đẩy/xoá task/gộp job/kiểm tra nhanh) hoặc ''."""
        if ctx.closing:
            return nap_anh.CLOSING_MSG
        if cvat_busy:
            for j, what in ((ctx.push_job, "đẩy"), (ctx.del_job, "xoá task")):
                if j.running:
                    return f"Đang {what} lượt {j.run} lên CVAT: chờ xong rồi mới đổi cài đặt CVAT (tiến trình con đang dùng token hiện tại)."
            if ctx.smoke_job.running:
                return "Đang chạy kiểm tra nhanh CVAT: chờ xong hoặc bấm Cancel check rồi mới đổi cài đặt CVAT (tiến trình con đang dùng token hiện tại)."
            if ctx.collect_job.running:
                return (f"Đang gộp job CVAT của lượt {ctx.collect_job.run} (Merge jobs & Finish): chờ xong (hoặc bấm Cancel ở khung gộp job của tab Các đợt) "
                        "rồi mới đổi cài đặt CVAT (tiến trình con đang dùng token hiện tại).")
        return ""

    def safe_with(where):
        """Bọc handler: lỗi lạ chỉ hiện thông báo đã lọc token ở `where` (không traceback ra trình duyệt); traceback đã lọc ra console."""
        def deco(fn):
            @functools.wraps(fn)
            def wrapper(*a):
                try:
                    return fn(*a)
                except Exception as exc:               # noqa: BLE001 - Gradio (show_error=True) sẽ hiện traceback có thể chứa token
                    print(cvat_io.scrub(traceback.format_exc()), file=sys.stderr, flush=True)
                    text = cvat_io.scrub(f"Lỗi không lường trước ({exc.__class__.__name__}). Chi tiết (đã lọc token) ở cửa sổ cmd.")
                    return ret(view(over={where: msg_html(text, "err")}))
            return wrapper
        return deco

    def reload_all(r, where):
        """Nạp lại toàn bộ (kể cả ô nhập) kèm thông báo của kết quả r."""
        return ret(view(full=True, over={where: msg_html(r["msg"], r["level"])}))

    # ---------- tải / chọn tab ----------
    def on_show(rev):
        snap = S.snapshot()
        return ret(view(full=(rev is None or rev != snap["rev"])))

    def show_pop(key, extra=None):
        over = {pops[k]: gr.update(visible=k == key) for k in POPS}
        if key:
            over.update({m: "" for m in pop_msgs[key]})
        over.update(extra or {})
        return ret(view(full=bool(key), over=over))

    def opener(key):
        def on_open():
            return show_pop(key)
        on_open.__name__ = f"on_open_{key}"
        return on_open

    def on_close():
        return show_pop(None)

    # ---------- CVAT ----------
    def note(c, text, level):
        return {c: msg_html(text, level)}

    @safe_with(cvat_msg)
    def on_save(url, token, org, rem, rev):
        cvat_io.register_secret((token or "").strip())
        why = refuse_why(cvat_busy=True)
        if why:
            return ret(view(over=note(cvat_msg, why, "warn")))
        r = S.save_cvat(url, token, org, bool(rem), rev)
        if r["stale"] or r["ok"]:
            return reload_all(r, cvat_msg)
        return ret(view(over=note(cvat_msg, r["msg"], r["level"])))

    @safe_with(cvat_msg)
    def on_test(url, token, org, rev):
        cvat_io.register_secret((token or "").strip())
        why = refuse_why()
        if why:
            return ret(view(over=note(cvat_msg, why, "warn")))
        eff = S.cvat_env()
        url_v = (url or "").strip() or eff["url"]
        tok_v = (token or "").strip() or eff["token"]
        org_v = (org or "").strip()
        typed = ((url or "").strip() != "" and cvat_io.norm_url(url) != cvat_io.norm_url(eff["url"])) or \
                ((token or "").strip() != "" and (token or "").strip() != eff["token"])
        chk = cai_dat.check_url(url_v)
        pipe = pipe_info()["pipe"]
        res = cai_dat.test_connection(url_v, tok_v, org_v, pipe, project_root=ctx.project_root or None)
        S.record_test(chk["url"] if chk["ok"] else url_v, tok_v, org_v, res)
        body = test_html(res, pipe["project"], typed=typed)
        if chk["ok"] and chk["warning"]:
            body += box_html("warn", "Cảnh báo", [chk["warning"]])
        return ret(view(over={cvat_msg: body}))

    @safe_with(cvat_msg)
    def on_forget_open(rev):
        why = refuse_why(cvat_busy=True)
        if why:
            return ret(view(over=note(cvat_msg, why, "warn")))
        snap = S.snapshot()
        lines = ["Xoá file " + (snap["file_path"] or "đã lưu") + " nếu có, và token đã nhập trong phiên này."]
        if snap["env"] != "none":
            lines.append("Token trong biến môi trường của cmd KHÔNG xoá được từ trang: nó vẫn còn trong cmd đang chạy trang này (đóng cmd, hoặc gõ "
                         "set CVAT_ACCESS_TOKEN= rồi mở lại trang để bỏ), và trang vẫn dùng nó.")
        lines.append("Nút Đẩy lên CVAT sẽ khoá lại nếu không còn nguồn token nào. Nên thu hồi token trong CVAT khi xong việc (Settings > Security).")
        body = '<div class="modal-title modal-danger" id="cd-forget-title">Quên token?</div>' + box_html("warn", "Sẽ làm:", lines)
        return ret(view(over={forget_modal: gr.update(visible=True), forget_body: body}))

    @safe_with(cvat_msg)
    def on_forget_ok(rev):
        hide = {forget_modal: gr.update(visible=False), forget_body: ""}
        why = refuse_why(cvat_busy=True)
        if why:
            return ret(view(over={**note(cvat_msg, why, "warn"), **hide}))
        r = S.forget_cvat(rev)
        return ret(view(full=True, over={**note(cvat_msg, r["msg"], r["level"]), **hide}))

    def on_forget_cancel():
        return ret({forget_modal: gr.update(visible=False), forget_body: ""})

    # ---------- người rà ----------
    @safe_with(rev_msg)
    def on_reviewer(name, rev):
        why = refuse_why()
        if why:
            return ret(view(over=note(rev_msg, why, "warn")))
        ten = (name or "").strip() if isinstance(name, str) else ""
        try:
            import dong_ho                                  # nạp lười: chỉ thư viện chuẩn
            co = dong_ho.DongHo(ctx.project_root or S.project_root).cac_nguoi()
        except Exception:
            co = []
        trung = [p for p in co if p != ten and p.casefold() == ten.casefold()] if ten not in co else []
        if trung:
            return ret(view(over=note(rev_msg, f"Đã có người rà tên {trung[0]} (chỉ khác {ten} ở chữ hoa/thường): Windows coi là cùng một file đồng hồ và gói kết quả. "
                                               f"Dùng đúng tên {trung[0]}.", "warn")))
        bo = getattr(S, "ten_bo", "") or ""                 # tên cũ có dấu _ (bản trước) vừa bị bỏ: set_reviewer xoá nó, nên đọc trước
        r = S.set_reviewer(name, rev)
        if r["stale"]:
            return reload_all(r, rev_msg)
        if r["ok"] and getattr(ctx, "reviewer_auto", False) and getattr(ctx, "nap_only", False):
            if bo and bo != r["name"]:
                ctx.ten_cu_bo = bo                          # đồng hồ chưa lưu của tên cũ đó cũng chuyển sang tên mới (after_reviewer)
            if r["name"] != ctx.reviewer:
                ctx.ten_cu_mac_dinh = ctx.reviewer         # tên cũ (mặc định P1, hay tên gõ nhầm rồi sửa) bị thay: after_reviewer chuyển đồng hồ chưa lưu của nó sang tên mới
                ctx.reviewer_mac_dinh = False
            ctx.reviewer = r["name"]                       # mở bằng menu không ghi tên và chưa có lượt nào: tên vừa lưu dùng ngay (đồng hồ, người nạp), không đợi lượt sau
        body = msg_html(r["msg"], r["level"])
        if r["ok"] and not day_cvat.env_state()["ok"]:
            body += NEXT_CVAT_HTML
        return ret(view(full=r["ok"], over={rev_msg: body}))

    # ---------- đường dẫn ----------
    def path_check(kind, msg_c):
        @safe_with(msg_c)
        def on_check(value):
            res = cai_dat.check_images_dir(value) if kind == "images_dir" else cai_dat.check_model(value)
            return ret(view(over={msg_c: check_html(res)}))
        return on_check

    def path_save(kind, msg_c):
        @safe_with(msg_c)
        def on_path_save(value, rev):
            why = refuse_why()
            if why:
                return ret(view(over=note(msg_c, why, "warn")))
            r = S.set_path(kind, value, rev)
            if r["stale"]:
                return reload_all(r, msg_c)
            body = (check_html(r["check"]) if r.get("check") else "") + msg_html(r["msg"], r["level"])
            return ret(view(full=r["ok"], over={msg_c: body}))
        return on_path_save

    # ---------- t_flip ----------
    def tflip_busy():
        for j, what in ((ctx.job, "chuẩn bị ảnh"), (ctx.push_job, "đẩy lên CVAT"), (ctx.del_job, "xoá task"), (ctx.smoke_job, "kiểm tra nhanh CVAT"),
                        (ctx.collect_job, "gộp job CVAT")):
            if j.running:
                return f"Đang {what} (lượt {j.run}): chờ xong rồi đổi t_flip."
        b = cai_dat.busy_runs(ctx.runs_root)
        if b:
            return f"Lượt {b[0][0]} đang có việc chạy ({b[0][1]}): chờ xong rồi đổi t_flip."
        return ""

    def tflip_open(is_null):
        @safe_with(tf_msg)
        def on_tflip(text, ack, rev):
            why = refuse_why() or tflip_busy()
            if why:
                return ret(view(over=note(tf_msg, why, "warn")))
            info = cai_dat.read_t_flip(config_path)
            if not info["ok"]:
                return ret(view(over=note(tf_msg, info["error"], "err")))
            if not is_null and not str(text or "").strip():
                return ret(view(over=note(tf_msg, "Chưa nhập ngưỡng mới (hoặc bấm Clear để bỏ ngưỡng).", "err")))
            try:
                new = None if is_null else cai_dat.parse_t_flip(text)
            except ValueError as e:
                return ret(view(over=note(tf_msg, str(e), "err")))
            if info["frozen"] and not ack:
                return ret(view(over=note(tf_msg, "Cấu hình đã được nhóm chốt: đổi giữa chừng làm cờ của các đợt đã chạy khác với đợt chạy sau. "
                                                  "Tick ô xác nhận ở trên rồi bấm lại.", "warn")))
            if info["t_flip"] == new:
                return ret(view(over=note(tf_msg, f"t_flip đã là {fmt_t(new)}: không có gì để đổi.", "info")))
            it = pending.open(kind="tflip", value=new, old=info["t_flip"])
            return ret(view(over={tf_modal: gr.update(visible=True), tf_body: tflip_confirm_html(info["t_flip"], new, S.images_dir()),
                                  tf_token: it["token"]}))
        return on_tflip

    @safe_with(tf_msg)
    def on_tf_ok(token, ack):
        hide = {tf_modal: gr.update(visible=False), tf_body: "", tf_token: ""}
        it = pending.take(token)
        why = refuse_why() or tflip_busy()
        if why:
            return ret(view(over={**note(tf_msg, why, "warn"), **hide}))
        if it is None:
            return ret(view(over={**note(tf_msg, "Yêu cầu xác nhận đã cũ hoặc không còn hiệu lực: không ghi gì, bấm Set t_flip lại.", "warn"), **hide}))
        info = cai_dat.read_t_flip(config_path)
        if info["ok"] and info["frozen"] and not ack:
            return ret(view(over={**note(tf_msg, "Cấu hình đã được nhóm chốt: tick ô xác nhận rồi bấm lại.", "warn"), **hide}))
        try:
            r = cai_dat.write_t_flip(config_path, it["value"])
        except (RunError, ValueError) as e:
            return ret(view(over={**note(tf_msg, str(e), "err"), **hide}))
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{stamp}] t_flip trong {os.path.normpath(config_path)} đổi: {fmt_t(r['old'])} -> {fmt_t(r['new'])} (từ popup low_conf)", flush=True)
        runs = cai_dat.runs_with_flags(ctx.runs_root)
        lines = [f"Đã đổi t_flip: {fmt_t(r['old'])} → {fmt_t(r['new'])} (lúc {stamp}); các trường khác của config giữ nguyên."]
        if runs:
            lines.append("Các lượt đã có flags.json, tính theo ngưỡng CŨ (chỉ tính lại khi chạy lại prepare với --force flags autoqc overlays): "
                         + ", ".join(runs))
        else:
            lines.append("Chưa có lượt nào có flags.json: chưa lượt nào cần tính lại.")
        return ret(view(over={**{tf_msg: box_html("ok", "Đã ghi", lines)}, **hide}))

    def on_tf_cancel():
        pending.cancel()
        return ret({tf_modal: gr.update(visible=False), tf_body: "", tf_token: ""})

    # ---------- kiểm tra nhanh CVAT (tiến trình con cvat_smoke.py; trang không gọi mạng) ----------
    sm_outs = [smoke_modal, smoke_body, smoke_msg, smoke_prog, smoke_log, b_smoke_stop, smoke_result, smoke_timer, b_smoke]
    sm_job = ctx.smoke_job

    def smoke_busy():
        """Lý do không chạy được kiểm tra nhanh lúc này (đang đóng, đang chuyển lượt, đẩy/xoá task/gộp job/kiểm tra nhanh khác đang chạy) hoặc ''."""
        if ctx.closing:
            return nap_anh.CLOSING_MSG
        if ctx.switch_to is not None:
            return "Trang đang chuyển sang lượt khác: chờ rồi thử lại."
        for j, what in ((ctx.push_job, "đẩy lượt"), (ctx.del_job, "xoá task của lượt"), (ctx.collect_job, "gộp job của lượt"), (sm_job, "chạy kiểm tra nhanh CVAT")):
            if j.running:
                huy = " hoặc bấm Cancel ở khung gộp job của tab Các đợt" if j is ctx.collect_job else " hoặc bấm Cancel"    # job gộp: nút Cancel nằm ở tab Các đợt
                return f"Đang {what}" + ("" if j is sm_job else f" {j.run} (CVAT)") + f": chờ xong{huy} rồi mới chạy kiểm tra nhanh."
        return ""

    def smoke_render(note="", level="warn", modal=None):
        snap = sm_job.snapshot()
        running = snap["state"] == "dang_chay"
        result = ""
        if snap["state"] == "chua":
            pass
        elif snap["state"] in ("xong", "loi") and snap["run_dir"]:
            rep = nap_anh.read_smoke_report(snap["run_dir"], snap["lines"])
            if rep:
                jp = next((ln[len("SMOKE_JSON: "):].strip() for ln in reversed(snap["lines"]) if ln.startswith("SMOKE_JSON: ")), "")
                result = smoke_result_html(rep, jp)
            else:
                result = box_html("err", "Kiểm tra nhanh dừng, chưa có báo cáo", [day_cvat.last_message(snap["lines"]) or "Xem log bên trên."])
        elif snap["state"] == "da_huy":
            result = box_html("warn", "Đã huỷ kiểm tra nhanh", ["Nếu task demo-smoke còn dở trên CVAT thì lần chạy sau tự dọn "
                                                                  "(runs\\_smoke\\dang_mo.json), hoặc xoá tay trong CVAT."])
        lines = "\n".join(snap["lines"][-80:])
        m = modal or {}
        return (m.get("modal", gr.update()), m.get("body", gr.update()), msg_html(note, level) if note else "",
                smoke_prog_html(snap, nap_anh.smoke_progress(snap["lines"])), gr.update(value=lines, visible=bool(lines)),
                gr.update(visible=running, interactive=running and not snap.get("cancelling")), result, gr.Timer(active=running),
                gr.update(interactive=not running))

    def smoke_safe(fn):
        @functools.wraps(fn)
        def wrapper(*a):
            try:
                return fn(*a)
            except Exception as exc:                       # noqa: BLE001 - như safe_with: chỉ thông báo đã lọc token, traceback đã lọc ra console
                print(cvat_io.scrub(traceback.format_exc()), file=sys.stderr, flush=True)
                return smoke_render(cvat_io.scrub(f"Lỗi không lường trước ({exc.__class__.__name__}). Chi tiết (đã lọc token) ở cửa sổ cmd."), "err")
        return wrapper

    @smoke_safe
    def on_smoke_open():
        why = smoke_busy()
        if why:
            return smoke_render(why)
        eff = S.cvat_env()
        if not eff["url"] or not eff["token"]:
            return smoke_render("Chưa có link và token CVAT: nhập và bấm Save ở khung CVAT (hoặc đặt CVAT_URL, CVAT_ACCESS_TOKEN trong cmd) rồi chạy lại.")
        return smoke_render(modal=dict(modal=gr.update(visible=True), body=smoke_confirm_html(cvat_io.norm_url(eff["url"]))))

    @smoke_safe
    def on_smoke_ok(keep):
        hide = dict(modal=gr.update(visible=False), body="")
        why = smoke_busy()
        if why:
            return smoke_render(why, modal=hide)
        eff = S.cvat_env()
        if not eff["url"] or not eff["token"]:
            return smoke_render("Chưa có link và token CVAT.", modal=hide)
        try:
            sm_job.start(ctx.runs_root, ctx.project_root, giu_task=bool(keep))
        except RunError as e:
            return smoke_render(str(e), modal=hide)
        return smoke_render(modal=hide)

    @smoke_safe
    def on_smoke_cancel_dialog():
        return smoke_render(modal=dict(modal=gr.update(visible=False), body=""))

    @smoke_safe
    def on_smoke_stop():
        sm_job.cancel()
        return smoke_render()

    @smoke_safe
    def on_smoke_tick():
        return smoke_render()

    # ---------- nối sự kiện ----------
    wr = dict(opts, concurrency_id="cd")
    ev_save = b_save.click(on_save, [url_tb, token_tb, org_tb, remember, rev_state], outs, **wr)
    b_test.click(on_test, [url_tb, token_tb, org_tb, rev_state], outs, **dict(opts, concurrency_id="cd_test"))
    b_eye.click(None, None, None, js=EYE_JS)
    b_forget.click(on_forget_open, [rev_state], outs, **wr)
    ev_forget = b_forget_ok.click(on_forget_ok, [rev_state], outs, **wr)
    b_forget_no.click(on_forget_cancel, None, outs, **wr)
    ev_save.then(None, None, None, js=HIDE_JS)
    ev_forget.then(None, None, None, js=HIDE_JS)
    if after_cvat is not None:
        after_cvat(ev_save)
        after_cvat(ev_forget)
    ev_rev = b_rev.click(on_reviewer, [rev_tb, rev_state], outs, **wr)
    if after_reviewer is not None:
        after_reviewer(ev_rev)
    b_img_check.click(path_check("images_dir", img_msg), [img_tb], outs, **wr)
    b_img_save.click(path_save("images_dir", img_msg), [img_tb, rev_state], outs, **wr)
    b_mod_check.click(path_check("model_path", mod_msg), [mod_tb], outs, **wr)
    ev_model = b_mod_save.click(path_save("model_path", mod_msg), [mod_tb, rev_state], outs, **wr)
    if after_model is not None:
        after_model(ev_model)
    b_tf_set.click(tflip_open(False), [tf_tb, tf_ack, rev_state], outs, **wr)
    b_tf_null.click(tflip_open(True), [tf_tb, tf_ack, rev_state], outs, **wr)
    b_tf_ok.click(on_tf_ok, [tf_token, tf_ack], outs, **wr)
    b_tf_no.click(on_tf_cancel, None, outs, **wr)
    sm_opts = dict(opts, concurrency_id="cd_smoke")
    b_smoke.click(on_smoke_open, None, sm_outs, **sm_opts)
    b_smoke_ok.click(on_smoke_ok, [smoke_keep], sm_outs, **sm_opts)
    b_smoke_no.click(on_smoke_cancel_dialog, None, sm_outs, **sm_opts)
    b_smoke_stop.click(on_smoke_stop, None, sm_outs, **dict(opts, concurrency_id="cd_smoke_huy"))
    smoke_timer.tick(on_smoke_tick, None, sm_outs, **dict(opts, concurrency_id="cd_smoke_tick"))
    demo.load(on_smoke_tick, None, sm_outs, **dict(opts, concurrency_id="cd_smoke_tick"))
    demo.load(on_show, [rev_state], outs, **dict(opts, concurrency_id="cd"))
    for k in POPS:
        bar[k].click(opener(k), None, outs, **wr).then(None, None, None, js=FOCUS_JS)
        closers[k].click(on_close, None, outs, **wr)
    return types.SimpleNamespace(show=show_pop, outs=outs, opts=dict(opts, concurrency_id="cd"), on_show=on_show, inputs=[rev_state])
