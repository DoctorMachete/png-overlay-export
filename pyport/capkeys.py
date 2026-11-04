"""Key caps on the background page, .148 script: CapKeys, CapSvg, CapGlassParts,
CapGlassSvg, CapGlassStyle/K, CapDishVary, CapLightVec, CapDirVec, CapMix,
CapDeep, BadgeSvg, BadgeRing, BadgeOcto, SvgUri, CapImageStyle,
CapInsertBefore, CapClearPaint, CapFaceRect, BadgeFit, CapFitMove,
LooseBadges, KeyBadges, CapBadge, CapTextMove, CapEmbossText, RenderSvg,
RenderShapeSrc/CapModelSrc as text (RenderTurnPts), RenderFaceOffset,
CapSplitPage; the transparent-role ring of AddForeground."""
import base64, copy, math, re
import model as M
import layout as LY
from util import fmt4, is_number, to_num, same_num, round_ahk, cap_hex
from render_shade import capmodel

CAP_EDGE = ("M866.661,1151.04C908.924,1138.32 952.16,1126.78 996.411,1116.49C1005.54,1116.12 1012.32,1119.57 "
            "1015.96,1128.11C1028.47,1167.02 1039.09,1206.43 1047.56,1246.43C1048.57,1254.57 1045.99,1261.45 "
            "1035.88,1265.69C995.26,1279.12 954.266,1291.08 912.914,1301.61C901.333,1303.84 894.002,1300.76 "
            "890.923,1292.37C878.497,1251.67 867.004,1210.63 856.46,1169.25C854.791,1159.59 858.892,1154.02 "
            "866.661,1151.04Z")
CAP_DISH = ("M863.478,1156.09C904.706,1141.54 954.82,1127.68 1000.25,1119.46C1009.38,1119.09 1012.32,1119.57 "
            "1015.96,1128.11C1029.45,1166.75 1040.23,1206.13 1047.56,1246.43C1048.57,1254.57 1049.98,1259.4 "
            "1041.5,1262.85C998.989,1280.14 943.399,1292.49 903.675,1299.69C896.23,1301.04 894.002,1300.76 "
            "890.923,1292.37C876.162,1254.12 864.596,1213.16 856.46,1169.25C854.791,1159.59 855.708,1159.07 "
            "863.478,1156.09Z")
CAP_DISH_T = "matrix(0.876434,0,0,0.895878,117.297,124.513)"
CAP_W, CAP_H = 166.33, 158.38
CAP_FACE = [1.8, 2.2, 23.0, 23.0]
BADGE_SIZES = [(23, 12), (11, 13)]
D2R = 0.017453292519943295


def f3(v):
    return '%.3f' % v


def f5(v):
    return '%.5f' % v


def cap_mix(c, f, to_white=False):
    res = '#'
    for i in range(3):
        v = int(c[1 + 2 * i:3 + 2 * i], 16)
        v = v + (255 - v) * f if to_white else v * f
        res += '%02X' % max(0, min(255, round_ahk(v)))
    return res


def cap_deep(f, dep):
    return 1 - (1 - f) * dep


def cap_atan2(y, x):
    if x > 0:
        return math.atan(y / x)
    if x < 0:
        return math.atan(y / x) + (math.pi if y >= 0 else -math.pi)
    return math.pi / 2 if y > 0 else -math.pi / 2 if y < 0 else 0


def cap_light_vec(mirrored, ang=45):
    vx, vy = math.cos(ang * D2R), math.sin(ang * D2R)
    if mirrored:
        vx = -vx
    a = 15.34 * D2R
    return [vx * math.cos(a) + vy * math.sin(a), -vx * math.sin(a) + vy * math.cos(a)]


def cap_dir_vec(d, mirrored):
    vx = 1 if d == 'east' else -1 if d == 'west' else 0
    vy = 1 if d == 'south' else -1 if d == 'north' else 0
    if mirrored:
        vx = -vx
    a = 15.34 * D2R
    return [vx * math.cos(a) + vy * math.sin(a), -vx * math.sin(a) + vy * math.cos(a)]


def cap_dish_vary(cfg, cx, cy, mirrored=False):
    base = 45 if mirrored else 135
    res = dict(ang=base, shade=1, glint=1, crease=1, goff=0.24, gside=0, gr=0.30)
    v = to_num(cfg.cap_dish_var) / 100 if (is_number(cx) and is_number(cy)) else 0
    if v <= 0:
        return res
    pos = cap_atan2(cy + 250, cx - M.GRP_W / 2) / D2R
    seed = (abs(round_ahk(cx * 7)) * 1000 + abs(round_ahk(cy * 7))) % 2147483645 + 1
    rn = []
    for _ in range(7):
        seed = (seed * 48271) % 2147483647
        rn.append(seed / 2147483647 * 2 - 1)
    res['ang'] = base + (pos - base) * v + rn[0] * 6 * v
    res['shade'] = 1 + rn[1] * 0.15 * v
    res['glint'] = 1 + rn[2] * 0.25 * v
    res['crease'] = 1 + rn[3] * 0.15 * v
    res['goff'] = 0.24 + rn[4] * 0.05 * v
    res['gside'] = rn[5] * 0.05 * v
    res['gr'] = 0.30 + rn[6] * 0.04 * v
    return res


def cap_glass_style(cfg, r):
    if cfg.cap_glass_nobg or LY.cap_prop(r, 'capGlass') == 'off':
        return 'none'
    gd = r.get('glassDef', '') if hasattr(r, 'get') else ''
    return gd if gd else cfg.cap_glass


def cap_glass_k(cfg, r):
    v = r['glassK'] if ('glassK' in r and is_number(r['glassK'])) else cfg.cap_glass_k
    return max(0, min(200, to_num(v))) / 100 if is_number(v) else 1


def _tr(w, h, mirrored):
    return (('scale(-1,1) ' if mirrored else '') + 'scale(' + f5(w / CAP_W) + ',' + f5(h / CAP_H)
            + ') translate(-599.34,-1417.87) rotate(15.34)')


