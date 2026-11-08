"""Render keycap models (.capmodel) from an STL file (.178): the generators of the
model set (render/models.py, gen_capmodels.py, gen_tilt_all.py, gen_ldsa_dish_tilt.py's
build_ls, grid_tilt.py, gen_flat_tops.py) in one module, so the exe makes them:

    png-overlay-export capmodel --stl cap.stl --out capmodels --key mycap --name "My cap"
        [--tilts 0,7,15,22.5,30] [--steep 1,1.5,2,3] [--tops dish,flat,wflat,xwflat]
        [--long] [--turn] [--turn90] [--sloped] [--progress f] [--result f]

Per tilt (degrees front to back; the low side at the bottom, or for a model sloped as
modelled, --sloped, on top of its own slope): the height map at 40 px/mm, the top face,
the normal map (tilted or sloped faces lit levelled, smoothing 12; regular / steeper), the
outlines, and the Legend 3D grids (warp= at the face's real slope with the dish's curve
3x, warpt= the tilt-only twin).  Flat tops (level, widened 20 % / 40 %) at 0 degrees only.
A file per tilt x lighting x top: <key>[_t<deg>][_flat|_wflat|_xwflat][_sNN].capmodel."""
import base64, io, json, math, os, re, struct, sys
import numpy as np
from scipy import ndimage as nd
from scipy.interpolate import griddata
from scipy.spatial import ConvexHull, Delaunay
from PIL import Image

PPM = 40.0
SLOPE = 0.30
BEND = 0.75                       # .161: face edge = steeper than SLOPE and bending down by BEND per mm
N_GRID, K_GRID = 12, 3.0          # Legend 3D: 13 x 13 nodes, the dish's curve at 3x
LEVEL_T, SMOOTH_T = 1.0, 12.0     # tilted / sloped faces: lit levelled, smoothed wider
DEG = chr(0xB0)


# ------------------------------------------------------------------ the mesh
def load_stl(path):
    """triangles (n, 3, 3) in mm: binary STL, or ASCII ('solid ... vertex x y z')"""
    b = open(path, 'rb').read()
    if len(b) >= 84:
        n = struct.unpack('<I', b[80:84])[0]
        if 84 + n * 50 == len(b) and n > 0:
            d = np.frombuffer(b[84:84 + n * 50], dtype=np.dtype([('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')]))
            return d['v'].astype(np.float64)
    t = b.decode('utf-8', 'replace')
    vs = re.findall(r'vertex\s+(\S+)\s+(\S+)\s+(\S+)', t)
    if not vs or len(vs) % 3:
        raise ValueError('not an STL file (binary or ASCII): ' + path)
    return np.array(vs, dtype=np.float64).reshape(-1, 3, 3)


def heightmap(v, ppm=40, up=+1):
    """orthographic top view looking down -z (up = +1); H in mm, -inf outside"""
    v = v.copy()
    if up < 0:
        v[:, :, 2] *= -1; v[:, :, 1] *= -1
    x0, y0 = v[:, :, 0].min(), v[:, :, 1].min(); x1, y1 = v[:, :, 0].max(), v[:, :, 1].max()
    W = int(np.ceil((x1 - x0) * ppm)) + 2; Hh = int(np.ceil((y1 - y0) * ppm)) + 2
    H = np.full((Hh, W), -np.inf)
    X = (v[:, :, 0] - x0) * ppm + 1; Y = (y1 - v[:, :, 1]) * ppm + 1; Z = v[:, :, 2]
    for t in range(len(v)):
        xs, ys, zs = X[t], Y[t], Z[t]
        ax, ay = xs[0], ys[0]; bx, by = xs[1], ys[1]; cx, cy = xs[2], ys[2]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        i0, i1 = int(np.floor(min(xs))), int(np.ceil(max(xs))); j0, j1 = int(np.floor(min(ys))), int(np.ceil(max(ys)))
        gx, gy = np.meshgrid(np.arange(i0, i1 + 1) + 0.5, np.arange(j0, j1 + 1) + 0.5)
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den; l3 = 1 - l1 - l2
        m = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        if not m.any():
            continue
        z = l1 * zs[0] + l2 * zs[1] + l3 * zs[2]
        sub = H[j0:j1 + 1, i0:i1 + 1]
        jj, ii = np.nonzero(m)
        np.maximum.at(sub, (jj, ii), z[m])
    return H, (x0, x1, y0, y1)


