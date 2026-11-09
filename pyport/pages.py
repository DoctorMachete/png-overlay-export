"""The pages handed to draw.io: BuildPageDoc / BuildPage of the .148 script.
Done: the page skeleton, the foreground (AddForeground: key borders, combo
bubbles, combo lists), the title pair (IsCentreCell, AlignTitlePair,
SetHtmlText, MirrorTitle) and NormaliseFonts.  Not yet: the background branch
(CopySubtree, StripKeyStrokes, CapKeys, KeyTextShift), CapSvg rings for
transparent roles in the SVG-caps style, mirrored layers, the legend.

Numbers: AHK passes floats to MSXML's setAttribute, which converts them as COM
does (15 significant digits, no trailing '.0'): vstr()."""
import copy, math, re
import numpy as np
from lxml import etree
import model as M
import layout as LY
import combos as CB
from util import fmt4, is_number, to_num, ahk_sorted, first_num

PAGE_W, PAGE_H, MARGIN = 500, 240, 13
GRP_W, GRP_H, FRAME_PAD = M.GRP_W, M.GRP_H, M.FRAME_PAD
BORDER_STYLE = ("whiteSpace=wrap;html=1;aspect=fixed;rounded=1;arcSize=20;glass=1;"
                "shadow=0;sketch=0;fillColor=none;align=center;verticalAlign=middle;"
                "fontFamily=Helvetica;fontSize=9;spacing=0;strokeColor=")
COMBO_ARROW = '⇒'


def vstr(x):
    """A number as MSXML writes a VT_R8 / VT_I4 attribute (VarBstrFromR8: 15 significant digits)."""
    if isinstance(x, bool):
        return '-1' if x else '0'
    if isinstance(x, int):
        return str(x)
    s = '%.15G' % x
    if 'E' in s:
        m, e = s.split('E')
        s = m + 'E' + e[0] + e[1:].lstrip('0').rjust(2, '0')
    return s


def _attr(v):
    return v if isinstance(v, str) else vstr(v)


def import_node(el):
    """out.importNode(el, true): a deep copy without the source's trailing whitespace."""
    c = copy.deepcopy(el)
    c.tail = None
    return c


def make_cell(cid, parent, style, value, x, y, w, h, rot=''):
    c = etree.Element('mxCell')
    c.set('id', cid)
    c.set('parent', parent)
    c.set('style', style if rot == '' else style + ';rotation=' + rot)
    c.set('value', value)
    c.set('vertex', '1')
    g = etree.SubElement(c, 'mxGeometry')
    for k, v in (('x', x), ('y', y), ('width', w), ('height', h)):
        g.set(k, _attr(v))
    g.set('as', 'geometry')
    return c


def new_page():
    xml = ('<mxfile host="zmk_layers" pages="1"><diagram name="p" id="p">'
           '<mxGraphModel dx="1085" dy="671" grid="0" gridSize="10" guides="1" '
           'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
           f'pageWidth="{PAGE_W}" pageHeight="{PAGE_H}" math="0" shadow="0">'
           '<root><mxCell id="0"/><mxCell id="1" parent="0"/></root>'
           '</mxGraphModel></diagram></mxfile>')
    out = etree.fromstring(xml)
    return out, out.find('.//root')


# ---------------------------------------------------------------- the titles
def is_centre_cell(cell, centre_x):
    g = M.geo(cell)
    return g is not None and not M.is_key_size(g) and M.centre_crosses_x(g, centre_x)


def set_html_text(html_val, new_text):
    esc = new_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    parts, last = [], 0
    for m in re.finditer(r'<[^>]+>', html_val):
        if m.start() > last:
            parts.append([False, html_val[last:m.start()]])
        parts.append([True, m.group(0)])
        last = m.end()
    if last < len(html_val):
        parts.append([False, html_val[last:]])
    target = next((i for i, p in enumerate(parts) if not p[0] and p[1].strip() != ''), None)
    if target is not None:
        for i, p in enumerate(parts):
            if not p[0] and p[1].strip() != '':
                p[1] = esc if i == target else ''
        return ''.join(p[1] for p in parts)
    last_close = None
    for i, p in enumerate(parts):
        if p[0] and p[1].startswith('</'):
            last_close = i
    if last_close is not None:
        return ''.join((esc if i == last_close else '') + p[1] for i, p in enumerate(parts))
    return esc


def align_title_pair(cells, L, warn):
    if len(cells) != 2:
        return
    a, b = cells
    ga, gb = M.geo(a), M.geo(b)
    if ga is None or gb is None:
        return
    r = M.round_ahk
    if r(ga['w']) != r(gb['w']) or r(ga['h']) != r(gb['h']):
        warn.append(f"layer {L['idx']} ({L['name']}): the two title cells differ "
                    "in size; not aligning them for render.")
        return
    if r(ga['x']) == r(gb['x']) and r(ga['y']) == r(gb['y']):
        return
    bottom = a if ga['y'] >= gb['y'] else b
    top = b if bottom is a else a
    truth = M.plain_text(bottom)
    if M.plain_text(top) != truth:
        top.set('value', set_html_text(top.get('value') or '', truth))
    bg = M.geo(bottom)
    tg = top.find('mxGeometry')
    tg.set('x', vstr(bg['x']))
    tg.set('y', vstr(bg['y']))


