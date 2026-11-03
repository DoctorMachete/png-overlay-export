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

VERSION = 'py-0.2.1 (2025-07-30.148)'


# ---------------------------------------------------------------- reporting
class Progress:
    """The progress file for AHK, plus a log: every line and event with the time since the start
    (log_path, appended; for finding where a run spends its time)."""
    def __init__(self, path=None, log_path=None):
        self.path, self.t0, self.logf = path, time.time(), None
        if log_path:
            try:
                self.logf = open(log_path, 'w', encoding='utf-8', buffering=1)
                self.log(f'{VERSION}  {time.strftime("%Y-%m-%d %H:%M:%S")}  {" ".join(sys.argv[1:])}')
            except OSError:
                self.logf = None

    def log(self, text):
        if self.logf:
            try:
                self.logf.write(f'{time.time() - self.t0:8.2f}  {text}\n')
            except OSError:
                pass

    def say(self, text, pct=None):
        """The latest line for AHK.  Never stops the run: on Windows the swap fails while AHK
        has the file open to read it (it polls 5 times a second), so it is retried briefly
        and otherwise skipped - the next line will get through."""
        line = ('' if pct is None else str(pct)) + '\t' + text.replace('\n', ' | ')
        self.log(line.replace('\t', '  '))
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
    def __init__(self, cfg, drawio, log=None):
        self.cfg, self.drawio, self.r, self.n = cfg, drawio, None, 0
        self.log = log or (lambda t: None)

    def __call__(self, page, out_png, label=''):
        import drawio_helper as DH
        xml = etree.tostring(page, encoding='unicode')
        if self.cfg.debug_export:
            with open(out_png[:-4] + '.drawio', 'w', encoding='utf-8') as f:
                f.write(xml)
        err = None
        for attempt in range(2):                         # one plain retry, as TryExportPng
            try:
                t = time.time()
                if self.r is None:
                    self.r = DH.Renderer(self.drawio)
                    self.log(f'    browser started in {time.time() - t:.2f} s')
                    t = time.time()
                png = self.r.render(xml, scale=self.cfg.scale, transparent=True)
                self.log(f'    draw.io {time.time() - t:5.2f} s  {os.path.basename(out_png)}  ({label})')
                tmp = out_png + '.part'
                with open(tmp, 'wb') as f:
                    f.write(png)
                os.replace(tmp, out_png)
                self.n += 1
                return
            except Exception as e:                       # noqa: BLE001 - reported below
                err = e
                self.log(f'    draw.io FAILED after {time.time() - t:.2f} s, attempt {attempt + 1}: '
                         f'{type(e).__name__}: {e}  {os.path.basename(out_png)}')
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


# ------------------------------------------------------------ per-layer work
class Ctx:
    """What a layer's work needs: the run's cfg, shapes, Run (pages, draw.io), source, combos and
    layers.  The main process has one; each worker process builds its own (_w_init)."""
    def __init__(self, cfg, shapes, R, src, layout, layers):
        self.cfg, self.shapes, self.R, self.src, self.layout = cfg, shapes, R, src, layout
        self.layers = {L['idx']: L for L in layers}


def layer_pass1(C, idx, jobs):
    """Pass 1 for one layer: jobs = [(role, raw png)] to draw (shaded / bent as needed).
    Returns ({'idx|role': box or None}, warnings)."""
    L, warn, ext = C.layers[idx], [], {}
    tag = f"{L['idx']}. {L['name']}"
    for role, raw in jobs:
        if not C.R.render_bg(L, C.layout, warn, raw, tag, C.src, role):
            warn.append(f'layer {tag}: the Render shading was left out - its image is not the size '
                        'the page frame gives at this zoom.')
        ext[f'{idx}|{role}'] = IM.alpha_box(IM.load(raw))
    return ext, warn


def layer_pass2(C, idx, box, pr, pb, o):
    """Pass 2 for one layer: its background / foreground (and cheat-sheet copy), the
    testalignment copies, its mirrored layer.  o: raw_dir, ta_dir, split_cs, in_cs, in_grid,
    mirror (key map or None), cm.  Returns (warnings, mirrored made)."""
    cfg, R, src, shapes = C.cfg, C.R, C.src, C.shapes
    L, warn = C.layers[idx], []
    tag, raw_dir = f"{L['idx']}. {L['name']}", o['raw_dir']
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
    if o['split_cs'] and o['in_cs']:
        cs = os.path.join(raw_dir, f'cs_{idx}.png')
        if os.path.exists(cs):
            R.compose(bg, cs, cs_out, box, pr, pb, True,
                      IM.shadow_keys(cfg, src, L, shapes, True) if o['in_grid'] else sh_k, rk)
    elif o['in_grid']:
        R.compose(bg, fg, cs_out, box, pr, pb, True, IM.shadow_keys(cfg, src, L, shapes, True), rk)
    if cfg.debug_export:
        shutil.copyfile(bg_out, os.path.join(o['ta_dir'], f'{idx}b.png'))
        shutil.copyfile(fg_out, os.path.join(o['ta_dir'], f'{idx}f.png'))
    made = False
    if o['mirror'] is not None:
        made = R.mirror_layer(L, o['mirror'], C.layout, warn, raw_dir, box, pr, pb, tag, o['cm'])
    else:
        for kind in ('background', 'foreground'):
            try:
                os.remove(os.path.join(cfg.out_dir(kind), f'{idx}m.png'))
            except OSError:
                pass
    return warn, made