def prep_rot(v0, deg, sign):
    """gen_tilt_all.prep_rot on a loaded mesh: centred, 1.5u landscape turned portrait, the
    top side (the smoother height map) up, turned deg about x (front to back), rasterised at
    40 px/mm and cropped; deg 0 = models.prep exactly"""
    v = v0.copy()
    flat = v.reshape(-1, 3); v = v - (flat.min(0) + flat.max(0)) / 2
    ext = flat.max(0) - flat.min(0)
    if ext[0] > ext[1] * 1.3:
        v = np.stack([-v[..., 1], v[..., 0], v[..., 2]], -1)
    best = None
    for up in (1, -1):
        H, _ = heightmap(v, 10, up); m = np.isfinite(H)
        rough = np.abs(nd.laplace(nd.gaussian_filter(np.where(m, H, 0), 1)))[nd.binary_erosion(m, iterations=3)].mean()
        if best is None or rough < best[0]:
            best = (rough, up)
    if best[1] < 0:
        v = v.copy(); v[..., 2] *= -1; v[..., 1] *= -1
    if deg:
        t = np.radians(deg) * sign; c, s = np.cos(t), np.sin(t)
        y, z = v[..., 1].copy(), v[..., 2].copy(); v[..., 1] = c * y - s * z; v[..., 2] = s * y + c * z
    H, _ = heightmap(v, PPM, 1)
    m = np.isfinite(H); ys, xs = np.nonzero(m)
    return H[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


# ------------------------------------------------------------------ the top face
def convex_hull_image(img):
    """skimage.morphology.convex_hull_image (offset_coordinates, tolerance 1e-10) with scipy"""
    if img.ndim != 2 or not img.any():
        return np.zeros_like(img, dtype=bool)
    coords = np.argwhere(img).astype(float)
    off = np.array([[0, 0], [0, 0.5], [0, -0.5], [0.5, 0], [-0.5, 0]])
    coords = (coords[:, None, :] + off[None]).reshape(-1, 2)
    hull = ConvexHull(coords)
    verts = hull.points[hull.vertices]
    rr, cc = np.nonzero(np.ones(img.shape, bool))
    pts = np.c_[rr, cc].astype(float)
    # inside the hull (with skimage's tolerance): every facet's half-space
    eq = hull.equations
    inside = np.all(pts @ eq[:, :2].T + eq[:, 2] <= 1e-10, axis=1)
    return inside.reshape(img.shape)


def radii(m, cx, cy, n=720):
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False); out = np.zeros(n); h, w = m.shape
    for i, a in enumerate(ang):
        r = 0.0
        while True:
            x, y = cx + np.cos(a) * (r + 0.5), cy + np.sin(a) * (r + 0.5)
            if not (0 <= int(y) < h and 0 <= int(x) < w) or not m[int(y), int(x)]:
                break
            r += 0.5
        out[i] = r
    return ang, out


