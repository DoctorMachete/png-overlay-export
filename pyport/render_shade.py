"""Render shading in numpy: RenderShade of the .147 script (RenderItems,
RenderAsset, RenderOverlay, RenderMeasure, RenderDrawItems, RenderBearing).

Each opaque cap of a layer gets an overlay - grey and alpha, from its model's
normal map lit by the lamp from its own angle - filled into its outline
(turned with the key, mirrored for the right hand, pulled in by the edge
inset), at its role's opacity, over the raw draw.io image.  Then its homing
ball, if any.  RenderMeasure first finds where each cap really is in the raw.
"""
import base64, io, math, os, re
import numpy as np, cv2
from PIL import Image

GRP_W, GRP_H, FRAME_PAD = 444.0, 177.7714699700121, 8.0
D2R = math.pi / 180

# ------------------------------------------------------------ the script's data
class Script:
    """Constants and built-in shapes read from the .ah2."""
    def __init__(self, ahk):
        s = open(ahk, encoding='utf-8-sig').read()
        self.s = s
        def strvar(name):
            parts = re.findall(r'^' + name + r' (?::=|\.=) "([^"]*)"', s, re.M)
            return ''.join(parts)
        self.shapes = {}
        for key, suf in (('real', 'REAL'), ('wide', 'WIDE'), ('flat', 'FLAT'), ('cover', 'COVER'),
                         ('bezel', 'BEZEL'), ('wflat', 'WFLAT')):
            m = strvar('RENDER_MAP_' + suf)
            if not m:
                continue
            face = re.search(r'"' + key + r'", Map\("map", RENDER_MAP_' + suf + r'[^\]]*"face", \[([^\]]+)\]', s) or \
                   re.search(r'RENDER_SHAPES\["' + key + r'"\] := Map\([^\]]*"face", \[([^\]]+)\]', s)
            self.shapes[key] = dict(map=m, sil=strvar('RENDER_SIL_' + suf), dish=strvar('RENDER_DISH_' + suf),
                                    face=[float(v) for v in face.group(1).split(',')])
        self.cap_warp = dict(re.findall(r'^CAP_WARP\["([^"]+)"\] := "([^"]*)"', s, re.M))
        pl = s[s.index('POS_LABEL := ['):]
        self.pos_label = re.findall(r'"([LR]H-[^"]+)"', pl[:pl.index(']')])

def pts(sx):
    return [tuple(float(v) for v in p.split(',')) for p in sx.split()]

def turn_pts(p, deg):
    if deg == 90:
        return [(25 - y, x) for x, y in p]
    if deg == 270:
        return [(y, 25 - x) for x, y in p]
    return [(25 - x, 25 - y) for x, y in p]

# ------------------------------------------------------------------ model files
_files = {}
def capmodel(capdir, mk):
    mk = mk.lower()
    if mk in _files:
        return _files[mk]
    fp = os.path.join(capdir or '', mk + '.capmodel')
    res = None
    if capdir and re.fullmatch(r'[a-z0-9_\-]+', mk) and os.path.exists(fp):
        mf = dict(name=mk, turn=False, turn90=False, lowtop=False, secs={})
        sec, raws = '', {}
        for ln in open(fp, encoding='utf-8-sig').read().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith(';'):
                continue
            m = re.fullmatch(r'\[(.+)\]', ln)
            if m:
                sec = m.group(1).lower(); raws[sec] = {}; continue
            if '=' not in ln:
                continue
            k, v = ln.split('=', 1); k = k.lower()
            if sec == '':
                if k == 'name': mf['name'] = v
                elif k == 'turn': mf['turn'] = v.strip() == '1'
                elif k == 'turn90': mf['turn90'] = v.strip() == '1'
                elif k == 'lowside': mf['lowtop'] = v.strip() == 'top'
            else:
                raws[sec][k] = v
        for sn, d in raws.items():
            if all(k in d for k in ('face', 'sil', 'dish', 'map')):
                f = d['face'].split(',')
                if len(f) == 4:
                    d['face'] = [float(v) for v in f]
                    mf['secs'][sn] = d
        res = mf
    _files[mk] = res
    return res

