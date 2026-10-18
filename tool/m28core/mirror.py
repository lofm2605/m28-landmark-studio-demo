"""Hoán vị gương của 478 đỉnh MediaPipe, học từ dữ liệu thật (chỉ numpy; không cần đáp án).

Vì sao cần: MediaPipe Face Landmarker không công bố bảng "đỉnh i đối xứng với đỉnh j". Cặp `flip` của 50 điểm (R <-> L) và việc
bỏ lật ảnh (flipped=True trong apply_map) đều cần bảng này, và nó phải đúng cho cả 478 đỉnh. Có hai cách học, cả hai đều ra phép ĐỐI HỢP
(perm[perm[i]] == i; đỉnh nằm trên trục tự ghép với chính nó):

  A. learn_mirror_flip (cách chính): với mỗi mặt có cả ảnh gốc và ảnh lật ngang, đỉnh j của ảnh lật nằm ở vị trí gương của đỉnh perm[j]
     của ảnh gốc. Lấy chi phí C[j, k] = trung bình trên các mặt của |(w - x_lật(j), y_lật(j)) - gốc(k)| / IOD rồi ghép đối hợp từ cặp gần
     nhất (greedy), sau đó SỬA bằng đồ thị lưới tam giác của MediaPipe (hoán vị gương phải bảo toàn cạnh của lưới): tìm cục bộ hoán đổi cặp
     làm giảm (chi phí hình học + phạt mỗi cạnh bị vỡ). Cách này không bị lệch do hướng nhìn của mặt (mặt "thẳng" của YawDD vẫn
     nghiêng 20-30 độ vì camera đặt lệch) vì dùng chính hai bản dự đoán của cùng một mặt.
  B. learn_mirror (kiểm chéo): hình trung bình Procrustes của các mặt thẳng, lật gương rồi khớp lại và ghép gần nhất (ý ban đầu của kế hoạch).
     Chỉ tin được khi các mặt đều gần thẳng (|yaw| nhỏ): hình trung bình của mặt nghiêng không đối xứng nên ghép sai nhiều đỉnh.

Sai số ghép báo ra là khoảng cách (% IOD, IOD = hai khoé mắt ngoài 33 và 263) giữa vị trí gương và đỉnh được ghép, trung bình trên các mặt.
Đỉnh khó nhất là cụm khoé miệng (61, 78, 291, 308 ...) vì đỉnh môi ngoài và môi trong ở rất gần nhau: ghép đúng cần (i) ước lượng hằng số bỏ lật w
trên chính dữ liệu (MediaPipe lệch khỏi chiều rộng ảnh ~1,5 px; dùng w = 512 thì cụm này ghép sai) và (ii) bước sửa bằng lưới như chốt an toàn. Trên dữ liệu
thật của đội, sau khi ước lượng w, ghép gần nhất đã đúng và bước sửa bằng lưới không đổi gì; 6 cạnh lưới còn "vỡ" là do lưới MediaPipe không đối xứng hoàn toàn.
"""
import json
import time

import numpy as np

from m28core.mapping import similarity, to_mean

N_VERT = 478
IOD_VERTS = (33, 263)             # hai khoé mắt ngoài; ảnh không lật: 33 ở nửa TRÁI ảnh (= mattrai_1 của DMS), 263 ở nửa PHẢI ảnh (= matphai_1)
SURE_PAIRS = ((33, 263), (133, 362), (61, 291), (159, 386), (145, 374), (70, 300), (468, 473))
SURE_FIXED = (1, 2, 0, 13, 14, 17, 152, 168)


def mean_shape(shapes, rounds=3):
    """Hình trung bình của các (478, 2) sau khi khớp similarity về nhau (khớp lại về trung bình vài vòng)."""
    P = [np.asarray(s, float) for s in shapes]
    if not P:
        raise ValueError("không có mặt nào để lấy hình trung bình")
    ref = P[0]
    for _ in range(rounds):
        ref = np.mean([to_mean(p, *similarity(p, ref)) for p in P], axis=0)
        ref = ref - ref.mean(0)
        ref = ref / np.sqrt((ref ** 2).sum() / len(ref))          # chuẩn co giãn cho khỏi trôi qua các vòng
    return ref


def _reflect(M):
    return M * np.array([-1.0, 1.0])


def check_involution(perm):
    """Danh sách lỗi (rỗng = hợp lệ): hoán vị của 0..n-1 và perm[perm[i]] == i."""
    perm = [int(v) for v in perm]
    err = []
    n = len(perm)
    if sorted(perm) != list(range(n)):
        err.append("không phải hoán vị của 0..n-1")
        return err
    bad = [i for i in range(n) if perm[perm[i]] != i]
    if bad:
        err.append(f"không phải phép đối hợp (perm[perm[i]] != i) ở {bad[:8]}")
    return err


