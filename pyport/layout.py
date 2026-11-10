"""Layouts, roles and the INI state of the .147 script:
LayList, LayStyleRaw, LayStyleOf, LayStoredName, LayRead, LayEnabled, LayCombo,
LayApply; CapPosParse, CapPosStr, CapPosSig, CapModelFile (render_shade.capmodel);
LoadRoles, RolesOverlay, LoadBadge, LoadCapRoles; CapLook, RenderLook,
RenderShapeOf, CapLookStr, RolesSig, CapLookChanges; CapBadgeParams,
RenderTextFactor, RenderStyleTag, RenderStyleName; the [state]/[cache…] keys:
LoadExtents, SaveExtents, BoxStr, BoxParse, UnionBox, LoadRoleLayers,
SaveRoleLayers, PendingRoleLayers, OutSfxAll."""
import os, re
import model as M
from config import CAP_KEYS, RND_KEYS, CAP_FACE, LAY_DEF, combo_norm
from render_shade import capmodel
from util import (is_number, to_num, first_num, fmt4, cap_hex, cap_opt_num, cap_opt_colour,
                  same_num, crc32_hex, ahk_sorted, round_ahk)


class IMap(dict):
    """A Map with CaseSense false: keys looked up ignoring case, first spelling kept."""
    def _k(self, k):
        kl = k.lower()
        for x in dict.keys(self):
            if x.lower() == kl:
                return x
        return k

    def __getitem__(self, k): return dict.__getitem__(self, self._k(k))
    def __setitem__(self, k, v): dict.__setitem__(self, self._k(k), v)
    def __contains__(self, k): return dict.__contains__(self, self._k(k))
    def get(self, k, d=None): return dict.get(self, self._k(k), d)


# ------------------------------------------------------------------ layouts
def lay_style_raw(cfg, name):
    st = cfg.ini.read("layout." + name, "Style", "drawio").strip().lower()
    return st if st in ("caps", "render") else "drawio"


def lay_list(cfg):
    names = [m.group(1) for s in cfg.ini.sections() for m in [re.fullmatch(r'(?i)layout\.(.+)', s)] if m]
    return [{"name": n, "style": lay_style_raw(cfg, n)} for n in sorted(names, key=str.lower)]


def _lay_find(cfg, name):
    for it in lay_list(cfg):
        if it["name"].lower() == name.lower():
            return it
    return None


def lay_style_of(cfg, name):
    it = _lay_find(cfg, name) if name else None
    return it["style"] if it else ""


def lay_stored_name(cfg, name):
    it = _lay_find(cfg, name)
    return it["name"] if it else name


def lay_new(name, style):
    lay = IMap(LAY_DEF)
    if style == "drawio":
        lay["ComboArc"] = ""
    if style == "caps":
        lay["CapLegendShape"] = "0"
    lay["name"], lay["style"], lay["roles"], lay["pos"] = name, style, {}, {}
    return lay


def lay_read(cfg, name):
    """LayRead: the layout's settings (defaults for the ones it lacks), its Role. looks and
    Pos. caps; None when there is no such layout."""
    if name == "" or lay_style_of(cfg, name) == "":
        return None
    name = lay_stored_name(cfg, name)
    sec = cfg.ini.section("layout." + name)
    if sec is None:
        return None
    lay = lay_new(name, lay_style_raw(cfg, name))
    roles, pos_txt = {}, ""
    for ln in sec.split("\n"):
        if "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k, v = k.strip(), v.strip()
        if k[:5].lower() == "role.":
            rm = IMap()
            for kv in v.split(";"):
                if "=" in kv:
                    a, b = kv.split("=", 1)
                    rm[a.strip()] = b.strip()
            roles[k[5:]] = rm
        elif k[:4].lower() == "pos.":
            pos_txt += k[4:] + "=" + v + "\n"
        elif k in lay and k.lower() not in ("name", "style", "roles", "pos"):
            lay[k] = v
    lay["roles"], lay["pos"] = roles, cap_pos_parse(pos_txt)
    return lay


def lay_enabled(cfg, name):
    if name == "" or lay_style_of(cfg, name) == "":
        return True
    return cfg.ini.read("layout." + lay_stored_name(cfg, name), "Enabled", "1").strip() != "0"


def lay_num(v, lo, hi, d):
    n = cap_opt_num(v, lo, hi)
    return d if n == "" else n