class Shapes:
    def __init__(self, script, capdir, render_shape='real'):
        self.sc, self.capdir, self.default = script, capdir, render_shape
        self.cache = {}

    def key(self, s):
        if s.startswith('m:'):
            return s
        return s.lower() if s.lower() in ('wide', 'flat', 'wflat', 'cover', 'bezel') else 'real'

    def src(self, shape):
        """RenderShapeSrc / CapModelSrc: map, sil, dish, face, turn."""
        shape = self.key(shape)
        if not shape.startswith('m:'):
            b = self.sc.shapes[shape]
            return dict(map=b['map'], sil=pts(b['sil']), dish=pts(b['dish']), face=b['face'], turn=0)
        parts = shape.split(':'); mk = parts[1] if len(parts) > 1 else ''
        turn, long, wide = 0, False, False
        for fl in parts[2:]:
            m = re.fullmatch(r'r(90|180|270)', fl)
            if m: turn = int(m.group(1))
            elif fl == 'L': long = True
            elif fl == 'w': wide = True
        mf = capmodel(self.capdir, mk); sn = ''
        if mf:
            if long:
                sn = 'longwide' if (wide and 'longwide' in mf['secs']) else 'long' if 'long' in mf['secs'] else ''
            if sn == '' and '1u' in mf['secs']:
                sn = '1u'
        if sn == '':
            b = self.sc.shapes['wide' if wide else 'real']
            return dict(map=b['map'], sil=pts(b['sil']), dish=pts(b['dish']), face=b['face'], turn=0)
        d = mf['secs'][sn]; fc = d['face']
        if sn != '1u' and turn != 180:
            turn = 0
        r = dict(map=d['map'], sil=pts(d['sil']), dish=pts(d['dish']), face=fc, turn=turn)
        if turn:
            r['sil'] = turn_pts(r['sil'], turn); r['dish'] = turn_pts(r['dish'], turn)
            r['face'] = ([25 - fc[2], 25 - fc[3], 25 - fc[0], 25 - fc[1]] if turn == 180 else
                         [25 - fc[3], fc[0], 25 - fc[1], fc[2]] if turn == 90 else
                         [fc[1], 25 - fc[2], fc[3], 25 - fc[0]])
        return r

    def asset(self, shape):
        """RenderAsset: the normal map as arrays (nh x n), turned as the model is."""
        shape = self.key(shape)
        if shape in self.cache:
            return self.cache[shape]
        src = self.src(shape)
        im = np.asarray(Image.open(io.BytesIO(base64.b64decode(src['map']))).convert('RGBA')).astype(np.float64)
        nx = im[..., 0] / 255 * 2 - 1; ny = im[..., 1] / 255 * 2 - 1
        nz = np.sqrt(np.maximum(0, 1 - nx * nx - ny * ny)); sh = im[..., 2] / 255; al = im[..., 3] / 255
        nh, n = nx.shape
        deg = src['turn']
        if deg in (90, 270) and n != nh:
            deg = 0
        if deg == 180:
            nx, ny, nz, sh, al = -nx[::-1, ::-1], -ny[::-1, ::-1], nz[::-1, ::-1], sh[::-1, ::-1], al[::-1, ::-1]
        elif deg in (90, 270):
            # new (x, y) takes old (y, n-1-x) [90] or (n-1-y, x) [270]; normals turn with it
            ii, jj = np.mgrid[0:n, 0:n]          # ii = y, jj = x
            if deg == 90:
                sy, sx = (n - 1 - jj), ii
                nx2, ny2 = -ny[sy, sx], nx[sy, sx]
            else:
                sy, sx = jj, (n - 1 - ii)
                nx2, ny2 = ny[sy, sx], -nx[sy, sx]
            nx, ny, nz, sh, al = nx2, ny2, nz[sy, sx], sh[sy, sx], al[sy, sx]
        a = dict(n=n, nh=nh, nx=nx, ny=ny, nz=nz, sh=sh, al=al, sil=src['sil'], dish=src['dish'], face=src['face'])
        self.cache[shape] = a
        return a

# --------------------------------------------------------------- the lighting
def light_params(light):
    return (dict(el=72, amb=0.50, key=0.45, sky=0.55, spec=0.35, shin=25, rim=0.60) if light == 'studio' else
            dict(el=50, amb=0.42, key=0.62, sky=0.25, spec=0.45, shin=40, rim=0.35))

