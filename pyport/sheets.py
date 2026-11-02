"""The run's shared outputs: the legend (RenderLegend), the cheat sheet (ParseGrid, CheatsheetIdx,
BuildCheatsheet, CsImgFor / CsImgOut), the sheet of all layers (ExportMosaic, MosaicStrips,
BackupRunName) and the image backup (ExportBackupZip).

Drawing follows images.py's GDI+ model: a bitmap drawn onto an empty one loses one level of
partial alpha (draw_on_empty); drawn onto pixels, it blends in linear light (over_u8);
scaled, it is HighQualityBicubic (Pillow's bicubic, prefiltered when shrinking).
"""
import datetime, os, re, struct, zipfile, zlib
import numpy as np
from PIL import Image
import model as M
import layout as LY
import images as IM
from util import crc32_hex, to_num, is_number, fmt4

Image.MAX_IMAGE_PIXELS = None


# ------------------------------------------------------------------ the grid
def parse_grid(spec):
    """ParseGrid: '(0,16,6),(15,18*,25)' -> rows of {'idx', 'legend'}; Die on a bad grid."""
    rows = []
    for chunk in spec.split(')'):
        chunk = chunk.strip(' ,\t').replace('(', '')
        if chunk == '':
            continue
        cells = []
        for tok in chunk.split(','):
            tok = tok.strip()
            if tok == '':
                continue
            leg = '*' in tok
            if leg:
                tok = tok.replace('*', '').strip()
            if not re.fullmatch(r'\d+', tok):
                raise M.Die(f"Cheat-sheet grid has an unreadable entry: '{tok}'\n\nUse indices like "
                            "(0,16,6),(15,18*,25) - digits, optional '*'.")
            cells.append({'idx': int(tok), 'legend': leg})
        if cells:
            rows.append(cells)
    if not rows:
        raise M.Die('Cheat-sheet grid is empty. Set [cheatsheet] Grid in the INI.')
    cols = len(rows[0])
    if any(len(r) != cols for r in rows):
        raise M.Die('Cheat-sheet grid rows are uneven - every row must hold the same number of '
                    f'layers.\n\nFirst row has {cols}.')
    return rows


def cheatsheet_idx(spec):
    """CheatsheetIdx: the layer indices the grid shows (empty when there is no grid)."""
    if spec.strip() == '':
        return {}
    return {c['idx']: True for row in parse_grid(spec) for c in row}


def _abs(cfg, p):
    """A path as the script resolves it: relative = from the script's folder (its working dir)."""
    return p if (re.match(r'^([A-Za-z]:|\\|/)', p) or p == '') else os.path.join(cfg.base_dir, p)


def cs_img_for(cfg, sx):
    """CsImgFor: [cheatsheet] ImagePath with the folder suffix sx before its extension."""
    p = cfg.cs_imgpath
    if sx == '' or p == '':
        return p
    d, name = os.path.split(p.replace('/', '\\'))
    stem, ext = (name.rsplit('.', 1) + [''])[:2] if '.' in name else (name, '')
    return (d + '\\' if d else '') + stem + sx + ('.' + ext if ext else '')


def cs_img_out(cfg):
    return cs_img_for(cfg, cfg.out_sfx())


# ------------------------------------------------------------- GDI+ drawing
def _resize(img, w, h):
    """img scaled to w x h as GDI+ draws it (HighQualityBicubic), not yet put anywhere."""
    if img.shape[1] == w and img.shape[0] == h:
        return img
    return np.asarray(Image.fromarray(img, 'RGBA').resize((w, h), Image.BICUBIC)).copy()


def _draw(canvas, img, x, y, w, h):
    """Gdip.Draw(g, img, x, y, w, h) onto canvas (uint8 RGBA, in place): onto its empty pixels as
    onto a new bitmap, onto drawn ones blended."""
    top = _resize(img, w, h)
    H, W = canvas.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    t = top[y0 - y:y1 - y, x0 - x:x1 - x]
    sub = canvas[y0:y1, x0:x1]
    empty = sub[..., 3] == 0
    if empty.all():
        sub[:] = IM.draw_on_empty(t)
        return
    res = IM.over_u8(sub, t)
    res[empty] = IM.draw_on_empty(t)[empty]
    sub[:] = res


