"""Kiểm manifest.csv. In lỗi và thoát mã 1 nếu sai (P1 chạy, P5 soát).

    python tool\\check_manifest.py data\\manifest.csv

Manifest là manifest IN-CABIN (YawDD + DrivFace, QĐ-001), có cột `source`: kiểm số lượng, tên file, khối X, tách người,
cột giá trị, khoảng cách giữa hai khung cùng video. Thiếu cột `source` thì báo lỗi.
Các hằng số và hàm dùng chung với inc_ingest.py nằm ở đây (một nguồn duy nhất): inc_ingest.py import từ file này.
"""
import csv
import re
import sys
from collections import Counter, defaultdict

EXPECT = {'F': 300, 'Tdev': 100, 'Ttest': 100, 'G': 20, 'P': 16, 'X': 50, 'D': 30}
FLAGS = ['pose', 'expression', 'illumination', 'makeup', 'occlusion', 'blur']
NAME = re.compile(r'^(F_\d{3}|Tdev_\d{3}|Ttest_\d{3}|G[1-5]_\d{2}|P[ab]_\d{2}|X[1-5]_\d{2}|D_\d{2})\.png$')

# ---------- dùng chung với inc_ingest.py (in-cabin) ----------
GROUP_A = ('F', 'Tdev', 'Ttest')          # ba tập này đôi một không chung người
GROUP_B = ('G', 'P', 'X', 'D')            # nhóm B: dùng chung người giữa các tập, nhưng không chung với nhóm A
MIN_GAP_S = 2.0                           # hai khung cùng video (YawDD) cách nhau ít nhất ngần này giây
DF_MIN_GAP_IMGS = 3                       # DrivFace: hai ảnh cùng tài xế cách nhau ít nhất ngần này số thứ tự ảnh (imgNum)
MAX_PER_VIDEO = 3                         # tối đa số mặt của một video trong manifest
SOURCES = ('yawdd', 'drivface')
CAMERAS = ('dash', 'mirror', 'drivface')
GENDERS = ('F', 'M', 'unknown')
GLASSES = ('none', 'glasses', 'sunglasses', 'unknown')
STATES = ('normal', 'talking', 'yawning', 'talking_yawning', 'dash', 'unknown')
SUBJECT_RE = re.compile(r'^(yd_[FM]\d{3}|df_\d{2})$')
MEASURES = ['yaw', 'pitch', 'roll', 'jaw_open', 'luma', 'contrast', 'bright_frac', 'lap_var',
            'gaze_label', 'gaze_ang', 'pad_frac']            # cột đo thô (để ai cũng soát lại được cờ)
INC_COLUMNS = ['file', 'set', 'block', 'seq', 'source', 'camera', 'subject', 'gender', 'glasses', 'state',
               'video', 'frame', 't_s', 'image', 'face_idx', 'x0', 'y0', 'x1', 'y1', 'left', 'top', 'k',
               *FLAGS, *MEASURES, 'seed']
X_NEED_KNOWN = ('gender', 'camera', 'glasses')   # khối X phải có >= 2 giá trị KHÁC NHAU (bỏ 'unknown') cho mỗi cột này


def _i(v):
    return int(float(v))


def x_block_errors(b, label='khối X'):
    """Luật một khối X (10 mặt): 1-2 pose=1, 2-4 occlusion=1, seq 1-2 cả 6 cờ = 0, không hai khung cùng video,
    đa dạng (>= 2 giới, >= 2 loại camera, >= 2 loại kính, không tính 'unknown'; chỉ kiểm khi manifest có các cột đó)."""
    err = []
    if len(b) != 10:
        return [f'{label}: {len(b)} mặt, cần 10']
    pose = sum(_i(r['pose']) for r in b)
    occ = sum(_i(r['occlusion']) for r in b)
    if not 1 <= pose <= 2:
        err.append(f'{label}: {pose} mặt pose=1, cần 1-2')
    if not 2 <= occ <= 4:
        err.append(f'{label}: {occ} mặt occlusion=1, cần 2-4')
    for r in b:
        if _i(r['seq']) <= 2 and any(_i(r[f]) for f in FLAGS):
            err.append(f'{r["file"]}: seq 1-2 của khối X phải có cả 6 cờ = 0')
    if 'source' in b[0]:
        for col in X_NEED_KNOWN:
            kinds = {r[col] for r in b} - {'unknown'}
            if len(kinds) < 2:
                err.append(f'{label}: cột {col} chỉ có {sorted(kinds)}, cần >= 2 giá trị khác nhau')
        vids = Counter(r['video'] for r in b)
        err += [f'{label}: hai khung cùng video {v}' for v, c in vids.items() if c > 1]
    return err


def x_blocks_ok(b):
    return not x_block_errors(b)


