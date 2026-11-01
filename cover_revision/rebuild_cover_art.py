from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).parent
source_art = Path(r'C:\Users\ammar\Documents\Codex\2026-10-09\ri\outputs\CLEON_assets\cleon_cover_background.jpg')
base = Image.open(source_art).convert('RGB').resize((1224, 1584), Image.Resampling.LANCZOS)
old = np.asarray(Image.open(ROOT / 'cover-idml-01.png').convert('RGB'))
arr = np.asarray(base).copy()
r, g, b = old[..., 0], old[..., 1], old[..., 2]
white_core = (r[900:1040, 300:950] > 232) & (g[900:1040, 300:950] > 232) & (b[900:1040, 300:950] > 232)
red_core = (r[1025:1185, 400:1010] > 185) & (g[1025:1185, 400:1010] < 80) & (b[1025:1185, 400:1010] < 100)
mask = np.zeros((1584, 1224), dtype=np.uint8)
mask[900:1040, 300:950] = white_core.astype(np.uint8) * 255
mask[1025:1185, 400:1010] = np.maximum(mask[1025:1185, 400:1010], red_core.astype(np.uint8) * 255)
mask = np.asarray(Image.fromarray(mask).filter(ImageFilter.MaxFilter(3)))
selection = mask > 0
arr[selection] = old[selection]
Image.fromarray(arr).save(ROOT / 'cover-art-restored-preview.png')
Image.fromarray(mask).save(ROOT / 'cover-wordmark-mask.png')
