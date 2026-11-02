"""Compose LameSaddle layer 0 from the script's raws and compare with its final images."""
import sys, time, numpy as np
import config, layout as LY, model as M, images as IM, render_shade as RS
S = '/home/claude/pyport/_t.ini'
import shutil; shutil.copy('/home/claude/export_from_drawio.ini', S)
cfg = config.Cfg(S, base_dir='/home/claude/capmodels_x'); LY.target_set(cfg, 'LameSaddle')
shapes = RS.Shapes(RS.Script('/home/claude/build66/export_from_drawio.ah2'), cfg.capmodel_dir, cfg.render_shape)
doc = M.Doc(M.load_xml('/home/claude/src.drawio')); L = [l for l in M.discover(doc, []) if l['idx'] == 0][0]
keys = IM.shadow_keys(cfg, doc, L, shapes)
box = LY.box_parse(cfg.ini.read('cache_LameSaddle', 'box')); pr, pb = IM.shadow_pad(cfg)
print(len(keys), 'keys,', sum('sil' in k for k in keys), 'with outlines; box', box, 'pad', pr, pb)
for z in sys.argv[1:] or ['2x', '0x']:
    D = f'/home/claude/dbg/{z}/'
    bg, fg = IM.load(D + '_raw_LameSaddle/bg_0.png'), IM.load(D + '_raw_LameSaddle/fg_0.png')
    t = time.time(); out = IM.compose(cfg, bg, fg, box, pr, pb, True, keys); dt = time.time() - t
    ref = IM.load(D + 'foreground_LameSaddle/0.png')
    IM.save(out, f'py_fg0_{z}.png')
    pf, rf = IM.to_f(out), IM.to_f(ref)
    d = np.abs(pf - rf) * 255
    dc, da = d[..., :3].max(-1), d[..., 3]
    print(f'{z}: {dt:.2f}s  size {out.shape[1]}x{out.shape[0]} vs {ref.shape[1]}x{ref.shape[0]} | '
          f'premult colour >2: {np.mean(dc > 2) * 100:.2f}%  >8: {np.mean(dc > 8) * 100:.2f}%  mean {dc.mean():.2f} | '
          f'alpha >2: {np.mean(da > 2) * 100:.2f}%  >8: {np.mean(da > 8) * 100:.2f}%  max {da.max():.0f}')
    np.save(f'diff_{z}.npy', np.stack([dc, da]))
