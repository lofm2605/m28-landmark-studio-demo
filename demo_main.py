"""Khởi động bản demo công khai của M28 Landmark Studio (tool thật + đợt mẫu 10 mặt).

Hai chế độ CVAT (tự chọn):
  - THẬT: có biến môi trường CVAT_ACCESS_TOKEN (và CVAT_URL, mặc định https://app.cvat.ai): tool đẩy / thu nhãn trên CVAT đó bằng cvat-sdk thật, trong một
    project riêng (M28_DEMO_CVAT_PROJECT, mặc định m28-demo). Người xem không sửa được trên CVAT, nên một luồng nền "người gán mô phỏng" tự đánh dấu job xong
    vài giây sau khi tạo task, và xoá task demo cũ để không vượt hạn mức gói miễn phí. Dùng một tài khoản CVAT RIÊNG cho demo, không dùng tài khoản chính.
  - MÔ PHỎNG: không có token (hoặc M28_DEMO_CVAT=fake): gói cvat_sdk giả (fake_cvat/) nằm trong chính tiến trình, không có kết nối mạng nào.

Còn lại: chép đợt mẫu (seed/NAP_001) vào work/runs/NAP_001; có người thao tác rồi im lặng quá IDLE_S giây thì chạy lại tiến trình (đặt lại sạch,
giải phóng bộ nhớ, dọn task trên CVAT)."""
import datetime
import json
import os
import shutil
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")
RUN = os.path.join(WORK, "runs", "NAP_001")          # đợt mở sẵn; các đợt mẫu khác mở ở Switch batch
INITIAL = None                                  # dấu vân tay "chưa ai thao tác", chụp sau khi trang đã lên (set_initial)
STATE = os.path.join(WORK, "_cvat_state.json")
FAKE_DIR = os.path.join(HERE, "fake_cvat")
IDLE_S = int(os.environ.get("M28_DEMO_IDLE_S", "300"))
TASK_PREFIX = "Lam-NAP_"                                   # tên task do đợt mẫu tạo ra: <người>-<đợt>
TASK_TTL_S = int(os.environ.get("M28_DEMO_TASK_TTL_S", "1500"))
PROJECT = os.environ.get("M28_DEMO_CVAT_PROJECT", "m28-demo")


def real_cvat():
    return bool(os.environ.get("CVAT_ACCESS_TOKEN")) and os.environ.get("M28_DEMO_CVAT", "auto") != "fake"


def _runs():
    return sorted(d for d in os.listdir(os.path.join(HERE, "seed")) if os.path.isdir(os.path.join(HERE, "seed", d)))


def fresh():
    global INITIAL
    os.chdir(HERE)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(os.path.join(WORK, "runs"), exist_ok=True)
    for name in _runs():
        rd = os.path.join(WORK, "runs", name)
        shutil.copytree(os.path.join(HERE, "seed", name), rd)
        meta = os.path.join(rd, "crop", "meta.json")
        with open(meta, encoding="utf-8") as f:
            text = f.read().replace("@RUN@", rd)
        with open(meta, "w", encoding="utf-8") as f:
            f.write(text)
    shutil.copytree(os.path.join(HERE, "config"), os.path.join(WORK, "config"))
    with open(os.path.join(WORK, "config", "pipeline.json"), "w", encoding="utf-8") as f:
        json.dump({"project": PROJECT, "prefix": "", "cvat_version": os.environ.get("M28_DEMO_CVAT_VERSION", "2.79.0" if real_cvat() else "2.77.0"),
                   "job_size": 0}, f, indent=1)
    os.makedirs(os.path.join(WORK, "_cfg"), exist_ok=True)          # nằm trong thư mục chạy: tool từ chối lưu token/cài đặt vào đây
    INITIAL = None


def set_initial():
    global INITIAL
    INITIAL = snapshot()


def snapshot():
    """Dấu vân tay của work/ (đường dẫn + cỡ file), bỏ _tmp (ảnh nhỏ tự sinh khi xem) và thư mục cấu hình: khác lúc mới dựng nghĩa là có người đã thao tác."""
    out = {}
    for root, dirs, files in os.walk(WORK):
        dirs[:] = [d for d in dirs if d not in ("_tmp", "_cfg", "__pycache__")]
        for n in files:
            if n in (".dang_chay", "_cvat_state.json"):
                continue
            p = os.path.join(root, n)
            try:
                out[os.path.relpath(p, WORK)] = os.path.getsize(p)
            except OSError:
                pass
    return out


def latest_mtime():
    t = 0.0
    for root, _d, files in os.walk(WORK):
        for n in files:
            try:
                t = max(t, os.path.getmtime(os.path.join(root, n)))
            except OSError:
                pass
    return t


def dirty():
    return INITIAL is not None and snapshot() != INITIAL


# ---------- CVAT thật: người gán mô phỏng và dọn task ----------
def _client():
    from m28core import cvat_io
    env = cvat_io.read_env()
    return cvat_io.connect(env), env


def _age(task):
    return (datetime.datetime.now(datetime.timezone.utc) - task.created_date).total_seconds()


