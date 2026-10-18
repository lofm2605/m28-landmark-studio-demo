import argparse
import json
import os
import re
import socket
import sys

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
from m28core import cvat_io  # noqa: E402

PREFIX = "CVAT_JOBS: "
PREFIX_LOI = "CVAT_JOBS_LOI: "
RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")


def _out(prefix, obj):
    print(prefix + json.dumps(obj, ensure_ascii=False, separators=(",", ":")), flush=True)


def _txt(v):
    return str(getattr(v, "value", v))


def jobs_of(task):
    out = []
    for j in sorted(task.get_jobs(), key=lambda j: j.start_frame):
        out.append(dict(id=j.id, n=j.stop_frame - j.start_frame + 1, stage=_txt(j.stage), state=_txt(j.state), start=j.start_frame,
                        stop=j.stop_frame, type=_txt(getattr(j, "type", None) or "annotation")))
    return out


def reopen_jobs(task):
    """Fix again (trang Sửa trên CVAT): đặt mọi job annotation đang "completed" của task về "in progress" để sửa tiếp; trả danh sách id đã mở lại.
    Chỉ gọi sau khi đã kiểm task theo id + tên trong push.json; không đụng job ground_truth, không đổi stage hay người được giao."""
    done = []
    for j in task.get_jobs():
        if _txt(getattr(j, "type", None) or "annotation") != "annotation" or _txt(j.state) != "completed":
            continue
        j.update({"state": "in progress"})
        done.append(j.id)
    return done


def read_push(run_dir):
    try:
        with open(os.path.join(run_dir, "push.json"), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def main(argv=None, environ=None):
    p = argparse.ArgumentParser(prog="cvat_jobs")
    p.add_argument("--run", required=True)
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--reopen", action="store_true", help="mở lại các job đã completed (state -> in progress) rồi đọc lại trạng thái")
    args = p.parse_args(argv)
    if not RUN_RE.fullmatch(args.run):
        _out(PREFIX_LOI, dict(loi=f"Tên lượt {args.run!r} không hợp lệ."))
        return 2
    ps = read_push(os.path.join("runs", args.run))
    tid = (ps or {}).get("task_id")
    name = (ps or {}).get("task")
    if (ps or {}).get("trang_thai") != "xong" or not isinstance(tid, int) or isinstance(tid, bool) or not isinstance(name, str):
        _out(PREFIX_LOI, dict(loi=f"Lượt {args.run} chưa đẩy xong lên CVAT (push.json không có task_id)."))
        return 2
    env = cvat_io.read_env(environ)
    why = cvat_io.env_problem(env)
    if why:
        _out(PREFIX_LOI, dict(loi=why))
        return 2
    socket.setdefaulttimeout(max(5.0, min(120.0, args.timeout)))
    try:
        client = cvat_io.connect(env)
        with client:
            task = client.tasks.retrieve(tid)
            if task.name != name:
                _out(PREFIX_LOI, dict(loi=f"Task id {tid} trên CVAT tên là {task.name!r}, không phải {name!r}: task đã bị xoá hoặc thay."))
                return 2
            reopened = reopen_jobs(task) if args.reopen else []
            if reopened:
                task = client.tasks.retrieve(tid)                # đọc lại sau khi đổi trạng thái
            jobs = jobs_of(task)
    except SystemExit as e:
        _out(PREFIX_LOI, dict(loi=cvat_io.scrub(str(e.code), env["token"])[:300]))
        return 2
    except Exception as e:
        msg = cvat_io.translate_error(e, env, "mở lại job" if args.reopen else "đọc trạng thái job") or f"Không đọc được trạng thái job: {type(e).__name__}: {cvat_io.scrub(e, env['token'])[:200]}"
        _out(PREFIX_LOI, dict(loi=msg))
        return 2
    _out(PREFIX, dict(task_id=tid, task=name, jobs=jobs, reopened=reopened))
    return 0


if __name__ == "__main__":
    sys.exit(main())
