"""m28 — pipeline nhãn nháp landmark khuôn mặt: prepare → review → push → collect (all = prepare → review → push).

    python tool\\m28.py prepare --run R1610 --list data\\r_list_1610.csv --images data\\frames --box auto
    python tool\\m28.py review  --run R1610 --review ui --reviewer P5
    python tool\\m28.py push    --run R1610 --reviewer P2 [--task P2-R1610] [--dry-run]
    python tool\\m28.py push    --run R1610 --resume            (lần push trước dừng sau khi đã tạo task: làm nốt trên đúng task đó)
    python tool\\m28.py push    --run R1610 --cleanup --confirm-name P2-R1610   (xoá ĐÚNG task trong push.json trên CVAT, không hoàn tác được)
    python tool\\m28.py collect --task P2-R1610
    python tool\\m28.py all     --run thuP1 --list data\\f5_list.csv --images data\\crops --box crop --review auto --reviewer P1

Công cụ đo (không nằm trong pipeline, cùng thư mục tool\\): make_config.py (sinh config + map + hoán vị gương), check_flip.py, flag_eval.py, eval50.py, check_drivface.py.
Ánh xạ 478 -> 50 là CHỌN ĐỈNH trực tiếp (config\\m28_config.json, mp_idx; xem QĐ-001..003 trong so-quyet-dinh.md).
--box crop: dùng ảnh đã cắt sẵn 512 (data\\crops) và hộp mặt từ cột x0,y0,x1,y1 của manifest.csv; --box auto: MediaPipe tự dò hộp trên ảnh gốc.
Mỗi bước ghi vào runs/<run>/<bước>/ và để lại done.txt khi xong thật; chạy lại thì bước đã xong được bỏ qua
(trừ khi tên bước nằm trong --force). Địa chỉ CVAT và token đọc từ CVAT_URL, CVAT_ACCESS_TOKEN (tuỳ chọn CVAT_ORG).
push chỉ tạo task MỚI <người>-<đợt> (QĐ-021; task demo-… cũ vẫn dùng được); collect chỉ xuất (--skip-export, --dry-run, nhiều --task, --reviewer). --cleanup xoá task đã đẩy rồi lượt đẩy lại được.
collect còn tách nhãn theo từng job mà push đã chia (offline, từ file cả task): raw\\<task>\\<task>_<người>_<DDMM>_job<id>.xml (+ .txt), mặc định bật cho task của tool:
    python tool\\m28.py collect --task P2-R1610 --reviewer P4                (cả task + file từng job)
    python tool\\m28.py collect --task P2-R1610 --reviewer P4 --no-per-job   (chỉ file cả task như trước)
    python tool\\m28.py collect --task P2-R1610 --reviewer P4 --job 105      (chỉ ghi file của job 105, nhiều --job được)
    python tool\\m28.py collect --task P2-R1610 --reviewer P4 --overwrite    (xuất lại nhãn mới nhất dù hôm nay đã collect; bản cũ vào raw\\_cu\\)
    python tool\\m28.py collect --task P2-R1610 --reviewer P4 --overwrite --no-per-job --require-completed
                                    (nút Merge jobs & Finish: còn job chưa completed thì không xuất gì, thoát mã 3)
File job chỉ để đọc/đo (eval50, QC), không nhập lại vào CVAT. Tách file đã xuất từ trước: python tool\\tach_job.py --xml raw\\<file>.xml
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m28core import steps  # noqa: E402

PREPARE = ["crop", "mediapipe", "map50", "flags", "autoqc", "overlays"]


def _log(args, name, status, t0):
    os.makedirs(os.path.join("runs", args.run), exist_ok=True)
    with open(os.path.join("runs", args.run, "log.txt"), "a", encoding="utf-8") as f:
        detail = steps._LOG_DETAIL.pop(name, "")      # chi tiết bước (ví dụ push: gan_tay co_nhap=a anh_trong=b)
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{name}\t{status}\t{time.time() - t0:.1f}s" + (f"\t{detail}" if detail else "") + "\n")


def run_step(name, args):
    t0 = time.time()
    out = os.path.join("runs", args.run, name)
    if os.path.exists(os.path.join(out, "done.txt")) and name not in args.force:
        print("bỏ qua", name)
        if name == "review":
            print("  (lượt này đã rà xong từ trước: muốn rà lại thì thêm --force review)")
        _log(args, name, "bo_qua", t0)
        return
    os.makedirs(out, exist_ok=True)
    status = "loi"
    try:
        ok = getattr(steps, name)(args, out)   # True chỉ khi bước xong thật; False thì hàm bước đã in lý do
        status = "xong" if ok else "dung"
    finally:
        _log(args, name, status, t0)
    if not ok:
        raise SystemExit(f"Dừng ở bước {name}: chưa xong nên không ghi done.txt (lý do in ở trên).")
    with open(os.path.join(out, "done.txt"), "w", encoding="utf-8") as f:
        f.write("ok")


def build_parser():
    p = argparse.ArgumentParser(prog="m28")
    p.add_argument("cmd", choices=["prepare", "review", "push", "collect", "all"])
    p.add_argument("--run", help="tên lượt chạy, ví dụ R1610 (collect không cần)")
    p.add_argument("--images", help="thư mục ảnh: data\\frames (khung gốc in-cabin), data\\crops (khi chỉ có gói: dùng chính ảnh cắt) hoặc ảnh khách")
    p.add_argument("--list", help="CSV có cột image, face_idx (như manifest.csv)")
    p.add_argument("--set", nargs="*", help="lọc theo cột set của manifest.csv")
    p.add_argument("--manifest", default=os.path.join("data", "manifest.csv"))
    p.add_argument("--box", choices=["crop", "auto"], default="auto",
                   help="auto: MediaPipe tự dò hộp mặt (chế độ chính cho in-cabin). crop: dùng ảnh đã cắt sẵn 512 (--images data\\crops) và lấy hộp mặt từ cột x0,y0,x1,y1 của "
                        "manifest.csv (cần --list hoặc --set)")
    p.add_argument("--config", default=os.path.join("config", "m28_config.json"))
    p.add_argument("--map", default=os.path.join("config", "map_mp50.json"))
    p.add_argument("--pipeline", default=os.path.join("config", "pipeline.json"))
    p.add_argument("--model", default="face_landmarker.task", help="mặc định ở thư mục chạy lệnh, không có thì tìm trong tool/")
    p.add_argument("--review", choices=["ui", "excel", "auto"], default="ui")
    p.add_argument("--reviewer", default="RA")
    p.add_argument("--review-file")
    p.add_argument("--task", action="append", default=[], help="push: tên task (một, mặc định <reviewer>-<run>); collect: nhiều task")
    p.add_argument("--tag")
    p.add_argument("--skip-export", action="store_true")
    p.add_argument("--force", nargs="*", default=[])
    p.add_argument("--resume", action="store_true", help="push: làm nốt phần còn lại (nhập nhãn, kiểm) trên đúng task_id trong push.json")
    p.add_argument("--cleanup", action="store_true",
                   help="push: xoá đúng task trong push.json trên CVAT (cần --confirm-name), đánh dấu task_deleted để đẩy lại được")
    p.add_argument("--confirm-name", help="push --cleanup: gõ lại đúng tên task sẽ xoá")
    p.add_argument("--dry-run", action="store_true",
                   help="push: chỉ ghi XML; collect: chỉ in danh sách job (kèm frame, loại và tên file job sẽ ghi); không ghi done.txt")
    p.add_argument("--per-job", action=argparse.BooleanOptionalAction, default=None, dest="per_job",
                   help="collect: tách nhãn theo từng job (file raw\\<task>\\<task>_<người>_<DDMM>_job<id>.xml). Mặc định tự động: bật cho task của tool (có trong runs\\*\\push.json hoặc demo-… cũ), tắt cho task khác; "
                        "--no-per-job chỉ giữ file cả task")
    p.add_argument("--job", action="append", type=int, default=None, metavar="ID",
                   help="collect: chỉ ghi file của job có id này (dùng nhiều lần được); file cả task vẫn xuất như cũ; tự bật tách job")
    p.add_argument("--overwrite", action="store_true",
                   help="collect: xuất lại dù raw\\<task>\\<task>_<người>_<DDMM>.xml hôm nay đã có (đã sửa thêm trên CVAT sau lần collect trước); xuất xong mới chuyển "
                        "bản cũ (.xml, .txt, file job) vào raw\\_cu\\, không xoá")
    p.add_argument("--require-completed", action="store_true", dest="require_completed",
                   help="collect: còn job chưa completed trên CVAT (chưa bấm Finish the job) thì không xuất gì, in danh sách job và thoát mã 3")
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)
    if args.cmd != "collect" and (args.per_job is not None or args.job or args.overwrite or args.require_completed):
        p.error("--per-job, --no-per-job, --job, --overwrite và --require-completed chỉ dùng với lệnh collect")
    if args.cmd == "collect":
        if not args.task:
            p.error("collect cần --task")
        if args.job and args.per_job is False:
            p.error("--job tự bật tách job nên không đi cùng --no-per-job")
        if (args.overwrite or args.require_completed) and args.skip_export:
            p.error("--overwrite và --require-completed cần CVAT nên không đi cùng --skip-export")
        if not steps.collect(args, None):
            raise SystemExit("collect chưa xong (lý do in ở trên).")
        return
    if not args.run:
        p.error("lệnh này cần --run")
    if (args.resume or args.cleanup or args.confirm_name) and args.cmd != "push":
        p.error("--resume, --cleanup và --confirm-name chỉ dùng với lệnh push")
    if args.resume and args.cleanup:
        p.error("--resume và --cleanup không đi cùng nhau")
    if args.confirm_name and not args.cleanup:
        p.error("--confirm-name chỉ dùng với --cleanup")
    if args.cmd == "push" and args.cleanup:
        steps.cleanup(args)               # không ghi done.txt: push --cleanup chỉ dọn task, lượt đẩy lại được sau đó
        return
    if args.cmd in ("prepare", "all"):
        stale = steps.stale_derived_steps(args)
        if stale:                                   # lượt chạy bằng định nghĩa 50 điểm cũ (hoặc config khác): tính lại các bước phụ thuộc tên điểm, giữ crop và MediaPipe
            print(f"Lượt {args.run} đã chạy map50 bằng config khác (ví dụ 50 điểm cũ version 2, trước QĐ-003): tính lại {', '.join(stale)} bằng config hiện tại (crop, mediapipe giữ nguyên).")
            args.force = sorted(set(args.force) | set(stale))
        for s in PREPARE:
            run_step(s, args)
    if args.cmd in ("review", "all"):
        run_step("review", args)
    if args.cmd in ("push", "all"):
        run_step("push", args)          # all dừng ở push; collect chạy riêng sau khi có người gán


if __name__ == "__main__":
    main()
