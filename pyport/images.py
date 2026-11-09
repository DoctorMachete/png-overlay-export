"""Compositing and shadows of the .147 script: ShadowKeys, KeyFootprints,
ShadowOf (DrawTinted + ScaleBlur), Compose, AlphaBox.

GDI+ behaviour reproduced (Gdip.Graphics: HighQualityBicubic, PixelOffsetMode
half, CompositingQuality HighQuality, AntiAlias):
- blending is in linear light (gamma 2.2: render_shade.blend);
- drawing a bitmap onto an empty one lowers every partial alpha by one level
  (1..254 -> 0..253): measured on the user's raws (exact on alpha);
- a hard clip (SetClipPath) takes the pixels whose centre is inside the path.
Images are uint8 RGBA arrays (straight alpha) between steps, as GDI+'s
32bppARGB bitmaps are."""
import math
import numpy as np, cv2
from PIL import Image
import model as M
import layout as LY
from util import is_number, to_num, round_ahk
from render_shade import blend, premul, pts as _pts

GRP_W, GRP_H, FRAME_PAD = M.GRP_W, M.GRP_H, M.FRAME_PAD


# ------------------------------------------------------------- GDI+ basics
def load(path):
    return np.asarray(Image.open(path).convert('RGBA')).copy()


def save(img, path):
    Image.fromarray(img, 'RGBA').save(path)


def draw_on_empty(img):
    """Gdip.Draw of img 1:1 onto a new (transparent) bitmap."""
    a = img[..., 3]
    a2 = a - ((a > 0) & (a < 255)).astype(np.uint8)       # partial alpha one level down
    out = img * (a2 > 0)[..., None].astype(np.uint8)      # fully transparent pixels: all 0
    out[..., 3] = a2
    return out


def to_f(img):
    return premul(img)


def to_u8(f):
    a = f[..., 3:4]
    c = np.where(a > 1e-6, f[..., :3] / np.maximum(a, 1e-6), 0)
    return np.clip(np.concatenate([c, a], -1) * 255 + 0.5, 0, 255).astype(np.uint8)


def over_u8(base, top):
    """Gdip.Draw of top 1:1 onto base (source-over, linear light)."""
    dst = to_f(base)
    blend(dst, to_f(top))
    return to_u8(dst)


def fill_coverage(polys, w, h, ss=4):
    """Antialiased coverage (0..1) of polygons in pixel space, winding fill, supersampled."""
    cov = np.zeros((h * ss, w * ss), np.uint8)
    pl = [np.round((np.asarray(p, np.float64) * ss - 0.5) * 16).astype(np.int32) for p in polys]
    if pl:
        cv2.fillPoly(cov, pl, 255, lineType=cv2.LINE_8, shift=4)
    # the mean of each ss x ss block (an area resize by a whole factor is exactly that)
    return cv2.resize(cov.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA) / 255


def clip_mask(polys, w, h):
    """The pixels whose centre lies inside the polygons (a GDI+ clip region)."""
    m = np.zeros((h, w), np.uint8)
    pl = [np.round((np.asarray(p, np.float64) - 0.5) * 16).astype(np.int32) for p in polys]
    if pl:
        cv2.fillPoly(m, pl, 1, lineType=cv2.LINE_8, shift=4)
    return m.astype(bool)


def resize_premul(img, w, h):
    """Gdip.Draw scaled onto a new bitmap: HighQualityBicubic on premultiplied pixels."""
    im = Image.fromarray(img, 'RGBA').resize((w, h), Image.BICUBIC)
    return draw_on_empty(np.asarray(im).copy())


def alpha_box(img, step=4):
    """Gdip.AlphaBox: the box of every non-transparent pixel, sampled on a grid and grown by
    the step; None for a blank image."""
    h, w = img.shape[:2]
    a = img[::step, ::step, 3] > 0
    if not a.any():
        return None
    ys, xs = np.nonzero(a)
    x1, x2, y1, y2 = xs.min() * step, xs.max() * step, ys.min() * step, ys.max() * step
    return {"x1": max(0, x1 - step), "y1": max(0, y1 - step),
            "x2": min(w - 1, x2 + step), "y2": min(h - 1, y2 + step)}


