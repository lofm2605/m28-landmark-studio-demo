"""Cờ low_conf (QĐ-025): MỘT chỗ tính cờ cho bước flags, bảng độ tin cậy ở trang rà soát và đo cờ.

Phiên bản 2 (khoá `low_conf_v2` trong config/m28_config.json): hồi quy logistic trên ba đặc trưng của từng điểm, đều lấy từ map50/mp50.json
(ảnh gốc và ảnh lật đã bỏ lật), không chạy thêm model:
  - log điểm số lật của điểm  = khoảng cách gốc–lật ÷ khoảng cách hai khoé mắt ngoài (như phiên bản 1),
  - log trung bình và log phân vị 0,9 điểm số lật của CẢ mặt (mặt khó thì mọi điểm đáng ngờ hơn),
  - nhóm điểm (7 nhóm DMS, one-hot).
Cờ bật khi xác suất > `threshold`. Hệ số học trên nửa dev của 210 mặt có nhãn gán tay (thí nghiệm 14–15/10), ngưỡng chọn trên dev
(tool/do_co_thi_nghiem.py --hoc-v2). Không có khoá đó thì dùng phiên bản 1: điểm số lật > t_flip (t_flip null: không cờ).
Mặt không có ảnh lật: mọi điểm có cờ (như trước)."""
import math

import numpy as np

KEY = "low_conf_v2"
EPS = 1e-4


def model_of(cfg):
    m = cfg.get(KEY) if isinstance(cfg, dict) else None
    return m if isinstance(m, dict) and m.get("w") and m.get("threshold") is not None else None


def flip_scores(face, cfg):
    """Điểm số lật của các điểm theo thứ tự config (np.array) hoặc None khi mặt không có ảnh lật / thiếu điểm."""
    names = [p["name"] for p in cfg["points"]]
    orig, flip = (face or {}).get("orig") or {}, (face or {}).get("flip") or {}
    if not flip or any(n not in orig or n not in flip for n in names):
        return None
    a, b = cfg["iod_points"][:2]
    iod = math.dist(orig[a], orig[b]) or 1.0
    return np.array([math.dist(orig[n], flip[n]) / iod for n in names], float)


def features(scores, cfg, groups):
    """Ma trận đặc trưng (số điểm × số đặc trưng) của một mặt từ điểm số lật của nó."""
    s = np.asarray(scores, float)
    grp = [p.get("group", p.get("region")) for p in cfg["points"]]
    onehot = np.array([[g == k for k in groups] for g in grp], float)
    fm, fq = float(s.mean()), float(np.quantile(s, 0.9))
    return np.c_[np.log(s + EPS), np.full(len(s), math.log(fm + EPS)), np.full(len(s), math.log(fq + EPS)), onehot]


def probs(face, cfg):
    """Xác suất điểm sai của từng điểm (phiên bản 2) hoặc None (không có mô hình, hoặc mặt không có ảnh lật)."""
    m = model_of(cfg)
    s = flip_scores(face, cfg)
    if m is None or s is None:
        return None
    X = features(s, cfg, m["groups"])
    z = m["b"] + ((X - np.array(m["mu"])) / np.array(m["sd"])) @ np.array(m["w"])
    return 1.0 / (1.0 + np.exp(-z))


def flags(face, cfg):
    """[bool] cờ low_conf của các điểm theo thứ tự config."""
    n = len(cfg["points"])
    m = model_of(cfg)
    if m is not None:
        p = probs(face, cfg)
        return [True] * n if p is None else [bool(v > float(m["threshold"])) for v in p]
    t = cfg.get("t_flip")
    if t is None:
        return [False] * n
    s = flip_scores(face, cfg)
    return [True] * n if s is None else [bool(v > float(t)) for v in s]


def face_suggestion(n_flags, cfg):
    """Gợi ý theo cả mặt từ số cờ phiên bản 2: "on" (Ổn), "can_xem", "nen_gan_tay"; None khi không có mô hình (giữ luật cũ của autoqc)."""
    m = model_of(cfg)
    if m is None or m.get("mat_on_max") is None:
        return None
    if n_flags >= int(m.get("mat_sua_min", 51)):
        return "nen_gan_tay"
    return "on" if n_flags <= int(m["mat_on_max"]) else "can_xem"


def confidence(p, threshold):
    """Độ tin cậy 0–1 hiện ở bảng: dưới 0,50 đúng là có cờ (xác suất > ngưỡng)."""
    return max(0.0, min(1.0, 1.0 - float(p) / (2.0 * float(threshold))))
