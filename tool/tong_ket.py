"""tong_ket — công cụ của NHÓM TRƯỞNG: gộp các gói kết quả của thành viên và tính ba chỉ số của thí nghiệm hai nhóm độc lập (QĐ-006). Chỉ cần gói, KHÔNG cần ảnh hay CVAT.

    python tool\\tong_ket.py --vao <thư mục chứa các gói ketqua_*.zip> --ra outputs\\tong_ket\\
    python tool\\tong_ket.py --vao goi_nhom --vao ketqua_P1_1410_NAP_001.zip --ra outputs\\tong_ket --nguong-sua 2

Mỗi gói do đồng hồ ở đầu trang rà soát (nút "Save timing" trong hộp Đóng trang) của một thành viên ghi ra (outputs\\ket_qua\\ketqua_<Pk>_<DDMM>_<đợt>.zip, kèm bản .json). Người nhóm
MANUAL gán thẳng trong CVAT (không dùng tool) không có gói: nhóm trưởng nhập tay ở tab Thống kê (mục "Nhập tay": thời gian + file nhãn xuất từ CVAT), bản nhập tay là gói cùng định
dạng ghi vào outputs\\goi_nhom của dự án. tong_ket TỰ ĐỌC THÊM các bản nhập tay đó (chỉ bản nhập tay, không đọc gói khác trong outputs\\goi_nhom) trừ khi đã nêu thư mục đó ở --vao
hoặc thêm --khong-nhap-tay; muốn dùng mọi gói trong đó thì thêm --vao outputs\\goi_nhom. Công cụ kiểm sha256, số phiên bản
định dạng, cấu trúc và rò rỉ riêng tư (đường dẫn tuyệt đối, email, tên máy, token) của TỪNG gói, loại gói hỏng hoặc trùng (cùng mã phiên) với lý do rõ ràng, gộp các người, rồi tính:
  (1) NME của nháp so với nhãn gán tay của nhóm manual (cùng ảnh), (2) tỉ lệ điểm phải sửa (nhóm assisted), (3) giây/mặt và % nhanh hơn của assisted so với manual (KTC 90% bằng
cluster bootstrap; mỗi nhóm < 2 người thì chỉ mô tả). Cùng code với tab Thống kê (thong_ke.py, m28core\\so_sanh.py).
Ghi <--ra>\\<YYYYMMDD-HHMM>\\: thong_ke.html (một file, không ảnh), các CSV của thong_ke, goi_da_dung.csv, goi_bi_loai.csv. Cần config\\m28_config.json (50 điểm) của repo.
Mã thoát: 0 xong (có ít nhất một gói dùng được), 2 lỗi đầu vào hoặc không có gói nào dùng được.
"""
import argparse
import os
import sys

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import thong_ke  # noqa: E402
from m28core import bang_mat, nhap_tay, toc_do  # noqa: E402


def bang_goi(st, project_root=None):
    """CSV danh sách gói: goi_da_dung.csv (tên file, nguồn: dong_ho hay nhap_tay), goi_bi_loai.csv (tên file, lý do)."""
    ng = st["nguon"]
    tay = set(ng.get("goi_nhap_tay") or ())
    return {"goi_da_dung": (["ten_goi", "nguon"], [dict(ten_goi=t, nguon="nhap_tay" if t in tay else "dong_ho") for t in ng["goi"]]),
            "goi_bi_loai": (["ten_goi", "ly_do"], [dict(ten_goi=t, ly_do=w) for t, w in ng["goi_hong"] + ng["goi_trung"]])}


