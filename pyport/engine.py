"""The export engine: Main of the .148 script from after the layer picker to the end message
(option B of §24: the AHK script keeps the source rewrite, the marks, the picker and the
merged preview, and calls this for the rest).

    png-overlay-export export --ini <INI> --ahk <script .ah2> --layout <name> --layers 0,3,16
                              [--recomp] [--all-run [--last]] [--last-bak <file>]
                              [--drawio <folder or app.asar>] [--progress <file>] [--result <file>]

--ahk: the AHK script, read for its built-in shapes, CAP_WARP and POS_LABEL (one source of
       truth while both exist).
--recomp: the background / full-key shadow settings changed: every layer is composed again.
--all-run: one target of Run all (a summary line instead of the message); --last: its last
       target (the backup zip and the sheet of all layers are made then).
--progress: the latest '<pct>\\t<text>' (AHK's UiSay), rewritten as the run goes.
--result: JSON {ok, message, line, warnings, images, mirrored}.  Exit 0 = done, 2 = stopped
       with a message (Die), 1 = crashed.
"""
import argparse, json, math, os, shutil, sys, time, traceback
from lxml import etree

import config, model as M, layout as LY, pages as P, combos as CB, mirror as MR
import images as IM, render_shade as RS, shade as SH, keys as K, legend3d as L3, sheets as S
import capkeys as CK
from util import to_num

VERSION = 'py-0.1.2 (2025-07-30.148)'


# ---------------------------------------------------------------- reporting
class Progress:
    def __init__(self, path=None):
        self.path = path

    def say(self, text, pct=None):
        """The latest line for AHK.  Never stops the run: on Windows the swap fails while AHK
        has the file open to read it (it polls 5 times a second), so it is retried briefly
        and otherwise skipped - the next line will get through."""
        line = ('' if pct is None else str(pct)) + '\t' + text.replace('\n', ' | ')
        try:
            print(line, flush=True)
        except Exception:                                # noqa: BLE001 - no console
            pass
        if not self.path:
            return
        tmp = self.path + '.part'
        for _ in range(10):
            try:
                with open(tmp, 'w', encoding='utf-8') as f:
                    f.write(line)
                os.replace(tmp, self.path)
                return
            except OSError:
                time.sleep(0.02)


def run_time(sec):
    """RunTime."""
    sec = M.round_ahk(sec)
    if sec < 60:
        return f'{sec} s'
    if sec < 3600:
        return f'{sec // 60} min {sec % 60:02d} s'
    return f'{sec // 3600} h {(sec // 60) % 60:02d} min'


# ----------------------------------------------------------------- draw.io
class Exporter:
    """ExportPng through the draw.io helper (one browser for the run, started on first use).
    With Debug on, the page is also kept as <out>.drawio (.148)."""
    def __init__(self, cfg, drawio):
        self.cfg, self.drawio, self.r, self.n = cfg, drawio, None, 0

    def __call__(self, page, out_png, label=''):
        import drawio_helper as DH
        xml = etree.tostring(page, encoding='unicode')
        if self.cfg.debug_export:
            with open(out_png[:-4] + '.drawio', 'w', encoding='utf-8') as f:
                f.write(xml)
        err = None
        for attempt in range(2):                         # one plain retry, as TryExportPng
            try:
                if self.r is None:
                    self.r = DH.Renderer(self.drawio)
                png = self.r.render(xml, scale=self.cfg.scale, transparent=True)
                tmp = out_png + '.part'
                with open(tmp, 'wb') as f:
                    f.write(png)
                os.replace(tmp, out_png)
                self.n += 1
                return
            except Exception as e:                       # noqa: BLE001 - reported below
                err = e
                if self.r is not None:
                    self.r.close()
                    self.r = None
        raise M.Die(f'draw.io did not produce:\n{out_png}\n\n({label})\n\nThe helper said:\n{err}')

    def close(self):
        if self.r is not None:
            self.r.close()
            self.r = None


def _copy_doc(doc):
    return etree.fromstring(etree.tostring(doc))


