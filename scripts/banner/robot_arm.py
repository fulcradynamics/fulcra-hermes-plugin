"""Replace Adam's (left) arm in hands.png with a rendered teal-metal robot arm in the same pose.
Each part is shaded per pixel (cylinders across their width, spheres by normal) with an environment
ramp, a specular highlight, brushed streaks and contact shadows. Coordinates are in hands.png's space."""
import numpy as np
from PIL import Image
from scipy import ndimage

SS = 4
rng = np.random.default_rng(7)
hands = Image.open('hands.png').convert('RGBA')
W, H = hands.size
src = np.asarray(hands)
lab, n = ndimage.label(src[..., 3] > 128)
left = min(range(1, n + 1), key=lambda i: np.where(lab == i)[1].mean())
keep = src.copy()
keep[ndimage.binary_dilation(lab == left, iterations=4)] = 0
keep[:, :395] = 0

HW, HH = W * SS, H * SS
yy, xx = np.mgrid[0:HH, 0:HW].astype(np.float32) / SS
col = np.zeros((HH, HW, 3), np.float32)
alpha = np.zeros((HH, HW), np.float32)

# Teal metal: an environment ramp (sky above, dark horizon, ground bounce) tinted to Fulcra teal.
STOPS = [(-1.0, (0.03, 0.12, 0.11)), (-0.82, (0.55, 0.92, 0.84)), (-0.62, (0.86, 1.0, 0.97)),
         (-0.45, (0.42, 0.84, 0.74)), (-0.1, (0.22, 0.58, 0.51)), (0.12, (0.05, 0.2, 0.18)),
         (0.38, (0.14, 0.42, 0.37)), (0.72, (0.30, 0.66, 0.58)), (0.9, (0.16, 0.40, 0.35)), (1.0, (0.03, 0.10, 0.09))]
SU = np.array([s[0] for s in STOPS], np.float32)
SC = np.array([s[1] for s in STOPS], np.float32)


def ramp(u):
    u = np.clip(u, -1, 1)
    return np.stack([np.interp(u, SU, SC[:, i]) for i in range(3)], -1)


def shadow(mask_fn, dx=1.6, dy=2.2, blur=2.5, strength=0.55):
    """Darken what's already drawn where this part will cast its shadow."""
    m = mask_fn(xx - dx, yy - dy).astype(np.float32)
    m = ndimage.gaussian_filter(m, blur * SS)
    col[:] *= (1 - strength * m)[..., None]


def put(mask, c):
    alpha[mask] = 1.0
    col[mask] = c[mask]


def capsule(a, b, r, light=1.0):
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    nx, ny = -vy, vx
    nl = np.hypot(nx, ny)
    if ny > 0:                                  # the across axis points up, so the lit side is on top
        nx, ny = -nx, -ny
    nx, ny = nx / nl, ny / nl

    def inside(x, y):
        t = np.clip(((x - ax) * vx + (y - ay) * vy) / L2, 0, 1)
        return np.hypot(x - (ax + t * vx), y - (ay + t * vy)) <= r

    shadow(inside)
    t = np.clip(((xx - ax) * vx + (yy - ay) * vy) / L2, 0, 1)
    px, py = ax + t * vx, ay + t * vy
    dist = np.hypot(xx - px, yy - py)
    m = dist <= r
    u = -((xx - px) * nx + (yy - py) * ny) / r
    c = ramp(u)
    along = ((xx - ax) * vx + (yy - ay) * vy) / np.sqrt(L2)
    streak = rng.normal(0, 1, 512).astype(np.float32)
    idx = ((u * 180 + 256) % 512).astype(int)
    c = c * (1 + 0.06 * streak[idx])[..., None] * (1 + 0.03 * np.sin(along * 0.9))[..., None]
    rim = np.clip(dist / r, 0, 1) ** 6
    c = c * (1 - 0.55 * rim[..., None]) * light
    put(m, c)