def mirror_title(t):
    out = []
    for w in reversed(re.sub(r'\s+', ' ', t.strip()).split(' ')):
        m = re.fullmatch(r'([^\W_]+)([\W_]+)', w) or re.fullmatch(r'([\W_]+)([^\W_]+)', w)
        if m:
            w = m.group(2) + m.group(1)
        out.append(w)
    return ' '.join(out)


# ------------------------------------------------------------- combo bubbles
def norm_text(s):
    return ''.join(sorted(s.replace(' ', '').replace(' ', '')))


def combo_label_of(c):
    d = (c.get('description') or '').strip()
    if '~~~' in d:
        d = d[:d.index('~~~')].strip()
    return d


def find_combo_element(cfg, src, spec):
    n = src.xpath('//mxCell[@id=' + M.q(spec) + ']')
    if n:
        return n[0]
    want = norm_text(spec)
    for c in src.xpath('//diagram[@name=' + M.q(cfg.combo_tab) + ']//mxCell[@style]'):
        if c.find('mxGeometry') is not None and norm_text(M.plain_text(c)) == want:
            return c
    return None


def cap_combo_style(cfg, st):
    cv = cfg.combo_val
    if cv('arc') != '':
        st = M.style_set(M.style_set(M.style_del(st, 'absoluteArcSize'), 'rounded', '1'), 'arcSize', cv('arc'))
    if cv('opac') != '':
        st = M.style_set(st, 'opacity', cv('opac'))
    if cv('fill') != '':
        st = M.style_set(M.style_del(M.style_del(st, 'gradientColor'), 'gradientDirection'), 'fillColor', cv('fill'))
    if cv('font') != '':
        st = M.style_set(st, 'fontColor', cv('font'))
    if cv('textop') != '':
        st = M.style_set(st, 'textOpacity', cv('textop'))
    if cv('border') != '':
        st = M.style_set(st, 'strokeColor', cv('border'))
    return st


def combo_outline(cell, c):
    st, v = cell.get('style') or '', cell.get('value') or ''
    if M.style_get(st, 'html', '') != '1':
        v = v.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        cell.set('style', M.style_set(st, 'html', '1'))
    o = '0.5px'
    ts = f'-{o} -{o} 0 {c}, {o} -{o} 0 {c}, -{o} {o} 0 {c}, {o} {o} 0 {c}, 0 0 1px {c}'
    cell.set('value', f'<div style="text-shadow: {ts}">{v}</div>')


def style_num(st, key, d):
    v = M.style_get(st, key, '')
    return to_num(v) if is_number(v) else d


def cap_scale_text(cell, f):
    st = cell.get('style') or ''
    st = M.style_set(st, 'fontSize', fmt4(style_num(st, 'fontSize', 11) * f))
    for k in ('spacing', 'spacingTop', 'spacingBottom', 'spacingLeft', 'spacingRight'):
        sv = M.style_get(st, k, '')
        if is_number(sv):
            st = M.style_set(st, k, fmt4(to_num(sv) * f))
    cell.set('style', st)
    v = cell.get('value') or ''
    cell.set('value', re.sub(r'(?i)(font-size\s*:\s*)([0-9.]+)px',
                             lambda m: m.group(1) + fmt4(float(m.group(2)) * f) + 'px', v))