_ov = {}
def overlay(shapes, shape, light, az, kS, kH):
    """RenderOverlay as 8-bit ARGB (non-premultiplied), nh x n x 4 RGBA."""
    ck = (shapes.key(shape), light, az, kS, kH)
    if ck in _ov:
        return _ov[ck]
    a = shapes.asset(shape); p = light_params(light)
    lx = math.cos(az * D2R) * math.cos(p['el'] * D2R); ly = -math.sin(az * D2R) * math.cos(p['el'] * D2R)
    lz = math.sin(p['el'] * D2R)
    hx, hy, hz = lx, ly, lz + 1; hn = math.sqrt(hx * hx + hy * hy + hz * hz); hx, hy, hz = hx / hn, hy / hn, hz / hn
    x, y, z = a['nx'], a['ny'], a['nz']
    s = p['amb'] + p['key'] * np.maximum(0, x * lx + y * ly + z * lz) + p['sky'] * (z - 0.8)
    s = 1 + (np.maximum(s, 0.02) ** 0.4545 - 1) * kS
    pp = (p['spec'] * np.maximum(0, x * hx + y * hy + z * hz) ** p['shin'] + p['rim'] * a['sh']) * kH
    pp = np.clip(pp, 0, 1)
    over1 = s > 1
    pp = np.where(over1, 1 - (1 - pp) * np.clip(2 - s, 0, 1), pp)
    s = np.where(over1, 1, s)
    s = np.maximum(0, s)
    aa = 1 - s * (1 - pp)
    gv = np.where(aa > 0, np.round(pp / np.where(aa > 0, aa, 1) * 255), 0)
    A = np.round(aa * a['al'] * 255)
    out = np.zeros(a['nx'].shape + (4,), np.uint8)
    keep = a['al'] > 0
    out[..., 0] = out[..., 1] = out[..., 2] = np.where(keep, np.clip(gv, 0, 255), 0)
    out[..., 3] = np.where(keep, np.clip(A, 0, 255), 0)
    _ov[ck] = out
    return out

_bear = {}
def bearing(mat, d, az, light):
    """RenderBearing: a homing ball sprite (RGBA uint8, n x n, n odd), 4x4 supersampled."""
    d = max(4, round(d * 2) / 2)
    ck = (mat, d, az, light)
    if ck in _bear:
        return _bear[ck]
    el = light_params(light)['el'] * D2R
    lx = math.cos(az * D2R) * math.cos(el); ly = -math.sin(az * D2R) * math.cos(el); lz = math.sin(el)
    hx, hy, hz = lx, ly, lz + 1; hn = math.sqrt(hx * hx + hy * hy + hz * hz); hx, hy, hz = hx / hn, hy / hn, hz / hn
    n = math.ceil(d * 1.5); n += (n + 1) % 2
    ss = 4; nn = n * ss; rr = d * ss / 2; half = nn / 2
    yy, xx = np.mgrid[0:nn, 0:nn] + 0.5 - half
    r2 = (xx * xx + yy * yy) / (rr * rr)
    inb = r2 <= 1
    nx = xx / rr; ny = yy / rr; nz = np.sqrt(np.maximum(0, 1 - r2))
    ndl = np.clip(nx * lx + ny * ly + nz * lz, 0, 1); ndh = np.clip(nx * hx + ny * hy + nz * hz, 0, 1)
    if mat != 'ruby':
        t = np.clip((2 * nz * nz - 1 + 0.35) / 1.35, 0, 1) ** 1.6
        df = 0.18 + 0.55 * ndl; spc = ndh ** 120 * 1.2
        cr = 0.80 * df + (0.22 + 0.78 * t) * 0.55 + spc
        cg = 0.62 * df + (0.15 + 0.78 * t) * 0.55 * 0.775 + spc * 0.97
        cb = 0.28 * df + (0.05 + 0.65 * t) * 0.55 * 0.35 + spc * 0.85
    else:
        th = np.clip(-(nx * lx + ny * ly) * 0.9 + 0.15, 0, 1) * np.clip(1 - nz * 0.4, 0, 1)
        th = th ** 1.5 * 0.8; fr = (1 - nz) ** 4; df = 0.45 + 0.50 * ndl
        hl = ndh ** 400 * 1.6 + ndh ** 40 * 0.15
        cr = 0.90 * df + 1.00 * th + fr * 0.35 + hl
        cg = 0.12 * df + 0.42 * th + fr * 0.30 + hl
        cb = 0.18 * df + 0.45 * th + fr * 0.32 + hl
    sx, sy = -lx * rr * 0.18, -ly * rr * 0.18
    rs = np.sqrt((xx - sx) ** 2 + (yy - sy) ** 2) / rr
    al = np.where(inb, 1.0, np.clip(1 - (rs - 0.85) / 0.45, 0, 1) * 0.55)
    cr, cg, cb = [np.where(inb, np.minimum(1, c), 0) for c in (cr, cg, cb)]
    blk = lambda v: v.reshape(n, ss, n, ss).sum(axis=(1, 3))
    A = blk(al) / (ss * ss)
    out = np.zeros((n, n, 4), np.uint8)
    safe = np.where(A > 0, A, 1)
    for i, c in enumerate((cr, cg, cb)):
        out[..., i] = np.where(A > 0, np.round(np.minimum(1, blk(c * al) / (ss * ss) / safe) * 255), 0)
    out[..., 3] = np.round(np.minimum(1, A) * 255)
    _bear[ck] = out
    return out