def cap_glass_parts(w, h, mirrored, tr, st, k, grot=0):
    op = lambda v: f3(max(0, min(1, v * k)))

    def gl(el, clip):
        if grot == 0:
            return el.replace('/>', ' clip-path="url(#' + clip + ')"/>', 1)
        return '<g clip-path="url(#' + clip + ')"><g transform="rotate(' + fmt4(-grot) + ')">' + el + '</g></g>'
    ga = grot * D2R
    cw = abs(w * math.cos(ga)) + abs(h * math.sin(ga))
    ch = abs(w * math.sin(ga)) + abs(h * math.cos(ga))
    w, h = cw, ch
    x0, y0, sx = -w / 2, -h / 2, (-1 if mirrored else 1)
    defs = ('<clipPath id="gce"><path d="' + CAP_EDGE + '" transform="' + tr + '"/></clipPath>'
            + '<clipPath id="gcd"><path d="' + CAP_DISH + '" transform="' + tr + ' ' + CAP_DISH_T + '"/></clipPath>')
    out = ''
    if st == 'crystal':
        out += gl('<rect x="' + fmt4(x0) + '" y="' + fmt4(y0) + '" width="' + fmt4(w) + '" height="' + fmt4(h)
                  + '" fill="#fff" fill-opacity="' + op(0.16) + '"/>', 'gce')
    if st in ('classic', 'over', 'overface'):
        defs += ('<linearGradient id="gA" x1="0" y1="0" x2="0" y2="1">'
                 '<stop offset="0" stop-color="#fff" stop-opacity="' + op(0.75) + '"/>'
                 '<stop offset="1" stop-color="#fff" stop-opacity="' + op(0.10) + '"/></linearGradient>')
        out += gl('<ellipse cx="0" cy="' + fmt4(y0 - h * 0.08) + '" rx="' + fmt4(w * 0.78) + '" ry="'
                  + fmt4(h * 0.60) + '" fill="url(#gA)"/>', 'gcd' if st == 'overface' else 'gce')
    if st in ('gloss', 'crystal'):
        defs += ('<radialGradient id="gB" cx="0.5" cy="0.35" r="0.65">'
                 '<stop offset="0" stop-color="#fff" stop-opacity="' + op(0.70) + '"/>'
                 '<stop offset="0.55" stop-color="#fff" stop-opacity="' + op(0.25) + '"/>'
                 '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>')
        out += (gl('<ellipse cx="' + fmt4(-sx * w * 0.04) + '" cy="' + fmt4(y0 + h * 0.30) + '" rx="'
                   + fmt4(w * 0.36) + '" ry="' + fmt4(h * 0.22) + '" fill="url(#gB)"/>', 'gcd')
                + gl('<ellipse cx="' + fmt4(sx * w * 0.17) + '" cy="' + fmt4(y0 + h * 0.24) + '" rx="'
                     + fmt4(w * 0.05) + '" ry="' + fmt4(h * 0.035) + '" fill="#fff" fill-opacity="' + op(0.85)
                     + '"/>', 'gcd'))
    if st in ('coat', 'crystal'):
        defs += ('<linearGradient id="gC" x1="' + ('0' if mirrored else '1') + '" y1="0" x2="'
                 + ('1' if mirrored else '0') + '" y2="1">'
                 '<stop offset="0" stop-color="#fff" stop-opacity="' + op(0.45) + '"/>'
                 '<stop offset="0.42" stop-color="#fff" stop-opacity="' + op(0.08) + '"/>'
                 '<stop offset="0.5" stop-color="#fff" stop-opacity="0"/></linearGradient>'
                 '<linearGradient id="gR" x1="0" y1="0" x2="0" y2="1"'
                 + ('' if grot == 0 else ' gradientTransform="rotate(' + fmt4(-grot) + ' 0.5 0.5)"') + '>'
                 '<stop offset="0" stop-color="#fff" stop-opacity="' + op(0.95) + '"/>'
                 '<stop offset="0.55" stop-color="#fff" stop-opacity="' + op(0.15) + '"/>'
                 '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
        out += (gl('<rect x="' + fmt4(x0) + '" y="' + fmt4(y0) + '" width="' + fmt4(w) + '" height="' + fmt4(h)
                   + '" fill="url(#gC)"/>', 'gce')
                + '<path d="' + CAP_EDGE + '" transform="' + tr + '" fill="none" stroke="url(#gR)" stroke-width="5"'
                + ' clip-path="url(#gce)"/>')
    return defs, out


def _svg_head(w, h):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="' + fmt4(w) + '" height="' + fmt4(h)
            + '" viewBox="' + fmt4(-w / 2) + ' ' + fmt4(-h / 2) + ' ' + fmt4(w) + ' ' + fmt4(h)
            + '" preserveAspectRatio="none">')


def cap_glass_svg(w, h, mirrored, k, st='over', grot=0):
    d, o = cap_glass_parts(w, h, mirrored, _tr(w, h, mirrored), st, k, grot)
    return _svg_head(w, h) + '<defs>' + d + '</defs>' + o + '</svg>'


# ------------------------------------------------------------ Render shapes (text)
def render_shape_key(s):
    if s.startswith('m:'):
        return s
    return s.lower() if re.fullmatch(r'(?i)wide|flat|wflat|cover|bezel', s or '') else 'real'


def render_turn_pts(pts, deg=180):
    out = []
    for pr in pts.split(' '):
        x, y = (to_num(v) for v in pr.split(','))
        nx, ny = (25 - y, x) if deg == 90 else (y, 25 - x) if deg == 270 else (25 - x, 25 - y)
        out.append(fmt4(round_ahk(nx, 2)) + ',' + fmt4(round_ahk(ny, 2)))
    return ' '.join(out)