def face_of(H, mask):
    """models.face_of (.161 rule, BEND 0.75): per ray the face ends where the top is steeper
    than SLOPE and bending down by more than BEND per mm; smoothed; convex"""
    h, w = H.shape; cy, cx = (h - 1) / 2, (w - 1) / 2
    Hf = np.where(mask, H, H[mask].min() - 2); Hs = nd.gaussian_filter(Hf, 2.0)
    yy, xx = np.mgrid[0:h, 0:w]
    core = mask & (np.hypot((xx - cx) / w, (yy - cy) / h) < 0.18)
    A = np.c_[xx[core], yy[core], np.ones(core.sum())]
    p, *_ = np.linalg.lstsq(A, Hs[core], rcond=None)
    D = Hs - (p[0] * xx + p[1] * yy + p[2])
    ang, ro = radii(mask, cx, cy, 720); rf = np.zeros_like(ro)
    for i, a in enumerate(ang):
        rr = np.arange(0, ro[i] - 1, 0.5)
        xs, ys = cx + np.cos(a) * rr, cy + np.sin(a) * rr
        d = nd.map_coordinates(D, [ys, xs], order=1)
        sl = np.gradient(d, 0.5 / PPM)
        k0 = int(0.4 * len(rr))
        cv = np.gradient(nd.gaussian_filter1d(sl, 4), 0.5 / PPM)
        hit = np.nonzero((sl[k0:] < -SLOPE) & (cv[k0:] < -BEND))[0]
        k = k0 + hit[0] if len(hit) else len(rr) - 1
        rf[i] = max(rr[k], 0.45 * ro[i])
    rf = nd.median_filter(rf, 31, mode='wrap'); rf = nd.gaussian_filter1d(rf, 6, mode='wrap')
    th = np.arctan2(yy - cy, xx - cx) % (2 * np.pi)
    rr = np.interp(th / (2 * np.pi) * len(ang), np.arange(len(ang) + 1), np.append(rf, rf[0]))
    return convex_hull_image((np.hypot(xx - cx, yy - cy) <= rr) & mask) & mask


def elongate(H, target_mm=26.5):
    """models.elongate: 1u -> 1.5u along the key's front-to-back axis, the tilt kept"""
    h, w = H.shape; m = np.isfinite(H); n = int(round(target_mm * PPM))
    yy = np.arange(h)
    mid = np.where(m, H, np.nan)[:, int(w * 0.35):int(w * 0.65)]
    with np.errstate(all='ignore'):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            rows = np.nanmean(mid, 1)
    ok = (yy > h * 0.3) & (yy < h * 0.7) & np.isfinite(rows)
    k, b = np.polyfit(yy[ok], rows[ok], 1)
    R = np.where(m, H - (k * yy[:, None] + b), -np.inf)
    t = np.linspace(0, 1, n); win = np.clip((t - 0.2) / 0.6, 0, 1)
    bump = np.sin(np.pi * win) ** 2
    a = (n - 1 - (h - 1)) / ((n - 1) * bump.mean()); d = 1 - a * bump
    src = np.concatenate([[0], np.cumsum((d[1:] + d[:-1]) / 2)]) * (n - 1) / (n - 1)
    src = src * (h - 1) / src[-1]
    Rf = np.where(np.isfinite(R), R, -50.0)
    out = np.stack([np.interp(src, yy, Rf[:, j]) for j in range(w)], 1)
    msk = np.stack([np.interp(src, yy, m[:, j].astype(float)) for j in range(w)], 1) > 0.5
    ynew = (np.arange(n) - (n - 1) / 2) + (h - 1) / 2
    return np.where(msk, out + k * ynew[:, None] + b, -np.inf)


# ------------------------------------------------------------------ lighting
def normals(Hs):
    gy, gx = np.gradient(Hs, 1 / PPM)
    N = np.dstack([-gx, -gy, np.ones_like(Hs)])
    return N / np.linalg.norm(N, axis=2, keepdims=True)


