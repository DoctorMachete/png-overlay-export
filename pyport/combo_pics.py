"""Picture combo bubbles (.190): a group on the combos tab (bubble + SVG / PNG picture) linked to
combos by a draw.io data property `combo` (Edit Data, Ctrl+M; several names comma-separated),
copied into the foreground between the combo's keys; the picture recoloured to the layout's
combo font colour (the Color Changer's "Recolor all": every SVG colour / every PNG pixel's
colour, transparency kept).  The script's PicBubble* functions do the same."""
import base64
import io
import re
import urllib.parse

import model as M

_WRAP = ('object', 'UserObject')
_CACHE = [None, None, None]              # [source document, combo tab name, {name: wrapper}]


def link_key(s):
    """.193: how a 'combo' value and a combo's description are compared: exactly like a text
    bubble's text (pages.norm_text: characters sorted, spaces and NBSP dropped, case kept -
    "( {" = "{ (", unicode symbols as they are)."""
    return ''.join(sorted((s or '').replace('\u00a0', '').replace(' ', '')))


def find_link(links, spec):
    """.192: the element linked to a combo through its spec - its combo_map.ini entry, else its
    description up to '~~~': the same text a text bubble is matched by (never the ZMK name, as
    with text bubbles).  None when not linked."""
    k = link_key(spec)
    return links.get(k) if k else None


def text_cell(src, tab, wrap):
    """.193: when the linked element is a plain text bubble (one cell, not grouped, no picture):
    a copy of its cell carrying the wrapper's label as its value, so it is placed exactly like a
    text bubble found by its text.  None for picture bubbles / groups."""
    cell, _, label = bubble_root(src, tab, wrap)
    if cell is None or cell.getparent() is not wrap:
        return None
    st = cell.get('style') or ''
    if _is_group(cell) or re.search(r'(^|;)image=', st):
        return None
    import copy as _copy
    c = _copy.deepcopy(cell)
    c.tail = None
    c.set('value', label)
    return c


def combo_links(src, tab):
    """{link_key(value): the object / UserObject on the combos tab whose 'combo' property lists
    it}; the first one wins.  Cached per source document."""
    if _CACHE[0] is src and _CACHE[1] == tab:
        return _CACHE[2]
    out = {}
    for o in src.xpath('//diagram[@name=' + M.q(tab) + ']//*[self::object or self::UserObject][@combo]'):
        for n in (o.get('combo') or '').split(','):
            n = link_key(n)
            if n and n not in out:
                out[n] = o
    _CACHE[0], _CACHE[1], _CACHE[2] = src, tab, out
    return out


def cell_id(cell):
    """The id of a cell, or of the object / UserObject wrapping it (draw.io puts it there)."""
    p = cell.getparent()
    if cell.get('id'):
        return cell.get('id')
    return p.get('id') if p is not None and p.tag in _WRAP else ''


def _is_group(cell):
    return cell is not None and 'group' in (cell.get('style') or '').split(';')


def bubble_root(src, tab, wrap):
    """.191: what to copy for a linked element (wrap: the object / UserObject carrying 'combo'):
    the element itself, or - when it sits inside a group (the property set on the bubble, then
    grouped with its picture) - the outermost group holding it below the page.
    Returns (cell, id, label)."""
    cell, cid, label = wrap.find('mxCell'), wrap.get('id') or '', wrap.get('label') or ''
    for _ in range(16):
        pid = cell.get('parent') if cell is not None else None
        if not pid:
            break
        hit = src.xpath('//diagram[@name=' + M.q(tab) + ']//*[@id=' + M.q(pid) + ']')
        if not hit:
            break
        el = hit[0]
        pcell = el.find('mxCell') if el.tag in _WRAP else el
        if not _is_group(pcell):
            break
        cell, cid = pcell, pid
        label = (el.get('label') if el.tag in _WRAP else pcell.get('value')) or ''
    return cell, cid, label


def own_text(src, cell, cid):
    """v0.2.25 (.193): (fontColor, textOpacity) of a picture bubble's own bubble - the first cell
    that is neither a group nor a picture, the top cell first, then its cells in document order
    (depth first); with none, the top cell's own (a single picture cell).  '' where unset."""
    def pick(c):
        st = c.get('style') or ''
        return (M.style_get(st, 'fontColor', ''), M.style_get(st, 'textOpacity', ''))

    def is_img(c):
        return re.search(r'(^|;)image=', c.get('style') or '') is not None

    def walk(c, i, depth):
        if not _is_group(c) and not is_img(c):
            return pick(c)
        if depth < 8:
            for k in src.children(i):
                r = walk(k, cell_id(k), depth + 1)
                if r is not None:
                    return r
        return None

    if cell is None:
        return '', ''
    r = walk(cell, cid, 0)
    if r is None:
        r = pick(cell) if not _is_group(cell) else ('', '')
    font, op = r
    if font.lower() in ('none', 'default'):
        font = ''
    return font, op


