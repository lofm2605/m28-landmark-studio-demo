"""Điểm bị che do MẶT NGHIÊNG (tự che): đặt occluded=1 trong file nháp, giữ nguyên vị trí ước lượng, không dùng outside.

MediaPipe không cho biết điểm nào bị che (visibility/presence của landmark mặt luôn rỗng), nên suy từ góc quay đầu:
  u = (x mũi - trung điểm hai gò má) / nửa bề ngang mặt, tính từ lưới 478 điểm của ảnh gốc (mũi = 1, gò má = 234 và 454).
  u < 0: mũi lệch sang nửa TRÁI ảnh, mặt quay về bên trái ảnh; nửa mặt bên đó nằm xa camera nên bị che (L theo config, side theo bức ảnh). u > 0 thì ngược lại.
  Góc quay ước lượng yaw = (|u| + 0.08) / 0.0405 độ: hồi quy trên 198 ảnh in-cabin (bo200_A) so với ma trận biến đổi mặt của MediaPipe (hệ số tương quan 0.98,
  yaw 0 đến 63 độ); ngoài khoảng đó chỉ là ngoại suy.
  Nửa mặt xa camera: lông mày và mắt bị che từ YAW_MAT độ; môi (các điểm cùng bên) bị che từ YAW_MOI độ. Sống mũi và các điểm trên trục (side M) không bao giờ bị che.
VẬT THỂ CHE MẮT (mặt nhìn thẳng; kính đen, vật mờ trước mắt): đo trên ảnh cắt, vùng đa giác của mắt (lưới 478 điểm), so với vòng da quanh mắt:
  gm   = độ nét = trung bình độ lớn gradient (Sobel, ảnh xám đã làm mờ nhẹ) trong vùng mắt / khoảng cách hai khoé mắt ngoài * 100 (mắt bình thường 15 đến 60).
  lum  = độ sáng trung bình vùng mắt / độ sáng trung bình vòng da quanh.
  sang = chỗ SÁNG NHẤT của vùng mắt (phân vị 90) / trung vị vòng da: mắt mở có lòng trắng sáng, mắt nhắm có mí cùng màu da (0,4 đến 1,2), tròng kính đen thì không có
         chỗ nào sáng (0,14 đến 0,35 trên các ca kính đen của bo200_A).
  Mắt bị che khi: gm < GM_PHANG (vùng gần như phẳng: vật mờ che, mắt chìm hẳn trong bóng tối), hoặc là tròng kính đen (sang < SANG_KINH và lum < LUM_KINH).
  Một mắt là tròng kính đen thì mắt kia cũng bị che nếu nó tối (lum < LUM_KINH_CAP): kính râm che cả hai mắt.
  Ngưỡng chọn CHẶT (sau khi xem tay trên 198 ảnh in-cabin và 5 ảnh chạy qua prepare): bản trước (gm < 6 hoặc tối và gm < 10) báo nhầm mắt thật hơi mờ/tối
  (ví dụ ảnh 010); bản này trên 198 ảnh chỉ đánh dấu 4 mặt (3 ca kính đen và 1 mắt chìm trong bóng tối). Kính râm PHẢN CHIẾU (sáng, nhiều chi tiết) thì KHÔNG bắt được.
  Chỉ áp cho MẮT: với miệng và lông mày, độ nét thấp chủ yếu là ảnh mờ hay tối, không phải bị che, nên không đoán. Người rà sửa occluded ngay trong CVAT khi cần.
  Vùng mắt PHẲNG hoàn toàn vì lý do khác (ảnh cháy sáng, ảnh hồng ngoại bị loá đúng chỗ mắt) cũng bị coi là bị che: đúng là không thấy mắt, người rà tự quyết.
Không phát hiện tay che miệng, khẩu trang, vật che lông mày (chưa có cách đáng tin).
"""
import numpy as np

NOSE, CHEEK_L, CHEEK_R = 1, 234, 454          # chỉ số trong lưới 478 điểm của MediaPipe
YAW_MAT = 60.0                                # độ: từ đây lông mày và mắt của nửa mặt xa camera bị che
YAW_MOI = 75.0                                # độ: từ đây môi của nửa mặt xa camera bị che
_A, _B = 0.0405, 0.08                         # |u| = _A * yaw - _B (hồi quy nói ở trên)
GM_PHANG = 4.0                                # độ nét vùng mắt dưới mức này: gần như phẳng, bị che
SANG_KINH, LUM_KINH = 0.38, 0.25              # tròng kính đen: chỗ sáng nhất < 0,38 lần da quanh VÀ trung bình < 0,25 lần
LUM_KINH_CAP = 0.45                           # mắt kia của người đeo kính đen: tối hơn 0,45 lần da quanh thì cũng bị che
MAT_TRAI = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246)       # mắt của người ở nửa TRÁI ảnh (không soi gương)
MAT_PHAI = (362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398)
KHOE_NGOAI = (33, 263)                        # hai khoé mắt ngoài: đo khoảng cách hai mắt
VUNG_MAT = ("brow", "eye")
VUNG_MOI = ("lip",)