def lay_combo(lay):
    return combo_norm({"arc": lay["ComboArc"], "opac": lay["ComboOpacity"], "fill": lay["ComboFill"],
                       "scale": lay["ComboScale"], "font": lay["ComboFont"], "textop": lay["ComboTextOpacity"],
                       "border": lay["ComboBorder"], "outline": lay["ComboOutline"]})


def lay_apply(cfg, lay):
    """LayApply: the layout made current - cfg's layout globals set from it."""
    st = lay["style"]
    cfg.key_style, cfg.lay_name = st, lay["name"]
    cfg.text_up[st] = lay_num(lay["TextUp"], -10, 10, "0")
    cfg.combo_set[st] = lay_combo(lay)
    lv = lay["CapBadge"].strip().lower()
    cfg.cap_badge = lv if lv in ("inlay", "decal", "raised", "printed", "emboss", "deboss", "plate",
                                 "inset", "tag", "current") else "inlay"
    lv = lay["CapBadgeFit"].strip().lower()
    cfg.cap_badge_fit = lv if lv in ("scale", "shrink", "move", "off") else "scale"
    cfg.cap_badge_margin = first_num(lay["CapBadgeMargin"], 0)
    cfg.cap_badge_text = lay_num(lay["CapBadgeText"], 20, 300, "100")
    cfg.cap_badge_top = cap_opt_colour(lay["CapBadgeTop"])
    cfg.cap_badge_bottom = cap_opt_colour(lay["CapBadgeBottom"])
    cfg.cap_badge_border = cap_opt_colour(lay["CapBadgeBorder"])
    cfg.cap_badge_opac = lay_num(lay["CapBadgeOpacity"], 0, 100, "100")
    cfg.cap_badge_radius = cap_opt_num(lay["CapBadgeRadius"], 0, 6)
    cfg.cap_badge_depth = lay_num(lay["CapBadgeDepth"], 0, 100, "60")
    cfg.cap_badge_outline = first_num(lay["CapBadgeOutline"], 0) != 0
    cfg.cap_edge_top = first_num(lay["CapEdgeOnTop"], 1) != 0
    lv = lay["CapGlass"].strip().lower()
    cfg.cap_glass = lv if lv in ("classic", "gloss", "coat", "crystal", "over", "overface") else "none"
    cfg.cap_glass_k = lay_num(lay["CapGlassStrength"], 0, 200, "100")
    cfg.cap_glass_bg = first_num(lay["CapGlassBackground"], 1) != 0
    cfg.cap_dish_def = lay_num(lay["CapDish"], 0, 100, "0")
    cfg.cap_dish_var = lay_num(lay["CapDishVariation"], 0, 100, "0")
    cfg.cap_text_warp = lay_num(lay["CapLegendShape"], 0, 4, "0")
    cfg.render_light = "studio" if lay["RenderLight"].strip().lower() == "studio" else "lamp"
    cfg.render_shape = "wide" if lay["RenderShape"].strip().lower() == "wide" else "real"
    cfg.render_shade = lay_num(lay["RenderShading"], 0, 200, "100")
    cfg.render_hilite = lay_num(lay["RenderHighlights"], 0, 200, "100")
    cfg.render_text = cap_opt_num(lay["RenderKeyText"], 20, 150)
    cfg.render_ring = first_num(lay["RenderRings"], 1) != 0
    cfg.render_ao = lay_num(lay.get("RenderAO", "0"), 0, 3, "0")      # v0.2.26 (.194)
    cfg.cap_pos, cfg.lay_roles = lay["pos"], lay["roles"]
    return cfg


def target_set(cfg, name):
    """TargetSet: LayApply(LayRead(name))."""
    lay = lay_read(cfg, name)
    if lay is None:
        raise M.Die(f'No layout "{name}" in {cfg.ini_file}.')
    return lay_apply(cfg, lay)


# ------------------------------------------------------- caps by position
def cap_pos_parse(txt):
    out = {}
    for ln in txt.replace("\r", "").split("\n"):
        ln = ln.strip()
        if ln == "" or ln.startswith(";") or "=" not in ln:
            continue
        p, rest = ln.split("=", 1)
        p = p.strip()
        m = {"model": "ldsa", "turn": 0, "long": True, "bear": "", "place": "centre"}
        for i, t in enumerate(rest.strip().split(" ")):
            t = t.strip().lower()
            if t == "":
                continue
            if i == 0:
                m["model"] = t
            elif t in ("turn", "turn180"):
                m["turn"] = 180
            elif t == "turn90":
                m["turn"] = 90
            elif t == "turn270":
                m["turn"] = 270
            elif t == "stretch":
                m["long"] = False
            elif t in ("brass", "ruby"):
                m["bear"] = t
            elif t in ("centre", "lower"):
                m["place"] = t
        if p != "" and p != "ExportSuffix":
            out[p] = m
    return out


