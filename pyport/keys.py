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


def conform_grid(shapes, shape, flip=False):
    """ConformGrid: the shape's grid, turned and flipped; None for none."""
    cw = shapes.sc.cap_warp
    sk = shapes.key(shape)
    if not sk.startswith('m:'):
        txt, turn = (cw.get('real', '') if sk in ('real', 'wide') else ''), 0
    else:
        src = shapes.src(sk); parts = sk.split(':')
        if src.get('warp'):                  # the model file's own grid wins (ConformGridSrc)
            return grid(src['warp'], src['turn'], flip)
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


def warp_keys(cfg, doc, L, shapes):
    """The keys CapWarpText bends: x, y, w, h, rot, pos, shape, flip, grid."""
    import images as IM
    ks = IM.shadow_keys(cfg, doc, L, shapes, with_warp=True)
    cache = {}
    for k in ks:
        ck = (k['shape'], k['flip'])
        if ck not in cache:
            cache[ck] = conform_grid(shapes, k['shape'], k['flip'])
        k['grid'] = cache[ck]
    return ks
