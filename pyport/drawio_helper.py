"""draw.io page renderer: draw.io's own drawing code (export3.html from the
user's app.asar) in a headless Edge/Chromium kept open, driven over the Chrome
DevTools Protocol.  Replaces `draw.io.exe -x -f png [-t] -s <scale>` without a
cold start per image.

Matches draw.io desktop's PNG export (src/main/electron.js, exportDiagram):
page rendered at device scale 2, image ceil(bounds.width + bounds.x) + 1 by
ceil(bounds.height + bounds.y) + 1, shrunk back to that size; transparent
background with -t.  (Desktop also waits a fixed 1 s before capturing; here
the page's own #LoadingComplete, set after fonts and images load, is enough.)

Usage:
  drawio_helper.py render --drawio <draw.io folder | app.asar> [--browser exe]
                          [-s 5] [-t] in.drawio out.png [in2 out2 ...]
  drawio_helper.py serve  --drawio <...> [--port 0] [--idle 600]
      GET /health  -> 200 "ok"
      POST /export {"in":..., "out":..., "scale":5, "transparent":true} -> 200 / 500 text
      GET /quit
"""
import argparse, base64, glob, functools, hashlib, http.server, io, json, math, os, socket, \
    socketserver, struct, subprocess, sys, tempfile, threading, time, shutil
from urllib.parse import urlparse

# ----------------------------------------------------------------- app.asar
def asar_extract(asar, out_dir, prefix='drawio/src/main/webapp/'):
    """Unpack the webapp folder of draw.io's app.asar (16-byte header, JSON index)."""
    with open(asar, 'rb') as f:
        _, hsize, _, jlen = struct.unpack('<4I', f.read(16))
        index = json.loads(f.read(jlen).decode('utf-8'))
        base = 8 + hsize
        def walk(node, path=''):
            for name, ch in node.get('files', {}).items():
                p = f'{path}/{name}' if path else name
                if 'files' in ch:
                    yield from walk(ch, p)
                else:
                    yield p, ch
        n = 0
        for p, ch in walk(index):
            if not p.startswith(prefix) or ch.get('unpacked') or 'link' in ch:
                continue
            dst = os.path.join(out_dir, p[len(prefix):])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            f.seek(base + int(ch['offset']))
            with open(dst, 'wb') as o:
                o.write(f.read(ch['size']))
            n += 1
    return n

def webapp_dir(drawio):
    """The extracted webapp for this app.asar, cached by its size and date."""
    asar = drawio
    if os.path.isdir(drawio):
        asar = os.path.join(drawio, 'resources', 'app.asar')
        if not os.path.exists(asar):
            asar = os.path.join(drawio, 'app.asar')
    st = os.stat(asar)
    tag = hashlib.sha1(f'{os.path.abspath(asar)}|{st.st_size}|{int(st.st_mtime)}'.encode()).hexdigest()[:12]
    root = os.environ.get('LOCALAPPDATA') or os.path.join(tempfile.gettempdir())
    d = os.path.join(root, 'png-overlay-export', 'webapp-' + tag)
    if not os.path.exists(os.path.join(d, 'export3.html')):
        tmp = d + '.part'
        shutil.rmtree(tmp, ignore_errors=True)
        asar_extract(asar, tmp)
        shutil.rmtree(d, ignore_errors=True)
        os.replace(tmp, d)
    return d

class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