def build(H, level=0.0, smooth=7.0, steep=1.0):
    """models.build"""
    mask = np.isfinite(H)
    Hf = np.where(mask, H, H[mask].min() - 1.0)
    face = face_of(H, mask)
    h0 = nd.gaussian_filter(Hf, 1.2)
    inner = nd.gaussian_filter(nd.binary_erosion(face, iterations=14).astype(float), 6)
    Hs = h0 * (1 - inner) + nd.gaussian_filter(Hf, smooth) * inner
    N = normals(Hs)
    if steep != 1.0:
        w = nd.gaussian_filter(nd.binary_dilation(face, iterations=2).astype(float), 3)
        gy, gx = np.gradient(Hs, 1 / PPM); k = 1 + (steep - 1) * w
        N = np.dstack([-gx * k, -gy * k, np.ones_like(Hs)]); N /= np.linalg.norm(N, axis=2, keepdims=True)
    if level > 0:
        hh, ww = H.shape; yy, xx = np.mgrid[0:hh, 0:ww]
        core = nd.binary_erosion(face, iterations=10)
        A = np.c_[xx[core] / PPM, yy[core] / PPM, np.ones(core.sum())]
        pa, *_ = np.linalg.lstsq(A, Hs[core], rcond=None)
        w = nd.gaussian_filter(nd.binary_dilation(face, iterations=2).astype(float), 3) * level
        gy, gx = np.gradient(Hs, 1 / PPM)
        gx = gx - w * pa[0]; gy = gy - w * pa[1]
        N = np.dstack([-gx, -gy, np.ones_like(Hs)]); N /= np.linalg.norm(N, axis=2, keepdims=True)
    ring = nd.binary_erosion(face, iterations=6) ^ face
    sheen = np.clip(N[..., 2], 0, 1) ** 300 * ((~face) | ring) * mask
    alpha = nd.gaussian_filter(mask.astype(float), 0.7)
    return dict(N=N, sheen=sheen, alpha=alpha, dish=face, mask=mask, H=Hf)


def build_ls(H, level=0.0, smooth=7.0, steep=1.0):
    """gen_ldsa_dish_tilt.build_ls: levelled first, then steeper (models.build alone would let
    the levelling undo the steepening)"""
    if steep == 1.0:
        return build(H, level, smooth)
    S = build(H, level, smooth); mask = S['mask']
    Hf = np.where(mask, H, H[mask].min() - 1.0); face = S['dish']
    h0 = nd.gaussian_filter(Hf, 1.2)
    inner = nd.gaussian_filter(nd.binary_erosion(face, iterations=14).astype(float), 6)
    Hs = h0 * (1 - inner) + nd.gaussian_filter(Hf, smooth) * inner
    hh, ww = H.shape; yy, xx = np.mgrid[0:hh, 0:ww]
    core = nd.binary_erosion(face, iterations=10)
    A = np.c_[xx[core] / PPM, yy[core] / PPM, np.ones(core.sum())]
    pa, *_ = np.linalg.lstsq(A, Hs[core], rcond=None)
    wf = nd.gaussian_filter(nd.binary_dilation(face, iterations=2).astype(float), 3)
    gy, gx = np.gradient(Hs, 1 / PPM)
    gx = gx - wf * level * pa[0]; gy = gy - wf * level * pa[1]
    k = 1 + (steep - 1) * wf; gx, gy = gx * k, gy * k
    N = np.dstack([-gx, -gy, np.ones_like(Hs)]); N /= np.linalg.norm(N, axis=2, keepdims=True)
    ring = nd.binary_erosion(face, iterations=6) ^ face
    S['N'] = N; S['sheen'] = np.clip(N[..., 2], 0, 1) ** 300 * ((~face) | ring) * mask
    return S


def to_map(S, nw=128, nh=128):
    def rs(a):
        return np.asarray(Image.fromarray(a.astype(np.float32), 'F').resize((nw, nh), Image.BOX))
    m = S['mask'].astype(float); A = rs(S['alpha']); wgt = np.maximum(rs(m), 1e-6)
    nx = rs(S['N'][..., 0] * m) / wgt; ny = rs(S['N'][..., 1] * m) / wgt
    rgba = np.dstack([(nx * 0.5 + 0.5) * 255, (ny * 0.5 + 0.5) * 255, rs(S['sheen']) * 255, A * 255])
    return np.clip(np.round(rgba), 0, 255).astype(np.uint8)


