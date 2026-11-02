"""Legend 3D + Render shading of LameSaddle layer 0, from the script's own draw.io parts, against
the script's shaded raws:
  dbg2x   __DEBUG_0x_2x.zip, Legend 3D 2x: bg_0_c/_t/_r.png -> bg_0.png (the older source)
  ref3x   the .148 Debug run, Legend 3D 3x: bg_0_c/_t/_r.png -> bg_0.png
  ref3xm  the same, its mirrored layer: mbg_0_c/_t/_r.png -> mbg_0.png
  legend  the .148 run's bg_legend.drawio drawn here by drawio_helper, its chips shaded
          (CapLegend's items, one a ring), against its bg_legend.png: chip pixels only, text
          masked out (Linux fonts here)
Everything (keys, grids, shading items) comes from cfg / model / layout (keys.warp_keys,
shade.render_items) on the current src.drawio."""
import sys, time, numpy as np
from PIL import Image
import model as M, keys as K, shade as SH, legend3d as L3, mirror as MR, combos as CB, tests_common as T

cfg, shapes = T.setup('LameSaddle')
doc = M.Doc(M.load_xml(T.SRC)); L = T.layer(doc, 0)
ld = lambda f: np.asarray(Image.open(f).convert('RGBA'))


def run(tag, d, pre, k, src, LL):
    keys = K.warp_keys(cfg, src, LL, shapes)
    items = SH.render_items(cfg, src, LL)
    c, t, r = (ld(f'{d}{pre}bg_0_{p}.png') for p in 'ctr')
    t0 = time.time(); bent, _ = L3.compose_warp(c, t, r, keys, k); t1 = time.time()
    out = SH.shade_raw(cfg, shapes, bent, items); t2 = time.time()
    Image.fromarray(out).save(f'/home/claude/pyport/py_{tag}.png')
    ref = ld(f'{d}{pre}bg_0.png').astype(int)
    dd = np.abs(ref - out.astype(int)).max(-1)
    np.save(f'/home/claude/pyport/d_{tag}.npy', dd)
    print(f'{tag:7s} k={k:.2f}  bend {t1 - t0:.2f}s shade {t2 - t1:.2f}s, measured '
          f'{sum("mfx" in i for i in items)}/{len(items)} | vs script: >8: {(dd > 8).mean() * 100:.2f}%  '
          f'>32: {(dd > 32).mean() * 100:.2f}%  >64: {(dd > 64).mean() * 100:.2f}%  mean {np.abs(ref - out).mean():.2f}')


jobs = sys.argv[1:] or ['dbg2x', 'ref3x', 'ref3xm', 'legend']
if 'dbg2x' in jobs:
    run('dbg2x', '/home/claude/dbg/2x/_raw_LameSaddle/', '', 2 / 3, doc, L)
if 'ref3x' in jobs:
    run('ref3x', '/home/claude/refraw/_raw_LameSaddle/', '', 3 / 3, doc, L)
if 'ref3xm' in jobs:
    data = CB.load_combo_data('/home/claude/combo_data.txt')
    srcm, Lm, _ = MR.mirror_source(cfg, T.SRC, L, MR.mirror_load(cfg)[0], data, MR.mirror_combo_load(cfg).get(0), [])
    run('ref3xm', '/home/claude/refraw/_raw_LameSaddle/', 'm', 3 / 3, srcm, Lm)
if 'legend' in jobs:
    import subprocess, cv2, pages as P
    R = '/home/claude/refraw/_raw_LameSaddle/'
    subprocess.run([sys.executable, '/home/claude/pyport/drawio_helper.py', '--drawio',
                    '/home/claude/dl/drawio30/resources/app.asar', '-s', '5', '-t', 'render',
                    R + 'bg_legend.drawio', '/home/claude/pyport/raw_legend.png'], check=True, capture_output=True)
    _, chips = P.build_legend_page(cfg, P.Ctx(cfg, shapes), doc, [])
    raw = ld('/home/claude/pyport/raw_legend.png')
    t0 = time.time(); out = SH.shade_raw(cfg, shapes, raw, [dict(c) for c in chips]); dt = time.time() - t0
    Image.fromarray(out).save('/home/claude/pyport/py_legend.png')
    ref, O, Rw = ld(R + 'bg_legend.png').astype(int), out.astype(int), raw.astype(int)
    tot = []
    for c in chips:
        x0, y0 = int((c['x'] + 8) * 5), int((c['y'] + 8) * 5)
        x1, y1 = int((c['x'] + c['w'] + 8) * 5), int((c['y'] + c['h'] + 8) * 5)
        a, f, r_ = O[y0:y1, x0:x1], ref[y0:y1, x0:x1], Rw[y0:y1, x0:x1]
        txt = np.abs(r_[..., :3] - np.median(r_[..., :3].reshape(-1, 3), 0)).max(-1) > 40
        k7 = np.ones((7, 7), np.uint8)
        mask = cv2.dilate(txt.astype(np.uint8), k7) | cv2.dilate((np.abs(a - f).max(-1) > 90).astype(np.uint8), k7)
        tot.append(np.abs(a - f).max(-1)[(mask == 0) & (f[..., 3] > 250)])
    d = np.concatenate(tot)
    print(f'legend  {len(chips)} chips ({sum(c["ring"] for c in chips)} ring), shade {dt:.2f}s | chips without text '
          f'vs script: >8: {(d > 8).mean() * 100:.2f}%  >16: {(d > 16).mean() * 100:.2f}%  mean {d.mean():.2f}')