def combo_pair_swap(cfg, spec):
    tk = [t for t in re.split(r'[ \t]', cfg.mirror_pairs) if t]
    pm = {}
    for i in range(len(tk) // 2):
        a, b = tk[2 * i], tk[2 * i + 1]
        pm[a], pm[b] = b, a
    if not pm:
        return spec
    return ' '.join(pm.get(t, t) for t in spec.split(' '))


# --------------------------------------------------------------- combo lists
def combo_side(positions):
    side = ''
    for p in positions:
        s = M.pos_name(int(p))[:2]
        if s not in ('LH', 'RH'):
            return ''
        if side == '':
            side = s
        elif side != s:
            return ''
    return side


def pos_index(label):
    return M.POS_LABEL.index(label) if label in M.POS_LABEL else -1


def anchor_index(side, col):
    for r in (5, 4, 3, 2, 1):
        i = pos_index(f'{side}-C{col}R{r}')
        if i >= 0:
            return i
    return -1


def strip_spaces(t):
    return t.strip().replace(' ', '').replace(' ', '')


def short_pos_name(p):
    return re.sub(r'^(?:LH|RH)-', '', M.pos_name(p))


def key_label_for(cfg, slots, p, c, L, layout, have_keys, warn):
    if not have_keys:
        t = strip_spaces(M.plain_text(slots[p]))
        return t if t else short_pos_name(p)
    k = f"{L['idx']}|{p}"
    lab, kp = layout.get('keyLabel', {}), layout.get('keyKp', {})
    if lab.get(k, '').strip():
        return strip_spaces(lab[k])
    if kp.get(k, '').strip():
        return strip_spaces(kp[k])
    beh = CB.key_behaviour(layout, L['idx'], p)
    if not (cfg.combo_quiettrans and beh == '&trans'):
        warn.append(f"layer {L['idx']} ({L['name']}): combo {c['name']} lists {M.pos_name(p)}, "
                    'which has no label and no &kp' + (f' (binding is {beh})' if beh else '')
                    + ' - printed its position instead')
    return short_pos_name(p)


def combo_list_label(cfg, src, spec):
    el = find_combo_element(cfg, src, spec)
    if el is None:
        return spec
    t = M.plain_text(el).strip()
    return t if t else spec


def combo_list_line(cfg, src, slots, c, spec, L, layout, have_keys, warn):
    line = ' + '.join(key_label_for(cfg, slots, int(p), c, L, layout, have_keys, warn)
                      for p in sorted(c['keyPositions']))
    return line + ' ' + COMBO_ARROW + ' ' + combo_list_label(cfg, src, spec)


def find_combo_list_element(cfg, src):
    if cfg.combo_listel != '':
        r = src.xpath('//diagram[@name=' + M.q(cfg.combo_tab) + ']//mxCell[@id=' + M.q(cfg.combo_listel) + ']')
        return r[0] if r else None
    best, best_a = None, -1
    for c in src.xpath('//diagram[@name=' + M.q(cfg.combo_tab) + ']//mxCell[@style]'):
        if (c.get('style') or '')[:6].lower() == 'group;':
            continue
        g = M.geo(c)
        if g is None or M.plain_text(c).strip() != '':
            continue
        a = g['w'] * g['h']
        if a > best_a:
            best_a, best = a, c
    return best


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def add_combo_lists(cfg, src, root, L, slots, lists, layout, have_keys, warn):
    if not lists['LH'] and not lists['RH']:
        return
    if not have_keys:
        warn.append(f"layer {L['idx']} ({L['name']}): the combo cache predates .40 and holds no key "
                    'labels - combo lines fall back to the artwork.  Drop a fresh layout .json in and run again.')
    elif cfg.combo_quiettrans and not layout.get('keyBeh'):
        warn.append(f"layer {L['idx']} ({L['name']}): the combo cache predates .41 and holds no key "
                    'behaviours, so transparent keys cannot be told apart and their warnings are still '
                    'shown.  Re-export.')
    el = find_combo_list_element(cfg, src)
    if el is None:
        warn.append(f"layer {L['idx']} ({L['name']}): combos need the list box, but no empty element "
                    f"was found on the '{cfg.combo_tab}' tab to use as one")
        return
    eg = M.geo(el)
    if eg is None or eg['w'] <= 0 or eg['h'] <= 0:
        warn.append(f"the combo list element on the '{cfg.combo_tab}' tab has no size")
        return
    for side in ('LH', 'RH'):
        lines = lists[side]
        if not lines:
            continue
        a_idx = anchor_index(side, cfg.combo_listanchor)
        if a_idx < 0 or a_idx >= len(slots):
            warn.append(f'no {side} key in column C{cfg.combo_listanchor} to align the {side} combo list '
                        'to - check [combos] ListAnchor')
            continue
        ag = M.geo(slots[a_idx])
        x = ag['x'] if side == 'LH' else ag['x'] + ag['w'] - eg['w']
        y = GRP_H - eg['h'] - cfg.combo_listup
        lo, hi = -FRAME_PAD, GRP_H + FRAME_PAD - eg['h']
        if y < lo or y > hi:
            y = lo if y < lo else hi
            warn.append(f"layer {L['idx']} ({L['name']}): the {side} combo list was clamped to stay "
                        'inside the export frame - adjust ListUp')
        shown = min(len(lines), int(cfg.combo_listmax))
        html = '<br>'.join(esc(ln) for ln in lines[:shown])
        if len(lines) > shown:
            warn.append(f"layer {L['idx']} ({L['name']}): {len(lines)} combos on the {side} side but the "
                        f'box holds {cfg.combo_listmax} - {len(lines) - shown} not printed (raise '
                        'ListMaxLines, or draw a taller box)')
        # (CheckListWidth: a GDI text-width estimate for a warning only; not ported yet)
        node = import_node(el)
        node.set('id', 'fg-list-' + side)
        node.set('parent', 'fg')
        node.set('value', html)
        ng = node.find('mxGeometry')
        ng.set('x', vstr(float(x)))
        ng.set('y', vstr(float(y)))
        root.append(node)


# ---------------------------------------------------------------- foreground
def add_foreground(cfg, ctx, src, root, L, layout, list_on, warn):
    """AddForeground: key borders, combo bubbles and combo lists into the 'fg' group."""
    slots = M.index_keys(src, L['id'])
    center = {}
    cap_style = cfg.caps_like()
    cap_roles = LY.load_cap_roles(cfg, src, [])[0] if cap_style else {}
    cap_mid = M.keys_mid_x(src, L['node'])     # .186
    for p in range(60):
        cell = slots[p]
        g = M.geo(cell)
        center[p] = (g['x'] + g['w'] / 2, g['y'] + g['h'] / 2)
        if M.eff_fill(src, cell) == 'NONE':
            continue
        pst = M.key_paint_cell(src, cell).get('style') or ''
        if M.style_get(pst, 'strokeColor') in ('none', '', '-'):
            continue
        if cap_style:
            rn = M.style_get(cell.get('style'), 'keyRole', '')
            if rn != '' and rn in cap_roles:
                if LY.cap_transparent(cap_roles[rn]) and (cfg.key_style != 'render' or cfg.render_ring):
                    root.append(ctx.cap_ring_cell(cfg, src, cap_roles[rn], cell, g, p, cap_mid))
                continue
        bc = M.style_get(pst, 'strokeColor')
        sw = M.style_get(pst, 'strokeWidth', '')
        if not is_number(sw):
            sw = '1'
        rot = M.style_get(cell.get('style'), 'rotation', '')
        root.append(make_cell(f'fg-b{p}', 'fg', BORDER_STYLE + bc + ';strokeWidth=' + sw + ';', '',
                              g['x'], g['y'], g['w'], g['h'], '' if rot == 'none' else rot))

    lists = {'LH': [], 'RH': []}
    have_keys = CB.have_key_data(layout)
    cmap = ctx.combo_map
    for c in layout['combos']:
        if not (L['idx'] in c['layers'] or -1 in c['layers']):
            continue
        kp = c['keyPositions']
        n = len(kp)
        if n < 2 or any(int(p) not in center for p in kp):
            continue
        spec = cmap[c['name']] if c['name'] in cmap else combo_label_of(c)
        if c.get('pairSwap'):
            spec = combo_pair_swap(cfg, spec)
        adjacent = False
        if n == 2:
            a, b = center[int(kp[0])], center[int(kp[1])]
            adjacent = math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) <= cfg.combo_span
        if not adjacent:
            if not list_on or spec == '':
                continue
            side = combo_side(kp)
            if side == '':
                warn.append(f"layer {L['idx']} ({L['name']}): combo {c['name']} spans both hands but is "
                            f"labelled '{spec}' - clear its description if it is meant to be skipped")
                continue
            lists[side].append(combo_list_line(cfg, src, slots, c, spec, L, layout, have_keys, warn))
            continue
        cx = sum(center[int(p)][0] for p in kp) / n
        cy = sum(center[int(p)][1] for p in kp) / n
        if spec == '':
            warn.append(f"{c['name']} has no description and no combo_map.ini entry")
            continue
        el = find_combo_element(cfg, src, spec)
        if el is None:
            warn.append(f"nothing on the '{cfg.combo_tab}' tab matches '{spec}' for {c['name']} - draw it, "
                        'or add an override to combo_map.ini')
            continue
        eg = M.geo(el)
        node = import_node(el)
        node.set('id', 'fg-c' + c['name'])
        node.set('parent', 'fg')
        ng = node.find('mxGeometry')
        ng.set('x', vstr(cx - eg['w'] / 2))
        ng.set('y', vstr(cy - eg['h'] / 2))
        node.set('style', cap_combo_style(cfg, node.get('style') or ''))
        oc = cfg.combo_val('outline')
        if oc != '':
            combo_outline(node, oc)
        cf = to_num(cfg.combo_val('scale')) / 100
        if abs(cf - 1) > 0.001:
            ng.set('width', fmt4(eg['w'] * cf))
            ng.set('height', fmt4(eg['h'] * cf))
            ng.set('x', fmt4(cx - eg['w'] * cf / 2))
            ng.set('y', fmt4(cy - eg['h'] * cf / 2))
            cap_scale_text(node, cf)
        root.append(node)
    add_combo_lists(cfg, src, root, L, slots, lists, layout, have_keys, warn)