def _match_involution(Q, M):
    """Ghép đối hợp: Q[i] là vị trí gương của đỉnh i (đã khớp), M[j] là vị trí đỉnh j. Cặp có chi phí thấp nhất ghép trước."""
    D = np.linalg.norm(Q[:, None, :] - M[None, :, :], axis=2)
    S = 0.5 * (D + D.T)
    np.fill_diagonal(S, np.diag(D))
    return _match_involution_cost(S)


def _match_involution_cost(S):
    """S: chi phí đối xứng (n, n); S[i, i] là chi phí để đỉnh i nằm trên trục. Ghép từ cặp rẻ nhất, hai đỉnh chưa có cặp thì ghép lẫn nhau."""
    n = len(S)
    iu, ju = np.triu_indices(n)
    order = np.argsort(S[iu, ju], kind="stable")
    perm = -np.ones(n, int)
    left = n
    for k in order:
        i, j = iu[k], ju[k]
        if perm[i] >= 0 or perm[j] >= 0:
            continue
        perm[i], perm[j] = j, i
        left -= 1 if i == j else 2
        if left == 0:
            break
    return perm


def _init_axis(M):
    """Ước lượng ban đầu của phép gương: thử nhiều trục đối xứng (góc, độ dời) và chọn trục cho hình lật trùng hình gốc nhất
    (khoảng cách gần nhất trung bình). Trả similarity T (co giãn 1) sao cho T(lật x của M) ~ M."""
    F = np.diag([-1.0, 1.0])
    best = None
    for deg in np.arange(-60, 60.1, 2.0):
        u = np.array([np.sin(np.deg2rad(deg)), np.cos(np.deg2rad(deg))])       # hướng trục (0 độ = thẳng đứng)
        n = np.array([u[1], -u[0]])
        A = 2 * np.outer(u, u) - np.eye(2)
        for d in np.linspace(-0.4, 0.4, 17):
            p = d * n
            b = 2 * (np.eye(2) - np.outer(u, u)) @ p
            Q = M @ A.T + b
            sc = np.linalg.norm(Q[::2, None, :] - M[None, :, :], axis=2).min(1).mean()
            if best is None or sc < best[0]:
                best = (sc, A, b)
    _, A, b = best
    return (1.0, A @ F, b)


def _icp(M, Mf, T, rounds=25):
    """Tinh chỉnh T bằng ghép gần nhất rồi khớp similarity (chưa cần hoán vị)."""
    for _ in range(rounds):
        Q = to_mean(Mf, *T)
        nn = np.argmin(np.linalg.norm(Q[:, None, :] - M[None, :, :], axis=2), axis=1)
        T = similarity(Mf, M[nn])
    return T


def _fit_to(M, Mf, perm):
    """Similarity T sao cho T(Mf[i]) gần M[perm[i]]."""
    return similarity(Mf, M[perm])


def learn_mirror(shapes, outer=6, inner=30, log=None):
    """Trả dict(perm, fixed, meta, resid) từ danh sách các (478, 2). resid: (478,) sai số ghép trên hình trung bình gốc, % IOD."""
    log = log or (lambda *_: None)
    M0 = mean_shape(shapes)
    M0 = M0 - M0.mean(0)
    iod = float(np.linalg.norm(M0[IOD_VERTS[0]] - M0[IOD_VERTS[1]]))
    M = M0.copy()
    perm = None
    for it in range(outer):
        Mf = _reflect(M)
        T = _icp(M, Mf, _init_axis(M)) if perm is None else _fit_to(M, Mf, perm)
        new = None
        for _ in range(inner):
            Q = to_mean(Mf, *T)
            new = _match_involution(Q, M)
            if perm is not None and np.array_equal(new, perm):
                break
            perm = new
            T = _fit_to(M, Mf, perm)
        perm = new
        # đối xứng hoá hình trung bình theo hoán vị hiện tại
        T = _fit_to(M, Mf, perm)
        back = to_mean(Mf, *T)                 # vị trí gương của đỉnh i, dự đoán cho đỉnh perm[i]
        M_new = M.copy()
        M_new[perm] = 0.5 * (M[perm] + back)
        change = float(np.linalg.norm(M_new - M, axis=1).max() / iod * 100)
        log(f"vòng {it + 1}: đối xứng hoá làm hình trung bình dịch tối đa {change:.2f}% IOD")
        M = M_new
        if change < 0.05:
            break
    errs = check_involution(perm)
    if errs:
        raise ValueError("hoán vị học được không hợp lệ: " + "; ".join(errs))
    Mf0 = _reflect(M0)
    T0 = _fit_to(M0, Mf0, perm)
    resid = np.linalg.norm(to_mean(Mf0, *T0) - M0[perm], axis=1) / iod * 100
    fixed = [int(i) for i in range(N_VERT) if perm[i] == i]
    meta = dict(n_faces=len(shapes), date=time.strftime("%Y-%m-%d"),
                resid_median_pct_iod=round(float(np.median(resid)), 3), resid_max_pct_iod=round(float(resid.max()), 3),
                resid_p95_pct_iod=round(float(np.percentile(resid, 95)), 3),
                n_fixed=len(fixed), method="mean shape Procrustes + gương + ghép đối hợp, lặp")
    return dict(perm=[int(v) for v in perm], fixed=fixed, meta=meta, resid=resid)


