"""CVAT GIẢ (chỉ để test, KHÔNG phải cvat-sdk thật). Giữ trạng thái "server" trong bộ nhớ; có M28_FAKE_CVAT_STATE=<file json> thì
đọc/ghi trạng thái vào file đó (dùng xuyên tiến trình cho e2e). Ghi lại MỌI lời gọi (tên, tham số) để test kiểm không có lời gọi
nào chạm task không có prefix demo- và để so với chữ ký của cvat-sdk thật (tests/test_push.py::test_signatures_match_real_sdk).

Giả lỗi theo lệnh bằng biến môi trường M28_FAKE_CVAT_CONTROL (JSON) hoặc cvat_sdk.CONTROL.update(...):
  connect_fail: true            make_client ném lỗi không kết nối được (tên lớp MaxRetryError như urllib3)
  auth_fail: true               mọi lời gọi sau đăng nhập trả 401
  version: "2.70.0"             bản server báo về (mặc định 2.77.0)
  import_fail_times: N          import_annotations ném lỗi 500 N lần đầu (không lưu gì)
  frames_by_name: true          server xếp frame theo tên file thay vì theo job_file_mapping (để thử ghép id ảnh theo frame thật)
  drop_point: true              xuất ra thiếu một điểm ở skeleton đầu tiên
  project_missing_sublabels: N  project tạo ra thiếu N sublabel
  tasks_without_project: true   task mới không gắn project
  hang: N                       make_client treo N giây (true = 60) để thử timeout của "Thử kết nối" (tiến trình con bị kill)
  username: "ten"               tên người dùng retrieve_current_user() trả về (mặc định "m28-fake-user")
  label_reject: true            projects.create ném 400 có body (CVAT từ chối định nghĩa skeleton)
  remove_fail: true             Task.remove ném 500 (không xoá được task)
  sublabel_order_shuffle: true  project tạo ra có sublabel đảo ngược thứ tự (để thử nhánh "thứ tự lệch")
  svg_label_ids: true           project tạo ra có sublabel id và svg đổi data-label-name thành data-label-id như server thật
  export_fail: true             Task.export_dataset ném 500 (không ghi file zip nào) để thử collect --overwrite giữ nguyên bản cũ
Job có `type` (mặc định "annotation" như server thật; test đặt "ground_truth" bằng khoá `type` trong bản ghi job của trạng thái). Đổi
`state` của job (ví dụ "completed") cũng sửa thẳng bản ghi job trong trạng thái.
Cho tool/cvat_smoke.py: projects.retrieve(id) (404 nếu không có), Project.get_tasks(), Project.remove() (xoá luôn task của project như server
thật), Project.fetch(); xuất nhãn ghi width/height thật của ảnh PNG đã tải lên (không đọc được thì 512).
Thuộc tính M28_FAKE_CVAT = True đánh dấu gói giả: tool/cai_dat_thu.py bỏ qua tiền kiểm HTTP /api/server/about (không có server HTTP);
CVAT thật không có thuộc tính này nên luôn qua tiền kiểm.
Giả định về hành vi server bám mã nguồn CVAT v2.77.0 (job_file_mapping: frame xếp theo thứ tự mapping, sorting_method phải mặc định).
"""
import copy
import datetime
import functools
import json
import os
import time
import zipfile
import xml.etree.ElementTree as ET

from . import exceptions  # noqa: F401
from .api_client.exceptions import ApiException
from .core.proxies.tasks import ResourceType  # noqa: F401

M28_FAKE_CVAT = True
STATE_ENV, CONTROL_ENV = "M28_FAKE_CVAT_STATE", "M28_FAKE_CVAT_CONTROL"
CONTROL = {}
_MEM = {}
VERSION = "2.77.0"


class MaxRetryError(Exception):
    """Tên lớp trùng urllib3.exceptions.MaxRetryError để cvat_io.translate_error nhận ra."""


def _control():
    c = dict(CONTROL)
    if os.environ.get(CONTROL_ENV):
        c.update(json.loads(os.environ[CONTROL_ENV]))
    return c


def _blank():
    return dict(next_project=1, next_task=1, next_job=100, projects=[], tasks=[], calls=[], counters={})


def load():
    path = os.environ.get(STATE_ENV)
    if path:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return _blank()
    if not _MEM:
        _MEM.update(_blank())
    return _MEM


def save(st):
    path = os.environ.get(STATE_ENV)
    if path:
        tmp = path + f".tmp{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, default=str)
        os.replace(tmp, path)


def reset():
    _MEM.clear()
    CONTROL.clear()
    path = os.environ.get(STATE_ENV)
    if path and os.path.exists(path):
        os.remove(path)


def calls():
    return load()["calls"]