class ShapeText:
    """RenderShapeSrc / CapModelSrc with sil and dish as the script's text."""
    def __init__(self, cfg, script):
        self.cfg, self.sc, self.cache = cfg, script, {}

    def src(self, shape):
        shape = render_shape_key(shape)
        if shape in self.cache:
            return self.cache[shape]
        if not shape.startswith('m:'):
            b = self.sc.shapes[shape]
            res = dict(sil=b['sil'], dish=b['dish'], face=b['face'])
        else:
            parts = shape.split(':')
            mk = parts[1] if len(parts) > 1 else ''
            turn, long, wide = 0, False, False
            for fl in parts[2:]:
                m = re.fullmatch(r'r(90|180|270)', fl)
                if m:
                    turn = int(m.group(1))
                elif fl == 'L':
                    long = True
                elif fl == 'w':
                    wide = True
            mf, sn = capmodel(self.cfg.capmodel_dir, mk), ''
            if mf:
                if long:
                    sn = 'longwide' if (wide and 'longwide' in mf['secs']) else 'long' if 'long' in mf['secs'] else ''
                if sn == '' and '1u' in mf['secs']:
                    sn = '1u'
            if sn == '':
                b = self.sc.shapes['wide' if wide else 'real']
                res = dict(sil=b['sil'], dish=b['dish'], face=b['face'])
            else:
                d = mf['secs'][sn]
                fc = d['face']
                if sn != '1u' and turn != 180:
                    turn = 0
                res = dict(sil=d['sil'], dish=d['dish'], face=fc)
                if turn:
                    res['sil'], res['dish'] = render_turn_pts(d['sil'], turn), render_turn_pts(d['dish'], turn)
                    res['face'] = ([25 - fc[2], 25 - fc[3], 25 - fc[0], 25 - fc[1]] if turn == 180 else
                                   [25 - fc[3], fc[0], 25 - fc[1], fc[2]] if turn == 90 else
                                   [fc[1], 25 - fc[2], fc[3], 25 - fc[0]])
        self.cache[shape] = res
        return res

    def face(self, shape=''):
        return self.src(shape or self.cfg.render_shape)['face']

    def face_offset(self, shape):
        """RenderFaceOffset: the dish's centroid from the key's centre, in key units."""
        pts = [[to_num(v) for v in pr.split(',')] for pr in self.src(shape or self.cfg.render_shape)['dish'].split(' ')]
        a = cx = cy = 0
        n = len(pts)
        for i in range(n):
            p, q = pts[i], pts[(i + 1) % n]
            c = p[0] * q[1] - q[0] * p[1]
            a += c
            cx += (p[0] + q[0]) * c
            cy += (p[1] + q[1]) * c
        return [cx / (3 * a) - 12.5, cy / (3 * a) - 12.5] if abs(a) > 1 else [0, 0]

    def text_factor(self, shape):
        """RenderTextFactor(shape)."""
        v = self.cfg.render_text
        if is_number(v):
            return max(0.2, min(1.5, to_num(v) / 100))
        f = self.face(shape)
        ts = (1, 1)
        if is_number(self.cfg.cap_text_warp) and to_num(self.cfg.cap_text_warp) > 0:      # .162
            import keys as K, render_shade as RS
            if getattr(self, '_shapes', None) is None:
                self._shapes = RS.Shapes(self.sc, self.cfg.capmodel_dir, self.cfg.render_shape)
            ts = K.tilt_scale(self._shapes, shape)
        return round_ahk(min((f[2] - f[0]) / ts[0] / (CAP_FACE[2] - CAP_FACE[0]), (f[3] - f[1]) / ts[1] / (CAP_FACE[3] - CAP_FACE[1])), 2)


def render_svg(cfg, st, r, w, h, ring, shape='', mirrored=False):
    lk = LY.render_look(cfg, r)
    edge = lk['edgeOwn']
    shu = shape if shape else lk['shape']
    sh = st.src(shu)
    sil, dish = 'M' + sh['sil'] + 'Z', 'M' + sh['dish'] + 'Z'
    defs, paint = '', lk['fill']
    if lk['grad'] != '':
        d = lk['dir']
        vx = 1 if d == 'east' else -1 if d == 'west' else 0
        vy = 1 if d == 'south' else -1 if d == 'north' else 0
        defs = ('<linearGradient id="d" gradientUnits="userSpaceOnUse" x1="' + f3(12.5 - vx * 12.5) + '" y1="'
                + f3(12.5 - vy * 12.5) + '" x2="' + f3(12.5 + vx * 12.5) + '" y2="' + f3(12.5 + vy * 12.5) + '">'
                '<stop offset="0" stop-color="' + lk['fill'] + '"/><stop offset="1" stop-color="' + lk['grad']
                + '"/></linearGradient>')
        paint = 'url(#d)'
    if ring:
        body = '<path d="' + sil + ' ' + dish + '" fill-rule="evenodd" fill="' + (edge if edge else paint) + '"/>'
    elif edge == '':
        body = '<path d="' + sil + '" fill="' + paint + '"/>'
    else:
        body = '<path d="' + sil + '" fill="' + edge + '"/><path d="' + dish + '" fill="' + paint + '"/>'
    if mirrored and LY.render_quarter(shu):
        body = '<g transform="matrix(-1,0,0,1,25,0)">' + body + '</g>'
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="' + fmt4(w) + '" height="' + fmt4(h)
            + '" viewBox="0 0 25 25" preserveAspectRatio="none"><defs>' + defs + '</defs>' + body + '</svg>')