def cleanup_cvat(older_than=None):
    """Xoá task demo (tên bắt đầu bằng TASK_PREFIX) cũ hơn `older_than` giây (None = mọi task demo). Chỉ đụng task có tiền tố đó."""
    from m28core import cvat_io
    client, env = _client()
    n = 0
    try:
        for t in client.tasks.list():
            if t.name.startswith(TASK_PREFIX) and (older_than is None or _age(t) > older_than):
                t.remove()
                n += 1
    except Exception as e:
        print("Demo dọn task CVAT:", type(e).__name__, cvat_io.scrub(e, env["token"])[:200], flush=True)
    return n


def annotator():
    """Chỉ làm việc khi đã có người đẩy task (push.json): sau vài giây đặt job "in progress", rồi "completed" như bấm Finish the job; xoá task quá hạn."""
    from m28core import cvat_io
    client, env, last_clean = None, None, 0.0
    while True:
        time.sleep(5)
        try:
            if not any(os.path.exists(os.path.join(WORK, "runs", r, "push.json")) for r in _runs()):
                continue
            if client is None:
                client, env = _client()
            for t in client.tasks.list():
                if not t.name.startswith(TASK_PREFIX):
                    continue
                age = _age(t)
                if age > TASK_TTL_S:
                    t.remove()
                    continue
                for i, j in enumerate(sorted(t.get_jobs(), key=lambda j: j.start_frame)):
                    state = str(getattr(j.state, "value", j.state))
                    if state == "completed":
                        continue
                    if age >= 12 + 6 * i:
                        j.update({"state": "completed", "stage": "acceptance"})
                    elif age >= 3 + i and state == "new":
                        j.update({"state": "in progress"})
        except Exception as e:
            print("Demo người gán mô phỏng:", type(e).__name__, cvat_io.scrub(e, (env or {}).get("token"))[:200], flush=True)
            client = None


def watchdog():
    while True:
        time.sleep(15)
        try:
            if dirty() and time.time() - latest_mtime() > IDLE_S:
                print("Demo: không ai thao tác, đặt lại đợt mẫu.", flush=True)
                if real_cvat():
                    cleanup_cvat(None)
                os.chdir(HERE)                                              # thư mục work sắp bị xoá: đừng đứng trong nó
                os.execv(sys.executable, [sys.executable, os.path.join(HERE, "demo_main.py")])       # chạy lại chính tiến trình này: fresh() chạy từ đầu
        except Exception as e:                                               # luồng nền không được chết vì lỗi lặt vặt
            print("Demo watchdog:", e, flush=True)


def main():
    fresh()
    env = os.environ
    real = real_cvat()
    env["M28_PUBLIC_DEMO"] = "1"
    env["M28_NO_BROWSER"] = "1"
    env["M28_CONFIG_DIR"] = os.path.join(WORK, "_cfg")
    env["GRADIO_SERVER_PORT"] = str(env.get("PORT") or env.get("GRADIO_SERVER_PORT") or 7860)
    env["PYTHONUTF8"] = "1"
    sys.path.insert(0, os.path.join(HERE, "tool"))
    if real:
        env["M28_DEMO_CVAT_MODE"] = "real"
        env.setdefault("CVAT_URL", "https://app.cvat.ai")
        print(f"Demo: CVAT THẬT ({env['CVAT_URL']}), project {PROJECT}.", flush=True)
    else:
        env["M28_DEMO_CVAT_MODE"] = "fake"
        env["M28_DEMO_AUTO_JOBS"] = "1"
        env["M28_FAKE_CVAT_STATE"] = STATE
        env["CVAT_URL"] = "https://cvat.mo-phong.demo"                      # tên giả: không phân giải, không có kết nối mạng nào
        env["CVAT_ACCESS_TOKEN"] = "demo-token"
        env["M28_FAKE_CVAT_CONTROL"] = json.dumps({"username": "nguoi-gan-mo-phong"})
        env["PYTHONPATH"] = FAKE_DIR + os.pathsep + env.get("PYTHONPATH", "")        # cvat_sdk giả đứng trước cho cả tiến trình con
        sys.path.insert(0, FAKE_DIR)
        print("Demo: CVAT MÔ PHỎNG (không có kết nối mạng tới CVAT).", flush=True)
    os.chdir(WORK)
    threading.Thread(target=watchdog, daemon=True).start()
    if real:
        threading.Thread(target=annotator, daemon=True).start()
        threading.Thread(target=lambda: cleanup_cvat(600), daemon=True).start()      # dọn task còn sót của lần chạy trước
    import gradio.networking as gn                       # CPU rất nhỏ khởi động chậm: Gradio chỉ chờ vài giây xem localhost có mở chưa, nên cho chờ lâu hơn
    ok = gn.url_ok

    def url_ok_cham(url):
        for _ in range(40):
            if ok(url):
                threading.Timer(20, set_initial).start()          # trang đã lên: vài giây sau chụp dấu vân tay "sạch"
                return True
            time.sleep(3)
        return False
    gn.url_ok = url_ok_cham
    import review_app
    sys.exit(review_app.main(["runs/NAP_001", "Lam"]))


if __name__ == "__main__":
    main()
