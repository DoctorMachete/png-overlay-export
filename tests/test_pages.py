"""Build pages and diff them with the script's .148 Debug pages (refraw/_raw_<layout>/)."""
import sys, shutil
import config, layout as LY, model as M, pages as P, combos as CB, render_shade as RS, pagediff as PD
S = '/home/claude/pyport/_t.ini'; shutil.copy('/home/claude/export_from_drawio.ini', S)
REF = '/home/claude/refraw/'
cfg = config.Cfg(S, base_dir='/home/claude/capmodels_x')
data = CB.load_combo_data('/home/claude/combo_data.txt')
src = M.Doc(M.load_xml('/home/claude/src.drawio'))
L0 = [l for l in M.discover(src, []) if l['idx'] == 0][0]
jobs = [a.split(':') for a in sys.argv[1:]] or [['LameSaddle', 'fg'], ['classic_minteal', 'fg'], ['svg_G', 'fg']]
import fonts as FN
# GDI's answer for Helvetica (= Arial on Windows) is not available here: the characters of these
# pages that Arial lacks (found from the script's pages) stand in for it.  On Windows: real GDI.
FN.NOT_COVERED['Helvetica'] = {int(l, 16) for l in open('/home/claude/pyport/arial_missing.txt') if l.strip() and l[0] != ';'}
import mirror as MR
SRCP = '/home/claude/src.drawio'
for lay, role in jobs:
    LY.target_set(cfg, lay)
    ctx = P.Ctx(cfg, RS.Shapes(RS.Script('/home/claude/build66/export_from_drawio.ah2'), cfg.capmodel_dir, cfg.render_shape))
    warn = []
    srcU, LU, dataU, pre = src, L0, data, ''
    if role.startswith('m'):
        r = MR.mirror_source(cfg, SRCP, L0, MR.mirror_load(cfg)[0], data, MR.mirror_combo_load(cfg).get(0), warn)
        srcU, LU, dataU = r; role = role[1:]; pre = 'm'
    print(f'== {lay} {role}_0')
    import os
    if role == 'bg' and os.path.exists(REF + f'_raw_{lay}/{pre}bg_0_c.drawio'):   # the run had Legend 3D on
        import capkeys, copy
        doc = P.build_page_doc(cfg, ctx, LU, dataU, 'bg', warn, srcU)
        for part in 'ctr':
            print(f'  -- {lay} {pre}bg_0_{part}')
            d = copy.deepcopy(doc); capkeys.cap_split_page(d, part)
            open(f'/home/claude/pyport/_pg_{lay}_bg_0_{part}.drawio', 'w', encoding='utf-8').write(P.etree.tostring(d, encoding='unicode'))
            PD.diff(REF + f'_raw_{lay}/{pre}bg_0_{part}.drawio', d)
        continue
    if role == 'legend':
        out, chips = P.build_legend_page(cfg, ctx, src, warn)
        PD.diff(REF + f'_raw_{lay}/bg_legend.drawio', out); continue
    cfg.cap_glass_nobg = role == 'bgg'
    if role == 'bgg': role = 'bg'
    try:
        out = P.build_page(cfg, ctx, f'/home/claude/pyport/_pg_{lay}_{role}_0.drawio', LU, dataU, role, warn, srcU)
    except NotImplementedError as e:
        print('  not ported:', e); continue
    PD.diff(REF + f'_raw_{lay}/{pre}{"bgg" if cfg.cap_glass_nobg else role}_0.drawio', out)
    for w in warn: print('  warn:', w)