# ------------------------------------------------------- the worker processes
def _low_priority():
    """This process below normal priority (Windows), so the user's own work comes first."""
    if sys.platform == 'win32':
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)       # BELOW_NORMAL_PRIORITY_CLASS
        except Exception:                                # noqa: BLE001
            pass


_W = None


def _w_init(spec):
    """A worker's own run context (it cannot share the main process's XML or browser)."""
    global _W
    import atexit
    _low_priority()
    if spec.get('test_arial'):                           # tests off Windows: the stand-in for GDI
        import fonts as FN
        FN.NOT_COVERED['Helvetica'] = set(spec['test_arial'])
    cfg = config.Cfg(spec['ini'], base_dir=spec['base'])
    LY.target_set(cfg, spec['layout'])
    shapes = RS.Shapes(RS.Script(spec['ahk']), cfg.capmodel_dir, cfg.render_shape)
    logs = []
    exporter = Exporter(cfg, spec['drawio'], lambda t: logs.append(t))
    atexit.register(exporter.close)
    src = M.Doc(M.load_xml(cfg.src_drawio))
    layout = CB.load_combo_data(cfg.combo_cache) if os.path.exists(cfg.combo_cache) else {'combos': []}
    R = Run(cfg, shapes, exporter, Progress())
    _W = (Ctx(cfg, shapes, R, src, layout, M.discover(src, [], {})), logs)


def _w_call(what, *args):
    C, logs = _W
    logs.clear()
    t = time.time()
    r = (layer_pass1 if what == 1 else layer_pass2)(C, *args)
    return r, list(logs), time.time() - t, os.getpid()


class Workers:
    """n worker processes taking whole layers; n = 1: everything in this process, in order."""
    def __init__(self, n, C, spec, ui):
        self.n, self.C, self.ui, self.pool = n, C, ui, None
        if n > 1:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor
            self.pool = ProcessPoolExecutor(n, mp_context=multiprocessing.get_context('spawn'),
                                            initializer=_w_init, initargs=(spec,))

    def run(self, what, tasks, say):
        """tasks: [(idx, args...)]; say(k, n, idx) after each; returns {idx: result}."""
        out = {}
        if self.pool is None:
            for k, t in enumerate(tasks, 1):
                say(k - 1, len(tasks), t[0], False)
                out[t[0]] = (layer_pass1 if what == 1 else layer_pass2)(self.C, *t)
            return out
        from concurrent.futures import as_completed
        fut = {self.pool.submit(_w_call, what, *t): t[0] for t in tasks}
        for k, f in enumerate(as_completed(fut), 1):
            r, logs, dt, pid = f.result()                 # an error in a worker is raised here
            for line in logs:
                self.ui.log(f'    [{pid}] {line.strip()}')
            self.ui.log(f'    [{pid}] layer {fut[f]} pass {what} done in {dt:.2f} s')
            out[fut[f]] = r
            say(k, len(tasks), fut[f], True)
        return out

    def close(self):
        if self.pool is not None:
            self.pool.shutdown(wait=True, cancel_futures=True)
            self.pool = None