# ------------------------------------------------------------------- engine
class Run:
    def __init__(self, cfg, shapes, export, progress):
        self.cfg, self.shapes, self.export, self.ui = cfg, shapes, export, progress
        self.ctx = P.Ctx(cfg, shapes)

    def page(self, L, layout, role, warn, src):
        """BuildPage's document (Render: the fg rings left out; Compose draws them)."""
        out = P.build_page_doc(self.cfg, self.ctx, L, layout, role, warn, src)
        if self.cfg.key_style == 'render' and role != 'bg':
            for c in out.xpath("//mxCell[starts-with(@id,'fg-r')]"):
                c.getparent().remove(c)
        return out

    def cap_warp_bg(self, L, layout, warn, raw, tag, src):
        """CapWarpBg: the background in three pages (caps, text, rims), the text bent."""
        doc = P.build_page_doc(self.cfg, self.ctx, L, layout, 'bg', warn, src)
        parts = {}
        for part, what in (('c', 'caps'), ('t', 'text'), ('r', 'rims')):
            d = _copy_doc(doc)
            CK.cap_split_page(d, part)
            parts[part] = raw[:-4] + f'_{part}.png'
            self.export(d, parts[part], f'{tag} ({what})')
        keys = K.warp_keys(self.cfg, src, L, self.shapes)
        bent, _ = L3.compose_warp(*(IM.load(parts[p]) for p in 'ctr'), keys, to_num(self.cfg.cap_text_warp) / 3)
        IM.save(bent, raw)

    def render_bg(self, L, layout, warn, raw, tag, src, role):
        """One raw page: bg (split when Legend 3D is on), bgg, fg or cs; the Render shading on bg."""
        cfg = self.cfg
        cfg.cap_glass_nobg = role == 'bgg'
        brole = 'bg' if role == 'bgg' else role
        try:
            if brole == 'bg' and cfg.caps_like() and to_num(cfg.cap_text_warp) > 0:
                self.cap_warp_bg(L, layout, warn, raw, tag, src)
            else:
                self.export(self.page(L, layout, brole, warn, src), raw, tag)
        finally:
            cfg.cap_glass_nobg = False
        if role == 'bg' and cfg.key_style == 'render':
            out = SH.shade_raw(cfg, self.shapes, IM.load(raw), SH.render_items(cfg, src, L, 'caps'))
            if out is None:
                return False
            IM.save(out, raw)
        return True

    def compose(self, base, overlay, out, box, pr, pb, shadow, keys, rings=None):
        cfg, shapes = self.cfg, self.shapes
        draw = (lambda f, rs, kx, ky, sx, sy: RS.draw_items(f, rs, kx, ky, SH.Params(cfg), shapes, sx, sy))
        img = IM.compose(cfg, IM.load(base), IM.load(overlay) if overlay else None, box, pr, pb, shadow,
                         keys or None, rings or None, draw)
        IM.save(img, out)

    def mirror_layer(self, L, m, layout, warn, raw_dir, box, pr, pb, tag, cm=None):
        """MirrorLayer: <N>m.png from the source with the layer's keys swapped."""
        cfg = self.cfg
        r = MR.mirror_source(cfg, cfg.src_drawio, L, m, layout, cm, None)
        if r is None:
            warn.append(f"layer {tag}: none of its mirrored positions was found - no {L['idx']}m.png made.")
            return False
        src_m, Lm, layout_m = r
        roles = ['bg', 'fg'] + (['bgg'] if cfg.glass_bg_split() else [])
        raws = {}
        for role in roles:
            raw = os.path.join(raw_dir, f"m{role}_{L['idx']}.png")
            what = {'fg': 'foreground', 'bgg': 'background without glass'}.get(role, 'background')
            self.ui.say(f'{tag}\nrendering the mirrored {what}')
            self.render_bg(Lm, layout_m, warn, raw, f'{tag} (mirrored)', src_m, role)
            raws[role] = raw
        sh_k = IM.shadow_keys(cfg, src_m, Lm, self.shapes) if cfg.sh_fullkeys else None
        rk = SH.render_items(cfg, src_m, Lm, 'rings') if cfg.key_style == 'render' else None
        self.compose(raws.get('bgg', raws['bg']), None, os.path.join(cfg.out_dir('background'), f"{L['idx']}m.png"),
                     box, pr, pb, cfg.sh_on_bg, sh_k)
        self.compose(raws['bg'], raws['fg'], os.path.join(cfg.out_dir('foreground'), f"{L['idx']}m.png"),
                     box, pr, pb, True, sh_k, rk)
        return True