def lech_mui(pts478):
    """u của một mặt (list [x, y] theo pixel, 478 điểm), hoặc None nếu thiếu điểm hay mặt không có bề ngang."""
    p = np.asarray(pts478, float)
    if p.ndim != 2 or len(p) <= CHEEK_R:
        return None
    nua = (p[CHEEK_R, 0] - p[CHEEK_L, 0]) / 2.0
    if abs(nua) < 1e-6:
        return None
    return float((p[NOSE, 0] - (p[CHEEK_L, 0] + p[CHEEK_R, 0]) / 2.0) / nua)


def yaw_uoc_luong(pts478):
    """Góc quay đầu ước lượng theo độ (luôn dương), hoặc None."""
    u = lech_mui(pts478)
    return None if u is None else max(0.0, (abs(u) + _B) / _A)


def do_vung_mat(gray, pts478):
    """{'L': (gm, lum, sang), 'R': (...)}: độ nét, độ sáng trung bình tương đối và chỗ sáng nhất tương đối của mắt ở nửa trái, nửa phải ảnh (xem đầu file). gray: ảnh xám (numpy 2 chiều). Vùng ngoài ảnh hoặc quá nhỏ thì bỏ."""
    import cv2
    p = np.asarray(pts478, float)
    if gray is None or getattr(gray, "ndim", 0) != 2 or p.ndim != 2 or len(p) <= max(MAT_TRAI + MAT_PHAI):
        return {}
    g = gray.astype(np.float32)
    gm = cv2.magnitude(cv2.Sobel(cv2.GaussianBlur(g, (0, 0), 1.0), cv2.CV_32F, 1, 0), cv2.Sobel(cv2.GaussianBlur(g, (0, 0), 1.0), cv2.CV_32F, 0, 1))
    iod = float(np.linalg.norm(p[KHOE_NGOAI[0]] - p[KHOE_NGOAI[1]]))
    if iod < 8.0:
        return {}
    out = {}
    mx = {id(idx): p[list(idx), 0].mean() for idx in (MAT_TRAI, MAT_PHAI)}
    for idx in (MAT_TRAI, MAT_PHAI):
        pts = p[list(idx)]
        xa = "L" if mx[id(idx)] <= min(mx.values()) else "R"                    # mắt nằm bên trái ảnh hơn là 'L' (theo vị trí thật trong ảnh, không theo tên mắt của MediaPipe)
        m = np.zeros(g.shape, np.uint8)
        cv2.fillPoly(m, [pts.astype(np.int32)], 1)
        k, k2 = max(3, int(0.12 * iod)), max(3, int(0.30 * iod))
        ring = (cv2.dilate(m, np.ones((2 * k2 + 1, 2 * k2 + 1), np.uint8)) - cv2.dilate(m, np.ones((2 * k + 1, 2 * k + 1), np.uint8))).astype(bool)
        m = m.astype(bool)
        if m.sum() < 5 or ring.sum() < 5:
            continue
        out[xa] = (float(gm[m].mean() / iod * 100.0), float(g[m].mean() / (g[ring].mean() + 1e-6)),
                   float(np.percentile(g[m], 90) / (np.median(g[ring]) + 1e-6)))
    return out


def mat_bi_che(gray, pts478):
    """Các nửa ảnh ('L', 'R') có mắt bị vật thể che theo độ nét và độ sáng (xem đầu file)."""
    v = do_vung_mat(gray, pts478)
    kinh = {xa for xa, (gm, lum, sang) in v.items() if sang < SANG_KINH and lum < LUM_KINH}
    out = {xa for xa, (gm, lum, sang) in v.items() if gm < GM_PHANG} | kinh
    if kinh:                                                                  # kính râm che cả hai mắt: mắt kia đủ tối thì cũng bị che
        out |= {xa for xa, (gm, lum, sang) in v.items() if lum < LUM_KINH_CAP}
    return out


def diem_bi_che(pts478, cfg, gray=None):
    """Tên các điểm (trong 50 điểm của config) bị che, theo thứ tự trong config: (1) mặt nghiêng (tự che), (2) nếu có ảnh xám `gray` của ảnh cắt: mắt bị vật thể che.
    Mặt thẳng, mắt rõ hoặc không tính được thì []."""
    xa_mat = mat_bi_che(gray, pts478) if gray is not None else set()
    u = lech_mui(pts478)
    yaw, xa = (0.0, None) if u is None else (max(0.0, (abs(u) + _B) / _A), "L" if u < 0 else "R")
    out = []
    for p in cfg["points"]:
        reg, side = p.get("region"), p.get("side")
        if (side == xa and ((reg in VUNG_MAT and yaw >= YAW_MAT) or (reg in VUNG_MOI and yaw >= YAW_MOI))) or (reg == "eye" and side in xa_mat):
            out.append(p["name"])
    return out