# ---------------------------------------------------------------------- page
class Ctx:
    """What a run holds for page building: the fonts, the combo map, the shapes."""
    def __init__(self, cfg, shapes=None):
        import fonts
        self.fonts = fonts.Fonts(cfg)
        self.combo_map = CB.load_combo_map(cfg)
        self.shapes = shapes

    def shape_text(self, cfg):
        import capkeys
        if getattr(self, '_st', None) is None:
            self._st = capkeys.ShapeText(cfg, self.shapes.sc)
        return self._st

    def cap_keys(self, cfg, src, out, gid, centre_x):
        import capkeys
        capkeys.cap_keys(cfg, self.shape_text(cfg), src, out, gid, centre_x)

    def cap_ring_cell(self, cfg, src, role, cell, g, p, cap_mid):
        import capkeys
        return capkeys.cap_ring_cell(cfg, self.shape_text(cfg), role, cell, g, p, cap_mid)


def copy_subtree(src, root, parent_id, centre_x, nested):
    for k in src.children(parent_id):
        if not nested and is_centre_cell(k, centre_x):
            continue
        root.append(import_node(k))
        copy_subtree(src, root, k.get('id'), centre_x, True)


def _out_cell(out, cid):
    r = out.xpath('//mxCell[@id=' + M.q(cid) + ']')
    return r[0] if r else None


def strip_key_strokes(src, out, gid):
    for key in M.index_keys(src, gid):
        if M.eff_fill(src, key) == 'NONE':
            continue
        c = _out_cell(out, M.key_paint_cell(src, key).get('id') or '')
        if c is None:
            continue
        st = c.get('style') or ''
        if M.style_get(st, 'strokeColor') not in ('none', '', '-'):
            c.set('style', M.style_set(st, 'strokeColor', 'none'))


def key_text_shift(src, out, gid, up):
    import capkeys as CK
    keys = M.index_keys(src, gid)
    lpics = CK.loose_pictures(src, gid, keys) if up != 0 else {}      # .176
    for key in keys:
        kid, pid = key.get('id'), M.key_paint_cell(src, key).get('id')
        for cid in ([kid] if pid == kid else [pid, kid]):
            c = _out_cell(out, cid or '')
            if c is None or (c.get('value') or '') == '':
                continue
            st = c.get('style') or ''
            st = M.style_set(st, 'spacingTop', fmt4(style_num(st, 'spacingTop', 0) - up))
            st = M.style_set(st, 'spacingBottom', fmt4(style_num(st, 'spacingBottom', 0) + up))
            c.set('style', st)
        # .163: the legend's other cells go up with the label (CapLegendExtras)
        if pid != kid and up != 0:
            pc = _out_cell(out, pid or '')
            if pc is not None:
                import capkeys as CK
                CK.cap_legend_extras(out, src, key, kid, pid, M.geo(pc), 1, 0, -up,
                                     M.style_get(pc.get('style') or '', 'rotation', ''))
        # .176: pictures loose on the key go up with it too
        if lpics.get(kid):
            pc = _out_cell(out, pid or '')
            if pc is not None:
                CK.cap_loose_extras(out, lpics[kid], M.geo(key), M.geo(pc), pid != kid, 1, 0, -up,
                                    M.style_get(pc.get('style') or '', 'rotation', ''))


