"""Nạp dữ liệu in-cabin (YawDD + DrivFace), chia tập, cắt ảnh và đóng gói (P1, giai đoạn 1 mới, QĐ-001).

Dựng gói dữ liệu in-cabin (phần cắt mặt dùng chung ở m28core/cat_mat.py). Ba lệnh con, chạy lần lượt hoặc gộp bằng `all`:

    scan   trích khung từ video YawDD / đọc ảnh DrivFace, dò mặt bằng MediaPipe, đo, ghi cache (chậm, chạy một lần)
    split  chia tập F/Tdev/Ttest/G/P/X/D theo người, ghi khung gốc + ảnh cắt + manifest.csv (nhanh, TẤT ĐỊNH: cùng cache
           + cùng seed ⇒ manifest giống hệt từng byte; không đọc video, không chạy MediaPipe)
    pack   gói zip để gửi đội (mỗi file <= 28 MiB; meta + các phần ảnh cắt)

    python tool\\inc_ingest.py all --yawdd "D:\\incab\\YawDD dataset" --drivface D:\\incab\\DrivFace --model face_landmarker.task --out data --seed 5
    python tool\\inc_ingest.py scan  --yawdd "D:\\incab\\YawDD dataset" --drivface D:\\incab\\DrivFace --model face_landmarker.task --out data
    python tool\\inc_ingest.py split --out data --seed 5
    python tool\\inc_ingest.py pack  --out data --parts data_parts

Đầu ra trong --out: cache\\ (khung ứng viên, candidates.csv, pts478.npz: chỉ người dựng gói giữ), frames\\<nguồn>\\<mã người>\\<tên>.jpg
(khung gốc), crops\\<file>.png (ảnh cắt 512 x 512), manifest.csv. KHÔNG commit gì trong đó (ảnh người lái xe là dữ liệu nhạy cảm).

--- YawDD: cách phân tích tên video ---
Thư mục cha quyết định camera: Dash = camera trên bảng điều khiển, Mirror = camera dưới gương chiếu hậu. Tên video:
    <số>-<Female|Male><NoGlasses|Glasses|SunGlasses>[Beard|moustache][-<Normal|Talking|Yawning|Talking&Yawning>].avi
(chấp nhận `.avi.avi`, dấu cách trước đuôi, hoa/thường lẫn lộn). Dash không có trạng thái trong tên (một video chứa cả lái xe thường,
nói và ngáp) nên `state` = dash. Video không khớp regex thì IN CẢNH BÁO và bỏ, không đoán.
Loại kính lấy từ tên, trừ 2 cặp tên sai so với Table1/Table2 (GLASSES_FIX: Mirror nam 5 và Dash nữ 11 là kính râm).
Mã người: yd_<F|M><số 3 chữ số>. Dash và Mirror CÙNG giới + CÙNG số ⇒ GỘP làm một người (tài liệu YawDD không khẳng định đó là hai
người khác nhau; gộp là phía an toàn của việc tách người, chỉ có thể thiệt độ đa dạng). Kính/không kính của cùng số là cùng người.

--- DrivFace ---
drivPoints.txt (cột fileName có dấu cách cuối, không có .jpg), mã người df_01..df_04 theo cột subject. readme.txt chỉ nói "2 nữ, 2 nam"
mà không nói người nào ⇒ gender = unknown; kính/râu cũng không ghi theo từng người ⇒ glasses = unknown.

--- Trích khung (scan) ---
Đọc video tuần tự bằng grab() (KHÔNG tin CAP_PROP_FRAME_COUNT, KHÔNG tua), chỉ retrieve() mỗi SAMPLE_STEP_S giây. Khung được ghi JPEG
(chất lượng JPEG_QUALITY) rồi ĐỌC LẠI trước khi dò mặt, để hộp mặt trong manifest đúng bằng hộp mà `m28.py prepare --box auto` tính ra
trên chính file khung. Loại: không thấy mặt, có điểm trong 478 điểm nằm ngoài khung ảnh, hộp mặt quá nhỏ (MIN_FACE_PX). Bỏ khung gần trùng:
giữ khung khi cách khung đã giữ >= MIN_GAP_S giây (DrivFace: DF_MIN_GAP_IMGS ảnh) VÀ dHash 64 bit vùng mặt khác >= DHASH_MIN_DIST bit.
Video talking/yawning/dash: ưu tiên xen kẽ khung miệng mở nhất (blendshape jawOpen) và khung trải đều theo thời gian.

--- Sáu cờ (0/1; ngưỡng cố định ở đầu file, hiệu chỉnh MỘT lần trên dữ liệu thật rồi ghi cứng, không tính theo phân vị lúc chạy) ---
  pose          YawDD: |yaw| >= POSE_YAW_DEG hoặc |pitch| >= POSE_PITCH_DEG (ước lượng từ ma trận biến đổi mặt của MediaPipe).
                DrivFace: label 1/3 (nhìn phải/trái theo nhãn của bộ). Không dùng yaw cho DrivFace vì camera đặt lệch trục
                (ảnh nhìn thẳng có yaw trung bình +10 độ, tối đa +27); yaw đo được tương quan 0,90 với góc `ang` của bộ.
  expression    jaw_open (blendshape jawOpen) >= EXPR_JAW_OPEN: miệng mở lớn (ngáp, nói to). Không gán theo nhãn video.
  illumination  vùng mặt tối (luma < LUMA_DARK), sáng gắt (luma > LUMA_BRIGHT hoặc bright_frac > BRIGHT_FRAC_MAX) hoặc tương phản
                thấp (contrast < CONTRAST_LOW).
  makeup        LUÔN 0: không ước lượng được trên bộ này (giữ cột cho khớp kế hoạch).
  occlusion     kính râm (từ tên video YawDD) = 1. Che miệng bằng tay khi ngáp chưa có cách ước lượng ổn định nên KHÔNG dùng.
  blur          phương sai Laplacian của vùng mặt (xám, chuẩn hoá về FACE_PX x FACE_PX) < BLUR_LAP_VAR[nguồn]
                (ngưỡng riêng cho YawDD và DrivFace vì độ phân giải gốc của mặt khác nhau).
Các cột đo thô đi cùng manifest (yaw, pitch, roll độ; jaw_open; luma, contrast, bright_frac; lap_var; gaze_label, gaze_ang của DrivFace;
pad_frac = phần viền xám của ảnh cắt) để ai cũng soát lại được cờ.
"""
import argparse
import csv
import datetime
import glob
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import zipfile
from collections import Counter, defaultdict

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_manifest as cm  # noqa: E402
from check_manifest import (DF_MIN_GAP_IMGS, FLAGS, INC_COLUMNS, MAX_PER_VIDEO, MIN_GAP_S)  # noqa: E402
from m28core import steps  # noqa: E402
from m28core.cat_mat import OUT, crop_geometry, square_crop  # noqa: E402

# ---------- hằng số trích khung ----------
SAMPLE_STEP_S = 1.0          # lấy một khung ứng viên mỗi chừng này giây
MAX_SAMPLES = 150            # tối đa số khung dò mặt mỗi video (video dài hơn thì dừng sau ngần này mẫu)
MAX_CAND_PER_VIDEO = 16      # tối đa số ứng viên giữ lại mỗi video
DEFAULT_FPS = 30.0           # khi file không báo fps hợp lệ
JPEG_QUALITY = 95
PNG_COMPRESSION = 6          # ảnh cắt PNG: mức 6 nhanh gấp ~8 lần mức 9 mà chỉ lớn hơn ~5% (đo ở README)
MIN_FACE_PX = 80             # cạnh dài hộp mặt (pixel khung gốc) nhỏ hơn thì loại
DHASH_MIN_DIST = 6           # video: khung chỉ được giữ nếu dHash (64 bit) khác khung đã giữ >= ngần này bit
DF_DHASH_MIN_DIST = 3        # DrivFace: ảnh liền nhau trong chuỗi vốn rất giống (trung vị 3 bit), nên ngưỡng thấp hơn
DASH_STATES = ('talking', 'yawning', 'talking_yawning', 'dash')   # video có miệng mở thật: ưu tiên khung jawOpen cao
SCAN_VERSION = 3             # tăng khi đổi cách đo, để bỏ cache cũ

