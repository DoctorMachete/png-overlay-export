"""The combo / key-label data of the .148 script: LoadComboData (combo_data.txt,
zmk_combo_cache v1-v3), CacheUnesc, SplitNums, LoadComboMap (combo_map.ini),
HaveKeyData, KeyBehaviour; the ZMK layout export: FindLayoutJson, ParseKeyData (ReadComboKeys,
KpText), CacheEsc, JoinNums, SaveComboData, and read_layout (Main's choice between them)."""
import glob, json, os
from util import ahk_sorted

CACHE_HEADER = 'zmk_combo_cache\tv3'


def cache_esc(s):
    return s.replace('\\', '\\\\').replace('\t', '\\t').replace('\r', '\\r').replace('\n', '\\n')


def _s(v):
    """A JSON value as AHK's  v ""  makes it text."""
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return '' if v is None else str(v)


def join_nums(arr):
    return ','.join(_s(v) for v in arr)


def kp_text(params):
    """KpText: &kp parameters as the keymap writes them ("LS(TAB)", "LC(LS(F22))")."""
    if not isinstance(params, list):
        return ''
    out = []
    for p in params:
        if not isinstance(p, dict):
            continue
        v = _s(p.get('value', ''))
        if v == '':
            continue
        if isinstance(p.get('params'), list) and p['params']:
            inner = kp_text(p['params'])
            if inner != '':
                v += '(' + inner + ')'
        out.append(v)
    return ','.join(out)


def read_combo_keys(layers, idx, positions, lab, kp, beh):
    if idx < 0 or idx >= len(layers):
        return
    lay = layers[idx]
    if not isinstance(lay, list):
        return
    for p in positions:
        pos = int(p)
        if pos < 0 or pos >= len(lay):
            continue
        k = f'{idx}|{pos}'
        if k in beh:
            continue
        b = lay[pos]
        if not isinstance(b, dict):
            continue
        v = _s(b.get('value', ''))
        beh[k] = v
        d = b.get('decoration')
        if isinstance(d, dict) and 'label' in d:
            t = _s(d['label']).strip(' \t')
            if t != '':
                lab[k] = t
        if v.lower() == '&kp' and 'params' in b:
            t = kp_text(b['params'])
            if t != '':
                kp[k] = t


def parse_key_data(layout):
    """ParseKeyData: keyLabel / keyKp / keyBeh ('layer|pos') for the positions combos use."""
    lab, kp, beh = {}, {}, {}
    layout['keyLabel'], layout['keyKp'], layout['keyBeh'] = lab, kp, beh
    layers = layout.get('layers')
    if not isinstance(layers, list):
        return
    for c in layout.get('combos') or []:
        if not isinstance(c, dict) or 'layers' not in c or 'keyPositions' not in c:
            continue
        for li in c['layers']:
            if li < 0:                                    # every layer
                for i in range(len(layers)):
                    read_combo_keys(layers, i, c['keyPositions'], lab, kp, beh)
            else:
                read_combo_keys(layers, int(li), c['keyPositions'], lab, kp, beh)


def save_combo_data(path, layout):
    """SaveComboData: combo_data.txt (v3: C and K lines), UTF-8 without BOM, LF."""
    text = CACHE_HEADER + '\n'
    for c in layout.get('combos') or []:
        text += ('C\t' + cache_esc(_s(c.get('name', ''))) + '\t' + join_nums(c.get('layers', []))
                 + '\t' + join_nums(c.get('keyPositions', [])) + '\t' + cache_esc(_s(c.get('description', ''))) + '\n')
    lab, kp, beh = layout.get('keyLabel', {}), layout.get('keyKp', {}), layout.get('keyBeh', {})
    for k in ahk_sorted(beh):
        text += 'K\t' + k + '\t' + cache_esc(lab.get(k, '')) + '\t' + cache_esc(kp.get(k, '')) + '\t' + cache_esc(beh[k]) + '\n'
    try:
        os.remove(path)
    except OSError:
        pass
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def find_layout_json(d, ignore=()):
    """FindLayoutJson(dir, false): the one .json in d, '' for none; Die for several.  ignore:
    files that are not a layout (the exe's own result file, if it is put there)."""
    import model as M
    ig = {os.path.normcase(os.path.abspath(p)) for p in ignore if p}
    found = sorted(f for f in glob.glob(os.path.join(d, '*.json')) if os.path.normcase(os.path.abspath(f)) not in ig)
    if not found:
        return ''
    if len(found) > 1:
        raise M.Die(f'More than one .json in\n{d}\n\n' + ''.join(f'  - {f}\n' for f in found)
                    + '\nLeave only the current export.')
    return found[0]