def cap_pos_str(m):
    v = m["model"]
    if m["turn"] == 180:
        v += " turn"
    elif m["turn"]:
        v += " turn" + str(m["turn"])
    if not m["long"]:
        v += " stretch"
    if m["bear"] != "":
        v += " " + m["bear"] + " " + m["place"]
    return v


def cap_pos_sig(cfg):
    txt, used = "b3;", {}
    for p in ahk_sorted(cfg.cap_pos):
        m = cfg.cap_pos[p]
        txt += p + "=" + cap_pos_str(m) + ";"
        used[m["model"]] = True
    for mk in ahk_sorted(used):
        fp = os.path.join(cfg.capmodel_dir, mk + ".capmodel")
        txt += mk + ":" + str(os.path.getsize(fp) if os.path.isfile(fp) else 0) + ";"
    return crc32_hex(txt)


def cap_model_file(cfg, mk):
    return capmodel(cfg.capmodel_dir, mk)


# ------------------------------------------------------------------- roles
def _norm_grad(v): return "none" if v in ("", "none") else v
def _norm_dir(v): return "south" if v == "" else v.lower()
def _norm_glass(v): return "1" if v == "1" else "0"
def _norm_opac(v): return v if is_number(v) else "100"


def _no_stroke(st):
    return M.style_get(st, "strokeColor") in ("none", "", "-")


def _role_cells(doc):
    return doc.xpath("//diagram[@name=" + M.q(M.ROLES_TAB) + "]//mxCell[@vertex='1']")


def load_roles(doc, warn):
    """LoadRoles: [roles (name -> IMap), order] from the @config-roles swatches."""
    roles, order = {}, []
    for c in _role_cells(doc):
        name = M.plain_text(c).strip()
        st = c.get("style") or ""
        fill = M.style_get(st, "fillColor", "")
        if name == "" or fill in ("", "none"):
            continue
        if re.search(r"[;=$]", name):
            warn.append(f'role swatch "{name}" skipped - a role name cannot contain ; = or $.')
            continue
        if name in roles:
            warn.append(f'role swatch "{name}" appears twice on {M.ROLES_TAB} - the first one is used.')
            continue
        if M.style_get(st, "roleKind", "") == "badge":
            continue
        sw = M.style_get(st, "strokeWidth", "")
        r = IMap(id=c.get("id"), fill=fill, grad=_norm_grad(M.style_get(st, "gradientColor", "")),
                 gdir=_norm_dir(M.style_get(st, "gradientDirection", "")),
                 glass=_norm_glass(M.style_get(st, "glass", "")),
                 opac=_norm_opac(M.style_get(st, "roleOpacity", "")),
                 stroke="none" if _no_stroke(st) else M.style_get(st, "strokeColor"),
                 sw=sw if is_number(sw) else "1")
        for k in CAP_KEYS:
            r[k] = M.style_get(st, k, "")
        roles[name] = r
        order.append(name)
    return roles, order


def roles_overlay(roles, own):
    for rn, rr in roles.items():
        rm = own.get(rn, {})
        for k in CAP_KEYS:
            rr[k] = rm[k] if k in rm else ""


def load_cap_roles(cfg, doc, warn):
    roles, order = load_roles(doc, warn)
    roles_overlay(roles, cfg.lay_roles)
    return roles, order


def load_badge(doc):
    for c in _role_cells(doc):
        st = c.get("style") or ""
        if M.style_get(st, "roleKind", "") != "badge":
            continue
        sw = M.style_get(st, "strokeWidth", "")
        return IMap(id=c.get("id"), name=M.plain_text(c).strip(), fill=M.style_get(st, "fillColor", ""),
                    grad=_norm_grad(M.style_get(st, "gradientColor", "")),
                    gdir=_norm_dir(M.style_get(st, "gradientDirection", "")),
                    glass=_norm_glass(M.style_get(st, "glass", "")), opac="100",
                    stroke="none" if _no_stroke(st) else M.style_get(st, "strokeColor"),
                    sw=sw if is_number(sw) else "1")
    return None


# --------------------------------------------------------------- cap looks
def cap_prop(r, k):
    return str(r[k]).strip() if k in r else ""


def cap_transparent(r):
    return same_num(r["opac"], 0)


