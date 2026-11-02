import asyncio, json, sys, time, threading, http.server, functools, socketserver, math, io
from playwright.async_api import async_playwright
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
WEB = '/home/claude/dl/asar_x/drawio/src/main/webapp'
def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=WEB)
    h.log_message = lambda *a: None
    s = socketserver.ThreadingTCPServer(('127.0.0.1', 0), h); s.daemon_threads = True
    threading.Thread(target=s.serve_forever, daemon=True).start(); return s.server_address[1]
async def one(ctx, port, xml, scale, out, dpr):
    t = time.time(); pg = await ctx.new_page()
    await pg.goto(f'http://127.0.0.1:{port}/export3.html', wait_until='networkidle')
    await pg.evaluate('d => render(d)', {'xml': xml, 'format': 'png', 'scale': scale, 'border': 0, 'bg': 'none', 'from':0,'to':0})
    el = await pg.wait_for_selector('#LoadingComplete', state='attached', timeout=60000)
    b = json.loads(await el.get_attribute('bounds'))
    W, H = math.ceil(b['width'] + b['x']) + 1, math.ceil(b['height'] + b['y']) + 1   # as electron.js
    await pg.set_viewport_size({'width': W, 'height': H})
    png = await pg.screenshot(omit_background=True)
    im = Image.open(io.BytesIO(png))
    if im.size != (W, H): im = im.resize((W, H), Image.LANCZOS)
    im.save(out); await pg.close()
    return time.time() - t, (W, H)
async def main():
    port = serve(); dpr = float(sys.argv[1]); jobs = sys.argv[2:]
    async with async_playwright() as p:
        br = await p.chromium.launch(args=['--disable-gpu'])
        ctx = await br.new_context(device_scale_factor=dpr)
        for j in jobs:
            src, out = j.split(':')
            dt, sz = await one(ctx, port, open(src, encoding='utf-8').read(), 5, out, dpr)
            print(f'{src}: {dt:.2f}s {sz}')
        await br.close()
asyncio.run(main())