# ------------------------------------------------------------------- the keys
# ------------------------------------------------------------------ measuring
def alpha_at(A, px, py):
    h, w = A.shape
    ix = math.floor(px - 0.5); iy = math.floor(py - 0.5); fx = px - 0.5 - ix; fy = py - 0.5 - iy
    v = 0.0
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xx, yy = ix + dx, iy + dy
        if 0 <= xx < w and 0 <= yy < h:
            v += wt * A[yy, xx]
    return v

def edge_at(A, cx, cy, ux, uy, dist):
    inside = alpha_at(A, cx + ux * (dist - 3), cy + uy * (dist - 3))
    if inside < 40:
        return None
    thr = inside / 2; t = dist + 3
    prev = alpha_at(A, cx + ux * t, cy + uy * t)
    if prev >= thr:
        return None
    while t > dist - 3:
        t2 = t - 0.25
        a = alpha_at(A, cx + ux * t2, cy + uy * t2)
        if a >= thr:
            return t2 + 0.25 * (a - thr) / max(a - prev, 0.000001)
        t, prev = t2, a
    return None

def measure(A, items, kx, ky, shapes):
    """RenderMeasure: each cap's offset (mdx, mdy) and size (mfx, mfy) as found in the raw."""
    dxs, dys, miss = [], [], []
    for it in items:
        if it.get('ring'):
            continue
        sil = shapes.asset(it['shape'])['sil']
        x0 = min(p[0] for p in sil); x1 = max(p[0] for p in sil); y0 = min(p[1] for p in sil); y1 = max(p[1] for p in sil)
        x0, y0 = min(x0, 25), min(y0, 25); x1, y1 = max(x1, 0), max(y1, 0)
        pw, ph = it['w'] * kx, it['h'] * ky
        cx = (it['x'] + FRAME_PAD + it['w'] / 2) * kx; cy = (it['y'] + FRAME_PAD + it['h'] / 2) * ky
        r = it['rot'] * D2R; ux, uy = math.cos(r), math.sin(r)
        hl, hr = (0.5 - x0 / 25) * pw, (x1 / 25 - 0.5) * pw
        ht, hb = (0.5 - y0 / 25) * ph, (y1 / 25 - 0.5) * ph
        tr = edge_at(A, cx, cy, ux, uy, hr); tl = edge_at(A, cx, cy, -ux, -uy, hl)
        tb = edge_at(A, cx, cy, -uy, ux, hb); tt = edge_at(A, cx, cy, uy, -ux, ht)
        if None in (tr, tl, tb, tt):
            miss.append(it); continue
        sx = (tr - tl) / 2 - (hr - hl) / 2; sy = (tb - tt) / 2 - (hb - ht) / 2
        fx = (tr + tl) / (hr + hl); fy = (tb + tt) / (hb + ht)
        if abs(sx) > 3 or abs(sy) > 3 or not (0.96 <= fx <= 1.04) or not (0.96 <= fy <= 1.04):
            miss.append(it); continue
        it['mdx'] = sx * ux - sy * uy; it['mdy'] = sx * uy + sy * ux; it['mfx'] = fx; it['mfy'] = fy
        dxs.append(it['mdx']); dys.append(it['mdy'])
    if dxs:
        mx, my = float(np.median(dxs)), float(np.median(dys))
        for it in miss:
            it['mdx'], it['mdy'] = mx, my
    return len(dxs)