# ---------- hằng số cờ (hiệu chỉnh 6/10/2026 trên YawDD + DrivFace, xem README) ----------
POSE_YAW_DEG = 32.0          # góc yaw tuyệt đối trong hệ camera (camera Mirror nằm lệch: mặt nhìn thẳng đã có yaw ~ +23 độ)
POSE_PITCH_DEG = 18.0
EXPR_JAW_OPEN = 0.40         # blendshape jawOpen >= 0,4: miệng mở lớn (ngáp thường > 0,5); 0,2 cho tới 35% mặt, quá nhiều
LUMA_DARK = 70.0             # độ sáng trung bình vùng mặt (0-255)
LUMA_BRIGHT = 170.0
BRIGHT_FRAC_MAX = 0.08       # tỉ lệ điểm cháy sáng (>= BRIGHT_LEVEL) trong vùng mặt
CONTRAST_LOW = 28.0          # độ lệch chuẩn độ sáng vùng mặt
BLUR_LAP_VAR = dict(yawdd=170.0, drivface=75.0)   # theo nguồn: mặt DrivFace nhỏ (~110 px) nên Laplacian thấp hơn hẳn mặt YawDD
FACE_PX = 128                # vùng mặt chuẩn hoá về cạnh này trước khi đo Laplacian
BRIGHT_LEVEL = 240           # điểm xám >= mức này tính là cháy sáng

# ---------- hằng số chia tập ----------
DF_SHARE = 0.20              # tỉ trọng DrivFace trong mỗi tập (4 tài xế, đừng để chiếm quá nhiều)
DASH_SHARE = 0.12            # tỉ trọng camera Dash trong phần YawDD
DF_POSE_SHARE = 0.30         # trong phần DrivFace của một tập, tối thiểu tỉ lệ ảnh pose=1 (hiếm, nguồn pose chính)
MAX_TRIES = 500
X_TRIES = 60
BALANCE_TRIES = 12           # chọn trong ngần này lần chia đạt luật lần cân bằng nhất (giới, Dash, kính râm, loại kính)
X_MAX_PER_PERSON = 6         # khối X: một người tối đa ngần này mặt trong cả 50 mặt (để X không toàn một vài người)
X_MAX_DF = 10                # khối X: tối đa ngần này ảnh DrivFace (một tài xế duy nhất trong nhóm B)

GLASSES_CODE = {'none': 0, 'glasses': 1, 'sunglasses': 2, 'unknown': 9}
YAWDD_RE = re.compile(
    r'^(?P<num>\d+)-(?P<gender>Female|Male)(?P<glasses>NoGlasses|SunGlasses|Glasses)(?P<hair>Beard|moustache)?'
    r'(?:-(?P<state>Normal|Talking&Yawning|Talking|Yawning))?\s*\.avi(?:\.avi)?$', re.I)
STATE_MAP = {'normal': 'normal', 'talking': 'talking', 'yawning': 'yawning', 'talking&yawning': 'talking_yawning'}
GLASSES_MAP = {'noglasses': 'none', 'glasses': 'glasses', 'sunglasses': 'sunglasses'}
CAMERA_DIRS = {'dash': 'dash', 'mirror': 'mirror'}
# Tên video ghi sai loại kính so với Table1.pdf / Table2.pdf (đối chiếu cả 349 video, 6/10/2026; xem bằng mắt thì đúng là kính râm):
GLASSES_FIX = {('mirror', 'M', 5): 'sunglasses',     # Mirror nam 5: tên NoGlasses, Table1 "Sun glasses" (3 video)
               ('dash', 'F', 11): 'sunglasses'}      # Dash nữ 11: tên Glasses, Table2 "Sun Glasses" (1 video)


# ======================================================================================================================
# Phân tích tên, liệt kê nguồn
# ======================================================================================================================
def parse_yawdd(rel_path):
    """rel_path: đường dẫn video tương đối so với thư mục YawDD (dùng '/'). Trả dict hoặc None nếu không khớp."""
    parts = rel_path.split('/')
    camera = CAMERA_DIRS.get(parts[0].strip().lower()) if len(parts) > 1 else None
    m = YAWDD_RE.match(parts[-1].strip() if parts[-1].strip().lower().endswith('.avi') else parts[-1])
    if not m or camera is None:
        return None
    if camera == 'mirror' and not m.group('state'):
        return None                                       # Mirror bắt buộc có trạng thái trong tên
    gender = 'F' if m.group('gender').lower() == 'female' else 'M'
    state = STATE_MAP[m.group('state').lower()] if m.group('state') else 'dash'
    num = int(m.group('num'))
    glasses = GLASSES_FIX.get((camera, gender, num), GLASSES_MAP[m.group('glasses').lower()])
    return dict(camera=camera, gender=gender, num=num, glasses=glasses, state=state, subject=f'yd_{gender}{num:03d}')


def list_yawdd(root):
    """(video hợp lệ, danh sách đường dẫn bị bỏ). Tìm đệ quy *.avi, không phân biệt hoa/thường."""
    vids, bad = [], []
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if '.avi' not in fn.lower():
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, '/')
            info = parse_yawdd(rel)
            if info is None:
                bad.append(rel)
                continue
            vids.append(dict(info, path=os.path.join(dirpath, fn), rel=rel))
    vids.sort(key=lambda v: v['rel'])
    bad.sort()
    return vids, bad


def read_drivface(root):
    """Danh sách ảnh DrivFace: dict(path, subject, imgnum, label, ang, face_box, name_in_txt, match)."""
    txt = os.path.join(root, 'drivPoints.txt')
    imgdir = os.path.join(root, 'imgs', 'DrivImages')
    out, stats = [], Counter()
    with open(txt, encoding='utf-8-sig', errors='replace', newline='') as f:
        for r in csv.DictReader(f):
            raw = r['fileName']
            for how, fn in (('raw+.jpg', raw + '.jpg'), ('strip+" .jpg"', raw.strip() + ' .jpg'), ('strip+.jpg', raw.strip() + '.jpg')):
                if os.path.exists(os.path.join(imgdir, fn)):
                    break
            else:
                stats['khong_thay_anh'] += 1
                continue
            stats[how] += 1
            out.append(dict(path=os.path.join(imgdir, fn), subject=f'df_{int(r["subject"]):02d}', imgnum=int(r['imgNum']),
                            label=int(r['label']), ang=float(r['ang']), file=fn))
    return out, stats


# ======================================================================================================================
# Dò mặt và đo
# ======================================================================================================================
def _mp_image(rgb):
    import mediapipe as mp
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))


def _jaw_open(blend):
    for c in blend:
        if getattr(c, 'category_name', None) == 'jawOpen':
            return float(c.score)
    return None


class FaceDetector:
    """Bọc landmarker: dùng lại steps.run_mp_padded (thêm viền xám khi không thấy) và cất thêm cho mặt lớn nhất
    ma trận biến đổi + blendshape jawOpen. `wrap(rgb)` đổi ảnh thành đầu vào của lm.detect (mặc định mp.Image; test truyền hàm khác)."""

    def __init__(self, lm, wrap=None):
        self.lm, self.wrap, self.extra = lm, wrap or _mp_image, None

    def _run(self, lm, rgb):
        res = lm.detect(self.wrap(rgb))
        self.extra = None
        if not res.face_landmarks:
            return None
        h, w = rgb.shape[:2]
        faces = [[[p.x * w, p.y * h] for p in face] for face in res.face_landmarks]
        i = max(range(len(faces)), key=lambda j: np.ptp(np.asarray(faces[j]), axis=0).prod())   # mặt lớn nhất, như steps.run_mp
        mats = getattr(res, 'facial_transformation_matrixes', None)
        blend = getattr(res, 'face_blendshapes', None)
        self.extra = dict(matrix=np.asarray(mats[i], float) if mats is not None and len(mats) > i else None,
                          jaw_open=_jaw_open(blend[i]) if blend is not None and len(blend) > i else None)
        return faces[i]

    def detect(self, rgb):
        """dict(pts (478, 2) theo pixel ảnh gốc, matrix, jaw_open) hoặc None."""
        pts = steps.run_mp_padded(self.lm, rgb, run=self._run)
        if pts is None:
            return None
        return dict(pts=np.asarray(pts, float), **(self.extra or dict(matrix=None, jaw_open=None)))

    def close(self):
        if hasattr(self.lm, 'close'):
            self.lm.close()


