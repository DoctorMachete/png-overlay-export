"""The pages handed to draw.io: BuildPageDoc / BuildPage of the .148 script.
Done: the page skeleton, the foreground (AddForeground: key borders, combo
bubbles, combo lists), the title pair (IsCentreCell, AlignTitlePair,
SetHtmlText, MirrorTitle) and NormaliseFonts.  Not yet: the background branch
(CopySubtree, StripKeyStrokes, CapKeys, KeyTextShift), CapSvg rings for
transparent roles in the SVG-caps style, mirrored layers, the legend.

Numbers: AHK passes floats to MSXML's setAttribute, which converts them as COM
does (15 significant digits, no trailing '.0'): vstr()."""
import copy, math, re
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
    gg = M.geo(L['node'])
    cap_mid = gg['w'] / 2 if gg else GRP_W / 2
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
    for key in M.index_keys(src, gid):
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
        g0 = M.geo(L['node'])
        centre_x = g0['w'] / 2 if g0 else GRP_W / 2
        copy_subtree(src, root, L['id'], centre_x, False)
        if isinstance(L['idx'], int):
            strip_key_strokes(src, out, L['id'])
            if cfg.caps_like():
                ctx.cap_keys(cfg, src, out, L['id'], centre_x)
            tu = cfg.text_up_val()
            if tu != 0:
                key_text_shift(src, out, L['id'], tu)
        ctx.fonts.normalise(out, set())
        return out
    grp = make_cell('fg', '1', 'group;fillColor=none;', '', MARGIN, MARGIN, GRP_W, GRP_H)
    grp.set('connectable', '0')
    root.append(grp)
    add_foreground(cfg, ctx, src, root, L, layout,
                   cfg.combo_list_cs if role == 'cs' else cfg.combo_list_fg, warn)
    gg = M.geo(L['node'])
    centre_x = gg['w'] / 2 if gg else GRP_W / 2
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
