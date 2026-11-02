"""Mirrored layers of the .148 script: MirrorParse, MirrorMoved, MirrorTwin, MirrorLoad
([mirrormap] / old [mirror]), MirrorComboLoad ([mirrorcombo]), MirrorCombos, MirrorSwap,
MirrorGeo, MirrorSetGeo, and the source copy + layer of MirrorLayer_ (pages: pages.build_page*
with the returned source and layer; the export/compose loop belongs to engine.py)."""
import copy, re
import model as M


def mirror_parse(txt):
    """MirrorParse: 60 distinct positions 0..59, or (None, error)."""
    txt = re.sub(r'(?s)/\*.*?\*/', ' ', txt)
    txt = re.sub(r'(?m)//.*$', ' ', txt)
    vals = [int(v) for v in re.findall(r'\d+', txt)]
    if len(vals) != 60:
        return None, f'{len(vals)} numbers, need 60'
    seen = set()
    for v in vals:
        if v > 59:
            return None, f'{v} is not a key position (0-59)'
        if v in seen:
            return None, f'{v} is in the grid twice'
        seen.add(v)
    return vals, ''


def mirror_moved(a):
    return sum(1 for k, v in enumerate(a) if v != k)


def mirror_twin(p):
    return 'RH-' + p[3:] if p[:3] == 'LH-' else 'LH-' + p[3:] if p[:3] == 'RH-' else p


def _int_key(ln):
    if '=' not in ln:
        return None
    k = ln.split('=', 1)[0].strip()
    return int(k) if re.fullmatch(r'[-+]?\d+', k) else None


def mirror_load(cfg):
    """MirrorLoad: layer -> its key map (a[k] = the position whose place key k takes)."""
    out = {}
    for ln in (cfg.ini.section('mirrormap') or '').split('\n'):
        k = _int_key(ln)
        if k is None:
            continue
        a, _ = mirror_parse(ln.split('=', 1)[1])
        if a and mirror_moved(a):
            out[k] = a
    for ln in (cfg.ini.section('mirror') or '').split('\n'):
        k = _int_key(ln)
        if k is None or k in out:
            continue
        a = list(range(60))
        for p in ln.split('=', 1)[1].split(','):
            p = p.strip(' ')
            if p and p in M.POS_LABEL:
                a[M.POS_LABEL.index(p)] = M.POS_LABEL.index(mirror_twin(p)) if mirror_twin(p) in M.POS_LABEL else -1
        if mirror_moved(a):
            out[k] = a
    return out


def mirror_combo_load(cfg):
    out = {}
    for ln in (cfg.ini.section('mirrorcombo') or '').split('\n'):
        k = _int_key(ln)
        if k is None:
            continue
        a, _ = mirror_parse(ln.split('=', 1)[1])
        if a:
            out[k] = a
    return out


def mirror_combos(layout, a):
    """MirrorCombos: the combos with their key positions moved by map a."""
    inv = {v: k for k, v in enumerate(a)}
    out = dict(layout)
    out['combos'] = [dict(c, keyPositions=[inv.get(int(p), p) for p in c['keyPositions']])
                     if 'keyPositions' in c else dict(c) for c in layout.get('combos', [])]
    return out


def mirror_geo(node):
    gm = node.find('mxGeometry')
    return [gm.get(k, '') if gm is not None else '' for k in ('x', 'y', 'width', 'height')] + \
        [M.style_get(node.get('style'), 'rotation', '')]


def mirror_set_geo(node, v):
    gm = node.find('mxGeometry')
    if gm is not None:
        for i, k in enumerate(('x', 'y', 'width', 'height')):
            if v[i] == '':
                gm.attrib.pop(k, None)
            else:
                gm.set(k, v[i])
    sa = node.get('style') or ''
    node.set('style', M.style_del(sa, 'rotation') if v[4] == '' else M.style_set(sa, 'rotation', v[4]))


def mirror_swap(doc, gid, a):
    at = M.index_keys(doc, gid)
    geo = [mirror_geo(n) for n in at]
    n = 0
    for k, v in enumerate(a):
        if v == k or v + 1 > len(at) or k + 1 > len(at):
            continue
        mirror_set_geo(at[v], geo[k])
        n += 1
    return n


def mirror_source(cfg, src_path, L, m, layout, cm=None, warn=None):
    """MirrorLayer_'s first half: (source copy with the pairs swapped, its layer, its combos), or
    None when no mirrored position was found."""
    src_m = M.Doc(M.load_xml(src_path))          # LoadSource([]): source fixes not ported yet
    if not mirror_swap(src_m, L['id'], m):
        if warn is not None:
            warn.append(f"layer {L['idx']}. {L['name']}: none of its mirrored positions was found - "
                        f"no {L['idx']}m.png made.")
        return None
    nd = src_m.xpath('//mxCell[@id=' + M.q(L['id']) + ']')
    if not nd:
        return None
    Lm = dict(L, node=nd[0], mirror=True)
    return src_m, Lm, mirror_combos(layout, cm if cm is not None else m)
