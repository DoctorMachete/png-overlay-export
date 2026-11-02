"""The source diagram: loading, geometry, styles, layers and keys.
Ports of the .147 script's LoadXml, Geo, StyleGet/Set/Del, PlainText,
IsKeySize, KeyPaintChild/Cell, EffFill, HasGradient, PageGrid, LayoutCols,
SlotOfGroup, CentreCrossesX, TitleCellsOf, LayerNameOf, Discover, IndexKeys,
PosName.  XPath expressions are the script's own (lxml's XPath 1.0 behaves as
MSXML's selectNodes: document order, document-wide unless scoped)."""
import math, re
from lxml import etree

GRP_W = 444
GRP_H = 177.7714699700121
FRAME_PAD = 8
SLOT_MAX = 32
SRC_PAGE_W, SRC_PAGE_H = 470, 210
THUMB_X = [52, 78, 104, 315, 341, 367, 133, 162, 188, 231, 257, 286]
BAND = [[0, 25], [25, 50], [50, 76], [76, 110]]
ROLES_TAB = '@config-roles'
POS_LABEL = [
    "LH-C6R1", "LH-C5R1", "LH-C4R1", "LH-C3R1", "LH-C2R1", "LH-C1R1",
    "RH-C1R1", "RH-C2R1", "RH-C3R1", "RH-C4R1", "RH-C5R1", "RH-C6R1",
    "LH-C6R2", "LH-C5R2", "LH-C4R2", "LH-C3R2", "LH-C2R2", "LH-C1R2",
    "RH-C1R2", "RH-C2R2", "RH-C3R2", "RH-C4R2", "RH-C5R2", "RH-C6R2",
    "LH-C6R3", "LH-C5R3", "LH-C4R3", "LH-C3R3", "LH-C2R3", "LH-C1R3",
    "RH-C1R3", "RH-C2R3", "RH-C3R3", "RH-C4R3", "RH-C5R3", "RH-C6R3",
    "LH-C6R4", "LH-C5R4", "LH-C4R4", "LH-C3R4", "LH-C2R4", "LH-C1R4",
    "RH-C1R4", "RH-C2R4", "RH-C3R4", "RH-C4R4", "RH-C5R4", "RH-C6R4",
    "LH-C4R5", "LH-C3R5", "LH-C2R5", "RH-C2R5", "RH-C3R5", "RH-C4R5",
    "LH-T1", "LH-T2", "LH-T3", "RH-T3", "RH-T2", "RH-T1"]


class Die(Exception):
    """The script's Die(): a fatal, user-facing error."""


def is_number(v):
    if isinstance(v, (int, float)):
        return True
    return bool(re.fullmatch(r'\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*', str(v or '')))


def num(v, default=0.0):
    return float(v) if is_number(v) else default


# ------------------------------------------------------------------ the file
def load_xml(path):
    """LoadXml: the whole .drawio as an lxml tree (uncompressed diagrams, as the script expects)."""
    try:
        parser = etree.XMLParser(remove_blank_text=False, huge_tree=True)
        return etree.parse(path, parser)
    except etree.XMLSyntaxError as e:
        raise Die(f'XML parse error in {path}\n\n{e}')


def sel(doc, xp):
    return doc.xpath(xp)


def sel1(doc, xp):
    r = doc.xpath(xp)
    return r[0] if r else None


def q(v):
    """A string literal for an XPath expression (ids never hold both quote kinds)."""
    return "'" + v + "'" if "'" not in v else '"' + v + '"'


class Doc:
    """The source tree with the document-wide //mxCell[@parent=…] lookups indexed
    (the script runs them as XPath each time; the result is the same)."""
    def __init__(self, tree):
        self.tree = tree
        self.root = tree.getroot()
        self.reindex()

    def reindex(self):
        self.kids = {}
        for c in self.root.iter('mxCell'):
            self.kids.setdefault(c.get('parent'), []).append(c)

    def children(self, cid):
        """//mxCell[@parent='cid'], in document order."""
        return self.kids.get(cid, [])

    def xpath(self, xp):
        return self.root.xpath(xp)

    def diagram(self, name):
        r = self.root.xpath('//diagram[@name=' + q(name) + ']')
        return r[0] if r else None


# ------------------------------------------------------------- cells, styles
def geo(node):
    """Geo: x, y, w, h of a cell's mxGeometry (0 for a missing number), or None."""
    g = node.find('mxGeometry')
    if g is None:
        return None
    def n(k):
        v = g.get(k)
        return 0.0 if v in (None, '') else float(v)
    return {'x': n('x'), 'y': n('y'), 'w': n('width'), 'h': n('height')}


