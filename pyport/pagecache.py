"""v0.2.34 (.200): the page cache - draw.io's PNG of a page kept by the page's content, so an
unchanged page is never drawn again.

The key is a SHA-256 of everything that decides what draw.io returns:
  - the page XML exactly as sent (every source / INI / layout change that alters a page alters it),
  - the export scale, transparency and border,
  - the environment: the app.asar (path, size, date), the browser exe (path, size, date) and the
    installed fonts (names, sizes, dates in the Windows and per-user font folders),
  - CACHE_VER, bumped whenever the engine changes how it screenshots or shrinks a page.
Only draw.io's raw output is kept; everything after it (Render shading, AO, Legend 3D, shadows,
composing) always runs.  A page with a picture that isn't embedded (image=http..., file:...) is
never cached: the picture can change without the XML changing.

Files: %LOCALAPPDATA%\\png-overlay-export\\page-cache\\<2 hex>\\<sha>.png; a hit touches the file,
prune() deletes the least recently used ones above the size cap ([export] PageCacheMB, default
1000).  [export] PageCache=0 switches it off; `export --clear-page-cache` empties it first.
"""
import glob, hashlib, os, re, shutil, tempfile, uuid

CACHE_VER = 1
_LINKED = re.compile(r'(?:^|[;"\s])image=(?!data:)[^;"&\s]')


def cache_dir():
    root = os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()
    return os.path.join(root, 'png-overlay-export', 'page-cache')


def _stat_tag(path):
    try:
        st = os.stat(path)
        return f'{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}'
    except OSError:
        return f'{path}|missing'


def _fonts_tag():
    """The installed fonts, as names / sizes / dates (Windows and per-user font folders)."""
    dirs = [os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')]
    la = os.environ.get('LOCALAPPDATA')
    if la:
        dirs.append(os.path.join(la, 'Microsoft', 'Windows', 'Fonts'))
    h = hashlib.sha256()
    for d in dirs:
        try:
            for e in sorted(os.scandir(d), key=lambda e: e.name.lower()):
                try:
                    st = e.stat()
                    h.update(f'{e.name.lower()}|{st.st_size}|{int(st.st_mtime)}\n'.encode())
                except OSError:
                    pass
        except OSError:
            pass
    return h.hexdigest()


def env_tag(drawio):
    """The environment part of every key (computed once per process)."""
    import drawio_helper as DH
    asar = drawio
    if os.path.isdir(drawio):
        asar = os.path.join(drawio, 'resources', 'app.asar')
        if not os.path.exists(asar):
            asar = os.path.join(drawio, 'app.asar')
    try:
        browser = DH.find_browser()
    except Exception:                                    # noqa: BLE001 - no browser: the render fails anyway
        browser = ''
    return f'v{CACHE_VER}|{_stat_tag(asar)}|{_stat_tag(browser)}|{_fonts_tag()}'


def cacheable(xml):
    return _LINKED.search(xml) is None


def key(xml, scale, transparent, env, border=0):
    h = hashlib.sha256()
    h.update(f'{env}|{scale}|{int(bool(transparent))}|{border}\n'.encode())
    h.update(xml.encode('utf-8'))
    return h.hexdigest()


def _path(k):
    return os.path.join(cache_dir(), k[:2], k + '.png')


def get(k, out_png):
    """Copy the cached PNG to out_png; True on a hit."""
    p = _path(k)
    try:
        with open(p, 'rb') as f:
            data = f.read()
    except OSError:
        return False
    if not data.startswith(b'\x89PNG'):
        return False
    tmp = out_png + '.part'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, out_png)
    try:
        os.utime(p)                                      # recently used: kept longest by prune()
    except OSError:
        pass
    return True


def put(k, png):
    p = _path(k)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = f'{p}.{uuid.uuid4().hex}.part'             # workers may store the same page at once
        with open(tmp, 'wb') as f:
            f.write(png)
        os.replace(tmp, p)
    except OSError:
        pass


def clear():
    """Empty the cache; the number of pages removed."""
    d = cache_dir()
    n = len(glob.glob(os.path.join(d, '*', '*.png')))
    shutil.rmtree(d, ignore_errors=True)
    return n


def prune(max_mb):
    """Least recently used pages deleted until the cache is within max_mb; (pages, MB) left."""
    files = []
    for p in glob.glob(os.path.join(cache_dir(), '*', '*')):
        try:
            st = os.stat(p)
        except OSError:
            continue
        if p.endswith('.part'):                          # a store cut short
            try:
                os.remove(p)
            except OSError:
                pass
            continue
        files.append((st.st_mtime, st.st_size, p))
    total, cap = sum(f[1] for f in files), max(0, max_mb) * 1024 * 1024
    for mt, sz, p in sorted(files):
        if total <= cap:
            break
        try:
            os.remove(p)
            total -= sz
        except OSError:
            pass
    left = sum(1 for f in files if os.path.exists(f[2]))
    return left, total / 1024 / 1024
