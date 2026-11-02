"""Compare the exe's fontcheck output with ci/arial_expect.txt; report in the job summary."""
import os, sys
exp = {l.split()[0]: l.split()[1] for l in open(sys.argv[1], encoding='utf-8') if l.strip() and l[0] != ';'}
got = {l.split()[0]: l.split()[1] for l in open(sys.argv[2], encoding='utf-8-sig') if l.strip()}
bad = [(c, exp[c], got.get(c, '?')) for c in exp if got.get(c) != exp[c]]
md = [f'### GDI glyph check (Helvetica = Arial)', f'{len(exp) - len(bad)} of {len(exp)} as expected.']
md += [f'- U+{c} {chr(int(c, 16))}: expected {e}, Windows says {g}' for c, e, g in bad]
out = '\n'.join(md) + '\n'
print(out)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8').write(out)
