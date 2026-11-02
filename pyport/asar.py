"""Minimal asar reader: list / extract. Usage: asar.py list|extract <app.asar> [outdir] [prefix]"""
import json, struct, sys, os
def read_index(f):
    f.seek(0); hdr = f.read(16)
    # pickle: [4 size=4][4 header_pickle_size][4 payload size][4 json len]
    _, hsize, _, jlen = struct.unpack('<4I', hdr)
    js = json.loads(f.read(jlen).decode('utf-8'))
    return js, 8 + hsize
def walk(node, path=''):
    for name, ch in node.get('files', {}).items():
        p = f'{path}/{name}' if path else name
        if 'files' in ch: yield from walk(ch, p)
        else: yield p, ch
if __name__ == '__main__':
    cmd, src = sys.argv[1], sys.argv[2]
    with open(src, 'rb') as f:
        idx, base = read_index(f)
        if cmd == 'list':
            for p, ch in walk(idx): print(ch.get('size', 0), 'U' if ch.get('unpacked') else '', p)
        else:
            out = sys.argv[3]; pre = sys.argv[4] if len(sys.argv) > 4 else ''
            n = 0
            for p, ch in walk(idx):
                if not p.startswith(pre) or ch.get('unpacked') or 'link' in ch: continue
                d = os.path.join(out, p); os.makedirs(os.path.dirname(d), exist_ok=True)
                f.seek(base + int(ch['offset'])); open(d, 'wb').write(f.read(ch['size'])); n += 1
            print(n, 'files')