def cap_look(cfg, r):
    fill = cap_hex(cap_prop(r, "capFill") or r["fill"])
    gv = cap_prop(r, "capGrad")
    if gv == "":
        gv = r["grad"] if "grad" in r else "none"
    grad = "" if gv in ("none", "") else cap_hex(gv, "")
    d = cap_prop(r, "capDir")
    if d == "":
        d = r["gdir"] if "gdir" in r else "south"
    d = d.lower()
    if d not in ("south", "north", "east", "west"):
        d = "south"
    edge = cap_hex(cap_prop(r, "capEdge"), "")
    if edge == "":
        edge = grad if grad != "" else fill
    dv, sv = cap_prop(r, "capDepth"), cap_prop(r, "capShine")
    depth = max(0, min(100, to_num(dv))) if is_number(dv) else 100
    shine = max(0, min(100, to_num(sv))) if is_number(sv) else 33
    xv = cap_prop(r, "capDish")
    if not is_number(xv):
        xv = r["dishDef"] if ("dishDef" in r and is_number(r["dishDef"])) else cfg.cap_dish_def
    dish = max(0, min(100, to_num(xv))) if is_number(xv) else 0
    return {"fill": fill, "grad": grad, "dir": d, "edge": edge, "depth": depth, "shine": shine, "dish": dish}


def render_custom(r):
    return any(cap_prop(r, k) != "" for k in RND_KEYS)


# .110 / .172 / .173: Shape entries that are model files (RENDER_SHAPE_FILES)
RENDER_SHAPE_FILES = {"chicago": "chicago_convex", "lameflat": "lame_flat", "lamewflat": "lame_wflat",
                      "xwflat": "ldsa_xwflat", "lamexwflat": "lame_xwflat"}       # .173: extra-wide


def render_shape_of(cfg, r, default=""):
    rs = cap_prop(r, "rndShape").lower()
    if rs in RENDER_SHAPE_FILES:
        mf = cap_model_file(cfg, RENDER_SHAPE_FILES[rs])
        if mf and "1u" in mf["secs"]:
            return "m:" + RENDER_SHAPE_FILES[rs]
        rs = ""
    return rs if rs in ("flat", "wflat", "cover", "bezel") else (default or cfg.render_shape)


def render_look(cfg, r):
    lk = cap_look(cfg, r)
    f = cap_hex(cap_prop(r, "rndFill"), "")
    if f:
        lk["fill"] = f
    gv = cap_prop(r, "rndGrad")
    if gv == "none":
        lk["grad"] = ""
    elif cap_hex(gv, ""):
        lk["grad"] = cap_hex(gv, "")
    dv = cap_prop(r, "rndDir").lower()
    if dv in ("south", "north", "east", "west"):
        lk["dir"] = dv
    e = cap_hex(cap_prop(r, "rndEdge"), "")
    lk["edgeOwn"] = e if e else cap_hex(cap_prop(r, "capEdge"), "")
    lk["shape"] = render_shape_of(cfg, r)
    return lk


def cap_look_str(cfg, r):
    lk = cap_look(cfg, r)
    s = (lk["fill"] + "/" + lk["grad"] + "/" + lk["dir"] + "/" + lk["edge"] + "/" + fmt4(lk["depth"])
         + "/" + fmt4(lk["shine"]) + "/" + fmt4(lk["dish"]) + "/" + str(r["opac"]) + "/" + str(r["stroke"]))
    if cap_prop(r, "capGlass") == "off":
        s += "/g:off"
    if render_custom(r):
        rl = render_look(cfg, r)
        s += "/r:" + rl["fill"] + "/" + rl["grad"] + "/" + rl["dir"] + "/" + rl["edgeOwn"] + "/" + rl["shape"]
    return s


def roles_sig(cfg, doc):
    roles, order = load_cap_roles(cfg, doc, [])
    sig = "".join(n + "=" + cap_look_str(cfg, roles[n]) + "\n" for n in order)
    bd = load_badge(doc)
    if bd is not None:
        sig += "@badge=" + bd["fill"] + "/" + bd["grad"] + "\n"
    return sig


def cap_looks_now(cfg, doc):
    """name -> CRC of its look (and @badge), as CapLookChanges stores them."""
    roles, order = load_cap_roles(cfg, doc, [])
    now = {n: crc32_hex(cap_look_str(cfg, roles[n])) for n in order}
    bd = load_badge(doc)
    if bd is not None:
        now["@badge"] = crc32_hex(bd["fill"] + "/" + bd["grad"])
    return now


