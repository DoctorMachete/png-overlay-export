"""Legend 3D in numpy: CapWarpText + CapComposeWarp of the .147 script.
Each key's 12 x 12 grid (13 x 13 nodes, two triangles per cell) maps the flat
text page onto the bent one, inside the key's (rotated) box; outside the keys
the text page stays as it is.  Instead of ~17 000 GDI+ triangle draws, every
pixel's source point is computed (barycentric, per triangle) into one map and
the page is resampled once (bilinear, premultiplied alpha)."""
import numpy as np, cv2

GRP_W, GRP_H, FRAME_PAD, N = 444.0, 177.7714699700121, 8.0, 12

def warp_map(w, h, keys, k):
    kx, ky = w / (GRP_W + 2 * FRAME_PAD), h / (GRP_H + 2 * FRAME_PAD)
    mx, my = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    uv = (-1 + 2 * np.arange(N + 1) / N)
    for key in keys:
        g = key.get('grid')
        if not g:
            continue
        g = np.asarray(g, dtype=np.float64).reshape(N + 1, N + 1, 2)
        hw, hh = key['w'] * kx / 2, key['h'] * ky / 2
        cx, cy = (key['x'] + FRAME_PAD) * kx + hw, (key['y'] + FRAME_PAD) * ky + hh
        a = np.radians(key['rot']); ca, sa = np.cos(a), np.sin(a)
        # the key's pixels: inside its turned box
        r = abs(hw * ca) + abs(hh * sa), abs(hw * sa) + abs(hh * ca)
        x0, x1 = max(0, int(cx - r[0]) - 1), min(w, int(cx + r[0]) + 2)
        y0, y1 = max(0, int(cy - r[1]) - 1), min(h, int(cy + r[1]) + 2)
        px, py = np.meshgrid(np.arange(x0, x1) + 0.0, np.arange(y0, y1) + 0.0)
        dx, dy = px - cx, py - cy
        U = (dx * ca + dy * sa) / hw          # the pixel in the key's own -1..1 units
        V = (-dx * sa + dy * ca) / hh
        inside = (np.abs(U) <= 1) & (np.abs(V) <= 1)
        SU = np.full(U.shape, np.nan); SV = np.full(U.shape, np.nan)
        du, dv = uv[None, :] + g[..., 0] * k, uv[:, None] + g[..., 1] * k   # where each node is drawn
        su, sv = np.broadcast_to(uv[None, :], du.shape), np.broadcast_to(uv[:, None], dv.shape)
        for i in range(N):
            for j in range(N):
                for t in (((i, j), (i, j + 1), (i + 1, j)), ((i, j + 1), (i + 1, j + 1), (i + 1, j))):
                    (a0, b0), (a1, b1), (a2, b2) = t
                    X = np.array([du[a0, b0], du[a1, b1], du[a2, b2]]); Y = np.array([dv[a0, b0], dv[a1, b1], dv[a2, b2]])
                    m = inside & (U >= X.min() - 1e-9) & (U <= X.max() + 1e-9) & (V >= Y.min() - 1e-9) & (V <= Y.max() + 1e-9)
                    if not m.any():
                        continue
                    det = (Y[1] - Y[2]) * (X[0] - X[2]) + (X[2] - X[1]) * (Y[0] - Y[2])
                    if abs(det) < 1e-12:
                        continue
                    uu, vv = U[m], V[m]
                    l0 = ((Y[1] - Y[2]) * (uu - X[2]) + (X[2] - X[1]) * (vv - Y[2])) / det
                    l1 = ((Y[2] - Y[0]) * (uu - X[2]) + (X[0] - X[2]) * (vv - Y[2])) / det
                    l2 = 1 - l0 - l1
                    hit = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9)
                    if not hit.any():
                        continue
                    idx = np.flatnonzero(m)[hit]
                    SU.flat[idx] = l0[hit] * su[a0, b0] + l1[hit] * su[a1, b1] + l2[hit] * su[a2, b2]
                    SV.flat[idx] = l0[hit] * sv[a0, b0] + l1[hit] * sv[a1, b1] + l2[hit] * sv[a2, b2]
        ok = inside & np.isfinite(SU)
        sx = cx + SU * hw * ca - SV * hh * sa
        sy = cy + SU * hw * sa + SV * hh * ca
        sub_x, sub_y = mx[y0:y1, x0:x1], my[y0:y1, x0:x1]
        sub_x[ok] = sx[ok]; sub_y[ok] = sy[ok]
        # a pixel of the box no triangle covers: cleared, as the script's clip leaves it
        gone = inside & ~np.isfinite(SU)
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
    return unpremul(over(premul(r), over(tb, premul(c)))), tb