def _ahk_num(v):
    """A number as AHK prints a value read from the INI (the string itself when it was one)."""
    if isinstance(v, str):
        return v
    return str(int(v)) if float(v).is_integer() else repr(float(v))


# ---------------------------------------------------------------- the legend
def _esc(v):
    return v.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _xml(el):
    """An element as MSXML's .xml gives it (whitespace-only text dropped on load)."""
    a = ''.join(f' {k}="{_esc(v)}"' for k, v in el.attrib.items())
    kids = [c for c in el if isinstance(c.tag, str)]
    if not kids:
        return f'<{el.tag}{a}/>'
    return f'<{el.tag}{a}>' + ''.join(_xml(c) for c in kids) + f'</{el.tag}>'


def subtree_xml(doc, node):
    """SubtreeXml: a node and everything nested under it (children point at it by parent)."""
    s = _xml(node)
    for ch in doc.xpath('//mxCell[@parent=' + M.q(node.get('id')) + ']'):
        s += subtree_xml(doc, ch)
    return s


def legend_key(cfg, shapes, src, grp, version):
    """RenderLegend's cache key (its CRC goes to [cache<sfx>] legend).  version is the exe's own,
    so a key from the AHK script never matches: switching between the two re-exports once."""
    key = f'v={version};s={_ahk_num(cfg.scale)};k={LY.render_style_tag(cfg, shapes)}\n{subtree_xml(src, grp)}'
    if cfg.caps_like():
        key += '\n' + LY.roles_sig(cfg, src)
    return key


def legend_canvas(cfg, box, pad_r, pad_b):
    return '/'.join([LY.box_str(box), str(pad_r), str(pad_b)] + [_ahk_num(v) for v in (
        cfg.sh_dist, cfg.sh_angle, cfg.sh_blur, cfg.sh_opacity)] + [cfg.sh_colour])


def render_legend(cfg, ctx, src, export, raw_dir, box, pad_r, pad_b, version, force=True,
                  cache_sec='cache'):
    """RenderLegend: foreground<sfx>\\legend.png, or '' when there is no legend group.
    export(page_doc, out_png) draws a page (the draw.io helper; raises on failure).  The raw
    (bg_legend.png) is redrawn only when forced, missing or its key changed; it is always
    composed again onto the current box."""
    import pages as P
    import shade as SH
    raw = os.path.join(raw_dir, 'bg_legend.png')
    grp = P.legend_group(cfg, src)
    if grp is None:
        return ''
    crc = crc32_hex(legend_key(cfg, ctx.shapes, src, grp, version))
    old = cfg.ini.read(cache_sec, 'legend', '')
    out = os.path.join(cfg.out_dir('foreground'), 'legend.png')
    canv = legend_canvas(cfg, box, pad_r, pad_b)
    if (not force and old == crc and not os.path.exists(raw) and os.path.exists(out)
            and cfg.ini.read(cache_sec, 'legendcanvas', '') == canv):
        return out
    if force or not os.path.exists(raw) or old != crc:
        page, chips = P.build_legend_page(cfg, ctx, src, [])
        os.makedirs(raw_dir, exist_ok=True)
        export(page, raw)
        if cfg.key_style == 'render' and chips:
            shaded = SH.shade_raw(cfg, ctx.shapes, IM.load(raw), chips)
            if shaded is not None:
                IM.save(shaded, raw)
        cfg.ini.write(crc, cache_sec, 'legend')
        try:
            os.remove(os.path.join(raw_dir, 'bg_legend.key'))
        except OSError:
            pass
    os.makedirs(os.path.dirname(out), exist_ok=True)
    IM.save(IM.compose(cfg, IM.load(raw), None, box, pad_r, pad_b), out)
    cfg.ini.write(canv, cache_sec, 'legendcanvas')
    return out