def tessellation_edges():
    """Cạnh của lưới tam giác MediaPipe (mảng (m, 2), mỗi cạnh một lần). Cần mediapipe (đã có sẵn khi chạy pipeline)."""
    from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarksConnections as C
    return np.array(sorted({tuple(sorted((c.start, c.end))) for c in C.FACE_LANDMARKS_TESSELATION}), int)


def violations(perm, edges):
    """Số cạnh của lưới bị vỡ bởi hoán vị (cạnh (a, b) mà (perm[a], perm[b]) không phải cạnh)."""
    perm = np.asarray(perm, int)
    adj = np.zeros((N_VERT, N_VERT), bool)
    adj[edges[:, 0], edges[:, 1]] = adj[edges[:, 1], edges[:, 0]] = True
    return int((~adj[perm[edges[:, 0]], perm[edges[:, 1]]]).sum())


def _swap_partners(p, i, j):
    """Ghép lại i <-> j (nếu chưa), giữ phép đối hợp: hai đối tác cũ ghép với nhau (hoặc tự cố định)."""
    q = p.copy()
    if i == j or p[i] == j:
        return q
    pi, pj = p[i], p[j]
    q[i], q[j] = j, i
    if pi == i and pj == j:
        return q
    if pi == i:
        q[pj] = pj
    elif pj == j:
        q[pi] = pi
    else:
        q[pi], q[pj] = pj, pi
    return q


def refine_with_mesh(perm, S, edges, mu=0.03, k=8, sweeps=20):
    """Giảm dần J = tổng chi phí hình học + mu * số cạnh bị vỡ bằng cách đổi cặp cục bộ; trả perm mới (vẫn là phép đối hợp)."""
    perm = np.asarray(perm, int).copy()
    adj = np.zeros((N_VERT, N_VERT), bool)
    adj[edges[:, 0], edges[:, 1]] = adj[edges[:, 1], edges[:, 0]] = True

    def total(p):
        return S[np.arange(N_VERT), p].sum() / 2 + mu * (~adj[p[edges[:, 0]], p[edges[:, 1]]]).sum()

    best = total(perm)
    cand = np.argsort(S, axis=1)[:, :k]
    for _ in range(sweeps):
        improved = False
        for i in range(N_VERT):
            for j in cand[i]:
                j = int(j)
                if j == perm[i]:
                    continue
                q = _swap_partners(perm, i, j)
                t = total(q)
                if t < best - 1e-12:
                    perm, best, improved = q, t, True
        if not improved:
            break
    return perm


def _flip_cost(origs, flips, width):
    """C[j, k] = trung bình trên các mặt của |(width - x_lật(j), y_lật(j)) - gốc(k)| / IOD."""
    C = np.zeros((N_VERT, N_VERT))
    for o, f in zip(origs, flips):
        iod = float(np.linalg.norm(o[IOD_VERTS[0]] - o[IOD_VERTS[1]])) or 1.0
        Q = np.stack([width - f[:, 0], f[:, 1]], axis=1)
        C += np.linalg.norm(Q[:, None, :] - o[None, :, :], axis=2) / iod
    return C / len(origs)


def _symmetric(C):
    S = 0.5 * (C + C.T)
    np.fill_diagonal(S, np.diag(C))
    return S