# -------------------------------------------------------------------- drawing
SS = 4      # supersampling of the outline's coverage (GDI+ antialiasing)
GAMMA = 2.2  # GDI+ CompositingQualityHighQuality blends in linear light (1 = plain sRGB blending)

def blend(sub, top):
    """Source-over of premultiplied top onto premultiplied sub (in place), as GDI+
    with CompositingQualityHighQuality: colours blended in linear light.  Only the pixels where
    a partly transparent top meets a drawn sub need that; elsewhere the result is the sub
    (top empty) or the top itself (top opaque, or sub empty), so the gamma maths runs on those
    few pixels only (same result, several times faster on a whole canvas)."""
    if GAMMA == 1:
        sub[:] = top + sub * (1 - top[..., 3:4]); return
    ta, da = top[..., 3], sub[..., 3]
    m = ta > 0
    if not m.any():
        return
    plain = m & ((ta >= 1) | (da <= 0))
    sub[plain] = top[plain]
    mix = m & ~plain
    if not mix.any():
        return
    t, d = top[mix], sub[mix]                     # n x 4
    ta1, da1 = t[:, 3:4], d[:, 3:4]
    tc = (t[:, :3] / ta1) ** GAMMA
    dc = (d[:, :3] / da1) ** GAMMA
    oa = ta1 + da1 * (1 - ta1)
    oc = ((tc * ta1 + dc * da1 * (1 - ta1)) / oa) ** (1 / GAMMA)
    sub[mix] = np.concatenate([oc * oa, oa], 1)

def premul(img_u8):
    f = img_u8.astype(np.float32) / 255
    f[..., :3] *= f[..., 3:4]
    return f

def _hex_rgb(h):
    """Gdip.Argb's colour: '#RRGGBB' -> floats 0..1 (anything else black)."""
    m = re.fullmatch(r'#?([0-9A-Fa-f]{6})', h or '')
    v = int(m.group(1), 16) if m else 0
    return np.array([(v >> 16) & 255, (v >> 8) & 255, v & 255], np.float32) / 255


def _poly_cov(polys, n, nh, xor=False):
    """Antialiased coverage (nh x n, 0..1) of polygons in pixel units, SS x SS supersampled;
    xor = GDI+'s alternate fill of several polygons in one path."""
    acc = None
    for P in polys:
        m = np.zeros((nh * SS, n * SS), np.uint8)
        cv2.fillPoly(m, [np.round(np.asarray(P, np.float64) * SS * 16).astype(np.int32)], 1,
                     lineType=cv2.LINE_8, shift=4)
        acc = m if acc is None else (acc ^ m if xor else acc | m)
    return acc.reshape(nh, SS, n, SS).mean(axis=(1, 3)).astype(np.float32)


def _paint(n, fill, grad, d):
    """The cap's paint over the whole n x n cell: flat, or Gdip.FillPathGradient's linear
    gradient over (-1, -1, n + 2, n + 2), the first colour on the side it comes from."""
    c1, c2 = _hex_rgb(fill), _hex_rgb(grad)
    if not grad:
        return np.broadcast_to(c1, (n, n, 3)).copy()
    if d in ('north', 'west'):
        c1, c2 = c2, c1
    t = ((np.arange(n) + 0.5) + 1) / (n + 2)
    lin = c1[None, :] + (c2 - c1)[None, :] * t[:, None]          # along the gradient
    if d in ('south', 'north'):
        return np.broadcast_to(lin[:, None, :], (n, n, 3)).copy()
    return np.broadcast_to(lin[None, :, :], (n, n, 3)).copy()


