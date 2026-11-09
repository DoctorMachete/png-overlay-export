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
        """//mxCell[@parent='cid'], in document order.  A cell with no id (draw.io puts the id
        on a UserObject / object wrapper) has no children: MSXML's lookup with "" finds none,
        while kids[None] would be the page roots (a loop through the whole document)."""
        if not cid:
            return []
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
def page_layer_cell(root):
    """PageLayerCell (.185): a page's layer cell, the child of its root cell - "0" in most
    files, a random id on a page draw.io duplicated (the old @parent='0' found nothing there
    and the grid fell back to 8 columns)."""
    if root is None:
        return None
    c = sel1(root, "mxCell[@parent='0']")
    if c is not None:
        return c
    r0 = sel1(root, "mxCell[not(@parent)]")
    return sel1(root, f"mxCell[@parent={q(r0.get('id'))}]") if r0 is not None else None


def layout_cols(doc):
    c = page_layer_cell(sel1(doc.root, "//diagram[@name='background']/mxGraphModel/root"))   # .185
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
    cx = keys_mid_x(doc, grp)                  # .186: the keys' middle
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
        if not is_layer_group_geo(g):          # .186: 200-444 wide
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


def is_layer_group_geo(g):
    """IsLayerGroupGeo (.186): a layer group is 200 to 444 (+1) units wide."""
    return g is not None and 200 <= g['w'] <= GRP_W + 1


def keys_mid_x(doc, grp):
    """KeysMidX (.186): the layer's middle line - the middle of its key-sized cells' span
    (222 on the 444 layout); the group's half width when it has none."""
    ks = [g for g in (geo(k) for k in doc.children(grp.get('id'))) if is_key_size(g)]
    if ks:
        return (min(g['x'] for g in ks) + max(g['x'] + g['w'] for g in ks)) / 2
    gg = geo(grp)
    return gg['w'] / 2 if gg else GRP_W / 2


_BOTTOM = ['C4R5', 'C3R5', 'C2R5', 'T1', 'T2', 'T3']


def classify_keys(doc, gid):
    """ClassifyKeys (.186): (60 cells in ZMK order, '') or (None, problem), by structure.
    Per hand (left / right of the keys' middle) keys within 3 units of the next one's x make
    a column; columns of 4+ are C1 (nearest the middle) .. C6, R1-R4 top to bottom; a 5th key
    and keys in no column are the bottom cluster, from the outside in C4R5 C3R5 C2R5 T1 T2 T3.
    Stable sorts, as the script's."""
    keys, lo, hi = [], None, None
    for k in doc.children(gid):
        g = geo(k)
        if not is_key_size(g):
            continue
        keys.append({'k': k, 'cx': g['x'] + g['w'] / 2, 'y': g['y']})
        lo = g['x'] if lo is None or g['x'] < lo else lo
        hi = g['x'] + g['w'] if hi is None or g['x'] + g['w'] > hi else hi
    dup = [f"x={round_ahk(a['cx'] - 12.5)} y={round_ahk(a['y'])}"
           for i, a in enumerate(keys) for b in keys[i + 1:]
           if abs(a['cx'] - b['cx']) < 3 and abs(a['y'] - b['y']) < 3]
    if dup:
        return None, 'doubled keys at ' + ', '.join(dup)
    if len(keys) != 60:
        return None, f'{len(keys)} key cells (expected 60)'
    mid, by_pos = (lo + hi) / 2, {}
    for hand, side in (('LH', -1), ('RH', 1)):
        hk = [e for e in keys if (e['cx'] - mid) * side > 0]
        if len(hk) != 30:
            return None, f'{hand}: {len(hk)} keys (expected 30)'
        hk.sort(key=lambda e: e['cx'])
        clusters = [[hk[0]]]
        for e in hk[1:]:
            if e['cx'] - clusters[-1][-1]['cx'] > 3:
                clusters.append([e])
            else:
                clusters[-1].append(e)
        cols, bottom = [], []
        for c in clusters:
            c.sort(key=lambda e: e['y'])
            if len(c) >= 4:
                cols.append((abs(c[0]['cx'] - mid), c[:4]))
                bottom += c[4:]
            else:
                bottom += c
        if len(cols) != 6 or len(bottom) != 6:
            return None, (f'{hand}: {len(cols)} column(s) of 4 keys and {len(bottom)} other key(s) '
                          '(expected 6 and 6: keys in a column within 3 units of the same x)')
        cols.sort(key=lambda c: c[0])
        for ci, (_, c) in enumerate(cols, 1):
            for ri, e in enumerate(c, 1):
                by_pos[f'{hand}-C{ci}R{ri}'] = e['k']
        bottom.sort(key=lambda e: abs(e['cx'] - mid), reverse=True)
        for nm, e in zip(_BOTTOM, bottom):
            by_pos[f'{hand}-{nm}'] = e['k']
    return [by_pos[pos_name(i)] for i in range(60)], ''


def index_keys(doc, gid):
    """IndexKeys: the 60 key cells of a layer group in ZMK position order (.186: by structure)."""
    slots, problem = classify_keys(doc, gid)
    if slots is None:
        raise Die(f'The keys could not be read: {problem}.')
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
    """KeyLayoutProblem (.186): '' when the group's 60 keys read by structure, else why not
    (doubled keys, hand counts, wrong-size cells by coordinates)."""
    wrong = [f"x={round_ahk(g['x'])} y={round_ahk(g['y'])} ({fmt_size(g['w'])}x{fmt_size(g['h'])})"
             for g in (geo(k) for k in doc.children(gid)) if not is_key_size(g) and is_keyish(g)]
    _, msg = classify_keys(doc, gid)
    if wrong:
        msg += ('; ' if msg else '') + ('wrong-size key cells at ' + ', '.join(wrong)
                                         + ' - resize to 25x25 (T3 25x37), or delete one stacked on a good key')
    return msg


def valid_layer_groups(doc):
    """ValidLayerGroups: Discover's layers without its warnings (document order, duplicates kept)."""
    pg = page_grid(doc)
    out = []
    for grp in doc.xpath("//diagram[@name='background']//mxCell[contains(@style,'group')]"):
        g = geo(grp)
        if not is_layer_group_geo(g):          # .186: 200-444 wide
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
