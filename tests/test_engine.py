"""engine.py end to end in a scratch copy of the user's folder (/home/claude/e2e): export
<layout> layer 0 (Debug on, as the INI has it), then diff every page the engine kept as .drawio
against the .148 run's (refraw/_raw_<layout>/), and report the outputs and the times."""
import os, sys, glob, json, time
import fonts as FN, pagediff as PD, model as M, engine as E

lay = sys.argv[1] if len(sys.argv) > 1 else 'LameSaddle'
D = '/home/claude/e2e'
# GDI's answer for Helvetica (Arial) is not available here: as in test_pages
FN.NOT_COVERED['Helvetica'] = {int(l, 16) for l in open('/home/claude/pyport/arial_missing.txt') if l.strip() and l[0] != ';'}
os.makedirs(f'{D}/_out', exist_ok=True)
t = time.time()
code = E.main(['export', '--ini', f'{D}/export_from_drawio_PY.ini', '--ahk', f'{D}/export_from_drawio_PY.ah2',
               '--layout', lay, '--layers', '0', '--drawio', '/home/claude/dl/drawio30/resources/app.asar',
               '--progress', f'{D}/_out/progress.txt', '--result', f'{D}/_out/result.json'])
el = time.time() - t
res = json.load(open(f'{D}/_out/result.json', encoding='utf-8'))
print(f'\n== exit {code} in {el:.1f}s; ok {res["ok"]}, {res["images"]} images, {res["mirrored"]} mirrored')
print(res['message'][:3000])
ref = f'/home/claude/refraw/_raw_{lay}/'
mine = f'{D}/_raw_{lay}/'
for f in sorted(glob.glob(ref + '*.drawio')):
    n = os.path.basename(f)
    if not os.path.exists(mine + n):
        print(f'  {n}: not made by the engine'); continue
    print(f'  -- {n}')
    PD.diff(f, mine + n)
