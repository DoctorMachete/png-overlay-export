"""Compare draw.io's own PNG with the exe's (same page, same scale): size, alpha, pixels;
write a side-by-side image and a job summary."""
import os, sys, numpy as np
from PIL import Image
a = np.asarray(Image.open(sys.argv[1]).convert('RGBA')).astype(int)
b = np.asarray(Image.open(sys.argv[2]).convert('RGBA')).astype(int)
md = ['### draw.io CLI vs the exe (Edge over CDP)', f'- draw.io: {a.shape[1]} x {a.shape[0]}, exe: {b.shape[1]} x {b.shape[0]}']
if a.shape == b.shape:
    d = np.abs(a - b).max(-1)
    md.append(f'- pixels > 8 levels apart: {(d > 8).mean() * 100:.2f} %, > 32: {(d > 32).mean() * 100:.2f} %, '
              f'mean {np.abs(a - b).mean():.2f}; alpha > 8 apart: {(np.abs(a[..., 3] - b[..., 3]) > 8).mean() * 100:.2f} %')
    h, w = a.shape[:2]
    bg = np.full((h, w, 3), 255)
    flat = lambda x: (x[..., :3] * x[..., 3:4] / 255 + bg * (1 - x[..., 3:4] / 255)).astype(np.uint8)
    diff = np.repeat(np.clip(d * 3, 0, 255)[..., None], 3, -1).astype(np.uint8)
    Image.fromarray(np.concatenate([flat(a), flat(b), 255 - diff], 0)).save(sys.argv[3])
else:
    md.append('- **sizes differ**')
out = '\n'.join(md) + '\n'
print(out)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8').write(out)