def cell_label(cell):
    p = cell.getparent()
    if p is not None and p.tag in _WRAP:
        return p.get('label') or ''
    return cell.get('value') or ''


# ------------------------------------------------------------------- recolour
_NAMED = {'black': 0x000000, 'white': 0xFFFFFF, 'red': 0xFF0000, 'green': 0x008000, 'lime': 0x00FF00,
          'blue': 0x0000FF, 'yellow': 0xFFFF00, 'cyan': 0x00FFFF, 'aqua': 0x00FFFF, 'magenta': 0xFF00FF,
          'fuchsia': 0xFF00FF, 'gray': 0x808080, 'grey': 0x808080, 'silver': 0xC0C0C0, 'maroon': 0x800000,
          'olive': 0x808000, 'navy': 0x000080, 'purple': 0x800080, 'teal': 0x008080, 'orange': 0xFFA500}
_SKIP = ('none', 'transparent', 'inherit', 'initial', 'unset', 'revert', 'context', 'var', 'url')
_COLOR_RX = re.compile(r'(?i)((?<![\w-])(?:fill|stroke|stop-color|flood-color|lighting-color|color)'
                       r'\s*(?:=\s*["\']|:)\s*)(#[0-9a-f]+|rgba?\([^)]*\)|[a-z]+)')


def _alpha_of(tok):
    """The alpha part a token carries (#rrggbbaa, #rgba, rgba(...,a)), kept on recolouring."""
    t = tok.lower()
    m = re.fullmatch(r'#([0-9a-f]+)', t)
    if m:
        h = m.group(1)
        return ('a' + h[3] * 2) if len(h) == 4 else ('a' + h[6:]) if len(h) == 8 else ''
    m = re.fullmatch(r'rgba?\((.*)\)', t)
    if m:
        parts = [x for x in re.split(r'[\s,/]+', m.group(1).strip()) if x]
        return ('r' + parts[3]) if len(parts) >= 4 else ''
    return ''


def recolor_svg(svg, rgb):
    """Every colour of the SVG -> rgb (0xRRGGBB), 'none' / url() etc. kept, alpha parts kept;
    a root without fill gets fill=rgb (shapes without a fill are black)."""
    hexc = '#%06x' % rgb

    def rep(m):
        tok = m.group(2)
        low = tok.lower()
        if low in _SKIP:
            return m.group(0)
        if not (low.startswith('#') or low.startswith('rgb') or low in _NAMED or low == 'currentcolor'):
            if not re.fullmatch(r'[a-z]+', low):
                return m.group(0)
        a = _alpha_of(tok)
        if a.startswith('r'):
            new = 'rgba(%d,%d,%d,%s)' % ((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255, a[1:])
        else:
            new = hexc + (a[1:] if a else '')
        return m.group(1) + new
    out = _COLOR_RX.sub(rep, svg)
    m = re.search(r'(?i)<svg\b[^>]*>', out)
    if m and not re.search(r'(?i)\sfill\s*=', m.group(0)):
        tag = re.sub(r'(?i)^<svg\b', '<svg fill="%s"' % hexc, m.group(0), count=1)
        out = out[:m.start()] + tag + out[m.end():]
    return out


def recolor_raster(data, rgb):
    """PNG (or any raster PIL reads) -> PNG bytes with every pixel's colour rgb, alpha kept."""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert('RGBA')
    solid = Image.new('RGBA', im.size, ((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255, 255))
    solid.putalpha(im.getchannel('A'))
    buf = io.BytesIO()
    solid.save(buf, 'PNG')
    return buf.getvalue()


def recolor_image_style(st, rgb):
    """The style's image=data:… recoloured; (style, '') or (style unchanged, why not)."""
    m = re.search(r'(^|;)image=data:image/([a-zA-Z0-9.+-]+),([^;]*)', st)
    if not m:
        return st, 'its picture is not embedded (a link, not data)' if 'image=' in st else ''
    kind, payload = m.group(2).lower(), m.group(3)
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception:                      # an SVG kept URL-encoded (%3Csvg…)
        raw = urllib.parse.unquote_to_bytes(payload)
    try:
        if kind.startswith('svg'):
            new = recolor_svg(raw.decode('utf-8', 'replace'), rgb).encode('utf-8')
            mime = 'svg+xml'
        else:
            new, mime = recolor_raster(raw, rgb), 'png'
    except Exception as e:                 # a broken picture: leave it as drawn
        return st, f'its picture could not be read ({type(e).__name__})'
    data = base64.b64encode(new).decode('ascii')         # draw.io's form: data:image/…,<base64>
    return st[:m.start()] + m.group(1) + 'image=data:image/' + mime + ',' + data + st[m.end():], ''


def parse_rgb(c):
    c = (c or '').strip().lstrip('#')
    if re.fullmatch(r'[0-9a-fA-F]{3}', c):
        c = ''.join(ch * 2 for ch in c)
    return int(c, 16) if re.fullmatch(r'[0-9a-fA-F]{6}', c) else None
