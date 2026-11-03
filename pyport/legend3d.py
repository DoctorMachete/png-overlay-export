"""Legend 3D in numpy: CapWarpText + CapComposeWarp of the .147 script.
Each key's 12 x 12 grid (13 x 13 nodes, two triangles per cell) maps the flat
text page onto the bent one, inside the key's (rotated) box; outside the keys
the text page stays as it is.  Instead of ~17 000 GDI+ triangle draws, every
pixel's source point is computed (barycentric, per triangle) into one map and
the page is resampled once (bilinear, premultiplied alpha)."""
import numpy as np, cv2

GRP_W, GRP_H, FRAME_PAD, N = 444.0, 177.7714699700121, 8.0, 12

def _bary(u, v, X, Y, d):
    l0 = ((Y[..., 1] - Y[..., 2]) * (u - X[..., 2]) + (X[..., 2] - X[..., 1]) * (v - Y[..., 2])) / d
    l1 = ((Y[..., 2] - Y[..., 0]) * (u - X[..., 2]) + (X[..., 0] - X[..., 2]) * (v - Y[..., 2])) / d
    return l0, l1, 1 - l0 - l1


def _exact(fix, U, V, X, Y, det, valid, lab, SU, SV, SU_T, SV_T):
    """The exact triangle (the last one drawn that contains it) for the pixels fix (flat indices)
    the label painting got wrong or left out: tried first among the labels of each pixel's
    3 x 3 neighbourhood, then, for the few still without one, among all triangles."""
    H, W = lab.shape
    yy, xx = np.divmod(fix, W)
    pad = np.pad(lab, 1)
    cand = np.stack([pad[yy + 1 + oy, xx + 1 + ox] for oy in (-1, 0, 1) for ox in (-1, 0, 1)], 1) - 1  # m x 9
    u, v = U.flat[fix][:, None], V.flat[fix][:, None]
    c = np.maximum(cand, 0)
    ok_c = (cand >= 0) & valid[c]
    d = np.where(ok_c, det[c], 1.0)
    l0, l1, l2 = _bary(u, v, X[c], Y[c], d)
    hit = ok_c & (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9)
    best = np.where(hit, cand, -1).max(1)                       # the last drawn among the hits
    got = best >= 0
    if (~got).any():                                            # rare: test every triangle
        rest = np.flatnonzero(~got)
        ur, vr = u[rest], v[rest]
        dd = np.where(valid, det, 1.0)[None, :]
        m0, m1, m2 = _bary(ur, vr, X[None], Y[None], dd)
        h2 = (m0 >= -1e-9) & (m1 >= -1e-9) & (m2 >= -1e-9) & valid[None, :]
        anyh = h2.any(1)
        best[rest[anyh]] = h2.shape[1] - 1 - np.argmax(h2[anyh][:, ::-1], 1)
        got = best >= 0
    if not got.any():
        return
    t = best[got]
    b0, b1, b2 = _bary(u[got, 0], v[got, 0], X[t], Y[t], det[t])
    SU.flat[fix[got]] = b0 * SU_T[t, 0] + b1 * SU_T[t, 1] + b2 * SU_T[t, 2]
    SV.flat[fix[got]] = b0 * SV_T[t, 0] + b1 * SV_T[t, 1] + b2 * SV_T[t, 2]


