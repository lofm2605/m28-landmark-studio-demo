"""Cắt mặt vuông 512 x 512 quanh hộp mặt (dùng chung cho mọi nguồn dữ liệu). Chỉ numpy và cv2.

Module trung lập cho mọi nguồn dữ liệu: steps.py, inc_ingest.py và các test dùng chung hai hàm này.
"""
import numpy as np

OUT = 512
SIDE_SCALE = 1.4


def crop_geometry(bbox, pts, side_scale=SIDE_SCALE, out=OUT):
    """Cạnh dài x 1,4, cùng tâm. Trả (left, top, k, inside, gt). Không cần ảnh."""
    x0, y0, x1, y1 = [float(v) for v in bbox]
    side = side_scale * max(x1 - x0, y1 - y0)
    left, top = (x0 + x1 - side) / 2, (y0 + y1 - side) / 2
    k = out / side
    gt = (pts - np.float32([left, top])) * k
    inside = bool(((gt >= 0) & (gt <= out - 1)).all())
    return left, top, k, inside, gt


def square_crop(img, bbox, pts, side_scale=SIDE_SCALE, out=OUT):
    import cv2
    left, top, k, inside, gt = crop_geometry(bbox, pts, side_scale, out)
    M = np.float32([[k, 0, -left * k], [0, k, -top * k]])
    crop = cv2.warpAffine(img, M, (out, out), borderValue=(128, 128, 128))
    return crop, gt, (left, top, k), inside