def cap_svg(cfg, st, r, w, h, mirrored, ring, cx='', cy='', style='', shape='', grot=0):
    if (style or cfg.key_style) == 'render':
        return render_svg(cfg, st, r, w, h, ring, shape, mirrored)
    lk = LY.cap_look(cfg, r)
    fill, grad, eb, dep = lk['fill'], lk['grad'], lk['edge'], lk['depth'] / 100
    tr = _tr(w, h, mirrored)
    defs = ('<linearGradient id="e" x1="0" y1="0" x2="1" y2="0" gradientUnits="userSpaceOnUse" '
            'gradientTransform="matrix(191.668,0,0,191.668,856.092,1209.39)">'
            '<stop offset="0" stop-color="' + cap_mix(eb, cap_deep(111 / 189, dep)) + '"/>'
            '<stop offset="0.46" stop-color="' + cap_mix(eb, cap_deep(88 / 189, dep)) + '"/>'
            '<stop offset="1" stop-color="' + cap_mix(eb, cap_deep(27 / 189, dep)) + '"/></linearGradient>')
    sk = cap_mix(eb, cap_deep(55 / 189, dep))
    if ring:
        defs += ('<mask id="m" maskUnits="userSpaceOnUse" x="700" y="1000" width="500" height="400">'
                 '<rect x="700" y="1000" width="500" height="400" fill="#fff"/>'
                 '<path d="' + CAP_DISH + '" transform="' + CAP_DISH_T + '" fill="#000"/></mask>')
        body = '<path d="' + CAP_EDGE + '" fill="url(#e)" stroke="' + sk + '" stroke-width="0.83" mask="url(#m)"/>'
    elif grad == '':
        defs += ('<radialGradient id="d" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" '
                 'gradientTransform="matrix(192.567,0,0,180.926,855.758,1209.84)">'
                 '<stop offset="0" stop-color="' + cap_mix(fill, lk['shine'] / 100, True) + '"/>'
                 '<stop offset="0.49" stop-color="' + fill + '"/>'
                 '<stop offset="1" stop-color="' + cap_mix(fill, cap_deep(124 / 189, dep)) + '"/></radialGradient>')
        body = ('<path d="' + CAP_EDGE + '" fill="url(#e)" stroke="' + sk + '" stroke-width="0.83"/>'
                '<path d="' + CAP_DISH + '" fill="url(#d)" transform="' + CAP_DISH_T + '"/>')
    else:
        v = cap_dir_vec(lk['dir'], mirrored)
        defs += ('<linearGradient id="d" x1="' + f3(0.5 - v[0] / 2) + '" y1="' + f3(0.5 - v[1] / 2) + '" x2="'
                 + f3(0.5 + v[0] / 2) + '" y2="' + f3(0.5 + v[1] / 2) + '">'
                 '<stop offset="0" stop-color="' + fill + '"/><stop offset="1" stop-color="' + grad
                 + '"/></linearGradient>'
                 '<radialGradient id="s" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" '
                 'gradientTransform="matrix(192.567,0,0,180.926,855.758,1209.84)">'
                 '<stop offset="0" stop-color="#fff" stop-opacity="' + f3(lk['shine'] / 100) + '"/>'
                 '<stop offset="0.49" stop-color="#fff" stop-opacity="0"/>'
                 '<stop offset="0.75" stop-color="#000" stop-opacity="0"/>'
                 '<stop offset="1" stop-color="#000" stop-opacity="' + f3(0.3 * dep) + '"/></radialGradient>')
        body = ('<path d="' + CAP_EDGE + '" fill="url(#e)" stroke="' + sk + '" stroke-width="0.83"/>'
                '<path d="' + CAP_DISH + '" fill="url(#d)" transform="' + CAP_DISH_T + '"/>'
                '<path d="' + CAP_DISH + '" fill="url(#s)" transform="' + CAP_DISH_T + '"/>')
    if not ring and lk['dish'] > 0:
        k = lk['dish'] / 100
        dv = cap_dish_vary(cfg, cx, cy, mirrored)
        lv = cap_light_vec(mirrored, dv['ang'])
        gx = 0.5 + lv[0] * dv['goff'] - lv[1] * dv['gside']
        gy = 0.5 + lv[1] * dv['goff'] + lv[0] * dv['gside']
        defs += ('<linearGradient id="ls" x1="' + f3(0.5 - lv[0] * 0.55) + '" y1="' + f3(0.5 - lv[1] * 0.55)
                 + '" x2="' + f3(0.5 + lv[0] * 0.55) + '" y2="' + f3(0.5 + lv[1] * 0.55) + '">'
                 '<stop offset="0" stop-color="#000" stop-opacity="' + f3(0.30 * k * dv['shade']) + '"/>'
                 '<stop offset="0.45" stop-color="#000" stop-opacity="0"/>'
                 '<stop offset="0.6" stop-color="#fff" stop-opacity="0"/>'
                 '<stop offset="1" stop-color="#fff" stop-opacity="' + f3(0.30 * k * dv['shade'])
                 + '"/></linearGradient>'
                 '<radialGradient id="lg" cx="' + f3(gx) + '" cy="' + f3(gy) + '" r="' + f3(dv['gr'])
                 + '"><stop offset="0" stop-color="#fff" stop-opacity="' + f3(0.38 * k * dv['glint']) + '"/>'
                 '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
                 '<linearGradient id="lc" x1="' + f3(0.5 - lv[0] * 0.5) + '" y1="' + f3(0.5 - lv[1] * 0.5)
                 + '" x2="' + f3(0.5 + lv[0] * 0.5) + '" y2="' + f3(0.5 + lv[1] * 0.5) + '">'
                 '<stop offset="0" stop-color="#000" stop-opacity="' + f3(0.55 * k * dv['crease']) + '"/>'
                 '<stop offset="0.5" stop-color="#000" stop-opacity="0"/>'
                 '<stop offset="0.5" stop-color="#fff" stop-opacity="0"/>'
                 '<stop offset="1" stop-color="#fff" stop-opacity="' + f3(0.55 * k * dv['crease'])
                 + '"/></linearGradient>')
        body += ('<path d="' + CAP_DISH + '" fill="url(#ls)" transform="' + CAP_DISH_T + '"/>'
                 '<path d="' + CAP_DISH + '" fill="url(#lg)" transform="' + CAP_DISH_T + '"/>'
                 '<path d="' + CAP_DISH + '" fill="none" stroke="url(#lc)" stroke-width="7" transform="'
                 + CAP_DISH_T + '"/>')
    gbody, gst = '', cap_glass_style(cfg, r)
    if not ring and gst not in ('none', 'over', 'overface'):
        gd, gbody = cap_glass_parts(w, h, mirrored, tr, gst, cap_glass_k(cfg, r), grot)
        defs += gd
    return _svg_head(w, h) + '<defs>' + defs + '</defs><g transform="' + tr + '">' + body + '</g>' + gbody + '</svg>'


# ------------------------------------------------------------------- badges
def badge_ring(dx, colour, sop, sw, w, h, r, extra=''):
    return ('<rect x="' + fmt4(0.6 + dx) + '" y="' + fmt4(0.6 + dx) + '" width="' + fmt4(w - 1.2)
            + '" height="' + fmt4(h - 1.2) + '" rx="' + fmt4(r) + '" fill="none" stroke="' + colour
            + '" stroke-opacity="' + f3(sop) + '" stroke-width="' + fmt4(sw) + '"' + extra + '/>')


def badge_octo(x0, y0, x1, y1, c):
    return ('M' + fmt4(x0 + c) + ',' + fmt4(y0) + ' L' + fmt4(x1 - c) + ',' + fmt4(y0)
            + ' L' + fmt4(x1) + ',' + fmt4(y0 + c) + ' L' + fmt4(x1) + ',' + fmt4(y1 - c)
            + ' L' + fmt4(x1 - c) + ',' + fmt4(y1) + ' L' + fmt4(x0 + c) + ',' + fmt4(y1)
            + ' L' + fmt4(x0) + ',' + fmt4(y1 - c) + ' L' + fmt4(x0) + ',' + fmt4(y0 + c) + ' Z')