def _js_int(st, k, d):
    """draw.io's parseInt of a style number (mxText: spacing values are cut to whole units,
    toward zero); d when the key is absent or not a number."""
    v = M.style_get(st, k, '')
    return int(to_num(v)) if is_number(v) else d


def _label_shift(st, axis, num):
    """mxText.getSpacing: how far the label's spacing moves its text along x or y (num = how a
    value is read: exact, or as draw.io does)."""
    sp = num(st, 'spacing', 2)
    if axis == 'x':
        a = M.style_get(st, 'align', 'center')
        l, r = num(st, 'spacingLeft', 0), num(st, 'spacingRight', 0)
        return sp + l if a == 'left' else -(sp + r) if a == 'right' else (l - r) / 2
    a = M.style_get(st, 'verticalAlign', 'middle')
    t, b = num(st, 'spacingTop', 0), num(st, 'spacingBottom', 0)
    return sp + t if a == 'top' else -(sp + b) if a == 'bottom' else (t - b) / 2


def _label_place(st, g, ox, oy):
    """How draw.io 30.0.1 places a centred label (measured): its spacing shift cut to whole units
    (ix, iy, in the label's own frame), and how far rounding puts the text from where that shift
    alone would (rx, ry, on the page).  Unturned: the middle is rounded to a whole unit (half
    up), except across a wrapped label, whose left edge and width are rounded before the shift.
    Turned: the label box's middle is placed on the page (the cell's centre plus the turned
    shift), rounded the same way (a wrapped one by its box's left edge), the text laid out there
    and then turned about the unrounded middle."""
    wrap = M.style_get(st, 'whiteSpace', '') == 'wrap'
    ix, iy = _label_shift(st, 'x', _js_int), _label_shift(st, 'y', _js_int)
    x, w = ox + g['x'], g['w']
    cx, cy = x + w / 2, oy + g['y'] + g['h'] / 2
    rot = M.style_get(st, 'rotation', '')
    t = to_num(rot) * 0.017453292519943295 if is_number(rot) else 0
    if t == 0:
        ax, ay = cx + ix, cy + iy
        rx = math.floor(x + 0.5) + math.floor(w + 0.5) / 2 + ix if wrap else math.floor(ax + 0.5)
    else:
        ax, ay = cx + ix * math.cos(t) - iy * math.sin(t), cy + ix * math.sin(t) + iy * math.cos(t)
        rx = math.floor(ax - w / 2 + 0.5) + math.floor(w + 0.5) / 2 if wrap else math.floor(ax + 0.5)
    return ix, iy, rx - ax, math.floor(ay + 0.5) - ay


def label_fractions(src, out, gid):
    """LabelFractions (.165): draw.io cuts spacing to whole units and rounds a label's place,
    so the face offset, the text factor's spacing and Key text up lose their fractions.  Each
    key's label (and a group key's other text cells) gets the difference between where it
    should be (where draw.io draws the source label, moved by exactly what the export changed)
    and where draw.io would draw it, as a CSS translate inside the label (its own frame, so a
    turned label's too).  Vertical text or not centred: only the spacing's cut part."""
    import capkeys as CK
    ids = {c.get('id'): c for c in out.iter('mxCell')}
    def offset(c):
        ox = oy = 0.0
        p = ids.get(c.get('parent'))
        while p is not None and p.get('id') not in ('0', '1'):
            g = M.geo(p)
            if g:
                ox, oy = ox + g['x'], oy + g['y']
            p = ids.get(p.get('parent'))
        return ox, oy
    exact = lambda st, k, d: style_num(st, k, d)
    for key in M.index_keys(src, gid):
        kid = key.get('id')
        pc = M.key_paint_cell(src, key)
        cells = [key] if pc is key else [pc, key]
        if pc is not key:
            skip = {bd.get('id') for bd in CK.key_badges(src, key)}
            cells += [sc for sc in src.children(kid) if sc is not pc and sc.get('id') not in skip
                      and not re.search(r'(^|;)group(;|$)', sc.get('style') or '')]
        for sc in cells:
            oc = ids.get(sc.get('id'))
            if oc is None or (oc.get('value') or '') == '':
                continue
            s0, s1 = sc.get('style') or '', oc.get('style') or ''
            if M.style_get(s1, 'html', '') != '1':
                continue
            g0, g1 = M.geo(sc), M.geo(oc)
            if g0 is None or g1 is None:
                continue
            ex = _label_shift(s1, 'x', exact) - _label_shift(s0, 'x', exact)
            ey = _label_shift(s1, 'y', exact) - _label_shift(s0, 'y', exact)
            ox, oy = offset(oc)
            ix0, iy0, rx0, ry0 = _label_place(s0, g0, ox, oy)
            ix1, iy1, rx1, ry1 = _label_place(s1, g1, ox, oy)
            if (M.style_get(s1, 'horizontal', '1') == '0' or M.style_get(s1, 'align', 'center') != 'center'
                    or M.style_get(s1, 'verticalAlign', 'middle') != 'middle'):
                cx, cy = ex - (ix1 - ix0), ey - (iy1 - iy0)
            else:
                cx, cy = ex - (ix1 - ix0) + rx0 - rx1, ey - (iy1 - iy0) + ry0 - ry1
            if abs(cx) > 0.00999 or abs(cy) > 0.00999:      # (not on a 0.00005 step)
                oc.set('value', '<div style="transform:translate(' + fmt4(cx) + 'px,' + fmt4(cy)
                       + 'px)">' + oc.get('value') + '</div>')