def export(cfg, shapes, export_fn, ui, selected, recomp_all=False, all_run=False, last=True, last_bak='',
           label=None, ignore=()):
    """Main after the picker.  selected: the layer indices to export.  Returns (message, line,
    warnings, images, mirrored)."""
    t0 = time.time()
    R = Run(cfg, shapes, export_fn, ui)
    osx = cfg.out_sfx()
    warn = []
    ui.say('Reading combos', 2)
    layout = CB.read_layout(cfg, ignore)
    ui.say('Loading source diagram\n' + os.path.basename(cfg.src_drawio), 5)
    src = M.Doc(M.load_xml(cfg.src_drawio))

    style_now = LY.render_style_tag(cfg, shapes)
    bg_sh_now = '1' if cfg.sh_on_bg else '0'
    bg_sh_was = cfg.ini.read('state', 'RenderedBgShadow' + osx, '1' if osx == '' else bg_sh_now)
    fk_now = ('1/' + (cfg.sh_keyinset or 'auto')) if cfg.sh_fullkeys else '0'
    fk_was = cfg.ini.read('state', 'RenderedFullKeys' + osx, '0' if osx == '' else fk_now)
    style_was = cfg.ini.read('state', 'RenderedStyle' + osx, 'drawio' if osx == '' else style_now)

    ui.say('Scanning for layer groups...', 8)
    skipped = {}
    layers = M.discover(src, warn, skipped)
    if not layers:
        raise M.Die('No source layers found. A layer needs a "N. NAME" title cell.')
    selected = {i for i in selected if any(L['idx'] == i for L in layers)}
    if not selected:
        raise M.Die('No layers selected.')
    if style_now != style_was and skipped:
        warn.append(f'{len(skipped)} layer(s) skipped for their key layout keep their PNGs in the previous '
                    f'style ({LY.render_style_name(style_was)}).')
    recomp = {L['idx'] for L in layers} if recomp_all else set()

    for kind in ('background', 'foreground'):
        os.makedirs(cfg.out_dir(kind), exist_ok=True)
    split_cs = cfg.combo_list_cs != cfg.combo_list_fg
    if split_cs or cfg.cs_quiet_shadow():
        os.makedirs(cfg.out_dir('cheatsheet'), exist_ok=True)
    ta_dir = cfg.out_dir('testalignment')
    if cfg.debug_export:
        os.makedirs(ta_dir, exist_ok=True)
    raw_dir = cfg.out_dir('_raw')
    os.makedirs(raw_dir, exist_ok=True)

    cs_idx = S.cheatsheet_idx(cfg.cs_grid) if split_cs else {}
    cs_grid = S.cheatsheet_idx(cfg.cs_grid) if cfg.cs_quiet_shadow() else {}
    total = len(layers) * (3 if cfg.glass_bg_split() else 2) + sum(1 for L in layers if L['idx'] in cs_idx)
    done, box = 0, None
    cache_sec = 'cache' + osx
    ext = LY.load_extents(cfg, cache_sec, os.path.join(raw_dir, 'extents.txt'))

    # ---- pass 1: every layer's extent, exporting only what is needed
    for L in layers:
        tag = f"{L['idx']}. {L['name']}"
        sel = L['idx'] in selected
        for role in cfg.render_roles(L['idx'], cs_idx):
            if role == 'bgg' and not sel and L['idx'] not in recomp:
                done += 1
                continue
            key = f"{L['idx']}|{role}"
            raw = os.path.join(raw_dir, f"{role}_{L['idx']}.png")
            must = sel or key not in ext or (L['idx'] in recomp and not os.path.exists(raw))
            pct = 8 + M.round_ahk(done / total * 55)
            if must:
                what = {'bg': 'background', 'bgg': 'background without glass', 'cs': 'cheat-sheet foreground'}.get(role, 'foreground')
                ui.say(f'({done + 1}/{total})  {tag}\nrendering {what}', pct)
                if not R.render_bg(L, layout, warn, raw, tag, src, role):
                    warn.append(f'layer {tag}: the Render shading was left out - its image is not the size '
                                'the page frame gives at this zoom.')
                b = IM.alpha_box(IM.load(raw))
                ext[key] = b
            else:
                ui.say(f'({done + 1}/{total})  {tag}\nusing cached extent', pct)
                b = ext[key]
            if b:
                box = LY.union_box(box, b)
            done += 1
    LY.save_extents(cfg, cache_sec, ext)

    full = len(selected) == len(layers)
    if split_cs and cs_idx and not full:
        warn.append('the cheat sheet is being rendered separately from the overlay, which changes the shared '
                    'box every layer is cropped to. Run once with "All" so the unselected layers are rebuilt '
                    'against it.')
    if not full:
        prev = LY.box_parse(cfg.ini.read(cache_sec, 'box', ''))
        if prev is None and os.path.exists(os.path.join(raw_dir, 'box.txt')):
            prev = LY.box_parse(open(os.path.join(raw_dir, 'box.txt'), encoding='utf-8-sig').read())
        if prev:
            box = LY.union_box(box, prev)
    if not box:
        raise M.Die('Every layer rendered blank. Check that the source groups actually contain artwork.')
    cfg.ini.write(LY.box_str(box), cache_sec, 'box')
    cw, ch = box['x2'] - box['x1'] + 1, box['y2'] - box['y1'] + 1
    ui.say(f'Common content box: {cw} x {ch} px\ncasting shadows', 66)
    pr, pb = IM.shadow_pad(cfg)

    # ---- pass 2: compose the selected layers (all of them after a shadow change)
    mir_sets, cm_sets = MR.mirror_load(cfg), MR.mirror_combo_load(cfg)
    todo = [L for L in layers if L['idx'] in selected or L['idx'] in recomp]
    mir_n = 0
    for i, L in enumerate(todo, 1):
        idx, tag = L['idx'], f"{L['idx']}. {L['name']}"
        ui.say(f'({i}/{len(todo)})  {tag}\ncompositing', 66 + M.round_ahk(i / len(todo) * 32))
        bg, fg = os.path.join(raw_dir, f'bg_{idx}.png'), os.path.join(raw_dir, f'fg_{idx}.png')
        bg_out = os.path.join(cfg.out_dir('background'), f'{idx}.png')
        fg_out = os.path.join(cfg.out_dir('foreground'), f'{idx}.png')
        sh_k = IM.shadow_keys(cfg, src, L, shapes) if cfg.sh_fullkeys else None
        rk = SH.render_items(cfg, src, L, 'rings') if cfg.key_style == 'render' else None
        bgg = os.path.join(raw_dir, f'bgg_{idx}.png')
        R.compose(bgg if (cfg.glass_bg_split() and os.path.exists(bgg)) else bg, None, bg_out, box, pr, pb,
                  cfg.sh_on_bg, sh_k)
        R.compose(bg, fg, fg_out, box, pr, pb, True, sh_k, rk)
        cs_out = os.path.join(cfg.out_dir('cheatsheet'), f'{idx}.png')
        if split_cs and idx in cs_idx:
            cs = os.path.join(raw_dir, f'cs_{idx}.png')
            if os.path.exists(cs):
                R.compose(bg, cs, cs_out, box, pr, pb, True,
                          IM.shadow_keys(cfg, src, L, shapes, True) if idx in cs_grid else sh_k, rk)
        elif idx in cs_grid:
            R.compose(bg, fg, cs_out, box, pr, pb, True, IM.shadow_keys(cfg, src, L, shapes, True), rk)
        if cfg.debug_export:
            shutil.copyfile(bg_out, os.path.join(ta_dir, f'{idx}b.png'))
            shutil.copyfile(fg_out, os.path.join(ta_dir, f'{idx}f.png'))
        if idx in mir_sets:
            if R.mirror_layer(L, mir_sets[idx], layout, warn, raw_dir, box, pr, pb, tag, cm_sets.get(idx)):
                mir_n += 1
        else:
            for kind in ('background', 'foreground'):
                try:
                    os.remove(os.path.join(cfg.out_dir(kind), f'{idx}m.png'))
                except OSError:
                    pass

    # ---- the legend, the cheat sheet
    ui.say('Rendering legend...', 98)
    legend_png = S.render_legend(cfg, R.ctx, src, lambda pg, out: export_fn(pg, out, 'legend'), raw_dir,
                                 box, pr, pb, VERSION, full, cache_sec)
    try:
        os.remove(os.path.join(cfg.base_dir, '_legend.png'))
    except OSError:
        pass
    cs_info = ''
    if cfg.cs_grid != '':
        grid = S.parse_grid(cfg.cs_grid)
        touched = any(c['idx'] in selected for row in grid for c in row)
        if not touched and os.path.exists(S._abs(cfg, S.cs_img_out(cfg))):
            pass
        else:
            ui.say('Building cheat-sheet montage...', 99)
            need = any(c['legend'] for row in grid for c in row)
            if need and legend_png == '':
                warn.append("cheat-sheet: a layer is starred for the legend overlay but no 444-wide group was "
                            f"found on the '{cfg.cs_legtab}' tab")
            cs_info = S.build_cheatsheet(cfg, grid, legend_png if need else '', warn)

    rl = LY.load_role_layers(cfg, osx)
    if rl & selected:
        LY.save_role_layers(cfg, rl - selected, osx)

    bak_zip, bak_n, mosaic = '', 0, ''
    if not all_run or last:
        ui.say('Zipping the backup layers...', 99)
        bak_zip, bak_n = S.export_backup_zip(cfg, warn, last_bak)
        if cfg.mosaic_sheet:
            ui.say('Saving the sheet of all layers...', 99)
            mosaic = S.export_mosaic(cfg, src, warn, last_bak)
    cfg.ini.write(style_now, 'state', 'RenderedStyle' + osx)
    cfg.ini.write(bg_sh_now, 'state', 'RenderedBgShadow' + osx)
    cfg.ini.write(fk_now, 'state', 'RenderedFullKeys' + osx)
    ui.say(f'Finished - {total} images written.', 100)

    if not cfg.debug_export:
        shutil.rmtree(raw_dir, ignore_errors=True)
        if os.path.isdir(ta_dir):
            import re
            for f in os.listdir(ta_dir):
                if re.fullmatch(r'\d+[bf]\.png', f, re.I):
                    try:
                        os.remove(os.path.join(ta_dir, f))
                    except OSError:
                        pass
            try:
                os.rmdir(ta_dir)
            except OSError:
                pass
    if cfg.key_style == 'render':
        gone = sorted({m['model'] for m in cfg.cap_pos.values()
                       if m['model'] != 'ldsa' and not LY.cap_model_file(cfg, m['model'])})
        if gone:
            warn.append(f"layout {cfg.lay_name}: {', '.join(gone)} not in the capmodels folder - drawn as the LDSA dish.")

    el = time.time() - t0
    fgd = cfg.out_dir('foreground') + os.sep
    line = (f"{label or cfg.lay_name}: {total} images" + (f' + {mir_n} mirrored layer(s)' if mir_n else '')
            + f' in {run_time(el)}, {cw + pr} x {ch + pb} px, {fgd}')
    if cs_info:
        line += '\n    cheat sheet ' + S.cs_img_out(cfg)
    if bak_zip:
        line += f'\n    backup of {bak_n} layer(s): {bak_zip}'
    line += ''.join('\n    - ' + w for w in warn)
    style_changed = style_now != style_was
    msg = (f'Time: {run_time(el)}\nLayout {cfg.lay_name}, key style {LY.render_style_name(style_now)}'
           + (' - its settings changed; layers not exported yet stay marked' if style_changed else '')
           + '\nShadow: foreground' + (' and background' if cfg.sh_on_bg else ' only')
           + (' - changed, every background re-composited' if bg_sh_now != bg_sh_was else '')
           + (', full-key shadows' if cfg.sh_fullkeys else '')
           + (' (new: every layer re-composited)' if fk_now != fk_was else '') + '\n\n'
           + f'{total} images written at {cw + pr} x {ch + pb} px'
           + (f', plus {mir_n} mirrored layer(s) (<N>m.png)' if mir_n else '') + '.\n\n'
           + f'Artwork sits flush at 0,0 - padding is {pr} px right and {pb} px bottom, where the shadow falls.\n\n'
           + cfg.out_dir('background') + os.sep + '\n' + fgd
           + (f'\n{ta_dir}{os.sep}   (Nb.png / Nf.png to check overlap)' if cfg.debug_export
              else f'\n(Debug off: {os.path.basename(raw_dir)} deleted, no testalignment)'))
    if legend_png:
        msg += '\n' + legend_png
    if bak_zip:
        msg += f'\n\nBackup of {bak_n} layer(s):\n{bak_zip}'
    if mosaic:
        msg += '\n\nAll layers on one sheet:\n' + mosaic
    if cs_info:
        msg += f"\n\nCheat sheet: {cs_info['w']} x {cs_info['h']} px\n{S.cs_img_out(cfg)}"
    if warn:
        msg += f'\n\n{len(warn)} warning(s):\n' + ''.join(f'  - {w}\n' for w in warn)
    return msg, line, warn, total, mir_n