def badge_svg(b, w, h, variant, bp):
    bf = bp['top'] if bp['top'] != '' else cap_hex(b['fill'], '#FFFBD9')
    bg = (bp['bottom'] if bp['bottom'] != '' else cap_mix(bf, 0.85) if b['grad'] == 'none'
          else cap_hex(b['grad'], cap_mix(bf, 0.85)))
    lip, hi = cap_mix(bg, 0.78), cap_mix(bf, 0.6, True)
    rim = bp['border'] if bp['border'] != '' else cap_mix(bg, 0.55)
    op = to_num(bp['opac']) / 100 if is_number(bp['opac']) else 1
    d = to_num(bp['depth']) / 100 if is_number(bp['depth']) else 0.6
    rad = to_num(bp['radius']) if is_number(bp['radius']) else ''
    head = ('<svg xmlns="http://www.w3.org/2000/svg" width="' + fmt4(w) + '" height="' + fmt4(h)
            + '" viewBox="0 0 ' + fmt4(w) + ' ' + fmt4(h) + '" preserveAspectRatio="none">')
    if variant in ('emboss', 'deboss') and bp.get('outline'):
        r = 1.4 if rad == '' else rad
        lo = 0.18 if variant == 'emboss' else -0.18
        return (head + '<defs><filter id="s" x="-10%" y="-10%" width="120%" height="140%">'
                '<feGaussianBlur stdDeviation="0.12"/></filter></defs><g opacity="' + f3(op) + '">'
                + badge_ring(lo, '#000', 0.6 * d, 0.45, w, h, r, ' filter="url(#s)"')
                + badge_ring(-lo, '#fff', 0.85 * d, 0.35, w, h, r)
                + (badge_ring(0, bp['border'], 0.6, 0.3, w, h, r) if bp['border'] != '' else '') + '</g></svg>')
    if variant in ('printed', 'emboss', 'deboss'):
        return head + '</svg>'
    rs = lambda dflt: dflt if rad == '' else rad
    if variant == 'inlay':
        r = rs(1.2)
        defs = ('<linearGradient id="f" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + bf
                + '"/><stop offset="1" stop-color="' + bg + '"/></linearGradient>'
                '<linearGradient id="i" x1="0" y1="0" x2="1" y2="1">'
                '<stop offset="0" stop-color="#000" stop-opacity="' + f3(0.45 * d) + '"/>'
                '<stop offset="0.35" stop-color="#000" stop-opacity="0"/>'
                '<stop offset="0.7" stop-color="#fff" stop-opacity="0"/>'
                '<stop offset="1" stop-color="#fff" stop-opacity="' + f3(0.5 * d) + '"/></linearGradient>')
        body = ('<g opacity="' + f3(0.85 * op) + '"><rect x="0.2" y="0.2" width="' + fmt4(w - 0.4)
                + '" height="' + fmt4(h - 0.4) + '" rx="' + fmt4(r) + '" fill="url(#f)"/>'
                '<rect x="0.45" y="0.45" width="' + fmt4(w - 0.9) + '" height="' + fmt4(h - 0.9) + '" rx="'
                + fmt4(max(0, r - 0.25)) + '" fill="none" stroke="' + (rim if bp['border'] != '' else 'url(#i)')
                + '" stroke-width="0.9"/></g>')
    elif variant == 'decal':
        r = rs(1.2)
        defs = ('<linearGradient id="f" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="'
                + cap_mix(bf, 0.25, True) + '"/><stop offset="1" stop-color="' + bg + '"/></linearGradient>'
                '<filter id="s" x="-20%" y="-20%" width="140%" height="160%"><feGaussianBlur stdDeviation="'
                + f3(0.35 * d + 0.05) + '"/></filter>')
        body = ('<g opacity="' + f3(op) + '"><rect x="0.6" y="0.9" width="' + fmt4(w - 1.1) + '" height="'
                + fmt4(h - 1.3) + '" rx="' + fmt4(r) + '" fill="#000" opacity="' + f3(0.45 * d)
                + '" filter="url(#s)"/>'
                '<rect x="0.3" y="0.3" width="' + fmt4(w - 1.0) + '" height="' + fmt4(h - 1.2) + '" rx="' + fmt4(r)
                + '" fill="url(#f)" stroke="' + (rim if bp['border'] != '' else cap_mix(bg, 0.6))
                + '" stroke-width="0.22"/>'
                '<rect x="0.9" y="0.6" width="' + fmt4(w - 2.2) + '" height="0.35" rx="0.17" fill="#fff" '
                'opacity="0.6"/></g>')
    elif variant == 'raised':
        r = rs(1.4)
        defs = ('<linearGradient id="f" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + bf
                + '"/><stop offset="1" stop-color="' + bg + '"/></linearGradient>'
                '<linearGradient id="b" x1="0" y1="0" x2="1" y2="1">'
                '<stop offset="0" stop-color="#fff" stop-opacity="' + f3(0.75 * d) + '"/>'
                '<stop offset="0.45" stop-color="#fff" stop-opacity="0"/>'
                '<stop offset="0.55" stop-color="#000" stop-opacity="0"/>'
                '<stop offset="1" stop-color="#000" stop-opacity="' + f3(0.55 * d) + '"/></linearGradient>'
                '<filter id="s" x="-20%" y="-20%" width="140%" height="160%"><feGaussianBlur stdDeviation="'
                + f3(0.3 * d + 0.05) + '"/></filter>')
        body = ('<g opacity="' + f3(op) + '"><rect x="0.7" y="0.8" width="' + fmt4(w - 1.2) + '" height="'
                + fmt4(h - 1.2) + '" rx="' + fmt4(r) + '" fill="#000" opacity="' + f3(0.35 * d)
                + '" filter="url(#s)"/>'
                '<rect x="0.35" y="0.35" width="' + fmt4(w - 1.0) + '" height="' + fmt4(h - 1.0) + '" rx="'
                + fmt4(r) + '" fill="url(#f)" fill-opacity="0.4"/>'
                '<rect x="0.6" y="0.6" width="' + fmt4(w - 1.5) + '" height="' + fmt4(h - 1.5) + '" rx="'
                + fmt4(max(0, r - 0.25)) + '" fill="none" stroke="' + (rim if bp['border'] != '' else 'url(#b)')
                + '" stroke-width="0.7"/></g>')
    elif variant == 'inset':
        defs = ('<linearGradient id="e" x1="0" y1="0" x2="0" y2="1">'
                '<stop offset="0" stop-color="' + cap_mix(bg, 0.92) + '"/>'
                '<stop offset="1" stop-color="' + cap_mix(bg, 0.62) + '"/></linearGradient>'
                '<radialGradient id="d" cx="0.4" cy="0.25" r="0.9">'
                '<stop offset="0" stop-color="' + hi + '"/><stop offset="0.55" stop-color="' + bf + '"/>'
                '<stop offset="1" stop-color="' + bg + '"/></radialGradient>')
        r = rs(2.2)
        body = ('<g opacity="' + f3(op) + '"><rect x="0.3" y="0.3" width="' + fmt4(w - 0.6) + '" height="'
                + fmt4(h - 0.6) + '" rx="' + fmt4(r) + '" fill="url(#e)" stroke="' + rim + '" stroke-width="0.35"/>'
                '<rect x="1.1" y="0.8" width="' + fmt4(w - 2.2) + '" height="' + fmt4(h - 2.4)
                + '" rx="' + fmt4(max(0, r - 0.7)) + '" fill="url(#d)"/></g>')
    elif variant == 'tag':
        c = min(2.2, h * 0.22) if rad == '' else rad
        defs = ('<linearGradient id="f" x1="0" y1="0" x2="0" y2="1">'
                '<stop offset="0" stop-color="' + hi + '"/><stop offset="0.45" stop-color="' + bf + '"/>'
                '<stop offset="1" stop-color="' + bg + '"/></linearGradient>')
        body = ('<g opacity="' + f3(op) + '"><path d="' + badge_octo(0.3, 0.3, w - 0.3, h - 0.3, c) + '" fill="'
                + lip + '" stroke="' + rim + '" stroke-width="0.4"/>'
                '<path d="' + badge_octo(0.75, 0.6, w - 0.75, h - 1.3, max(0, c - 0.35)) + '" fill="url(#f)"/></g>')
    else:
        r = rs(1.6)
        defs = ('<linearGradient id="f" x1="0" y1="0" x2="0" y2="1">'
                '<stop offset="0" stop-color="' + bf + '"/><stop offset="1" stop-color="' + bg + '"/></linearGradient>')
        body = ('<g opacity="' + f3(op) + '"><rect x="0.3" y="0.3" width="' + fmt4(w - 0.6) + '" height="'
                + fmt4(h - 0.6) + '" rx="' + fmt4(r) + '" fill="' + lip + '" stroke="' + rim
                + '" stroke-width="0.4"/>'
                '<rect x="0.7" y="0.6" width="' + fmt4(w - 1.4) + '" height="' + fmt4(h - 1.9)
                + '" rx="' + fmt4(max(0, r - 0.4)) + '" fill="url(#f)"/>'
                '<rect x="1.4" y="0.9" width="' + fmt4(w - 2.8)
                + '" height="0.5" rx="0.25" fill="#fff" fill-opacity="0.75"/></g>')
    return head + '<defs>' + defs + '</defs>' + body + '</svg>'


