"""Dựng bộ 200 ảnh chung cho hai nhóm thử gán 50 điểm: MANUAL (gán tay) và ASSISTED (dùng tool, sửa nháp) (QĐ-008).

Một bộ 200 ảnh in-cabin (YawDD + DrivFace) phủ mọi độ khó khi gán 50 điểm DMS, hai gói: GÓI A cho nhóm gán tay (ảnh thô, KHÔNG nháp) và GÓI B
cho nhóm dùng tool (cùng ảnh + manifest + `prelabel.xml` sinh sẵn + lượt chạy sẵn `runs/bo200`). Số thứ tự 001..200 xáo cố định theo seed,
riêng 001 và 002 là hai ảnh dễ để khởi động. Ánh xạ số -> khung gốc / tài xế / camera / mức khó / thẻ / cờ CHỈ nằm trong file bí mật cho nhóm trưởng.

Các lệnh con (chạy lần lượt; `all` = do -> chon -> goi -> kiem):

    do     đo mọi ứng viên trên ẢNH CẮT 512 (MediaPipe thấy mặt không, blendshape mắt/miệng, độ lệch nháp gốc-lật `flip_nme`, gợi ý tay che).
           Chậm, chạy nền, LÀM TIẾP ĐƯỢC khi chạy lại (cache theo từng ứng viên). Ghi cache/do.jsonl và cache/bang_do.csv.
    them   trích thêm khung từ video YawDD cho các thẻ còn thiếu (lấy mẫu dày hơn, bỏ trần 150 giây), ghi cache/new/. Rồi chạy lại `do`.
    chon   chọn 200 ảnh, đánh số, ghi file bí mật. THUẦN và TẤT ĐỊNH: cùng bảng đo + cùng --sua-the + cùng --seed => cùng kết quả.
           --dry-run: chỉ in bảng phân bố và thẻ thiếu, không ghi gì.
    luoi   vẽ lưới ảnh nhỏ có mã và thẻ ở dải dưới ô (để kiểm bằng mắt rồi ghi sửa thẻ vào --sua-the)
    goi    ghi ảnh 001..200, chạy ĐÚNG `tool/m28.py` để sinh nháp (prepare -> review auto -> push --dry-run), đóng zip gói A, gói B, bí mật
    kiem   giải nén sạch từng gói vào thư mục mới và kiểm (sha256, rò rỉ, chạy tool bằng code HEAD...); ghi kiem/bao_cao_kiem.txt
    all    do -> chon -> goi -> kiem

Ví dụ (bash, Linux; đứng ở source-tool/m28-prelabel; KHÔNG đặt --out trong repo):
    python tool/tao_bo200.py do   --candidates /d/incab_data/cache/candidates.csv --model /d/face_landmarker.task --out /d/bo200
    python tool/tao_bo200.py chon --out /d/bo200 --sua-the /d/bo200/sua_the.csv --seed 7 --dry-run
    python tool/tao_bo200.py chon --out /d/bo200 --sua-the /d/bo200/sua_the.csv --seed 7
    python tool/tao_bo200.py goi  --out /d/bo200 --model /d/face_landmarker.task
Ví dụ (cmd, Windows):
    python tool\\tao_bo200.py chon --out D:\\bo200 --sua-the D:\\bo200\\sua_the.csv --seed 7 --dry-run

Đầu vào: candidates.csv + khung ứng viên (từ `inc_ingest.py scan`), manifest.csv của gói 616 (để đánh dấu mặt trùng), video YawDD / ảnh DrivFace (chỉ `them`),
face_landmarker.task. Đầu ra trong --out: cache/, luoi/, A/, B/, bi_mat/, SHA256SUMS_bo200.txt, nhat_ky.txt. KHÔNG commit gì trong đó
(ảnh người lái xe là dữ liệu nhạy cảm; --out bị từ chối nếu nằm trong repo). Mọi sửa đổi bằng mắt nằm trong MỘT file đầu vào --sua-the
(cột ung_vien, the_them, the_bo, quyet_dinh (giu|loai), ghi_chu) nên chạy lại ra đúng kết quả.

--- Độ khó (khó khi gán 50 điểm DMS: mày, sống mũi, mắt, môi ngoài, môi trong; không viền hàm) ---
Mỗi ứng viên có các THẺ yếu tố (bảng THE_DIEM bên dưới: góc mặt theo hệ camera, kính, miệng, mắt nhắm, sáng/tối, mờ, che...), mỗi thẻ một điểm;
tổng S quyết định mức: dễ (S <= 0,5), vừa (1..2,5), khó (3..4,5), rất khó (S >= 5, hoặc tay che mắt, hoặc |yaw| >= 45, hoặc kính râm cộng một yếu tố >= 1,5).
Ngưỡng và trọng số hiệu chỉnh MỘT lần bằng mắt trên lưới rồi ghi cứng ở đầu file (giống inc_ingest.py); không tính theo phân vị lúc chạy.
Hạn chế phải nhớ: mọi ảnh trong bộ đều là ảnh MediaPipe thấy mặt (nháp ASSISTED cần có), nên ca khó nhất (MediaPipe bỏ cuộc) KHÔNG có trong bộ.

--- Chọn ---
Hạn mức mức (dễ 40, vừa 70, khó 60, rất khó 30), mỗi thẻ hiếm tối thiểu 8 (mục tiêu 10) nếu dữ liệu cho phép, 8-10 ảnh nháp tệ (xác nhận bằng mắt),
mỗi tài xế <= 6 ảnh, mỗi video <= 3 ảnh cách nhau >= 2 giây, không hai ảnh gần trùng (dHash) trong cùng tài xế, ưu tiên ứng viên NGOÀI 616 mặt của gói đội.
Thử nhiều seed liên tiếp (như inc_ingest.split_sets), lấy lần đạt mọi luật cứng có điểm phạt cân bằng nhỏ nhất; ghi seed khởi đầu và seed thực dùng.
"""
import argparse
import csv
import datetime
import glob
import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import socket
import struct
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_drivface as cd  # noqa: E402
import check_manifest as cm  # noqa: E402
import inc_ingest as ii  # noqa: E402
from m28core import mapping, steps  # noqa: E402
from m28core.cat_mat import OUT, SIDE_SCALE, square_crop  # noqa: E402

PROJECT = os.path.dirname(HERE)                       # source-tool/m28-prelabel

# ======================================================================================================================
# Hằng số (hiệu chỉnh MỘT lần bằng mắt, 9/10/2026; xem docstring và QĐ-008)
# ======================================================================================================================
BO_ANH = 'bo200_v1'                                   # giá trị cho trường bo_anh (config/nhom_thi_nghiem.json do máy khác giữ)
N_ANH = 200
N_WARMUP = 2
LEVELS = ('de', 'vua', 'kho', 'rat_kho')
LEVEL_VI = {'de': 'dễ', 'vua': 'vừa', 'kho': 'khó', 'rat_kho': 'rất khó'}
QUOTA = {'de': 40, 'vua': 70, 'kho': 60, 'rat_kho': 30}
K_PER_SUBJECT = 6                                     # mỗi tài xế tối đa ngần này ảnh
MAX_PER_VIDEO = cm.MAX_PER_VIDEO                      # 3
MIN_GAP_S = cm.MIN_GAP_S                              # 2 giây
DF_MIN_GAP_IMGS = cm.DF_MIN_GAP_IMGS                  # 3 số ảnh
MIN_THE, TARGET_THE = 8, 10                           # thẻ hiếm: tối thiểu / mục tiêu
N_NHAP_TE, MIN_NHAP_TE = 10, 8                        # ảnh nháp tệ: mặc định / tối thiểu
N_BLOCKS = 9                                          # đánh số: chia 198 ảnh thành 9 khối liên tiếp
MAX_TE_PER_BLOCK = 2
DF_RANGE = (16, 24)                                   # số ảnh DrivFace mong muốn
SEEDS_TRIED = 400                                     # số seed liên tiếp thử tối đa
SEEDS_GOOD = 12                                       # lấy ngần này lần ĐẠT mọi luật đầu tiên rồi chọn lần có điểm phạt nhỏ nhất
OUT_616_MIN = 0.80                                    # mục tiêu: >= 80% bộ 200 là ứng viên NGOÀI 616 mặt của gói đội
SHARE_TARGET = dict(mirror=(0.65, 0.75), dash=(0.12, 0.20), drivface=(0.08, 0.12))
FEMALE_RANGE = (0.45, 0.55)
MIN_SUBJECTS = 40

# ---- ngưỡng thẻ (độ / tỉ lệ / pixel) ----
YAW_VUA, YAW_LON, YAW_MANH, YAW_RAT_KHO = 20.0, 32.0, 40.0, 45.0     # |yaw| hệ camera (không trừ độ lệch +23 độ của Mirror)
PITCH_VUA, PITCH_LECH = 15.0, 20.0
ROLL_NGHIENG = 15.0
YAW_PHAI_DUONG = True        # yaw > 0 = mặt quay về phía PHẢI ảnh (đã kiểm bằng mắt trên 60 ảnh yaw cực đoan, 9/10/2026)
PITCH_LEN_DUONG = False      # pitch > 0 = CÚI xuống, pitch < 0 = NGẨNG lên (đã kiểm bằng mắt trên 60 ảnh pitch cực đoan: ngáp ngửa đầu có pitch âm)
JAW_NOI, JAW_NGAP = 0.15, 0.50                        # jawOpen trên ảnh cắt
BLINK_LIM, BLINK_NHAM = 0.35, 0.60                    # eyeBlink (min hai mắt) trên ảnh cắt
BLINK_YAW_MAX = YAW_MANH                              # mặt nghiêng |yaw| >= ngần này: blendshape mắt không tin được (nhìn bằng mắt: nghiêng mà mắt mở vẫn báo ~0,8)
LUMA_TOI, LUMA_SANG = ii.LUMA_DARK, ii.LUMA_BRIGHT    # 70 / 170
BRIGHT_FRAC_SANG = ii.BRIGHT_FRAC_MAX                 # 0,08
CONTRAST_THAP = ii.CONTRAST_LOW                       # 28
MAT_NHO_PX = 130.0                                    # cạnh dài hộp mặt (px khung gốc)
PAD_SAT_MEP = 0.05
HAND_COV_GOI_Y = 0.15                                 # bàn tay phủ >= ngần này diện tích hộp mặt thì GỢI Ý thẻ che_tay (xem bằng mắt rồi mới chốt)
NHAP_TOT_NME = 3.5                                    # flip_nme (% IOD) <= ngần này: nháp "tốt" (xác nhận bằng mắt trên mẫu)
NHAP_TE_NME = 12.0                                    # flip_nme >= ngần này: ĐỦ nghi nháp tệ để xem bằng mắt (thẻ nhap_te chỉ ghi khi đã xác nhận)
BOX_IOU_NGHI = 0.6                                    # hộp mặt MediaPipe trên ảnh cắt khác hộp ứng viên (IoU thấp): nghi bắt nhầm mặt

# thẻ -> điểm. Thẻ không có trong bảng có điểm 0 (cam_*, nhap_te, nhap_tot, che_tay_mat).
THE_DIEM = {
    'yaw_vua': 1.0, 'yaw_lon': 2.0, 'yaw_manh_trai': 3.0, 'yaw_manh_phai': 3.0,
    'pitch_vua': 1.0, 'pitch_len': 2.0, 'pitch_xuong': 2.0, 'nghieng_dau': 0.5,
    'kinh_can': 1.0, 'kinh_ram': 3.0,
    'che_tay': 3.0, 'che_khac': 1.0, 'che_khac_nhieu': 2.0, 'toc_che_may': 1.0,
    'noi': 0.5, 'ngap_rong': 1.0, 'lim_dim': 1.0, 'mat_nham': 1.5,
    'toi': 1.5, 'sang_chay': 1.5, 'tuong_phan_thap': 1.0, 'mo': 1.5, 'mat_nho': 1.0,
    'rau': 0.5, 'sat_mep': 0.5,
    'cam_dash': 0.0, 'cam_mirror': 0.0, 'cam_drivface': 0.0,
    'che_tay_mat': 0.0, 'nhap_te': 0.0, 'nhap_tot': 0.0,
}
THE_THU_TU = list(THE_DIEM)                           # thứ tự hiển thị
THE_HIEM = ('yaw_manh_trai', 'yaw_manh_phai', 'pitch_len', 'pitch_xuong', 'kinh_ram', 'che_tay', 'ngap_rong', 'mat_nham', 'toi', 'sang_chay', 'mo')
THE_TU_DONG = ('yaw_vua', 'yaw_lon', 'yaw_manh_trai', 'yaw_manh_phai', 'pitch_vua', 'pitch_len', 'pitch_xuong', 'nghieng_dau', 'kinh_can', 'kinh_ram',
               'noi', 'ngap_rong', 'lim_dim', 'mat_nham', 'toi', 'sang_chay', 'tuong_phan_thap', 'mo', 'mat_nho', 'rau', 'sat_mep',
               'cam_dash', 'cam_mirror', 'cam_drivface')
THE_BANG_MAT = ('che_tay', 'che_tay_mat', 'che_khac', 'che_khac_nhieu', 'toc_che_may', 'nhap_te', 'nhap_tot')   # chỉ gán bằng mắt (--sua-the)
RE_RAU = re.compile(r'(Beard|moustache)', re.I)       # trong tên video YawDD (parse_yawdd khớp nhưng không trả về)

CSV_BANG = ['name', 'moi', 'source', 'camera', 'subject', 'gender', 'glasses', 'state', 'video', 'frame', 't_s', 'khung', 'face_idx',
            'x0', 'y0', 'x1', 'y1', 'left', 'top', 'k', 'yaw', 'pitch', 'roll', 'jaw_open', 'luma', 'contrast', 'bright_frac', 'lap_var',
            'gaze_label', 'gaze_ang', 'pad_frac', 'w', 'h', 'canh_mat_px', 'hash', 'trung_goi616',
            'mp_ok', 'mp_flip_ok', 'blink_l', 'blink_r', 'jaw_crop', 'flip_nme', 'df_err', 'hand_n', 'hand_cov', 'box_iou']
SO_COT = ('frame', 'x0', 'y0', 'x1', 'y1', 'left', 'top', 'k', 'yaw', 'pitch', 'roll', 'jaw_open', 'luma', 'contrast', 'bright_frac', 'lap_var',
          'gaze_label', 'gaze_ang', 'pad_frac', 'w', 'h', 'canh_mat_px', 'blink_l', 'blink_r', 'jaw_crop', 'flip_nme', 'df_err', 'hand_n',
          'hand_cov', 'box_iou', 't_s', 'face_idx')


# ======================================================================================================================
# Tiện ích chung
# ======================================================================================================================
def _num(v, default=None):
    try:
        return default if v in (None, '') else float(v)
    except (TypeError, ValueError):
        return default


def ghi_nhat_ky(out, msg, echo=True):
    """Nối một dòng có giờ vào <out>/nhat_ky.txt (và in ra màn hình)."""
    line = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    if echo:
        print(line, flush=True)
    if out:
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, 'nhat_ky.txt'), 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def repo_root():
    """Thư mục gốc git (đi ngược từ file này tới chỗ có .git); không thấy thì thư mục PROJECT."""
    d = PROJECT
    while True:
        if os.path.exists(os.path.join(d, '.git')):
            return d
        up = os.path.dirname(d)
        if up == d:
            return PROJECT
        d = up