def export(cfg, shapes, export_fn, ui, selected, recomp_all=False, all_run=False, last=True, last_bak='',
           label=None, ignore=(), workers=1, spec=None):
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

    C = Ctx(cfg, shapes, R, src, layout, layers)
    names = {L['idx']: f"{L['idx']}. {L['name']}" for L in layers}
    # ---- pass 1: every layer's extent, exporting only what is needed
    tasks = []
    for L in layers:
        sel = L['idx'] in selected
        jobs = []
        for role in cfg.render_roles(L['idx'], cs_idx):
            if role == 'bgg' and not sel and L['idx'] not in recomp:
                continue
            key = f"{L['idx']}|{role}"
            raw = os.path.join(raw_dir, f"{role}_{L['idx']}.png")
            if sel or key not in ext or (L['idx'] in recomp and not os.path.exists(raw)):
                jobs.append((role, raw))
        if jobs:
            tasks.append((L['idx'], jobs))
    W = Workers(workers if len(tasks) > 1 else 1, C, spec, ui)
    try:
        def say1(k, n, idx, finished):
            ui.say(f'({k}/{n})  {names[idx]}' + (' drawn' if finished else '\nrendering'),
                   8 + M.round_ahk(k / max(1, n) * 55))
        if tasks:
            ui.say(f'Drawing {len(tasks)} layer(s)' + (f' with {W.n} workers' if W.pool else ''), 8)
        for idx, (e, w) in sorted(W.run(1, tasks, say1).items()):
            ext.update(e)
            warn.extend(w)
        for L in layers:
            for role in cfg.render_roles(L['idx'], cs_idx):
                b = ext.get(f"{L['idx']}|{role}")
                if b:
                    box = LY.union_box(box, b)
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
        todo = [L['idx'] for L in layers if L['idx'] in selected or L['idx'] in recomp]
        # the mirrored layers first: they take longest, so the workers finish together
        todo.sort(key=lambda i: i not in mir_sets)
        tasks = [(i, box, pr, pb, {'raw_dir': raw_dir, 'ta_dir': ta_dir, 'split_cs': split_cs,
                                   'in_cs': i in cs_idx, 'in_grid': i in cs_grid,
                                   'mirror': mir_sets.get(i), 'cm': cm_sets.get(i)}) for i in todo]

        def say2(k, n, idx, finished):
            ui.say(f'({k}/{n})  {names[idx]}' + (' composed' if finished else '\ncompositing'),
                   66 + M.round_ahk(k / max(1, n) * 32))
        res2 = W.run(2, tasks, say2)
    finally:
        W.close()
    mir_n = 0
    for idx in sorted(res2):
        w, made = res2[idx]
        warn.extend(w)
        mir_n += bool(made)

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


def _selftest_pid(_):
    time.sleep(0.2)
    _low_priority()
    return os.getpid()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ('render', 'serve'):          # the draw.io helper on its own
        import drawio_helper as DH
        DH.main(argv)
        return 0
    if argv and argv[0] == 'fontcheck':
        return fontcheck(argv[1:])
    if argv and argv[0] == 'selftest-workers':          # CI: worker processes start from the exe
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        n = int(argv[1]) if len(argv) > 1 else 3
        with ProcessPoolExecutor(n, mp_context=multiprocessing.get_context('spawn')) as ex:
            pids = set(ex.map(_selftest_pid, range(4 * n)))
        print(f'{len(pids)} worker process(es) ran: {sorted(pids)}')
        return 0 if len(pids) >= 1 else 1
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
    e.add_argument('--workers', type=int, default=None,
                   help='processes drawing and composing layers at once (default: [export] Workers, else 3)')
    a = ap.parse_args(argv)

    res = {'ok': False, 'message': '', 'line': '', 'warnings': [], 'images': 0, 'mirrored': 0}
    code, exporter = 0, None
    ui = Progress(a.progress, os.path.join(os.path.dirname(os.path.abspath(a.result)), 'png_overlay_log.txt')
                  if a.result else None)
    try:
        base = os.path.dirname(os.path.abspath(a.ini))
        cfg = config.Cfg(a.ini, base_dir=base)
        if LY.lay_read(cfg, a.layout) is None:
            raise M.Die(f'No layout called "{a.layout}" in {a.ini}.')
        LY.target_set(cfg, a.layout)
        shapes = RS.Shapes(RS.Script(a.ahk), cfg.capmodel_dir, cfg.render_shape)
        drawio = a.drawio or os.path.dirname(cfg.ini.read('paths', 'DrawioExe', ''))
        exporter = Exporter(cfg, drawio, ui.log)
        sel = {int(t) for t in a.layers.replace(' ', ',').split(',') if t.strip().isdigit()}
        _low_priority()
        nw = a.workers
        if nw is None:
            v = cfg.ini.read('export', 'Workers', '').strip()
            nw = int(v) if v.isdigit() else 3
        nw = max(1, min(nw, os.cpu_count() or 1))
        import fonts as FN
        spec = {'ini': os.path.abspath(a.ini), 'base': base, 'ahk': os.path.abspath(a.ahk), 'layout': a.layout,
                'drawio': drawio, 'test_arial': sorted(FN.NOT_COVERED.get('Helvetica', ()))}
        ui.log(f'workers: {nw}')
        msg, line, warn, total, mir = export(cfg, shapes, exporter, ui, sel, a.recomp,
                                             a.all_run, a.last or not a.all_run, a.last_bak, a.label,
                                             (a.result, a.progress), nw, spec)
        res.update(ok=True, message=msg, line=line, warnings=warn, images=total, mirrored=mir)
    except M.Die as d:
        res['message'], code = str(d), 2
    except Exception as e:                               # noqa: BLE001
        # the error itself first: the script shows only the start of the message
        res['message'], code = (f'Unexpected error - please report it: {type(e).__name__}: {e}\n\n'
                                + traceback.format_exc()), 1
    finally:
        if exporter is not None:
            exporter.close()
    ui.log(f'exit {code}' + ('' if res['ok'] else ': ' + res['message']))
    if a.result:
        with open(a.result, 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(res['message'] if not res['ok'] else res['line'])
    return code


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()          # worker processes of the built exe start here
    sys.exit(main())
