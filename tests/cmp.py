import sys, numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
a = np.asarray(Image.open(sys.argv[1]).convert('RGBA')).astype(int)
b = np.asarray(Image.open(sys.argv[2]).convert('RGBA')).astype(int)
print(sys.argv[2], 'size', a.shape[:2], b.shape[:2], end=' ')
if a.shape != b.shape: print('SIZE DIFFERS'); sys.exit()
d = np.abs(a - b); mx = d.max(axis=2)
print(f'| alpha max diff {d[...,3].max()}, pixels differing >8: {(mx>8).mean()*100:.3f}%, >32: {(mx>32).mean()*100:.3f}%, mean {d.mean():.3f}')
