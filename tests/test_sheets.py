"""sheets.py end to end in a scratch folder (LameSaddle): the legend through the draw.io helper,
the cheat sheet, the sheet of all layers, the backup zip.  With no reference images from the
script yet, the cells are the script's own foreground_LameSaddle\\0.png (2x Debug run) copied
to every layer; checked: sizes, placement, a second run's legend cache hit, the PNG readable."""
import os, shutil, time, zipfile, numpy as np
from PIL import Image
import model as M, pages as P, sheets as S, images as IM, tests_common as T
from lxml import etree

cfg, shapes = T.setup('LameSaddle')
base = '/home/claude/pyport/_sheets'
shutil.rmtree(base, ignore_errors=True); os.makedirs(base)
cfg.base_dir = base
src = M.Doc(M.load_xml(T.SRC))
ctx = P.Ctx(cfg, shapes)
box = {'x1': 36, 'y1': 36, 'x2': 2264, 'y2': 928}; pr, pb = IM.shadow_pad(cfg)

import drawio_helper as DH
R = DH.Renderer('/home/claude/dl/drawio30/resources/app.asar')
calls = []
def export(page, out_png):
    calls.append(out_png)
    open(out_png, 'wb').write(R.render(etree.tostring(page, encoding='unicode'), scale=5, transparent=True))
try:
    raw_dir = os.path.join(base, '_raw_LameSaddle')
    t = time.time()
    lg = S.render_legend(cfg, ctx, src, export, raw_dir, box, pr, pb, 'py-test', force=False, cache_sec='cache_LameSaddle')
    t1 = time.time() - t
    os.remove(os.path.join(raw_dir, 'bg_legend.png'))              # Debug off: the raw goes
    t = time.time()
    lg2 = S.render_legend(cfg, ctx, src, export, raw_dir, box, pr, pb, 'py-test', force=False, cache_sec='cache_LameSaddle')
    t2 = time.time() - t
finally:
    R.close()
im = Image.open(lg)
print(f'legend: {im.size} (canvas {box["x2"] - box["x1"] + 1 + pr} x {box["y2"] - box["y1"] + 1 + pb}); '
      f'first {t1:.2f}s ({len(calls)} draw.io page), second {t2:.2f}s, draw.io pages now {len(calls)} (cache hit = 1)')

fg = cfg.out_dir('foreground'); os.makedirs(fg, exist_ok=True)
cell = '/home/claude/dbg/2x/foreground_LameSaddle/0.png'
for L in M.valid_layer_groups(src):
    shutil.copy(cell, os.path.join(fg, f"{L['idx']}.png"))
os.remove(os.path.join(fg, '25.png'))                               # a gap in the grid
warn = []
t = time.time(); info = S.build_cheatsheet(cfg, S.parse_grid(cfg.cs_grid), lg, warn); t3 = time.time() - t
cs = Image.open(os.path.join(base, S.cs_img_out(cfg)))
print(f'cheat sheet: {info} in {t3:.2f}s, file {cs.size}; warn {warn}')
a = np.asarray(cs)
print('  empty gap where 25 is:', a[(1 * (info["h"] + 10) // 3) + 50, 2 * (info["w"] + 10) // 3 + 100, 3] == 0)

t = time.time(); mz = S.export_mosaic(cfg, src, warn); t4 = time.time() - t
mi = Image.open(mz); mi.load()
pg = M.page_grid(src)
print(f'sheet of all layers: {os.path.basename(mz)} {mi.size} in {t4:.2f}s; page grid {pg}')
zp, n = S.export_backup_zip(cfg, warn)
print(f'backup zip: {os.path.basename(zp)}, {n} layers: {zipfile.ZipFile(zp).namelist()}')
print('warnings:', warn)