def outline(m, cw, ch, n=120):
    h, w = m.shape; cy, cx = (h - 1) / 2, (w - 1) / 2
    ang, r = radii(m, cx, cy, n * 4); r = nd.gaussian_filter1d(r, 2, mode='wrap')
    return [(round((cx + np.cos(a) * rr) / w * cw, 3), round((cy + np.sin(a) * rr) / h * ch, 3))
            for a, rr in list(zip(ang, r))[::4]]


def _asset_of(S, tall):
    cw, ch = 25, (37 if tall else 25)
    rgba = to_map(S, 128, 190 if tall else 128)
    sil, dsh = outline(S['mask'], cw, ch), outline(S['dish'], cw, ch)
    xs = [p[0] for p in dsh]; ys = [p[1] for p in dsh]
    b = io.BytesIO(); Image.fromarray(rgba, 'RGBA').save(b, 'PNG', optimize=True)
    return dict(rgba=rgba, sil=sil, dish=dsh, png=b.getvalue(),
                face=[round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)])


def asset(H, tall, level=0.0, smooth=7.0, steep=1.0, levelled_steep=False):
    return _asset_of((build_ls if levelled_steep else build)(H, level, smooth, steep), tall)


# ------------------------------------------------------------------ flat tops
def widen(Hf, mask, dish, alpha):
    """assets.widen on any model: the rim moved alpha of the way out toward the edge"""
    h, w = Hf.shape; cy, cx = (h - 1) / 2, (w - 1) / 2
    yy, xx = np.mgrid[0:h, 0:w]
    ang, RD = radii(dish, cx, cy); _, RO = radii(mask, cx, cy)
    RD = nd.gaussian_filter1d(RD, 3, mode='wrap'); RO = nd.gaussian_filter1d(RO, 2, mode='wrap')
    th = np.arctan2(yy - cy, xx - cx) % (2 * np.pi); r = np.hypot(xx - cx, yy - cy)
    idx = th / (2 * np.pi) * len(ang)
    rd = np.interp(idx, np.arange(len(ang) + 1), np.append(RD, RD[0]))
    ro = np.interp(idx, np.arange(len(ang) + 1), np.append(RO, RO[0]))
    f = RD / (RD + alpha * (RO - RD)); f = nd.gaussian_filter1d(f, 40, mode='wrap')
    fi = np.interp(idx, np.arange(len(ang) + 1), np.append(f, f[0]))
    rd2 = np.minimum(rd / fi, ro - 0.5)
    s = np.where(r <= rd2, r * rd / rd2, rd + (r - rd2) * (ro - rd) / np.maximum(ro - rd2, 1e-6))
    k = np.where(r > 0, s / np.maximum(r, 1e-9), 0)
    return nd.map_coordinates(Hf, [cy + (yy - cy) * k, cx + (xx - cx) * k], order=1, mode='nearest')


def flat_top(H, wide):
    """gen_flat_tops: the dish filled level at the rim's top less 0.05 mm (rim widened by
    'wide' first when not 0), Gaussian 4 px into the flank, variants.finish lighting"""
    mask = np.isfinite(H)
    Hf = np.where(mask, H, H[mask].min() - 1.0)
    dish = face_of(H, mask)
    if wide:
        Hf = np.where(mask, widen(Hf, mask, dish, wide), Hf)
        dish = face_of(np.where(mask, Hf, -np.inf), mask)
    zt = float(Hf[mask & ~dish].max()) - 0.05
    Ht = np.where(dish, zt, np.minimum(Hf, zt))
    Ht = np.where(mask, nd.gaussian_filter(Ht, 4.0), Hf)
    N = normals(nd.gaussian_filter(Ht, 1.2))
    ring = nd.binary_erosion(dish, iterations=6) ^ dish
    sheen = np.clip(N[..., 2], 0, 1) ** 300 * ((~dish) | ring) * mask * 0.6
    return dict(N=N, sheen=sheen, alpha=nd.gaussian_filter(mask.astype(float), 0.7), dish=dish, mask=mask, H=Ht)