# --------------------------------------------------------------- page cells
def svg_uri(svg):
    return 'data:image/svg+xml,' + base64.b64encode(svg.encode('utf-8')).decode('ascii')


def cap_image_style(uri, rot='', opac='100'):
    st = 'shape=image;imageAspect=0;'
    if is_number(rot) and not same_num(rot, 0):
        st += 'rotation=' + str(rot) + ';'
    if is_number(opac) and to_num(opac) < 100:
        st += 'opacity=' + str(opac) + ';'
    return st + 'image=' + uri + ';'


def cap_insert_before(node, cid, style):
    from lxml import etree
    c = etree.Element('mxCell')
    c.set('id', cid)
    c.set('parent', node.get('parent'))
    c.set('style', style)
    c.set('value', '')
    c.set('vertex', '1')
    g = node.find('mxGeometry')
    if g is not None:
        gc = copy.deepcopy(g)
        gc.tail = None
        c.append(gc)
    node.addprevious(c)
    return c


def cap_clear_paint(st):
    st = M.style_del(M.style_del(st, 'gradientColor'), 'gradientDirection')
    return M.style_set(M.style_set(M.style_set(st, 'fillColor', 'none'), 'glass', '0'), 'strokeColor', 'none')


def cap_face_rect(cfg, st, px, py, pw, ph, mirrored, margin, face=None):
    fc = face if face is not None else (st.face() if cfg.key_style == 'render' else CAP_FACE)
    x0, x1 = fc[0], fc[2]
    if mirrored:
        x0, x1 = 25 - x1, 25 - x0
    sx, sy = pw / 25, ph / 25
    return [px + (x0 + margin) * sx, py + (fc[1] + margin) * sy, px + (x1 - margin) * sx, py + (fc[3] - margin) * sy]


def cap_fit_move(a, l, lo, hi):
    if l >= hi - lo:
        return [lo, hi - lo]
    return [min(max(a, lo), hi - l), l]


def badge_fit(x, y, w, h, f, mode):
    if mode == 'move':
        xs, ys = cap_fit_move(x, w, f[0], f[2]), cap_fit_move(y, h, f[1], f[3])
        return [xs[0], ys[0], xs[1], ys[1]]
    x0, y0, x1, y1 = max(x, f[0]), max(y, f[1]), min(x + w, f[2]), min(y + h, f[3])
    if x1 - x0 < 1 or y1 - y0 < 1:
        return [x, y, w, h]
    return [x0, y0, x1 - x0, y1 - y0]


def _badge_sized(g):
    return g is not None and any(abs(g['w'] - a) < 0.01 and abs(g['h'] - b) < 0.01 for a, b in BADGE_SIZES)


def _not_badge_style(st):
    return re.search(r'(^|;)group(;|$)', st) or M.style_get(st, 'shape', '') == 'image'