def check_out_dir(out, root=None):
    """SystemExit nếu --out nằm trong repo (ảnh người lái xe, zip, file bí mật không được ở trong repo)."""
    root = os.path.realpath(root or repo_root())
    p = os.path.realpath(out)
    if p == root or p.startswith(root + os.sep):
        raise SystemExit(f'--out {out} nằm trong repo ({root}): dữ liệu nhạy cảm không được ở trong repo. Chọn thư mục ngoài repo.')
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def doc_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def ghi_csv(path, cols, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, cols, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def hair_of(video):
    """True nếu tên video YawDD ghi râu/ria (Beard / moustache)."""
    return bool(RE_RAU.search(os.path.basename(str(video))))


# ======================================================================================================================
# Thẻ và mức (THUẦN: không cv2, không mediapipe)
# ======================================================================================================================
def the_tu_dong(c):
    """Danh sách thẻ tự động của một ứng viên (dict số đo; giá trị thiếu = None). Thứ tự theo THE_THU_TU."""
    t = set()
    yaw, pitch, roll = _num(c.get('yaw')), _num(c.get('pitch')), _num(c.get('roll'))
    if yaw is not None:
        a = abs(yaw)
        if YAW_VUA <= a < YAW_LON:
            t.add('yaw_vua')
        elif YAW_LON <= a < YAW_MANH:
            t.add('yaw_lon')
        elif a >= YAW_MANH:
            t.add('yaw_manh_phai' if (yaw > 0) == YAW_PHAI_DUONG else 'yaw_manh_trai')
    if pitch is not None:
        a = abs(pitch)
        if PITCH_VUA <= a < PITCH_LECH:
            t.add('pitch_vua')
        elif a >= PITCH_LECH:
            t.add('pitch_len' if (pitch > 0) == PITCH_LEN_DUONG else 'pitch_xuong')
    if roll is not None and abs(roll) >= ROLL_NGHIENG:
        t.add('nghieng_dau')
    glasses = c.get('glasses')
    if glasses == 'glasses':
        t.add('kinh_can')
    elif glasses == 'sunglasses':
        t.add('kinh_ram')
    jaw = _num(c.get('jaw_crop'))
    if jaw is None:
        jaw = _num(c.get('jaw_open'))
    if jaw is not None:
        if jaw >= JAW_NGAP:
            t.add('ngap_rong')
        elif jaw >= JAW_NOI:
            t.add('noi')
    bl, br = _num(c.get('blink_l')), _num(c.get('blink_r'))
    if bl is not None and br is not None and glasses != 'sunglasses' and (yaw is None or abs(yaw) < BLINK_YAW_MAX):   # kính râm / mặt nghiêng: blendshape mắt vô nghĩa
        b = min(bl, br)
        if b >= BLINK_NHAM:
            t.add('mat_nham')
        elif b >= BLINK_LIM:
            t.add('lim_dim')
    luma, bright = _num(c.get('luma')), _num(c.get('bright_frac'))
    if luma is not None and luma < LUMA_TOI:
        t.add('toi')
    if (luma is not None and luma > LUMA_SANG) or (bright is not None and bright > BRIGHT_FRAC_SANG):
        t.add('sang_chay')
    ct = _num(c.get('contrast'))
    if ct is not None and ct < CONTRAST_THAP:
        t.add('tuong_phan_thap')
    lv = _num(c.get('lap_var'))
    if lv is not None and lv < ii.BLUR_LAP_VAR.get(c.get('source'), ii.BLUR_LAP_VAR['yawdd']):
        t.add('mo')
    canh = _num(c.get('canh_mat_px'))
    if canh is None and all(_num(c.get(k)) is not None for k in ('x0', 'y0', 'x1', 'y1')):
        canh = max(_num(c['x1']) - _num(c['x0']), _num(c['y1']) - _num(c['y0']))
    if canh is not None and canh < MAT_NHO_PX:
        t.add('mat_nho')
    if c.get('source') == 'yawdd' and hair_of(c.get('video', '')):
        t.add('rau')
    pad = _num(c.get('pad_frac'))
    if pad is not None and pad > PAD_SAT_MEP:
        t.add('sat_mep')
    cam = c.get('camera')
    if cam in ('dash', 'mirror', 'drivface'):
        t.add('cam_' + cam)
    return [x for x in THE_THU_TU if x in t]


def tinh_diem(tags):
    return sum(THE_DIEM.get(x, 0.0) for x in tags)


def tinh_muc(tags, yaw=None):
    """Mức khó từ các thẻ: dễ S <= 0,5 (và không thẻ hiếm); vừa 1..2,5; khó 3..4,5; rất khó S >= 5, hoặc tay che mắt, hoặc |yaw| >= 45,
    hoặc kính râm cộng một yếu tố >= 1,5."""
    s = tinh_diem(tags)
    nang = 'kinh_ram' in tags and any(THE_DIEM.get(x, 0.0) >= 1.5 for x in tags if x != 'kinh_ram')
    if s >= 5 or 'che_tay_mat' in tags or (yaw is not None and abs(yaw) >= YAW_RAT_KHO) or nang:
        return 'rat_kho'
    if s >= 3:
        return 'kho'
    if s >= 1 or any(x in THE_HIEM for x in tags):
        return 'vua'
    return 'de'


def doc_sua_the(path):
    """File sửa thẻ: {ứng viên: dict(them=set, bo=set, loai=bool, ghi_chu=[...])}. Dòng bắt đầu bằng # và dòng trống bị bỏ. Các dòng cùng ứng viên cộng dồn,
    quyết định sau đè quyết định trước (loai sau giu thì thành giu)."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding='utf-8-sig', newline='') as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith('#')]
    for r in csv.DictReader(io.StringIO(''.join(lines))):
        name = (r.get('ung_vien') or '').strip()
        if not name:
            continue
        e = out.setdefault(name, dict(them=set(), bo=set(), loai=False, ghi_chu=[]))
        for key, col in (('them', 'the_them'), ('bo', 'the_bo')):
            for x in re.split(r'[;,\s]+', r.get(col) or ''):
                if x:
                    if x not in THE_DIEM:
                        raise SystemExit(f'--sua-the: thẻ lạ {x!r} (ứng viên {name}); thẻ hợp lệ: {", ".join(THE_THU_TU)}')
                    e[key].add(x)
                    (e['bo'] if key == 'them' else e['them']).discard(x)       # dòng sau đè dòng trước
        qd = (r.get('quyet_dinh') or '').strip().lower()
        if qd not in ('', 'giu', 'loai'):
            raise SystemExit(f'--sua-the: quyet_dinh {qd!r} (ứng viên {name}) phải là giu hoặc loai')
        if qd:
            e['loai'] = qd == 'loai'
            e['loai_ro'] = True
        else:
            e.setdefault('loai_ro', False)
        if (r.get('ghi_chu') or '').strip():
            e['ghi_chu'].append(r['ghi_chu'].strip())
    return out


def sua_cua(sua, r):
    """Gộp sửa thẻ theo tài xế (khoá `subject:<mã>`) rồi sửa theo từng ứng viên (khoá = tên ứng viên); sửa theo ứng viên đè sửa theo tài xế."""
    es = [e for e in (sua.get('subject:' + r.get('subject', '')), sua.get(r['name'])) if e]
    if not es:
        return None
    m = dict(them=set(), bo=set(), loai=False, ghi_chu=[])
    for e in es:
        m['them'] = (m['them'] | e['them']) - e['bo']
        m['bo'] = (m['bo'] | e['bo']) - e['them']
        m['loai'] = e['loai'] if e.get('loai_ro', True) else m['loai']
        m['ghi_chu'] += e['ghi_chu']
    return m


def gan_the(rows, sua):
    """Gắn vào mỗi hàng bảng đo: the (danh sách thẻ sau sửa), the_sua (thẻ đã sửa bằng mắt), diem, muc, loai, ghi_chu_sua, nhap (tot|vua|te).
    Hàng được SỬA TẠI CHỖ và trả về. Thẻ nhap_te/nhap_tot chỉ có khi gán bằng mắt; nhap suy ra từ chúng và flip_nme. Khoá `subject:<mã>` trong sua áp cho
    mọi ứng viên của tài xế đó."""
    for r in rows:
        auto = the_tu_dong(r)
        e = sua_cua(sua, r)
        the = set(auto)
        r['the_sua'] = ''
        if e:
            the |= e['them']
            the -= e['bo']
            r['the_sua'] = ';'.join([f'+{x}' for x in sorted(e['them'])] + [f'-{x}' for x in sorted(e['bo'])])
            if 'che_tay_mat' in e['them']:
                the.add('che_tay')
        r['the'] = [x for x in THE_THU_TU if x in the]
        r['diem'] = tinh_diem(r['the'])
        r['muc'] = tinh_muc(r['the'], _num(r.get('yaw')))
        r['loai'] = bool(e and e['loai'])
        r['ghi_chu_sua'] = ' | '.join(e['ghi_chu']) if e else ''
        nme = _num(r.get('flip_nme'))
        if 'nhap_te' in r['the']:
            r['nhap'] = 'te'
        elif 'nhap_tot' in r['the'] or (nme is not None and nme <= NHAP_TOT_NME):
            r['nhap'] = 'tot'
        else:
            r['nhap'] = 'vua'
    return rows


def doc_bang(path):
    """Đọc cache/bang_do.csv: ép kiểu số, tách mp_ok / moi thành bool/int."""
    rows = doc_csv(path)
    for r in rows:
        for k in SO_COT:
            if k in r:
                r[k] = _num(r[k])
        for k in ('moi', 'mp_ok', 'mp_flip_ok'):
            r[k] = int(_num(r.get(k), 0) or 0)
        r['hash'] = int(r['hash']) if r.get('hash') not in (None, '') else None
    return rows


# ======================================================================================================================
# Đo trên ảnh cắt (cần cv2 + MediaPipe; phần chọn/đóng gói bên dưới không cần)
# ======================================================================================================================
def _blend(blend, name):
    for c in blend or []:
        if getattr(c, 'category_name', None) == name:
            return float(c.score)
    return None


class BlendDetector(ii.FaceDetector):
    """Như inc_ingest.FaceDetector (không sửa lớp đó) nhưng cất thêm blendshape eyeBlinkLeft / eyeBlinkRight / jawOpen của mặt lớn nhất.
    Lưu ý eyeBlinkLeft là mắt TRÁI CỦA NGƯỜI, tức thường nằm nửa PHẢI ảnh; thẻ mắt nhắm dùng min của hai mắt nên không phụ thuộc bên."""

    def _run(self, lm, rgb):
        res = lm.detect(self.wrap(rgb))
        self.extra = None
        if not res.face_landmarks:
            return None
        h, w = rgb.shape[:2]
        faces = [[[p.x * w, p.y * h] for p in face] for face in res.face_landmarks]
        i = max(range(len(faces)), key=lambda j: np.ptp(np.asarray(faces[j]), axis=0).prod())
        mats = getattr(res, 'facial_transformation_matrixes', None)
        blend = getattr(res, 'face_blendshapes', None)
        b = blend[i] if blend is not None and len(blend) > i else []
        self.extra = dict(matrix=np.asarray(mats[i], float) if mats is not None and len(mats) > i else None,
                          jaw_open=_blend(b, 'jawOpen'), blink_l=_blend(b, 'eyeBlinkLeft'), blink_r=_blend(b, 'eyeBlinkRight'))
        return faces[i]


def make_hand_landmarker(path):
    """HandLandmarker của MediaPipe (tuỳ chọn, Apache-2.0; file model để ngoài git). CHỈ dùng trong tao_bo200.py để GỢI Ý ứng viên che tay, không vào tool/m28.py."""
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    opts = vision.HandLandmarkerOptions(base_options=mp_python.BaseOptions(model_asset_path=path),
                                        running_mode=vision.RunningMode.IMAGE, num_hands=2)
    return vision.HandLandmarker.create_from_options(opts)


def hand_boxes(hl, rgb):
    """Hộp bao (x0, y0, x1, y1, pixel) của từng bàn tay MediaPipe thấy trong ảnh."""
    res = hl.detect(ii._mp_image(rgb))
    h, w = rgb.shape[:2]
    out = []
    for hand in res.hand_landmarks or []:
        xs, ys = [p.x * w for p in hand], [p.y * h for p in hand]
        out.append((min(xs), min(ys), max(xs), max(ys)))
    return out


def box_inter_frac(a, b):
    """Phần diện tích hộp b nằm trong hộp a."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max((b[2] - b[0]) * (b[3] - b[1]), 1e-9)
    return ix * iy / area


def box_iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def flip_nme_of(p50, p50f, names, iod_pair):
    """Trung bình khoảng cách hai bộ 50 điểm (gốc và lật đã bỏ lật) chia IOD, % IOD: cùng cách `steps.flags` so sánh."""
    o = np.array([p50[n] for n in names], float)
    f = np.array([p50f[n] for n in names], float)
    iod = float(np.linalg.norm(np.array(p50[iod_pair[0]]) - np.array(p50[iod_pair[1]]))) or 1.0
    return float(np.mean(np.linalg.norm(o - f, axis=1) / iod) * 100)


_G = {}


def _init_worker(model, hand_model, cfg_path, map_path, df_refs):
    _G['lm'] = steps.make_landmarker(model, num_faces=5, outputs=True)
    _G['det'] = BlendDetector(_G['lm'])
    _G['hand'] = make_hand_landmarker(hand_model) if hand_model else None
    with open(cfg_path, encoding='utf-8') as f:
        _G['cfg'] = json.load(f)
    with open(map_path, encoding='utf-8') as f:
        _G['map'] = json.load(f)
    _G['df'] = df_refs or {}


def do_measure(t, G=None):
    """Đo MỘT ứng viên trên ảnh cắt 512 (cắt bằng cat_mat.square_crop, hộp x0..y1 như inc_ingest.split). Trả dict JSON-được."""
    G = G or _G
    out = dict(name=t['name'])
    bgr = cv2.imread(t['path'])
    if bgr is None:
        return dict(out, err='khong_doc_duoc_khung')
    box = tuple(float(v) for v in t['box'])
    crop, _, (left, top, k), _ = square_crop(bgr, box, np.zeros((1, 2), np.float32))
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    out['hash'] = ii.measure_face(bgr, np.array([[box[0], box[1]], [box[2], box[3]]], float), None, None)['hash']
    res = G['det'].detect(rgb)
    out['mp_ok'] = int(res is not None)
    if G.get('hand') is not None:
        hb = hand_boxes(G['hand'], rgb)
        exp = ((box[0] - left) * k, (box[1] - top) * k, (box[2] - left) * k, (box[3] - top) * k)
        out['hand_n'] = len(hb)
        out['hand_cov'] = round(max([box_inter_frac(h, exp) for h in hb] or [0.0]), 3)
    if res is None:
        return out
    cfg, mp_map = G['cfg'], G['map']
    names = [p['name'] for p in cfg['points']]
    pts = np.asarray(res['pts'], float)
    exp = ((box[0] - left) * k, (box[1] - top) * k, (box[2] - left) * k, (box[3] - top) * k)
    out['box_iou'] = round(box_iou((*pts.min(0), *pts.max(0)), exp), 3)
    out.update(jaw_crop=None if res.get('jaw_open') is None else round(res['jaw_open'], 4),
               blink_l=None if res.get('blink_l') is None else round(res['blink_l'], 4),
               blink_r=None if res.get('blink_r') is None else round(res['blink_r'], 4))
    p50 = mapping.apply_map(pts, mp_map, cfg, flipped=False)
    out['p50'] = [[round(p50[n][0], 2), round(p50[n][1], 2)] for n in names]
    pf = steps.run_mp_padded(G['lm'], rgb[:, ::-1])
    out['mp_flip_ok'] = int(pf is not None)
    if pf is not None:
        p50f = mapping.apply_map(np.asarray(pf, float), mp_map, cfg, flipped=True)
        out['p50f'] = [[round(p50f[n][0], 2), round(p50f[n][1], 2)] for n in names]
        out['flip_nme'] = round(flip_nme_of(p50, p50f, names, cfg['iod_points']), 3)
    ref = G['df'].get(t.get('video'))
    if ref is not None:
        try:
            to_frame = {n: np.asarray(v, float) / k + [left, top] for n, v in p50.items()}
            five = cd.ours_five(to_frame, cfg, pts / k + [left, top])
            err = cd.point_errors(five, ref)
            if err:
                out['df_err'] = round(float(np.mean(list(err.values()))), 3)
        except (KeyError, ValueError, IndexError):
            pass
    return out


def _measure_safe(t):
    try:
        return do_measure(t)
    except Exception as e:                                           # một ứng viên lỗi không làm hỏng cả lượt
        return dict(name=t['name'], err=f'{type(e).__name__}: {e}')


def ung_vien_tat_ca(a):
    """Ứng viên cũ (candidates.csv) + khung trích thêm (<out>/cache/new/candidates_new.csv, nếu có). Mỗi hàng thêm moi (0/1) và khung_path."""
    rows = doc_csv(a.candidates)
    frames = a.frames or os.path.join(os.path.dirname(os.path.abspath(a.candidates)), 'frames')
    for r in rows:
        r['moi'] = 0
        r['khung_path'] = os.path.join(frames, r['name'] + '.jpg')
    newp = os.path.join(a.out, 'cache', 'new', 'candidates_new.csv')
    if os.path.exists(newp):
        for r in doc_csv(newp):
            r['moi'] = 1
            r['khung_path'] = os.path.join(a.out, 'cache', 'new', 'frames', r['name'] + '.jpg')
            rows.append(r)
    names = Counter(r['name'] for r in rows)
    dup = [n for n, c in names.items() if c > 1]
    if dup:
        raise SystemExit(f'tên ứng viên trùng giữa cũ và mới: {dup[:3]}')
    return rows


def doc_drivface_ref(drivface_dir):
    """{tên ảnh (bỏ dấu cách) -> 5 điểm mốc theo bên của ảnh} để tính df_err; thư mục None thì {}."""
    if not drivface_dir:
        return {}
    rows = cd.read_drivpoints(os.path.join(drivface_dir, 'drivPoints.txt'))
    eye, mouth, _ = cd.side_convention(rows)
    re_left = eye > 0.9 and mouth > 0.9
    if not (re_left or (eye < 0.1 and mouth < 0.1)):
        return {}
    return {r['name'].strip().replace(' ', '') + '.jpg': cd.image_side_ref(r['pts'], re_left) for r in rows}


def doc_do_jsonl(out):
    d = {}
    p = os.path.join(out, 'cache', 'do.jsonl')
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            for ln in f:
                if ln.strip():
                    try:
                        r = json.loads(ln)
                    except ValueError:
                        continue                                       # dòng cuối ghi dở khi bị ngắt: bỏ, đo lại
                    d[r['name']] = r
    return d


def map_trung_616(path):
    """{(video, khung): tên file trong gói 616}."""
    if not path or not os.path.exists(path):
        return {}
    return {(r['video'], str(int(float(r['frame'])))): r['file'] for r in doc_csv(path)}


def ghi_bang_do(a, rows, meas):
    """Gộp ứng viên + số đo thành cache/bang_do.csv (đầu vào của `chon`)."""
    trung = map_trung_616(a.manifest616)
    outrows = []
    for r in rows:
        m = meas.get(r['name'], {})
        o = {c: r.get(c, '') for c in CSV_BANG}
        o['moi'] = r['moi']
        o['khung'] = ii.frame_rel(r)
        x0, y0, x1, y1 = (float(r[k]) for k in ('x0', 'y0', 'x1', 'y1'))
        o['canh_mat_px'] = round(max(x1 - x0, y1 - y0), 1)
        o['trung_goi616'] = trung.get((r['video'], str(int(float(r['frame'])))), '')
        for c in ('mp_ok', 'mp_flip_ok', 'blink_l', 'blink_r', 'jaw_crop', 'flip_nme', 'df_err', 'hand_n', 'hand_cov', 'box_iou', 'hash'):
            o[c] = '' if m.get(c) is None else m[c]
        if m and not m.get('mp_ok'):
            o['mp_ok'] = 0
        outrows.append(o)
    ghi_csv(os.path.join(a.out, 'cache', 'bang_do.csv'), CSV_BANG, outrows)
    return outrows


def cmd_do(a):
    """Đo mọi ứng viên trên ảnh cắt, làm tiếp được (cache/do.jsonl theo từng ứng viên), rồi ghi cache/bang_do.csv."""
    import multiprocessing as mp
    a.out = check_out_dir(a.out)
    os.makedirs(os.path.join(a.out, 'cache'), exist_ok=True)
    rows = ung_vien_tat_ca(a)
    with open(os.path.join(a.out, 'cache', 'do_meta.json'), 'w', encoding='utf-8') as f:     # để luoi/goi biết thư mục khung cũ mà không cần nhớ tham số
        json.dump(dict(frames=os.path.abspath(a.frames or os.path.join(os.path.dirname(os.path.abspath(a.candidates)), 'frames')),
                       candidates=os.path.abspath(a.candidates)), f)
    meas = {} if a.fresh else doc_do_jsonl(a.out)
    if a.fresh and os.path.exists(os.path.join(a.out, 'cache', 'do.jsonl')):
        os.remove(os.path.join(a.out, 'cache', 'do.jsonl'))
    todo = [r for r in rows if r['name'] not in meas or 'err' in meas[r['name']]]
    if a.limit:
        todo = todo[:a.limit]
    ghi_nhat_ky(a.out, f'do: {len(rows)} ứng viên ({sum(r["moi"] for r in rows)} khung mới), đã đo {len(meas)}, cần đo {len(todo)}, {a.jobs} tiến trình')
    df_refs = doc_drivface_ref(a.drivface)
    hand_model = a.hand_model if a.hand_model and os.path.exists(a.hand_model) else None
    if a.hand_model and not hand_model:
        ghi_nhat_ky(a.out, f'CẢNH BÁO: không thấy --hand-model {a.hand_model}, bỏ gợi ý tay che')
    tasks = [dict(name=r['name'], path=r['khung_path'], video=r['video'] if r['source'] == 'drivface' else None,
                  box=[float(r[k]) for k in ('x0', 'y0', 'x1', 'y1')]) for r in todo]
    cfg = os.path.join(a.project, 'config', 'm28_config.json')
    mp_map = os.path.join(a.project, 'config', 'map_mp50.json')
    initargs = (a.model, hand_model, cfg, mp_map, df_refs)
    if tasks:
        path = os.path.join(a.out, 'cache', 'do.jsonl')
        with open(path, 'a', encoding='utf-8') as f:
            if a.jobs <= 1:
                _init_worker(*initargs)
                it = map(_measure_safe, tasks)
                pool = None
            else:
                pool = mp.get_context('spawn').Pool(a.jobs, initializer=_init_worker, initargs=initargs)
                it = pool.imap(_measure_safe, tasks, chunksize=4)
            try:
                for n, res in enumerate(it, 1):
                    f.write(json.dumps(res, ensure_ascii=False) + '\n')
                    meas[res['name']] = res
                    if n % 100 == 0 or n == len(tasks):
                        f.flush()
                        ghi_nhat_ky(a.out, f'  do {n}/{len(tasks)}')
            finally:
                if pool is not None:
                    pool.terminate()
                    pool.join()
                elif _G.get('lm') is not None:
                    _G['lm'].close()
    out = ghi_bang_do(a, rows, meas)
    err = [r['name'] for r in out if 'err' in meas.get(r['name'], {})]
    ghi_nhat_ky(a.out, f'do xong: {len(out)} hàng; mp_ok {sum(int(r["mp_ok"] or 0) for r in out)}, mp_flip_ok {sum(int(r["mp_flip_ok"] or 0) for r in out)}, '
                       f'lỗi đo {len(err)} {err[:3]}')
    return out


# ======================================================================================================================
# Chọn 200 ảnh (THUẦN: chỉ dùng bảng đo + sửa thẻ + seed)
# ======================================================================================================================
def doc_quota(text):
    """'de=40,vua=70,kho=60,rat_kho=30' -> dict; SystemExit nếu sai."""
    q = {}
    for part in str(text).split(','):
        k, _, v = part.partition('=')
        k = k.strip()
        if k not in LEVELS or not v.strip().isdigit():
            raise SystemExit(f'--quota sai ở {part!r}: dạng de=40,vua=70,kho=60,rat_kho=30')
        q[k] = int(v)
    miss = [k for k in LEVELS if k not in q]
    if miss:
        raise SystemExit(f'--quota thiếu mức {miss}')
    return q


def vkey(c):
    """Khoá 'cùng video' để giới hạn số ảnh: YawDD = video; DrivFace = từng ảnh (khoảng cách do DF_MIN_GAP_IMGS lo)."""
    return (c['source'], c['video'] if c['source'] == 'yawdd' else c['name'])


def gap_ok(c, d):
    """Hai ứng viên cùng nguồn gốc (cùng video YawDD / cùng tài xế DrivFace) có đủ xa nhau không."""
    if c['source'] != d['source']:
        return True
    if c['source'] == 'yawdd':
        if c['video'] != d['video']:
            return True
        return abs(_num(c['t_s'], 0.0) - _num(d['t_s'], 0.0)) >= MIN_GAP_S - 1e-6
    if c['subject'] != d['subject']:
        return True
    return abs(_num(c['frame'], 0.0) - _num(d['frame'], 0.0)) >= DF_MIN_GAP_IMGS


def hash_ok(c, d):
    """Cùng tài xế thì dHash phải khác đủ xa (không hai ảnh gần trùng, kể cả khác video)."""
    if c['subject'] != d['subject']:
        return True
    if c.get('hash') is None or d.get('hash') is None:
        return True
    return ii.hamming(c['hash'], d['hash']) >= ii.DHASH_MIN_DIST


class Chon:
    """Trạng thái một lần chọn: giữ danh sách đã chọn và mọi bộ đếm để kiểm luật cứng nhanh."""

    def __init__(self, quota, k, max_te=N_NHAP_TE):
        self.quota, self.k, self.max_te = dict(quota), k, max_te
        self.items = []
        self.by_subject = defaultdict(list)
        self.by_video = defaultdict(list)
        self.by_level = Counter()
        self.by_tag = Counter()
        self.by_camera = Counter()
        self.by_gender = Counter()
        self.names = set()

    def can_add(self, c):
        if c['name'] in self.names or self.by_level[c['muc']] >= self.quota.get(c['muc'], 0):
            return False
        if 'nhap_te' in c['the'] and self.by_tag['nhap_te'] >= self.max_te:          # chừa 8-10 ảnh nháp tệ, không nhiều hơn
            return False
        if len(self.by_subject[c['subject']]) >= self.k:
            return False
        if len(self.by_video[vkey(c)]) >= (MAX_PER_VIDEO if c['source'] == 'yawdd' else 10 ** 6):
            return False
        same = self.by_subject[c['subject']]
        return all(gap_ok(c, d) and hash_ok(c, d) for d in same)

    def add(self, c):
        self.items.append(c)
        self.names.add(c['name'])
        self.by_subject[c['subject']].append(c)
        self.by_video[vkey(c)].append(c)
        self.by_level[c['muc']] += 1
        self.by_tag.update(c['the'])
        self.by_camera[c['camera']] += 1
        if c['gender'] in ('F', 'M'):
            self.by_gender[c['gender']] += 1

    def n(self):
        return len(self.items)

    def con_thieu(self):
        return {m: self.quota[m] - self.by_level[m] for m in LEVELS if self.by_level[m] < self.quota[m]}


def diem_chon(c, st, rng, jit, n_total, tags_can=(), tag_target=TARGET_THE, scarce=None):
    """Điểm ưu tiên khi chọn ứng viên c (càng cao càng nên chọn): ngẫu nhiên theo seed + phủ thẻ hiếm còn thiếu (thẻ càng hiếm trong nhóm càng nặng: scarce[thẻ])
    + cân bằng giới/camera/tài xế - phạt mạnh ứng viên trùng gói 616."""
    s = jit[c['name']]
    s += 0.7 * sum((scarce or {}).get(t, 1.0) for t in c['the'] if t in tags_can and st.by_tag[t] < tag_target)
    s += 0.5 * (1 - len(st.by_subject[c['subject']]) / max(st.k, 1))
    tot = max(st.n(), 1)
    lo, hi = SHARE_TARGET.get(c['camera'], (0.0, 1.0))
    share = st.by_camera[c['camera']] / tot
    s += 0.6 if share < (lo + hi) / 2 else (-0.6 if share > hi else 0.0)
    if c['gender'] in ('F', 'M'):
        known = max(sum(st.by_gender.values()), 1)
        mine = st.by_gender[c['gender']] / known
        s += 0.5 if mine < 0.5 else (-0.5 if mine > FEMALE_RANGE[1] else 0.0)
    if c['source'] == 'drivface':
        s += -3.0 if st.by_camera['drivface'] >= DF_RANGE[1] else 0.0
    if c.get('trung_goi616'):
        s -= 5.0
    return s


def chon_mot_lan(pool, seed, quota, k, min_the=MIN_THE, n_te=N_NHAP_TE, target_the=TARGET_THE):
    """Một lần chọn với seed này. Trả Chon hoặc None khi không đủ hạn mức mức. Thứ tự: nháp tệ -> thẻ hiếm (hiếm nhất trước) -> lấp từng mức."""
    rng = random.Random(seed)
    jit = {c['name']: rng.random() for c in pool}
    st = Chon(quota, k, max_te=n_te)
    ordered = sorted(pool, key=lambda c: c['name'])                    # thứ tự cố định, độc lập thứ tự đọc file

    avail = {t: sum(1 for c in pool if t in c['the']) for t in THE_HIEM}
    scarce = {t: min(4.0, 20.0 / max(avail[t], 1)) for t in THE_HIEM}

    def pick_best(cands, tags_can=()):
        best, bs = None, None
        for c in cands:
            if st.can_add(c):
                sc = diem_chon(c, st, rng, jit, N_ANH, tags_can, scarce=scarce)
                if bs is None or sc > bs:
                    best, bs = c, sc
        return best

    te_pool = [c for c in ordered if 'nhap_te' in c['the'] and c['muc'] in ('kho', 'rat_kho')]
    while sum(1 for c in st.items if 'nhap_te' in c['the']) < n_te and te_pool:
        c = pick_best(te_pool, THE_HIEM)
        if c is None:
            break
        st.add(c)
    for t in sorted(THE_HIEM, key=lambda x: (avail[x], x)):
        cand = [c for c in ordered if t in c['the']]
        while st.by_tag[t] < target_the and cand:
            c = pick_best(cand, THE_HIEM)
            if c is None:
                break
            st.add(c)
    for m in ('rat_kho', 'kho', 'vua', 'de'):
        cand = [c for c in ordered if c['muc'] == m]
        while st.by_level[m] < quota[m]:
            c = pick_best(cand, THE_HIEM)
            if c is None:
                return None
            st.add(c)
    return st


def khong_dat(st, pool, min_the=MIN_THE, n_te_min=MIN_NHAP_TE):
    """Danh sách lỗi LUẬT CỨNG của một lần chọn (rỗng = đạt). Thẻ hiếm thiếu chỉ là lỗi khi nhóm ứng viên có đủ (còn không thì vào danh sách thẻ thiếu)."""
    err = []
    for m in LEVELS:
        if st.by_level[m] != st.quota[m]:
            err.append(f'mức {m}: {st.by_level[m]}/{st.quota[m]}')
    for t in THE_HIEM:
        have = sum(1 for c in pool if t in c['the'])
        if have >= min_the and st.by_tag[t] < min_the:
            err.append(f'thẻ {t}: {st.by_tag[t]} < {min_the} (nhóm ứng viên có {have})')
    n_te = sum(1 for c in st.items if 'nhap_te' in c['the'])
    if sum(1 for c in pool if 'nhap_te' in c['the'] and c['muc'] in ('kho', 'rat_kho')) >= n_te_min and n_te < n_te_min:
        err.append(f'nháp tệ: {n_te} < {n_te_min}')
    return err


def phat_can_bang(st):
    """Điểm phạt độ cân bằng (càng nhỏ càng tốt; mục tiêu mềm, không phải luật cứng)."""
    n = max(st.n(), 1)
    pen = 0.0
    known = sum(st.by_gender.values())
    if known:
        f = st.by_gender['F'] / known
        pen += 20 * (max(0.0, FEMALE_RANGE[0] - f) + max(0.0, f - FEMALE_RANGE[1]))
    for cam, (lo, hi) in SHARE_TARGET.items():
        s = st.by_camera[cam] / n
        pen += 20 * (max(0.0, lo - s) + max(0.0, s - hi))
    pen += 0.5 * max(0, MIN_SUBJECTS - len({c['subject'] for c in st.items}))
    df = st.by_camera['drivface']
    pen += 2.0 * (max(0, DF_RANGE[0] - df) + max(0, df - DF_RANGE[1]))
    for m in LEVELS:
        rows = [c for c in st.items if c['muc'] == m]
        if rows:
            pen += 3.0 * (len({c['gender'] for c in rows} - {'unknown'}) < 2) + 3.0 * (len({c['camera'] for c in rows}) < 2)
    pen += 0.3 * sum(max(0, TARGET_THE - st.by_tag[t]) for t in THE_HIEM)
    out616 = sum(1 for c in st.items if not c.get('trung_goi616')) / n
    pen += 100 * max(0.0, OUT_616_MIN - out616)
    pen += 0.05 * sum(len(v) ** 2 for v in st.by_subject.values())
    return pen


def chon(rows, seed, quota=None, k=K_PER_SUBJECT, min_the=MIN_THE, max_tries=SEEDS_TRIED, n_good=SEEDS_GOOD, n_te=N_NHAP_TE, log=None):
    """Chọn bộ ảnh từ các hàng ĐÃ gan_the. Thử seed, seed + 1, ...; lấy n_good lần ĐẠT luật cứng đầu tiên rồi chọn lần có phat_can_bang nhỏ nhất
    (hoà thì seed nhỏ hơn). Trả dict(items, seed_goc, seed_dung, pool, phat, thu, dat, loi_gan_nhat)."""
    quota = dict(quota or QUOTA)
    pool = [r for r in rows if r['mp_ok'] and not r['loai']]
    good, last_err, tried = [], [], 0
    for t in range(max_tries):
        st = chon_mot_lan(pool, seed + t, quota, k, min_the, n_te)
        tried += 1
        if st is None:
            last_err = ['không đủ ứng viên cho một mức (quota)']
            continue
        err = khong_dat(st, pool, min_the)
        if err:
            last_err = err
            continue
        good.append((phat_can_bang(st), seed + t, st))
        if log:
            log(f'  seed {seed + t}: đạt luật cứng, điểm phạt {good[-1][0]:.2f}')
        if len(good) >= n_good:
            break
    if not good:
        raise SystemExit(f'không chọn được bộ {sum(quota.values())} ảnh đạt luật cứng sau {tried} lần thử (seed {seed}..{seed + tried - 1}); lỗi gần nhất: {last_err}')
    pen, used, st = min(good, key=lambda g: (g[0], g[1]))
    return dict(items=st.items, state=st, seed_goc=seed, seed_dung=used, pool=pool, phat=pen, thu=tried, dat=len(good))


def the_thieu(items, pool, min_the=MIN_THE, target=TARGET_THE):
    """Thẻ hiếm chưa đủ: [(thẻ, có trong bộ, cần, số ứng viên trong nhóm gốc, lý do)] (rỗng nếu mọi thẻ >= min_the)."""
    cnt = Counter(t for c in items for t in c['the'])
    out = []
    for t in THE_HIEM:
        if cnt[t] < min_the:
            have = sum(1 for c in pool if t in c['the'])
            out.append((t, cnt[t], min_the, have, f'nhóm ứng viên chỉ có {have} ảnh mang thẻ này (sau loại/sửa thẻ)' if have < min_the
                        else 'ràng buộc tài xế/video/hạn mức mức không cho thêm'))
    return out


# ---------- đánh số ----------
def chon_khoi_dong(items, rng, n=N_WARMUP):
    """Hai ảnh khởi động: ảnh dễ nhất (nhìn thẳng, mắt mở, miệng khép, đủ sáng, không kính), khác tài xế, khác giới nếu được, không DrivFace.
    Chọn ngẫu nhiên theo seed trong nhóm đạt chuẩn nghiêm nhất còn >= 6 ảnh (nới dần chuẩn nếu thiếu). Trả list ứng viên."""
    de = [c for c in items if c['muc'] == 'de' and c['source'] == 'yawdd']

    def strict(level):
        out = []
        for c in de:
            if level >= 0 and (c['diem'] > 0 or c['glasses'] != 'none' or 'nhap_te' in c['the']):
                continue
            if level >= 1 and not (abs(_num(c.get('yaw'), 99)) < 15 and abs(_num(c.get('pitch'), 99)) < 10):
                continue
            if level >= 2 and not (90 <= _num(c.get('luma'), 0) <= 150 and _num(c.get('contrast'), 0) >= 40):
                continue
            out.append(c)
        return out

    cand = []
    for level in (2, 1, 0):
        cand = strict(level)
        if len({c['subject'] for c in cand}) >= 6:
            break
    if len({c['subject'] for c in cand}) < n:
        cand = sorted(de, key=lambda c: (c['diem'], abs(_num(c.get('yaw'), 99)) + abs(_num(c.get('pitch'), 99)), c['name']))[:12]
    cand = sorted(cand, key=lambda c: c['name'])
    rng.shuffle(cand)
    pick = []
    for want_other_gender in (True, False):
        pick = []
        for c in cand:
            if all(c['subject'] != d['subject'] for d in pick) and (not want_other_gender or not pick or c['gender'] != pick[0]['gender']):
                pick.append(c)
            if len(pick) == n:
                break
        if len(pick) == n:
            break
    if len(pick) < n:
        raise SystemExit(f'không tìm được {n} ảnh khởi động dễ, khác tài xế')
    return pick


def chia_khoi(resto, rng, n_blocks=N_BLOCKS, max_te=MAX_TE_PER_BLOCK):
    """Chia các ảnh còn lại vào n_blocks khối liên tiếp: sắp theo mức rồi chia vòng (mỗi mức rải đều: số ảnh mỗi mức ở mỗi khối chỉ lệch 1),
    ảnh nháp tệ đứng đầu mỗi mức khó nên rơi vào các khối khác nhau. Trả list khối (list ứng viên) hoặc None nếu có khối > max_te ảnh nháp tệ."""
    n = len(resto)
    rot = rng.randrange(n_blocks)
    seq = []
    for m in LEVELS:
        run = [c for c in resto if c['muc'] == m]
        rng.shuffle(run)
        run.sort(key=lambda c: 0 if 'nhap_te' in c['the'] else 1)
        seq += run
    blocks = [[] for _ in range(n_blocks)]
    for i, c in enumerate(seq):
        blocks[(i + rot) % n_blocks].append(c)
    # kích thước các khối chênh nhau tối đa 1; muốn khối đầu dài hơn thì dịch vòng để khối n % n_blocks đầu có thêm
    blocks.sort(key=lambda b: -len(b))
    for b in blocks:
        rng.shuffle(b)
    if any(sum(1 for c in b if 'nhap_te' in c['the']) > max_te for b in blocks):
        return None
    order = list(range(n_blocks))
    rng.shuffle(order)
    sizes = sorted((len(b) for b in blocks), reverse=True)
    if sizes[0] - sizes[-1] > 1:
        return None
    return [blocks[i] for i in order]


def sap_ke_nhau(seq, rng, first_subject=None, tries=400):
    """Hoán vị trong seq (không đổi tập) sao cho không hai ảnh liền nhau cùng tài xế (và ảnh đầu khác first_subject). Trả list mới hoặc None."""
    seq = list(seq)

    def bad(i):
        prev = first_subject if i == 0 else seq[i - 1]['subject']
        return prev is not None and seq[i]['subject'] == prev

    for _ in range(tries):
        viol = [i for i in range(len(seq)) if bad(i)]
        if not viol:
            return seq
        i = rng.choice(viol)
        j = rng.randrange(len(seq))
        seq[i], seq[j] = seq[j], seq[i]
    return None


def danh_so(items, seed, n_blocks=N_BLOCKS, max_attempts=300):
    """Đánh số 001..N: hai ảnh dễ nhất đứng đầu; phần còn lại xáo theo seed, rải độ khó đều theo vị trí (n_blocks khối liên tiếp), không hai ảnh liền
    nhau cùng tài xế. Tất định theo (items, seed). Trả list ứng viên theo thứ tự số 1..N."""
    base = sorted(items, key=lambda c: c['name'])
    for att in range(max_attempts):
        rng = random.Random(f'{seed}/{att}')
        warm = chon_khoi_dong(base, rng)
        rest = [c for c in base if c['name'] not in {w['name'] for w in warm}]
        blocks = chia_khoi(rest, rng, n_blocks)
        if blocks is None:
            continue
        seq, prev, ok = list(warm), warm[-1]['subject'], True
        for b in blocks:
            b2 = sap_ke_nhau(b, rng, prev)
            if b2 is None:
                ok = False
                break
            seq += b2
            prev = b2[-1]['subject']
        if ok and all(seq[i]['subject'] != seq[i + 1]['subject'] for i in range(len(seq) - 1)):
            return seq
    raise SystemExit(f'không đánh số được sau {max_attempts} lần thử (seed {seed}): kiểm số ảnh nháp tệ và phân bố tài xế')


# ======================================================================================================================
# Lưới ảnh để kiểm bằng mắt (cần cv2)
# ======================================================================================================================
def thu_muc_khung(a):
    """Thư mục khung ứng viên cũ: --frames, hoặc suy từ --candidates, hoặc lấy từ cache/do_meta.json do `do` ghi."""
    if getattr(a, 'frames', None):
        return a.frames
    if getattr(a, 'candidates', None):
        return os.path.join(os.path.dirname(os.path.abspath(a.candidates)), 'frames')
    p = os.path.join(a.out, 'cache', 'do_meta.json')
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            return json.load(f)['frames']
    raise SystemExit('không biết thư mục khung ứng viên: truyền --frames hoặc --candidates (hoặc chạy `do` trước để có cache/do_meta.json)')


def duong_khung(a, r, frames=None):
    if r.get('moi'):
        return os.path.join(a.out, 'cache', 'new', 'frames', r['name'] + '.jpg')
    return os.path.join(frames or thu_muc_khung(a), r['name'] + '.jpg')


def cat_anh(a, r, frames=None):
    """Ảnh cắt 512 x 512 của một hàng bảng đo: ĐÚNG cat_mat.square_crop với hộp x0..y1 trên khung gốc (như inc_ingest.split)."""
    bgr = cv2.imread(duong_khung(a, r, frames))
    if bgr is None:
        raise SystemExit(f'không đọc được khung {duong_khung(a, r, frames)}')
    box = tuple(float(r[k]) for k in ('x0', 'y0', 'x1', 'y1'))
    return square_crop(bgr, box, np.zeros((1, 2), np.float32))[0]


def tai_bang(a):
    """Bảng đo + sửa thẻ: các hàng đã gan_the."""
    path = os.path.join(a.out, 'cache', 'bang_do.csv')
    if not os.path.exists(path):
        raise SystemExit(f'chưa có {path}: chạy `do` trước')
    return gan_the(doc_bang(path), doc_sua_the(a.sua_the))


_WHERE = re.compile(r'^\s*(\w+)\s*(>=|<=|==|!=|>|<)\s*(\S+)\s*$')


def loc_where(rows, conds):
    """Lọc theo điều kiện kiểu 'yaw>=40', 'abs_yaw>=40', 'glasses==sunglasses'. abs_<cột> là trị tuyệt đối."""
    out = rows
    for cond in conds or []:
        m = _WHERE.match(cond)
        if not m:
            raise SystemExit(f'--where {cond!r} sai: dạng cột>=giá_trị')
        col, op, val = m.groups()
        absol = col.startswith('abs_')
        col = col[4:] if absol else col

        def keep(r, col=col, op=op, val=val, absol=absol):
            v = r.get(col)
            fv = _num(val)
            if fv is not None and _num(v) is not None:
                x = abs(_num(v)) if absol else _num(v)
                return {'>=': x >= fv, '<=': x <= fv, '>': x > fv, '<': x < fv, '==': x == fv, '!=': x != fv}[op]
            if op in ('==', '!='):
                return (str(v) == val) == (op == '==')
            return False
        out = [r for r in out if keep(r)]
    return out


def dong_the(tags, width=44):
    """Chia danh sách thẻ thành các dòng <= width ký tự (bỏ thẻ cam_*)."""
    words = [t for t in tags if not t.startswith('cam_')]
    lines, cur = [], ''
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = ''
        cur = (cur + ' ' + w).strip()
    if cur:
        lines.append(cur)
    return lines


def ve_o(img512, lines, cell=256, strip=56, overlay=None, names=None):
    """Một ô lưới: ảnh vuông (cell x cell) + dải chữ bên dưới (không đè lên mặt)."""
    im = cv2.resize(img512, (cell, cell), interpolation=cv2.INTER_AREA)
    if overlay is not None:
        from m28core import mau_nhom
        for n, (x, y) in zip(names, overlay):
            rgb = mau_nhom.dot_rgb(mau_nhom.group_of(n), False)
            cv2.circle(im, (int(round(x * cell / 512)), int(round(y * cell / 512))), max(2, cell // 128), (rgb[2], rgb[1], rgb[0]), -1, cv2.LINE_AA)
    cv2.rectangle(im, (0, 0), (cell - 1, cell - 1), (60, 60, 60), 1)
    bar = np.full((strip, cell, 3), 28, np.uint8)
    for i, ln in enumerate(lines[:5]):
        col = (255, 255, 255) if i == 0 else ((120, 220, 255) if i < len(lines) - 1 or len(lines) <= 2 else (200, 200, 200))
        cv2.putText(bar, ln[:48], (3, 11 + 11 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.32, col, 1, cv2.LINE_AA)
    return np.vstack([im, bar])


def ve_luoi(cells, prefix, cols=6, rows=5, cell=256, strip=56, jpeg_quality=88):
    """cells: [dict(img=ảnh BGR 512, lines=[chữ], overlay=điểm hoặc None, names=tên điểm, key=chuỗi ghi vào csv)]. Chia thành các trang cols x rows.
    Ghi <prefix>_NN.jpg và <prefix>_NN.csv (ô -> key). Trả danh sách file ảnh. Ảnh lưới <= ~1600 px mỗi cạnh."""
    per = cols * rows
    outs = []
    os.makedirs(os.path.dirname(os.path.abspath(prefix)), exist_ok=True)
    for pg in range(max(1, math.ceil(len(cells) / per))):
        chunk = cells[pg * per:(pg + 1) * per]
        if not chunk:
            break
        h = cell + strip
        canvas = np.full((rows * h, cols * cell, 3), 20, np.uint8)
        for i, c in enumerate(chunk):
            o = ve_o(c['img'], c['lines'], cell, strip, c.get('overlay'), c.get('names'))
            r, q = divmod(i, cols)
            canvas[r * h:(r + 1) * h, q * cell:(q + 1) * cell] = o
        path = f'{prefix}_{pg + 1:02d}.jpg'
        cv2.imwrite(path, canvas, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        with open(f'{prefix}_{pg + 1:02d}.csv', 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, lineterminator='\n')
            w.writerow(['o', 'key'])
            w.writerows([i + 1, c['key']] for i, c in enumerate(chunk))
        outs.append(path)
    return outs


def dong_chu(r, so=None, ten=True):
    """Các dòng chữ của một ô: dòng 1 = số hoặc tên, dòng 2 = số đo, các dòng sau = thẻ."""
    def f(k, fmt, d='-'):
        v = _num(r.get(k))
        return d if v is None else format(v, fmt)
    head = f'{so:03d}' if so is not None else r['name']
    if so is not None:
        head += f' {LEVEL_VI[r["muc"]]} S{r["diem"]:g}'
    meas = (f'y{f("yaw", "+.0f")} p{f("pitch", "+.0f")} r{f("roll", "+.0f")} j{f("jaw_crop", ".2f")} b{f("blink_l", ".1f")}/{f("blink_r", ".1f")} '
            f'L{f("luma", ".0f")} n{f("flip_nme", ".1f")}')
    if r.get('hand_cov') not in (None, '') and (_num(r.get('hand_cov')) or 0) >= HAND_COV_GOI_Y:
        meas += f' H{_num(r["hand_cov"]):.2f}'
    return [head, meas] + dong_the(r['the']) + ([] if not r.get('trung_goi616') else ['(trung 616)'])


def cmd_luoi(a):
    """Vẽ lưới ảnh: nguồn bảng đo (lọc bằng --the/--where/--camera/--source/--muc) hoặc bộ đã chọn (--nguon chon). Ghi luoi/<ten>_NN.jpg + .csv."""
    a.out = check_out_dir(a.out)
    rows = tai_bang(a)
    chon_path = os.path.join(a.out, 'cache', 'chon.json')
    so = {}
    if a.nguon == 'chon':
        with open(chon_path, encoding='utf-8') as f:
            order = json.load(f)['thu_tu']
        byname = {r['name']: r for r in rows}
        rows = [byname[n] for n in order]
        so = {n: i + 1 for i, n in enumerate(order)}
    if a.the:
        rows = [r for r in rows if all(t in r['the'] for t in a.the.split(','))]
    if a.camera:
        rows = [r for r in rows if r['camera'] == a.camera]
    if a.source:
        rows = [r for r in rows if r['source'] == a.source]
    if a.muc:
        rows = [r for r in rows if r['muc'] == a.muc]
    if a.subject:
        rows = [r for r in rows if r['subject'] == a.subject]
    rows = [r for r in rows if r['mp_ok']] if a.nguon != 'chon' else rows
    rows = loc_where(rows, a.where)
    if a.sort:
        col, _, d = a.sort.partition(':')
        rows = sorted(rows, key=lambda r: (_num(r.get(col)) is None, (-1 if d == 'desc' else 1) * (_num(r.get(col)) or 0.0), r['name']))
    if a.sample and len(rows) > a.sample:
        rng = random.Random(a.seed)
        rows = sorted(rng.sample(rows, a.sample), key=lambda r: r['name'])
    if a.n:
        rows = rows[a.skip:a.skip + a.n]
    if not rows:
        raise SystemExit('lưới rỗng: không ứng viên nào khớp bộ lọc')
    frames = thu_muc_khung(a)
    meas = doc_do_jsonl(a.out) if a.overlay else {}
    cfg_names = None
    if a.overlay:
        with open(os.path.join(a.project, 'config', 'm28_config.json'), encoding='utf-8') as f:
            cfg_names = [p['name'] for p in json.load(f)['points']]
    cells = []
    for r in rows:
        ov = meas.get(r['name'], {}).get('p50') if a.overlay else None
        cells.append(dict(img=cat_anh(a, r, frames), lines=dong_chu(r, so.get(r['name']) if a.nguon == 'chon' else None, ten=True),
                          overlay=ov, names=cfg_names, key=r['name']))
    prefix = os.path.join(a.out, 'luoi', a.ten)
    for old in glob.glob(prefix + '_[0-9][0-9].*'):
        os.remove(old)
    outs = ve_luoi(cells, prefix, cols=a.cols, rows=a.rows, cell=a.cell)
    ghi_nhat_ky(a.out, f'luoi {a.ten}: {len(rows)} ô -> {len(outs)} ảnh ({outs[0]}...)')
    return outs


# ======================================================================================================================
# Trích thêm khung từ video cho thẻ còn thiếu (lệnh them)
# ======================================================================================================================
STEP_THEM_S = 0.5                       # lấy mẫu dày hơn inc_ingest (1,0 giây)
PER_VIDEO_THEM = 6                      # mỗi video giữ thêm tối đa ngần này khung
CAN_THEM = 40                           # thẻ hiếm có ít hơn ngần này ứng viên trong nhóm thì trích thêm
VIDEO_THEO_THE = {                      # thẻ nào có khả năng xuất hiện ở video nào (nhắm đúng video, không quét cả 349)
    'yaw_manh_trai': lambda v: v['camera'] == 'dash', 'yaw_manh_phai': lambda v: v['camera'] == 'dash',
    'pitch_len': lambda v: v['camera'] == 'dash' or v['state'] in ('yawning', 'talking_yawning'),
    'pitch_xuong': lambda v: v['camera'] == 'dash',
    'che_tay': lambda v: v['camera'] == 'dash' or v['state'] in ('yawning', 'talking_yawning'),
    'mat_nham': lambda v: v['camera'] == 'dash' or v['state'] in ('yawning', 'talking_yawning'),
    'ngap_rong': lambda v: v['state'] in ('yawning', 'talking_yawning') or v['camera'] == 'dash',
    'kinh_ram': lambda v: v['glasses'] == 'sunglasses',
    'sang_chay': lambda v: v['camera'] == 'dash', 'toi': lambda v: v['camera'] == 'dash', 'mo': lambda v: v['camera'] == 'dash',
}


def the_can_them(rows, can=CAN_THEM, extra=('che_tay',)):
    """Thẻ hiếm cần trích thêm: ít hơn `can` ứng viên NGOÀI 616 trong nhóm (đã tính sửa thẻ), cộng các thẻ ở `extra`."""
    cnt = Counter(t for r in rows if r['mp_ok'] and not r['loai'] and not r.get('trung_goi616') for t in r['the'])
    return [t for t in THE_HIEM if cnt[t] < can or t in extra]


def giu_khung(samples, old, need, per_video=PER_VIDEO_THEM):
    """Chọn khung giữ thêm của MỘT video. samples: [dict(t, hash, the, prio)] (khung mới, đã đạt >= 1 thẻ cần); old: [dict(t, hash)] khung đã có của cùng video
    (ứng viên cũ + khung mới đã giữ). Giữ khung ưu tiên cao trước, chỉ khi cách mọi khung đã có >= MIN_GAP_S giây và dHash khác >= DHASH_MIN_DIST bit.
    Trả (danh sách giữ, số loại vì gần trùng thời gian/ảnh, số loại vì vượt trần)."""
    kept, near, over = [], 0, 0
    have = list(old)
    for s in sorted(samples, key=lambda s: (-s['prio'], s['t'])):
        if len(kept) >= per_video:
            over += 1
            continue
        if any(abs(s['t'] - h['t']) < MIN_GAP_S - 1e-6 or (s.get('hash') is not None and h.get('hash') is not None
                                                           and ii.hamming(s['hash'], h['hash']) < ii.DHASH_MIN_DIST) for h in have):
            near += 1
            continue
        kept.append(s)
        have.append(s)
    return sorted(kept, key=lambda s: s['t']), near, over


def _them_init(model, hand_model):
    _G['lm'] = steps.make_landmarker(model, num_faces=5, outputs=True)
    _G['det'] = BlendDetector(_G['lm'])
    _G['hand'] = make_hand_landmarker(hand_model) if hand_model else None


def them_video(job):
    """Quét MỘT video: đọc tuần tự, lấy mẫu dày, dò mặt như scan_video (mã hoá JPEG rồi đọc lại), đo, chấm thẻ nhanh, giữ khung đạt thẻ cần. Ghi khung JPEG
    vào <dir>/frames. Trả dict(video, rows, log)."""
    v, need, out_dir, old, taken, step, per_video = (job[k] for k in ('v', 'need', 'dir', 'old', 'taken', 'step', 'per_video'))
    det, hand = _G['det'], _G.get('hand')
    rej, samples = Counter(), []
    for idx, t, bgr, fps in ii.sample_video(v['path'], step_s=step, max_samples=10 ** 9):
        rej['khung_doc'] += 1
        buf = ii._jpeg(bgr)
        dec = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
        res = det.detect(cv2.cvtColor(dec, cv2.COLOR_BGR2RGB))
        if res is None:
            rej['khong_thay_mat'] += 1
            continue
        why = ii.reject_reason(res['pts'], dec.shape[1], dec.shape[0])
        if why:
            rej[why] += 1
            continue
        m = ii.measure_face(dec, res['pts'], res['matrix'], res['jaw_open'])
        row = dict(m, source='yawdd', camera=v['camera'], glasses=v['glasses'], video=v['rel'], blink_l=res.get('blink_l'), blink_r=res.get('blink_r'),
                   canh_mat_px=max(m['box'][2] - m['box'][0], m['box'][3] - m['box'][1]))
        the = the_tu_dong(row)
        if hand is not None:
            hb = hand_boxes(hand, cv2.cvtColor(dec, cv2.COLOR_BGR2RGB))
            cov = max([box_inter_frac(h, m['box']) for h in hb] or [0.0])
            if cov >= HAND_COV_GOI_Y:
                the.append('che_tay')
        got = [x for x in the if x in need]
        if not got:
            rej['khong_dat_the_can'] += 1
            continue
        samples.append(dict(t=t, frame=idx, hash=m['hash'], the=got, prio=10 * len(got) + (m['jaw_open'] or 0.0), buf=buf, m=m, hw=dec.shape[:2],
                            pts=res['pts']))
    kept, near, over = giu_khung(samples, old, need, per_video)
    rej['gan_trung'] += near
    rej['vuot_tran'] += over
    rows = []
    os.makedirs(os.path.join(out_dir, 'frames'), exist_ok=True)
    taken = set(taken)
    for s in kept:
        base = f"{v['subject']}_{v['camera']}_{v['state']}_g{ii.GLASSES_CODE[v['glasses']]}_f{s['frame']:06d}"
        name = ii._unique_name(base, taken)
        with open(os.path.join(out_dir, 'frames', name + '.jpg'), 'wb') as f:
            f.write(s['buf'])
        meta = dict(source='yawdd', camera=v['camera'], subject=v['subject'], gender=v['gender'], glasses=v['glasses'], state=v['state'], video=v['rel'])
        r = ii._cand_row(meta, name, s['m'], s['frame'], s['t'], f'cache/new/frames/{name}.jpg', s['hw'][1], s['hw'][0])
        r['hash'] = s['m']['hash']
        r['the_can'] = ';'.join(s['the'])
        rows.append(r)
    return dict(video=v['rel'], rows=rows, rej=dict(rej))


def _them_safe(job):
    try:
        return them_video(job)
    except Exception as e:
        return dict(video=job['v']['rel'], rows=[], rej={}, err=f'{type(e).__name__}: {e}')


def cmd_them(a):
    """Trích thêm khung từ video YawDD cho các thẻ còn thiếu. Làm tiếp được (mỗi video một shard JSON theo thẻ cần + bước lấy mẫu)."""
    import multiprocessing as mp
    a.out = check_out_dir(a.out)
    if not a.yawdd:
        raise SystemExit('them cần --yawdd (thư mục "YawDD dataset")')
    rows = tai_bang(a)
    need = [t for t in a.cho_the.split(',') if t] if a.cho_the else the_can_them(rows, a.can_them)
    for t in need:
        if t not in THE_HIEM:
            raise SystemExit(f'--cho-the: {t!r} không phải thẻ hiếm ({", ".join(THE_HIEM)})')
    vids, bad = ii.list_yawdd(a.yawdd)
    ghi_nhat_ky(a.out, f'them: thẻ cần {need}; {len(vids)} video YawDD hợp lệ, {len(bad)} bỏ')
    vids = [v for v in vids if any(VIDEO_THEO_THE[t](v) for t in need if t in VIDEO_THEO_THE)]
    if a.video_re:
        vids = [v for v in vids if re.search(a.video_re, v['rel'])]
    new_dir = os.path.join(a.out, 'cache', 'new')
    sh_dir = os.path.join(new_dir, 'shards')
    os.makedirs(sh_dir, exist_ok=True)
    old_by_video = defaultdict(list)
    for r in rows:
        if r['source'] == 'yawdd':
            old_by_video[r['video']].append(dict(t=_num(r['t_s'], 0.0), hash=r.get('hash')))
    taken = {r['name'] for r in rows}
    key = f'step={a.step};per={a.per_video};need={",".join(sorted(need))};v={ii.SCAN_VERSION}'
    jobs, done = [], {}
    for v in vids:
        sp = os.path.join(sh_dir, hashlib.sha1((v['rel'] + '|' + key).encode('utf-8')).hexdigest()[:16] + '.json')
        if os.path.exists(sp) and not a.fresh:
            with open(sp, encoding='utf-8') as f:
                done[v['rel']] = json.load(f)
        else:
            jobs.append(dict(v=v, need=need, dir=new_dir, old=old_by_video[v['rel']], taken=sorted(taken), step=a.step, per_video=a.per_video, shard=sp))
    ghi_nhat_ky(a.out, f'them: {len(vids)} video nhắm tới ({len(done)} đã có shard, {len(jobs)} cần quét), lấy mẫu {a.step} s, tối đa {a.per_video} khung/video')
    hand_model = a.hand_model if a.hand_model and os.path.exists(a.hand_model) else None
    pool = mp.get_context('spawn').Pool(a.jobs, initializer=_them_init, initargs=(a.model, hand_model)) if jobs else None
    try:
        for n, res in enumerate(pool.imap_unordered(_them_safe, jobs) if pool else [], 1):
            job = next(j for j in jobs if j['v']['rel'] == res['video'])
            if res.get('err'):
                ghi_nhat_ky(a.out, f'  LỖI video {res["video"]}: {res["err"]}')
                continue
            with open(job['shard'], 'w', encoding='utf-8') as f:
                json.dump(res, f, ensure_ascii=False)
            done[res['video']] = res
            ghi_nhat_ky(a.out, f'  them {n}/{len(jobs)} {res["video"]}: đọc {res["rej"].get("khung_doc", 0)} khung, giữ {len(res["rows"])}, '
                               f'loại {({k: v for k, v in res["rej"].items() if k != "khung_doc"})}')
    finally:
        if pool:
            pool.terminate()
            pool.join()
    allrows, names = [], set()
    for rel in sorted(done):
        for r in done[rel]['rows']:
            if r['name'] in names:
                r['name'] = ii._unique_name(r['name'], names)                 # (hiếm) trùng tên giữa hai lượt chạy
            names.add(r['name'])
            allrows.append(r)
    ghi_csv(os.path.join(new_dir, 'candidates_new.csv'), ii.CAND_COLUMNS + ['hash', 'the_can'], allrows)
    c = Counter(t for r in allrows for t in r['the_can'].split(';'))
    ghi_nhat_ky(a.out, f'them xong: {len(allrows)} khung mới từ {len(done)} video; thẻ cần đạt: {dict(c)}. Chạy lại `do` để đo trên ảnh cắt.')
    return allrows


# ======================================================================================================================
# Lệnh chon: chọn, đánh số, báo cáo phân bố, ghi file bí mật
# ======================================================================================================================
BI_MAT_COLS = ['so', 'ten_file', 'warmup', 'muc', 'diem_kho', 'the', 'nhap', 'flip_nme', 'nguon', 'camera', 'tai_xe', 'gioi', 'kinh', 'trang_thai', 'video',
               'frame', 't_s', 'khung_goc', 'x0', 'y0', 'x1', 'y1', 'yaw', 'pitch', 'roll', 'jaw_open', 'eye_blink_l', 'eye_blink_r', 'luma', 'contrast',
               'bright_frac', 'lap_var', 'canh_mat_px', 'pad_frac', 'gaze_label', 'trung_goi616', 'khung_moi', 'sua_bang_mat', 'ghi_chu', 'ung_vien',
               'duoc_dang_anh', 'box_iou', 'hand_cov', 'df_err']


def kinh_cua(r):
    return 'sunglasses' if 'kinh_ram' in r['the'] else ('glasses' if 'kinh_can' in r['the'] else 'none')


def hang_bi_mat(so, r, dang_anh=None):
    jaw = r.get('jaw_crop') if r.get('jaw_crop') is not None else r.get('jaw_open')
    ghi = [r.get('ghi_chu_sua') or '']
    if (_num(r.get('box_iou')) or 1.0) < BOX_IOU_NGHI:
        ghi.append('NGHI: hộp mặt MediaPipe trên ảnh cắt lệch hộp ứng viên (nghi bắt nhầm mặt)')
    if (_num(r.get('pad_frac')) or 0.0) > 0.10:
        ghi.append('NGHI: viền xám lớn')
    if (_num(r.get('hand_cov')) or 0.0) >= HAND_COV_GOI_Y and 'che_tay' not in r['the']:
        ghi.append('NGHI: hand landmarker gợi ý tay che nhưng chưa chốt thẻ che_tay')
    return {'so': f'{so:03d}', 'ten_file': f'{so:03d}.png', 'warmup': int(so <= N_WARMUP), 'muc': r['muc'], 'diem_kho': f'{r["diem"]:g}', 'the': ';'.join(r['the']),
            'nhap': r['nhap'], 'flip_nme': '' if r.get('flip_nme') is None else f'{r["flip_nme"]:.2f}', 'nguon': r['source'], 'camera': r['camera'],
            'tai_xe': r['subject'], 'gioi': r['gender'], 'kinh': kinh_cua(r), 'trang_thai': r['state'], 'video': r['video'], 'frame': int(r['frame']),
            't_s': '' if r.get('t_s') is None else f'{r["t_s"]:g}', 'khung_goc': ii.frame_rel(r), 'x0': r['x0'], 'y0': r['y0'], 'x1': r['x1'], 'y1': r['y1'],
            'yaw': r['yaw'], 'pitch': r['pitch'], 'roll': r['roll'], 'jaw_open': '' if jaw is None else jaw,
            'eye_blink_l': '' if r.get('blink_l') is None else r['blink_l'], 'eye_blink_r': '' if r.get('blink_r') is None else r['blink_r'],
            'luma': r['luma'], 'contrast': r['contrast'], 'bright_frac': r['bright_frac'], 'lap_var': r['lap_var'], 'canh_mat_px': r['canh_mat_px'],
            'pad_frac': r['pad_frac'], 'gaze_label': '' if r.get('gaze_label') is None else int(r['gaze_label']), 'trung_goi616': r.get('trung_goi616') or '',
            'khung_moi': int(r['moi']), 'sua_bang_mat': r.get('the_sua') or '', 'ghi_chu': ' | '.join(x for x in ghi if x), 'ung_vien': r['name'],
            'duoc_dang_anh': (dang_anh or {}).get(r['video'], 'chua_doi_chieu') if r['source'] == 'yawdd' else 'khong_ap_dung',
            'box_iou': '' if r.get('box_iou') is None else r['box_iou'], 'hand_cov': '' if r.get('hand_cov') is None else r['hand_cov'],
            'df_err': '' if r.get('df_err') is None else r['df_err']}


def bang_muc_the(items, tags=None):
    """Bảng mức x thẻ: {mức: {thẻ: số ảnh}}, thêm hàng 'tong'."""
    tags = tags or [t for t in THE_THU_TU if not t.startswith('cam_')]
    out = {m: Counter() for m in (*LEVELS, 'tong')}
    for c in items:
        out[c['muc']]['n'] += 1
        out['tong']['n'] += 1
        for t in c['the']:
            if t in tags or t.startswith('cam_'):
                out[c['muc']][t] += 1
                out['tong'][t] += 1
    return out, tags


def ghi_phan_bo_csv(path, items):
    tab, tags = bang_muc_the(items)
    cols = ['muc', 'n'] + tags + ['cam_dash', 'cam_mirror', 'cam_drivface']
    ghi_csv(path, cols, [dict(muc=LEVEL_VI.get(m, 'tổng'), **{k: tab[m][k] for k in cols if k != 'muc'}) for m in (*LEVELS, 'tong')])


def bao_cao_phan_bo(items, order, res, thieu, a, quota):
    """Văn bản (markdown) phân bố của bộ đã chọn: mức, thẻ, giới, camera, nguồn, tài xế, 616, seed."""
    L = []
    n = len(items)
    L.append(f'Seed khởi đầu {res["seed_goc"]}, seed thực dùng {res["seed_dung"]} ({res["dat"]} lần đạt luật cứng trong {res["thu"]} lần thử; điểm phạt cân bằng {res["phat"]:.2f}).')
    L.append(f'Hạn mức mức: ' + ', '.join(f'{LEVEL_VI[m]} {quota[m]}' for m in LEVELS) + f'; k = {a.k} ảnh/tài xế; thẻ hiếm tối thiểu {a.min_the} (mục tiêu {TARGET_THE}).')
    L.append(f'Tổng {n} ảnh; mức thực: ' + ', '.join(f'{LEVEL_VI[m]} {sum(1 for c in items if c["muc"] == m)}' for m in LEVELS) + '.')
    known = [c for c in items if c['gender'] in ('F', 'M')]
    f = sum(1 for c in known if c['gender'] == 'F')
    L.append(f'Giới (bỏ unknown): nữ {f}, nam {len(known) - f} ({100 * f / max(len(known), 1):.0f}% nữ); unknown {n - len(known)}.')
    cam = Counter(c['camera'] for c in items)
    L.append('Camera: ' + ', '.join(f'{k} {v} ({100 * v / n:.0f}%)' for k, v in sorted(cam.items())) + '.')
    src = Counter(c['source'] for c in items)
    L.append('Nguồn: ' + ', '.join(f'{k} {v}' for k, v in sorted(src.items())) + '.')
    subj = Counter(c['subject'] for c in items)
    L.append(f'Tài xế: {len(subj)} người khác nhau; nhiều nhất {max(subj.values())} ảnh/người; phân bố số ảnh/người: ' +
             ', '.join(f'{k} ảnh x {v} người' for k, v in sorted(Counter(subj.values()).items())) + '.')
    vid = Counter(vkey(c) for c in items if c['source'] == 'yawdd')
    L.append(f'Video: {len(vid)} video khác nhau, nhiều nhất {max(vid.values())} ảnh/video.')
    t616 = [c for c in items if c.get('trung_goi616')]
    L.append(f'Ảnh trùng gói 616: {len(t616)} ({100 * len(t616) / n:.0f}%); ngoài 616: {n - len(t616)} ({100 * (n - len(t616)) / n:.0f}%).')
    L.append(f'Khung trích thêm từ video (ngoài candidates.csv): {sum(int(c["moi"]) for c in items)}.')
    nh = Counter(c['nhap'] for c in items)
    L.append(f'Nháp: tốt {nh["tot"]}, vừa {nh["vua"]}, tệ {nh["te"]} (nháp tệ = đã xác nhận bằng mắt; nháp tốt = flip_nme <= {NHAP_TOT_NME} % IOD).')
    if thieu:
        L.append('THẺ THIẾU: ' + '; '.join(f'{t} có {h}/cần {need} ({why})' for t, h, need, _, why in thieu) + '.')
    else:
        L.append(f'Không thiếu thẻ hiếm nào (mọi thẻ >= {a.min_the}).')
    cnt = Counter(t for c in items for t in c['the'])
    L.append('Thẻ hiếm trong bộ: ' + ', '.join(f'{t} {cnt[t]}' for t in THE_HIEM) + '.')
    return L


def cmd_chon(a):
    """Chọn + đánh số + ghi file bí mật. THUẦN: không đọc ảnh, không gọi MediaPipe. --dry-run: chỉ in bảng, không ghi gì."""
    a.out = check_out_dir(a.out)
    quota = doc_quota(a.quota)
    if sum(quota.values()) != N_ANH:
        raise SystemExit(f'--quota cộng lại {sum(quota.values())}, phải đúng {N_ANH}')
    rows = tai_bang(a)
    res = chon(rows, a.seed, quota, a.k, a.min_the, log=print if a.dry_run else None)
    order = danh_so(res['items'], a.seed)
    thieu = the_thieu(res['items'], res['pool'], a.min_the)
    lines = bao_cao_phan_bo(res['items'], order, res, thieu, a, quota)
    print('\n'.join(lines))
    tab, tags = bang_muc_the(res['items'])
    print('mức \\ thẻ: ' + ' '.join(f'{t}' for t in tags if tab['tong'][t]))
    for m in (*LEVELS, 'tong'):
        print(f'  {LEVEL_VI.get(m, "tổng"):8s} n={tab[m]["n"]:3d} ' + ' '.join(f'{tab[m][t]:>3d}' for t in tags if tab['tong'][t]))
    print('khởi động: ' + ', '.join(f'{i + 1:03d}' for i in range(N_WARMUP)))
    if a.dry_run:
        print('(--dry-run: không ghi file nào)')
        return res, order
    bm = os.path.join(a.out, 'bi_mat')
    os.makedirs(bm, exist_ok=True)
    dang = doc_dang_anh(os.path.join(a.out, 'dang_anh.csv'))
    if a.table1 and a.table2:                                    # `pdftotext -layout Table1.pdf t1.txt` (Mirror) và Table2.pdf (Dash)
        tb_ = doc_table_yawdd(open(a.table1, encoding='utf-8', errors='replace').read(), open(a.table2, encoding='utf-8', errors='replace').read())
        dang = {r['video']: dang_anh_cua(r['video'], tb_) for r in order if r['source'] == 'yawdd'}
        ghi_nhat_ky(a.out, f'chon: đối chiếu Table1/Table2 ({len(tb_)} dòng đọc được): ' + str(dict(Counter(dang.values()))))
    ghi_csv(os.path.join(bm, 'bo200_bi_mat.csv'), BI_MAT_COLS, [hang_bi_mat(i + 1, r, dang) for i, r in enumerate(order)])
    ghi_phan_bo_csv(os.path.join(bm, 'phan_bo.csv'), order)
    nx = os.path.join(a.out, 'nhan_xet.md')
    with open(os.path.join(bm, 'bo200_bi_mat.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(viet_md(a, res, order, thieu, lines, quota, open(nx, encoding='utf-8').read() if os.path.exists(nx) else ''))
    with open(os.path.join(a.out, 'cache', 'chon.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(thu_tu=[r['name'] for r in order], seed_goc=res['seed_goc'], seed_dung=res['seed_dung'], bo_anh=BO_ANH, quota=quota, k=a.k), f)
    if a.sua_the and os.path.exists(a.sua_the):
        shutil.copyfile(a.sua_the, os.path.join(bm, 'sua_the.csv'))
    with open(os.path.join(bm, 'nhat_ky_chon.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
        f.write(f'Lệnh: tao_bo200.py chon --seed {a.seed} --k {a.k} --quota "{a.quota}" --min-the {a.min_the}'
                f'{" --sua-the sua_the.csv" if a.sua_the else ""}\n')
    ghi_nhat_ky(a.out, f'chon xong: seed khởi đầu {res["seed_goc"]}, thực dùng {res["seed_dung"]}; ghi {bm}')
    return res, order


def doc_dang_anh(path):
    """{video YawDD: Yes|No|chua_doi_chieu} từ dang_anh.csv (cột video, duoc_dang), nếu có."""
    if not os.path.exists(path):
        return {}
    return {r['video']: r['duoc_dang'] for r in doc_csv(path)}


TABLE_GLASSES = {'none': 'no glasses', 'glasses': 'prescription', 'sunglasses': 'sun glasses'}
_RE_T1 = re.compile(r'^\s*(\d+)\s+(Talking\s*&\s*Yawning|Normal|Talking|Yawning)\s+(\S+)\s+(\S+)\s+(No Glasses|Sun ?glasses|Prescription)\b.*?(Yes|No)\s*$', re.I)
_RE_T2 = re.compile(r'^\s*(\d+)\s+(?:Normal-Talking-\s+)?(\S+)\s+(Yes|No)\s+(No Glasses|Sun ?glasses|Prescription)\b.*?(Yes|No)\s*$', re.I)


def doc_table_yawdd(text1, text2):
    """Đọc Table1.pdf (Mirror) và Table2.pdf (Dash) của YawDD đã đổi sang văn bản bằng `pdftotext -layout`; lấy cột "Allow Researchers to use picture in their paper".
    Trả {khoá: 'Yes'|'No'}: Mirror (camera, giới, số, trạng thái, kính) ; Dash (camera, giới, số). Dòng không đọc được thì bỏ (video đó sẽ ghi chua_doi_chieu)."""
    out = {}
    for text, cam in ((text1, 'mirror'), (text2, 'dash')):
        gender = None
        for ln in text.splitlines():
            if re.match(r'^\s*Male\b', ln):
                gender = 'M'
            elif re.match(r'^\s*Female\b', ln):
                gender = 'F'
            if gender is None:
                continue
            if cam == 'mirror':
                m = _RE_T1.match(ln)
                if m:
                    num, st, _, _, gl, ok = m.groups()
                    state = re.sub(r'\s+', '', st).lower()
                    out[(cam, gender, int(num), ii.STATE_MAP.get(state, state), re.sub(r' ?glasses', ' glasses', gl.lower()).replace('sun glasses', 'sun glasses'))] = ok.capitalize()
            else:
                m = _RE_T2.match(ln)
                if m:
                    out[(cam, gender, int(m.group(1)))] = m.group(5).capitalize()
    return out


def dang_anh_cua(video_rel, table):
    """'Yes' / 'No' / 'chua_doi_chieu' cho một video YawDD (đường dẫn tương đối, dùng '/')."""
    info = ii.parse_yawdd(video_rel)
    if info is None or not table:
        return 'chua_doi_chieu'
    if info['camera'] == 'dash':
        return table.get(('dash', info['gender'], info['num']), 'chua_doi_chieu')
    gl = TABLE_GLASSES.get(info['glasses'], '')
    return table.get(('mirror', info['gender'], info['num'], info['state'], gl), 'chua_doi_chieu')


# ======================================================================================================================
# Đóng gói (THUẦN: ghi zip tất định, kế hoạch chia phần, quét rò rỉ, văn bản README)
# ======================================================================================================================
ZIP_DATE = (2026, 10, 9, 0, 0, 0)                 # ngày tạo bộ; cố định để dựng lại ra cùng sha256
NGAY_TAO = '2026-10-09'
KIEU_ZIP = 0o100644 << 16                         # tệp thường, quyền 0644
ANH_PNG_CHUNKS = {'IHDR', 'IDAT', 'IEND'}         # ảnh không mang metadata: chỉ ba chunk bắt buộc (không tEXt, eXIf, iTXt, pHYs, gAMA...)
HOP_ULPS = 30


def hop_dong_nhat():
    """Hộp (x0, y0, x1, y1) vuông ở giữa ảnh 512, cạnh 512 / SIDE_SCALE, tính để crop_geometry cho ĐÚNG left = top = 0, k = 1.0 (không sai số dấu phẩy động),
    nên `m28.py ... --box crop` cắt lại ra đúng ảnh cũ (biến đổi đồng nhất). Tìm trong +-HOP_ULPS ulp quanh nghiệm lý thuyết; không có thì dùng nghiệm lý thuyết."""
    from m28core.cat_mat import crop_geometry
    s = OUT / SIDE_SCALE
    x0c = (OUT - s) / 2
    x1c = x0c + s

    def step(x, n):
        for _ in range(abs(n)):
            x = float(np.nextafter(x, math.inf if n > 0 else -math.inf))
        return x

    for d in range(HOP_ULPS + 1):
        for i, j in sorted({(a, b) for a in range(-d, d + 1) for b in range(-d, d + 1) if max(abs(a), abs(b)) == d}):
            xa, xb = step(x0c, i), step(x1c, j)
            left, top, k, _, _ = crop_geometry((xa, xa, xb, xb), np.zeros((1, 2), np.float32))
            if left == 0.0 and top == 0.0 and k == 1.0:
                return xa, xa, xb, xb
    return x0c, x0c, x1c, x1c


def manifest_b_rows(n=N_ANH):
    """Các dòng manifest gói B: chỉ các cột m28.py cần, mỗi dòng 001.png .. N.png (file = image), hộp vuông giữa ảnh cắt, left = top = 0, k = 1."""
    x0, y0, x1, y1 = hop_dong_nhat()
    return [dict(file=f'{i:03d}.png', image=f'{i:03d}.png', face_idx=0, x0=repr(x0), y0=repr(y0), x1=repr(x1), y1=repr(y1), left=0, top=0, k=1)
            for i in range(1, n + 1)]


MANIFEST_B_COLS = ['file', 'image', 'face_idx', 'x0', 'y0', 'x1', 'y1', 'left', 'top', 'k']


def ghi_zip(path, entries):
    """Ghi zip TẤT ĐỊNH: mục sắp theo tên, ngày giờ cố định, quyền 0644, không nén (ZIP_STORED), tên ASCII. entries: [(tên trong zip, bytes hoặc đường dẫn file)]."""
    names = [n for n, _ in entries]
    if len(set(names)) != len(names):
        raise ValueError('tên mục trùng trong zip')
    for n in names:
        n.encode('ascii')                                     # UnicodeEncodeError nếu có ký tự ngoài ASCII
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED) as z:
        for n, src in sorted(entries, key=lambda e: e[0]):
            data = src if isinstance(src, (bytes, bytearray)) else open(src, 'rb').read()
            zi = zipfile.ZipInfo(n, ZIP_DATE)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = KIEU_ZIP
            zi.create_system = 3
            z.writestr(zi, data)
    return path


def chia_phan(files, limit):
    """files: [(tên trong zip, kích thước)] -> các phần (list tên) mỗi phần <= limit byte, dùng đúng inc_ingest.plan_parts (tính cả header zip)."""
    return ii.plan_parts(sorted(files), limit)


def text_crlf(s):
    """README: UTF-8 có BOM và xuống dòng CRLF để Notepad cũ đọc được tiếng Việt có dấu."""
    return ('\ufeff' + s.replace('\r\n', '\n').replace('\n', '\r\n')).encode('utf-8')


def png_chunks(data):
    """Danh sách tên chunk của một file PNG (bytes); ValueError nếu không phải PNG."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('không phải PNG')
    out, i = [], 8
    while i + 8 <= len(data):
        ln, = struct.unpack('>I', data[i:i + 4])
        out.append(data[i + 4:i + 8].decode('ascii', 'replace'))
        i += 12 + ln
    return out


def mau_ro_ri(hostname=None):
    """Các mẫu rò rỉ cho gói A/B (mục 4.1): mã tài xế, tên video, camera/nguồn theo ảnh, tên khung gốc, thẻ, mức khó, cờ, đường dẫn tuyệt đối, tên máy."""
    the = '|'.join(re.escape(t) for t in THE_THU_TU if not t.startswith('cam_'))
    pats = [('ma_tai_xe', r'yd_[FM]\d{3}'), ('ma_drivface', r'df_\d\d'), ('video_avi', r'\.avi\b'), ('camera', r'(?i)\b(?:mirror|dash)\b'),
            ('nguon', r'(?i)yawdd|drivface'), ('khung_goc', r'_g\d_f\d{6}|\bf\d{6}\b'), ('the_yeu_to', rf'\b(?:{the})\b'),
            ('muc_kho', r'rat_kho|diem_kho|bi_mat|khung_goc|nhap_te|nhap_tot'),
            ('duong_dan_tuyet_doi', r'(?:^|[\s"\'(=:])(?:/home/|/tmp/|/root/|/Users/|/mnt/|[A-Za-z]:\\)|scratchpad')]
    host = (hostname if hostname is not None else socket.gethostname()) or ''
    if len(host) >= 3:
        pats.append(('ten_may', r'(?i)\b' + re.escape(host) + r'\b'))
    return [(n, re.compile(p)) for n, p in pats]


def quet_ro_ri(entries, hostname=None, cho_phep_nguon=('NOTICE.txt',)):
    """entries: [(tên mục, bytes)]. Trả danh sách (tên mục, mẫu, đoạn khớp) của mọi rò rỉ. PNG chỉ kiểm tên mục + chunk metadata; mục khác kiểm tên và nội dung văn bản.
    NOTICE.txt được nêu tên hai bộ dữ liệu (mẫu `nguon`), mọi mẫu khác vẫn áp dụng."""
    pats = mau_ro_ri(hostname)
    out = []
    for name, data in entries:
        base = name.rsplit('/', 1)[-1]
        for pn, rx in pats:
            if pn == 'nguon' and base in cho_phep_nguon:
                continue
            m = rx.search(name)
            if m:
                out.append((name, pn + ' (tên mục)', m.group(0)))
        if name.lower().endswith('.png'):
            try:
                extra = [c for c in png_chunks(data) if c not in ANH_PNG_CHUNKS]
            except ValueError:
                extra = ['(không phải PNG)']
            if extra:
                out.append((name, 'metadata_png', ','.join(sorted(set(extra)))))
            continue
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            out.append((name, 'khong_phai_van_ban', ''))
            continue
        for pn, rx in pats:
            if pn == 'nguon' and base in cho_phep_nguon:
                continue
            m = rx.search(text)
            if m:
                out.append((name, pn, text[max(0, m.start() - 20):m.end() + 20].replace('\n', ' ')))
    return out


def sha_anh_text(shas):
    """SHA256SUMS_anh.txt: '<sha256>  anh/001.png' mỗi dòng, theo số."""
    return ''.join(f'{h}  anh/{n}\n' for n, h in sorted(shas.items()))


def info_json(shas, n_warm=N_WARMUP):
    names = sorted(shas)
    d = dict(bo_anh=BO_ANH, so_anh=len(names), dinh_dang='png 512x512 (nén mức %d, không metadata)' % ii.PNG_COMPRESSION, ngay_tao=NGAY_TAO,
             warmup=names[:n_warm], anh=names, sha256={n: shas[n] for n in names}, tong_sha256=sha256_bytes(sha_anh_text(shas).encode('utf-8')))
    return json.dumps(d, ensure_ascii=False, indent=1) + '\n'


NOTICE_DAU = """NGUON DU LIEU VA DIEU KHOAN (file UTF-8, bo anh bo200_v1)
=========================================================
Du an M28 (nhan nhap landmark khuon mat) cua doi T015-SIXSEVEN la du an PHI THUONG MAI (hoc tap/nghien cuu).
Bo 200 anh nay (de thu gan 50 diem) lay tu hai bo du lieu cong khai duoi day. Chi dung NOI BO NHOM.
KHONG phat tan, KHONG dang lai, KHONG dua vao bao cao/slide cong khai, KHONG dua anh len chat hay dich vu ben ngoai.
Anh nguoi lai xe la du lieu nhay cam. Goi nay khong ghi nguon cua tung anh; truoc khi dua bat ky anh nao ra ngoai nhom,
hoi nhom truong de tra file bi mat va doi chieu Table1.pdf / Table2.pdf cua bo YawDD.

"""
NOTICE = NOTICE_DAU + ii.NOTICE[ii.NOTICE.index('1. YawDD'):ii.NOTICE.index('3. Ma nguoi')].rstrip() + '\n'


def bang_sha_text(parts):
    """Bảng markdown-ish dung lượng + sha256 của các phần ảnh. parts: [(tên file, byte, sha256)]."""
    L = ['Phần ảnh                              Dung lượng (byte)   MiB    sha256']
    for n, size, h in parts:
        L.append(f'{n:<38s} {size:>12d}   {size / 1048576:6.2f}   {h}')
    return '\n'.join(L)


QUY_UOC_DIEM = """- TRÁI/PHẢI THEO BỨC ẢNH, không theo người và không soi gương: label có chữ "trai" (longmaytrai, mattrai) nằm ở nửa TRÁI ảnh, label có chữ "phai" nằm ở nửa PHẢI ảnh.
- Thứ tự điểm trong mỗi label (QĐ-003): lông mày: _1 đầu mày (gần mũi) đến _5 đuôi mày; sống mũi: _1 giữa hai mắt đến _4 chóp mũi;
  mắt (vòng kín): _1 khoé ngoài, _2 đến _4 mí trên đi vào trong, _5 khoé trong, _6 đến _8 mí dưới đi ra ngoài;
  môi ngoài và môi trong (vòng kín): _1 là khoé môi bên TRÁI ảnh, đi theo mép trên từ trái sang phải đến khoé môi bên phải ảnh, rồi mép dưới từ phải sang trái.
- Điểm bị che (kính râm, tay, tóc...): quy ước CHƯA CHỐT trong repo (bản chụp kế hoạch 5/10/2026 ghi dạng "Đề xuất": đặt điểm ở vị trí ước lượng và BẬT cờ occluded;
  KHÔNG dùng cờ outside, vì eval50.py bỏ điểm outside khỏi phép đo). NHÓM TRƯỞNG CHỐT TRƯỚC KHI PHÁT GÓI; gói A và gói B ghi cùng một quy ước. Đề xuất hiện tại:
  đặt ở vị trí ước lượng, bật occluded, không dùng outside; kính trong nhìn thấy mắt rõ thì không bật occluded."""

README_A = """BỘ 200 ẢNH THỬ GÁN NHÃN 50 ĐIỂM (bo_anh: {bo_anh}) - GÓI A
Dành cho nhóm MANUAL: gán tay hoàn toàn, KHÔNG có nhãn nháp.
============================================================================
Ngày tạo: {ngay}. Nhóm ASSISTED (gói B) làm đúng 200 ảnh này, nên hai nhóm so sánh được trên cùng ảnh.

1. Gói này có gì
- anh/001.png ... anh/200.png: 200 ảnh mặt 512 x 512. Hai ảnh 001 và 002 là ảnh KHỞI ĐỘNG: vẫn gán, nhưng không tính vào số đo.
- face50_label.json: định nghĩa bảy label skeleton (50 điểm) để dán vào CVAT (mục 3).
- NOTICE.txt: nguồn và điều khoản của dữ liệu. ĐỌC TRƯỚC KHI DÙNG.
- bo200_info.json, SHA256SUMS_anh.txt: danh sách ảnh và sha256 từng ảnh để kiểm.

2. Giải nén
Gói gồm nhiều file zip, mỗi file là một zip độc lập: m28_bo200_A_part00_meta.zip (tài liệu) và các phần ảnh m28_bo200_A_part01_of_{n}.zip ... Hãy giải nén TẤT CẢ
vào CÙNG MỘT thư mục (kết quả: thư mục bo200_A\\ có anh\\, face50_label.json, README_A.txt, NOTICE.txt...).
  cmd (Windows 10/11, đứng trong thư mục chứa các file zip):   for %f in (m28_bo200_A_part*.zip) do tar -xf "%f"
  bash (Linux):                                                  for f in m28_bo200_A_part*.zip; do unzip -o "$f"; done
Lưu ý: tar -xf có sẵn của Windows mở được zip nhưng CHƯA được thử trên máy Windows thật. Nếu tar báo lỗi: dùng 7-Zip (chuột phải từng file -> 7-Zip -> Extract Here)
hoặc Explorer (chuột phải -> Extract All). Nếu WinRAR/7-Zip báo file hỏng: so dung lượng và sha256 với bảng ở mục 8
(Windows: certutil -hashfile <file> SHA256; Linux: sha256sum <file>); lệch là tải bị cắt, hãy tải lại.

3. Tạo task CVAT thủ công (CVAT 2.77.0 tự cài, http://localhost:8080)
a) Project: dùng project m28 đã có đủ BẢY label skeleton (QĐ-004), hoặc tạo project mới: Constructor -> Raw -> dán toàn bộ nội dung face50_label.json -> Done.
b) Tạo task mới gắn vào project đó và chọn đúng 200 ảnh trong thư mục anh\\.
c) Mục Advanced: Sorting method = Lexicographical; Image quality = 95; Segment size = 8.
   Đây là cùng cách chia job (8 mặt mỗi job) và cùng chất lượng ảnh với task mà `m28.py push` tạo cho nhóm ASSISTED. Để mặc định (chất lượng 70) là thiệt cho nhóm gán tay.
d) Tên task theo quy ước của nhóm trưởng. Đề xuất: demo-bo200-manual-<Pk> (Pk = P1..P5), vì `python tool/m28.py collect --task <tên>` chỉ tự xuất được task có tên bắt đầu bằng demo-.

4. Cách gán
- Với mỗi mặt, chọn lần lượt bảy label rồi đặt đủ điểm của label đó: longmaytrai 5 điểm, longmayphai 5, songmui 4, mattrai 8, matphai 8, moingoai 12, moitrong 8 (tổng 50).
{quy_uoc}

5. Hai ảnh khởi động
001 và 002 vẫn gán đầy đủ (để làm quen), nhưng không tính vào số đo của nhóm.

6. Bấm giờ
Bấm giờ theo hướng dẫn của P5/nhóm trưởng. Nếu bản tool của bạn đã có tab "Đồng hồ" trên trang rà soát thì bấm Bắt đầu trước ảnh 001 và Xong sau ảnh 200; chưa có thì ghi giờ theo hướng dẫn bấm giờ.

7. Xuất nhãn gửi nhóm trưởng
Trong CVAT: Actions -> Export task dataset -> định dạng "CVAT for images 1.1", KHÔNG chọn kèm ảnh (Save images tắt). Hoặc, nếu task tên demo-...:
`python tool/m28.py collect --task <tên task> --reviewer <Pk>` (ghi vào raw/). Đặt tên file theo quy ước nhóm trưởng. KHÔNG gửi ảnh, KHÔNG gửi token.

8. Dung lượng và sha256 các phần ảnh
{bang}

9. Quyền riêng tư
Đây là ảnh người lái xe: chỉ dùng trong nhóm, không đăng, không gửi ra ngoài, không đưa lên dịch vụ bên ngoài, không đưa lên git. Nguồn và điều khoản: NOTICE.txt.
"""

README_B = """BỘ 200 ẢNH THỬ GÁN NHÃN 50 ĐIỂM (bo_anh: {bo_anh}) - GÓI B
Dành cho nhóm ASSISTED: dùng tool (tool/m28.py), sửa nhãn nháp.
============================================================================
Ngày tạo: {ngay}. Nhóm MANUAL (gói A) làm đúng 200 ảnh này, không có nháp.

1. Gói này có gì (giải nén thẳng vào source-tool/m28-prelabel/ của repo)
- data/bo200/anh/001.png ... 200.png: 200 ảnh mặt 512 x 512, giống hệt từng byte ảnh của gói A. 001 và 002 là ảnh KHỞI ĐỘNG (vẫn làm, không tính vào số đo).
- data/bo200/manifest.csv: danh sách ảnh cho m28.py (chỉ các cột m28.py cần). KHÔNG phải manifest của gói 616 mặt: không ghi đè data/manifest.csv và không chạy check_manifest.py trên file này.
- data/bo200/prelabel.xml: nhãn nháp CHUNG cho mọi người (200 ảnh, bảy skeleton mỗi ảnh, đủ 50 điểm), sinh bằng chính m28.py.
- runs/bo200/{{mediapipe,map50,flags,autoqc}}/: kết quả chạy sẵn các bước đó, để nháp ở mọi máy giống nhau (mục 4).
- data/bo200/face50_label.json (bảy label skeleton), NOTICE.txt, bo200_info.json, SHA256SUMS_anh.txt, README_B.txt (file này).
Mọi thứ nằm trong data/ và runs/ nên .gitignore chặn: KHÔNG commit gì trong đó.

2. Chuẩn bị
- Lấy code mới: git pull (nhánh main).
- Môi trường Python và model như HUONG-DAN-UBUNTU.md / HUONG-DAN-WINDOWS.md; cách nhanh: chạy ./chay.sh (Linux) hoặc chay.bat (Windows) một lần để tự cài .venv và tải face_landmarker.task.
- Bật môi trường mỗi lần mở terminal mới: Linux `source .venv/bin/activate`; Windows cmd `call .venv\\Scripts\\activate.bat`. Chạy lệnh từ thư mục source-tool/m28-prelabel.

3. Giải nén các phần vào source-tool/m28-prelabel/
Gói gồm nhiều file zip độc lập: m28_bo200_B_part00_meta.zip (tài liệu, manifest, prelabel.xml, lượt chạy sẵn) và các phần ảnh m28_bo200_B_part01_of_{n}.zip ... Chép TẤT CẢ các file zip
vào thư mục source-tool/m28-prelabel rồi giải nén chúng vào chính thư mục đó (có thể xoá các file zip sau khi giải nén):
  bash:  cd source-tool/m28-prelabel && for f in m28_bo200_B_part*.zip; do unzip -o "$f"; done
  cmd:   cd source-tool\\m28-prelabel && for %f in (m28_bo200_B_part*.zip) do tar -xf "%f"
tar -xf của Windows mở zip được nhưng CHƯA được thử trên Windows thật; dự phòng: 7-Zip hoặc Explorer (Extract All) vào đúng thư mục source-tool\\m28-prelabel.
Kiểm: có data/bo200/anh/200.png, data/bo200/manifest.csv, runs/bo200/map50/mp50.json. Nếu 7-Zip/WinRAR báo hỏng: so sha256 với bảng ở mục 10 (tải bị cắt thì tải lại).

4. LUỒNG CHÍNH: dùng tool (khuyến nghị)
Cần CVAT đang chạy (http://localhost:8080), project m28 có đủ bảy label skeleton (QĐ-004), và biến môi trường CVAT_URL, CVAT_ACCESS_TOKEN đặt trong CHÍNH cửa sổ terminal này
(theo HUONG-DAN-*; KHÔNG ghi token vào file, lệnh hay chat). Thay <Pk> bằng P1..P5.
  bash:
    python tool/m28.py all --run bo200 --manifest data/bo200/manifest.csv --list data/bo200/manifest.csv --images data/bo200/anh --box crop --review ui --reviewer <Pk> --task demo-bo200-<Pk>
  cmd:
    python tool\\m28.py all --run bo200 --manifest data\\bo200\\manifest.csv --list data\\bo200\\manifest.csv --images data\\bo200\\anh --box crop --review ui --reviewer <Pk> --task demo-bo200-<Pk>
Từng bước:
  prepare: bước crop cắt lại 200 ảnh (kết quả giống từng pixel ảnh trong anh/); các bước mediapipe, map50, flags, autoqc được BỎ QUA (in "bỏ qua") vì đã có sẵn trong runs/bo200
           và dùng kết quả chung; bước overlays vẽ ảnh chồng trên máy bạn.
  review:  trang rà soát (chỉ mở ở 127.0.0.1) để Nhận / Sửa nhãn / Bỏ từng mặt. Đề xuất cho thí nghiệm này (nhóm trưởng chốt): Nhận cả 200 mặt, để task có đủ 200 ảnh kèm nháp.
  push:    tạo task demo-bo200-<Pk> trong project m28, tải 200 ảnh PNG, nhập nhãn nháp (job 8 mặt) rồi bạn sửa nháp trong CVAT.
Chạy thử không cần CVAT và không cần token (tự rà theo gợi ý autoqc, chỉ ghi XML):
  bash:  python tool/m28.py all --run bo200 --manifest data/bo200/manifest.csv --list data/bo200/manifest.csv --images data/bo200/anh --box crop --review auto --dry-run
  cmd:   python tool\\m28.py all --run bo200 --manifest data\\bo200\\manifest.csv --list data\\bo200\\manifest.csv --images data\\bo200\\anh --box crop --review auto --dry-run
push --dry-run ghi runs/bo200/xml/prelabel.xml rồi m28.py THOÁT MÃ KHÁC 0 theo thiết kế ("Dừng ở bước push"): đó là bình thường, kết quả nằm ở file XML. Chạy push tách riêng thì phải truyền lại đúng --review auto.
Luôn thêm --manifest data/bo200/manifest.csv (mặc định m28.py đọc data/manifest.csv của gói 616).

5. LUỒNG DỰ PHÒNG: CVAT thật lỗi khi push
Tạo task thủ công GIỐNG HỆT gói A: project có bảy label, 200 ảnh trong data/bo200/anh, Sorting = Lexicographical, Image quality = 95, Segment size = 8. Rồi Upload annotations ->
định dạng "CVAT for images 1.1" -> chọn data/bo200/prelabel.xml. Hai luồng cho CÙNG một nháp; luồng dự phòng chia job khác `push` (không có job Sửa nhãn riêng ở cuối).

6. Không dùng tab "Nạp ảnh" cho bộ này
Tab đó dò lại mặt bằng --box auto trên ảnh cắt rồi cắt lần nữa, nên nháp KHÁC nháp chung của bộ này.

7. Ghi chú về nháp
- Sinh bằng MediaPipe 1.0.1 trên Linux (Python 3.11) ngày {ngay}. Máy khác tự chạy lại MediaPipe có thể lệch nhẹ: nếu chạy `--force mediapipe` hoặc xoá runs/bo200 thì MediaPipe chạy lại trên máy bạn
  và nháp có thể khác nháp chung. Muốn giữ nháp chung thì dùng lượt chạy sẵn hoặc nhập prelabel.xml.
- low_conf đều là false (t_flip chưa được chốt). Khi t_flip được chốt phải chạy lại: `prepare --run bo200 ... --force flags autoqc overlays`.

8. Cách gán và quy ước (giống gói A)
- Trong CVAT mỗi mặt có bảy label (longmaytrai 5, longmayphai 5, songmui 4, mattrai 8, matphai 8, moingoai 12, moitrong 8 = 50 điểm); bạn sửa điểm nháp cho đúng chỗ.
{quy_uoc}
- Hai ảnh 001 và 002 là khởi động (vẫn làm, không tính vào số đo). Bấm giờ theo hướng dẫn của P5/nhóm trưởng; nếu bản tool của bạn có tab "Đồng hồ" thì bấm Bắt đầu trước ảnh 001 và Xong sau ảnh 200.

9. Xuất nhãn gửi nhóm trưởng
CVAT: Actions -> Export task dataset -> "CVAT for images 1.1", KHÔNG kèm ảnh; hoặc `python tool/m28.py collect --task demo-bo200-<Pk> --reviewer <Pk>`. Đặt tên theo quy ước nhóm trưởng. KHÔNG gửi ảnh, KHÔNG gửi token.

10. Dung lượng và sha256 các phần ảnh
{bang}

11. Quyền riêng tư
Ảnh người lái xe: chỉ dùng trong nhóm, không đăng, không gửi ra ngoài, không đưa lên dịch vụ bên ngoài, không đưa lên git. Nguồn và điều khoản: NOTICE.txt.
"""


def doc_readme(kind, parts, n_parts):
    tpl = README_A if kind == 'A' else README_B
    return tpl.format(bo_anh=BO_ANH, ngay=NGAY_TAO, n=f'{n_parts:02d}', quy_uoc=QUY_UOC_DIEM, bang=bang_sha_text(parts))


# ======================================================================================================================
# Lệnh goi: ghi ảnh, sinh nháp bằng m28.py, đóng zip A / B / bí mật
# ======================================================================================================================
ZIP_A, ZIP_B = 'A', 'B'
RUN_BO200 = 'bo200'
RUN_DIRS = ('mediapipe', 'map50', 'flags', 'autoqc')       # các bước chạy sẵn đưa vào gói B (không kèm crop, overlays, review, xml, log.txt, no_face.csv)


def ghi_anh(a, order, img_dir):
    """Ghi ảnh 001..N.png (cat_mat.square_crop trên khung gốc, PNG nén mức PNG_COMPRESSION). Trả {tên: sha256}."""
    shutil.rmtree(img_dir, ignore_errors=True)
    os.makedirs(img_dir)
    frames = thu_muc_khung(a)
    shas = {}
    for so, r in enumerate(order, 1):
        crop = cat_anh(a, r, frames)
        if crop.shape != (OUT, OUT, 3):
            raise SystemExit(f'ảnh cắt {r["name"]} không phải {OUT}x{OUT}: {crop.shape}')
        path = os.path.join(img_dir, f'{so:03d}.png')
        cv2.imwrite(path, crop, [cv2.IMWRITE_PNG_COMPRESSION, ii.PNG_COMPRESSION])
        shas[f'{so:03d}.png'] = sha256_file(path)
    return shas


def chay_m28(cwd, args, model=None, log=None):
    """Chạy ĐÚNG tool/m28.py bằng dòng lệnh trong cwd; trả (mã thoát, đầu ra gộp). PYTHONUTF8=1."""
    env = dict(os.environ, PYTHONUTF8='1')
    p = subprocess.run([sys.executable, os.path.join('tool', 'm28.py'), *args], cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8')
    txt = (p.stdout or '') + (p.stderr or '')
    if log:
        log(f'  m28.py {" ".join(args[:3])}...: mã {p.returncode}')
    return p.returncode, txt


def dung_thu_muc_sinh(a, sinh, img_dir, project=None):
    """Thư mục tạm kiểu thành viên: tool/ và config/ chép từ repo, data/bo200/{anh,manifest.csv}. Trả đường dẫn manifest."""
    project = project or a.project
    shutil.rmtree(sinh, ignore_errors=True)
    os.makedirs(sinh)
    ig = shutil.ignore_patterns('__pycache__', '*.pyc')
    shutil.copytree(os.path.join(project, 'tool'), os.path.join(sinh, 'tool'), ignore=ig)
    shutil.copytree(os.path.join(project, 'config'), os.path.join(sinh, 'config'), ignore=ig)
    d = os.path.join(sinh, 'data', RUN_BO200)
    os.makedirs(d)
    shutil.copytree(img_dir, os.path.join(d, 'anh'))
    ghi_csv(os.path.join(d, 'manifest.csv'), MANIFEST_B_COLS, manifest_b_rows(len(os.listdir(img_dir))))
    return os.path.join(d, 'manifest.csv')


def lenh_prepare(model, run=RUN_BO200):
    return ['prepare', '--run', run, '--manifest', 'data/bo200/manifest.csv', '--list', 'data/bo200/manifest.csv', '--images', 'data/bo200/anh',
            '--box', 'crop', '--model', model]


def so_pixel(dir_a, dir_b):
    """Danh sách tên ảnh KHÁC pixel giữa hai thư mục ảnh cùng tên (np.array_equal)."""
    bad = []
    for n in sorted(os.listdir(dir_a)):
        x, y = cv2.imread(os.path.join(dir_a, n)), cv2.imread(os.path.join(dir_b, n))
        if x is None or y is None or not np.array_equal(x, y):
            bad.append(n)
    return bad


def sinh_nhap(a, img_dir, log):
    """4.5: chạy chính m28.py (prepare -> review auto -> push --dry-run) trong <out>/kiem/sinh; kiểm; trả dict(files={tên trong zip: bytes}, xml=bytes, n=...)."""
    sinh = os.path.join(a.out, 'kiem', 'sinh')
    dung_thu_muc_sinh(a, sinh, img_dir)
    model = os.path.abspath(a.model)
    rc, txt = chay_m28(sinh, lenh_prepare(model), log=log)
    if rc != 0:
        raise SystemExit(f'prepare lỗi (mã {rc}):\n{txt[-1500:]}')
    rc, txt = chay_m28(sinh, ['review', '--run', RUN_BO200, '--review', 'auto'], log=log)
    if rc != 0:
        raise SystemExit(f'review auto lỗi (mã {rc}):\n{txt[-1500:]}')
    rc, txt = chay_m28(sinh, ['push', '--run', RUN_BO200, '--review', 'auto', '--dry-run', '--manifest', 'data/bo200/manifest.csv'], log=log)
    if 'Chạy thử (--dry-run)' not in txt:
        raise SystemExit(f'push --dry-run không ra "Chạy thử (--dry-run)" (mã {rc}):\n{txt[-1500:]}')
    run = os.path.join(sinh, 'runs', RUN_BO200)
    n = len(os.listdir(img_dir))
    with open(os.path.join(run, 'map50', 'mp50.json'), encoding='utf-8') as f:
        mp50 = json.load(f)
    thieu = [f'{i:03d}' for i in range(1, n + 1) if f'{i:03d}' not in mp50]
    if thieu:
        raise SystemExit(f'MediaPipe không thấy mặt ở {len(thieu)} ảnh ({thieu[:5]}): thay ảnh khác rồi chọn lại (mục 3.5)')
    nf = os.path.join(run, 'no_face.csv')
    if os.path.exists(nf) and len(doc_csv(nf)) > 0:
        raise SystemExit(f'no_face.csv không rỗng: {doc_csv(nf)[:3]}')
    bad = so_pixel(img_dir, os.path.join(run, 'crop', 'images'))
    if bad:
        raise SystemExit(f'bước crop cắt lại LỆCH pixel ở {len(bad)} ảnh ({bad[:5]}): sửa cách ghi hộp trong manifest gói B')
    with open(os.path.join(run, 'xml', 'prelabel.xml'), 'rb') as f:
        xml = f.read()
    files = {}
    for sub in RUN_DIRS:
        for root, _, fs in os.walk(os.path.join(run, sub)):
            for fn in fs:
                full = os.path.join(root, fn)
                files['runs/%s/%s' % (RUN_BO200, os.path.relpath(full, run).replace(os.sep, '/'))] = open(full, 'rb').read()
    qc = {r['name']: r['suggestion'] for r in doc_csv(os.path.join(run, 'autoqc', 'autoqc.csv'))}
    log(f'sinh nháp: {len(mp50)} mặt có nháp, crop giống từng pixel; autoqc gợi ý: {dict(Counter(qc.values()))}')
    return dict(files=files, xml=xml, n=len(mp50), autoqc=qc, mp50=mp50)


def entries_anh(img_dir, prefix):
    """[(tên trong zip, đường dẫn)] cho mọi ảnh."""
    return [(f'{prefix}/anh/{n}', os.path.join(img_dir, n)) for n in sorted(os.listdir(img_dir))]


def dong_phan_anh(kind, ents, tmpdir, limit):
    """Chia ảnh thành các phần zip (<= limit) và ghi chúng. Trả [(đường dẫn zip, byte, sha256)]."""
    sizes = [(n, os.path.getsize(src)) for n, src in ents]
    plan = chia_phan(sizes, limit)
    src_of = dict(ents)
    out = []
    for i, names in enumerate(plan, 1):
        path = os.path.join(tmpdir, f'm28_bo200_{kind}_part{i:02d}_of_{len(plan):02d}.zip')
        ghi_zip(path, [(n, src_of[n]) for n in names])
        out.append((path, os.path.getsize(path), sha256_file(path)))
    return out


def cmd_goi(a):
    """Ghi ảnh, sinh nháp, đóng zip gói A, gói B, file bí mật (+ lưới nếu có) và SHA256SUMS_bo200.txt."""
    a.out = check_out_dir(a.out)
    log = lambda m: ghi_nhat_ky(a.out, m)                                     # noqa: E731
    cp = os.path.join(a.out, 'cache', 'chon.json')
    if not os.path.exists(cp):
        raise SystemExit('chưa có cache/chon.json: chạy `chon` trước')
    with open(cp, encoding='utf-8') as f:
        ch = json.load(f)
    rows = tai_bang(a)
    byname = {r['name']: r for r in rows}
    order = [byname[n] for n in ch['thu_tu']]
    img_dir = os.path.join(a.out, 'img', 'anh')
    shas = ghi_anh(a, order, img_dir)
    log(f'goi: ghi {len(shas)} ảnh PNG vào {img_dir}; tổng {sum(os.path.getsize(os.path.join(img_dir, n)) for n in shas) / 1048576:.1f} MiB')
    nh = sinh_nhap(a, img_dir, log)
    label = open(os.path.join(a.project, 'config', 'face50_label.json'), 'rb').read()
    info = info_json(shas).encode('utf-8')
    shatxt = sha_anh_text(shas).encode('utf-8')
    notice = text_crlf(NOTICE)
    manifest = io.StringIO()
    w = csv.DictWriter(manifest, MANIFEST_B_COLS, lineterminator='\n')
    w.writeheader()
    w.writerows(manifest_b_rows(len(shas)))
    tmp = os.path.join(a.out, 'kiem', 'zip_tam')
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    res_zips = {}
    for kind, prefix in ((ZIP_A, 'bo200_A'), (ZIP_B, 'data/bo200')):
        d = os.path.join(a.out, kind)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        parts = dong_phan_anh(kind, entries_anh(img_dir, prefix), tmp, a.limit_bytes)
        n_parts = len(parts)
        tab = [(os.path.basename(p), sz, h) for p, sz, h in parts]
        readme = text_crlf(doc_readme(kind, tab, n_parts))
        meta = {f'{prefix}/README_{kind}.txt': readme, f'{prefix}/NOTICE.txt': notice, f'{prefix}/bo200_info.json': info,
                f'{prefix}/SHA256SUMS_anh.txt': shatxt, f'{prefix}/face50_label.json': label}
        if kind == ZIP_B:
            meta[f'{prefix}/manifest.csv'] = manifest.getvalue().encode('utf-8')
            meta[f'{prefix}/prelabel.xml'] = nh['xml']
            meta.update(nh['files'])
        leaks = quet_ro_ri(list(meta.items()) + [(n, open(s, 'rb').read()) for n, s in entries_anh(img_dir, prefix)])
        if leaks:
            raise SystemExit(f'RÒ RỈ trong gói {kind}: {leaks[:5]}')
        meta_path = os.path.join(d, f'm28_bo200_{kind}_part00_meta.zip')
        ghi_zip(meta_path, list(meta.items()))
        if os.path.getsize(meta_path) > a.limit_bytes:
            raise SystemExit(f'{meta_path} vượt giới hạn {a.limit_bytes}: chia nhỏ phần meta')
        final = [meta_path]
        for p, _, _ in parts:
            shutil.move(p, os.path.join(d, os.path.basename(p)))
            final.append(os.path.join(d, os.path.basename(p)))
        res_zips[kind] = final
        log(f'goi: gói {kind}: ' + ', '.join(f'{os.path.basename(p)} {os.path.getsize(p) / 1048576:.2f} MiB' for p in final))
    bm = os.path.join(a.out, 'bi_mat')
    secret = [(n, os.path.join(bm, n)) for n in ('bo200_bi_mat.csv', 'bo200_bi_mat.md', 'phan_bo.csv', 'nhat_ky_chon.txt', 'sua_the.csv') if os.path.exists(os.path.join(bm, n))]
    zb = ghi_zip(os.path.join(bm, 'bo200_bi_mat.zip'), secret)
    others = [zb]
    lg = sorted(glob.glob(os.path.join(a.out, 'luoi', 'final_*')) + glob.glob(os.path.join(a.out, 'luoi', 'te_*')))     # lưới bộ cuối + ảnh chồng nháp (bằng chứng nháp tệ)
    if lg:
        others.append(ghi_zip(os.path.join(bm, 'bo200_luoi.zip'), [('luoi/' + os.path.basename(p), p) for p in lg]))
    allz = res_zips[ZIP_A] + res_zips[ZIP_B] + others
    lines = ['# sha256 và dung lượng các file zip của bộ 200 ảnh (bo_anh %s). Kiểm: sha256sum -c SHA256SUMS_bo200.txt (Linux) hoặc certutil -hashfile <file> SHA256 (Windows)' % BO_ANH]
    for p in allz:
        lines.append(f'# {os.path.basename(p)}: {os.path.getsize(p)} byte ({os.path.getsize(p) / 1048576:.2f} MiB)')
    for p in allz:
        lines.append(f'{sha256_file(p)}  {os.path.basename(p)}')
    with open(os.path.join(a.out, 'SHA256SUMS_bo200.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    log(f'goi xong: {len(allz)} file zip; bảng sha256: {os.path.join(a.out, "SHA256SUMS_bo200.txt")}')
    return allz


# ======================================================================================================================
# File bí mật dạng đọc được (bo200_bi_mat.md)
# ======================================================================================================================
def bang_the_md():
    """Bảng thẻ: cách đo, ngưỡng, điểm (đúng các hằng số đang dùng)."""
    rows = [('yaw_vua', '|yaw| hệ camera', f'{YAW_VUA:g} <= |yaw| < {YAW_LON:g}'), ('yaw_lon', '|yaw|', f'{YAW_LON:g} <= |yaw| < {YAW_MANH:g}'),
            ('yaw_manh_trai / yaw_manh_phai', 'dấu yaw (yaw > 0 = mặt quay về phía PHẢI ảnh)', f'|yaw| >= {YAW_MANH:g}'),
            ('pitch_vua', '|pitch|', f'{PITCH_VUA:g} <= |pitch| < {PITCH_LECH:g}'), ('pitch_len / pitch_xuong', 'dấu pitch (pitch < 0 = ngẩng lên, > 0 = cúi xuống)', f'|pitch| >= {PITCH_LECH:g}'),
            ('nghieng_dau', '|roll|', f'>= {ROLL_NGHIENG:g}'), ('kinh_can', 'tên video (kính thuốc) hoặc mắt (DrivFace)', 'kính thuốc'),
            ('kinh_ram', 'tên video (kính râm) hoặc mắt', 'kính râm'), ('che_tay', 'mắt (+ gợi ý hand landmarker)', 'tay che miệng/mũi/mắt; che_tay_mat: che mắt -> rất khó'),
            ('che_khac / che_khac_nhieu', 'mắt', 'vô lăng, vật, tóc che một phần mặt'), ('toc_che_may', 'mắt', 'tóc che lông mày'),
            ('noi', 'jawOpen trên ảnh cắt', f'{JAW_NOI:g} <= jaw < {JAW_NGAP:g}'), ('ngap_rong', 'jawOpen', f'>= {JAW_NGAP:g}'),
            ('lim_dim', 'eyeBlink (nhỏ hơn của hai mắt; bỏ khi kính râm hoặc |yaw| >= %g)' % BLINK_YAW_MAX, f'{BLINK_LIM:g}-{BLINK_NHAM:g}'), ('mat_nham', 'eyeBlink', f'>= {BLINK_NHAM:g}'),
            ('toi', 'luma vùng mặt', f'< {LUMA_TOI:g}'), ('sang_chay', 'luma hoặc bright_frac', f'luma > {LUMA_SANG:g} hoặc bright_frac > {BRIGHT_FRAC_SANG:g}'),
            ('tuong_phan_thap', 'contrast', f'< {CONTRAST_THAP:g}'), ('mo', 'lap_var', f'< {ii.BLUR_LAP_VAR["yawdd"]:g} (YawDD) / {ii.BLUR_LAP_VAR["drivface"]:g} (DrivFace)'),
            ('mat_nho', 'cạnh dài hộp mặt (px khung gốc)', f'< {MAT_NHO_PX:g}'), ('rau', 'tên video (Beard/moustache) hoặc mắt', 'râu/ria che viền môi'),
            ('sat_mep', 'pad_frac', f'> {PAD_SAT_MEP:g}'), ('cam_dash / cam_mirror / cam_drivface', 'camera', '(để cân bằng)')]
    L = ['| Thẻ | Đo bằng | Ngưỡng | Điểm |', '|---|---|---|---|']
    for t, how, th in rows:
        first = t.split(' / ')[0]
        L.append(f'| `{t}` | {how} | {th} | {THE_DIEM.get(first, 0):g} |')
    return '\n'.join(L)


def bang_md(tab, tags):
    keep = [t for t in tags if tab['tong'][t]]
    L = ['| Mức | n | ' + ' | '.join(f'`{t}`' for t in keep) + ' |', '|---|---|' + '---|' * len(keep)]
    for m in (*LEVELS, 'tong'):
        L.append(f'| {LEVEL_VI.get(m, "tổng")} | {tab[m]["n"]} | ' + ' | '.join(str(tab[m][t]) for t in keep) + ' |')
    return '\n'.join(L)


def viet_md(a, res, order, thieu, lines, quota, nhan_xet=''):
    items = order
    tab, tags = bang_muc_the(items)
    cnt = Counter(c['subject'] for c in items)
    te = [(i + 1, c) for i, c in enumerate(order) if c['nhap'] == 'te']
    tot = [(i + 1, c) for i, c in enumerate(order) if c['nhap'] == 'tot']
    nghi = [(i + 1, c) for i, c in enumerate(order) if ((_num(c.get('box_iou')) or 1.0) < BOX_IOU_NGHI or (_num(c.get('pad_frac')) or 0.0) > 0.10
                                                       or ((_num(c.get('hand_cov')) or 0.0) >= HAND_COV_GOI_Y and 'che_tay' not in c['the'])
                                                       or str(c.get('ghi_chu_sua', '')).startswith('NGHI'))]
    L = [f'# Bộ 200 ảnh ({BO_ANH}): file BÍ MẬT cho nhóm trưởng', '',
         '**Chỉ nhóm trưởng được giữ file này.** Nó nối số ảnh 001-200 với khung gốc, tài xế, camera, mức khó, thẻ và nháp; gói A và gói B không chứa các thông tin đó. '
         'Trước khi đưa bất kỳ ảnh nào ra ngoài nhóm, tra cột `duoc_dang_anh` và `Table1.pdf`/`Table2.pdf` của YawDD; mọi ảnh chỉ dùng nội bộ, phi thương mại (NOTICE.txt).', '',
         '## 1. Cách chấm độ khó', '',
         'Độ khó là khó khi gán 50 điểm DMS (mày, sống mũi, mắt, môi ngoài, môi trong; không viền hàm). Mỗi ảnh có các thẻ yếu tố, mỗi thẻ một điểm; '
         'tổng S quyết định mức: **dễ** S <= 0,5 (và không thẻ hiếm); **vừa** 1 <= S <= 2,5; **khó** 3 <= S <= 4,5; **rất khó** S >= 5, hoặc tay che mắt (`che_tay_mat`), '
         f'hoặc |yaw| >= {YAW_RAT_KHO:g}, hoặc kính râm cộng một yếu tố >= 1,5. Ngưỡng hiệu chỉnh một lần bằng mắt trên lưới (9/10/2026) và ghi cứng ở đầu `tao_bo200.py`.',
         'Dùng yaw/pitch theo hệ camera (không trừ độ lệch +23 độ của camera Mirror): người gán nhìn ảnh nên cái làm khó là góc mặt so với camera. '
         'Thẻ hiếm: ' + ', '.join(f'`{t}`' for t in THE_HIEM) + '.', '', bang_the_md(), '',
         'Hạn chế: độ khó là ƯỚC LƯỢNG heuristic; mọi ảnh trong bộ đều là ảnh MediaPipe thấy mặt (nháp ASSISTED cần có), nên ca khó nhất (MediaPipe bỏ cuộc) KHÔNG có trong bộ.', '',
         '## 2. Seed, hạn mức và phân bố', ''] + [f'- {x}' for x in lines] + ['', '## 3. Bảng mức x thẻ', '', bang_md(tab, tags), '',
         f'Số ảnh mỗi tài xế (k = {a.k}): ' + ', '.join(f'{s} {n}' for s, n in sorted(cnt.items())) + '.', '']
    L += ['## 4. Thẻ thiếu', '']
    L += ([f'- `{t}`: có {h}/cần {need}; {why}.' for t, h, need, _, why in thieu] if thieu else ['Không thiếu thẻ hiếm nào.'])
    L += ['', f'## 5. Ảnh nháp tệ ({len(te)} ảnh; đã xem ảnh chồng nháp bằng mắt để xác nhận)', '']
    L += [f'- {so:03d} (mức {LEVEL_VI[c["muc"]]}, flip_nme {_num(c.get("flip_nme")) or 0:.1f}% IOD, thẻ: {" ".join(x for x in c["the"] if not x.startswith("cam_"))}; {c.get("ghi_chu_sua", "")})' for so, c in te]
    L += ['', f'Ảnh có nháp TỐT (flip_nme <= {NHAP_TOT_NME} % IOD hoặc thẻ nhap_tot): {len(tot)} ảnh; cột `nhap` của CSV ghi tot / vua / te cho từng ảnh.', '',
          '## 6. Ảnh nghi ngờ (thẻ chưa chắc, nghi bắt nhầm mặt, viền xám lớn...)', '']
    L += ([f'- {so:03d}: ' + (c.get('ghi_chu_sua') or '') + (' hộp mặt MediaPipe lệch hộp ứng viên;' if (_num(c.get('box_iou')) or 1.0) < BOX_IOU_NGHI else '')
           + (' viền xám lớn;' if (_num(c.get('pad_frac')) or 0.0) > 0.10 else '')
           + (' tay gợi ý chưa chốt;' if ((_num(c.get('hand_cov')) or 0.0) >= HAND_COV_GOI_Y and 'che_tay' not in c['the']) else '') for so, c in nghi] or ['Không có.'])
    L += ['', '## 7. Ảnh trùng gói 616 mặt của đội', '']
    t616 = [(i + 1, c) for i, c in enumerate(order) if c.get('trung_goi616')]
    L += ([f'- {so:03d} = {c["trung_goi616"]}' for so, c in t616] or ['Không có.'])
    L += ['', '## 8. Nhận xét từng lưới (kiểm bằng mắt)', '', nhan_xet.strip() or '(chưa có nhận xét)', '']
    return '\n'.join(L)


# ======================================================================================================================
# Lệnh kiem: giải nén sạch từng gói và kiểm như người nhận
# ======================================================================================================================
class BaoCaoKiem:
    """Gom kết quả kiểm theo mục (đạt / KHÔNG đạt + số liệu) và ghi kiem/bao_cao_kiem.txt."""

    def __init__(self, out):
        self.out, self.rows = out, []

    def them(self, ten, ok, chi_tiet=''):
        self.rows.append((ten, bool(ok), chi_tiet))
        ghi_nhat_ky(self.out, f'  kiem [{"đạt" if ok else "KHÔNG ĐẠT"}] {ten}: {chi_tiet}')

    @property
    def ok(self):
        return all(r[1] for r in self.rows)

    def ghi(self, path):
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            for ten, ok, ct in self.rows:
                f.write(f'[{"dat" if ok else "KHONG DAT"}] {ten}: {ct}\n')
            f.write(f'\nTONG: {"DAT" if self.ok else "KHONG DAT"} ({sum(1 for r in self.rows if r[1])}/{len(self.rows)} muc)\n')


def _chay(cmd, cwd=None, inp=None):
    p = subprocess.run(cmd, cwd=cwd, input=inp, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def kiem_goi(a, kind, zips, rb, limit):
    """Kiểm một gói (A hoặc B): toàn vẹn zip, giải nén sạch bằng unzip và zipfile, 200 ảnh 512x512, sha256, dung lượng. Trả {tên ảnh: bytes}."""
    kd = os.path.join(a.out, 'kiem')
    for p in zips:
        rc1, o1 = _chay(['unzip', '-tq', p])
        rc2, o2 = _chay(['7z', 't', p]) if shutil.which('7z') else (0, 'không có 7z')
        with zipfile.ZipFile(p) as z:
            bad = z.testzip()
        rb.them(f'gói {kind}: {os.path.basename(p)} toàn vẹn', rc1 == 0 and rc2 == 0 and bad is None and 'No errors' in o1,
                f'unzip -t mã {rc1}, 7z t mã {rc2}{"" if shutil.which("7z") else " (không có 7z)"}, zipfile.testzip {bad}')
        rb.them(f'gói {kind}: {os.path.basename(p)} <= {limit} byte', os.path.getsize(p) <= limit, f'{os.path.getsize(p)} byte ({os.path.getsize(p) / 1048576:.2f} MiB)')
        with zipfile.ZipFile(p) as z:
            nm = [zi.filename for zi in z.infolist()]
            ok_meta = (nm == sorted(nm) and all(zi.date_time == ZIP_DATE and (zi.external_attr >> 16) == 0o100644 and zi.compress_type == 0 for zi in z.infolist())
                       and all(n.isascii() for n in nm))
        rb.them(f'gói {kind}: {os.path.basename(p)} tất định (mục sắp theo tên, ngày cố định, 0644, ASCII, không nén)', ok_meta, '')
    d1, d2 = os.path.join(kd, f'giainen_unzip_{kind}'), os.path.join(kd, f'giainen_py_{kind}')
    for d in (d1, d2):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    for p in zips:
        _chay(['unzip', '-oq', p, '-d', d1])
        with zipfile.ZipFile(p) as z:
            z.extractall(d2)

    def tree(d):
        return {os.path.relpath(os.path.join(r, f), d).replace(os.sep, '/'): sha256_file(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs}
    t1, t2 = tree(d1), tree(d2)
    rb.them(f'gói {kind}: giải nén bằng unzip và bằng zipfile ra cùng cây thư mục và cùng nội dung', t1 == t2, f'{len(t1)} file')
    root = 'bo200_A' if kind == ZIP_A else 'data/bo200'
    imgs = {n[len(root) + 5:]: n for n in t1 if n.startswith(root + '/anh/')}
    rb.them(f'gói {kind}: đúng 200 ảnh, tên 001.png..200.png', sorted(imgs) == [f'{i:03d}.png' for i in range(1, N_ANH + 1)], f'{len(imgs)} ảnh')
    bad_size = []
    data = {}
    for n, rel in imgs.items():
        im = cv2.imread(os.path.join(d1, rel))
        if im is None or im.shape != (OUT, OUT, 3):
            bad_size.append(n)
        data[n] = open(os.path.join(d1, rel), 'rb').read()
    rb.them(f'gói {kind}: mọi ảnh {OUT} x {OUT}', not bad_size, f'sai: {bad_size[:3]}')
    sums = {ln.split()[1][4:]: ln.split()[0] for ln in open(os.path.join(d1, root, 'SHA256SUMS_anh.txt'), encoding='utf-8').read().splitlines() if ln.strip()}
    mis = [n for n in imgs if sums.get(n) != t1[imgs[n]]]
    rb.them(f'gói {kind}: sha256 từng ảnh khớp SHA256SUMS_anh.txt', not mis and len(sums) == len(imgs), f'lệch: {mis[:3]}')
    info = json.load(open(os.path.join(d1, root, 'bo200_info.json'), encoding='utf-8'))
    rb.them(f'gói {kind}: bo200_info.json (bo_anh, so_anh, warmup, sha256)', info['bo_anh'] == BO_ANH and info['so_anh'] == N_ANH and info['warmup'] == ['001.png', '002.png']
            and all(info['sha256'][n] == t1[imgs[n]] for n in imgs), f'bo_anh {info["bo_anh"]}, so_anh {info["so_anh"]}')
    bad_chunk = [n for n, b in data.items() if set(png_chunks(b)) - ANH_PNG_CHUNKS]
    rb.them(f'gói {kind}: ảnh không mang metadata (chỉ chunk IHDR/IDAT/IEND)', not bad_chunk, f'có metadata: {bad_chunk[:3]}')
    ents = []
    for r_, _, fs in os.walk(d1):
        for f in fs:
            full = os.path.join(r_, f)
            ents.append((os.path.relpath(full, d1).replace(os.sep, '/'), open(full, 'rb').read()))
    leaks = quet_ro_ri(ents)
    rb.them(f'gói {kind}: quét rò rỉ trên {len(ents)} mục (mã tài xế, video, camera/nguồn, khung gốc, thẻ, đường dẫn tuyệt đối, tên máy)', not leaks, f'{leaks[:3]}')
    return data, d1, root


def kiem_chay_tool(a, rb, d1B, rootB, imgsA):
    """Gói B với CODE CỦA HEAD (git archive) + model + giải nén B: (a) prepare dùng lượt chạy sẵn; (b) review auto + push dry-run ra prelabel.xml trùng byte;
    (c) eval50 NME 0; (d) chạy lại từ đầu với lượt tên khác, so toạ độ."""
    kd = os.path.join(a.out, 'kiem')
    head = os.path.join(kd, 'head')
    shutil.rmtree(head, ignore_errors=True)
    os.makedirs(head)
    repo = repo_root()
    p1 = subprocess.Popen(['git', '-C', repo, 'archive', 'HEAD', 'source-tool/m28-prelabel'], stdout=subprocess.PIPE)
    p2 = subprocess.run(['tar', '-x', '-C', head], stdin=p1.stdout, capture_output=True)
    p1.stdout.close()
    p1.wait()
    proj = os.path.join(head, 'source-tool', 'm28-prelabel')
    rb.them('B: lấy code HEAD bằng git archive', p1.returncode == 0 and p2.returncode == 0 and os.path.exists(os.path.join(proj, 'tool', 'm28.py')),
            f'HEAD {_chay(["git", "-C", repo, "rev-parse", "--short", "HEAD"])[1].strip()}')
    shutil.copyfile(a.model, os.path.join(proj, 'face_landmarker.task'))
    for p in sorted(glob.glob(os.path.join(a.out, ZIP_B, 'm28_bo200_B_part*.zip'))):
        with zipfile.ZipFile(p) as z:
            z.extractall(proj)
    model = 'face_landmarker.task'
    rc, txt = chay_m28(proj, lenh_prepare(model))
    lg = open(os.path.join(proj, 'runs', RUN_BO200, 'log.txt'), encoding='utf-8').read().splitlines() if os.path.exists(os.path.join(proj, 'runs', RUN_BO200, 'log.txt')) else []
    st = {ln.split('\t')[1]: ln.split('\t')[2] for ln in lg if ln.count('\t') >= 2}
    ok_a = rc == 0 and st.get('crop') == 'xong' and all(st.get(s) == 'bo_qua' for s in ('mediapipe', 'map50', 'flags', 'autoqc')) and st.get('overlays') == 'xong'
    bad = so_pixel(os.path.join(proj, 'data', RUN_BO200, 'anh'), os.path.join(proj, 'runs', RUN_BO200, 'crop', 'images'))
    rb.them('B (a): prepare với lượt chạy sẵn: crop xong; mediapipe/map50/flags/autoqc bỏ qua; overlays xong', ok_a, f'mã {rc}, trạng thái {st}')
    rb.them('B (a): ảnh crop/images giống từng pixel data/bo200/anh (200 ảnh)', not bad and len(os.listdir(os.path.join(proj, 'runs', RUN_BO200, 'crop', 'images'))) == N_ANH,
            f'lệch: {bad[:3]}')
    rc, txt = chay_m28(proj, ['review', '--run', RUN_BO200, '--review', 'auto'])
    rc2, txt2 = chay_m28(proj, ['push', '--run', RUN_BO200, '--review', 'auto', '--dry-run', '--manifest', 'data/bo200/manifest.csv'])
    x1 = open(os.path.join(proj, 'data', RUN_BO200, 'prelabel.xml'), 'rb').read()
    x2 = open(os.path.join(proj, 'runs', RUN_BO200, 'xml', 'prelabel.xml'), 'rb').read()
    rb.them('B (b): review auto + push --dry-run: prelabel.xml sinh ra trùng TỪNG BYTE data/bo200/prelabel.xml (push dry-run thoát mã != 0 là đúng thiết kế)',
            rc == 0 and rc2 != 0 and 'Chạy thử (--dry-run)' in txt2 and x1 == x2, f'review mã {rc}, push mã {rc2}, {len(x1)} byte, sha256 {sha256_bytes(x1)[:12]}')
    # lệnh trong README_B (chạy thử không CVAT): all --review auto --dry-run, cùng lượt bo200
    rc3, txt3 = chay_m28(proj, ['all', '--run', RUN_BO200, '--manifest', 'data/bo200/manifest.csv', '--list', 'data/bo200/manifest.csv', '--images', 'data/bo200/anh',
                                '--box', 'crop', '--review', 'auto', '--dry-run', '--model', model])
    x3 = open(os.path.join(proj, 'runs', RUN_BO200, 'xml', 'prelabel.xml'), 'rb').read()
    rb.them('B (b2): lệnh `all ... --review auto --dry-run` trong README_B chạy được (bỏ qua các bước đã xong, thoát mã != 0), XML vẫn trùng byte',
            rc3 != 0 and 'Chạy thử (--dry-run)' in txt3 and 'bỏ qua mediapipe' in txt3 and x3 == x1, f'mã {rc3}')
    rc, txt = _chay([sys.executable, os.path.join('tool', 'eval50.py'), '--gt', 'data/bo200/prelabel.xml', '--pred', 'runs/bo200/xml/prelabel.xml'], cwd=proj)
    nm = re.findall(r'(?i)nme[^\n]*', txt)[:2]
    rb.them('B (c): eval50.py --gt prelabel.xml --pred prelabel.xml chạy được, NME 0', rc == 0 and bool(re.search(r'(?i)trung bình[^\n]*0[.,]00|mean[^\n]*0[.,]00|NME[^\n]*\b0[.,]0', txt)),
            f'mã {rc}; {nm}')
    # (d) chạy lại từ đầu, không lượt chạy sẵn, lượt tên khác
    h2 = os.path.join(kd, 'head2')
    shutil.rmtree(h2, ignore_errors=True)
    shutil.copytree(proj, h2, ignore=shutil.ignore_patterns('runs'))
    rc, txt = chay_m28(h2, lenh_prepare(model, run='bo200r'))
    f1 = json.load(open(os.path.join(proj, 'runs', RUN_BO200, 'map50', 'mp50.json'), encoding='utf-8'))
    f2p = os.path.join(h2, 'runs', 'bo200r', 'map50', 'mp50.json')
    if rc == 0 and os.path.exists(f2p):
        f2 = json.load(open(f2p, encoding='utf-8'))
        dev = [np.linalg.norm(np.array(f1[n]['orig'][k]) - np.array(f2[n]['orig'][k])) for n in f1 for k in f1[n]['orig']]
        rb.them('B (d): chạy lại MediaPipe từ đầu (lượt tên khác, không lượt chạy sẵn): so toạ độ 50 điểm với nháp chung', len(f1) == len(f2) == N_ANH,
                f'{len(dev)} điểm; lệch lớn nhất {max(dev):.4f} px, trung bình {np.mean(dev):.4f} px')
    else:
        rb.them('B (d): chạy lại từ đầu', False, f'mã {rc}: {txt[-300:]}')


def kiem_git(a, rb):
    rc, out = _chay(['git', '-C', repo_root(), 'status', '--porcelain'])
    bad = [ln for ln in out.splitlines() if re.search(r'\.(png|jpe?g|zip|csv|xml|npz|jsonl|task|avi|mp4)$', ln.strip(), re.I)]
    rb.them('git status: không có ảnh, zip, csv/xml dữ liệu nào trong repo', rc == 0 and not bad, f'{len(out.splitlines())} mục thay đổi; vi phạm: {bad[:3]}')


def cmd_kiem(a):
    """Kiểm như người nhận: giải nén sạch từng gói, kiểm toàn vẹn, ảnh, sha256, rò rỉ; chạy tool bằng code HEAD trên gói B; git status. Ghi kiem/bao_cao_kiem.txt."""
    a.out = check_out_dir(a.out)
    rb = BaoCaoKiem(a.out)
    zA = sorted(glob.glob(os.path.join(a.out, ZIP_A, 'm28_bo200_A_part*.zip')))
    zB = sorted(glob.glob(os.path.join(a.out, ZIP_B, 'm28_bo200_B_part*.zip')))
    if not zA or not zB:
        raise SystemExit('chưa có gói A/B: chạy `goi` trước')
    dA, d1A, rA = kiem_goi(a, ZIP_A, zA, rb, a.limit_bytes)
    dB, d1B, rB = kiem_goi(a, ZIP_B, zB, rb, a.limit_bytes)
    same = sorted(dA) == sorted(dB) and all(dA[n] == dB[n] for n in dA)
    rb.them('ảnh gói A = ảnh gói B giống hệt từng byte (sha256)', same, f'{len(dA)} ảnh')
    with open(os.path.join(a.out, 'SHA256SUMS_bo200.txt'), encoding='utf-8') as f:
        sums = {ln.split()[1]: ln.split()[0] for ln in f.read().splitlines() if ln.strip() and not ln.startswith('#')}
    where = {k: glob.glob(os.path.join(a.out, '*', k)) for k in sums}
    bad = [k for k, h in sums.items() if len(where[k]) != 1 or sha256_file(where[k][0]) != h]
    rb.them('SHA256SUMS_bo200.txt (tên file, không đường dẫn) khớp mọi file zip', not bad and len(sums) >= len(zA) + len(zB) + 1, f'{len(sums)} zip; lệch: {bad[:3]}')
    kiem_chay_tool(a, rb, d1B, rB, dA)
    kiem_git(a, rb)
    path = os.path.join(a.out, 'kiem', 'bao_cao_kiem.txt')
    rb.ghi(path)
    ghi_nhat_ky(a.out, f'kiem xong: {"ĐẠT" if rb.ok else "KHÔNG ĐẠT"} ({sum(1 for r in rb.rows if r[1])}/{len(rb.rows)} mục); báo cáo {path}')
    return rb


# ======================================================================================================================
# ==== CLI ====
# ======================================================================================================================
def build_parser():
    p = argparse.ArgumentParser(prog='tao_bo200', description=__doc__.split('\n')[0])
    p.add_argument('cmd', choices=['do', 'them', 'chon', 'luoi', 'goi', 'kiem', 'all'])
    p.add_argument('--out', default=os.path.join(os.path.expanduser('~'), 'm28_bo200'), help='thư mục ra (NGOÀI repo)')
    p.add_argument('--candidates', help='candidates.csv của gói in-cabin (cache/candidates.csv)')
    p.add_argument('--frames', help='thư mục khung ứng viên (mặc định <thư mục candidates.csv>/frames)')
    p.add_argument('--manifest616', help='manifest.csv của gói 616 mặt (để đánh dấu ứng viên trùng)')
    p.add_argument('--yawdd', help='thư mục "YawDD dataset" (chỉ lệnh them)')
    p.add_argument('--drivface', help='thư mục DrivFace (để tính sai số 5 điểm mốc, chỉ tham khảo)')
    p.add_argument('--model', default='face_landmarker.task')
    p.add_argument('--hand-model', help='hand_landmarker.task (tuỳ chọn, gợi ý ứng viên che tay; ngoài git)')
    p.add_argument('--project', default=PROJECT, help='thư mục m28-prelabel (lấy config/); mặc định thư mục chứa tool/')
    p.add_argument('--seed', type=int, default=7, help='seed khởi đầu (thử seed, seed+1, ...)')
    p.add_argument('--k', type=int, default=K_PER_SUBJECT, help='tối đa ảnh mỗi tài xế')
    p.add_argument('--quota', default=','.join(f'{k}={v}' for k, v in QUOTA.items()), help='hạn mức mức, ví dụ de=40,vua=70,kho=60,rat_kho=30')
    p.add_argument('--min-the', type=int, default=MIN_THE, help='tối thiểu mỗi thẻ hiếm')
    p.add_argument('--sua-the', help='file sửa thẻ bằng mắt (ung_vien,the_them,the_bo,quyet_dinh,ghi_chu)')
    p.add_argument('--limit-bytes', type=int, default=ii.LIMIT_BYTES, help='kích thước tối đa một file zip')
    p.add_argument('--jobs', type=int, default=3, help='do/them: số tiến trình')
    p.add_argument('--limit', type=int, help='do: chỉ đo ngần này ứng viên (thử nhanh)')
    p.add_argument('--fresh', action='store_true', help='do: bỏ cache đo, đo lại từ đầu')
    p.add_argument('--dry-run', action='store_true', help='chon: chỉ in bảng phân bố và thẻ thiếu, không ghi gì')
    g = p.add_argument_group('them')
    g.add_argument('--cho-the', help='them: thẻ hiếm cần trích thêm, cách nhau dấu phẩy (mặc định: tự suy từ bảng đo)')
    g.add_argument('--can-them', type=int, default=CAN_THEM, help='them: thẻ có ít hơn ngần này ứng viên ngoài 616 thì trích thêm')
    g.add_argument('--step', type=float, default=STEP_THEM_S, help='them: bước lấy mẫu (giây)')
    g.add_argument('--per-video', type=int, default=PER_VIDEO_THEM, help='them: tối đa khung giữ thêm mỗi video')
    g.add_argument('--video-re', help='them: chỉ video có đường dẫn khớp regex này (thử nhanh)')
    g = p.add_argument_group('chon')
    g.add_argument('--table1', help='chon: Table1.pdf của YawDD đã đổi sang văn bản (pdftotext -layout) để ghi cột duoc_dang_anh (Mirror)')
    g.add_argument('--table2', help='chon: Table2.pdf đã đổi sang văn bản (Dash)')
    g = p.add_argument_group('luoi')
    g.add_argument('--ten', default='luoi', help='luoi: tên tệp lưới (luoi/<tên>_NN.jpg)')
    g.add_argument('--nguon', choices=['bang', 'chon'], default='bang', help='luoi: lấy từ bảng đo hoặc từ bộ 200 đã chọn (theo số)')
    g.add_argument('--the', help='luoi: chỉ ứng viên có MỌI thẻ này (cách nhau dấu phẩy)')
    g.add_argument('--where', action='append', help='luoi: điều kiện, ví dụ yaw>=40, abs_pitch>=20, glasses==sunglasses (nhắc lại được)')
    g.add_argument('--camera', choices=['dash', 'mirror', 'drivface'])
    g.add_argument('--source', choices=['yawdd', 'drivface'])
    g.add_argument('--muc', choices=list(LEVELS))
    g.add_argument('--subject')
    g.add_argument('--sort', help='luoi: cột[:desc]')
    g.add_argument('--n', type=int, default=30, help='luoi: số ô (6 x 5 = 30 ô một ảnh)')
    g.add_argument('--cols', type=int, default=6)
    g.add_argument('--rows', type=int, default=5)
    g.add_argument('--cell', type=int, default=256, help='luoi: cạnh ô (px); ảnh lưới <= ~1600 px mỗi cạnh')
    g.add_argument('--skip', type=int, default=0)
    g.add_argument('--sample', type=int, help='luoi: lấy ngẫu nhiên ngần này ô (theo --seed)')
    g.add_argument('--overlay', action='store_true', help='luoi: vẽ 50 điểm nháp (tô màu nhóm) lên ảnh')
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.out = check_out_dir(a.out)
    if a.cmd in ('do', 'all'):
        if not a.candidates:
            raise SystemExit('do cần --candidates')
        cmd_do(a)
    if a.cmd == 'them':
        cmd_them(a)
    if a.cmd == 'luoi':
        cmd_luoi(a)
    if a.cmd in ('chon', 'all'):
        cmd_chon(a)
    if a.cmd in ('goi', 'all'):
        cmd_goi(a)
    if a.cmd in ('kiem', 'all'):
        rb = cmd_kiem(a)
        if not rb.ok:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
