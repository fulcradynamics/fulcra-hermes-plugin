"""assets/banner.png: the Fulcra logo, two reaching arms in Fulcra teal, and a caption, on a transparent 1200x600.

Run from a work directory by ./make.sh, which explains the steps. `compose.py hands` recolors the fresco's
hands into hands.png; robot_arm.py replaces Adam's arm; `compose.py banner LOGO FONT` lays out banner.png."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TEAL = np.array([0x56, 0xD6, 0xB7]) / 255
DARK = np.array([0x0E, 0x3B, 0x33]) / 255
LIGHT = np.array([0xE6, 0xF9, 0xF1]) / 255

src = Image.open('adam.jpg').convert('RGB')
crop = src.crop((940, 590, 1690, 845))
arr = np.asarray(crop).astype(float) / 255
r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
mx, mn = arr.max(-1), arr.min(-1)
sat = (mx - mn) / (mx + 1e-6)
m = np.clip((r - b - 0.10) / 0.12, 0, 1) * np.clip((sat - 0.18) / 0.12, 0, 1)
from scipy import ndimage
solid = ndimage.binary_closing(m > 0.35, structure=np.ones((9, 9)))
solid = ndimage.binary_fill_holes(solid)
solid = ndimage.binary_opening(solid, structure=np.ones((5, 5)))
lab, n = ndimage.label(solid)
sizes = ndimage.sum(solid, lab, range(1, n + 1))
keep = 1 + np.argsort(sizes)[-2:]          # the two arms
solid = np.isin(lab, keep)
h, w = solid.shape
fade = np.ones((h, w))
ramp = 90
x = np.arange(w)
fade *= np.clip(np.minimum(x, w - 1 - x) / ramp, 0, 1)[None, :]  # arms fade out at the image edges
y = np.arange(h)
fade *= np.clip((h - 1 - y) / 40, 0, 1)[:, None]
mask = Image.fromarray((solid * fade * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(1.0))

# Statue look: luminance, contrast-stretched within the arms, mapped dark teal -> teal -> pale.
lum = 0.3 * r + 0.59 * g + 0.11 * b
sel = np.asarray(mask) > 128
lo, hi = np.percentile(lum[sel], 3), np.percentile(lum[sel], 97)
t = np.clip((lum - lo) / (hi - lo), 0, 1)[..., None] ** 0.75  # lifts the highlights
K = 0.5
col = np.where(t < K, DARK + (TEAL - DARK) * (t / K), TEAL + (LIGHT - TEAL) * ((t - K) / (1 - K)))
rgba = np.dstack([(col * 255).astype('uint8'), np.asarray(mask)])
hands = Image.fromarray(rgba, 'RGBA')
if sys.argv[1] == 'hands':
    hands.save('hands.png')
    sys.exit()
hands = Image.open('hands-robot.png').convert('RGBA')

W, H = 1200, 600
out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
logo = Image.open(sys.argv[2]).convert('RGBA')
logo = logo.crop(logo.getbbox())
lh = 250
logo = logo.resize((round(logo.width * lh / logo.height), lh), Image.LANCZOS)
hw = 820
hands = hands.resize((hw, round(hands.height * hw / hands.width)), Image.LANCZOS)
gap = 50
x0 = (W - (logo.width + gap + hands.width)) // 2
band_top = 130
out.alpha_composite(logo, (x0, band_top))
out.alpha_composite(hands, (x0 + logo.width + gap, band_top + (lh - hands.height) // 2))

font_path = sys.argv[3] if len(sys.argv) > 3 else None
font = ImageFont.truetype(font_path, 64) if font_path else ImageFont.load_default(64)
d = ImageDraw.Draw(out)
text = 'Fulcra agent messaging'
w = d.textlength(text, font=font)
d.text(((W - w) / 2, band_top + lh + 45), text, font=font, fill=(0x56, 0xD6, 0xB7, 255))
out.save('banner.png', optimize=True)

prev = Image.new('RGB', (W, 2 * H))
for i, c in enumerate([(250, 250, 250), (28, 28, 32)]):
    bg = Image.new('RGBA', (W, H), c + (255,)); bg.alpha_composite(out); prev.paste(bg.convert('RGB'), (0, H * i))
prev.save('preview.png')  # on light and dark, to check by eye