def key_badges(doc, key):
    return [ch for ch in doc.children(key.get('id'))
            if not _not_badge_style(ch.get('style') or '') and _badge_sized(M.geo(ch))]


def loose_badges(doc, gid, keys):
    out = {}
    for ch in doc.children(gid):
        st = ch.get('style') or ''
        if _not_badge_style(st) or M.style_get(st, 'fillColor', 'none') in ('none', ''):
            continue
        bg = M.geo(ch)
        if not _badge_sized(bg):
            continue
        cx, cy = bg['x'] + bg['w'] / 2, bg['y'] + bg['h'] / 2
        for key in keys:
            kg = M.geo(key)
            if kg['x'] <= cx <= kg['x'] + kg['w'] and kg['y'] <= cy <= kg['y'] + kg['h']:
                out.setdefault(key.get('id'), []).append(ch)
                break
    return out


def cap_legend_extras(out, src, key, kid, pid, pg, tf, fdx, fdy, rot):
    """CapLegendExtras (.163): a group key's other legend cells (images, text cells; not its
    label pid, badges or groups) scaled by tf about the label's middle and moved by the face
    offset, turned by the label's rotation."""
    from pages import cap_scale_text
    if abs(tf - 1) <= 0.001 and abs(fdx) < 0.01 and abs(fdy) < 0.01:
        return
    skip = {bd.get('id') for bd in key_badges(src, key)}
    a = to_num(rot) * 0.017453292519943295 if is_number(rot) else 0
    ox, oy = fdx * math.cos(a) - fdy * math.sin(a), fdx * math.sin(a) + fdy * math.cos(a)
    pcx = (pg['x'] or 0) + pg['w'] / 2
    pcy = (pg['y'] or 0) + pg['h'] / 2
    for sc in src.children(kid):             # the source key's own cells (not the export's -cap)
        cid = sc.get('id')
        if cid == pid or cid in skip or re.search(r'(^|;)group(;|$)', sc.get('style') or ''):
            continue
        ch = _out_cell(out, cid)
        if ch is None:
            continue
        g = ch.find('mxGeometry')
        if g is None:
            continue
        def num(k):
            v = g.get(k)
            return to_num(v) if is_number(v) else 0
        x, y, w, h = num('x'), num('y'), num('width'), num('height')
        cx, cy = pcx + (x + w / 2 - pcx) * tf + ox, pcy + (y + h / 2 - pcy) * tf + oy
        w, h = w * tf, h * tf
        g.set('x', fmt4(cx - w / 2)); g.set('y', fmt4(cy - h / 2))
        g.set('width', fmt4(w)); g.set('height', fmt4(h))
        if abs(tf - 1) > 0.001 and ch.get('value'):
            cap_scale_text(ch, tf)


def cap_text_move(cell, dx, dy):
    from pages import style_num
    st = cell.get('style') or ''
    if dx != 0:
        st = M.style_set(M.style_set(st, 'spacingLeft', fmt4(style_num(st, 'spacingLeft', 0) + dx)),
                         'spacingRight', fmt4(style_num(st, 'spacingRight', 0) - dx))
    if dy != 0:
        st = M.style_set(M.style_set(st, 'spacingTop', fmt4(style_num(st, 'spacingTop', 0) + dy)),
                         'spacingBottom', fmt4(style_num(st, 'spacingBottom', 0) - dy))
    cell.set('style', st)


def cap_emboss_text(cell, raised, bp):
    d = to_num(bp['depth']) / 100 if is_number(bp['depth']) else 0.6
    hi, sh = 'rgba(255,255,255,' + f3(0.85 * d) + ')', 'rgba(0,0,0,' + f3(0.6 * d) + ')'
    ts = ('-0.3px -0.3px 0.1px ' + hi + ', 0.35px 0.35px 0.25px ' + sh if raised
          else '0.3px 0.3px 0.1px ' + hi + ', -0.3px -0.3px 0.2px ' + sh)
    cell.set('value', '<div style="text-shadow: ' + ts + '">' + (cell.get('value') or '') + '</div>')
    if bp['top'] != '':
        cell.set('style', M.style_set(cell.get('style') or '', 'fontColor', bp['top']))


def _out_cell(out, cid):
    r = out.xpath('//mxCell[@id=' + M.q(cid) + ']')
    return r[0] if r else None


def cap_badge(cfg, out, bd, face, badge, mode):
    from pages import cap_scale_text
    bc = _out_cell(out, bd.get('id'))
    if bc is None:
        return
    tf = to_num(cfg.cap_badge_text) / 100
    if mode in ('shrink', 'move', 'scale'):
        bg = M.geo(bc)
        fit = badge_fit(bg['x'], bg['y'], bg['w'], bg['h'], face, 'shrink' if mode == 'scale' else mode)
        if mode == 'scale' and bg['w'] > 0 and bg['h'] > 0:
            tf *= min(fit[2] / bg['w'], fit[3] / bg['h'])
        gn = bc.find('mxGeometry')
        gn.set('x', fmt4(fit[0]))
        gn.set('y', fmt4(fit[1]))
        gn.set('width', fmt4(fit[2]))
        gn.set('height', fmt4(fit[3]))
    if abs(tf - 1) > 0.001:
        cap_scale_text(bc, tf)
    if cfg.cap_badge in ('emboss', 'deboss'):
        cap_emboss_text(bc, cfg.cap_badge == 'emboss', LY.cap_badge_params(cfg))
    bst = bc.get('style') or ''
    bg = M.geo(bc)
    bc.set('style', cap_clear_paint(bst))
    cap_insert_before(bc, bd.get('id') + '-plate',
                      cap_image_style(svg_uri(badge_svg(badge, bg['w'], bg['h'], cfg.cap_badge,
                                                        LY.cap_badge_params(cfg))),
                                      M.style_get(bst, 'rotation', '')))