def cap_look_changes(cfg, doc, marks):
    """CapLookChanges: marks the layers whose roles' cap looks changed since the last run of
    this layout, and stores the looks ([state] CapLooks<sfx>)."""
    now = cap_looks_now(cfg, doc)
    old = {}
    for part in cfg.ini.read("state", "CapLooks" + cfg.out_sfx(), "").split(";"):
        if "=" in part:
            a, b = part.split("=", 1)
            old[a] = b
    if old:
        changed = {n for n, crc in now.items() if old.get(n) != crc}
        if changed:
            for lay in M.valid_layer_groups(doc):
                if "@badge" in changed:
                    marks[lay["idx"]] = True
                    continue
                for key in M.index_keys(doc, lay["id"]):
                    if M.style_get(key.get("style"), "keyRole", "") in changed:
                        marks[lay["idx"]] = True
                        break
    cfg.ini.write("".join(n + "=" + now[n] + ";" for n in ahk_sorted(now)), "state", "CapLooks" + cfg.out_sfx())


# --------------------------------------------------------------- style tag
def cap_badge_params(cfg):
    return {"top": cfg.cap_badge_top, "bottom": cfg.cap_badge_bottom, "border": cfg.cap_badge_border,
            "opac": cfg.cap_badge_opac, "radius": cfg.cap_badge_radius, "depth": cfg.cap_badge_depth,
            "outline": 1 if cfg.cap_badge_outline else 0}


def render_text_factor(cfg, shapes, shape="", pct=""):
    """RenderTextFactor; shapes = a render_shade.Shapes (for the face of a shape)."""
    v = "" if pct == "auto" else pct if pct != "" else cfg.render_text
    if is_number(v):
        return max(0.2, min(1.5, to_num(v) / 100))
    f = shapes.src(shape or cfg.render_shape)["face"]
    ts = (1, 1)
    if is_number(cfg.cap_text_warp) and to_num(cfg.cap_text_warp) > 0:      # .162: as RenderTextFactor
        import keys as K
        ts = K.tilt_scale(shapes, shape)
    return round_ahk(min((f[2] - f[0]) / ts[0] / 25, (f[3] - f[1]) / ts[1] / 25), 2)        # .170: against the key


def _s(v):
    return repr(v) if isinstance(v, float) else str(v)


def render_style_tag(cfg, shapes):
    cv = cfg.combo_val
    if not cfg.caps_like():
        dtag = "drawio"
        dcb = ",".join(cv(k) for k in ("arc", "opac", "fill", "scale", "font", "textop", "border", "outline"))
        if dcb != ",,,100,,,,":
            dtag += "/cmb" + dcb
        tu = cfg.text_up_val()
        return dtag + ("/tu" + fmt4(tu) if tu != 0 else "")
    bp = cap_badge_params(cfg)
    tag = ("caps/" + cfg.cap_badge + "/" + cfg.cap_badge_fit + "/" + fmt4(cfg.cap_badge_margin) + "/"
           + cfg.cap_badge_text + "/" + cv("arc") + "/" + cv("opac") + "/" + cv("fill") + "/"
           + ("rim" if cfg.cap_edge_top else "") + "/v" + cfg.cap_dish_var + "/ls" + cfg.cap_text_warp
           + "/light2/" + ",".join(_s(bp[k]) for k in ("top", "bottom", "border", "opac", "radius", "depth",
                                                         "outline")))
    if cv("scale") != "100":
        tag += "/bs" + cv("scale")
    if cv("font") + cv("textop") + cv("border") + cv("outline") != "":
        tag += "/cb" + ",".join(cv(k) for k in ("font", "textop", "border", "outline"))
    if cfg.key_style == "render":
        tag = ("render/" + tag[5:] + "/" + cfg.render_light + "/" + cfg.render_shape + "/" + cfg.render_shade
               + "/" + cfg.render_hilite + "/t" + _s(render_text_factor(cfg, shapes)) + "/r3"
               + ("" if cfg.render_ring else "/nr") + ("" if cfg.render_inset == "0.5" else "/i" + cfg.render_inset)
               + "/fc" + ("/cm" + cap_pos_sig(cfg) if cfg.cap_pos else "")
               + ("/ao" + cfg.render_ao if to_num(cfg.render_ao) > 0 else ""))      # .194
    if cfg.key_style != "render" and cfg.cap_glass != "none":
        tag += "/gl:" + cfg.cap_glass + ":" + cfg.cap_glass_k + ":r" + ("" if cfg.cap_glass_bg else ":nobg")
    tu = cfg.text_up_val()
    if tu != 0:
        tag += "/tu" + fmt4(tu)
    return tag