# ------------------------------------------------------------------ Legend 3D grids
def grid_for(H, tilt_k=1.0, curv_k=None):
    """grid_tilt.grid_for: the face's overall tilt foreshortened at tilt_k x its real slope,
    the dish's curve at curv_k (default 3; 0 = the tilt-only twin, warpt=)"""
    ck = K_GRID if curv_k is None else curv_k
    mask = np.isfinite(H); h, w = H.shape
    Hf = np.where(mask, H, H[mask].min() - 1)
    face = face_of(H, mask)
    ys, xs = np.nonzero(face); fx, fy = xs.mean(), ys.mean()
    Hs = nd.gaussian_filter(Hf, 3.0)
    gy, gx = np.gradient(Hs, 1 / PPM)
    core = nd.binary_erosion(face, iterations=10); yy0, xx0 = np.nonzero(core)
    A = np.c_[xx0 / PPM, yy0 / PPM, np.ones(len(xx0))]; pa, *_ = np.linalg.lstsq(A, Hs[yy0, xx0], rcond=None)
    F = nd.binary_erosion(face, iterations=2).astype(float)
    ex = tilt_k * pa[0] + ck * (gx - pa[0]); ey = tilt_k * pa[1] + ck * (gy - pa[1])
    sx = np.sqrt(1 + (ex * F) ** 2); sy = np.sqrt(1 + (ey * F) ** 2)
    U = np.cumsum(sx, 1); V = np.cumsum(sy, 0)
    U = U - np.array([np.interp(fx, np.arange(w), U[r]) for r in range(h)])[:, None]
    V = V - np.array([np.interp(fy, np.arange(h), V[:, c]) for c in range(w)])[None, :]
    yy, xx = np.mgrid[0:h, 0:w]
    Ax, Ay = fx + U, fy + V
    st = 3
    P = np.c_[Ax[::st, ::st].ravel(), Ay[::st, ::st].ravel()]
    nodes = np.array([[(j / N_GRID) * (w - 1), (i / N_GRID) * (h - 1)] for i in range(N_GRID + 1) for j in range(N_GRID + 1)])
    X = griddata(P, xx[::st, ::st].ravel().astype(float), nodes, 'linear')
    Y = griddata(P, yy[::st, ::st].ravel().astype(float), nodes, 'linear')
    dx = np.nan_to_num(X - nodes[:, 0]); dy = np.nan_to_num(Y - nodes[:, 1])
    out_d = nd.distance_transform_edt(~face)
    wgt = np.clip(1 - nd.map_coordinates(out_d, [nodes[:, 1], nodes[:, 0]], order=1) / (1.5 * PPM), 0, 1)
    ii = np.repeat(np.arange(N_GRID + 1), N_GRID + 1); jj = np.tile(np.arange(N_GRID + 1), N_GRID + 1)
    wgt[(ii == 0) | (ii == N_GRID) | (jj == 0) | (jj == N_GRID)] = 0
    du = dx * wgt / ((w - 1) / 2); dv = dy * wgt / ((h - 1) / 2)
    return np.c_[du, dv].reshape(N_GRID + 1, N_GRID + 1, 2)


def enc(g):
    return ' '.join('%d,%d' % (round(a * 1000), round(b * 1000)) for a, b in g.reshape(-1, 2))


# ------------------------------------------------------------------ tilt and sides
def plane_slope(H):
    m = np.isfinite(H); face = face_of(H, m); yy, xx = np.nonzero(face)
    A = np.c_[xx / PPM, yy / PPM, np.ones(len(xx))]; p, *_ = np.linalg.lstsq(A, H[yy, xx], rcond=None)
    return p[1]


def lowside(H):
    m = np.isfinite(H); face = face_of(H, m)
    ys = np.nonzero(face.any(1))[0]; y0, y1 = ys.min(), ys.max(); n = int((y1 - y0) * 0.3)
    top = H[y0:y0 + n][face[y0:y0 + n]].mean(); bot = H[y1 - n:y1 + 1][face[y1 - n:y1 + 1]].mean()
    return 'top' if top < bot else 'bottom'


