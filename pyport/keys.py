"""Legend 3D's key list: ShadowKeys(src, L, false, true) = images.shadow_keys(with_warp=True),
each key with its 13 x 13 grid (ConformGrid / ConformGridSrc) from the script's CAP_WARP
(render_shade.Script.cap_warp): 169 (du, dv), or None for a shape with no grid."""
import re
import render_shade as RS


def grid(txt, turn=0, flip=False):
    g = [tuple(int(v) / 1000 for v in p.split(',')) for p in txt.split()]
    assert len(g) == 169
    if turn == 180:
        g = [(-g[(12 - i) * 13 + 12 - j][0], -g[(12 - i) * 13 + 12 - j][1]) for i in range(13) for j in range(13)]
    elif turn == 90:
        g = [(-g[(12 - j) * 13 + i][1], g[(12 - j) * 13 + i][0]) for i in range(13) for j in range(13)]
    elif turn == 270:
        g = [(g[j * 13 + 12 - i][1], -g[j * 13 + 12 - i][0]) for i in range(13) for j in range(13)]
    if flip:
        g = [(-g[i * 13 + 12 - j][0], g[i * 13 + 12 - j][1]) for i in range(13) for j in range(13)]
    return g


def conform_grid(shapes, shape, flip=False, tilt=False):
    """ConformGrid: the shape's grid, turned and flipped; None for none.  tilt=True: its
    tilt-only twin (.162: CAP_WARPT / the file's warpt=), None when there is none."""
    cw = shapes.sc.cap_warpt if tilt else shapes.sc.cap_warp
    sk = shapes.key(shape)
    if not sk.startswith('m:'):
        txt, turn = (cw.get('real', '') if sk in ('real', 'wide') else ''), 0
    else:
        src = shapes.src(sk); parts = sk.split(':')
        if src.get('warp'):                  # the model file's own grid wins (ConformGridSrc)
            txt = src.get('warpt', '') if tilt else src['warp']
            return grid(txt, src['turn'], flip) if txt else None
        mf = RS.capmodel(shapes.capdir, parts[1])
        sec = ''
        if mf:
            long = 'L' in parts[2:]; wide = 'w' in parts[2:]
            if long:
                sec = 'longwide' if (wide and 'longwide' in mf['secs']) else 'long' if 'long' in mf['secs'] else ''
            if sec == '' and '1u' in mf['secs']:
                sec = '1u'
        if sec == '':
            txt, turn = cw.get('real', ''), 0
        else:
            mk = re.sub(r'_s\d+$', '', parts[1].lower())
            txt, turn = cw.get(mk + '|' + ('long' if sec == 'longwide' else sec), ''), src['turn']
    return grid(txt, turn, flip) if txt else None


_ts_cache = {}
def tilt_scale(shapes, shape):
    """ConformTiltScale (.162): how much the shape's tilt-only twin foreshortens across (x, y)
    near the middle, turned as the shape is; 1 without a twin, and 1 when under 1 %."""
    key = (id(shapes), shape)
    if key in _ts_cache:
        return _ts_cache[key]
    res = (1, 1)
    g = conform_grid(shapes, shape or 'real', False, tilt=True)
    if g:
        sx = ((0.5 + g[6 * 13 + 9][0]) - (-0.5 + g[6 * 13 + 3][0])) / 1.0
        sy = ((0.5 + g[9 * 13 + 6][1]) - (-0.5 + g[3 * 13 + 6][1])) / 1.0
        res = (1 if (sx >= 0.99 or sx <= 0.3) else sx, 1 if (sy >= 0.99 or sy <= 0.3) else sy)
    _ts_cache[key] = res
    return res


def warp_keys(cfg, doc, L, shapes):
    """The keys CapWarpText bends: x, y, w, h, rot, pos, shape, flip, grid."""
    import images as IM
    ks = IM.shadow_keys(cfg, doc, L, shapes, with_warp=True)
    cache = {}
    for k in ks:
        ck = (k['shape'], k['flip'])
        if ck not in cache:
            g = conform_grid(shapes, k['shape'], k['flip'])
            cache[ck] = (g, conform_grid(shapes, k['shape'], k['flip'], tilt=True) if g else None)
        k['grid'], k['tgrid'] = cache[ck]
    return ks