def read_layout(cfg, ignore=()):
    """Main's start: a fresh ZMK export wins (parsed, cached, then deleted), else the cache."""
    import model as M
    jp = cfg.json_name if (cfg.json_name and os.path.exists(cfg.json_name)) else find_layout_json(cfg.base_dir, ignore)
    if jp:
        with open(jp, encoding='utf-8-sig') as f:
            layout = json.load(f)
        parse_key_data(layout)
        save_combo_data(cfg.combo_cache, layout)
        try:
            os.remove(jp)
        except OSError:
            pass
        return layout
    if os.path.exists(cfg.combo_cache):
        return load_combo_data(cfg.combo_cache)
    raise M.Die(f'No .json found in\n{cfg.base_dir}\n\nand no combo_data.txt cache exists yet.\n\n'
                'Export the ZMK layout and drop it in this folder.')


def cache_unesc(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == '\\' and i < n - 1:
            e = s[i + 1]
            i += 2
            out.append({'t': '\t', 'r': '\r', 'n': '\n', '\\': '\\'}.get(e, e))
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def split_nums(s):
    return [int(p) if p.strip().lstrip('+-').isdigit() else float(p) for p in s.split(',')] if s != '' else []


def load_combo_data(path):
    """LoadComboData: {combos: [{name, layers, keyPositions, description}], keyLabel, keyKp, keyBeh}
    (the key maps by 'layer|pos')."""
    combos, lab, kp, beh = [], {}, {}, {}
    raw = open(path, encoding='utf-8-sig').read()
    lines = raw.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    v2 = len(lines) >= 1 and ('\tv2' in lines[0] or '\tv3' in lines[0])
    for i, ln in enumerate(lines):
        if i == 0 or ln == '':
            continue
        f = ln.split('\t')
        off = 0
        if v2:
            if len(f) < 2:
                continue
            if f[0] == 'K':
                if len(f) >= 4:
                    if f[2] != '':
                        lab[f[1]] = cache_unesc(f[2])
                    if f[3] != '':
                        kp[f[1]] = cache_unesc(f[3])
                    if len(f) >= 5:
                        beh[f[1]] = cache_unesc(f[4])
                continue
            if f[0] != 'C':
                continue
            off = 1
        if len(f) < 3 + off:
            continue
        combos.append({'name': cache_unesc(f[off]), 'layers': split_nums(f[1 + off]),
                       'keyPositions': split_nums(f[2 + off]),
                       'description': cache_unesc(f[3 + off]) if len(f) >= 4 + off else ''})
    return {'combos': combos, 'keyLabel': lab, 'keyKp': kp, 'keyBeh': beh}


def load_combo_map(cfg):
    """LoadComboMap: combo name -> element spec, from combo_map.ini (if present)."""
    out = {}
    if not os.path.isfile(cfg.combo_mapf):
        return out
    for line in open(cfg.combo_mapf, encoding='utf-8-sig').read().splitlines():
        line = line.strip()
        if line == '' or line[0] in ';[' or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip()
        if ';' in v:
            v = v[:v.index(';')].strip()
        if k and v:
            out[k] = v
    return out


def have_key_data(layout):
    return any(layout.get(f) for f in ('keyBeh', 'keyLabel', 'keyKp'))


def key_behaviour(layout, idx, p):
    return layout.get('keyBeh', {}).get(f'{idx}|{p}', '')