def serve_dir(d):
    h = functools.partial(_Quiet, directory=d)
    class _Server(socketserver.ThreadingTCPServer):
        request_queue_size = 128          # Edge opens many connections at once (two tabs loading);
                                          # the default backlog of 5 can drop some, which then stall
        daemon_threads = True
    s = _Server(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, s.server_address[1]

# ------------------------------------------------- a minimal websocket client
class WS:
    """RFC 6455 client: enough for CDP (text frames, masked, no extensions)."""
    def __init__(self, url):
        u = urlparse(url)
        self.s = socket.create_connection((u.hostname, u.port), timeout=30)   # no message from Edge for 30 s = stuck
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f'GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n'
                        f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                        f'Sec-WebSocket-Version: 13\r\n\r\n').encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            c = self.s.recv(4096)
            if not c:
                raise ConnectionError('websocket handshake failed')
            buf += c
        head, self.rest = buf.split(b'\r\n\r\n', 1)
        if b' 101 ' not in head.split(b'\r\n')[0]:
            raise ConnectionError(head.decode(errors='replace'))

    def _read(self, n):
        while len(self.rest) < n:
            c = self.s.recv(1 << 20)
            if not c:
                raise ConnectionError('websocket closed')
            self.rest += c
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def send(self, text):
        data = text.encode()
        n = len(data)
        hdr = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else
              bytes([0x80 | 126]) + struct.pack('>H', n) if n < 65536 else
              bytes([0x80 | 127]) + struct.pack('>Q', n))
        mask = os.urandom(4)
        body = bytes(b ^ mask[i & 3] for i, b in enumerate(data)) if n < 4096 else \
            (int.from_bytes(data, 'big') ^ int.from_bytes((mask * (n // 4 + 1))[:n], 'big')).to_bytes(n, 'big')
        self.s.sendall(hdr + mask + body)

    def recv(self):
        msg = b''
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7f
            if n == 126:
                n = struct.unpack('>H', self._read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._read(8))[0]
            if b1 & 0x80:
                self._read(4)                         # servers don't mask; skip if they do
            data = self._read(n)
            op = b0 & 0x0f
            if op == 8:
                raise ConnectionError('websocket closed by browser')
            if op in (9, 10):                         # ping / pong
                continue
            msg += data
            if b0 & 0x80:
                return msg.decode('utf-8')

class CDP:
    def __init__(self, ws_url):
        self.ws = WS(ws_url)
        self.n = 0
        self.events = []

    def call(self, method, params=None, session=None, timeout=120):
        self.n += 1
        mid = self.n
        m = {'id': mid, 'method': method, 'params': params or {}}
        if session:
            m['sessionId'] = session
        self.ws.send(json.dumps(m))
        t_end = time.time() + timeout
        while time.time() < t_end:
            r = json.loads(self.ws.recv())
            if r.get('id') == mid:
                if 'error' in r:
                    raise RuntimeError(f'{method}: {r["error"]}')
                return r.get('result', {})
            self.events.append(r)
        raise TimeoutError(method)

    def wait_event(self, name, session=None, timeout=60):
        t_end = time.time() + timeout
        while True:
            for i, e in enumerate(self.events):
                if e.get('method') == name and (session is None or e.get('sessionId') == session):
                    return self.events.pop(i)
            if time.time() > t_end:
                raise TimeoutError(name)
            self.events.append(json.loads(self.ws.recv()))

# --------------------------------------------------------------- the browser
def find_browser(given=None):
    if given:
        return given
    cands = []
    for env in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
        b = os.environ.get(env)
        if b:
            cands += [os.path.join(b, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                      os.path.join(b, 'Google', 'Chrome', 'Application', 'chrome.exe')]
    cands += [shutil.which(n) for n in ('msedge', 'microsoft-edge', 'google-chrome', 'chromium', 'chromium-browser')]
    pw = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/opt/pw-browsers')
    if os.path.isdir(pw):
        for d in sorted(os.listdir(pw), reverse=True):
            cands.append(os.path.join(pw, d, 'chrome-linux64', 'chrome'))
    for c in cands:
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError('No Edge or Chrome found; pass --browser')

def _shrink(im, W, H):
    """The 2x screenshot down to W x H as an area average on premultiplied pixels (a plain 2 x 2
    mean).  Lanczos rang past every edge: faint alpha one AlphaBox step outside the artwork,
    so the shared box grew by 4 px; this gives draw.io's own box."""
    import numpy as np, cv2
    from PIL import Image
    f = np.asarray(im).astype(np.float32) / 255
    f[..., :3] *= f[..., 3:4]
    f = cv2.resize(f, (W, H), interpolation=cv2.INTER_AREA)
    a = f[..., 3:4]
    c = np.where(a > 1e-6, f[..., :3] / np.maximum(a, 1e-6), 0)
    return Image.fromarray(np.clip(np.concatenate([c, a], -1) * 255 + 0.5, 0, 255).astype(np.uint8), 'RGBA')


class Renderer:
    def __init__(self, drawio, browser=None):
        self.web = webapp_dir(drawio)
        self.http, self.port = serve_dir(self.web)
        # profiles left by runs that were killed (older than 6 h): cleared
        try:
            for d in glob.glob(os.path.join(tempfile.gettempdir(), 'poe-edge-*')):
                if time.time() - os.path.getmtime(d) > 6 * 3600:
                    shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass
        self.profile = tempfile.mkdtemp(prefix='poe-edge-')
        exe = find_browser(browser)
        # The anti-throttling measures, each switchable for ci/helper_variants.ps1 (POE_<name>=0/1).
        # On Windows (CI): WAKE (lifecycle 'active' + focus emulation) without FRONT stops the
        # screenshot coming at all, and with it is slower: off.  FLAGS and FRONT work: on.
        dflt = {'FLAGS': '1', 'WAKE': '0', 'FRONT': '1'}
        self.opt = {k: os.environ.get('POE_' + k, d) != '0' for k, d in dflt.items()}
        args = [exe, '--headless=new', '--remote-debugging-port=0', f'--user-data-dir={self.profile}',
                '--no-first-run', '--no-default-browser-check', '--disable-extensions',
                '--hide-scrollbars', '--mute-audio', '--disable-gpu', '--force-color-profile=srgb',
                '--disable-background-networking', '--disable-renderer-backgrounding']
        if self.opt['FLAGS']:
            args += [
                # never throttle, freeze or sleep a tab: the two tabs take turns, so one is always
                # "in the background" (one page in a hundred hung for 120 s on the user's PC)
                '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows',
                '--disable-features=msSleepingTabs,IntensiveWakeUpThrottling,CalculateNativeWinOcclusion',
                '--disable-ipc-flooding-protection', '--disable-hang-monitor', '--noerrdialogs',
                '--disable-component-update', '--disable-sync', '--disable-default-apps']
        args.append('about:blank')
        if sys.platform != 'win32':
            args.insert(1, '--no-sandbox')
        # CREATE_NO_WINDOW, and below normal priority: the user's own work comes first
        flags = (0x08000000 | 0x00004000) if sys.platform == 'win32' else 0
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        port_file = os.path.join(self.profile, 'DevToolsActivePort')
        t_end = time.time() + 30
        found = None
        while found is None:
            try:
                parts = open(port_file).read().split() if os.path.exists(port_file) else []
                if len(parts) >= 2:
                    found = parts[:2]
                    break
            except OSError:                              # Windows: Edge is still writing it
                pass
            if time.time() > t_end or self.proc.poll() is not None:
                raise RuntimeError('the browser did not start: ' + exe)
            time.sleep(0.05)
        port, path = found
        self.cdp = CDP(f'ws://127.0.0.1:{port}{path}')
        self.url = f'http://127.0.0.1:{self.port}/export3.html'
        # two tabs take turns: one renders while the other loads a fresh page
        # (export3.html keeps state between renders, so each render needs a reload)
        self.tabs, self.loading, self.turn = [], {}, 0
        for _ in range(2):
            tid = self.cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
            sid = self.cdp.call('Target.attachToTarget', {'targetId': tid, 'flatten': True})['sessionId']
            self.cdp.call('Page.enable', session=sid)
            self._wake(sid)
            self.tabs.append(sid)
            self.sid = sid
            self._load()

    def _wake(self, sid):
        """The tab as if in front and focused, never frozen."""
        if not self.opt['WAKE']:
            return
        for m, prm in (('Page.setWebLifecycleState', {'state': 'active'}),
                       ('Emulation.setFocusEmulationEnabled', {'enabled': True})):
            try:
                self.cdp.call(m, prm, session=sid, timeout=10)
            except Exception:                            # noqa: BLE001 - an older browser
                pass

    def _load(self):
        """Start loading a fresh export3.html (one render() each); not waited for
        here, so it loads while the caller works on the last image."""
        self.cdp.call('Emulation.clearDeviceMetricsOverride', session=self.sid)
        self.cdp.events = [e for e in self.cdp.events
                           if not (e.get('method') == 'Page.loadEventFired' and e.get('sessionId') == self.sid)]
        self.cdp.call('Page.navigate', {'url': self.url}, session=self.sid)
        self.loading[self.sid] = True

    def eval(self, expr):
        r = self.cdp.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True,
                                               'awaitPromise': True}, session=self.sid)
        if 'exceptionDetails' in r:
            raise RuntimeError(r['exceptionDetails'].get('text', 'script error') + ' ' +
                               json.dumps(r['exceptionDetails'].get('exception', {}).get('description', ''))[:300])
        return r['result'].get('value')

    def render(self, xml, scale=1, transparent=True, border=0):
        """PNG bytes of the page, as draw.io desktop's -x -f png [-t] -s scale."""
        from PIL import Image
        self.sid = self.tabs[self.turn]
        self.turn = (self.turn + 1) % len(self.tabs)
        stage = 'start'
        try:
            stage = 'waking the tab'
            self._wake(self.sid)
            if self.loading.get(self.sid):
                stage = 'loading export3.html'
                self.cdp.wait_event('Page.loadEventFired', self.sid, timeout=20)
                self.loading[self.sid] = False
            # wait for the shapes: export.js renders at once when shapesLoaded
            stage = "waiting for draw.io's render()"
            self.eval("new Promise((r, j) => { const t0 = Date.now(); const t = () => (typeof render == 'function')"
                      " ? r(1) : (Date.now() - t0 > 20000) ? j('no render() after 20 s') : setTimeout(t, 10); t(); })")
            data = {'xml': xml, 'format': 'png', 'scale': scale, 'border': border,
                    'bg': 'none' if transparent else '#ffffff', 'w': 0, 'h': 0, 'from': 0, 'to': 0}
            stage = 'render()'
            self.eval(f'render({json.dumps(data)}); 1')
            stage = 'waiting for #LoadingComplete'
            b = self.eval("new Promise((r, j) => { const t0 = Date.now(); const t = () => {"
                          " const e = document.getElementById('LoadingComplete');"
                          " if (e) r(e.getAttribute('bounds')); else if (Date.now() - t0 > 25000) j('no LoadingComplete after 25 s');"
                          " else setTimeout(t, 10); }; t(); })")
        except Exception as e:
            raise RuntimeError(f'{stage}: {type(e).__name__}: {e}') from e
        bounds = json.loads(b)
        if bounds is None or bounds['width'] < 5 or bounds['height'] < 5:
            raise RuntimeError('draw.io rendered an empty page')
        W = math.ceil(bounds['width'] + bounds['x']) + 1
        H = math.ceil(bounds['height'] + bounds['y']) + 1
        self.cdp.call('Emulation.setDeviceMetricsOverride',
                      {'width': W, 'height': H, 'deviceScaleFactor': 2, 'mobile': False}, session=self.sid)
        if transparent:
            self.cdp.call('Emulation.setDefaultBackgroundColorOverride',
                          {'color': {'r': 0, 'g': 0, 'b': 0, 'a': 0}}, session=self.sid)
        try:
            if self.opt['FRONT']:
                # the tab that is drawn is brought to the front: a background tab may not be
                # painted, and its screenshot then never comes
                self.cdp.call('Page.bringToFront', session=self.sid, timeout=20)
            shot = self.cdp.call('Page.captureScreenshot', {'format': 'png', 'optimizeForSpeed': True},
                                 session=self.sid)
        except Exception as e:
            raise RuntimeError(f'screenshot: {type(e).__name__}: {e}') from e
        im = Image.open(io.BytesIO(base64.b64decode(shot['data'])))
        im.load()
        if im.size != (W, H):
            im = _shrink(im.convert('RGBA'), W, H)
        out = io.BytesIO()
        im.save(out, 'PNG', compress_level=1)
        self._load()                     # the next page loads while the caller works on this one
        return out.getvalue()

    def export(self, src, dst, scale=1, transparent=True):
        with open(src, encoding='utf-8') as f:
            xml = f.read()
        png = self.render(xml, scale, transparent)
        tmp = dst + '.part'
        with open(tmp, 'wb') as f:
            f.write(png)
        os.replace(tmp, dst)

    def close(self):
        try:
            self.cdp.call('Browser.close', timeout=5)
        except Exception:
            pass
        try:
            self.proc.wait(5)
        except Exception:
            self.proc.kill()
        self.http.shutdown()
        shutil.rmtree(self.profile, ignore_errors=True)

# ------------------------------------------------------------------- serve
def serve(r, port, idle):
    lock = threading.Lock()
    last = [time.time()]

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, text):
            b = text.encode()
            self.send_response(code)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            last[0] = time.time()
            if self.path == '/health':
                self.reply(200, 'ok')
            elif self.path == '/quit':
                self.reply(200, 'bye')
                threading.Thread(target=srv.shutdown, daemon=True).start()
            else:
                self.reply(404, 'unknown')

        def do_POST(self):
            last[0] = time.time()
            if self.path != '/export':
                return self.reply(404, 'unknown')
            try:
                job = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
                t0 = time.time()
                with lock:
                    r.export(job['in'], job['out'], float(job.get('scale', 1)), bool(job.get('transparent', True)))
                self.reply(200, f'ok {time.time() - t0:.2f}s')
            except Exception as e:
                self.reply(500, f'{type(e).__name__}: {e}')

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'listening on 127.0.0.1:{srv.server_address[1]}', flush=True)

    def watchdog():
        while True:
            time.sleep(5)
            if time.time() - last[0] > idle:
                srv.shutdown()
                return
    threading.Thread(target=watchdog, daemon=True).start()
    srv.serve_forever()

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['render', 'serve'])
    ap.add_argument('--drawio', required=True, help='draw.io folder (with resources\\app.asar) or app.asar')
    ap.add_argument('--browser')
    ap.add_argument('-s', '--scale', type=float, default=1)
    ap.add_argument('-t', '--transparent', action='store_true')
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--idle', type=float, default=600)
    ap.add_argument('files', nargs='*')
    a = ap.parse_args(argv)
    t0 = time.time()
    r = Renderer(a.drawio, a.browser)
    print(f'ready in {time.time() - t0:.2f}s', flush=True)
    try:
        if a.cmd == 'render':
            for src, dst in zip(a.files[::2], a.files[1::2]):
                t = time.time()
                r.export(src, dst, a.scale, a.transparent)
                print(f'{dst}: {time.time() - t:.2f}s', flush=True)
        else:
            serve(r, a.port, a.idle)
    finally:
        r.close()

if __name__ == '__main__':
    main()