FIT_COLS, FIT_PX, FIT_PY, FIT_PAD = 24, 42, 54, 8      # LegendFit's probe page: 42 x 54 slots, 8-unit margin


def _fit_anchor(st, g, ox, oy):
    """A label's unrounded middle on the page: the cell's centre plus its exact spacing shift,
    turned with the cell.  [x, y, angle in radians]"""
    sx, sy = _label_shift(st, 'x', style_num), _label_shift(st, 'y', style_num)
    rot = M.style_get(st, 'rotation', '')
    t = to_num(rot) * 0.017453292519943295 if is_number(rot) else 0
    cx, cy = ox + g['x'] + g['w'] / 2, oy + g['y'] + g['h'] / 2
    return cx + sx * math.cos(t) - sy * math.sin(t), cy + sx * math.sin(t) + sy * math.cos(t), t


def _fit_plain(st):
    for k, v in (('fillColor', 'none'), ('strokeColor', 'none'), ('gradientColor', 'none'),
                 ('shadow', '0'), ('glass', '0')):
        st = M.style_set(st, k, v)
    return st


def _fit_centroid(a, scale, tx, ty, g):
    """The ink's centroid (alpha-weighted, page units) around the probe cell at about (tx, ty)
    of geometry g: its box and FIT_PAD units round it, kept inside its slot; or None."""
    h, w = a.shape[:2]
    x0, y0 = max(0, math.floor((tx - FIT_PAD) * scale)), max(0, math.floor((ty - FIT_PAD) * scale))
    x1 = min(w, math.floor((tx + min(g['w'] + FIT_PAD, FIT_PX - FIT_PAD)) * scale))
    y1 = min(h, math.floor((ty + min(g['h'] + FIT_PAD, FIT_PY - FIT_PAD)) * scale))
    if x1 <= x0 or y1 <= y0:
        return None
    al = a[y0:y1, x0:x1, 3].astype(np.int64)
    s = int(al.sum())
    if s < 3 * 255:
        return None
    sx = int((al.sum(0) * np.arange(x0, x1)).sum()) + s * 0.5
    sy = int((al.sum(1) * np.arange(y0, y1)).sum()) + s * 0.5
    return sx / s / scale, sy / s / scale


