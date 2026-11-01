from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).parent
image = np.asarray(Image.open(ROOT / 'extracted0.png').convert('RGB')).astype(np.float32)
red, green, blue = image[..., 0], image[..., 1], image[..., 2]
mask = np.zeros(image.shape[:2], dtype=bool)

# The cover artwork has the old Mission copy at the top and Model copy at the
# bottom. Select only the high-contrast glyph pixels within their text bands.
bands = ((75, 285, 175, 1145), (1360, 1545, 175, 1110))
for y0, y1, x0, x1 in bands:
    r, g, b = red[y0:y1, x0:x1], green[y0:y1, x0:x1], blue[y0:y1, x0:x1]
    bright_text = (r > 200) & (g > 190) & (b > 190) & ((np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)) < 55)
    red_text = (r > 180) & (g < 100) & (b < 110) & ((r - g) > 110)
    local = bright_text | red_text
    mask[y0:y1, x0:x1] |= local

# Expand slightly to catch antialiased letter edges without masking broad art.
mask_image = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(9))
mask = np.asarray(mask_image) > 0

# Diffuse neighboring artwork into masked glyph pixels in a short expanded crop.
# Limiting work to the top/bottom text bands keeps the retouch localized and fast.
work = image.copy()
for y0, y1, x0, x1 in bands:
    local_mask = mask[y0:y1, x0:x1]
    ys, xs = np.where(local_mask)
    if not len(xs):
        continue
    pad = 8
    ya, yb = max(0, ys.min() - pad), min(y1-y0, ys.max() + pad + 1)
    xa, xb = max(0, xs.min() - pad), min(x1-x0, xs.max() + pad + 1)
    region = work[y0+ya:y0+yb, x0+xa:x0+xb].copy()
    region_mask = local_mask[ya:yb, xa:xb].copy()
    known = ~region_mask
    for _ in range(35):
        sums = np.zeros_like(region)
        counts = np.zeros(region_mask.shape, dtype=np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            shifted = np.roll(np.roll(region, dy, axis=0), dx, axis=1)
            valid = np.roll(np.roll(known, dy, axis=0), dx, axis=1)
            sums += shifted * valid[..., None]
            counts += valid
        update = region_mask & (counts > 0)
        region[update] = sums[update] / counts[update, None]
        known[update] = True
    target = work[y0+ya:y0+yb, x0+xa:x0+xb]
    target[region_mask] = region[region_mask]

Image.fromarray(np.uint8(np.clip(work, 0, 255))).save(ROOT / 'cover-art-clean-v3.png')
Image.fromarray(np.uint8(mask) * 255).save(ROOT / 'cover-text-mask-v3.png')