def render_style_name(tag):
    return "Render" if tag.startswith("render/") else "SVG caps" if tag.startswith("caps/") else "draw.io"


# ------------------------------------------------------- [state] / [cache]
def load_extents(cfg, sec, old_file=""):
    ext = {}
    txt = cfg.ini.read(sec, "extents", "")
    if txt != "":
        txt = txt.replace(";", "\n")
    elif old_file and os.path.isfile(old_file):
        txt = open(old_file, encoding="utf-8-sig").read()
    for line in txt.replace("\r", "").split("\n"):
        f = line.split("|")
        if line == "" or len(f) < 3:
            continue
        key = f[0] + "|" + f[1]
        if f[2] == "BLANK":
            ext[key] = None
        elif len(f) >= 6:
            ext[key] = {"x1": to_num(f[2]), "y1": to_num(f[3]), "x2": to_num(f[4]), "y2": to_num(f[5])}
    return ext


def save_extents(cfg, sec, ext):
    parts = []
    for key in ahk_sorted(ext):
        b = ext[key]
        parts.append(f'{key}|{b["x1"]}|{b["y1"]}|{b["x2"]}|{b["y2"]}' if b else key + "|BLANK")
    cfg.ini.write(";".join(parts), sec, "extents")


def box_str(b):
    return f'{b["x1"]}|{b["y1"]}|{b["x2"]}|{b["y2"]}'


def box_parse(txt):
    f = txt.strip().split("|")
    if len(f) < 4:
        return None
    return {"x1": to_num(f[0]), "y1": to_num(f[1]), "x2": to_num(f[2]), "y2": to_num(f[3])}


def union_box(a, b):
    if not a:
        return b
    return {"x1": min(a["x1"], b["x1"]), "y1": min(a["y1"], b["y1"]),
            "x2": max(a["x2"], b["x2"]), "y2": max(a["y2"], b["y2"])}


def load_role_layers(cfg, sx):
    out = set()
    for v in cfg.ini.read("state", "RoleLayers" + sx, "").split(","):
        v = v.strip(" ")
        if re.fullmatch(r"[-+]?\d+", v):
            out.add(int(v))
    return out


def save_role_layers(cfg, mp, sx):
    cfg.ini.write(",".join(str(i) for i in sorted(mp)) if mp else "", "state", "RoleLayers" + sx)


def out_sfx_all(cfg):
    out = {}
    for it in lay_list(cfg):
        out.setdefault(("_" + it["name"]).lower(), "_" + it["name"])
    out.setdefault(cfg.out_sfx().lower(), cfg.out_sfx())
    return [out[k] for k in sorted(out)]


def pending_role_layers(cfg, moved_idx, now_idx, cur_idx=None):
    old_to_new = {int(old): nw for nw, old in moved_idx.items()}
    cur, mine = cfg.out_sfx(), set()
    for sx in out_sfx_all(cfg):
        out = set()
        for idx in load_role_layers(cfg, sx):
            if idx in old_to_new:
                out.add(old_to_new[idx])
            elif idx not in moved_idx:
                out.add(idx)
        out |= set(now_idx)
        if sx.lower() == cur.lower() and cur_idx is not None:
            out |= set(cur_idx)
        save_role_layers(cfg, out, sx)
        if sx.lower() == cur.lower():
            mine = out
    return mine


# ---------------------------------------------------------- shapes by position
def render_pos_shape(cfg, pos, tall, pmap=None):
    """RenderPosShape: the model shape a position's cap takes ('' = the layout's own)."""
    mp = cfg.cap_pos if pmap is None else pmap
    if pos not in mp:
        return ""
    m = mp[pos]
    mk = m["model"]
    mf = cap_model_file(cfg, mk)
    if mk == "ldsa":
        if not (tall and m["long"] and mf and "long" in mf["secs"]):
            return ""
        return "m:ldsa:L" + (":w" if cfg.render_shape == "wide" else "")
    if not mf or "1u" not in mf["secs"]:
        return ""
    v = "m:" + mk
    td = m["turn"]
    if (td == 180 and mf["turn"]) or (td in (90, 270) and mf["turn90"] and not tall):
        v += ":r" + str(td)
    if tall and m["long"] and "long" in mf["secs"]:
        v += ":L"
    return v


def render_quarter(shape):
    return bool(re.search(r":r(90|270)(:|$)", shape or ""))