def euler_deg(matrix):
    """(yaw, pitch, roll) độ từ ma trận biến đổi mặt 4x4 của MediaPipe; None nếu thiếu ma trận.
    Quy ước đã kiểm bằng DrivFace (xem README): yaw dương = mặt quay về phía bên PHẢI của ảnh (người lái nhìn sang trái ảnh...)."""
    if matrix is None:
        return None
    R = np.asarray(matrix, float)[:3, :3]
    R = R / (np.linalg.norm(R, axis=0, keepdims=True) + 1e-9)
    yaw = math.degrees(math.atan2(R[0, 2], R[2, 2]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -R[1, 2]))))
    roll = math.degrees(math.atan2(R[1, 0], R[1, 1]))
    return yaw, pitch, roll


def dhash(gray_face):
    """dHash 64 bit (int) của ảnh xám."""
    s = cv2.resize(gray_face, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (s[:, 1:] > s[:, :-1]).flatten()
    return int(''.join('1' if b else '0' for b in bits), 2)


def hamming(a, b):
    return bin(a ^ b).count('1')


def box_of(pts):
    p = np.asarray(pts, float)
    x0, y0 = p.min(0)
    x1, y1 = p.max(0)
    return round(float(x0), 4), round(float(y0), 4), round(float(x1), 4), round(float(y1), 4)


def reject_reason(pts, w, h):
    """Lý do loại khung (chuỗi) hoặc None nếu dùng được."""
    p = np.asarray(pts, float)
    if (p[:, 0] < 0).any() or (p[:, 0] > w - 1).any() or (p[:, 1] < 0).any() or (p[:, 1] > h - 1).any():
        return 'diem_ngoai_khung'
    x0, y0, x1, y1 = box_of(p)
    if max(x1 - x0, y1 - y0) < MIN_FACE_PX:
        return 'mat_qua_nho'
    return None


def pad_fraction(box, w, h):
    """Phần diện tích ảnh cắt (vuông 1,4 x cạnh dài hộp) rơi ra ngoài ảnh gốc, tức phần viền xám."""
    left, top, k, _, _ = crop_geometry(box, np.zeros((1, 2), np.float32))
    side = OUT / k
    ox = max(0.0, min(left + side, w) - max(left, 0.0))
    oy = max(0.0, min(top + side, h) - max(top, 0.0))
    return max(0.0, 1.0 - (ox * oy) / (side * side))


def measure_face(bgr, pts, matrix, jaw_open):
    """Các cột đo thô của một mặt (dict float) + hộp/hình học cắt. Dùng chung cho video và ảnh DrivFace."""
    h, w = bgr.shape[:2]
    box = box_of(pts)
    left, top, k, _, _ = crop_geometry(box, np.zeros((1, 2), np.float32))
    crop, _, _, _ = square_crop(bgr, box, np.zeros((1, 2), np.float32))
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    fx0, fy0 = int(max(0, (box[0] - left) * k)), int(max(0, (box[1] - top) * k))
    fx1, fy1 = int(min(OUT, (box[2] - left) * k)), int(min(OUT, (box[3] - top) * k))
    face = gray[fy0:max(fy1, fy0 + 1), fx0:max(fx1, fx0 + 1)].astype(np.float32)
    gx0, gy0, gx1, gy1 = [int(round(v)) for v in (max(box[0], 0), max(box[1], 0), min(box[2], w), min(box[3], h))]
    fgray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)[gy0:max(gy1, gy0 + 1), gx0:max(gx1, gx0 + 1)]
    norm = cv2.resize(fgray, (FACE_PX, FACE_PX), interpolation=cv2.INTER_AREA if fgray.shape[0] >= FACE_PX else cv2.INTER_LINEAR)
    ang = euler_deg(matrix)
    return dict(box=box, left=round(left, 4), top=round(top, 4), k=round(k, 6),
                yaw=None if ang is None else round(ang[0], 2), pitch=None if ang is None else round(ang[1], 2),
                roll=None if ang is None else round(ang[2], 2),
                jaw_open=None if jaw_open is None else round(float(jaw_open), 4),
                luma=round(float(face.mean()), 2), contrast=round(float(face.std()), 2),
                bright_frac=round(float((face >= BRIGHT_LEVEL).mean()), 4),
                lap_var=round(float(cv2.Laplacian(norm, cv2.CV_64F).var()), 2),
                pad_frac=round(pad_fraction(box, w, h), 4),
                hash=dhash(norm))


def _f(v, default=0.0):
    try:
        return default if v in (None, '') else float(v)
    except ValueError:
        return default


def compute_flags(c):
    """Sáu cờ (dict 0/1) từ các cột đo thô của một ứng viên (dict, giá trị chuỗi hoặc số)."""
    yaw, pitch = abs(_f(c.get('yaw'))), abs(_f(c.get('pitch')))
    luma, contrast = _f(c.get('luma'), 128.0), _f(c.get('contrast'), 60.0)
    if c.get('source') == 'drivface':      # camera DrivFace đặt lệch trục (yaw nhìn thẳng trung bình +10 độ): dùng nhãn của bộ
        pose = str(c.get('gaze_label')) in ('1', '3')
    else:
        pose = yaw >= POSE_YAW_DEG or pitch >= POSE_PITCH_DEG
    return dict(pose=int(pose),
                expression=int(_f(c.get('jaw_open')) >= EXPR_JAW_OPEN),
                illumination=int(luma < LUMA_DARK or luma > LUMA_BRIGHT or _f(c.get('bright_frac')) > BRIGHT_FRAC_MAX
                                 or contrast < CONTRAST_LOW),
                makeup=0,
                occlusion=int(c.get('glasses') == 'sunglasses'),
                blur=int(_f(c.get('lap_var'), 1e9) < BLUR_LAP_VAR.get(c.get('source'), BLUR_LAP_VAR['yawdd'])))


