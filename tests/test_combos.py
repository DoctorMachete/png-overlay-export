"""ParseKeyData + SaveComboData round trip: a ZMK-style layout .json rebuilt from the user's
combo_data.txt (its combos; each cached position as a binding with its label, &kp params and
behaviour; filler bindings everywhere else) must give back the same file, byte for byte."""
import json, os, re, random
import combos as C

SRC = '/home/claude/combo_data.txt'
data = C.load_combo_data(SRC)


def kp_params(t):
    """'LS(TAB),A' -> [{'value': 'LS', 'params': [{'value': 'TAB'}]}, {'value': 'A'}]."""
    out, i = [], 0
    while i < len(t):
        m = re.match(r'[^(),]+', t[i:]); v = m.group(0); i += len(v)
        p = {'value': v}
        if i < len(t) and t[i] == '(':
            depth, j = 1, i + 1
            while depth:
                depth += {'(': 1, ')': -1}.get(t[j], 0); j += 1
            p['params'] = kp_params(t[i + 1:j - 1]); i = j
        out.append(p)
        if i < len(t) and t[i] == ',':
            i += 1
    return out


random.seed(1)
nl = 1 + max(int(k.split('|')[0]) for k in data['keyBeh'])
layers = [[{'value': random.choice(['&trans', '&kp', '&none']), 'params': [{'value': 'X'}],
            'decoration': {'label': 'filler'}} for _ in range(60)] for _ in range(nl)]
for k, beh in data['keyBeh'].items():
    li, p = map(int, k.split('|'))
    b = {'value': beh, 'params': kp_params(data['keyKp'][k]) if k in data['keyKp'] else []}
    b['decoration'] = {'label': '  ' + data['keyLabel'][k] + '\t'} if k in data['keyLabel'] else {}
    layers[li][p] = b
lay = {'layers': layers, 'combos': [dict(c) for c in data['combos']], 'keyboard': 'x'}
d = '/home/claude/pyport/_combos'; os.makedirs(d, exist_ok=True)
jp = os.path.join(d, 'layout.json'); json.dump(lay, open(jp, 'w', encoding='utf-8'), ensure_ascii=False)


class Cfg:
    base_dir, json_name, combo_cache = d, '', os.path.join(d, 'combo_data.txt')


got = C.read_layout(Cfg)
same = open(Cfg.combo_cache, 'rb').read() == open(SRC, 'rb').read()
print(f"{len(data['combos'])} combos, {len(data['keyBeh'])} keys; rebuilt cache byte-identical: {same}; "
      f".json deleted: {not os.path.exists(jp)}; second read from the cache: "
      f"{C.read_layout(Cfg)['keyBeh'] == got['keyBeh']}")
print('kp_text of a nested code:', C.kp_text(kp_params('LC(LS(F22))')))
