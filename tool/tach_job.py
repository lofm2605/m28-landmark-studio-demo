"""tach_job — tách file nhãn CẢ TASK (đã xuất bằng collect) thành file nhãn theo TỪNG JOB, OFFLINE (không CVAT, không mạng, không ảnh).

    python tool\\tach_job.py --xml raw\\demo-F5_P2_1810.xml
    python tool\\tach_job.py --xml raw\\demo-F5_P2_1810.xml --job 105 --job 106
    python tool\\tach_job.py --xml final\\demo-F5_P2_1810.xml --out final\\ --config config\\m28_config.json

Ranh giới job đọc từ file .txt cạnh file XML (--txt đổi được): dòng `job <id>: <n> frame, stage <s>, state <t> | frames <a>-<b> | loai <nhan|gan_tay|khong_ro>`;
.txt cũ không có `frames` thì tính cộng dồn từ n; không có .txt thì lỗi rõ (không đoán). Mỗi job ra `<--out>\\<tên file cả task>_job<id>.xml` + `.txt` cùng tên.
File đã có KHÔNG bị ghi đè. File job chỉ để ĐỌC/ĐO (eval50, QC, xem lại), KHÔNG nhập lại vào CVAT (nhập sẽ thay toàn bộ nhãn của task bằng nhãn của một job).
Mã thoát: 0 xong (kể cả khi mọi file đã có), 2 lỗi đầu vào (thiếu file/.txt, id ảnh ngoài mọi job, --job không tồn tại...).
Chi tiết quy tắc: m28core/tach_job.py. collect cũng gọi cùng module này (mặc định bật cho task demo-…).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m28core import tach_job as core  # noqa: E402


def build_parser():
    p = argparse.ArgumentParser(prog="tach_job", description="Tách file nhãn cả task (CVAT for images 1.1) thành file theo từng job, offline. "
                                "File job chỉ để đọc/đo, không nhập lại vào CVAT.")
    p.add_argument("--xml", required=True, help="file nhãn cả task, ví dụ raw\\demo-F5_P2_1810.xml")
    p.add_argument("--txt", help="file .txt có dòng job (mặc định: file .txt cùng tên cạnh --xml)")
    p.add_argument("--out", help="thư mục ghi file job (mặc định: thư mục chứa --xml); dùng được cho final\\")
    p.add_argument("--job", type=int, nargs="+", action="extend", metavar="ID",
                   help="chỉ ghi các job có id này (viết nhiều id sau một --job hoặc lặp --job); mặc định tất cả job")
    p.add_argument("--config", help="tuỳ chọn: config\\m28_config.json để in thêm số mặt đủ 50 điểm của từng file job")
    p.add_argument("--runs", default="runs", help="thư mục runs\\ để tra loại job (nhan/gan_tay) từ push.json khi .txt chưa ghi (mặc định: runs)")
    return p


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    args = build_parser().parse_args(argv)
    xml = args.xml
    if not os.path.isfile(xml):
        print(f"LỖI: không thấy file {xml}.")
        return 2
    m = core.JOB_RE.match(os.path.basename(xml))
    if m:
        print(f"LỖI: {os.path.basename(xml)} đã là file của một job (job {m.group('job')}); tách từ file cả task {m.group('goc')}.xml.")
        return 2
    point_names = None
    if args.config:
        from m28core import collect
        point_names = collect._point_names(args.config)
        if point_names is None:
            print(f"LỖI: không đọc được {args.config}.")
            return 2
    out_dir = args.out or os.path.dirname(xml) or "."
    try:
        res = core.tach(xml, out_dir, txt_path=args.txt, only=args.job, runs_dir=args.runs)
    except core.TachJobLoi as e:
        print(f"LỖI: {e}")
        return 2
    print(f"{os.path.basename(xml)}: task {res['task'] or '?'}, {len(res['jobs'])} job được tách ({res['kiem_lech']}).")
    n_new = 0
    for j in res["jobs"]:
        line = f"  job {j['id']} ({j['kind']}) frames {j['start']}-{j['stop']}: {j['n_anh']}/{j['n']} ảnh -> {j['path']}"
        if j["da_co"]:
            line += "  (đã có: KHÔNG ghi đè)"
        else:
            n_new += 1
        if point_names:
            from m28core import collect
            with open(j["path"], "rb") as f:
                st = collect.analyze(f.read(), point_names)
            line += f" · ảnh có nhãn {st['n_face']} · mặt đủ {len(point_names)} điểm {st['n_full']}"
        print(line)
        for w in j["canh_bao"]:
            print(f"    cảnh báo: {w}")
        if j["suy_ra"]:
            print("    ghi chú: frame suy ra từ số frame cộng dồn (.txt cũ không có trường frames)")
    print(f"Xong: ghi mới {n_new} file job, giữ nguyên {len(res['jobs']) - n_new} file đã có. File job chỉ để đọc/đo, không nhập lại vào CVAT.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
