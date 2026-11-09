"""The Render shading's inputs from the ported model / layout code (RenderItems, RenderAz,
RenderEdge, the legend chips' items) and RenderShade on top of render_shade's pixel work.

    items = render_items(cfg, doc, L, 'caps')      # the opaque caps of layer L
    out = shade_raw(cfg, shapes, raw, items)        # RenderShade: None if raw is not the frame's size

The layout must be applied first (layout.target_set), as LayApply does in the script.
"""
import model as M
import layout as LY
import capkeys as CK
import render_shade as RS
from util import is_number, to_num, round_ahk


class Params:
    """The globals RenderDrawItems reads: RENDER_LIGHT, RENDER_SHADE / HILITE (as factors),
    RENDER_INSET."""
    def __init__(self, cfg):
        self.light = cfg.render_light
        self.kS = to_num(cfg.render_shade) / 100
        self.kH = to_num(cfg.render_hilite) / 100
        self.inset = to_num(cfg.render_inset)


def render_az(cfg, cx, cy, mirrored):
    """RenderAz: the light's direction in the overlay's own image, rounded to 5 degrees.
    cx = cy = '' (the legend) gives CapDishVary's plain base angle."""
    ang = CK.cap_dish_vary(cfg, cx, cy, mirrored)['ang']
    az = ang if mirrored else 180 - ang
    return round_ahk(az / 5) * 5


def render_edge(cfg, r):
    """RenderEdge: the flank colour of role r's cap, '' = the dish's paint all over."""
    return LY.render_look(cfg, r)['edgeOwn']


def ring_item(cfg, r, x, y, w, h, rot, mir, az, shape):
    lk = LY.render_look(cfg, r)
    return dict(x=x, y=y, w=w, h=h, rot=rot, mir=mir, az=az, opac=100, ring=True,
                edge=lk['edgeOwn'], fill=lk['fill'], grad=lk['grad'], dir=lk['dir'], shape=shape)


def render_items(cfg, doc, L, which='caps'):
    """RenderItems(src, L, which): "caps" = every painted key with an existing, not transparent
    role (its paint box); "rings" = every transparent role's key with a border (its key box)."""
    if which == 'rings' and not cfg.render_ring:
        return []
    roles = LY.load_cap_roles(cfg, doc, [])[0]
    centre_x = M.keys_mid_x(doc, L['node'])     # .186
    out = []
    for ki, key in enumerate(M.index_keys(doc, L['id'])):
        if M.eff_fill(doc, key) == 'NONE':
            continue
        rn = M.style_get(key.get('style'), 'keyRole', '')
        if rn == '' or rn not in roles:
            continue
        r = roles[rn]
        trans = LY.cap_transparent(r)
        if (which == 'rings') != trans:
            continue
        pc = M.key_paint_cell(doc, key)
        kg, pg = M.geo(key), M.geo(pc)
        if kg is None or pg is None:
            continue
        mir = kg['x'] + kg['w'] / 2 > centre_x
        az = render_az(cfg, kg['x'] + kg['w'] / 2, kg['y'] + kg['h'] / 2, mir)
        kpos = M.pos_name(ki)
        shp = LY.render_shape_of(cfg, r, LY.render_pos_shape(cfg, kpos, kg['h'] > kg['w'] * 1.2))
        if trans:
            if LY._no_stroke(pc.get('style')):
                continue
            rot = M.style_get(key.get('style'), 'rotation', '')
            out.append(ring_item(cfg, r, kg['x'], kg['y'], kg['w'], kg['h'],
                                 to_num(rot) if is_number(rot) else 0, mir, az, shp))
        else:
            is_child = pc is not key
            pm = cfg.cap_pos.get(kpos)
            bear = pm['bear'] if (pm and shp not in ('cover', 'bezel')) else ''
            rot = M.style_get(pc.get('style'), 'rotation', '')
            op = r['opac']
            out.append(dict(x=kg['x'] + (pg['x'] if is_child else 0), y=kg['y'] + (pg['y'] if is_child else 0),
                            w=pg['w'], h=pg['h'], rot=to_num(rot) if is_number(rot) else 0, mir=mir, az=az,
                            opac=to_num(op) if is_number(op) else 100, ring=False, edge='', shape=shp,
                            bear=bear, bplace=pm['place'] if pm else 'lower', pos=kpos))
    return out


def legend_item(cfg, r, x, y, w, h, rot):
    """One of CapLegend's chips as a RenderShade item: unmirrored, lit from the base angle, a
    ring when its role is transparent."""
    shp = LY.render_shape_of(cfg, r)
    az = render_az(cfg, '', '', False)
    if LY.cap_transparent(r):
        return ring_item(cfg, r, x, y, w, h, rot, False, az, shp)
    lk = LY.render_look(cfg, r)
    return dict(x=x, y=y, w=w, h=h, rot=rot, mir=False, az=az, opac=100, ring=False,
                edge=lk['edgeOwn'], fill=lk['fill'], grad=lk['grad'], dir=lk['dir'], shape=shp)


def shade_raw(cfg, shapes, raw, items):
    """RenderShade on a raw (uint8 RGBA array): the shaded copy, the raw itself when there is
    nothing to shade, or None when the raw is not the size the page frame promises."""
    if not items:
        return raw
    return RS.render_shade(raw, items, Params(cfg), shapes, cfg.scale)