def cap_keys(cfg, st, src, out, gid, centre_x):
    """CapKeys: each key with a role gets its cap image (and rim / glass over everything),
    its paint cleared, its text fitted to the cap's face, its badges plated."""
    from pages import cap_scale_text, make_cell
    roles = LY.load_cap_roles(cfg, src, [])[0]
    badge = LY.load_badge(src)
    keys = M.index_keys(src, gid)
    loose = loose_badges(src, gid, keys)
    rims = []
    render = cfg.key_style == 'render'
    for ki, key in enumerate(keys):
        if M.eff_fill(src, key) == 'NONE':
            continue
        rn = M.style_get(key.get('style'), 'keyRole', '')
        if rn == '' or rn not in roles:
            continue
        r = roles[rn]
        kg0 = M.geo(key)
        shp = (LY.render_shape_of(cfg, r, LY.render_pos_shape(cfg, M.pos_name(ki), kg0 is not None
                                                                and kg0['h'] > kg0['w'] * 1.2)) if render else '')
        tf = st.text_factor(shp) if render else 1
        rface = st.face(shp) if render else None
        kid = key.get('id')
        pid = M.key_paint_cell(src, key).get('id')
        pc = _out_cell(out, pid)
        if pc is None:
            continue
        sty = pc.get('style') or ''
        rot = M.style_get(sty, 'rotation', '')
        pc.set('style', cap_clear_paint(sty))
        is_child = pid != kid
        wc = _out_cell(out, kid) if is_child else None
        if wc is not None:
            wc.set('style', cap_clear_paint(wc.get('style') or ''))
        if abs(tf - 1) > 0.001:
            if pc.get('value'):
                cap_scale_text(pc, tf)
            if wc is not None and wc.get('value'):
                cap_scale_text(wc, tf)
        kg, pg = M.geo(key), M.geo(pc)
        mir = kg is not None and kg['x'] + kg['w'] / 2 > centre_x
        if render and pg is not None:
            fo = st.face_offset(shp)
            fdx, fdy = (-fo[0] if mir else fo[0]) * pg['w'] / 25, fo[1] * pg['h'] / 25
            if abs(fdx) >= 0.01 or abs(fdy) >= 0.01:
                if pc.get('value'):
                    cap_text_move(pc, fdx, fdy)
                if wc is not None and wc.get('value'):
                    cap_text_move(wc, fdx, fdy)
            if is_child:                         # .163: the legend's other parts with it
                cap_legend_extras(out, src, key, kid, pid, pg, tf, fdx, fdy, rot)
        grot = to_num(rot) if is_number(rot) else 0
        if not LY.cap_transparent(r):
            cap_insert_before(pc, pid + '-cap', cap_image_style(svg_uri(cap_svg(
                cfg, st, r, pg['w'], pg['h'], mir, False, kg['x'] + kg['w'] / 2, kg['y'] + kg['h'] / 2, '', shp, grot)),
                rot, r['opac']))
            bx0 = kg['x'] + (pg['x'] if is_child else 0)
            by0 = kg['y'] + (pg['y'] if is_child else 0)
            if cfg.cap_edge_top:
                rims.append([pid + '-rim', cap_image_style(svg_uri(cap_svg(cfg, st, r, pg['w'], pg['h'], mir, True,
                                                                           '', '', '', shp)), rot, r['opac']),
                             bx0, by0, pg['w'], pg['h']])
            if not render and re.fullmatch(r'over(face)?', cap_glass_style(cfg, r)):
                rims.append([pid + '-glass', cap_image_style(svg_uri(cap_glass_svg(
                    pg['w'], pg['h'], mir, cap_glass_k(cfg, r), cap_glass_style(cfg, r), grot)), rot, r['opac']),
                    bx0, by0, pg['w'], pg['h']])
        if cfg.cap_badge == 'current' or badge is None:
            continue
        bx, by = (pg['x'], pg['y']) if is_child else (0, 0)
        mode = 'off' if (is_number(rot) and not same_num(rot, 0)) else cfg.cap_badge_fit
        for bd in key_badges(src, key):
            cap_badge(cfg, out, bd, cap_face_rect(cfg, st, bx, by, pg['w'], pg['h'], mir, cfg.cap_badge_margin,
                                                  rface), badge, mode)
        for bd in loose.get(kid, []):
            cap_badge(cfg, out, bd, cap_face_rect(cfg, st, kg['x'] + bx, kg['y'] + by, pg['w'], pg['h'], mir,
                                                  cfg.cap_badge_margin, rface), badge, mode)
    if rims:
        root = out.find('.//root')
        for rm in rims:
            root.append(make_cell(rm[0], gid, rm[1], '', fmt4(rm[2]), fmt4(rm[3]), fmt4(rm[4]), fmt4(rm[5])))


def cap_ring_cell(cfg, st, role, cell, g, p, cap_mid):
    """AddForeground's ring for a key of a transparent role."""
    from pages import make_cell
    tall = g['h'] > g['w'] * 1.2
    shp = LY.render_shape_of(cfg, role, LY.render_pos_shape(cfg, M.pos_name(p), tall))
    return make_cell(f'fg-r{p}', 'fg', cap_image_style(svg_uri(cap_svg(
        cfg, st, role, g['w'], g['h'], g['x'] + g['w'] / 2 > cap_mid, True, '', '', '', shp)),
        M.style_get(cell.get('style'), 'rotation', '')), '', g['x'], g['y'], g['w'], g['h'])


def cap_split_page(d, part):
    """CapSplitPage: the page cut to its caps ('c'), text ('t') or rims ('r') for Legend 3D."""
    for c in list(d.xpath("//mxCell[@vertex='1']")):
        cid = c.get('id') or ''
        kind = ('frame' if cid == 'frame' else 'rim' if re.search(r'-(rim|glass)$', cid)
                else 'cap' if cid.endswith('-cap') else 'plate' if cid.endswith('-plate') else '')
        sty = c.get('style') or ''
        if part == 'c':
            if kind in ('rim', 'plate') or (kind == '' and M.style_get(sty, 'shape', '') == 'image'):
                c.getparent().remove(c)
            else:
                if c.get('value'):
                    c.set('value', '')
                if kind == '' and re.search(r'(?i)(^|;)image=', sty):
                    c.set('style', M.style_del(sty, 'image'))
        elif part == 't':
            if kind in ('rim', 'cap'):
                c.getparent().remove(c)
            elif kind == '':
                c.set('style', cap_clear_paint(sty))
        else:
            if kind in ('rim', 'frame'):
                continue
            if re.search(r'(^|;)group(;|$)', sty):
                c.set('style', cap_clear_paint(sty))
                c.set('value', '')
            else:
                c.getparent().remove(c)