def sphere(cx, cy, r, light=1.0):
    def inside(x, y):
        return np.hypot(x - cx, y - cy) <= r
    shadow(inside, blur=1.8)
    dx, dy = (xx - cx) / r, (yy - cy) / r
    rr = dx * dx + dy * dy
    m = rr <= 1
    nz = np.sqrt(np.clip(1 - rr, 0, 1))
    c = ramp(dy * 0.95 - nz * 0.1)
    lx, ly, lz = -0.45, -0.6, 0.66
    spec = np.clip(dx * lx + dy * ly + nz * lz, 0, 1) ** 28
    c = c * (1 - 0.6 * np.clip(rr, 0, 1)[..., None] ** 3) * light + spec[..., None] * 0.9
    put(m, np.clip(c, 0, 1))


def plate(points, light=1.0):
    """A flat beveled plate with a vertical sheen and a darker bevel."""
    from matplotlib.path import Path
    p = Path(points)

    def inside(x, y):
        return p.contains_points(np.stack([x.ravel(), y.ravel()], -1)).reshape(x.shape)
    shadow(inside, blur=3)
    m = inside(xx, yy)
    ys = np.array([q[1] for q in points])
    top, bot = ys.min(), ys.max()
    u = (yy - top) / max(bot - top, 1) * 2 - 1
    c = ramp(u * 0.9 - 0.15) * light
    edge = ndimage.distance_transform_edt(m) / SS
    c = c * (0.55 + 0.45 * np.clip(edge / 2.5, 0, 1))[..., None]
    put(m, c)


# Forearm: two bones, a piston, a ribbed sleeve.
capsule((-25, 210), (196, 113), 7.5, 0.8)       # ulna (behind)
capsule((-25, 172), (192, 86), 8.5)             # radius
capsule((15, 185), (150, 120), 3.2)             # piston rod
capsule((15, 184), (92, 152), 6)                # piston sleeve
for i in range(4):
    x = 30 + i * 14
    capsule((x, 182 - i * 6.2 + 4), (x + 3, 182 - i * 6.2 - 7), 2.2, 0.9)
sphere(201, 99, 13)                             # wrist

# Hand: carpal plate and metacarpals, then the fingers (index reaching, others curled).
plate([(205, 82), (240, 69), (263, 82), (259, 113), (222, 119)])
knuckles = {'little': (285, 80), 'ring': (305, 85), 'middle': (322, 91), 'index': (338, 98)}
for k in knuckles.values():
    capsule((246, 92), k, 4)
fingers = {
    'little': [(285, 80), (292, 116), (300, 144), (305, 162)],
    'ring': [(305, 85), (318, 124), (328, 151), (337, 169)],
    'middle': [(322, 91), (338, 128), (348, 155), (356, 171)],
    'index': [(338, 98), (362, 117), (377, 131), (390, 143)],
}
for name in ('little', 'ring', 'middle', 'index'):
    pts = fingers[name]
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        capsule(a, b, (4.6, 4.0, 3.5)[i])
    for i, p in enumerate(pts[1:3]):
        sphere(*p, (6.2, 5.6)[i])                 # joints sit on top as knobs
    sphere(*pts[-1], 3.6)                         # rounded fingertip
for k in knuckles.values():
    sphere(*k, 7.5)
thumb = [(226, 110), (252, 132), (272, 145), (286, 152)]
for i, (a, b) in enumerate(zip(thumb, thumb[1:])):
    capsule(a, b, (5.2, 4.6, 4.0)[i])
for i, p in enumerate(thumb[:3]):
    sphere(*p, (7.5, 6.4, 5.8)[i])
sphere(*thumb[-1], 4.0)

rgba = np.dstack([np.clip(col, 0, 1) * 255, alpha * 255]).astype(np.uint8)
arm = Image.fromarray(rgba, 'RGBA').resize((W, H), Image.LANCZOS)
a = np.asarray(arm).astype(float)
a[..., 3] *= np.clip((np.arange(W) - 8) / 80, 0, 1)[None, :]
out = Image.fromarray(keep)
out.alpha_composite(Image.fromarray(a.astype('uint8'), 'RGBA'))
out.save('hands-robot.png')
print('ok')