def tilted(v, deg, sloped):
    """gen_tilt_all.tilted: a sloped model steepened (the turn giving the steeper face plane),
    else the low side at the bottom"""
    if sloped:
        cands = [(abs(plane_slope(Ht)), Ht) for Ht in (prep_rot(v, deg, 1), prep_rot(v, deg, -1))]
        return max(cands, key=lambda c: c[0])[1]
    Ht = None
    for sign in (1, -1):
        Ht = prep_rot(v, deg, sign)
        if lowside(Ht) == 'bottom':
            return Ht
    return Ht


# ------------------------------------------------------------------ the file
def _fmt(v):
    s = '%.2f' % v; s = s.rstrip('0').rstrip('.') if '.' in s else s
    return '0' if s in ('-0', '') else s


def _pts(p, ky):
    return ' '.join('%s,%s' % (_fmt(x), _fmt(y * ky)) for x, y in p)


def section(a, tall, grids=None):
    """gen_capmodels.section, plus (embed_warps) the warp= / warpt= lines after map="""
    ky = 25 / 37 if tall else 1
    f = a['face']; face = [f[0], f[1] * ky, f[2], f[3] * ky]
    t = ('face=' + ','.join(_fmt(v) for v in face) + '\n' + 'sil=' + _pts(a['sil'], ky) + '\n'
         + 'dish=' + _pts(a['dish'], ky) + '\n' + 'map=' + base64.b64encode(a['png']).decode() + '\n')
    if grids:
        t += 'warp=' + grids[0] + '\n'
        if grids[1]:
            t += 'warpt=' + grids[1] + '\n'
    return t