# ----------------------------------------------------------- the cheat sheet
def build_cheatsheet(cfg, grid, legend_png, warn):
    """BuildCheatsheet: the montage of the grid's layers (each scaled by Zoom / Scale), the legend
    over starred cells.  Returns {'w', 'h'} or '' when no listed layer has a PNG."""
    if cfg.cs_imgpath == '':
        raise M.Die('Cheat-sheet image path is empty. Set [cheatsheet] ImagePath.')
    cs_dir = cfg.out_dir('cheatsheet') if cfg.combo_list_cs != cfg.combo_list_fg else cfg.out_dir('foreground')
    quiet = cfg.combo_list_cs == cfg.combo_list_fg and cfg.cs_quiet_shadow()
    csk = to_num(cfg.cs_zoom) / to_num(cfg.scale)
    bmp, cw, ch, missing = {}, 0, 0, []
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            f = os.path.join(cs_dir, f"{cell['idx']}.png")
            if quiet:
                qf = os.path.join(cfg.out_dir('cheatsheet'), f"{cell['idx']}.png")
                # FileGetTime: whole seconds
                if os.path.exists(qf) and os.path.exists(f) and int(os.path.getmtime(qf)) >= int(os.path.getmtime(f)):
                    f = qf
            if not os.path.exists(f):
                missing.append(cell['idx'])
                continue
            b = IM.load(f)
            bmp[(r, c)] = b
            cw, ch = max(cw, b.shape[1]), max(ch, b.shape[0])
    if not bmp:
        warn.append('cheat-sheet not written - none of the listed layers have a rendered PNG yet.')
        return ''
    if missing:
        seen = list(dict.fromkeys(missing))
        warn.append('cheat-sheet left gaps for layer(s) ' + ', '.join(map(str, seen))
                    + ' - not drawn yet, or skipped above for a key-layout problem.')
    rows, cols = len(grid), len(grid[0])
    scw, sch = max(1, M.round_ahk(cw * csk)), max(1, M.round_ahk(ch * csk))
    img_w = M.round_ahk(cols * scw + (cols - 1) * cfg.cs_padh)
    img_h = M.round_ahk(rows * sch + (rows - 1) * cfg.cs_padv)
    canvas = np.zeros((img_h, img_w, 4), np.uint8)
    leg = IM.load(legend_png) if (legend_png and os.path.exists(legend_png)) else None
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if (r, c) not in bmp:
                continue
            dx, dy = M.round_ahk(c * (scw + cfg.cs_padh)), M.round_ahk(r * (sch + cfg.cs_padv))
            _draw(canvas, bmp[(r, c)], dx, dy, scw, sch)
            if cell['legend'] and leg is not None:
                _draw(canvas, leg, dx, dy, scw, sch)
    out = _abs(cfg, cs_img_out(cfg)).replace('\\', os.sep)
    if os.path.dirname(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
    IM.save(canvas, out)
    return {'w': img_w, 'h': img_h}


# ------------------------------------------------- the sheet of all layers
def backup_run_name(cfg, d, last_bak=''):
    """BackupRunName: the source backup this run made, else the next free
    source_diagram_<yyyyMMdd>_<nn> in backup\\ (.drawio) and in d (.png, .zip)."""
    if last_bak:
        return os.path.splitext(os.path.basename(last_bak.replace('\\', os.sep)))[0]
    base = 'source_diagram_' + datetime.datetime.now().strftime('%Y%m%d')
    nn = 1
    while any(os.path.exists(p) for p in (
            os.path.join(cfg.base_dir, 'backup', f'{base}_{nn:02d}.drawio'),
            os.path.join(d, f'{base}_{nn:02d}.png'), os.path.join(d, f'{base}_{nn:02d}.zip'))):
        nn += 1
    return f'{base}_{nn:02d}'


class PngStripWriter:
    """An RGBA PNG written a band of rows at a time (MosaicStrips' WIC encoder), so the whole
    sheet is never in memory."""
    def __init__(self, path, w, h, level=6):
        self.f = open(path, 'wb')
        self.w, self.h, self.rows = w, h, 0
        self.z = zlib.compressobj(level)
        self.f.write(b'\x89PNG\r\n\x1a\n')
        self._chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))

    def _chunk(self, kind, data):
        self.f.write(struct.pack('>I', len(data)) + kind + data
                     + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF))

    def write(self, band):
        """band: rows x w x 4 uint8 RGBA."""
        assert band.shape[1] == self.w
        raw = np.zeros((band.shape[0], self.w * 4 + 1), np.uint8)      # filter byte 0 (none)
        raw[:, 1:] = band.reshape(band.shape[0], -1)
        data = self.z.compress(raw.tobytes())
        if data:
            self._chunk(b'IDAT', data)
        self.rows += band.shape[0]

    def close(self):
        assert self.rows == self.h, (self.rows, self.h)
        self._chunk(b'IDAT', self.z.flush())
        self._chunk(b'IEND', b'')
        self.f.close()