_capbmp = {}
def cap_bitmap(shapes, edge, fill, grad, d, ring, shape, light, az, kS, kH):
    """RenderCapBitmap: a whole render cap, 128 x 128, premultiplied float RGBA: painted (flat or
    gradient), with edge set the outline in edge and only the dish painted; ring = the outline
    less the dish; the overlay on top (clipped to the ring for a ring)."""
    ck = (edge, fill, grad, d, ring, shapes.key(shape), light, az, kS, kH)
    if ck in _capbmp:
        return _capbmp[ck]
    n = 128
    a = shapes.asset(shape)
    sil = [(p[0] * n / 25, p[1] * n / 25) for p in a['sil']]
    dish = [(p[0] * n / 25, p[1] * n / 25) for p in a['dish']]
    out = np.zeros((n, n, 4), np.float32)
    def fill_with(cov, rgb):
        top = np.concatenate([rgb * cov[..., None], cov[..., None]], -1)
        blend(out, top)
    paint = _paint(n, fill, grad, d)
    if ring:
        rc = _poly_cov([sil, dish], n, n, xor=True)
        fill_with(rc, np.broadcast_to(_hex_rgb(edge), (n, n, 3)) if edge else paint)
    else:
        sc_ = _poly_cov([sil], n, n)
        if edge:
            fill_with(sc_, np.broadcast_to(_hex_rgb(edge), (n, n, 3)))
            fill_with(_poly_cov([dish], n, n), paint)
        else:
            fill_with(sc_, paint)
    ov = premul(overlay(shapes, shape, light, az, kS, kH))
    if ov.shape[:2] != (n, n):
        ov = cv2.resize(ov, (n, n), interpolation=cv2.INTER_AREA if ov.shape[0] > n else cv2.INTER_CUBIC)
    if ring:                       # GdipSetClipPath: a region, not antialiased (pixel centres)
        clip = np.zeros((n, n), np.uint8)
        cv2.fillPoly(clip, [np.round((np.asarray(sil) - 0.5) * 16).astype(np.int32)], 1, cv2.LINE_8, 4)
        hole = np.zeros((n, n), np.uint8)
        cv2.fillPoly(hole, [np.round((np.asarray(dish) - 0.5) * 16).astype(np.int32)], 1, cv2.LINE_8, 4)
        ov = ov * (clip ^ hole)[..., None]
    blend(out, ov)
    _capbmp[ck] = out
    return out


