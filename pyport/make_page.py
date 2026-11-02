"""One-page .drawio: a layer group of `background` with everything under it."""
import sys, re, copy, xml.etree.ElementTree as ET
src, prefix, out = sys.argv[1:4]
root = ET.parse(src).getroot()
bg = [d for d in root.findall('diagram') if d.get('name') == 'background'][0]
model = bg.find('mxGraphModel'); cells = list(model.find('root'))
kids = {}
for c in cells: kids.setdefault(c.get('parent'), []).append(c)
grp = None
for c in cells:
    if 'group' in (c.get('style') or ''):
        txt = ' '.join(re.sub('<[^>]+>', '', k.get('value') or '') for k in kids.get(c.get('id'), []))
        if re.search(r'(^|\s)' + re.escape(prefix), txt):
            grp = c; break
keep = []
def add(c):
    keep.append(c)
    for k in kids.get(c.get('id'), []): add(k)
add(grp)
nm = copy.deepcopy(model); r = nm.find('root')
for c in list(r): r.remove(c)
for c in cells[:2]: r.append(copy.deepcopy(c))          # the two root cells
for c in keep:
    c2 = copy.deepcopy(c)
    if c is grp: c2.set('parent', cells[1].get('id'))
    r.append(c2)
mf = ET.Element('mxfile'); d = ET.SubElement(mf, 'diagram', id='p', name='layer'); d.append(nm)
ET.ElementTree(mf).write(out, encoding='unicode')
print(out, len(keep), 'cells')
