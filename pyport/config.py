"""The settings the script reads at start (the globals at the top of the .ah2),
from export_from_drawio.ini.  The layout-specific ones are then set by
layout.lay_apply, as LayApply does.  The INI is expected migrated already
(LayMigrate runs in AHK at start, before any export)."""
import os, math
from ini import Ini
from util import (first_num, to_num, cap_opt_num, cap_opt_colour, sfx_clean, layer_spec_norm,
                  pairs_decode, parse_cp_list, anchor_col)

SLOT_MAX = 32
CAP_KEYS = ["capFill", "capGrad", "capDir", "capEdge", "capDepth", "capShine", "capDish", "capGlass",
            "rndFill", "rndGrad", "rndDir", "rndEdge", "rndShape"]
RND_KEYS = ["rndFill", "rndGrad", "rndDir", "rndEdge", "rndShape"]
CAP_FACE = [1.8, 2.2, 23.0, 23.0]

LAY_DEF = {"TextUp": "0",
           "ComboArc": "20", "ComboOpacity": "", "ComboFill": "", "ComboScale": "100", "ComboFont": "",
           "ComboTextOpacity": "", "ComboBorder": "", "ComboOutline": "",
           "CapEdgeOnTop": "1", "CapDish": "0", "CapDishVariation": "0", "CapLegendShape": "3",
           "CapGlass": "none", "CapGlassStrength": "100", "CapGlassBackground": "1",
           "CapBadge": "inlay", "CapBadgeFit": "scale", "CapBadgeMargin": "0", "CapBadgeText": "100",
           "CapBadgeTop": "", "CapBadgeBottom": "", "CapBadgeBorder": "", "CapBadgeOpacity": "100",
           "CapBadgeRadius": "", "CapBadgeDepth": "60", "CapBadgeOutline": "0",
           "RenderLight": "lamp", "RenderShape": "real", "RenderShading": "100", "RenderHighlights": "100",
           "RenderKeyText": "", "RenderRings": "1"}
LAY_GROUPS = [
    ("textup", "drawio caps render", ["TextUp"]),
    ("caps", "caps render", ["CapEdgeOnTop", "CapDish", "CapDishVariation", "CapLegendShape", "CapGlass",
                             "CapGlassStrength", "CapGlassBackground"]),
    ("badges", "caps render", ["CapBadge", "CapBadgeFit", "CapBadgeMargin", "CapBadgeText", "CapBadgeTop",
                               "CapBadgeBottom", "CapBadgeBorder", "CapBadgeOpacity", "CapBadgeRadius",
                               "CapBadgeDepth", "CapBadgeOutline"]),
    ("combos", "drawio caps render", ["ComboArc", "ComboOpacity", "ComboFill", "ComboScale", "ComboFont",
                                      "ComboTextOpacity", "ComboBorder", "ComboOutline"]),
    ("render", "render", ["RenderLight", "RenderShape", "RenderShading", "RenderHighlights",
                          "RenderKeyText", "RenderRings"]),
    ("pos", "render", [])]


def _opt(v, lo, hi, dflt):
    n = cap_opt_num(v, lo, hi)
    return dflt if n == '' else n


def combo_norm(m):
    out = {"arc": cap_opt_num(m["arc"], 0, 50), "opac": cap_opt_num(m["opac"], 0, 100),
           "fill": cap_opt_colour(m["fill"]), "scale": cap_opt_num(m["scale"], 20, 200),
           "font": cap_opt_colour(m["font"]), "textop": cap_opt_num(m["textop"], 0, 100),
           "border": cap_opt_colour(m["border"]), "outline": cap_opt_colour(m["outline"])}
    if out["scale"] == '':
        out["scale"] = "100"
    return out