def write(out, key, name, turn, turn90, low, src, secs):
    t = ('; PR-PEEK Render keycap model, for export_from_drawio 2025-07-30.89 and later.\n'
         '; One model per file, read from the capmodels folder next to the script.\n'
         '; Delete the file to drop the model. Made from ' + src + '.\n'
         'name=' + name + '\nturn=' + str(turn) + '\n' + ('lowside=' + low + '\n' if low else '')
         + ('turn90=1\n' if turn90 else ''))
    for s, body in secs:
        t += '[' + s + ']\n' + body
    p = os.path.join(out, key + '.capmodel')
    with open(p, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(t)
    return p


def deg_tag(d):
    return ('%g' % d).replace('.', '_')


STEEP_SFX = {1.0: '', 1.5: '_s15', 2.0: '_s20', 3.0: '_s30'}
TOPS = {'flat': (0.0, 'flat top'), 'wflat': (0.20, 'widened flat top'), 'xwflat': (0.40, 'extra widened flat top')}


def make(stl, out, key, name, tilts=(0,), steeps=(1.0,), tops=('dish',), long_=False, turn=False,
         turn90=False, sloped=False, say=lambda pct, msg: None):
    """the model files for one STL; returns the paths written"""
    key = re.sub(r'[^a-z0-9_]', '_', key.lower()).strip('_') or 'cap'
    os.makedirs(out, exist_ok=True)
    v = load_stl(stl)
    src = os.path.basename(stl)
    jobs = []
    for d in tilts:
        if 'dish' in tops:
            jobs += [('dish', d, s) for s in steeps]
        if d == 0:
            jobs += [(t, 0, 1.0) for t in ('flat', 'wflat', 'xwflat') if t in tops]
    done, paths, hcache, gcache = 0, [], {}, {}
    for kind, d, s in jobs:
        say(int(5 + 90 * done / max(1, len(jobs))), '%s: %s%s%s' % (
            name, ('tilted %g%s, ' % (d, DEG)) if d else '', kind if kind != 'dish' else 'dish',
            (', %gx steeper' % s) if s != 1 else ''))
        if d not in hcache:
            H = prep_rot(v, 0, 1) if d == 0 else tilted(v, d, sloped)
            hcache[d] = (H, elongate(H) if long_ else None)
        H, HL = hcache[d]
        tiltlit = bool(d) or sloped
        lvl, sm = (LEVEL_T, SMOOTH_T) if tiltlit else (0.0, 7.0)
        if kind == 'dish':
            if d not in gcache:
                gcache[d] = ((enc(grid_for(H, 1.0)), enc(grid_for(H, 1.0, 0.0))),
                             (enc(grid_for(HL, 1.0)), enc(grid_for(HL, 1.0, 0.0))) if long_ else None)
            g1, gl = gcache[d]
            secs = [('1u', section(asset(H, False, lvl, sm, s, levelled_steep=tiltlit), False, g1))]
            if long_:
                secs.append(('long', section(asset(HL, True, lvl, sm, s, levelled_steep=tiltlit), True, gl)))
            k = key + ('_t' + deg_tag(d) if d else '') + STEEP_SFX.get(s, '_s%d' % round(s * 10))
            nm = name + ((' +%g%s' % (d, DEG)) if (d and 'tilted' in name.lower()) else (' tilted %g%s' % (d, DEG)) if d else '') \
                + (' steeper %gx' % s if s != 1 else '')
            note = src + (', tilted %g%s front to back' % (d, DEG) if d else '') + (', face lit %gx steeper' % s if s != 1 else '')
            low = lowside(H) if d else ''
            paths.append(write(out, k, nm, 1 if (d or turn) else 0, turn90, low, note, secs))
        else:
            wide, label = TOPS[kind]
            secs = [('1u', section(_asset_of(flat_top(H, wide), False), False))]
            if long_:
                secs.append(('long', section(_asset_of(flat_top(HL, wide), True), True)))
            paths.append(write(out, key + '_' + kind, name + ' ' + label, 1 if turn else 0, turn90, '',
                               src + ': ' + label + (' (rim widened %d %%)' % round(wide * 100) if wide else ''), secs))
        done += 1
    say(100, '%d model file(s) written' % len(paths))
    return paths


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='png-overlay-export capmodel')
    ap.add_argument('--stl', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--key', default=None)
    ap.add_argument('--name', default=None)
    ap.add_argument('--tilts', default='0')
    ap.add_argument('--steep', default='1')
    ap.add_argument('--tops', default='dish')
    ap.add_argument('--long', action='store_true')
    ap.add_argument('--turn', action='store_true')
    ap.add_argument('--turn90', action='store_true')
    ap.add_argument('--sloped', action='store_true')
    ap.add_argument('--progress', default=None)
    ap.add_argument('--result', default=None)
    a = ap.parse_args(argv)
    base = os.path.splitext(os.path.basename(a.stl))[0]

    def say(pct, msg):
        print('%3d%%  %s' % (pct, msg), flush=True)
        if a.progress:
            try:
                with open(a.progress, 'w', encoding='utf-8') as f:
                    f.write('%d\t%s' % (pct, msg))
            except OSError:
                pass
    res = {'ok': False, 'files': [], 'message': ''}
    try:
        nums = lambda s: [float(x) for x in re.split(r'[ ,;]+', s.strip()) if x]
        res['files'] = make(a.stl, a.out, a.key or base, a.name or base, nums(a.tilts) or [0.0],
                            nums(a.steep) or [1.0], [t for t in re.split(r'[ ,;]+', a.tops.strip().lower()) if t] or ['dish'],
                            a.long, a.turn, a.turn90, a.sloped, say)
        res['ok'] = True
        res['message'] = '%d model file(s) written to %s' % (len(res['files']), a.out)
        code = 0
    except Exception as e:                          # noqa: BLE001 - reported to the script
        import traceback
        res['message'] = '%s: %s' % (type(e).__name__, e)
        res['trace'] = traceback.format_exc()
        code = 1
    if a.result:
        with open(a.result, 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(res['message'])
    return code