# ======================================================================================================================
# scan
# ======================================================================================================================
def sample_video(path, step_s=SAMPLE_STEP_S, max_samples=MAX_SAMPLES):
    """Sinh (chỉ số khung, giây, ảnh BGR, fps). Đọc tuần tự bằng grab(); KHÔNG tin CAP_PROP_FRAME_COUNT, KHÔNG tua."""
    cap = cv2.VideoCapture(path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps != fps or fps < 1 or fps > 240:
            fps = DEFAULT_FPS
        step = max(1, int(round(fps * step_s)))
        i = n = 0
        while n < max_samples and cap.grab():
            if i % step == 0:
                ok, bgr = cap.retrieve()
                if ok and bgr is not None:
                    yield i, i / fps, bgr, fps
                    n += 1
            i += 1
    finally:
        cap.release()


def _jpeg(bgr):
    ok, buf = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    assert ok, 'không mã hoá được JPEG'
    return buf.tobytes()


def _cand_row(meta, name, m, frame, t_s, image_rel, w, h, extra=None):
    row = dict(name=name, source=meta['source'], camera=meta['camera'], subject=meta['subject'], gender=meta['gender'],
               glasses=meta['glasses'], state=meta['state'], video=meta['video'], frame=frame, t_s=round(t_s, 3), image=image_rel,
               face_idx=0, x0=m['box'][0], y0=m['box'][1], x1=m['box'][2], y1=m['box'][3], left=m['left'], top=m['top'], k=m['k'],
               yaw=m['yaw'], pitch=m['pitch'], roll=m['roll'], jaw_open=m['jaw_open'], luma=m['luma'], contrast=m['contrast'],
               bright_frac=m['bright_frac'], lap_var=m['lap_var'], gaze_label='', gaze_ang='', pad_frac=m['pad_frac'], w=w, h=h)
    row.update(extra or {})
    return row


def _select(cands, mouth_priority, max_keep, min_gap, gap_of):
    """Chọn ứng viên theo thứ tự ưu tiên, giữ khi đủ xa các khung đã giữ (gap_of(a, b) >= min_gap) và dHash đủ khác.
    Trả (danh sách giữ, số bị bỏ vì gần trùng, số bị bỏ vì vượt trần)."""
    by_time = sorted(cands, key=lambda c: c['frame'])
    if mouth_priority:
        by_jaw = sorted(cands, key=lambda c: (-(c['_m']['jaw_open'] or 0.0), c['frame']))
        order, seen = [], set()
        for a, b in zip(by_jaw, by_time):                 # xen kẽ: miệng mở nhất / trải đều theo thời gian
            for c in (a, b):
                if id(c) not in seen:
                    seen.add(id(c))
                    order.append(c)
    else:
        order = by_time
    kept, near, over = [], 0, 0
    for c in order:
        if len(kept) >= max_keep:
            over += 1
            continue
        if any(gap_of(c, k) < min_gap or hamming(c['_m']['hash'], k['_m']['hash']) < DHASH_MIN_DIST for k in kept):
            near += 1
            continue
        kept.append(c)
    return sorted(kept, key=lambda c: c['frame']), near, over


def _unique_name(base, taken):
    name, n = base, 1
    while name in taken:
        n += 1
        name = f'{base}_v{n}'
    taken.add(name)
    return name


def _fingerprint():
    return json.dumps(dict(v=SCAN_VERSION, step=SAMPLE_STEP_S, max_samples=MAX_SAMPLES, max_cand=MAX_CAND_PER_VIDEO, q=JPEG_QUALITY,
                           min_face=MIN_FACE_PX, hash=DHASH_MIN_DIST, dfhash=DF_DHASH_MIN_DIST, gap=MIN_GAP_S, dfgap=DF_MIN_GAP_IMGS, face_px=FACE_PX,
                           bright=BRIGHT_LEVEL), sort_keys=True)


def _shard_path(out, key):
    return os.path.join(out, 'cache', 'shards', hashlib.sha1(key.encode('utf-8')).hexdigest()[:16] + '.npz')


def _save_shard(path, rows, pts_list, rejects):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez_compressed(path, pts=np.asarray(pts_list, np.float32).reshape(-1, 478, 2),
                        meta=np.array(json.dumps(dict(fp=_fingerprint(), rows=rows, rejects=rejects))))


def _load_shard(path):
    if not os.path.exists(path):
        return None
    try:
        z = np.load(path, allow_pickle=False)
        meta = json.loads(str(z['meta']))
        if meta['fp'] != _fingerprint():
            return None
        return meta['rows'], z['pts'], meta['rejects']
    except (OSError, ValueError, KeyError):
        return None


def scan_video(v, det, out, taken):
    """Một video YawDD → (hàng ứng viên, mảng điểm, bộ đếm loại). Ghi khung JPEG vào out/cache/frames."""
    rej = Counter()
    cands = []
    n_read = 0
    for idx, t, bgr, fps in sample_video(v['path']):
        n_read += 1
        buf = _jpeg(bgr)
        dec = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
        res = det.detect(cv2.cvtColor(dec, cv2.COLOR_BGR2RGB))
        if res is None:
            rej['khong_thay_mat'] += 1
            continue
        why = reject_reason(res['pts'], dec.shape[1], dec.shape[0])
        if why:
            rej[why] += 1
            continue
        m = measure_face(dec, res['pts'], res['matrix'], res['jaw_open'])
        cands.append(dict(frame=idx, t=t, buf=buf, _m=m, pts=res['pts'], hw=dec.shape[:2]))
    rej['khung_doc'] += n_read
    if n_read == 0:
        rej['video_khong_doc_duoc'] += 1
    kept, near, over = _select(cands, v['state'] in DASH_STATES, MAX_CAND_PER_VIDEO, MIN_GAP_S, lambda a, b: abs(a['t'] - b['t']))
    rej['gan_trung'] += near
    rej['vuot_tran'] += over
    rows, pts_list = [], []
    for c in kept:
        base = f"{v['subject']}_{v['camera']}_{v['state']}_g{GLASSES_CODE[v['glasses']]}_f{c['frame']:06d}"
        name = _unique_name(base, taken)
        rel = f"cache/frames/{name}.jpg"
        os.makedirs(os.path.join(out, 'cache', 'frames'), exist_ok=True)
        with open(os.path.join(out, 'cache', 'frames', name + '.jpg'), 'wb') as f:
            f.write(c['buf'])
        meta = dict(source='yawdd', camera=v['camera'], subject=v['subject'], gender=v['gender'], glasses=v['glasses'],
                    state=v['state'], video=v['rel'])
        rows.append(_cand_row(meta, name, c['_m'], c['frame'], c['t'], rel, c['hw'][1], c['hw'][0]))
        pts_list.append(c['pts'])
    return rows, pts_list, rej


def scan_drivface(items, det, out, taken):
    """Ảnh DrivFace → (hàng ứng viên, mảng điểm, bộ đếm loại), theo từng tài xế (đã sắp theo imgNum)."""
    rej = Counter()
    cands = []
    for it in items:
        data = open(it['path'], 'rb').read()
        bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        rej['khung_doc'] += 1
        if bgr is None:
            rej['anh_khong_doc_duoc'] += 1
            continue
        res = det.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        if res is None:
            rej['khong_thay_mat'] += 1
            continue
        why = reject_reason(res['pts'], bgr.shape[1], bgr.shape[0])
        if why:
            rej[why] += 1
            continue
        m = measure_face(bgr, res['pts'], res['matrix'], res['jaw_open'])
        cands.append(dict(frame=it['imgnum'], t=float(it['imgnum']), buf=data, _m=m, pts=res['pts'], hw=bgr.shape[:2], it=it))
    # ảnh nhìn phải/trái (hiếm) được xét giữ trước, rồi mới đến ảnh nhìn thẳng
    pose_first = sorted(cands, key=lambda c: (c['it']['label'] == 2, c['frame']))
    kept, near = [], 0
    for c in pose_first:
        if any(abs(c['frame'] - k['frame']) < DF_MIN_GAP_IMGS or hamming(c['_m']['hash'], k['_m']['hash']) < DF_DHASH_MIN_DIST for k in kept):
            near += 1
            continue
        kept.append(c)
    rej['gan_trung'] += near
    rows, pts_list = [], []
    for c in sorted(kept, key=lambda c: c['frame']):
        it = c['it']
        name = _unique_name(f"{it['subject']}_{c['frame']:04d}", taken)
        os.makedirs(os.path.join(out, 'cache', 'frames'), exist_ok=True)
        with open(os.path.join(out, 'cache', 'frames', name + '.jpg'), 'wb') as f:
            f.write(c['buf'])                                  # DrivFace đã là JPEG: giữ nguyên byte, không nén lại
        meta = dict(source='drivface', camera='drivface', subject=it['subject'], gender='unknown', glasses='unknown',
                    state='unknown', video=it['file'].replace(' ', ''))
        rows.append(_cand_row(meta, name, c['_m'], c['frame'], 0.0, f'cache/frames/{name}.jpg', c['hw'][1], c['hw'][0],
                              extra=dict(gaze_label=it['label'], gaze_ang=it['ang'], t_s='')))
        pts_list.append(c['pts'])
    return rows, pts_list, rej


CAND_COLUMNS = ['name', 'source', 'camera', 'subject', 'gender', 'glasses', 'state', 'video', 'frame', 't_s', 'image', 'face_idx',
                'x0', 'y0', 'x1', 'y1', 'left', 'top', 'k', 'yaw', 'pitch', 'roll', 'jaw_open', 'luma', 'contrast', 'bright_frac',
                'lap_var', 'gaze_label', 'gaze_ang', 'pad_frac', 'w', 'h']


def scan(yawdd, drivface, model, out, make_detector=None, fresh=False, limit_videos=None, log=print):
    """Trích ứng viên, dò mặt, đo, ghi out/cache. Chạy lại thì dùng lại phần đã xong (theo từng video) trừ khi fresh."""
    os.makedirs(os.path.join(out, 'cache'), exist_ok=True)
    if fresh:
        shutil.rmtree(os.path.join(out, 'cache'), ignore_errors=True)
        os.makedirs(os.path.join(out, 'cache'), exist_ok=True)
    make_detector = make_detector or (lambda m: FaceDetector(steps.make_landmarker(m, num_faces=5, outputs=True)))
    stats = dict(videos_ok=0, videos_bad=[], drivface_match={}, rejects=Counter())
    jobs = []
    if yawdd:
        vids, bad = list_yawdd(yawdd)
        if limit_videos:
            vids = vids[:limit_videos]
        stats['videos_bad'] = bad
        for b in bad:
            log(f'CẢNH BÁO: tên video không khớp mẫu, bỏ: {b}')
        jobs += [('yawdd', v) for v in vids]
        stats['videos_ok'] = len(vids)
    if drivface:
        items, match = read_drivface(drivface)
        stats['drivface_match'] = dict(match)
        by_sub = defaultdict(list)
        for it in items:
            by_sub[it['subject']].append(it)
        jobs += [('drivface', sorted(v, key=lambda x: x['imgnum'])) for _, v in sorted(by_sub.items())]
        log(f'DrivFace: {len(items)} ảnh khớp tên ({dict(match)})')
    det, all_rows, all_pts, taken = None, [], [], set()
    for n, (kind, job) in enumerate(jobs, 1):
        key = job['rel'] if kind == 'yawdd' else 'drivface:' + job[0]['subject']
        sp = _shard_path(out, key)
        got = _load_shard(sp)
        if got is None:
            det = det or make_detector(model)
            fn = scan_video if kind == 'yawdd' else scan_drivface
            rows, pts, rej = fn(job, det, out, taken)
            _save_shard(sp, rows, pts, dict(rej))
        else:
            rows, pts, rej = got
            pts = list(pts)
            taken.update(r['name'] for r in rows)
        all_rows += rows
        all_pts += pts
        stats['rejects'].update(rej)
        if n % 10 == 0 or n == len(jobs):
            log(f'  scan {n}/{len(jobs)} nguồn, {len(all_rows)} ứng viên')
    if det is not None:
        det.close()
    cp = os.path.join(out, 'cache', 'candidates.csv')
    with open(cp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, CAND_COLUMNS)
        w.writeheader()
        w.writerows([{c: r.get(c, '') for c in CAND_COLUMNS} for r in all_rows])
    np.savez_compressed(os.path.join(out, 'cache', 'pts478.npz'), **{r['name']: np.asarray(p, np.float32) for r, p in zip(all_rows, all_pts)})
    stats['rejects'] = dict(stats['rejects'])
    with open(os.path.join(out, 'cache', 'scan_stats.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    log(f'scan xong: {len(all_rows)} ứng viên từ {len(jobs)} nguồn; loại: {stats["rejects"]}')
    return all_rows, stats


# ======================================================================================================================
# split
# ======================================================================================================================
def read_candidates(out):
    with open(os.path.join(out, 'cache', 'candidates.csv'), encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r.update({k: str(v) for k, v in compute_flags(r).items()})
        r['_flags'] = {k: int(r[k]) for k in FLAGS}
    return rows


def vkey(c):
    """Khoá 'cùng video': YawDD = video; DrivFace = tên ảnh (mỗi ảnh một khoá; khoảng cách giữa ảnh do DF_MIN_GAP_IMGS lo)."""
    return (c['source'], c['video'])


def is_easy(c):
    return not any(c['_flags'].values())


def make_x_blocks(easy, rest, seed):
    """Như split.make_x_blocks: 2 mặt dễ ở seq 01-02, 40 mặt còn lại xếp theo (pose, occlusion) rồi chia vòng 1→5, 5→1."""
    rng = random.Random(seed)
    easy, rest = easy[:], rest[:]
    rng.shuffle(easy)
    rng.shuffle(rest)
    rest.sort(key=lambda r: (r['_flags']['pose'], r['_flags']['occlusion']), reverse=True)
    blocks = [[] for _ in range(5)]
    for i, r in enumerate(rest):
        k = i % 5 if (i // 5) % 2 == 0 else 4 - i % 5
        blocks[k].append(r)
    for k in range(5):
        rng.shuffle(blocks[k])
        blocks[k] = easy[2 * k:2 * k + 2] + blocks[k]
    return blocks


def _block_rows(b, k):
    """Hàng giả cho check_manifest.x_block_errors (seq 1..10)."""
    return [dict(r, seq=i + 1, file=f'X{k}_{i + 1:02d}.png', **{f: r['_flags'][f] for f in FLAGS}) for i, r in enumerate(b)]


def x_blocks_ok(blocks):
    return all(not cm.x_block_errors(_block_rows(b, k + 1), f'khối X{k + 1}') for k, b in enumerate(blocks))


def _rare(c):
    """Mặt có cờ hiếm (kính râm, miệng mở): được lấy trước trong mỗi video để tỉ lệ cờ của 616 mặt không quá thấp."""
    f = c['_flags']
    return 2 * f['occlusion'] + f['expression']


def pick(pool, n, rng, per_video=MAX_PER_VIDEO, taken=None):
    """Chọn n mặt từ pool: lần lượt từng vòng, mỗi vòng lấy 1 mặt của mỗi video (thứ tự video xáo theo rng, video có mặt kính râm lên
    trước), tối đa per_video mặt/video (tính cả `taken`: Counter số mặt đã lấy của video trong toàn manifest). Trong một video, mặt có
    cờ hiếm được lấy trước: ở vòng đầu mặt miệng mở (expression) rồi kính râm, từ vòng hai chỉ ưu tiên kính râm (cờ hiếm nhất), còn lại ngẫu nhiên.
    Trả list hoặc None nếu không đủ."""
    taken = taken if taken is not None else Counter()
    groups = defaultdict(list)
    for c in pool:
        groups[vkey(c)].append(c)
    keys = sorted(groups)
    for key in keys:
        rng.shuffle(groups[key])
        groups[key].sort(key=_rare)                            # sort ổn định; pop() lấy phần tử cuối = cờ hiếm nhất
    got = []
    for rnd in range(per_video):
        if rnd == 1:                                           # từ vòng hai: chỉ còn ưu tiên kính râm
            for key in keys:
                rng.shuffle(groups[key])
                groups[key].sort(key=lambda c: c['_flags']['occlusion'])
        order = [k for k in keys if groups[k] and taken[k] < per_video]
        rng.shuffle(order)
        order.sort(key=lambda k: -(groups[k][-1]['_flags']['occlusion']))
        for key in order:
            if len(got) >= n:
                break
            got.append(groups[key].pop())
            taken[key] += 1
    return got if len(got) >= n else None


def pick_group(pool, n, rng, taken, df_share=DF_SHARE, dash_share=DASH_SHARE, per_video=MAX_PER_VIDEO, df_taken=None):
    """Chọn n mặt cho một tập: ~df_share DrivFace (trong đó >= DF_POSE_SHARE là ảnh pose=1 nếu có), ~dash_share Dash, phần còn lại Mirror;
    thiếu loại nào thì bù từ loại khác. Trả list hoặc None."""
    df = [c for c in pool if c['source'] == 'drivface']
    dash = [c for c in pool if c['camera'] == 'dash']
    mir = [c for c in pool if c['camera'] == 'mirror']
    n_df = min(int(round(df_share * n)), len(df))
    chosen = []
    if n_df:
        n_pose = min(int(math.ceil(DF_POSE_SHARE * n_df)), sum(c['_flags']['pose'] for c in df))
        a = pick([c for c in df if c['_flags']['pose']], n_pose, rng, 1, taken) or []
        used = {id(c) for c in a}
        b = pick([c for c in df if id(c) not in used and not c['_flags']['pose']], n_df - len(a), rng, 1, taken)
        if b is None:
            b = pick([c for c in df if id(c) not in used], n_df - len(a), rng, 1, taken)
        if b is None:
            return None
        chosen += a + b
    n_dash = min(int(round(dash_share * (n - len(chosen)))), len(dash))
    if n_dash:
        d = pick(dash, n_dash, rng, per_video, taken)
        chosen += d or []
    used = {id(c) for c in chosen}
    rest = pick([c for c in mir if id(c) not in used], n - len(chosen), rng, per_video, taken)
    if rest is None:                                           # Mirror không đủ: bù từ Dash/DrivFace còn lại
        rest = pick([c for c in pool if id(c) not in used], n - len(chosen), rng, per_video, taken)
        if rest is None:
            return None
    chosen += rest
    rng.shuffle(chosen)
    return chosen


def _supply(cands):
    c = Counter(vkey(x) for x in cands)
    return sum(min(v, MAX_PER_VIDEO) for v in c.values())


def assign_people(cands, rng):
    """Chia người vào bốn nhóm F, Tdev, Ttest, B (B = G+P+X+D). DrivFace: mỗi nhóm một tài xế (xáo theo rng). YawDD: xếp tầng theo
    (giới, có kính râm, có video Dash) rồi lần lượt gán người cho nhóm đang thiếu mặt nhất."""
    need = dict(F=cm.EXPECT['F'], Tdev=cm.EXPECT['Tdev'], Ttest=cm.EXPECT['Ttest'],
                B=sum(cm.EXPECT[s] for s in cm.GROUP_B))
    by = defaultdict(list)
    for c in cands:
        by[c['subject']].append(c)
    groups = {g: [] for g in need}
    df_people = sorted(p for p in by if p.startswith('df_'))
    order = list(need)
    rng.shuffle(order)
    rng.shuffle(df_people)
    for i, p in enumerate(df_people):
        groups[order[i % 4]].append(p)
    yd = defaultdict(list)
    for p in sorted(q for q in by if not q.startswith('df_')):
        yd[(by[p][0]['gender'], any(c['glasses'] == 'sunglasses' for c in by[p]), any(c['camera'] == 'dash' for c in by[p]))].append(p)
    supply = {g: 0 for g in need}
    order_p = []
    for key in sorted(yd):                                     # xen kẽ các tầng theo tỉ lệ để mọi nhóm đều nhận đủ loại người
        ps = yd[key][:]
        rng.shuffle(ps)
        order_p += [((i + rng.random()) / len(ps), p) for i, p in enumerate(ps)]
    for _, p in sorted(order_p):
        deficit = {g: need[g] * (1 - DF_SHARE) - supply[g] for g in need}
        g = max(need, key=lambda x: (deficit[x], rng.random()))
        groups[g].append(p)
        supply[g] += _supply(by[p])
    return groups, by


def choose_x(pool, rng, taken):
    """10 mặt dễ + 40 mặt còn lại cho X, thành phần định trước: 5-8 pose, tổng occlusion ~ 11-16 → mỗi khối đạt luật.
    Trả (easy, rest40) hoặc None."""
    easy = pick_group([c for c in pool if is_easy(c)], 10, rng, taken, per_video=1)
    if easy is None:
        return None
    used = {id(c) for c in easy}
    rest_pool = [c for c in pool if id(c) not in used]
    pose_pool = [c for c in rest_pool if c['_flags']['pose']]
    if len(pose_pool) < 5:
        return None
    pose = pick(pose_pool, min(rng.randint(5, 8), len(pose_pool)), rng, 2, taken)
    if pose is None:
        return None
    used |= {id(c) for c in pose}
    want_occ = rng.randint(12, 16)
    occ_pool = [c for c in rest_pool if id(c) not in used and c['_flags']['occlusion'] and not c['_flags']['pose']]
    n_occ = max(0, want_occ - sum(c['_flags']['occlusion'] for c in pose))
    if len(occ_pool) < max(n_occ, 6):
        return None
    occ = pick(occ_pool, min(n_occ, len(occ_pool)), rng, 2, taken)
    if occ is None:
        return None
    used |= {id(c) for c in occ}
    others = [c for c in rest_pool if id(c) not in used and not c['_flags']['pose'] and not c['_flags']['occlusion']
              and c['source'] != 'drivface']             # DrivFace chỉ vào X qua mặt dễ và mặt pose (giữ X_MAX_DF)
    oth = pick(others, 40 - len(pose) - len(occ), rng, 2, taken)
    if oth is None:
        return None
    return easy, pose + occ + oth


def deal_gpd(got):
    """Chia 66 mặt cho G (20), P (16), D (30) sao cho DrivFace và các loại camera được chia đều theo tỉ lệ (không để D toàn DrivFace)."""
    need = [cm.EXPECT['G'], cm.EXPECT['P'], cm.EXPECT['D']]
    out = [[], [], []]
    for group in ([c for c in got if c['source'] == 'drivface'], [c for c in got if c['camera'] == 'dash'],
                  [c for c in got if c['source'] != 'drivface' and c['camera'] != 'dash']):
        quota = [round(len(group) * n / sum(need)) for n in need]
        quota[2] = len(group) - quota[0] - quota[1]
        i = 0
        for k in range(3):
            take = min(quota[k], need[k] - len(out[k]))
            out[k] += group[i:i + take]
            i += take
        for c in group[i:]:                                    # phần dư do làm tròn: vào tập còn chỗ
            k = next(j for j in range(3) if len(out[j]) < need[j])
            out[k].append(c)
    return out


def try_split(cands, seed):
    """Một lần thử chia với seed này. Trả danh sách mục {c, set, block, seq, file, seed} hoặc None."""
    rng = random.Random(seed)
    groups, by = assign_people(cands, rng)
    taken = Counter()
    items = []

    def add(rows, name, fmt, blk=lambda i: ''):
        for i, c in enumerate(rows):
            items.append(dict(c=c, set=name, block=blk(i), seq=i + 1, file=fmt(i), seed=seed))

    for g, fmt in (('F', 'F_{:03d}.png'), ('Tdev', 'Tdev_{:03d}.png'), ('Ttest', 'Ttest_{:03d}.png')):
        pool = [c for p in groups[g] for c in by[p]]
        got = pick_group(pool, cm.EXPECT[g], rng, taken)
        if got is None:
            return None
        add(got, g, lambda i, f=fmt: f.format(i + 1))
    poolB = [c for p in groups['B'] for c in by[p]]
    sel = None
    for _ in range(X_TRIES):
        tk = Counter(taken)
        x = choose_x(poolB, rng, tk)
        if x is None:
            return None
        blocks = make_x_blocks(x[0], x[1], rng.randrange(1 << 30))
        allx = x[0] + x[1]
        if max(Counter(c['subject'] for c in allx).values()) > X_MAX_PER_PERSON or \
                sum(c['source'] == 'drivface' for c in allx) > X_MAX_DF:
            continue
        if x_blocks_ok(blocks):
            sel, taken = blocks, tk
            break
    if sel is None:
        return None
    usedx = {id(c) for b in sel for c in b}
    for k, b in enumerate(sel, 1):
        add(b, 'X', lambda i, k=k: f'X{k}_{i + 1:02d}.png', blk=lambda i, k=k: str(k))
    others = [c for c in poolB if id(c) not in usedx]
    n_other = cm.EXPECT['G'] + cm.EXPECT['P'] + cm.EXPECT['D']
    x_df = sum(1 for b in sel for c in b if c['source'] == 'drivface')
    share = max(0.0, (DF_SHARE * (n_other + 50) - x_df) / n_other)
    got = pick_group(others, n_other, rng, taken, df_share=share)
    if got is None:
        return None
    G, P, D = deal_gpd(got)
    for k in range(5):
        add(G[4 * k:4 * k + 4], 'G', lambda i, k=k: f'G{k + 1}_{i + 1:02d}.png', blk=lambda i, k=k: str(k + 1))
    for name, rows in (('a', P[:8]), ('b', P[8:])):
        add(rows, 'P', lambda i, n=name: f'P{n}_{i + 1:02d}.png', blk=lambda i, n=name: n)
    add(D, 'D', lambda i: f'D_{i + 1:02d}.png')
    return items


def balance_penalty(items):
    """Điểm phạt độ cân bằng (càng nhỏ càng tốt; ưu tiên, không phải luật cứng): với F, Tdev, Ttest và cả nhóm B gộp lại, phạt lệch giới,
    thiếu camera Dash, không có kính râm, thiếu hẳn một loại kính (không kính / kính thuốc)."""
    sets = {'F': ['F'], 'Tdev': ['Tdev'], 'Ttest': ['Ttest'], 'B': list(cm.GROUP_B)}
    pen = 0.0
    for names in sets.values():
        rows = [o['c'] for o in items if o['set'] in names]
        known = [c['gender'] for c in rows if c['gender'] != 'unknown']
        if known:
            pen += 2 * abs(known.count('F') / len(known) - 0.5)
        pen += 0.0 if any(c['camera'] == 'dash' for c in rows) else 1.0
        pen += 0.0 if any(c['glasses'] == 'sunglasses' for c in rows) else 1.0
        gl = [c['glasses'] for c in rows if c['glasses'] != 'unknown']
        if gl:
            pen += 2 * max(0.0, 0.2 - min(gl.count('none'), gl.count('glasses')) / len(gl))
    return pen


def split_sets(cands, seed, max_tries=MAX_TRIES, n_good=BALANCE_TRIES):
    """Chia 616 mặt thành F/Tdev/Ttest/G/P/X/D, tách theo người. Thử seed, seed + 1, ... (tối đa max_tries lần); lấy n_good lần ĐẠT mọi luật
    đầu tiên rồi chọn lần có balance_penalty nhỏ nhất (hoà thì seed nhỏ hơn). Seed của lần được chọn ghi vào cột seed: chạy lại với chính
    seed đó cho đúng kết quả (lần thử đầu tiên của nó đã đạt)."""
    good = []
    for t in range(max_tries):
        items = try_split(cands, seed + t)
        if items is None or cm.check_incabin(manifest_rows(items)):
            continue
        good.append((balance_penalty(items), seed + t, items))
        if len(good) >= n_good:
            break
    if not good:
        raise AssertionError(f'không chia được 616 mặt đạt luật sau {max_tries} lần thử (seed {seed}..{seed + max_tries - 1}): '
                             'kiểm số người/ứng viên, nhất là mặt dễ, pose, kính râm trong nhóm B')
    return min(good, key=lambda g: (g[0], g[1]))[2]


def manifest_rows(items):
    """Các dòng manifest (dict chuỗi) theo INC_COLUMNS, theo thứ tự items."""
    rows = []
    for o in items:
        c = o['c']
        r = {col: c.get(col, '') for col in INC_COLUMNS}
        r.update(file=o['file'], set=o['set'], block=o['block'], seq=o['seq'], seed=o['seed'], **c['_flags'])
        rows.append({k: ('' if v is None else str(v)) for k, v in r.items()})
    return rows


def write_manifest(items, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, INC_COLUMNS, lineterminator='\n')
        w.writeheader()
        w.writerows(manifest_rows(items))


def frame_rel(c):
    return f"{c['source']}/{c['subject']}/{c['name']}.jpg"


def split(out, seed, log=print):
    """Chia tập từ cache, ghi khung gốc, ảnh cắt và manifest.csv vào out. Tất định theo (cache, seed)."""
    cands = read_candidates(out)
    items = split_sets(cands, seed)
    for o in items:
        c = o['c']
        c['image'] = frame_rel(c)
    for sub in ('frames', 'crops'):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
    os.makedirs(os.path.join(out, 'crops'), exist_ok=True)
    for o in items:
        c = o['c']
        dst = os.path.join(out, 'frames', *c['image'].split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(out, 'cache', 'frames', c['name'] + '.jpg'), dst)
        bgr = cv2.imread(dst)
        box = tuple(float(c[k]) for k in ('x0', 'y0', 'x1', 'y1'))
        crop, _, _, _ = square_crop(bgr, box, np.zeros((1, 2), np.float32))
        cv2.imwrite(os.path.join(out, 'crops', o['file']), crop, [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION])
    write_manifest(items, os.path.join(out, 'manifest.csv'))
    log(f'split: {len(items)} mặt, seed thực dùng {items[0]["seed"]} (khởi đầu {seed})')
    return items


# ======================================================================================================================
# pack
# ======================================================================================================================
LIMIT_BYTES = 28 * 1024 * 1024          # 29 360 128: công cụ gửi file giới hạn 30 MiB
DOC_NAME, NOTICE_NAME = 'DOC.txt', 'sources/NOTICE.txt'


def _entry_cost(name, size):
    n = len(name.encode('utf-8'))
    return 30 + n + size + 46 + n                      # local header + dữ liệu + mục thư mục trung tâm (ZIP_STORED, không zip64)


def plan_parts(files, limit):
    """files: [(tên, kích thước)] → danh sách các phần (list tên), mỗi phần <= limit byte (tính cả header zip)."""
    parts, cur, used = [], [], 22
    for name, size in files:
        cost = _entry_cost(name, size)
        if cost + 22 > limit:
            raise ValueError(f'{name} ({size} byte) lớn hơn giới hạn một phần {limit}')
        if used + cost > limit and cur:
            parts.append(cur)
            cur, used = [], 22
        cur.append(name)
        used += cost
    if cur:
        parts.append(cur)
    return parts


NOTICE = """NGUON DU LIEU VA DIEU KHOAN (file UTF-8)
==========================================
Du an M28 (nhan nhap landmark khuon mat) cua doi T015-SIXSEVEN la du an PHI THUONG MAI (hoc tap/nghien cuu).
Anh nay chi dung noi bo nhom. KHONG phat tan, KHONG dang lai, KHONG dua vao bao cao/slide cong khai,
KHONG dua anh len chat hay dich vu ben ngoai. Anh nguoi lai xe la du lieu nhay cam.

1. YawDD (video trong xe)
   Trich dan bat buoc (theo Readme_YawDD.pdf cua bo du lieu):
     S. Abtahi, M. Omidyeganeh, S. Shirmohammadi, and B. Hariri, "YawDD: A Yawning Detection Dataset",
     Proc. ACM Multimedia Systems, Singapore, March 19-21 2014.
   Dieu khoan (nguyen van tom tat tu Readme_YawDD.pdf): video chi cho muc dich phi thuong mai va nghien cuu ("non-commercial and
   research purposes only"); duoc dung trong bai bao hoc thuat; chi duoc dung anh chup man hinh cua nhung video ma cot
   "Allow Researchers to use picture in their paper" (Table1.pdf, Table2.pdf) la "Yes". Cot do la "No" thi KHONG duoc dung anh
   cua video do trong bai bao hay an pham. Bo du lieu lay tu kho ACM Multimedia Systems Conference Dataset Archive
   (https://skuld.cs.umass.edu/traces/mmsys/2014/user06.tar). Giay phep chinh thuc tren IEEE DataPort: chua xac minh.
   Ve ky thuat: manifest KHONG ghi cot "duoc dung anh hay khong" cho tung video; truoc khi dua bat ky anh nao ra ngoai nhom,
   phai doi chieu video goc voi Table1.pdf / Table2.pdf.

2. DrivFace (606 anh, 4 tai xe)
   Trich dan (theo file .bib di kem bo du lieu):
     Katerine Diaz-Chito, Aura Hernandez-Sabate, Antonio M. Lopez, "A reduced feature set for driver head pose estimation",
     Applied Soft Computing, Volume 45, August 2016, Pages 98-107, ISSN 1568-4946, doi 10.1016/j.asoc.2016.04.027.
   Dieu khoan (theo readme.txt cua bo): "This database is free for academic usage. For other purposes, please contact" tac gia
   (thong tin lien he nam trong readme.txt cua bo du lieu). Du an phi thuong mai nen dung duoc cho hoc tap.

3. Ma nguoi an danh: yd_F001... (YawDD), df_01..df_04 (DrivFace). Bo du lieu khong co ten nguoi; khong them truong nao chua ten.
"""


def write_doc(items, seed, seed_used, n_parts, when):
    c = Counter(o['set'] for o in items)
    sets = ', '.join(f'{s} {c[s]}' for s in cm.EXPECT)
    return f"""GOI DU LIEU IN-CABIN M28 (file UTF-8)
Tao ngay {when}, seed khoi dau {seed}; lan chia duoc chon dung seed {seed_used} (cot seed cua manifest.csv).
Noi dung: manifest.csv, crops\\<file>.png (anh cat 512 x 512 quanh mat), sources\\NOTICE.txt (nguon va dieu khoan). Khong co video,
khong co khung goc (khung goc chi nguoi dung goi giu).
So anh: {len(items)} ({sets}). Chia thanh {n_parts} phan anh (m28_incab_part01..) va 1 phan meta (m28_incab_part00_meta.zip).

GIAI NEN (cmd). Tat ca cac phan vao CUNG thu muc data\\ de ra data\\manifest.csv va data\\crops\\:
    mkdir data
    for %f in (m28_incab_part*.zip) do tar -xf "%f" -C data
KIEM TRA:
    python tool\\check_manifest.py data\\manifest.csv
CHAY THU (5 mat F, chi can goi nay; chay.bat muc 3 lam san viec nay):
    python tool\\m28.py all --run F5 --list data\\f5_list.csv --images data\\crops --box crop --review auto --dry-run
  (data\\f5_list.csv co cot image,face_idx,seed cua 5 dong F dau trong manifest.csv. --images data\\crops: nguoi chi co goi dung chinh anh cat.)

CAC COT manifest.csv: file (ten anh cat), set (F/Tdev/Ttest/G/P/X/D), block (G 1-5, P a/b, X 1-5), seq, source (yawdd|drivface),
camera (dash|mirror|drivface), subject (ma nguoi an danh), gender (F|M|unknown), glasses (none|glasses|sunglasses|unknown),
state (normal|talking|yawning|talking_yawning|dash|unknown), video (video goc hoac ten anh DrivFace), frame (chi so khung; DrivFace = imgNum),
t_s (giay trong video; trong voi DrivFace), image (khung goc, tuong doi so voi frames\\), face_idx (0), x0 y0 x1 y1 (hop mat tren anh goc),
left top k (cat lai: x_goc = x_cat / k + left), 6 co 0/1 (pose expression illumination makeup occlusion blur), cac cot do tho
(yaw pitch roll jaw_open luma contrast bright_frac lap_var gaze_label gaze_ang pad_frac), seed.
Quy tac: nhom A = F, Tdev, Ttest (doi mot khong chung nguoi); nhom B = G, P, X, D; khong nguoi nao o ca A va B.

TAO LAI (chi P1/chu repo, can video YawDD + DrivFace):
    python tool\\inc_ingest.py all --yawdd "<YawDD dataset>" --drivface <DrivFace> --model face_landmarker.task --out data --seed {seed}
(Chay lai voi cung seed khoi dau va cung video ra manifest giong het tung byte; chua thu tren Windows.)
"""


def pack(out, parts_dir, seed=None, limit=LIMIT_BYTES, log=print):
    """Gói out/manifest.csv + out/crops/*.png thành zip trong parts_dir (không đưa video/khung gốc/cache).
    seed = seed khởi đầu của lệnh chia (ghi vào DOC.txt để dựng lại); không cho thì lấy seed thực dùng trong manifest."""
    with open(os.path.join(out, 'manifest.csv'), encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    used = rows[0]['seed'] if rows else ''
    seed = seed if seed is not None else used
    names = [f'crops/{r["file"]}' for r in rows]
    files = [(n, os.path.getsize(os.path.join(out, *n.split('/')))) for n in names]
    plan = plan_parts(files, limit)
    os.makedirs(parts_dir, exist_ok=True)
    for old in glob.glob(os.path.join(parts_dir, 'm28_incab_part*.zip')):
        os.remove(old)
    items = [dict(set=r['set']) for r in rows]
    when = datetime.date.today().isoformat()
    meta_files = {'manifest.csv': open(os.path.join(out, 'manifest.csv'), 'rb').read(),
                  DOC_NAME: write_doc(items, seed, used, len(plan), when).encode('utf-8'),
                  NOTICE_NAME: NOTICE.encode('utf-8')}
    made = []
    meta = os.path.join(parts_dir, 'm28_incab_part00_meta.zip')
    with zipfile.ZipFile(meta, 'w', zipfile.ZIP_STORED) as z:
        for n, data in meta_files.items():
            z.writestr(n, data)
    made.append(meta)
    for i, part in enumerate(plan, 1):
        p = os.path.join(parts_dir, f'm28_incab_part{i:02d}_of_{len(plan):02d}.zip')
        with zipfile.ZipFile(p, 'w', zipfile.ZIP_STORED) as z:
            for n in part:
                z.write(os.path.join(out, *n.split('/')), n)
        made.append(p)
    for p in made:
        assert os.path.getsize(p) <= limit, f'{p} vượt giới hạn {limit}'
        log(f'  {os.path.basename(p)}: {os.path.getsize(p) / 1048576:.2f} MiB')
    return made


# ======================================================================================================================
# thống kê, CLI
# ======================================================================================================================
def stats_report(items):
    """Chuỗi thống kê: số mặt/người, phân bố, tỉ lệ cờ, bảng khối X."""
    L = []
    cs = [(o['set'], o['c']) for o in items]
    sets = list(cm.EXPECT)
    for s in sets:
        rows = [c for t, c in cs if t == s]
        L.append(f'{s}: {len(rows)} mặt, {len({c["subject"] for c in rows})} người')
        for col in ('camera', 'gender', 'glasses', 'state', 'source'):
            L.append(f'   {col}: ' + ', '.join(f'{k} {v}' for k, v in sorted(Counter(c[col] for c in rows).items())))
        L.append('   cờ: ' + ', '.join(f'{f} {sum(c["_flags"][f] for c in rows) / len(rows):.0%}' for f in FLAGS))
    allr = [c for _, c in cs]
    L.append('TOÀN BỘ ' + str(len(allr)) + ' mặt: cờ ' + ', '.join(f'{f} {sum(c["_flags"][f] for c in allr) / len(allr):.0%}' for f in FLAGS))
    L.append('   DrivFace: ' + f'{sum(c["source"] == "drivface" for c in allr) / len(allr):.0%}, Dash: '
             f'{sum(c["camera"] == "dash" for c in allr) / len(allr):.0%}')
    for k in '12345':
        b = [c for t, c in [(o['set'], o['c']) for o in items if o['set'] == 'X' and o['block'] == k]]
        L.append(f'   X{k}: pose {sum(c["_flags"]["pose"] for c in b)}, occlusion {sum(c["_flags"]["occlusion"] for c in b)}, '
                 f'giới {sorted({c["gender"] for c in b} - {"unknown"})}, camera {sorted({c["camera"] for c in b})}, '
                 f'kính {sorted({c["glasses"] for c in b} - {"unknown"})}')
    return '\n'.join(L)


def build_parser():
    p = argparse.ArgumentParser(prog='inc_ingest', description=__doc__.split('\n')[0])
    p.add_argument('cmd', choices=['scan', 'split', 'pack', 'all'])
    p.add_argument('--yawdd', help='thư mục "YawDD dataset" (có Dash\\ và Mirror\\)')
    p.add_argument('--drivface', help='thư mục DrivFace (có drivPoints.txt và imgs\\DrivImages)')
    p.add_argument('--model', default='face_landmarker.task')
    p.add_argument('--out', default='data')
    p.add_argument('--parts', help='thư mục ra các file zip (mặc định <out>_parts)')
    p.add_argument('--seed', type=int, default=5, help='seed khởi đầu của lệnh chia (lần chia được chọn ghi seed thực dùng vào cột seed)')
    p.add_argument('--fresh', action='store_true', help='scan: xoá cache cũ, dò lại từ đầu')
    p.add_argument('--limit-videos', type=int, help='scan: chỉ xử lý ngần này video đầu (thử nhanh)')
    p.add_argument('--limit-bytes', type=int, default=LIMIT_BYTES, help='pack: kích thước tối đa một file zip')
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    parts = a.parts or a.out.rstrip('\\/') + '_parts'
    if a.cmd in ('scan', 'all'):
        if not (a.yawdd or a.drivface):
            raise SystemExit('scan cần --yawdd và/hoặc --drivface')
        scan(a.yawdd, a.drivface, a.model, a.out, fresh=a.fresh, limit_videos=a.limit_videos)
    if a.cmd in ('split', 'all'):
        items = split(a.out, a.seed)
        print(stats_report(items))
    if a.cmd in ('pack', 'all'):
        pack(a.out, parts, seed=a.seed, limit=a.limit_bytes)


if __name__ == '__main__':
    main()
