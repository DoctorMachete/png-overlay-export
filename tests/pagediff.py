"""Structural diff of two .drawio pages: cells by id, in order; attributes, geometry, value."""
import sys
from lxml import etree

def cells(path_or_el):
    r = etree.parse(path_or_el).getroot() if isinstance(path_or_el, str) else path_or_el
    out = []
    for c in r.iter('mxCell'):
        g = c.find('mxGeometry')
        a = dict(c.attrib)
        out.append((c.get('id'), a, dict(g.attrib) if g is not None else None,
                    [etree.QName(x).localname for x in g] if g is not None else []))
    return out

def style_dict(s):
    return [kv for kv in (s or '').split(';') if kv]

def diff(a, b, la='ahk', lb='py', show=40):
    A, B = cells(a), cells(b)
    ia, ib = [x[0] for x in A], [x[0] for x in B]
    n = 0
    if ia != ib:
        sa, sb = set(ia), set(ib)
        print(f'  ids only in {la}: {[i for i in ia if i not in sb]}')
        print(f'  ids only in {lb}: {[i for i in ib if i not in sa]}')
        if [i for i in ia if i in sb] != [i for i in ib if i in sa]:
            print('  order differs'); n += 1
        n += len(sa ^ sb)
    db = {x[0]: x for x in B}
    for cid, a1, g1, k1 in A:
        if cid not in db:
            continue
        _, a2, g2, k2 = db[cid]
        for k in sorted(set(a1) | set(a2)):
            v1, v2 = a1.get(k), a2.get(k)
            if v1 != v2:
                n += 1
                if n <= show:
                    if k == 'style':
                        s1, s2 = style_dict(v1), style_dict(v2)
                        print(f'  {cid} style: -{[x for x in s1 if x not in s2]} +{[x for x in s2 if x not in s1]}'
                              + ('' if sorted(s1) != sorted(s2) else ' (order only)'))
                    else:
                        print(f'  {cid} @{k}:\n     {la}: {str(v1)[:300]}\n     {lb}: {str(v2)[:300]}')
        if g1 != g2 or k1 != k2:
            n += 1
            if n <= show:
                print(f'  {cid} geometry: {la} {g1} {k1}\n           {lb} {g2} {k2}')
    print(f'  {n} difference(s); {len(A)} vs {len(B)} cells')
    return n

if __name__ == '__main__':
    diff(sys.argv[1], sys.argv[2])
