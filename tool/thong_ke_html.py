"""HTML của trang Thống kê (CHỈ BA CHỈ SỐ, QĐ-006): MỘT nguồn dựng HTML cho tab "Thống kê" (thong_ke_ui.py), bản xuất tĩnh (thong_ke.xuat) và tool\tong_ket.py của nhóm trưởng.

Chỉ HTML + CSS thuần: không JavaScript, không CDN, không font tải về, không ảnh (không <img>), không ảnh mặt. Màu lấy theo Ý NGHĨA và cố định:
  * 7 nhóm điểm: m28core.mau_nhom.GROUP_COLOR (giống label CVAT và ảnh chồng), luôn kèm tên nhóm tiếng Việt (GROUP_VI);
  * một chuỗi số đơn lẻ: một màu trung tính; Đạt / Không đạt / Chưa kết luận luôn có chữ + ký hiệu (✓ ✗ •), không chỉ màu.
Số tiêu đề là ô số kèm n; so sánh độ lớn giữa các nhóm là thanh ngang BẮT ĐẦU TỪ 0, cùng thang trong một bảng, số in cạnh thanh; mục tiêu là một vạch đánh dấu có nhãn chữ.
Chữ dùng màu chữ của theme (var(--body-text-color)...), không dùng màu nhóm cho chữ. Trang dùng dấu phẩy thập phân; CSV giữ dấu chấm.
"""
import html

from m28core import mau_nhom

N_NHO = 5
MUC_TIEU_NHANH_HON = 20.0
MUC_TIEU_MAT_HONG = 10.0
NEUTRAL = "#64748b"
KET_LUAN = {"dat": ("✓", "Đạt", "ok"), "khong_dat": ("✗", "Không đạt", "bad"), "chua_ket_luan": ("•", "Chưa kết luận", "mid"), "chua_du_du_lieu": ("•", "Chưa đủ dữ liệu", "mid"),
            "chi_mo_ta": ("•", "Chỉ có kết quả mô tả, chưa kết luận được", "mid")}
COLOR_COND = {"manual": "#64748b", "assisted": "#2563eb"}                 # hai nhóm thí nghiệm: màu cố định, luôn kèm tên nhóm
COND_VI = {"manual": "manual (gán tay)", "assisted": "assisted (dùng tool)"}


def e(x):
    return html.escape("" if x is None else str(x), quote=True)


def num(x, d=1, suffix=""):
    """Số theo kiểu Việt (dấu phẩy thập phân); None -> '—'."""
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return (f"{x:.{d}f}".replace(".", ",")) + suffix


# ---------- thành phần ----------
def trong(t):
    """Trạng thái trống: vì sao trống, cần file nào, ai làm ra file đó. Không bao giờ có số."""
    return ('<div class="tk-trong" role="status"><b>Chưa có số.</b> ' + e(t["ly_do"]) + f'<div class="tk-can">Cần: {e(t["can"])} · người làm ra: <b>{e(t["ai"])}</b></div></div>')


def tile(gia_tri, nhan, n=None, ghi_chu="", cls="", title=""):
    n_html = "" if n is None else f'<div class="tk-tn">n = {e(n)}' + (" · <b>n quá nhỏ</b>" if isinstance(n, int) and n < N_NHO else "") + "</div>"
    return (f'<div class="tk-tile {e(cls)}" title="{e(title)}"><div class="tk-tv">{gia_tri}</div><div class="tk-tl">{e(nhan)}</div>{n_html}'
            + (f'<div class="tk-tg">{ghi_chu}</div>' if ghi_chu else "") + "</div>")


def tiles(*ts):
    return '<div class="tk-tiles">' + "".join(ts) + "</div>"


def chip(kl):
    sym, vi, cls = KET_LUAN[kl]
    return f'<span class="tk-chip tk-{cls}"><span aria-hidden="true">{sym}</span> {vi}</span>'


def thanh(rows, fmt=lambda v: num(v, 2), vach=None, toi_da=None, don_vi=""):
    """Thanh ngang từ 0. rows: [(nhãn, giá trị|None, màu, ghi chú tooltip, n|None)]. Cùng thang (toi_da, mặc định max giá trị / vạch). vach = (giá trị, nhãn chữ)."""
    vals = [v for _l, v, _c, _t, _n in rows if v is not None]
    top = toi_da or max(vals + ([vach[0]] if vach else []) + [1e-9]) * 1.1
    out = ['<div class="tk-bars">']
    for lab, v, col, tip, n in rows:
        if v is None or (n is not None and n < N_NHO):
            out.append(f'<div class="tk-row"><div class="tk-lab">{lab}</div><div class="tk-bar tk-na"></div><div class="tk-val">'
                       + ("n quá nhỏ" if v is not None or n is not None else "—") + (f" <span class=\"tk-n\">(n = {n})</span>" if n is not None else "") + "</div></div>")
            continue
        w = max(0.0, min(100.0, 100.0 * v / top))
        mark = f'<span class="tk-vach" style="left:{100.0 * vach[0] / top:.2f}%" title="{e(vach[1])}"></span>' if vach else ""
        out.append(f'<div class="tk-row" title="{e(tip)}"><div class="tk-lab">{lab}</div><div class="tk-bar"><span class="tk-fill" style="width:{w:.2f}%;background:{col}"></span>{mark}</div>'
                   f'<div class="tk-val">{fmt(v)}{e(don_vi)}' + (f' <span class="tk-n">(n = {n})</span>' if n is not None else "") + "</div></div>")
    if vach:
        out.append(f'<div class="tk-vach-lab">┃ {e(vach[1])}</div>')
    out.append("</div>")
    return "".join(out)