def learn_mirror_flip(origs, flips, width=512.0, edges=None, log=None):
    """Cách A (xem docstring module). origs, flips: danh sách các (478, 2) của CÙNG mặt (ảnh gốc và ảnh lật ngang, cùng khung).
    `width` là điểm xuất phát của hằng số bỏ lật; sau lần ghép đầu hàm ước lượng lại w = trung bình của x_gốc(i) + x_lật(perm[i]) rồi ghép lại
    (MediaPipe thường lệch khỏi chiều rộng ảnh vài pixel, xem flip_width ở make_config.py). edges=None: không sửa bằng lưới.
    Trả dict(perm, fixed, meta, resid, width)."""
    log = log or (lambda *_: None)
    if len(origs) != len(flips) or not origs:
        raise ValueError("cần danh sách ảnh gốc và ảnh lật cùng độ dài, không rỗng")
    origs = [np.asarray(o, float) for o in origs]
    flips = [np.asarray(f, float) for f in flips]
    perm = _match_involution_cost(_symmetric(_flip_cost(origs, flips, width)))
    w = float(np.mean([np.mean(o[:, 0] + f[perm, 0]) for o, f in zip(origs, flips)]))
    log(f"w ước lượng sau lần ghép đầu: {w:.3f} (xuất phát {width:g})")
    C = _flip_cost(origs, flips, w)
    S = _symmetric(C)
    perm = _match_involution_cost(S)
    v0 = violations(perm, edges) if edges is not None else None
    if edges is not None:
        perm = refine_with_mesh(perm, S, edges)
    errs = check_involution(perm)
    if errs:
        raise ValueError("hoán vị học được không hợp lệ: " + "; ".join(errs))
    resid = np.array([C[i, perm[i]] for i in range(N_VERT)]) * 100
    fixed = [int(i) for i in range(N_VERT) if perm[i] == i]
    meta = dict(n_faces=len(origs), date=time.strftime("%Y-%m-%d"), method="flip-pair cost + greedy involution + mesh refinement",
                width_used=round(w, 4), resid_median_pct_iod=round(float(np.median(resid)), 3), resid_max_pct_iod=round(float(resid.max()), 3),
                resid_p95_pct_iod=round(float(np.percentile(resid, 95)), 3), n_fixed=len(fixed))
    if edges is not None:
        meta["mesh_edges"] = int(len(edges))
        meta["mesh_violations_before_refine"] = v0
        meta["mesh_violations_after_refine"] = violations(perm, edges)
    return dict(perm=[int(v) for v in perm], fixed=fixed, meta=meta, resid=resid, width=w)


def agreement(perm_a, perm_b):
    """Số đỉnh hai hoán vị ghép khác nhau và danh sách (tối đa 20) đỉnh đó."""
    a, b = np.asarray(perm_a), np.asarray(perm_b)
    diff = [int(i) for i in np.nonzero(a != b)[0]]
    return len(diff), diff[:20]


def check_against_data(perm, origs, flips, edges=None, width=512.0):
    """Kiểm một hoán vị CÓ SẴN (config/mp_mirror478.json) trên dữ liệu thật mà KHÔNG ghi gì: học lại trong bộ nhớ bằng learn_mirror_flip rồi so.
    Trả dict(n_faces, n_diff, diff (tối đa 20 đỉnh), resid_median_pct_iod, resid_max_pct_iod của CHÍNH hoán vị có sẵn, n_fixed_learned).
    Hoán vị gương là tính chất hình học của 478 đỉnh, không phụ thuộc tên điểm, nên đổi định nghĩa 50 điểm không đòi học lại; hàm này là bằng chứng cho điều đó."""
    perm = np.asarray(perm, int)
    new = learn_mirror_flip(origs, flips, width, edges)
    n_diff, diff = agreement(perm, new["perm"])
    C = _flip_cost([np.asarray(o, float) for o in origs], [np.asarray(f, float) for f in flips], new["width"])
    resid = np.array([C[i, perm[i]] for i in range(N_VERT)]) * 100
    return dict(n_faces=len(origs), n_diff=n_diff, diff=diff, resid_median_pct_iod=float(np.median(resid)), resid_max_pct_iod=float(resid.max()),
                n_fixed_learned=len(new["fixed"]))


def suspicious(resid, perm, k=12):
    """[(đỉnh, cặp, sai số % IOD)] của k đỉnh có sai số ghép lớn nhất (để người xem lại bằng mắt)."""
    order = np.argsort(-np.asarray(resid))[:k]
    return [(int(i), int(perm[i]), round(float(resid[i]), 2)) for i in order]


def sanity(perm):
    """Kiểm cứng bằng cặp chắc chắn đúng; trả danh sách lỗi (rỗng = đạt)."""
    err = check_involution(perm)
    if err:
        return err
    for a, b in SURE_PAIRS:
        if perm[a] != b:
            err.append(f"đỉnh {a} phải ghép với {b}, đang là {perm[a]}")
    for a in SURE_FIXED:
        if perm[a] != a:
            err.append(f"đỉnh {a} phải nằm trên trục (cố định), đang ghép với {perm[a]}")
    for a in range(469, 473):
        if not 474 <= perm[a] <= 477:
            err.append(f"đỉnh iris {a} phải ghép với một đỉnh trong 474-477, đang là {perm[a]}")
    return err


def save_mirror(path, result):
    obj = {"perm": result["perm"], "fixed": result["fixed"], "meta": result["meta"]}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False)
        f.write("\n")


def load_mirror(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    perm = obj.get("perm")
    if not isinstance(perm, list) or len(perm) != N_VERT:
        raise ValueError(f"{path}: 'perm' phải có {N_VERT} số")
    errs = check_involution(perm)
    if errs:
        raise ValueError(f"{path}: " + "; ".join(errs))
    return obj
