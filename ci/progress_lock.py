"""The progress file under AHK's polling: a thread keeps opening and reading it (as FileRead
does) while lines are written by the old way (a bare os.replace) and by engine.Progress.say.
Reports how often each failed; the old way failing on Windows is what stopped v0.1.0."""
import os, sys, threading, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pyport'))
import engine as E

d = tempfile.mkdtemp()
path = os.path.join(d, 'progress.txt')
open(path, 'w').write('0\tstart')
stop = False

def reader():
    while not stop:
        try:
            with open(path, encoding='utf-8') as f:
                f.read()
        except OSError:
            pass

th = threading.Thread(target=reader, daemon=True); th.start()
old_fail = 0
for i in range(2000):
    tmp = path + '.part'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(f'{i}\tline')
        os.replace(tmp, path)
    except OSError:
        old_fail += 1
p = E.Progress(path)
t = time.time(); new_fail = 0
import io, contextlib
for i in range(2000):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            p.say(f'line {i}', i % 100)
    except Exception:
        new_fail += 1
stop = True
out = (f'### Progress file under polling\n- old write (bare os.replace): {old_fail} of 2000 failed\n'
       f'- Progress.say: {new_fail} of 2000 raised ({time.time() - t:.1f} s)\n')
print(out)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8').write(out)
sys.exit(1 if new_fail else 0)
