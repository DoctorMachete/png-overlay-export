"""Shared set-up for the tests: cfg on a copy of the INI, the source, the shapes."""
import shutil
import config, layout as LY, model as M, render_shade as RS
AHK = '/home/claude/build66/export_from_drawio.ah2'
SRC = '/home/claude/src.drawio'
_SC = None

def setup(layout, ini_copy='/home/claude/pyport/_t.ini'):
    global _SC
    shutil.copy('/home/claude/export_from_drawio.ini', ini_copy)
    cfg = config.Cfg(ini_copy, base_dir='/home/claude/capmodels_x')
    LY.target_set(cfg, layout)
    _SC = _SC or RS.Script(AHK)
    shapes = RS.Shapes(_SC, cfg.capmodel_dir, cfg.render_shape)
    return cfg, shapes

def layer(doc, idx):
    return [l for l in M.discover(doc, []) if l['idx'] == idx][0]