def export_mosaic(cfg, src, warn, last_bak=''):
    """ExportMosaic: every layer's foreground PNG where the layer sits on the source's page
    grid, at MosaicScale % of draw.io's 500 %, in backup\\exported_png\\<run name>.png.
    Returns the file or ''."""
    pg = M.page_grid(src)
    cols = pg['cols']
    fg = cfg.out_dir('foreground')
    imgs = [(L['idx'], os.path.join(fg, f"{L['idx']}.png")) for L in M.valid_layer_groups(src)]
    imgs = [it for it in imgs if os.path.exists(it[1])]
    if not imgs:
        warn.append('the sheet of all layers was not made: no layer has a foreground PNG yet.')
        return ''
    k = to_num(cfg.mosaic_pct) / 100 * 5 / to_num(cfg.scale)
    max_c = max(i % cols for i, _ in imgs)
    max_r = max(i // cols for i, _ in imgs)
    with Image.open(imgs[0][1]) as im0:
        w0, h0 = im0.size
    d = os.path.join(cfg.base_dir, 'backup', 'exported_png')
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, backup_run_name(cfg, d, last_bak) + '.png')
    dw, dh = max(1, M.round_ahk(w0 * k)), max(1, M.round_ahk(h0 * k))
    step_x = max(dw, M.round_ahk(pg['pw'] * to_num(cfg.scale) * k))
    step_y = max(dh, M.round_ahk(pg['ph'] * to_num(cfg.scale) * k))
    sw, sh = max_c * step_x + dw, max_r * step_y + dh
    if os.path.exists(out):
        os.remove(out)
    try:
        wr = PngStripWriter(out, sw, sh)
        y0 = 0
        while y0 < sh:
            bh, r = min(step_y, sh - y0), y0 // step_y
            strip = np.zeros((bh, sw, 4), np.uint8)
            for idx, f in imgs:
                if idx // cols == r:
                    _draw(strip, IM.load(f), (idx % cols) * step_x, 0, dw, dh)
            wr.write(strip)
            y0 += bh
        wr.close()
        return out
    except (MemoryError, OSError) as e:
        try:
            os.remove(out)
        except OSError:
            pass
        warn.append(f'the sheet of all layers was not made: {e}. Lower [export] MosaicScale '
                    f'(now {cfg.mosaic_pct}%).')
        return ''


# ---------------------------------------------------------- the image backup
def export_backup_zip(cfg, warn, last_bak=''):
    """ExportBackupZip: the foreground PNGs of [export] BackupLayers in
    backup\\exported_png\\<run name>.zip.  Returns (file or '', how many layers)."""
    from util import layer_spec_parse
    want = layer_spec_parse(cfg.backup_layers)
    if not want:
        return '', 0
    fg = cfg.out_dir('foreground')
    names = [f'{i}.png' for i in sorted(want) if os.path.exists(os.path.join(fg, f'{i}.png'))]
    if not names:
        warn.append(f'no backup zip: none of the backup layers ({cfg.backup_layers}) has a foreground PNG yet.')
        return '', 0
    d = os.path.join(cfg.base_dir, 'backup', 'exported_png')
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, backup_run_name(cfg, d, last_bak) + '.zip')
    try:
        if os.path.exists(out):
            os.remove(out)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for n in names:
                z.write(os.path.join(fg, n), n)
        return out, len(names)
    except OSError as e:
        try:
            os.remove(out)
        except OSError:
            pass
        warn.append(f'the backup zip was not made: {e}.')
        return '', 0