def style_get(style, key, default='none'):
    m = re.search(r'(?i)(?:^|;)' + re.escape(key) + r'=([^;]*)', style or '')
    return m.group(1) if m else default


def style_set(style, key, val):
    style = style or ''
    if re.search(r'(?i)(?:^|;)' + re.escape(key) + '=', style):
        return re.sub(r'(?i)(^|;)' + re.escape(key) + r'=[^;]*', lambda m: m.group(1) + key + '=' + str(val), style)
    return style.rstrip(';') + ';' + key + '=' + str(val) + ';'


def style_del(style, key):
    return re.sub(r'(?i)(^|;)' + re.escape(key) + r'=[^;]*;?', r'\1', style or '')


def plain_text(node):
    v = node.get('value') or ''
    if v == '':
        return ''
    v = re.sub(r'<[^>]+>', ' ', v)
    for a, b in (('&nbsp;', ' '), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'"), ('&amp;', '&')):
        v = v.replace(a, b)
    return re.sub(r'\s+', ' ', v).strip()


def is_key_size(g):
    return g is not None and abs(g['w'] - 25) < 0.01 and (abs(g['h'] - 25) < 0.01 or abs(g['h'] - 37) < 0.01)


def key_paint_child(doc, node):
    for ch in doc.children(node.get('id')):
        if is_key_size(geo(ch)):
            return ch
    return None


def key_paint_cell(doc, node):
    ch = key_paint_child(doc, node)
    return ch if ch is not None else node


def eff_fill(doc, node):
    ch = key_paint_child(doc, node)
    if ch is not None:
        f = style_get(ch.get('style'), 'fillColor')
        if f not in ('none', '-'):
            return f.upper()
    f = style_get(node.get('style'), 'fillColor')
    if f not in ('none', '-'):
        return f.upper()
    return 'NONE'


def has_gradient(node):
    gc = style_get(node.get('style'), 'gradientColor')
    return gc not in ('', 'none', '-')


def pos_name(p):
    return POS_LABEL[p] if 0 <= p < len(POS_LABEL) else f'pos {p}'


# -------------------------------------------------------------------- layers
def layout_cols(doc):
    c = sel1(doc.root, "//diagram[@name='background']/mxGraphModel/root/mxCell[@parent='0']")
    v = style_get(c.get('style'), 'layoutCols', '') if c is not None else ''
    return int(v) if re.fullmatch(r'\s*\d+\s*', v or '') and 1 <= int(v) <= SLOT_MAX else 8


def page_grid(doc):
    pw, ph = SRC_PAGE_W, SRC_PAGE_H
    m = sel1(doc.root, "//diagram[@name='background']/mxGraphModel")
    if m is not None:
        v = m.get('pageWidth')
        if v and is_number(v) and float(v) > 0:
            pw = float(v)
        v = m.get('pageHeight')
        if v and is_number(v) and float(v) > 0:
            ph = float(v)
    cols = layout_cols(doc)
    return {'pw': pw, 'ph': ph, 'cols': cols, 'rows': math.ceil(SLOT_MAX / cols)}


def slot_of_group(g, pg):
    if g is None:
        return -1
    col = math.floor((g['x'] + g['w'] / 2) / pg['pw'])
    row = math.floor((g['y'] + g['h'] / 2) / pg['ph'])
    if col < 0 or col >= pg['cols'] or row < 0 or row >= pg['rows']:
        return -1
    idx = row * pg['cols'] + col
    return idx if idx < SLOT_MAX else -1


def centre_crosses_x(g, cx):
    return g is not None and g['x'] <= cx <= g['x'] + g['w']


def title_cells_of(doc, grp):
    gg = geo(grp)
    cx = gg['w'] / 2 if gg else GRP_W / 2
    cells = [k for k in doc.children(grp.get('id'))
             if (lambda gk: gk is not None and not is_key_size(gk) and centre_crosses_x(gk, cx))(geo(k))]
    # the script's bubble sort: stable, ascending y
    return sorted(cells, key=lambda c: geo(c)['y'])


def layer_name_of(cells):
    for c in reversed(cells):
        t = plain_text(c).strip()
        m = re.match(r'^\s*\d+\.\s*(.+?)\s*$', t)
        if m:
            return m.group(1).strip()
        if t != '' and not re.fullmatch(r'[\s\-]+', t):
            return t
    return ''


def discover(doc, warn, skipped=None):
    """Discover: the layers of the background tab, by page-grid slot."""
    out = {}
    pg = page_grid(doc)
    for grp in doc.xpath("//diagram[@name='background']//mxCell[contains(@style,'group')]"):
        g = geo(grp)
        if g is None or abs(g['w'] - GRP_W) > 1:
            continue
        gid = grp.get('id')
        idx = slot_of_group(g, pg)
        if idx < 0:
            continue
        cells = title_cells_of(doc, grp)
        name = layer_name_of(cells)
        if name == '':
            continue
        title_geo = geo(cells[-1]) if cells else None
        keys = painted = 0
        for k in doc.children(gid):
            if is_key_size(geo(k)):
                keys += 1
                if eff_fill(doc, k) != 'NONE' or has_gradient(k):
                    painted += 1
        problem = key_layout_problem(doc, gid)
        if problem:
            warn.append(f'layer {idx} ({name}) skipped - {problem}')
            if skipped is not None and idx not in skipped:
                skipped[idx] = {'name': name, 'reason': problem}
            continue
        if painted == 0:
            warn.append(f'layer {idx} ({name}) has no painted keys - rendering it blank. '
                        'Intended placeholder, or unfinished?')
        clash = '; '.join(f'{pos_name(i)} ({c})' for i, cell in enumerate(index_keys(doc, gid))
                          for c in [wrapper_fill_clash(doc, cell)] if c)
        if clash:
            warn.append(f'layer {idx} ({name}) - group key fill disagrees with its '
                        f'visible rect at {clash}. The rect is used; clear the wrapper\'s '
                        'fill (select the key with ONE click, Fill: none).')
        if idx not in out:
            out[idx] = {'idx': idx, 'name': name, 'node': grp, 'id': gid, 'titleGeo': title_geo}
    return [out[i] for i in sorted(out)]


def index_keys(doc, gid):
    """IndexKeys: the 60 key cells of a layer group in ZMK position order."""
    rows = [[], [], [], []]
    thumbs = {}
    for k in doc.children(gid):
        g = geo(k)
        if not is_key_size(g):
            continue
        if g['y'] >= 110:
            thumbs[round_ahk(g['x'])] = k
            continue
        for i, b in enumerate(BAND):
            if b[0] <= g['y'] < b[1]:
                rows[i].append({'x': g['x'], 'cell': k})
                break
    slots = []
    for i, r in enumerate(rows, 1):
        if len(r) != 12:
            raise Die(f'Row {i} holds {len(r)} keys, expected 12.')
        r.sort(key=lambda e: e['x'])          # the script's bubble sort is stable too
        slots += [e['cell'] for e in r]
    for x in THUMB_X:
        if x not in thumbs:
            raise Die(f'No thumb key at x={x}.')
        slots.append(thumbs[x])
    return slots


def round_ahk(x):
    """AHK Round(): half away from zero."""
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


# ------------------------------------------------------- key layout checks
MAIN_COL_XS = [0, 26, 52, 78, 104, 130, 289, 315, 341, 367, 393, 419]
_LHX = {0: 'C6', 26: 'C5', 52: 'C4', 78: 'C3', 104: 'C2', 130: 'C1'}
_RHX = {289: 'C1', 315: 'C2', 341: 'C3', 367: 'C4', 393: 'C5', 419: 'C6'}


def wrapper_fill_clash(doc, node):
    """WrapperFillClash: '' or 'wrapper #AAA, rect #BBB' for a group key whose
    wrapper fill differs from its key-sized child's."""
    ch = key_paint_child(doc, node)
    if ch is None:
        return ''
    wf = style_get(node.get('style'), 'fillColor')
    cf = style_get(ch.get('style'), 'fillColor')
    if wf in ('none', '-') or cf in ('none', '-'):
        return ''
    return '' if wf.upper() == cf.upper() else f'wrapper {wf.upper()}, rect {cf.upper()}'


def is_keyish(g):
    return g is not None and 20 < g['w'] < 45 and 20 < g['h'] < 45


def fmt_size(n):
    r = round_ahk(n)
    return str(r) if abs(n - r) < 0.01 else repr(round(n, 2))


def label_for_row_x(row, x):
    if x in _LHX:
        return f'LH-{_LHX[x]}R{row}'
    if x in _RHX:
        return f'RH-{_RHX[x]}R{row}'
    return f'x={x} R{row}'


def snap_column_x(x):
    best, bestd = x, 99999
    for c in MAIN_COL_XS:
        if abs(c - x) < bestd:
            bestd, best = abs(c - x), c
    return best if bestd <= 3 else x


def size_audit_label(g):
    x = snap_column_x(round_ahk(g['x']))
    if g['y'] >= 110:
        return f'thumb x={x}'
    for i, b in enumerate(BAND, 1):
        if b[0] <= g['y'] < b[1]:
            return label_for_row_x(i, x)
    return f'x={x} y={round_ahk(g["y"])}'


def _ahk_map_order(d):
    """AHK v2 Map enumeration: integer keys ascending, then strings in ordinal order."""
    return sorted(d.items(), key=lambda kv: (isinstance(kv[0], str), kv[0]))


def _dedupe(a):
    return list(dict.fromkeys(a))


def key_layout_problem(doc, gid):
    """KeyLayoutProblem: '' when the group holds exactly the 60 keys in place,
    else the reason the layer is skipped (doubled, missing, wrong-size keys)."""
    rows = [[], [], [], []]
    thumbs, thumb_dup, wrong_list = {}, [], []
    for k in doc.children(gid):
        g = geo(k)
        if not is_key_size(g):
            if is_keyish(g):
                wrong_list.append((size_audit_label(g), f'{fmt_size(g["w"])}x{fmt_size(g["h"])}'))
            continue
        if g['y'] >= 110:
            xk = round_ahk(g['x'])
            if xk in thumbs:
                thumb_dup.append(xk)
            thumbs[xk] = k
            continue
        for i, b in enumerate(BAND):
            if b[0] <= g['y'] < b[1]:
                rows[i].append(round_ahk(g['x']))
                break
    occupied = {label_for_row_x(i, kx) for i, r in enumerate(rows, 1) for kx in r}
    occupied |= {f'thumb x={xk}' for xk in thumbs}
    wrong, wrong_dup = {}, {}
    for lbl, sz in wrong_list:
        (wrong_dup if lbl in occupied else wrong)[lbl] = sz
    bad, miss = [], []
    for i, r in enumerate(rows, 1):
        seen = set()
        for kx in r:
            if kx in seen:
                bad.append(label_for_row_x(i, kx))
            seen.add(kx)
        for x in MAIN_COL_XS:
            if x not in seen and label_for_row_x(i, x) not in wrong:
                miss.append(label_for_row_x(i, x))
    bad += [f'thumb x={xk}' for xk in thumb_dup]
    miss += [f'thumb x={x}' for x in THUMB_X if x not in thumbs and f'thumb x={x}' not in wrong]
    total = len(thumbs) + sum(len(r) for r in rows)
    row_note = ', '.join(f'row {i} has {len(r)}' for i, r in enumerate(rows, 1) if len(r) != 12)
    if not (bad or miss or wrong or wrong_dup) and total == 60 and row_note == '':
        return ''
    msg = []
    if bad:
        msg.append('doubled keys at ' + ', '.join(_dedupe(bad)))
    if miss:
        msg.append('missing keys at ' + ', '.join(_dedupe(miss)))
    if wrong:
        msg.append('wrong-size keys at ' + ', '.join(f'{l} ({s})' for l, s in _ahk_map_order(wrong))
                   + ' - resize to 25x25 (T3 25x37)')
    if wrong_dup:
        msg.append('off-spec duplicate keys at ' + ', '.join(f'{l} ({s})' for l, s in _ahk_map_order(wrong_dup))
                   + ' - a wrong-size cell stacked on a good key; delete the off-spec one')
    out = '; '.join(msg)
    if total != 60:
        out += ('; ' if out else '') + f'{total} key cells (expected 60)' + (f' - {row_note}' if row_note else '')
    return out


def valid_layer_groups(doc):
    """ValidLayerGroups: Discover's layers without its warnings (document order, duplicates kept)."""
    pg = page_grid(doc)
    out = []
    for grp in doc.xpath("//diagram[@name='background']//mxCell[contains(@style,'group')]"):
        g = geo(grp)
        if g is None or abs(g['w'] - GRP_W) > 1:
            continue
        idx = slot_of_group(g, pg)
        if idx < 0:
            continue
        name = layer_name_of(title_cells_of(doc, grp))
        if name == '':
            continue
        gid = grp.get('id')
        if key_layout_problem(doc, gid) != '':
            continue
        out.append({'idx': idx, 'name': name, 'id': gid})
    return out