def warp_map(w, h, keys, k):
    """The remap of the whole page: for every pixel of every key, its source point.  Each key's 288
    bent triangles are painted into a label image (cv2.fillConvexPoly, later triangles over
    earlier ones, as the script's clear-then-draw), then every labelled pixel's barycentric
    coordinates in its triangle are computed at once."""
    kx, ky = w / (GRP_W + 2 * FRAME_PAD), h / (GRP_H + 2 * FRAME_PAD)
    mx, my = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    uv = (-1 + 2 * np.arange(N + 1) / N)
    # the 2 * N * N triangles as node indices (row, col), in the order they are drawn
    tri = []
    for i in range(N):
        for j in range(N):
            tri.append(((i, j), (i, j + 1), (i + 1, j)))
            tri.append(((i, j + 1), (i + 1, j + 1), (i + 1, j)))
    ti = np.array([[a[0] for a in t] for t in tri]); tj = np.array([[a[1] for a in t] for t in tri])
    su_n = np.broadcast_to(uv[None, :], (N + 1, N + 1)); sv_n = np.broadcast_to(uv[:, None], (N + 1, N + 1))
    SU_T, SV_T = su_n[ti, tj], sv_n[ti, tj]                    # source (flat) corners, n x 3
    for key in keys:
        g = key.get('grid')
        if not g:
            continue
        g = np.asarray(g, dtype=np.float64).reshape(N + 1, N + 1, 2)
        hw, hh = key['w'] * kx / 2, key['h'] * ky / 2
        cx, cy = (key['x'] + FRAME_PAD) * kx + hw, (key['y'] + FRAME_PAD) * ky + hh
        a = np.radians(key['rot']); ca, sa = np.cos(a), np.sin(a)
        r = abs(hw * ca) + abs(hh * sa), abs(hw * sa) + abs(hh * ca)
        x0, x1 = max(0, int(cx - r[0]) - 1), min(w, int(cx + r[0]) + 2)
        y0, y1 = max(0, int(cy - r[1]) - 1), min(h, int(cy + r[1]) + 2)
        if x0 >= x1 or y0 >= y1:
            continue
        px, py = np.meshgrid(np.arange(x0, x1) + 0.0, np.arange(y0, y1) + 0.0)
        dx, dy = px - cx, py - cy
        U = (dx * ca + dy * sa) / hw
        V = (-dx * sa + dy * ca) / hh
        inside = (np.abs(U) <= 1) & (np.abs(V) <= 1)
        du = uv[None, :] + g[..., 0] * k; dv = uv[:, None] + g[..., 1] * k     # drawn node positions
        X, Y = du[ti, tj], dv[ti, tj]                                          # n x 3, key units
        # the drawn triangles in this box's pixels (pixel index = coordinate, as U/V above)
        PX = cx + X * hw * ca - Y * hh * sa - x0
        PY = cy + X * hw * sa + Y * hh * ca - y0
        lab = np.zeros(U.shape, np.int32)
        pts = np.round(np.stack([PX, PY], -1) * 16).astype(np.int32)
        for n in range(len(tri)):
            cv2.fillConvexPoly(lab, pts[n], n + 1, lineType=cv2.LINE_8, shift=4)
        # barycentric coordinates of each labelled pixel in its own triangle
        det = (Y[:, 1] - Y[:, 2]) * (X[:, 0] - X[:, 2]) + (X[:, 2] - X[:, 1]) * (Y[:, 0] - Y[:, 2])
        valid = np.abs(det) >= 1e-12
        sel = (lab > 0) & inside
        n_ = lab[sel] - 1
        keep = valid[n_]
        n_ = n_[keep]
        uu, vv = U[sel][keep], V[sel][keep]
        Xn, Yn, dn = X[n_], Y[n_], det[n_]
        l0 = ((Yn[:, 1] - Yn[:, 2]) * (uu - Xn[:, 2]) + (Xn[:, 2] - Xn[:, 1]) * (vv - Yn[:, 2])) / dn
        l1 = ((Yn[:, 2] - Yn[:, 0]) * (uu - Xn[:, 2]) + (Xn[:, 0] - Xn[:, 2]) * (vv - Yn[:, 2])) / dn
        l2 = 1 - l0 - l1
        SU = np.full(U.shape, np.nan); SV = np.full(U.shape, np.nan)
        idx = np.flatnonzero(sel)[keep]
        good = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9)
        SU.flat[idx[good]] = (l0 * SU_T[n_, 0] + l1 * SU_T[n_, 1] + l2 * SU_T[n_, 2])[good]
        SV.flat[idx[good]] = (l0 * SV_T[n_, 0] + l1 * SV_T[n_, 1] + l2 * SV_T[n_, 2])[good]
        # the painting is only a fast guess near edges (it takes pixels up to half a pixel past
        # an edge, or misses some): the pixels it got wrong or left out, tested exactly against
        # every triangle, the last one drawn winning
        fix = np.flatnonzero(inside & ~np.isfinite(SU))
        if fix.size:
            _exact(fix, U, V, X, Y, det, valid, lab, SU, SV, SU_T, SV_T)
        ok = inside & np.isfinite(SU)
        sx = cx + SU * hw * ca - SV * hh * sa
        sy = cy + SU * hw * sa + SV * hh * ca
        sub_x, sub_y = mx[y0:y1, x0:x1], my[y0:y1, x0:x1]
        sub_x[ok] = sx[ok]; sub_y[ok] = sy[ok]
        gone = inside & ~np.isfinite(SU)          # in the box, under no triangle: cleared
        sub_x[gone] = -10; sub_y[gone] = -10
    return mx, my

def premul(rgba):
    f = rgba.astype(np.float32) / 255
    f[..., :3] *= f[..., 3:4]
    return f

def unpremul(f):
    out = f.copy(); a = out[..., 3:4]
    out[..., :3] = np.where(a > 1e-6, out[..., :3] / np.maximum(a, 1e-6), 0)
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)

GAMMA = 2.2      # GDI+ (CompositingQualityHighQuality) blends in linear light

def over(top, base, gamma=None):
    """Premultiplied source-over, colours blended in linear light as GDI+ does."""
    g = GAMMA if gamma is None else gamma
    if g == 1:
        return top + base * (1 - top[..., 3:4])
    ta, da = top[..., 3:4], base[..., 3:4]
    tc = np.where(ta > 0, top[..., :3] / np.maximum(ta, 1e-6), 0) ** g
    dc = np.where(da > 0, base[..., :3] / np.maximum(da, 1e-6), 0) ** g
    oa = ta + da * (1 - ta)
    oc = np.where(oa > 0, (tc * ta + dc * da * (1 - ta)) / np.maximum(oa, 1e-6), 0) ** (1 / g)
    return np.concatenate([oc * oa, oa], -1)

def compose_warp(c, t, r, keys, k):
    """bg = caps, then the text bent, then the rims (CapComposeWarp)."""
    h, w = t.shape[:2]
    mx, my = warp_map(w, h, keys, k)
    tb = cv2.remap(premul(t), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    # caps, then the bent text, then the rims: render_shade.blend = over(), on only the pixels
    # that need the linear-light maths (same result, much faster than two whole-page blends)
    from render_shade import blend
    out = premul(c)
    blend(out, tb)
    blend(out, premul(r))
    return unpremul(out), tb