# ---------------------------------------------------------------- the keys
def shadow_keys(cfg, doc, L, shapes, skip_trans=False, with_warp=False):
    """ShadowKeys: the painted keys of layer L as dicts x, y, w, h, rot (+ sil: the outline of
    its Render shape; + grid: its Legend 3D grid when with_warp)."""
    out = []
    roles = LY.load_cap_roles(cfg, doc, [])[0] if cfg.key_style == "render" else {}
    centre_x = M.keys_mid_x(doc, L["node"])     # .186
    sils = {}
    for ki, key in enumerate(M.index_keys(doc, L["id"])):
        if M.eff_fill(doc, key) == "NONE":
            continue
        pc = M.key_paint_cell(doc, key)
        kg, pg = M.geo(key), M.geo(pc)
        if kg is None or pg is None:
            continue
        is_child = pc is not key
        rot = M.style_get(pc.get("style"), "rotation", "")
        if not is_number(rot):
            rot = M.style_get(key.get("style"), "rotation", "0")
        k = {"x": kg["x"] + (pg["x"] if is_child else 0), "y": kg["y"] + (pg["y"] if is_child else 0),
             "w": pg["w"], "h": pg["h"], "rot": to_num(rot) if is_number(rot) else 0, "pos": M.pos_name(ki)}
        rn = M.style_get(key.get("style"), "keyRole", "")
        shp, flip = "", False
        tall = kg["h"] > kg["w"] * 1.2
        if roles and rn in roles:
            if skip_trans and LY.cap_transparent(roles[rn]):
                continue
            shp = LY.render_shape_of(cfg, roles[rn], LY.render_pos_shape(cfg, M.pos_name(ki), tall))
            flip = LY.render_quarter(shp) and (kg["x"] + kg["w"] / 2 > centre_x)
            sk = shp + ("|m" if flip else "")
            if sk not in sils:
                p = [list(q) for q in shapes.src(shp)["sil"]]
                if flip:
                    for q in p:
                        q[0] = 25 - q[0]
                sils[sk] = p
            k["sil"] = sils[sk]
        if with_warp:
            if shp == "" and cfg.key_style == "render":
                shp = LY.render_pos_shape(cfg, M.pos_name(ki), tall) or cfg.render_shape
                flip = LY.render_quarter(shp) and (kg["x"] + kg["w"] / 2 > centre_x)
            k["shape"], k["flip"] = shp or "real", flip
        out.append(k)
    return out


def _round_rect(x, y, w, h, r, seg=16):
    """Gdip.RoundPath as a polygon (four 90-degree arcs)."""
    if r <= 0:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    d = 2 * r
    out = []
    for (ax, ay, start) in ((x, y, 180), (x + w - d, y, 270), (x + w - d, y + h - d, 0), (x, y + h - d, 90)):
        for i in range(seg + 1):
            t = math.radians(start + 90 * i / seg)
            out.append((ax + r + r * math.cos(t), ay + r + r * math.sin(t)))
    return out