def nhap_tay_them(project_root, vao):
    """Đường dẫn các bản nhập tay của nhóm trưởng (<project>\\outputs\\goi_nhom, nguon_nhap=nhap_tay) chưa nằm trong --vao (thư mục hoặc file đã nêu thì không thêm lần nữa)."""
    da_neu = {os.path.realpath(p) for p in vao}
    if os.path.realpath(os.path.join(project_root, nhap_tay.THU_MUC)) in da_neu:
        return []
    out = []
    for _ten, fs in sorted(nhap_tay.file_goi(project_root).items()):
        if not {os.path.realpath(p) for p in fs} & da_neu:
            out.append(next((p for p in fs if p.lower().endswith(".zip")), fs[0]))
    return out


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Tổng kết thí nghiệm hai nhóm từ các gói kết quả của thành viên (không cần ảnh hay CVAT). Chỉ đọc gói; ghi CSV + HTML tĩnh.")
    ap.add_argument("--vao", action="append", required=True, metavar="THƯ_MỤC_HOẶC_FILE", help="thư mục chứa các gói (ketqua_*.zip/.json) hoặc một file gói; dùng nhiều lần được. "
                    "Bản nhập tay của nhóm manual (tab Thống kê, mục Nhập tay, ghi ở outputs\\goi_nhom) được đọc thêm tự động; muốn dùng MỌI gói trong outputs\\goi_nhom thì thêm --vao outputs\\goi_nhom")
    ap.add_argument("--khong-nhap-tay", action="store_true", help="không tự đọc thêm bản nhập tay trong outputs\\goi_nhom của dự án (chỉ dùng đúng các --vao)")
    ap.add_argument("--ra", default=os.path.join("outputs", "tong_ket"), help="thư mục gốc xuất (mặc định outputs\\tong_ket); tạo thư mục con theo ngày-giờ")
    ap.add_argument("--nguong-sua", type=float, default=thong_ke.NGUONG_SUA, help=f"ngưỡng điểm 'đã sửa' (%% IOD, mặc định {thong_ke.NGUONG_SUA:g})")
    ap.add_argument("--gom-ttest", action="store_true", help="gồm cả Ttest (cần data\\manifest.csv để biết mặt nào là Ttest)")
    ap.add_argument("--project", default=bang_mat.mac_dinh_du_an(), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    for p in a.vao:
        if not os.path.exists(p):
            print(f"Lỗi: không thấy {p}.", file=sys.stderr)
            return 2
    try:
        them = [] if a.khong_nhap_tay else nhap_tay_them(a.project, a.vao)
        if them:
            print(f"Đọc thêm {len(them)} bản nhập tay của nhóm trưởng trong {nhap_tay.THU_MUC} (mục Nhập tay ở tab Thống kê; bỏ bằng --khong-nhap-tay): "
                  + ", ".join(os.path.basename(p) for p in them))
        st = thong_ke.tinh(a.project, None, a.nguong_sua, False, a.gom_ttest, None, list(a.vao) + them, False, True)
        if not st["nguon"]["goi"]:
            for t, w in st["nguon"]["goi_hong"]:
                print(f"  bị loại: {w}", file=sys.stderr)
            print("Lỗi: không có gói nào dùng được trong " + ", ".join(a.vao) + ".", file=sys.stderr)
            return 2
        d, files = thong_ke.xuat(a.project, st, a.ra, trong_du_an=False, tieu_de="Tổng kết thí nghiệm M28 — hai nhóm độc lập (từ các gói kết quả)")
        for fn, (cols, rows) in bang_goi(st).items():
            with open(os.path.join(d, fn + ".csv"), "wb") as f:
                f.write(thong_ke.csv_bytes(cols, rows))
            files.append(fn + ".csv")
    except (bang_mat.BangLoi, toc_do.TocDoLoi, ValueError, OSError) as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 2
    ng = st["nguon"]
    tay = set(ng.get("goi_nhap_tay") or ())
    print(f"Đã dùng {len(ng['goi'])} gói: {', '.join(t + (' (nhập tay)' if t in tay else '') for t in ng['goi'])}")
    for t, w in ng["goi_hong"]:
        print(f"  bị loại (hỏng): {w}")
    for t, w in ng["goi_trung"]:
        print(f"  bản trùng, bỏ: {t} — {w}")
    print(f"Đã ghi {bang_mat.rel(a.project, d)} ({len(files)} file)")
    for w in st["meta"]["canh_bao"]:
        print("Cảnh báo:", w)
    thong_ke.in_tom_tat(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