def draw_items(dst, items, kx, ky, P, shapes, ox=0.0, oy=0.0):
    """RenderDrawItems onto dst (premultiplied float RGBA, modified in place).  P: light, kS,
    kH, inset (shade.Params)."""
    H, W = dst.shape[:2]
    for it in items:
        ring = bool(it.get('ring'))
        ov = (cap_bitmap(shapes, it['edge'], it['fill'], it['grad'], it['dir'], True, it['shape'],
                         P.light, it['az'], P.kS, P.kH) if ring
              else overlay(shapes, it['shape'], P.light, it['az'], P.kS, P.kH))
        nh, n = ov.shape[:2]
        pw = it['w'] * kx * it.get('mfx', 1); ph = it['h'] * ky * it.get('mfy', 1)
        cx = (it['x'] + FRAME_PAD + it['w'] / 2) * kx - ox + it.get('mdx', 0)
        cy = (it['y'] + FRAME_PAD + it['h'] / 2) * ky - oy + it.get('mdy', 0)
        a = it['rot'] * D2R; ca, sa = math.cos(a), math.sin(a); mx = -1.0 if it['mir'] else 1.0
        R = math.hypot(pw, ph) / 2 + 2
        x0, x1 = max(0, int(cx - R)), min(W, int(cx + R) + 2); y0, y1 = max(0, int(cy - R)), min(H, int(cy + R) + 2)
        if x0 >= x1 or y0 >= y1:
            continue
        # pixel centres (PixelOffsetModeHalf) -> the key's local coordinates
        def local(px, py):
            dx, dy = px - cx, py - cy
            return (dx * ca + dy * sa) * mx, (-dx * sa + dy * ca)
        if ring:
            # a ring is drawn whole (GdipDrawImageRectRect, TileFlipXY): the cap bitmap stretched
            # over the key's box; its edges antialiased
            py_, px_ = np.mgrid[y0:y1, x0:x1].astype(np.float64)
            lx, ly = local(px_ + 0.5, py_ + 0.5)
            tx = ((lx + pw / 2) * n / pw - 0.5).astype(np.float32)
            ty = ((ly + ph / 2) * nh / ph - 0.5).astype(np.float32)
            tex = np.clip(cv2.remap(ov, tx, ty, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT), 0, 1)
            cov = np.clip(pw / 2 + 0.5 - np.abs(lx), 0, 1) * np.clip(ph / 2 + 0.5 - np.abs(ly), 0, 1)
            blend(dst[y0:y1, x0:x1], tex * (cov * max(0, min(100, it['opac'])) / 100)[..., None])
            continue
        # the outline's coverage, supersampled
        sil = shapes.asset(it['shape'])['sil']
        ins = P.inset
        fx = max(0, pw - 2 * ins) / pw; fy = max(0, ph - 2 * ins) / ph
        poly = np.array([((p[0] / 25 - 0.5) * pw * fx, (p[1] / 25 - 0.5) * ph * fy) for p in sil])
        # outline into pixel space (forward transform), then rasterise at SS x
        wx = cx + poly[:, 0] * mx * ca - poly[:, 1] * sa
        wy = cy + poly[:, 0] * mx * sa + poly[:, 1] * ca
        bw, bh = x1 - x0, y1 - y0
        cov = np.zeros((bh * SS, bw * SS), np.uint8)
        Q = np.stack([(wx - x0) * SS, (wy - y0) * SS], 1)
        cv2.fillPoly(cov, [np.round(Q * 16).astype(np.int32)], 255, lineType=cv2.LINE_8, shift=4)
        cov = cov.reshape(bh, SS, bw, SS).mean(axis=(1, 3)) / 255
        # the texture: local -> texel (scale pw/n, ph/nh, translated by -pw/2, -ph/2)
        py_, px_ = np.mgrid[y0:y1, x0:x1].astype(np.float64)
        lx, ly = local(px_ + 0.5, py_ + 0.5)
        tx = ((lx + pw / 2) * n / pw - 0.5).astype(np.float32)
        ty = ((ly + ph / 2) * nh / ph - 0.5).astype(np.float32)
        tex = cv2.remap(premul(ov), tx, ty, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        tex = np.clip(tex, 0, 1)
        k = cov * max(0, min(100, it['opac'])) / 100
        top = tex * k[..., None]
        sub = dst[y0:y1, x0:x1]
        blend(sub, top)
        # the homing ball
        if it.get('bear'):
            fc = shapes.src(it['shape'])['face']
            fyb = 0.5 if it['bplace'] == 'centre' else 0.78
            bx = ((fc[0] + fc[2]) / 50 - 0.5) * pw
            by = ((fc[1] + fyb * (fc[3] - fc[1])) / 25 - 0.5) * ph
            bs = bearing(it['bear'], 2 / 17.5 * 25 * kx, it['az'], P.light)
            bn = bs.shape[0]
            sx_ = ((lx - (bx - bn / 2)) - 0.5).astype(np.float32)
            sy_ = ((ly - (by - bn / 2)) - 0.5).astype(np.float32)
            spr = cv2.remap(premul(bs), sx_, sy_, cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            spr = np.clip(spr, 0, 1)
            blend(sub, spr)


def render_shade(raw_rgba, items, P, shapes, scale):
    """RenderShade: the raw (uint8 RGBA) with the shading drawn on, or None if it is not the frame's size."""
    h, w = raw_rgba.shape[:2]
    kx, ky = w / (GRP_W + 2 * FRAME_PAD), h / (GRP_H + 2 * FRAME_PAD)
    if abs(kx - scale) > scale * 0.03 or abs(ky - scale) > scale * 0.03:
        return None
    measure(raw_rgba[..., 3].astype(np.float64), items, kx, ky, shapes)
    dst = premul(raw_rgba)
    draw_items(dst, items, kx, ky, P, shapes)
    a = dst[..., 3:4]
    out = np.where(a > 1e-6, dst[..., :3] / np.maximum(a, 1e-6), 0)
    return np.clip(np.concatenate([out, a], -1) * 255 + 0.5, 0, 255).astype(np.uint8)