def _log(method, *args, **kwargs):
    st = load()
    st["calls"].append(dict(m=method, args=[str(a) if not isinstance(a, (int, float, bool, type(None), str, list, dict, tuple)) else a for a in args],
                            kwargs={k: (v if isinstance(v, (int, float, bool, type(None), str, list, dict, tuple)) else str(v))
                                    for k, v in kwargs.items()}))
    save(st)


def logged(name):
    """Ghi lời gọi NGUYÊN VĂN (tham số như người gọi viết) trước khi chạy, để so với chữ ký của cvat-sdk thật."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, *a, **kw):
            _log(name, *a, **kw)
            return fn(self, *a, **kw)
        return wrapper
    return deco


def _check_auth(client):
    if _control().get("auth_fail"):
        raise ApiException(status=401, reason="Unauthorized")
    if not client._token:
        raise ApiException(status=401, reason="Unauthorized")


def _png_size(rec, name):
    """(rộng, cao) đọc từ IHDR của file PNG đã tải lên task; không đọc được (file giả b'x') thì 512x512."""
    import struct
    for f in rec.get("files", []):
        if os.path.basename(f) == name:
            try:
                with open(f, "rb") as fh:
                    head = fh.read(24)
                if head[:8] == b"\x89PNG\r\n\x1a\n":
                    return struct.unpack(">II", head[16:24])
            except OSError:
                pass
    return 512, 512


class _V(str):
    pass


class Client:
    def __init__(self, url, token=None):
        self.url, self._token, self._org = url, token, None

    @property
    def organization_slug(self):
        return self._org

    @organization_slug.setter
    def organization_slug(self, value):
        _log("Client.organization_slug", value)
        self._org = value

    @logged("Client.get_server_version")
    def get_server_version(self):
        return _V(_control().get("version", VERSION))

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    @property
    def projects(self):
        return ProjectsRepo(self)

    @property
    def users(self):
        return UsersRepo(self)

    @property
    def tasks(self):
        return TasksRepo(self)


def make_client(host, *, port=None, credentials=None, access_token=None):
    _log("make_client", host, port=port, credentials=None if credentials is None else "<redacted>",
         access_token=None if access_token is None else "<redacted>")
    c = _control()
    if c.get("hang"):
        time.sleep(60 if c["hang"] is True else float(c["hang"]))
    if c.get("connect_fail"):
        raise MaxRetryError(f"HTTPConnectionPool(host='{host}'): Max retries exceeded (NewConnectionError)")
    return Client(host.rstrip("/"), access_token)


class _Model:
    def __init__(self, d):
        self.__dict__.update(d)

    def __getitem__(self, k):
        return self.__dict__[k]


class Project:
    def __init__(self, client, rec):
        self._c, self._rec = client, rec
        self.id, self.name = rec["id"], rec["name"]

    @logged("Project.get_labels")
    def get_labels(self):
        return copy.deepcopy(self._rec["labels"])

    @logged("Project.get_tasks")
    def get_tasks(self):
        return [Task(self._c, t) for t in load()["tasks"] if t["project_id"] == self.id]

    @logged("Project.fetch")
    def fetch(self):
        return self

    @logged("Project.remove")
    def remove(self):
        st = load()
        if not any(p["id"] == self.id for p in st["projects"]):
            raise ApiException(status=404, reason="Not Found")
        st["projects"] = [p for p in st["projects"] if p["id"] != self.id]
        st["tasks"] = [t for t in st["tasks"] if t["project_id"] != self.id]          # server thật xoá luôn task của project
        save(st)


class UsersRepo:
    @logged("users.retrieve_current_user")
    def retrieve_current_user(self):
        _check_auth(self._c)
        return _Model(dict(id=1, username=_control().get("username", "m28-fake-user")))

    def __init__(self, client):
        self._c = client


class ProjectsRepo:
    def __init__(self, client):
        self._c = client

    @logged("projects.list")
    def list(self, *, return_json=False, **kwargs):
        _check_auth(self._c)
        return [Project(self._c, p) for p in load()["projects"]]

    @logged("projects.retrieve")
    def retrieve(self, obj_id):
        _check_auth(self._c)
        for p in load()["projects"]:
            if p["id"] == obj_id:
                return Project(self._c, p)
        raise ApiException(status=404, reason="Not Found")

    @logged("projects.create")
    def create(self, spec):
        _check_auth(self._c)
        c = _control()
        if c.get("label_reject"):
            raise ApiException(status=400, reason="Bad Request", http_resp=_Model(dict(
                status=400, reason="Bad Request", data="label skeleton bị từ chối (giả)")))
        st = load()
        labels = []
        for lb in spec.get("labels", []):
            lb = copy.deepcopy(lb)
            miss = int(c.get("project_missing_sublabels", 0))
            if miss and lb.get("sublabels"):
                lb["sublabels"] = lb["sublabels"][:-miss]
            if c.get("sublabel_order_shuffle") and lb.get("sublabels"):
                lb["sublabels"].reverse()
            for s in lb.get("sublabels", []):
                s.setdefault("has_parent", True)
            if c.get("svg_label_ids") and lb.get("sublabels"):
                for i, s in enumerate(lb["sublabels"]):
                    s["id"] = 1000 + st["next_project"] * 100 + i
                    lb["svg"] = lb["svg"].replace(f'data-label-name="{s["name"]}"', f'data-label-id="{s["id"]}"')
            labels.append(lb)
        rec = dict(id=st["next_project"], name=spec["name"], labels=labels)
        st["next_project"] += 1
        st["projects"].append(rec)
        save(st)
        return Project(self._c, rec)


class Job:
    def __init__(self, rec):
        self.id, self.start_frame, self.stop_frame = rec["id"], rec["start_frame"], rec["stop_frame"]
        self.stage, self.state = rec["stage"], rec["state"]
        self.type = rec.get("type", "annotation")


class Task:
    def __init__(self, client, rec):
        self._c, self.id = client, rec["id"]
        self.name, self.project_id, self.size = rec["name"], rec["project_id"], len(rec["frames"])
        self.created_date = datetime.datetime.fromisoformat(rec["created"])

    def _rec(self):
        for t in load()["tasks"]:
            if t["id"] == self.id:
                return t
        raise ApiException(status=404, reason="Not Found")

    @logged("Task.get_jobs")
    def get_jobs(self):
        rec = self._rec()
        if os.environ.get('M28_DEMO_AUTO_JOBS') == '1':       # demo công khai: job tự được 'người gán' sửa xong theo thời gian
            age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(rec['created'])).total_seconds()
            out = []
            for i, j in enumerate(rec['jobs']):
                j = dict(j)
                if age >= 12 + 6 * i:
                    j['state'], j['stage'] = 'completed', 'acceptance'
                elif age >= 3 + i:
                    j['state'] = 'in progress'
                out.append(Job(j))
            return out
        return [Job(j) for j in rec["jobs"]]

    @logged("Task.get_frames_info")
    def get_frames_info(self):
        return [_Model(dict(name=n, width=512, height=512)) for n in self._rec()["frames"]]

    @logged("Task.get_annotations")
    def get_annotations(self):
        ann = self._rec()["annotations"]
        return _Model(dict(version=0, tags=[], tracks=[], shapes=[dict(label="face50", frame=i) for i in ann.get("frames", [])] if ann else []))

    @logged("Task.fetch")
    def fetch(self):
        return self

    @logged("Task.remove")
    def remove(self):
        if _control().get("remove_fail"):
            raise ApiException(status=500, reason="Server Error", http_resp=_Model(dict(status=500, reason="Server Error",
                                                                                         data="không xoá được (giả)")))
        st = load()
        if not any(t["id"] == self.id for t in st["tasks"]):
            raise ApiException(status=404, reason="Not Found")
        st["tasks"] = [t for t in st["tasks"] if t["id"] != self.id]
        save(st)

    @logged("Task.import_annotations")
    def import_annotations(self, format_name, filename, *, conv_mask_to_poly=None, import_mode=None, status_check_period=None, pbar=None):
        st = load()
        c = _control()
        if format_name != "CVAT 1.1":
            raise ApiException(status=400, reason="Bad Request", http_resp=_Model(dict(status=400, reason="Bad Request",
                                                                                        data=f"unknown format {format_name}")))
        n = st["counters"].get("import_fail", 0)
        if n < int(c.get("import_fail_times", 0)):
            st["counters"]["import_fail"] = n + 1
            save(st)
            raise ApiException(status=500, reason="Server Error", http_resp=_Model(dict(status=500, reason="Server Error",
                                                                                         data="import crashed (giả)")))
        rec = next(t for t in st["tasks"] if t["id"] == self.id)
        root = ET.parse(filename).getroot()
        out = {}
        for im in root.iter("image"):
            name = im.get("name")
            if name not in rec["frames"]:
                raise ApiException(status=400, reason="Bad Request", http_resp=_Model(dict(
                    status=400, reason="Bad Request", data=f"image {name} not in task")))
            sks = []
            for sk in im.findall("skeleton"):
                pts = []
                for p in sk.findall("points"):
                    if p.get("occluded") is None or p.get("outside") is None:
                        raise ApiException(status=400, reason="Bad Request", http_resp=_Model(dict(
                            status=400, reason="Bad Request", data="points need occluded and outside")))
                    pts.append(dict(label=p.get("label"), xy=p.get("points"),
                                    low_conf=next((a.text for a in p.findall("attribute") if a.get("name") == "low_conf"), None)))
                sks.append(dict(label=sk.get("label"), points=pts))
            out[name] = sks
        rec["annotations"] = dict(by_name=out, frames=[rec["frames"].index(n) for n in out], xml_ids={im.get("name"): im.get("id") for im in root.iter("image")})
        save(st)

    @logged("Task.export_dataset")
    def export_dataset(self, format_name, filename, *, pbar=None, status_check_period=None, include_images=True, location=None,
                       cloud_storage_id=None):
        rec = self._rec()
        if format_name != "CVAT for images 1.1":
            raise ApiException(status=400, reason="Bad Request")
        if _control().get("export_fail"):
            raise ApiException(status=500, reason="Server Error", http_resp=_Model(dict(status=500, reason="Server Error",
                                                                                         data="export crashed (giả)")))
        ann = (rec["annotations"] or {}).get("by_name", {})
        drop = bool(_control().get("drop_point"))
        out = ['<?xml version="1.0" encoding="utf-8"?>', "<annotations>", "  <version>1.1</version>"]
        for i, name in enumerate(rec["frames"]):
            w, h = _png_size(rec, name)
            out.append(f'  <image id="{i}" name="{name}" width="{w}" height="{h}">')
            for sk in ann.get(name, []):
                out.append(f'    <skeleton label="{sk["label"]}" source="file" occluded="0" z_order="0">')
                for j, p in enumerate(sk["points"]):
                    if drop and j == 0:
                        drop = False
                        continue
                    out.append(f'      <points label="{p["label"]}" source="file" outside="0" occluded="0" keyframe="1" '
                               f'points="{p["xy"]}" z_order="0">')
                    if p["low_conf"] is not None:
                        out.append(f'        <attribute name="low_conf">{p["low_conf"]}</attribute>')
                    out.append("      </points>")
                out.append("    </skeleton>")
            out.append("  </image>")
        out.append("</annotations>")
        with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("annotations.xml", "\n".join(out))
        return filename


class TasksRepo:
    def __init__(self, client):
        self._c = client

    @logged("tasks.list")
    def list(self, *, return_json=False, **kwargs):
        _check_auth(self._c)
        return [Task(self._c, t) for t in load()["tasks"]]

    @logged("tasks.retrieve")
    def retrieve(self, obj_id):
        _check_auth(self._c)
        for t in load()["tasks"]:
            if t["id"] == obj_id:
                return Task(self._c, t)
        raise ApiException(status=404, reason="Not Found")

    @logged("tasks.remove_by_ids")
    def remove_by_ids(self, task_ids):
        st = load()
        st["tasks"] = [t for t in st["tasks"] if t["id"] not in set(task_ids)]
        save(st)

    @logged("tasks.create_from_data")
    def create_from_data(self, spec, resources, *, resource_type=ResourceType.LOCAL, data_params=None, annotation_path="",
                         annotation_format="CVAT XML 1.1", status_check_period=None, pbar=None):
        _check_auth(self._c)
        if spec.get("labels"):
            raise ApiException(status=400, reason="Bad Request")         # task trong project không được có labels (như SDK thật)
        params = data_params or {}
        names = [os.path.basename(str(r)) for r in resources]
        if len(set(names)) != len(names):
            raise ApiException(status=400, reason="Bad Request")
        if any(k in params for k in ("sorting_method", "segment_size")):
            raise ApiException(status=400, reason="job_file_mapping cannot be used with sorting_method")
        mapping = params.get("job_file_mapping")
        if mapping is not None:
            flat = [n for g in mapping for n in g]
            if sorted(flat) != sorted(names):
                raise ApiException(status=400, reason="Bad Request", http_resp=_Model(dict(
                    status=400, reason="Bad Request", data="job_file_mapping files must be a subset of the input files")))
            frames = sorted(flat) if _control().get("frames_by_name") else flat
            sizes = [len(g) for g in mapping]
        else:
            frames, sizes = sorted(names), [len(names)]
        st = load()
        tid = st["next_task"]
        st["next_task"] += 1
        jobs, start = [], 0
        for n in sizes:
            jobs.append(dict(id=st["next_job"], start_frame=start, stop_frame=start + n - 1, stage="annotation", state="new"))
            st["next_job"] += 1
            start += n
        rec = dict(id=tid, name=spec["name"], project_id=None if _control().get("tasks_without_project") else spec.get("project_id"),
                   frames=frames, jobs=jobs, annotations=None, files=[str(r) for r in resources],
                   created=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
        st["tasks"].append(rec)
        save(st)
        return Task(self._c, rec)


__all__ = ["make_client", "Client", "reset", "calls", "CONTROL"]