# ------------------------------------------------------------------- the CLI
def fontcheck(argv):
    """fontcheck <family> <file of hex code points>: FontCoversCp's answer for each (GDI on
    Windows), as 'XXXX covered|missing' lines; for checking the Linux stand-in list."""
    import fonts as FN
    fam, path = argv[0], argv[1]
    for ln in open(path, encoding='utf-8'):
        ln = ln.strip()
        if ln and ln[0] != ';':
            cp = int(ln.split()[0], 16)
            print(f'{cp:04X} {"covered" if FN._covers(fam, cp) else "missing"}')
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ('render', 'serve'):          # the draw.io helper on its own
        import drawio_helper as DH
        DH.main(argv)
        return 0
    if argv and argv[0] == 'fontcheck':
        return fontcheck(argv[1:])
    if argv and argv[0] in ('--version', 'version'):
        print(VERSION)
        return 0
    ap = argparse.ArgumentParser(prog='png-overlay-export')
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('export')
    e.add_argument('--ini', required=True)
    e.add_argument('--ahk', required=True)
    e.add_argument('--layout', required=True)
    e.add_argument('--layers', required=True)
    e.add_argument('--recomp', action='store_true')
    e.add_argument('--all-run', action='store_true')
    e.add_argument('--last', action='store_true')
    e.add_argument('--last-bak', default='')
    e.add_argument('--label', default=None)
    e.add_argument('--drawio', default=None, help='draw.io folder or app.asar (default: [paths] DrawioExe)')
    e.add_argument('--progress', default=None)
    e.add_argument('--result', default=None)
    a = ap.parse_args(argv)

    res = {'ok': False, 'message': '', 'line': '', 'warnings': [], 'images': 0, 'mirrored': 0}
    code, exporter = 0, None
    try:
        base = os.path.dirname(os.path.abspath(a.ini))
        cfg = config.Cfg(a.ini, base_dir=base)
        if LY.lay_read(cfg, a.layout) is None:
            raise M.Die(f'No layout called "{a.layout}" in {a.ini}.')
        LY.target_set(cfg, a.layout)
        shapes = RS.Shapes(RS.Script(a.ahk), cfg.capmodel_dir, cfg.render_shape)
        drawio = a.drawio or os.path.dirname(cfg.ini.read('paths', 'DrawioExe', ''))
        exporter = Exporter(cfg, drawio)
        sel = {int(t) for t in a.layers.replace(' ', ',').split(',') if t.strip().isdigit()}
        msg, line, warn, total, mir = export(cfg, shapes, exporter, Progress(a.progress), sel, a.recomp,
                                             a.all_run, a.last or not a.all_run, a.last_bak, a.label,
                                             (a.result, a.progress))
        res.update(ok=True, message=msg, line=line, warnings=warn, images=total, mirrored=mir)
    except M.Die as d:
        res['message'], code = str(d), 2
    except Exception:                                    # noqa: BLE001
        res['message'], code = 'Unexpected error - please report it:\n\n' + traceback.format_exc(), 1
    finally:
        if exporter is not None:
            exporter.close()
    if a.result:
        with open(a.result, 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(res['message'] if not res['ok'] else res['line'])
    return code


if __name__ == '__main__':
    sys.exit(main())