def _gap_errors(rows):
    """Hai mặt cùng video (YawDD: cùng `video`, so t_s; DrivFace: cùng tài xế, so imgNum) phải đủ xa nhau."""
    err = []
    g = defaultdict(list)
    for r in rows:
        if r['source'] == 'yawdd':
            g[('yawdd', r['video'])].append(float(r['t_s']))
        else:
            g[('drivface', r['subject'])].append(float(r['frame']))
    for (src, key), vals in g.items():
        need = MIN_GAP_S if src == 'yawdd' else DF_MIN_GAP_IMGS
        vals.sort()
        for a, b in zip(vals, vals[1:]):
            if b - a < need - 1e-6:
                err.append(f'{key}: hai mặt cách nhau {b - a:.2f} {"giây" if src == "yawdd" else "ảnh"}, cần >= {need}')
    return err


def _check_common(rows, key_cols):
    err = []
    cnt = Counter(r['set'] for r in rows)
    for s, n in EXPECT.items():
        if cnt.get(s, 0) != n:
            err.append(f'tập {s}: {cnt.get(s, 0)} mặt, cần {n}')
    for s in cnt.keys() - EXPECT.keys():
        err.append(f'tập lạ: {s}')
    keys = Counter(tuple(r[c] for c in key_cols) for r in rows)
    err += [f'trùng ({", ".join(key_cols)}): {k}' for k, c in keys.items() if c > 1]
    names = Counter(r['file'] for r in rows)
    err += [f'trùng tên file: {k}' for k, c in names.items() if c > 1]
    err += [f'tên file sai mẫu: {r["file"]}' for r in rows if not NAME.match(r['file'])]
    return err


def _name_matches_set(r):
    """Tên file phải khớp set/block/seq: F_001 (seq 1), G2_03 (block 2, seq 3), Pa_01 (block a), X5_10, D_07..."""
    m = re.match(r'^([A-Za-z]+?)([1-5ab]?)_(\d+)\.png$', r['file'])
    if not m:
        return False
    s, blk, seq = m.group(1), m.group(2), int(m.group(3))
    return s == r['set'] and blk == (r['block'] or '') and seq == _i(r['seq'])


def check_incabin(rows):
    err = []
    if not rows:
        return ['manifest rỗng']
    missing = [c for c in INC_COLUMNS if c not in rows[0]]
    if missing:
        return [f'thiếu cột bắt buộc: {missing}']
    err += _check_common(rows, ('image', 'face_idx'))
    err += [f'{r["file"]}: set/block/seq không khớp tên file' for r in rows
            if NAME.match(r['file']) and not _name_matches_set(r)]
    for k in '12345':
        b = [r for r in rows if r['set'] == 'X' and r['block'] == k]
        err += x_block_errors(b, f'khối X{k}')
    # cột giá trị
    allowed = dict(source=SOURCES, camera=CAMERAS, gender=GENDERS, glasses=GLASSES, state=STATES)
    for r in rows:
        for col, ok in allowed.items():
            if r[col] not in ok:
                err.append(f'{r["file"]}: {col}={r[col]!r} ngoài {ok}')
        for f in FLAGS:
            if r[f] not in ('0', '1'):
                err.append(f'{r["file"]}: cờ {f}={r[f]!r}, chỉ được 0 hoặc 1')
        if r['makeup'] != '0':
            err.append(f'{r["file"]}: makeup phải = 0 (bộ này không ước lượng được)')
        if not SUBJECT_RE.match(r['subject']):
            err.append(f'{r["file"]}: subject {r["subject"]!r} sai mẫu yd_[FM]000 / df_00')
    # tách người
    people = defaultdict(set)
    for r in rows:
        people[r['set']].add(r['subject'])
    a_all = set().union(*(people.get(s, set()) for s in GROUP_A))
    b_all = set().union(*(people.get(s, set()) for s in GROUP_B))
    if a_all & b_all:
        err.append(f'người có mặt ở cả nhóm A (F/Tdev/Ttest) và B (G/P/X/D): {sorted(a_all & b_all)}')
    for i, s in enumerate(GROUP_A):
        for t in GROUP_A[i + 1:]:
            both = people.get(s, set()) & people.get(t, set())
            if both:
                err.append(f'tập {s} và {t} chung người: {sorted(both)}')
    # giới hạn mỗi video và khoảng cách
    try:
        per = Counter((r['source'], r['video']) for r in rows)
        err += [f'video {v} có {c} mặt, tối đa {MAX_PER_VIDEO}' for (_, v), c in per.items()
                if c > MAX_PER_VIDEO and _ == 'yawdd']
        err += _gap_errors(rows)
    except (ValueError, KeyError) as e:
        err.append(f'cột t_s/frame không đọc được: {e}')
    return err


def check(rows):
    """Manifest in-cabin: cần cột `source`, `image`, `face_idx`; thiếu thì báo lỗi."""
    if rows and 'source' in rows[0]:
        return check_incabin(rows)
    return ['manifest cần cột source, image, face_idx (manifest in-cabin YawDD + DrivFace)']


def kind_of(rows):
    return 'in-cabin (YawDD + DrivFace)' if rows and 'source' in rows[0] else 'không rõ (thiếu cột source)'


def main(path='data/manifest.csv'):
    with open(path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    print(f'Kiểm manifest kiểu: {kind_of(rows)}')
    err = check(rows)
    for e in err:
        print('LỖI:', e)
    print('manifest.csv đạt' if not err else f'{len(err)} lỗi')
    return 1 if err else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:2]))