def legend_fit(cfg, ctx, src, out, gid, probe):
    """LegendFit (.171): draw.io (Chromium) puts a label's text baseline on a whole unit, so a
    legend whose font the export scales does not scale about its middle: it keeps its line or
    jumps a whole unit (4 % of a key; LDSA's 0.74 put 9 px labels ~0.9 low).  Every legend text
    cell the export changed (as LabelFractions: label, wrapper, a group key's other text cells;
    not badges, pictures or vertical text) goes twice onto one probe page - the source's cell and
    the export's - each in its own slot, moved by whole units only (the snapping stays the same).
    probe(doc) renders it (RGBA array).  Each cell's ink centroid gives where draw.io really puts
    it; the export's label is moved (its .165 translate, own frame) to the source's centroid
    scaled about the label's anchor: A1 + tf (D - A0), tf = the font size ratio."""
    import capkeys as CK
    ids = {c.get('id'): c for c in out.iter('mxCell')}
    def offset(c):
        ox = oy = 0.0
        p = ids.get(c.get('parent'))
        while p is not None and p.get('id') not in ('0', '1'):
            g = M.geo(p)
            if g:
                ox, oy = ox + g['x'], oy + g['y']
            p = ids.get(p.get('parent'))
        return ox, oy
    pairs = []
    for key in M.index_keys(src, gid):
        kid = key.get('id')
        pc = M.key_paint_cell(src, key)
        cells = [key] if pc is key else [pc, key]
        if pc is not key:
            skip = {bd.get('id') for bd in CK.key_badges(src, key)}
            cells += [sc for sc in src.children(kid) if sc is not pc and sc.get('id') not in skip
                      and not re.search(r'(^|;)group(;|$)', sc.get('style') or '')]
        for sc in cells:
            oc = ids.get(sc.get('id'))
            if oc is None or (oc.get('value') or '') == '':
                continue
            s0, s1 = sc.get('style') or '', oc.get('style') or ''
            if (M.style_get(s1, 'html', '') != '1' or M.style_get(s1, 'horizontal', '1') == '0'
                    or M.style_get(s1, 'shape', '') == 'image' or re.search(r'(?i)(^|;)image=', s1)):
                continue
            g0, g1 = M.geo(sc), M.geo(oc)
            if g0 is None or g1 is None:
                continue
            if s0 == s1 and (sc.get('value') or '') == oc.get('value') and g0 == g1:
                continue
            pairs.append((sc, oc, g0, g1, offset(oc)))
    if not pairs:
        return 0
    pd, root = new_page()
    rows = (len(pairs) - 1) // FIT_COLS + 1
    root.append(make_cell('fitframe', '1', 'fillColor=none;strokeColor=none;', '', 0, 0,
                          FIT_PX * FIT_COLS + FIT_PAD, FIT_PY * 2 * rows + FIT_PAD))
    slots = []
    for i, (sc, oc, g0, g1, (ox, oy)) in enumerate(pairs):
        tx, ty = FIT_PAD + 2 + FIT_PX * (i % FIT_COLS), FIT_PAD + 2 + FIT_PY * 2 * (i // FIT_COLS)
        s0 = (math.floor(tx - (ox + g0['x']) + 0.5), math.floor(ty - (oy + g0['y']) + 0.5))
        s1 = (math.floor(tx - (ox + g1['x']) + 0.5), math.floor(ty + FIT_PY - (oy + g1['y']) + 0.5))
        root.append(make_cell(f'fit{i}s', '1', _fit_plain(sc.get('style') or ''), sc.get('value') or '',
                              fmt4(ox + g0['x'] + s0[0]), fmt4(oy + g0['y'] + s0[1]), fmt4(g0['w']), fmt4(g0['h'])))
        slots.append((tx, ty, s0, s1))
    ctx.fonts.normalise(pd, set())            # the source's cells as any page has them
    for i, (sc, oc, g0, g1, (ox, oy)) in enumerate(pairs):
        s1 = slots[i][3]
        root.append(make_cell(f'fit{i}e', '1', _fit_plain(oc.get('style') or ''), oc.get('value') or '',
                              fmt4(ox + g1['x'] + s1[0]), fmt4(oy + g1['y'] + s1[1]), fmt4(g1['w']), fmt4(g1['h'])))
    scale = cfg.scale
    a = probe(pd)
    n = 0
    for i, (sc, oc, g0, g1, (ox, oy)) in enumerate(pairs):
        tx, ty, s0, s1 = slots[i]
        d, e = _fit_centroid(a, scale, tx, ty, g0), _fit_centroid(a, scale, tx, ty + FIT_PY, g1)
        if d is None or e is None:
            continue
        a0x, a0y, _ = _fit_anchor(sc.get('style') or '', g0, ox, oy)
        a1x, a1y, t = _fit_anchor(oc.get('style') or '', g1, ox, oy)
        tf = style_num(oc.get('style'), 'fontSize', 11) / style_num(sc.get('style'), 'fontSize', 11)
        dx = a1x + tf * (d[0] - s0[0] - a0x) - (e[0] - s1[0])
        dy = a1y + tf * (d[1] - s0[1] - a0y) - (e[1] - s1[1])
        lx, ly = dx * math.cos(t) + dy * math.sin(t), -dx * math.sin(t) + dy * math.cos(t)
        if abs(lx) <= 0.00999 and abs(ly) <= 0.00999:
            continue
        v = oc.get('value')
        m = re.fullmatch(r'<div style="transform:translate\((-?[0-9.]+)px,(-?[0-9.]+)px\)">(.*)</div>', v, re.S)
        if m:
            lx, ly, v = float(m.group(1)) + lx, float(m.group(2)) + ly, m.group(3)
        oc.set('value', '<div style="transform:translate(' + fmt4(lx) + 'px,' + fmt4(ly) + 'px)">' + v + '</div>')
        n += 1
    return n


def build_page_doc(cfg, ctx, L, layout, role, warn, src):
    """BuildPageDoc: the one-page document for layer L (role fg / cs; bg not yet)."""
    out, root = new_page()
    root.append(make_cell('frame', '1', 'fillColor=none;strokeColor=none;', '',
                          MARGIN - FRAME_PAD, MARGIN - FRAME_PAD, GRP_W + FRAME_PAD * 2, GRP_H + FRAME_PAD * 2))
    title_cells = []
    if role == 'bg':
        grp = import_node(L['node'])
        grp.set('parent', '1')
        gg = grp.find('mxGeometry')
        gg.set('x', vstr(MARGIN))
        gg.set('y', vstr(MARGIN))
        root.append(grp)
        centre_x = M.keys_mid_x(src, L['node'])   # .186
        copy_subtree(src, root, L['id'], centre_x, False)
        if isinstance(L['idx'], int):
            strip_key_strokes(src, out, L['id'])
            if cfg.caps_like():
                ctx.cap_keys(cfg, src, out, L['id'], centre_x)
            tu = cfg.text_up_val()
            if tu != 0:
                key_text_shift(src, out, L['id'], tu)
            label_fractions(src, out, L['id'])       # .165: the fractions draw.io drops
        ctx.fonts.normalise(out, set())
        return out
    grp = make_cell('fg', '1', 'group;fillColor=none;', '', MARGIN, MARGIN, GRP_W, GRP_H)
    grp.set('connectable', '0')
    root.append(grp)
    add_foreground(cfg, ctx, src, root, L, layout,
                   cfg.combo_list_cs if role == 'cs' else cfg.combo_list_fg, warn)
    centre_x = M.keys_mid_x(src, L['node'])     # .186
    for k in src.children(L['id']):
        if not is_centre_cell(k, centre_x):
            continue
        c = import_node(k)
        c.set('parent', 'fg')
        root.append(c)
        title_cells.append(c)
    align_title_pair(title_cells, L, warn)
    if L.get('mirror'):
        for c in title_cells:
            tt = M.plain_text(c).strip()
            if tt:
                c.set('value', set_html_text(c.get('value') or '', mirror_title(tt)))
    ctx.fonts.normalise(out, {c.get('id') for c in title_cells})
    return out


def build_page(cfg, ctx, path, L, layout, role, warn, src):
    """BuildPage: the page written to path (Render: the transparent keys' rings left out of
    the foreground - Compose draws them)."""
    out = build_page_doc(cfg, ctx, L, layout, role, warn, src)
    if cfg.key_style == 'render' and role != 'bg':
        for c in out.xpath("//mxCell[starts-with(@id,'fg-r')]"):
            c.getparent().remove(c)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(etree.tostring(out, encoding='unicode'))
    return out


# -------------------------------------------------------------------- legend
def legend_group(cfg, src):
    """LegendGroup: the 444-wide group on the legend tab, or None."""
    for g in src.xpath('//diagram[@name=' + M.q(cfg.cs_legtab) + "]//mxCell[contains(@style,'group')]"):
        gg = M.geo(g)
        if gg is not None and abs(gg['w'] - GRP_W) <= 1:
            return g
    return None


def legend_chips(out, gid):
    chips = []
    for sub in out.xpath('//mxCell[@parent=' + M.q(gid) + ']'):
        if 'group' not in (sub.get('style') or '').lower():
            continue
        chips += [c for c in out.xpath('//mxCell[@parent=' + M.q(sub.get('id') or '') + ']') if M.plain_text(c) != '']
    return chips


def needs_solid_border(st):
    if M.style_get(st, 'strokeColor', 'default') == 'none':
        return False
    return (M.style_get(st, 'glass', '0') == '1' or style_num(st, 'opacity', 100) < 100
            or style_num(st, 'strokeOpacity', 100) < 100)


def add_legend_borders(out, gid):
    root = out.find('.//root')
    n = 0
    for c in legend_chips(out, gid):
        st = c.get('style') or ''
        if not needs_solid_border(st):
            continue
        g = M.geo(c)
        if g is None:
            continue
        col, sw = M.style_get(st, 'strokeColor', 'default'), M.style_get(st, 'strokeWidth', '1')
        rnd, arc, rot = M.style_get(st, 'rounded', '0'), M.style_get(st, 'arcSize', '20'), M.style_get(st, 'rotation', '')
        c.set('style', M.style_set(st, 'strokeColor', 'none'))
        n += 1
        root.append(make_cell(f'lg-b{n}', c.get('parent'), BORDER_STYLE + col + ';strokeWidth=' + sw + ';rounded='
                              + rnd + ';arcSize=' + arc + ';', '', g['x'], g['y'], g['w'], g['h'], rot))


def cap_legend(cfg, ctx, out, gid, roles):
    """CapLegend: the legend's role chips as caps; returns them as RenderShade items (x, y in
    the legend group; a transparent role's chip is a ring) with their role."""
    import capkeys as CK
    import shade as SH
    st = ctx.shape_text(cfg)
    root = out.find('.//root')
    items = []
    for c in legend_chips(out, gid):
        sty = c.get('style') or ''
        rn = M.style_get(sty, 'keyRole', '')
        g = M.geo(c)
        if rn == '' or rn not in roles or g is None:
            continue
        r = roles[rn]
        c.set('style', CK.cap_clear_paint(sty))
        rot = M.style_get(sty, 'rotation', '')
        CK.cap_insert_before(c, (c.get('id') or '') + '-cap', CK.cap_image_style(CK.svg_uri(
            CK.cap_svg(cfg, st, r, g['w'], g['h'], False, LY.cap_transparent(r))), rot))
        if cfg.cap_edge_top and not LY.cap_transparent(r):
            root.append(make_cell((c.get('id') or '') + '-rim', c.get('parent'), CK.cap_image_style(CK.svg_uri(
                CK.cap_svg(cfg, st, r, g['w'], g['h'], False, True)), rot), '',
                fmt4(g['x']), fmt4(g['y']), fmt4(g['w']), fmt4(g['h'])))
        lx, ly, par = g['x'], g['y'], c.get('parent') or ''
        while par not in ('', gid):
            pn = out.xpath('//mxCell[@id=' + M.q(par) + ']')
            if not pn:
                break
            pgo = M.geo(pn[0])
            if pgo is not None:
                lx, ly = lx + pgo['x'], ly + pgo['y']
            par = pn[0].get('parent') or ''
        it = SH.legend_item(cfg, r, lx, ly, g['w'], g['h'], to_num(rot) if is_number(rot) else 0)
        it['role'] = rn
        items.append(it)
    return items


def build_legend_page(cfg, ctx, src, warn=None):
    """RenderLegend's page: (page, chips) or (None, []) when there is no legend group."""
    grp = legend_group(cfg, src)
    if grp is None:
        return None, []
    L = {'idx': 'legend', 'name': 'legend', 'node': grp, 'id': grp.get('id'), 'titleGeo': None}
    out = build_page_doc(cfg, ctx, L, {}, 'bg', [] if warn is None else warn, src)
    chips = cap_legend(cfg, ctx, out, L['id'], LY.load_cap_roles(cfg, src, [])[0]) if cfg.caps_like() else []
    add_legend_borders(out, L['id'])
    return out, chips