def key_footprints(cfg, keys, raw_w, raw_h, sx, sy):
    """KeyFootprints: the keys' outlines as polygons in the composite's pixels, or None when
    the raw is not the size the page frame gives."""
    kx, ky = raw_w / (GRP_W + 2 * FRAME_PAD), raw_h / (GRP_H + 2 * FRAME_PAD)
    s = cfg.scale
    if abs(kx - s) > s * 0.03 or abs(ky - s) > s * 0.03:
        return None
    rf = 0.1 if cfg.caps_like() else 0.2
    ins = max(0, to_num(cfg.sh_keyinset)) if is_number(cfg.sh_keyinset) else (0.6 if cfg.caps_like() else 0.25)
    polys = []
    for k in keys:
        cx = (k["x"] + FRAME_PAD + k["w"] / 2) * kx - sx
        cy = (k["y"] + FRAME_PAD + k["h"] / 2) * ky - sy
        if "sil" in k:
            pw, ph, inset = k["w"] * kx, k["h"] * ky, ins * kx
            fx, fy = max(0, pw - 2 * inset) / pw, max(0, ph - 2 * inset) / ph
            p = [((q[0] / 25 - 0.5) * pw * fx, (q[1] / 25 - 0.5) * ph * fy) for q in k["sil"]]
        else:
            pw, ph = max(1, (k["w"] - 2 * ins) * kx), max(1, (k["h"] - 2 * ins) * ky)
            p = _round_rect(-pw / 2, -ph / 2, pw, ph, min(pw, ph) * rf)
        a = math.radians(k["rot"])
        ca, sa = math.cos(a), math.sin(a)
        polys.append([(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in p])
    return polys


# ----------------------------------------------------------------- shadows
def scale_blur(img, radius):
    """Gdip.ScaleBlur: shrink by k and grow back, twice."""
    h, w = img.shape[:2]
    k = max(2, round_ahk(radius * 0.85))
    cur = img
    for _ in range(2):
        small = resize_premul(cur, max(1, w // k), max(1, h // k))
        cur = resize_premul(small, w, h)
    return cur


def shadow_of(cfg, img, dx, dy):
    """ShadowOf: img's alpha, offset by dx, dy, tinted the shadow colour at its opacity, blurred."""
    h, w = img.shape[:2]
    c = cfg.sh_colour
    rgb = [int(c[i:i + 2], 16) for i in (0, 2, 4)]
    t = np.zeros_like(img)
    a = np.floor(img[..., 3].astype(np.float64) * (cfg.sh_opacity / 100) + 0.5).astype(np.uint8)
    t[..., 3] = a
    t[..., :3] = rgb
    sh = np.zeros_like(img)
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    sh[yd, xd] = t[ys, xs]
    sh = draw_on_empty(sh)
    if cfg.sh_blur > 0:
        sh = scale_blur(sh, cfg.sh_blur)
    return sh


def shadow_offset(cfg):
    rad = cfg.sh_angle * 3.14159265358979 / 180
    return round_ahk(cfg.sh_dist * math.cos(rad)), round_ahk(cfg.sh_dist * math.sin(rad))


def shadow_pad(cfg):
    dx, dy = shadow_offset(cfg)
    return max(0, math.ceil(dx + 3 * cfg.sh_blur)), max(0, math.ceil(dy + 3 * cfg.sh_blur))


# ----------------------------------------------------------------- compose
def compose(cfg, base, overlay, box, pad_r, pad_b, shadow=True, keys=None, rings=None, draw_rings=None):
    """Compose: base (and overlay over it) cropped to box, on a canvas padR x padB larger,
    with the shadow underneath.  base/overlay: uint8 RGBA arrays (overlay may be None).
    keys: ShadowKeys for the full-key shadow.  rings: Render ring items, drawn by
    draw_rings(premultiplied canvas, items, kx, ky, sx, sy).  Returns the uint8 image."""
    sx, sy = box["x1"], box["y1"]
    w, h = box["x2"] - sx + 1, box["y2"] - sy + 1
    cw, ch = w + pad_r, h + pad_b
    raw_h, raw_w = base.shape[:2]

    flat = np.zeros((ch, cw, 4), np.uint8)
    flat[:h, :w] = base[sy:sy + h, sx:sx + w]
    flat = draw_on_empty(flat)
    if rings and draw_rings:
        rkx, rky = raw_w / (GRP_W + 2 * FRAME_PAD), raw_h / (GRP_H + 2 * FRAME_PAD)
        s = cfg.scale
        if abs(rkx - s) <= s * 0.03 and abs(rky - s) <= s * 0.03:
            f = to_f(flat)
            draw_rings(f, rings, rkx, rky, sx, sy)
            flat = to_u8(f)
    if overlay is not None:
        top = np.zeros_like(flat)
        top[:h, :w] = overlay[sy:sy + h, sx:sx + w]
        flat = over_u8(flat, top)

    kpolys = key_footprints(cfg, keys, raw_w, raw_h, sx, sy) if (shadow and keys) else None
    shad = solid = None
    if shadow:
        dx, dy = shadow_offset(cfg)
        shad = shadow_of(cfg, flat, dx, dy)
        if kpolys:
            full = draw_on_empty(flat)
            cov = fill_coverage(kpolys, cw, ch)
            black = np.zeros_like(full)
            black[..., 3] = np.round(cov * 255).astype(np.uint8)
            full = over_u8(full, black)
            solid = shadow_of(cfg, full, dx, dy)

    if solid is not None:
        out = draw_on_empty(solid)
        m = clip_mask(kpolys, cw, ch)
        out[m] = shad[m]
    elif shad is not None:
        out = draw_on_empty(shad)
    else:
        out = np.zeros_like(flat)
    return over_u8(out, flat)