def bang(cols, rows, cls=""):
    """Bảng HTML. cols: [(tiêu đề, khoá|hàm, căn 'l'|'r')]; rows: list dict. Giá trị là chuỗi thường thì bị escape, là raw(...) thì giữ nguyên.
    Bọc trong khung cuộn ngang để trang hẹp (420 px) không bị tràn."""
    cr = ' class="tk-r"'
    th = "".join('<th scope="col"' + (cr if a == "r" else "") + ">" + e(t) + "</th>" for t, _k, a in cols)
    body = []
    for r in rows:
        tds = []
        for _t, k, a in cols:
            v = k(r) if callable(k) else r.get(k)
            tds.append("<td" + (cr if a == "r" else "") + ">" + (v if isinstance(v, _Raw) else e(v)) + "</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return '<div class="tk-tw"><table class="tk-table ' + cls + '"><thead><tr>' + th + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"


class _Raw(str):
    """Chuỗi HTML đã an toàn (không escape lại)."""


def raw(s):
    return _Raw(s)


def lab_nhom(g):
    return (f'<span class="tk-sw" style="background:{mau_nhom.GROUP_COLOR[g]}" aria-hidden="true"></span>{e(mau_nhom.GROUP_VI.get(g, g))}') if g in mau_nhom.GROUP_COLOR else e(g)


def muc(tieu_de, noi_dung, ghi_chu="", mid=""):
    return (f'<section class="tk-sec" id="{e(mid)}"><h3>{e(tieu_de)}</h3>' + (f'<p class="tk-ghi">{ghi_chu}</p>' if ghi_chu else "") + noi_dung + "</section>")


# ---------- đầu trang ----------
def phan_dau(st, tach=False):
    """Dòng meta + các khung ghi chú/cảnh báo ở đầu báo cáo. tach=True: trả (dòng meta, các khung) để trang hiện khung trong nút Log."""
    m, ng, nh = st["meta"], st["nguon"], st["nhom"]
    dong = [f"Lập lúc {e(m['ngay'])}", f"commit {e(m['commit'])}", f"config 50 điểm version {e(m['config_version'])}", f"ngưỡng sửa {num(m['nguong_sua'], 1)}% IOD"]
    out = [f'<div class="tk-meta">{" · ".join(dong)}</div>']
    cau = nh["cau_hinh"]
    if cau:
        out.append('<div class="tk-note"><b>Nhóm theo config\\nhom_thi_nghiem.json:</b> ' + "; ".join(f"{e(p)} → {e(c)}" for p, c in sorted(cau.items()))
                   + (f" · bộ ảnh chung: <b>{e(nh['bo_anh'])}</b>" if nh["bo_anh"] else " · chưa đặt bo_anh") + "</div>")
    else:
        out.append('<div class="tk-note tk-warn">Chưa xếp nhóm trong config\\nhom_thi_nghiem.json (file mẫu còn trống): nhóm lấy từ gói kết quả hoặc dòng bấm giờ; nhãn trong raw\\ chỉ dùng được khi suy được nhóm từ tên task. '
                   'Việc xếp ai vào nhóm nào do cả đội chốt, tool không đoán.</div>')
    out.append('<div class="tk-note"><b>Người theo nhóm:</b> ' + "; ".join(f"{e(COND_VI[c])}: " + (e(", ".join(nh["nguoi"][c])) if nh["nguoi"][c] else "chưa có") for c in ("manual", "assisted")) + "</div>")
    k = st["kiem"]
    if k["n_manual"] or k["n_assisted"]:
        out.append(f'<div class="tk-note{" tk-warn" if k["lech"] else ""}"><b>Hai nhóm làm cùng bộ ảnh?</b> manual có nhãn {k["n_manual"]} ảnh, assisted {k["n_assisted"]} ảnh, chung {k["chung"]}'
                   + (f", chỉ manual {k['chi_manual']}, chỉ assisted {k['chi_assisted']}: <b>LỆCH</b>" if k["lech"] else (": khớp" if k["chung"] else "")) + ".</div>")
    tay = set(ng.get("goi_nhap_tay") or ())                                  # bản nhập tay của nhóm trưởng (nhóm manual gán thẳng trong CVAT): tính như gói, đánh dấu cho rõ
    ten_goi = [t + (" (nhập tay)" if t in tay else "") for t in ng["goi"]]
    out.append('<div class="tk-note"><b>Nguồn:</b> ' + f'{len(ng["goi"])} gói kết quả' + (f" ({e(', '.join(ten_goi))})" if ng["goi"] else "")
               + (f", trong đó {len(tay & set(ng['goi']))} bản nhập tay" if tay & set(ng["goi"]) else "")
               + f'; {len(ng["nhan_raw"])} file nhãn trong raw\\' + (f' ({e(", ".join(f["file"] for f in ng["nhan_raw"][:12]))})' if ng["nhan_raw"] else "")
               + f'; {len(ng["timing"])} file bấm giờ' + (f' ({e(", ".join(ng["timing"][:12]))})' if ng["timing"] else "") + ".</div>")
    if ng.get("doi_ten"):
        out.append('<div class="tk-note"><b>Tên người do nhóm trưởng đặt</b> (file gói không bị sửa): ' + e("; ".join(f"{t}: {a} → {b}" for t, a, b in ng["doi_ten"]))
                   + ". Hai gói cùng tên mới thì tính là một người.</div>")
    for ten, why in ng["goi_hong"]:
        out.append(f'<div class="tk-note tk-warn">Gói bị loại: {e(why)}</div>')
    if ng["goi_trung"]:
        out.append(f'<div class="tk-note">{len(ng["goi_trung"])} bản trùng bị bỏ (cùng mã phiên, thường là bản .json đi kèm .zip): ' + e("; ".join(t for t, _w in ng["goi_trung"][:6]))
                   + (" …" if len(ng["goi_trung"]) > 6 else "") + ". Lý do từng bản nằm trong goi_bi_loai.csv khi dùng tong_ket.py.</div>")
    for w in ng["timing_loi"]:
        out.append(f'<div class="tk-note tk-warn">{e(w)} File này bị bỏ, các file khác vẫn đọc.</div>')
    for w in ng["timing_trung"]:
        out.append(f'<div class="tk-note">Dòng bấm giờ trùng khoá: {e(w)}</div>')
    for n in ng["nhan_bo_qua"]:
        out.append(f'<div class="tk-note">Nhãn {e(n.get("file"))}: {e(n.get("ghi_chu"))}</div>')
    for w in m["canh_bao"]:
        out.append(f'<div class="tk-note tk-warn">{e(w)}</div>')
    if m["n_xoa_mem"]:
        out.append(f'<div class="tk-note">Đã bỏ {m["n_xoa_mem"]} mặt xoá mềm khỏi số đo (chỉ đếm ở đây).</div>')
    if m.get("n_mat_trung"):
        out.append(f'<div class="tk-note tk-warn"><b>Đã bỏ {m["n_mat_trung"]} mặt trùng</b> (cùng tên người và cùng ảnh ở hai nguồn: chỉ tính một lần). Nếu đó là HAI người '
                   "khác nhau mà cùng tên (ví dụ cùng để tên mặc định P1), số liệu đang gộp họ làm một: đặt tên người cho từng gói ở mục Gói đã nạp.</div>")
    return (out[0], "".join(out[1:])) if tach else "".join(out)


def _bars_nhom(r):
    rows = [(lab_nhom(g), v["tb"], mau_nhom.GROUP_COLOR.get(g, NEUTRAL), f"{g}: trung bình lỗi chính các điểm của nhóm, {v['n']} mặt", v["n"]) for g, v in r["nhom"].items()]
    return thanh(rows, lambda v: num(v, 2), vach=(MUC_TIEU_MAT_HONG, "mặt hỏng: NME >= 10% IOD"), don_vi="% IOD")


def _khoi_nme(tieu, r, ghi):
    t = r["tong"]
    out = [f"<h4>{e(tieu)}</h4>", f'<p class="tk-ghi">{ghi}</p>',
           tiles(tile(num(t["tb"], 2, "% IOD"), "NME trung bình", t["n"]), tile(num(t["trung_vi"], 2, "% IOD"), "NME trung vị", t["n"]),
                 tile(num(t["ti_le_hong"], 1, "%"), "mặt hỏng (NME >= 10% IOD)", t["n"], f'{t["n_hong"]}/{t["n"]} mặt'))]
    out.append("<h5>Theo 7 nhóm điểm (trung bình lỗi chính của các điểm trong nhóm, mỗi mặt một giá trị)</h5>" + _bars_nhom(r))
    cols = [("Nhóm điểm", lambda x: raw(lab_nhom(x["g"])), "l"), ("n mặt", "n", "r"), ("Trung bình", lambda x: "n quá nhỏ" if x["n"] < N_NHO else num(x["tb"], 2), "r"),
            ("Trung vị", lambda x: "n quá nhỏ" if x["n"] < N_NHO else num(x["trung_vi"], 2), "r"), ("Mặt hỏng", lambda x: "n quá nhỏ" if x["n"] < N_NHO else f'{x["n_hong"]} ({num(x["ti_le_hong"], 1)}%)', "r")]
    out.append(bang(cols, [dict(g=g, **v) for g, v in r["nhom"].items()]))
    if r["chua_co_dap_an"]:
        out.append(f'<div class="tk-note">{len(r["chua_co_dap_an"])} ảnh chưa có đáp án (chưa có nhãn manual): chưa chấm NME ("chưa có đáp án").</div>')
    if r["khong_cham_duoc"]:
        out.append('<div class="tk-note tk-warn">Không chấm được: ' + e("; ".join(f"{a}: {w}" for a, w in r["khong_cham_duoc"][:5])) + ".</div>")
    return "".join(out)


def muc_nme(st):
    n = st["nme"]
    if n.get("trong"):
        return muc("1. NME của nháp so với nhãn gán tay của nhóm manual", trong(n["trong"]), mid="tk-nme")
    ref = f'Đáp án = nhãn gán tay của nhóm manual trên cùng ảnh ({n["n_manual_mat"]} ảnh, {n["n_nguoi_manual"]} người; nhiều người thì trung bình toạ độ từng điểm theo tên điểm; số người mỗi ảnh: {e(", ".join(str(x) for x in n["n_nguoi_ref"]))}).'
    out = [_khoi_nme("Nháp của máy (nhóm assisted đã nhận) so với đáp án manual", n["nhap"], ref + " NME là % IOD của đáp án; mặt hỏng khi NME ≥ 10% IOD."),
           _khoi_nme("Nhãn cuối của nhóm assisted so với cùng đáp án manual (kiểm \"nhanh hơn mà nhãn không kém đi\")", n["nhan_cuoi"],
                     "Nếu nhãn cuối của assisted gần đáp án manual như hai người manual gần nhau thì nhãn không kém đi; số này CHƯA có mốc nhiễu giữa hai người manual nên đọc kèm số người đáp án.")]
    return muc("1. NME của nháp so với nhãn gán tay của nhóm manual", "".join(out), "NME dùng đúng eval50.face_scores (chỉ số chính, điểm C đo tới đường gấp khúc của đáp án).", "tk-nme")


def muc_sua(st):
    s = st["sua"]
    if s.get("trong"):
        return muc("2. Tỉ lệ điểm phải sửa (nhóm assisted)", trong(s["trong"]), mid="tk-sua")
    out = [tiles(tile(num(s["ti_le"], 1, "%"), f'điểm phải sửa (> {num(s["nguong"], 1)}% IOD)', s["n_mat"], f'{s["n_sua"]}/{s["n_diem"]} điểm nháp, trong đó xoá/ẩn: {s["n_xoa"]}'),
                 tile(num(s["ti_le_mat"], 1, "%"), "mặt phải sửa ít nhất một điểm", s["n_mat"], f'{s["n_mat_phai_sua"]}/{s["n_mat"]} mặt'))]
    rows = [(lab_nhom(g), v["ti_le"], mau_nhom.GROUP_COLOR.get(g, NEUTRAL), f"{g}: {v['n_sua']}/{v['n_diem']} điểm đã sửa", v["n_diem"]) for g, v in s["nhom"].items()]
    out.append("<h5>Theo 7 nhóm điểm (% điểm đã sửa)</h5>" + thanh(rows, lambda v: num(v, 1), toi_da=100.0, don_vi="%"))
    out.append("<h5>Theo người</h5>" + bang([("Người", "nguoi", "l"), ("Mặt", "n_mat", "r"), ("Điểm nháp", "n_diem", "r"), ("Điểm sửa", "n_sua", "r"), ("Trong đó xoá/ẩn", "n_xoa", "r"),
                                             ("% điểm sửa", lambda r: "n quá nhỏ" if r["n_mat"] < N_NHO else num(r["ti_le"], 1), "r"),
                                             ("% mặt phải sửa", lambda r: "n quá nhỏ" if r["n_mat"] < N_NHO else num(r["ti_le_mat"], 1), "r")], s["theo_nguoi"]))
    if s["bo_qua"]:
        out.append(f'<div class="tk-note tk-warn">Bỏ {len(s["bo_qua"])} mặt vì nhãn cuối thiếu IOD (hai khoé mắt ngoài): ' + e(", ".join(a for a, _w in s["bo_qua"][:5])) + ".</div>")
    ghi = (f"Mỗi điểm: khoảng cách điểm-điểm giữa nháp và nhãn cuối chia IOD của nhãn cuối (không dùng khoảng cách tới đường gấp khúc: kéo điểm trượt dọc mí cũng là đã sửa). Ngưỡng {num(s['nguong'], 1)}% IOD "
           "chỉnh được. Điểm có trong nháp mà thiếu hoặc outside trong nhãn cuối tính là đã sửa (đếm riêng là xoá/ẩn). Chỉ nhóm assisted có nháp; nhóm manual không có nháp nên không áp dụng.")
    return muc("2. Tỉ lệ điểm phải sửa (nhóm assisted)", "".join(out), ghi, "tk-sua")


def _bang_nhom_tg(tg):
    rows = []
    for c in ("manual", "assisted"):
        v = tg["nhom"][c]
        rows.append(dict(c=c, n_nguoi=v["n_nguoi"], n_mat=v["n_mat"], tv=v["trung_vi"], tbn=v["tb_nhan"], tbc=v["tb_cong"]))
    cols = [("Nhóm", lambda r: raw(f'<span class="tk-sw" style="background:{COLOR_COND[r["c"]]}" aria-hidden="true"></span>{e(COND_VI[r["c"]])}'), "l"), ("Người", "n_nguoi", "r"), ("Mặt", "n_mat", "r"),
            ("Trung vị (giây/mặt)", lambda r: "—" if r["tv"] is None else ("n quá nhỏ" if r["n_mat"] < N_NHO else num(r["tv"], 1)), "r"),
            ("TB nhân (giây/mặt)", lambda r: "—" if r["tbn"] is None else ("n quá nhỏ" if r["n_mat"] < N_NHO else num(r["tbn"], 1)), "r"),
            ("TB cộng (giây/mặt)", lambda r: "—" if r["tbc"] is None else ("n quá nhỏ" if r["n_mat"] < N_NHO else num(r["tbc"], 1)), "r")]
    return bang(cols, rows)


def muc_thoi_gian(st, an_danh_dau=False):
    """Mục 3. an_danh_dau=True: bỏ bảng 'Dòng bị đánh dấu' (trang đưa bản gộp vào nút Log; bản xuất HTML vẫn có bảng đủ)."""
    tg = st["thoi_gian"]
    f = st["tg_loc"]
    if tg.get("trong"):
        return muc("3. So sánh thời gian: manual và assisted", trong(tg["trong"]), mid="tk-tg")
    out = []
    a, m = tg["nhom"]["assisted"], tg["nhom"]["manual"]
    out.append(_bang_nhom_tg(tg))
    if tg["nhanh_hon_pct"] is None:
        out.append(f'<div class="tk-note tk-warn">{e(tg["ly_do"])}</div>')
    else:
        lo_hi = tg["ktc90_pct"]
        kl = chip(tg["ket_luan"]) if tg["ket_luan"] != "chi_mo_ta" else chip("chi_mo_ta")
        n_txt = f'n: manual {m["n_nguoi"]} người / {m["n_mat"]} mặt, assisted {a["n_nguoi"]} người / {a["n_mat"]} mặt'
        tiles_ = [tile(num(tg["nhanh_hon_pct"], 1, "%"), "assisted nhanh hơn manual (1 − TB nhân assisted ÷ TB nhân manual)", None, kl + f'<div class="tk-n">{e(n_txt)}</div>',
                       title="Mục tiêu: nhanh hơn >= 20%")]
        tiles_.append(tile(f'{num(lo_hi[0], 1)} – {num(lo_hi[1], 1)}%' if lo_hi else "—", "KTC 90% (cluster bootstrap)", None,
                           f'{tg["n_boot"]:,} lần bốc, seed 28'.replace(",", ".") if lo_hi else "cần ≥ 2 người mỗi nhóm để có khoảng tin cậy"))
        tiles_.append(tile(num(tg["nhanh_hon_trung_vi_pct"], 1, "%"), "nhanh hơn theo trung vị", None, "đối chiếu, không thay chỉ số chính"))
        out.append(tiles(*tiles_))
        top = max(40.0, (lo_hi[1] * 1.1) if lo_hi else 0, tg["nhanh_hon_pct"] * 1.1)
        out.append(thanh([("Nhanh hơn manual", max(tg["nhanh_hon_pct"], 0.0), "#2563eb", "1 − TB nhân assisted ÷ TB nhân manual", None)], lambda v: num(v, 1),
                         vach=(MUC_TIEU_NHANH_HON, "mục tiêu: nhanh hơn 20%"), toi_da=top, don_vi="%"))
        if tg["ket_luan"] == "chi_mo_ta":
            out.append(f'<div class="tk-note tk-warn"><b>Chỉ có kết quả mô tả, chưa kết luận được.</b> {e(tg["ly_do"])}</div>')
    if tg["bo_lan"]:
        out.append(f'<div class="tk-note">{tg["bo_lan"]} lần bốc bị bỏ vì một nhóm không có dữ liệu.</div>')
    ds = tg["do_nhay"]
    if ds:
        out.append('<div class="tk-note"><b>Độ nhạy: bỏ dòng bị đánh dấu.</b> ' + (f'Bỏ {ds["n_bo"]} dòng (gián đoạn, sửa tay, có cảnh báo, vượt Q3 + 3·IQR): nhanh hơn {num(ds["nhanh_hon_pct"], 1)}%. Chỉ số chính ở trên KHÔNG bỏ các dòng này.'
                                                                  if ds["nhanh_hon_pct"] is not None else f'Bỏ {ds["n_bo"]} dòng thì một nhóm không còn dữ liệu: không tính được.') + "</div>")
    if tg["n_uoc_luong"]:
        out.append(f'<div class="tk-note"><b>{tg["n_uoc_luong"]} dòng là ước lượng chia đều</b> (giây phiên ÷ số mặt, không đo từng mặt): vẫn tính, nhưng bootstrap theo mặt trong người không thêm thông tin cho các dòng này.</div>')
    out.append("<h5>Từng người</h5>" + bang([("Nhóm", lambda r: COND_VI[r["c"]], "l"), ("Người", "p", "l"), ("Mặt", "n", "r"),
                                             ("Trung vị (giây)", lambda r: "n quá nhỏ" if r["n"] < N_NHO else num(r["tv"], 1), "r"), ("TB nhân (giây)", lambda r: "n quá nhỏ" if r["n"] < N_NHO else num(r["tbn"], 1), "r")],
                                            [dict(c=c, p=p, n=v["n_mat"], tv=v["trung_vi"], tbn=v["tb_nhan"]) for c in ("manual", "assisted") for p, v in tg["nhom"][c]["nguoi"].items()]))
    if (tg["danh_dau"] or tg["ngoai_lai"]) and not an_danh_dau:
        rows = [dict(person=o["person"], condition=o["condition"], face_id=o["face_id"], seconds=o["seconds"], ly=f'vượt Q3 + 3·IQR (ngưỡng {num(o["nguong"], 1)})') for o in tg["ngoai_lai"]]
        rows += [dict(person=o["person"], condition=o["condition"], face_id=o["face_id"], seconds=o["seconds"], ly=o["ly_do"]) for o in tg["danh_dau"]]
        out.append("<h5>Dòng bị đánh dấu — vẫn nằm trong chỉ số chính</h5>" + bang([("Người", "person", "l"), ("Nhóm", "condition", "l"), ("Mặt", "face_id", "l"), ("Giây", lambda r: num(r["seconds"], 1), "r"),
                                                                                  ("Lý do", "ly", "l")], rows))
    loc = [f'{f["dung"]} dòng tính giờ (gói {tg["n_dong_goi"]}, file CSV {tg["n_dong_csv"]})', f'bỏ {f["bo_giay"]} dòng giây trống/≤ 0', f'{f["khoi_dong"]} dòng khởi động (warmup)',
           f'{f["ngoai_dieu_kien"]} dòng không thuộc manual/assisted']
    if f["ngoai_bo_anh"] or f["khong_ro_bo_anh"]:
        loc.append(f'{f["ngoai_bo_anh"]} dòng ngoài bộ ảnh thí nghiệm và {f["khong_ro_bo_anh"]} dòng không rõ bộ ảnh (bỏ ô "Chỉ bộ ảnh thí nghiệm" để gồm)')
    ghi = ("Hai nhóm ĐỘC LẬP (không ghép cặp theo người). Giây/mặt mỗi nhóm: trung vị và trung bình nhân trên mọi mặt của nhóm; % nhanh hơn = (1 − TB nhân assisted ÷ TB nhân manual) × 100, mục tiêu ≥ 20%. "
           "KTC 90% bằng cluster bootstrap: bốc lại người trong nhóm, rồi bốc lại mặt trong từng người đã bốc, 2.000 lần, seed 28. Đạt khi cận dưới KTC ≥ 20%; Không đạt khi cận trên < 20%; còn lại Chưa kết luận; "
           "mỗi nhóm dưới 2 người thì chỉ có kết quả mô tả. " + e("; ".join(loc)) + ".")
    return muc("3. So sánh thời gian: manual và assisted (hai nhóm độc lập)", "".join(out), ghi, "tk-tg")


def han_che(st):
    return '<div class="tk-note"><b>Hạn chế của thiết kế hai nhóm:</b><ul>' + "".join(f"<li>{e(x)}</li>" for x in st["han_che"]) + "</ul></div>"


def noi_dung(st):
    return phan_dau(st) + han_che(st) + muc_nme(st) + muc_sua(st) + muc_thoi_gian(st)


def danh_dau_gon(st):
    """Các dòng thời gian bị đánh dấu (mục 3) gộp theo (người, nhóm, lý do): MỘT dòng cho mỗi nhóm thay vì mỗi mặt một dòng; vẫn tính trong chỉ số chính. '' nếu không có."""
    tg = st["thoi_gian"]
    if tg.get("trong") or not (tg.get("danh_dau") or tg.get("ngoai_lai")):
        return ""
    gop = {}
    for o in tg["ngoai_lai"]:
        gop.setdefault((o["person"], o["condition"], f'vượt Q3 + 3·IQR (ngưỡng {num(o["nguong"], 1)})'), []).append(o["seconds"])
    for o in tg["danh_dau"]:
        gop.setdefault((o["person"], o["condition"], o["ly_do"]), []).append(o["seconds"])
    rows = [dict(person=p, condition=c, ly=ly, n=len(v), lo=min(v), hi=max(v)) for (p, c, ly), v in gop.items()]
    cols = [("Người", "person", "l"), ("Nhóm", "condition", "l"), ("Số mặt", "n", "r"), ("Giây (nhỏ nhất–lớn nhất)", lambda r: num(r["lo"], 1) + ("" if r["lo"] == r["hi"] else "–" + num(r["hi"], 1)), "r"),
            ("Lý do", "ly", "l")]
    return ('<div class="tk-note"><b>Dòng thời gian bị đánh dấu — vẫn nằm trong chỉ số chính</b> (gộp theo người, nhóm và lý do; bảng từng mặt có trong bản xuất HTML và thoi_gian.csv):'
            + bang(cols, rows) + "</div>")


def noi_dung_gon(st):
    """(nội dung chính, log) cho trang: nội dung chính = dòng meta + ba chỉ số; log = nguồn dữ liệu, cảnh báo, bản trùng, hạn chế (hiện trong hộp của nút Log).
    Bản xuất HTML vẫn dùng noi_dung (đủ cả hai)."""
    meta, ghi = phan_dau(st, tach=True)
    n = st["meta"].get("n_mat_trung")
    trung = (f'<div class="tk-note tk-warn"><b>Đã bỏ {n} mặt trùng</b> (cùng tên người, cùng ảnh): nếu là hai người khác nhau cùng tên (ví dụ cùng để mặc định P1) thì số '
             "đang gộp họ làm một; đặt tên người cho từng gói ở mục Gói đã nạp. Chi tiết trong Log.</div>") if n else ""      # quan trọng: hiện cả ở trang chính, không chỉ trong Log
    return meta + trung + muc_nme(st) + muc_sua(st) + muc_thoi_gian(st, an_danh_dau=True), ghi + danh_dau_gon(st) + han_che(st)


# ---------- CSS ----------
CSS = """
.tk-root { font-size: 15px; color: var(--body-text-color); line-height: 1.45; }
.tk-root h2 { margin: 0 0 6px; font-size: 20px; } .tk-root h3 { margin: 22px 0 6px; font-size: 17px; padding-top: 6px; border-top: 1px solid var(--border-color-primary); }
.tk-root h4 { margin: 16px 0 6px; font-size: 15px; } .tk-root h5 { margin: 12px 0 4px; font-size: 14px; color: var(--body-text-color-subdued); }
.tk-meta { font-size: 13px; color: var(--body-text-color-subdued); margin-bottom: 6px; overflow-wrap: anywhere; }
.tk-ghi { font-size: 13px; color: var(--body-text-color-subdued); margin: 4px 0 8px; overflow-wrap: anywhere; }
.tk-note { margin: 6px 0; padding: 7px 10px; border: 1px solid var(--border-color-primary); border-radius: 8px; background: var(--background-fill-secondary); font-size: 14px; overflow-wrap: anywhere; }
.tk-note.tk-warn { border-color: #d97706; background: color-mix(in srgb, #d97706 12%, transparent); }
.tk-trong { margin: 8px 0; padding: 10px 12px; border: 2px dashed var(--border-color-primary); border-radius: 10px; background: var(--background-fill-secondary); overflow-wrap: anywhere; }
.tk-can { margin-top: 4px; font-size: 13px; color: var(--body-text-color-subdued); }
.tk-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; margin: 8px 0; }
.tk-tile { padding: 9px 11px; border: 1px solid var(--border-color-primary); border-radius: 10px; background: var(--block-background-fill); min-width: 0; }
.tk-tv { font-size: 22px; font-weight: 800; line-height: 1.15; overflow-wrap: anywhere; } .tk-tl { font-size: 13px; color: var(--body-text-color-subdued); }
.tk-tn { font-size: 13px; color: var(--body-text-color-subdued); } .tk-tg { margin-top: 3px; font-size: 13px; overflow-wrap: anywhere; }
.tk-bars { display: flex; flex-direction: column; gap: 5px; margin: 6px 0; }
.tk-row { display: grid; grid-template-columns: minmax(90px, 30%) minmax(60px, 1fr) minmax(70px, auto); gap: 8px; align-items: center; }
.tk-lab { font-size: 14px; overflow-wrap: anywhere; } .tk-val { font-size: 14px; font-variant-numeric: tabular-nums; text-align: right; }
.tk-n { color: var(--body-text-color-subdued); font-size: 13px; }
.tk-bar { position: relative; height: 14px; border-radius: 3px; background: var(--background-fill-secondary); border: 1px solid var(--border-color-primary); }
.tk-bar.tk-na { background: repeating-linear-gradient(45deg, transparent 0 6px, var(--border-color-primary) 6px 7px); }
.tk-fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 2px; }
.tk-vach { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--body-text-color); }
.tk-vach-lab { font-size: 13px; color: var(--body-text-color-subdued); }
.tk-sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: baseline; }
.tk-chip { display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: 13px; font-weight: 700; border: 1px solid var(--border-color-primary); color: var(--body-text-color); }
.tk-chip.tk-ok { background: color-mix(in srgb, #16a34a 18%, transparent); border-color: #16a34a; }
.tk-chip.tk-bad { background: color-mix(in srgb, #dc2626 16%, transparent); border-color: #dc2626; }
.tk-chip.tk-mid { background: color-mix(in srgb, #d97706 16%, transparent); border-color: #d97706; }
.tk-tw { overflow-x: auto; max-width: 100%; margin: 4px 0 8px; }
.tk-table { border-collapse: collapse; font-size: 14px; width: 100%; }
.tk-table th, .tk-table td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border-color-primary); vertical-align: middle; background: transparent; white-space: nowrap; }
.tk-table th { font-size: 13px; color: var(--body-text-color-subdued); font-weight: 700; } .tk-table .tk-r { text-align: right; font-variant-numeric: tabular-nums; }
.tk-stack { display: flex; height: 12px; min-width: 90px; border-radius: 3px; overflow: hidden; border: 1px solid var(--border-color-primary); }
.tk-seg { display: block; height: 100%; }
@media (max-width: 600px) { .tk-row { grid-template-columns: 1fr; gap: 2px; } .tk-val { text-align: left; } .tk-tv { font-size: 19px; } }
"""

PAGE_VARS = """
:root { --body-text-color: #1f2937; --body-text-color-subdued: #6b7280; --border-color-primary: #d1d5db; --background-fill-primary: #ffffff;
        --background-fill-secondary: #f3f4f6; --block-background-fill: #ffffff; }
@media (prefers-color-scheme: dark) { :root { --body-text-color: #e5e7eb; --body-text-color-subdued: #9ca3af; --border-color-primary: #374151;
        --background-fill-primary: #111827; --background-fill-secondary: #1f2937; --block-background-fill: #111827; } }
body { margin: 0; padding: 16px; background: var(--background-fill-primary); font-family: ui-sans-serif, system-ui, "Segoe UI", sans-serif; }
.tk-page { max-width: 1100px; margin: 0 auto; }
"""

NGUON_DONG = ("Nguồn dữ liệu: YawDD và DrivFace (bộ nghiên cứu công khai, dùng học thuật/nghiên cứu); nhãn 50 điểm do nhóm gán trong CVAT; nháp từ MediaPipe Face Landmarker (Apache-2.0). "
              "Dự án M28 là <b>phi thương mại</b>: không phát tán, không đăng lại, không giao bên thứ ba. Trang này chỉ có số liệu tổng hợp, không có ảnh mặt người lái xe và không có mã tài xế.")


PAGE_VARS = """
:root { --body-text-color: #1f2937; --body-text-color-subdued: #6b7280; --border-color-primary: #d1d5db; --background-fill-primary: #ffffff;
        --background-fill-secondary: #f3f4f6; --block-background-fill: #ffffff; }
@media (prefers-color-scheme: dark) { :root { --body-text-color: #e5e7eb; --body-text-color-subdued: #9ca3af; --border-color-primary: #374151;
        --background-fill-primary: #111827; --background-fill-secondary: #1f2937; --block-background-fill: #111827; } }
body { margin: 0; padding: 16px; background: var(--background-fill-primary); font-family: ui-sans-serif, system-ui, "Segoe UI", sans-serif; }
.tk-page { max-width: 1100px; margin: 0 auto; }
"""

NGUON_DONG = ("Nguồn dữ liệu: YawDD và DrivFace (bộ nghiên cứu công khai, dùng học thuật/nghiên cứu); nhãn 50 điểm do nhóm gán trong CVAT; nháp từ MediaPipe Face Landmarker (Apache-2.0). "
              "Dự án M28 là <b>phi thương mại</b>: không phát tán, không đăng lại, không giao bên thứ ba. Trang này chỉ có số liệu tổng hợp, không có ảnh mặt người lái xe và không có mã tài xế.")


def trang_tinh(st, tieu_de=None):
    """Một file HTML tự chứa (CSS nội tuyến, sáng/tối theo prefers-color-scheme, rộng 420 px vẫn đọc được). Không ảnh, không script, không đường dẫn tuyệt đối."""
    ten = tieu_de or "Thống kê M28 — NME của nháp, tỉ lệ điểm phải sửa, thời gian manual so với assisted"
    return ("<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>" + e(ten) + "</title><style>" + PAGE_VARS + CSS + "</style></head><body><div class=\"tk-page tk-root\"><h2>" + e(ten) + "</h2>"
            + f'<p class="tk-ghi">{NGUON_DONG}</p>' + noi_dung(st) + "</div></body></html>\n")
