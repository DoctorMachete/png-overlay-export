"""model.py + layout.py + ini.py checks (PYTHON_EXPORT_HANDOFF.md §16)."""
import copy, hashlib, shutil
import model as M, layout as LY, config, render_shade as RS
S = '/home/claude/pyport/_t.ini'
shutil.copy('/home/claude/export_from_drawio.ini', S)
cfg = config.Cfg(S, base_dir='/home/claude/capmodels_x')
doc = M.Doc(M.load_xml('/home/claude/src.drawio'))
w = []; L = M.discover(doc, w); print(len(L), 'layers, warnings', w)
g = L[3]['id']
def broken(mut, label):
    d2 = M.Doc(M.load_xml('/home/claude/src.drawio')); ks = [k for k in d2.children(g) if M.is_key_size(M.geo(k))]
    mut(d2, ks); d2.reindex(); w = []; M.discover(d2, w); print(' ', label, '->', w)
def dup(d, ks): c = copy.deepcopy(ks[7]); c.set('id', 'dupX'); ks[7].addnext(c)
def off(d, ks): c = copy.deepcopy(ks[9]); c.set('id', 'dupY'); c.find('mxGeometry').set('height', '30'); ks[9].addnext(c)
broken(lambda d, ks: ks[5].getparent().remove(ks[5]), 'remove a key')
broken(dup, 'duplicate a key')
broken(lambda d, ks: ks[2].find('mxGeometry').set('width', '28.82'), 'resize a key')
broken(off, 'off-spec cell on a key')
sc = RS.Script('/home/claude/build66/export_from_drawio.ah2')
for l in LY.lay_list(cfg):
    LY.target_set(cfg, l['name'])
    tag = LY.render_style_tag(cfg, RS.Shapes(sc, cfg.capmodel_dir, cfg.render_shape))
    was = cfg.ini.read('state', 'RenderedStyle' + cfg.out_sfx(), '')
    looks = ''
    if cfg.caps_like():
        now = LY.cap_looks_now(cfg, doc)
        looks = ' looks ' + ('OK' if ''.join(n + '=' + now[n] + ';' for n in LY.ahk_sorted(now)) ==
                             cfg.ini.read('state', 'CapLooks' + cfg.out_sfx(), '') else 'DIFF')
    print(f"  {l['name']:16s} tag {'OK' if tag == was else 'DIFF (stored by an older script)' if '/w0/' in was else 'DIFF'}{looks}")
h = lambda: hashlib.md5(open(S, 'rb').read()).hexdigest(); h0 = h()
for sec in [s for s in cfg.ini.sections() if s.startswith('cache')]:
    LY.save_extents(cfg, sec, LY.load_extents(cfg, sec))
    cfg.ini.write(LY.box_str(LY.box_parse(cfg.ini.read(sec, 'box'))), sec, 'box')
for sx in LY.out_sfx_all(cfg):
    if cfg.ini.read('state', 'RoleLayers' + sx, None) is not None:
        LY.save_role_layers(cfg, LY.load_role_layers(cfg, sx), sx)
print('INI round trip byte-identical:', h() == h0)