class Cfg:
    """The script's globals.  base_dir = the folder of the .ah2 (A_ScriptDir)."""

    def __init__(self, ini_path, base_dir=None):
        self.ini = Ini(ini_path)
        self.ini_file = ini_path
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(ini_path))
        r = self.ini.read
        self.drawio_exe = r("paths", "DrawioExe", "")
        self.src_drawio = r("paths", "SourceFile", "source_diagram.drawio")
        self.json_name = r("paths", "LayoutJson", "")
        self.scale = to_num(r("export", "Scale", 5))
        self.use_profile = to_num(r("export", "UseProfileDir", 1))
        self.no_gpu = to_num(r("export", "DisableGpu", 1))
        self.sh_dist = to_num(r("shadow", "Distance", 20))
        self.sh_angle = to_num(r("shadow", "Angle", 45))
        self.sh_blur = to_num(r("shadow", "Blur", 12))
        self.sh_opacity = to_num(r("shadow", "Opacity", 50))
        self.sh_colour = r("shadow", "Colour", "505050")
        self.sh_on_bg = first_num(r("shadow", "OnBackground", "0"), 0) != 0
        self.sh_fullkeys = first_num(r("shadow", "FullKeys", "1"), 1) != 0
        self.sh_keyinset = r("shadow", "FullKeysInset", "").strip()
        self.font_over = r("render", "FontOverride",
                           "Segoe UI Symbol,Segoe UI Historic,Segoe UI Emoji,Cambria Math,Segoe UI")
        self.font_base = r("render", "BaseFont", "Helvetica")
        self.font_mode = r("render", "FontMode", "auto").strip().lower()
        self.fix_chars = parse_cp_list(r("render", "FixChars", ""))
        self.keep_chars = parse_cp_list(r("render", "KeepChars", ""))
        self.probe_on = to_num(r("render", "ProbeGlyphs", "1"))
        self.title_pad_k = first_num(r("render", "TitlePadK", "0.148"), 0.148)
        self.title_pad_b = first_num(r("render", "TitlePadB", "0"), 0)
        self.chips_follow = first_num(r("render", "ChipsFollowRoles", "0"), 0) != 0
        self.render_inset = _opt(r("render", "RenderEdgeInset", "0.5"), 0, 3, "0.5")
        self.out_folder = {st: sfx_clean(r("export", "Folder" + st.title(), d))
                           for st, d in (("drawio", "classic"), ("caps", "svg"), ("render", "render"))}
        self.capmodel_dir = os.path.join(self.base_dir, "capmodels")
        self.combo_span = to_num(r("combos", "MaxSpan", 30))
        self.combo_tab = r("combos", "Tab", "combos")
        mf = r("combos", "MapFile", "combo_map.ini")
        self.combo_mapf = mf if '\\' in mf or '/' in mf else os.path.join(self.base_dir, mf)
        self.combo_listel = r("combos", "ListElement", "").strip()
        self.combo_listup = self._list_up()
        self.combo_listmax = first_num(r("combos", "ListMaxLines", "4"), 4)
        self.combo_list_fg = first_num(r("combos", "ListCombos", "1"), 1)
        self.combo_list_cs = first_num(r("combos", "ListCombosSheet", str(self.combo_list_fg)), self.combo_list_fg)
        self.combo_listanchor = anchor_col(r("combos", "ListAnchor", "3"))
        self.combo_quiettrans = first_num(r("combos", "ListQuietTrans", "0"), 0)
        self.combo_listpad = first_num(r("combos", "ListTextPad", "4"), 4)
        self.combo_cache = os.path.join(self.base_dir, "combo_data.txt")
        self.cs_grid = r("cheatsheet", "Grid", "")
        self.cs_zoom = to_num(r("cheatsheet", "Zoom", 2.5))
        self.cs_padh = to_num(r("cheatsheet", "PadH", 2))
        self.cs_padv = to_num(r("cheatsheet", "PadV", 2))
        self.cs_legtab = r("cheatsheet", "LegendTab", "legend")
        self.cs_imgpath = r("cheatsheet", "ImagePath", "")
        if '\\' not in self.src_drawio and '/' not in self.src_drawio:
            self.src_drawio = os.path.join(self.base_dir, self.src_drawio)
        if self.json_name and '\\' not in self.json_name and '/' not in self.json_name:
            self.json_name = os.path.join(self.base_dir, self.json_name)
        self.mosaic_pct = _opt(r("export", "MosaicScale", "100"), 10, 100, "100")
        self.backup_layers = layer_spec_norm(r("export", "BackupLayers", "0-31"))
        self.mosaic_sheet = r("export", "MosaicSheet", "0").strip() == "1"
        self.debug_export = r("export", "Debug", "0").strip() == "1"
        self.mirror_pairs = pairs_decode(r("export", "MirrorPairs", "( ) [ ] { } < >").strip())
        self.grid_cols = max(1, min(SLOT_MAX, round(first_num(r("layout", "Columns", "8"), 8))))
        # the layout's globals (LayApply sets them; these are the values before any layout)
        self.key_style = "drawio"
        self.lay_name = ""
        self.lay_roles = {}
        self.cap_pos = {}
        self.text_up = {"drawio": "0", "caps": "0", "render": "0"}
        self.combo_set = {"drawio": combo_norm(dict.fromkeys(
            ("arc", "opac", "fill", "scale", "font", "textop", "border", "outline"), ""))}
        self.cap_glass_nobg = False

    def _list_up(self):
        v = self.ini.read("combos", "ListUp", "").strip()
        if v != '':
            return first_num(v, 0)
        old = self.ini.read("combos", "ListDy", "").strip()
        if old == '':
            return 0
        n = -first_num(old, 0)
        self.ini.write(n, "combos", "ListUp")
        self.ini.delete("combos", "ListDy")
        return n

    # --------------------------------------------------- small getters of the script
    def caps_like(self):
        return self.key_style in ("caps", "render")

    def out_sfx(self):
        return "" if self.lay_name == "" else "_" + self.lay_name

    def out_dir(self, kind):
        return os.path.join(self.base_dir, kind + self.out_sfx())

    def text_up_val(self):
        v = self.text_up.get(self.key_style, "0")
        from util import is_number
        return to_num(v) if is_number(v) else 0

    def combo_val(self, k, st=''):
        return self.combo_set[st or self.key_style][k]

    def glass_bg_split(self):
        return self.key_style == "caps" and self.cap_glass != "none" and not self.cap_glass_bg

    def cs_quiet_shadow(self):
        return (self.key_style == "render" and not self.render_ring and self.sh_fullkeys
                and self.cs_grid.strip() != "")

    def render_roles(self, idx=None, cs_idx=None):
        if self.combo_list_cs == self.combo_list_fg:
            out = ["bg", "fg"]
        elif idx is None or cs_idx is None:
            out = ["bg", "fg", "cs"]
        else:
            out = ["bg", "fg", "cs"] if idx in cs_idx else ["bg", "fg"]
        if self.glass_bg_split():
            out.append("bgg")
        return out
