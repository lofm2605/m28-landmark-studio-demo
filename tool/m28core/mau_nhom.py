"""Màu theo nhóm của 50 điểm DMS và kiểu chấm trên ảnh chồng (overlays): MỘT nguồn cho make_label (màu label CVAT), steps.overlays (cv2) và trang rà soát (PIL),
để màu trên trang giống màu trong CVAT (QĐ-004). Chỉ thư viện chuẩn.

Chấm ổn: một chấm màu nhóm, viền tối mảnh cho dễ thấy trên mọi nền. Chấm low_conf (nhìn kỹ): CÙNG CỠ chấm ổn như trên CVAT (CVAT không đổi cỡ điểm),
chỉ khác viền TRẮNG thay cho viền tối, nên vẫn nhận ra điểm đáng ngờ mà không che mép mắt, môi. Điểm có tên không thuộc nhóm nào (lượt cũ tên `pNN_…`) vẽ kiểu cũ: đỏ = low_conf, xanh = ổn.
"""
GROUP_COLOR = {"longmaytrai": "#e74c3c", "longmayphai": "#3498db", "songmui": "#2ecc71", "mattrai": "#e67e22", "matphai": "#9b59b6",
               "moingoai": "#1abc9c", "moitrong": "#f1c40f"}
# tên tiếng Việt cho chú giải; trái/phải là của ẢNH (QĐ-003), không phải của người
GROUP_VI = {"longmaytrai": "lông mày trái", "longmayphai": "lông mày phải", "songmui": "sống mũi", "mattrai": "mắt trái", "matphai": "mắt phải",
            "moingoai": "môi ngoài", "moitrong": "môi trong"}
FALLBACK_OK, FALLBACK_LOW = (0, 200, 0), (255, 0, 0)       # RGB, kiểu cũ cho điểm không có nhóm
DARK, WHITE = (20, 20, 20), (255, 255, 255)
R_OK = 3                                                    # bán kính chấm ổn (px trên ảnh cắt 512)
R_LOW = R_OK                                                # bán kính chấm màu của điểm low_conf: bằng chấm ổn
RING_LOW = 1                                                # bề dày viền trắng quanh chấm low_conf (thay cho viền tối của chấm ổn)
R_OCC = 5                                                   # bán kính vòng RỖNG của điểm bị che (occluded): vòng màu nhóm, không tô đặc, viền tối ngoài


def group_of(point_name):
    """Nhóm của điểm `<nhóm>_<k>`; không thuộc nhóm nào thì None."""
    g = str(point_name).rsplit("_", 1)[0]
    return g if g in GROUP_COLOR else None


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def dot_rgb(group, low_conf):
    """Màu RGB của chấm: màu nhóm; không có nhóm thì đỏ (low_conf) / xanh (ổn) như bản cũ."""
    if group in GROUP_COLOR:
        return hex_rgb(GROUP_COLOR[group])
    return FALLBACK_LOW if low_conf else FALLBACK_OK


def all_grouped(names):
    """True khi MỌI tên điểm thuộc một nhóm đã biết (lượt dùng tên v3)."""
    names = list(names)
    return bool(names) and all(group_of(n) for n in names)
