"""
Procedural, tileable PBR texture generator (placeholder for Gemini-generated maps).

Every material gets three maps:
  T_<Name>_BaseColor.png  (sRGB)
  T_<Name>_Normal.png     (OpenGL / +Y up, Non-Color)
  T_<Name>_ORM.png        (R=AO, G=Roughness, B=Metallic, Non-Color)

All tiling textures repeat seamlessly and cover exactly one grid unit
(GRID = 1 m) unless stated otherwise in MATERIALS[...]["tile_m"].
"""
import os
import numpy as np
from PIL import Image

RNG_SEED = 7


# ----------------------------------------------------------------------------- helpers
def rng(seed):
    return np.random.default_rng(RNG_SEED * 1000 + seed)


def pnoise(size, freq, seed, aniso=(1.0, 1.0)):
    """Periodic (tileable) band-limited noise in [0,1]. freq ~ features per tile."""
    h, w = size
    r = rng(seed)
    white = r.standard_normal((h, w))
    fy = np.fft.fftfreq(h) * h / aniso[1]
    fx = np.fft.fftfreq(w) * w / aniso[0]
    f = np.sqrt(fy[:, None] ** 2 + fx[None, :] ** 2)
    F = np.fft.fft2(white) * np.exp(-(f / max(freq, 1e-3)) ** 2)
    n = np.real(np.fft.ifft2(F))
    n -= n.min()
    n /= max(n.max(), 1e-8)
    return n


def fbm(size, base_freq, seed, octaves=4, aniso=(1.0, 1.0)):
    acc = np.zeros(size)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        acc += pnoise(size, base_freq * 2 ** o, seed + o * 17, aniso) * amp
        tot += amp
        amp *= 0.5
    return acc / tot


def uv(size):
    h, w = size
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    return (x + 0.5) / w, (y + 0.5) / h  # u right, v DOWN (image rows)


def hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def mix(a, b, t):
    t = np.asarray(t)[..., None] if np.ndim(t) else t
    return a * (1 - t) + b * t


def fill(size, col):
    return np.ones(size + (3,)) * hex2rgb(col)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def normal_from_height(h, strength):
    # periodic central differences; image rows go DOWN so +v = -row
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * h.shape[1]
    dy = (np.roll(h, 1, 0) - np.roll(h, -1, 0)) * 0.5 * h.shape[0]
    s = strength / max(h.shape)
    n = np.dstack([-dx * s, -dy * s, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def ao_from_height(h, amount=0.6):
    blur = pnoise_blur(h, 6)
    cav = np.clip((blur - h) * 4.0, 0, 1)
    return np.clip(1.0 - cav * amount, 0, 1)


def pnoise_blur(img, radius):
    h, w = img.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-((fx ** 2 + fy ** 2) * (np.pi * radius) ** 2 * 2))
    return np.real(np.fft.ifft2(np.fft.fft2(img) * g))


def save(path, arr, mode="RGB"):
    arr = np.clip(arr, 0, 1)
    img = Image.fromarray((arr * 255 + 0.5).astype(np.uint8), mode)
    img.save(path, optimize=True)


# ----------------------------------------------------------------------------- generators
# each returns dict(base=HxWx3, height=HxW, rough=HxW or float, metal=HxW or float, ao=optional)

def g_wallpaper(S):
    u, v = uv(S)
    base = fill(S, "#7f957f")
    # 4 vertical stripes per unit, alternating shade
    stripe = (np.floor(u * 4) % 2)
    base = mix(base, fill(S, "#89a088"), stripe * 0.9)
    # thin pinstripes on stripe borders
    d = np.abs((u * 4) - np.round(u * 4))
    pin = smoothstep(0.012, 0.004, d)
    base = mix(base, fill(S, "#6d8370"), pin * 0.7)
    # diamond motif in the light stripes, two rows per unit
    motif = np.zeros(S[:2])
    for cx in (0.375, 0.875):
        for cy in (0.25, 0.75):
            du = np.abs(u - cx)
            dv = np.abs(v - cy)
            dd = du * 2.0 + dv            # tall diamond
            ring = smoothstep(0.075, 0.068, dd) * smoothstep(0.050, 0.057, dd)
            inner = smoothstep(0.022, 0.016, dd)
            motif = np.maximum(motif, np.maximum(ring, inner))
    base = mix(base, fill(S, "#a9bca3"), motif * 0.85)
    grain = fbm(S[:2], 60, 1, 3)
    base *= (0.94 + 0.08 * grain)[..., None]
    height = grain * 0.3 + motif * 0.15
    return dict(base=base, height=height, rough=0.82 - motif * 0.1, metal=0.0, nstr=1.5)


def g_plaster(S):
    n = fbm(S[:2], 12, 2, 5)
    base = mix(fill(S, "#7f7890"), fill(S, "#938ca3"), n)
    return dict(base=base, height=n, rough=0.9, metal=0.0, nstr=3.0)


def g_trim(S):
    u, v = uv(S)
    g = pnoise(S[:2], 50, 3, aniso=(0.08, 1.0))
    base = mix(fill(S, "#e4d2b6"), fill(S, "#efe2cc"), g)
    return dict(base=base, height=g * 0.3, rough=0.55, metal=0.0, nstr=1.0)


def g_checker(S):
    u, v = uv(S)
    n = 4
    iu, iv = np.floor(u * n), np.floor(v * n)
    par = (iu + iv) % 2
    red, cream = fill(S, "#9e4550"), fill(S, "#eee0cf")
    base = mix(red, cream, par)
    # per-tile tint variation (periodic because tiles are periodic)
    r = rng(4).random((n, n))
    tint = r[iv.astype(int), iu.astype(int)]
    base *= (0.94 + 0.08 * tint)[..., None]
    fu, fv = (u * n) % 1, (v * n) % 1
    edge = np.minimum(np.minimum(fu, 1 - fu), np.minimum(fv, 1 - fv))
    grout = smoothstep(0.022, 0.012, edge)
    wear = fbm(S[:2], 20, 5, 4)
    base = mix(base, fill(S, "#6d5a5a"), grout)
    base *= (0.95 + 0.07 * wear)[..., None]
    bevel = smoothstep(0.012, 0.05, edge)
    height = bevel * 0.8 + wear * 0.05
    rough = 0.32 + wear * 0.15 + grout * 0.5
    return dict(base=base, height=height, rough=rough, metal=0.0, nstr=4.0)


def planks(S, count, seed, c0, c1, gap_col, rough0):
    u, v = uv(S)
    row = np.floor(v * count)
    fv = (v * count) % 1
    r = rng(seed)
    offs = r.random(count)
    tints = r.random((count, 2))
    ri = row.astype(int)
    su = (u + offs[ri]) % 1.0           # one butt seam per row per tile
    half = (su >= 0.5).astype(int)
    tint = tints[ri, half]
    grain = pnoise(S[:2], 80, seed + 1, aniso=(0.05, 1.0))
    rings = np.sin((v * count * 9 + grain * 3 + tint * 5) * np.pi * 2) * 0.5 + 0.5
    base = mix(hex2rgb(c0) * np.ones(S[:2] + (3,)), hex2rgb(c1) * np.ones(S[:2] + (3,)),
               np.clip(rings * 0.5 + tint * 0.5, 0, 1))
    seam_v = np.minimum(fv, 1 - fv)
    seam_u = np.minimum(np.abs(su - 0.0), np.minimum(np.abs(su - 0.5), np.abs(su - 1.0)))
    gap = np.maximum(smoothstep(0.035, 0.015, seam_v), smoothstep(0.006, 0.002, seam_u))
    base = mix(base, hex2rgb(gap_col) * np.ones(S[:2] + (3,)), gap)
    height = (1 - gap) * 0.7 + rings * 0.08
    rough = rough0 + grain * 0.1 + gap * 0.2
    return dict(base=base, height=height, rough=rough, metal=0.0, nstr=4.0)


def g_floor_plank(S):
    return planks(S, 5, 10, "#8d8e97", "#a6a7ae", "#5c5c66", 0.7)


def g_crate(S):
    return planks(S, 4, 20, "#b98a55", "#d2a66e", "#6e4a2a", 0.75)


def wood(S, seed, c0, c1, rough, rings_n=24):
    u, v = uv(S)
    warp = pnoise(S[:2], 4, seed, aniso=(0.25, 1.0))      # long, gentle waves along the grain
    fine = pnoise(S[:2], 160, seed + 5, aniso=(0.03, 1.0))
    rings = np.sin((v * rings_n + warp * 0.9) * np.pi * 2) * 0.5 + 0.5
    rings = rings ** 2.2
    base = mix(fill(S, c0), fill(S, c1), np.clip(rings * 0.45 + fine * 0.55, 0, 1))
    height = rings * 0.2 + fine * 0.2
    return dict(base=base, height=height, rough=rough + fine * 0.08, metal=0.0, nstr=1.5)


def g_oak(S):
    return wood(S, 30, "#b8703a", "#d18d4f", 0.55)


def g_wood_dark(S):
    return wood(S, 31, "#7e4230", "#9a5840", 0.55)


def painted(col, seed, rough=0.6):
    def g(S):
        w = wood(S, seed, col, col, rough)
        n = pnoise(S[:2], 80, seed + 3, aniso=(0.05, 1.0))
        c = hex2rgb(col)
        w["base"] = mix(c * 0.92 * np.ones(S[:2] + (3,)), c * 1.05 * np.ones(S[:2] + (3,)), n)
        w["nstr"] = 0.8
        return w
    return g


def flat(col, seed, rough, metal=0.0, freq=40, var=0.06, nstr=1.0):
    def g(S):
        n = fbm(S[:2], freq, seed, 3)
        base = fill(S, col) * (1 - var + 2 * var * n)[..., None]
        return dict(base=base, height=n * 0.3, rough=rough + (n - 0.5) * 0.08, metal=metal, nstr=nstr)
    return g


def g_brushed(col, seed, rough):
    def g(S):
        n = pnoise(S[:2], 200, seed, aniso=(0.02, 1.0))
        base = fill(S, col) * (0.94 + 0.1 * n)[..., None]
        return dict(base=base, height=n * 0.1, rough=rough + n * 0.08, metal=1.0, nstr=0.5)
    return g


def weave(col0, col1, seed, cells, rough, nstr=5.0, diag=False):
    def g(S):
        u, v = uv(S)
        a = np.sin(u * cells * np.pi * 2) * 0.5 + 0.5
        b = np.sin(v * cells * np.pi * 2) * 0.5 + 0.5
        sel = ((np.floor(u * cells * 2) + np.floor(v * cells * 2)) % 2)
        h = np.where(sel > 0, a, b)
        n = fbm(S[:2], 30, seed, 3)
        base = mix(fill(S, col0), fill(S, col1), np.clip(h * 0.6 + n * 0.4, 0, 1))
        return dict(base=base, height=h * 0.8 + n * 0.2, rough=rough, metal=0.0, nstr=nstr)
    return g


def g_cardboard(S):
    u, v = uv(S)
    fib = pnoise(S[:2], 150, 50, aniso=(1.0, 0.15))
    n = fbm(S[:2], 10, 51, 4)
    base = mix(fill(S, "#c49a64"), fill(S, "#d8b27c"), np.clip(n * 0.7 + fib * 0.3, 0, 1))
    return dict(base=base, height=fib * 0.3 + n * 0.2, rough=0.85, metal=0.0, nstr=1.5)


def g_stone(S):
    u, v = uv(S)
    n = fbm(S[:2], 8, 60, 5)
    base = mix(fill(S, "#7c7784"), fill(S, "#99949f"), n)
    # 2x1 block seams
    fv = (v * 2) % 1
    fu = (u * 1 + np.floor(v * 2) * 0.5) % 1
    seam = np.maximum(smoothstep(0.02, 0.008, np.minimum(fv, 1 - fv)),
                      smoothstep(0.01, 0.004, np.minimum(fu, 1 - fu)))
    base = mix(base, fill(S, "#5d5866"), seam)
    return dict(base=base, height=n * 0.5 + (1 - seam) * 0.5, rough=0.9, metal=0.0, nstr=4.0)


def g_bread(S):
    n = fbm(S[:2], 14, 70, 4)
    base = mix(fill(S, "#b0703a"), fill(S, "#dba066"), n)
    pores = pnoise(S[:2], 160, 71)
    return dict(base=base, height=n * 0.5 + pores * 0.3, rough=0.8, metal=0.0, nstr=3.0)


def g_rug(S):
    u, v = uv(S)
    n = fbm(S[:2], 40, 80, 3)
    base = fill(S, "#a8505a") * (0.92 + 0.12 * n)[..., None]
    du = np.minimum(u, 1 - u)
    dv = np.minimum(v, 1 - v) * 4.0  # rug is 1 x 4 aspect
    d = np.minimum(du, dv)
    border = smoothstep(0.075, 0.07, d) * smoothstep(0.055, 0.06, d)
    base = mix(base, fill(S, "#d2848a"), border)
    edge = smoothstep(0.02, 0.0, d)
    base = mix(base, fill(S, "#7c343d"), edge)
    fib = pnoise(S[:2], 250, 81)
    return dict(base=base, height=fib * 0.6 + n * 0.2, rough=0.95, metal=0.0, nstr=2.0)


def g_calendar(S):
    u, v = uv(S)
    base = fill(S, "#f2ebdc")
    head = v < 0.28
    base[head] = hex2rgb("#9a82a8")
    # 7x5 grid below header
    gu, gv = u * 7, (v - 0.34) / 0.6 * 5
    inside = (v > 0.34) & (v < 0.94) & (u > 0.04) & (u < 0.96)
    gu = (u - 0.04) / 0.92 * 7
    lines = (np.minimum(gu % 1, 1 - gu % 1) < 0.04) | (np.minimum(gv % 1, 1 - gv % 1) < 0.04)
    base[inside & lines] = hex2rgb("#8a7f8f")
    rings = (v < 0.05) & ((np.abs(u - 0.3) < 0.02) | (np.abs(u - 0.7) < 0.02))
    base[rings] = hex2rgb("#555555")
    return dict(base=base, height=np.zeros(S[:2]), rough=0.85, metal=0.0, nstr=0.0)


def g_note(S):
    u, v = uv(S)
    base = fill(S, "#f3e7c4")
    lines = (np.minimum((v * 8) % 1, 1 - (v * 8) % 1) < 0.05) & (v > 0.25) & (u > 0.12) & (u < 0.88)
    base[lines] = hex2rgb("#8a7f70")
    return dict(base=base, height=np.zeros(S[:2]), rough=0.85, metal=0.0, nstr=0.0)


# ----------------------------------------------------------------------------- registry
# name: (resolution, generator, tile size in metres covered by one texture repeat)
GRID = 1.0
MATERIALS = {
    # --- architecture (1024 px per 1 m grid cell)
    "Wallpaper_Sage":   (1024, g_wallpaper, GRID),
    "Plaster_Lilac":    (512, g_plaster, GRID),
    "Trim_Cream":       (512, g_trim, GRID),
    "Floor_Checker":    (1024, g_checker, GRID),
    "Floor_PlankGrey":  (1024, g_floor_plank, GRID),
    "Stone_Foundation": (512, g_stone, GRID),
    # --- wood
    "Wood_Oak":         (1024, g_oak, GRID),
    "Wood_Walnut":      (512, g_wood_dark, GRID),
    "Wood_Crate":       (512, g_crate, GRID * 0.5),
    "Paint_Sage":       (256, painted("#8e9a6c", 32), 0.5),
    "Paint_Brick":      (256, painted("#a0503e", 33), 0.5),
    "Counter_Maroon":   (256, flat("#86384a", 40, 0.38), GRID),
    # --- metal / ceramic / glass
    "Metal_Steel":      (256, g_brushed("#b9b9be", 41, 0.32), 0.5),
    "Metal_Copper":     (256, g_brushed("#c26a3a", 42, 0.28), 0.5),
    "Metal_Iron":       (256, flat("#35353c", 43, 0.5, metal=1.0), 0.5),
    "Ceramic_White":    (256, flat("#efe9dd", 44, 0.18, var=0.02), 0.5),
    "Enamel_Cream":     (256, flat("#e9e3d6", 45, 0.25, var=0.02), 0.5),
    "Glass_Clear":      (128, flat("#e4efec", 46, 0.04, var=0.0, nstr=0.0), 0.5),
    # --- soft goods
    "Fabric_Curtain":   (512, weave("#848c93", "#98a0a6", 47, 90, 0.95, 2.0), 0.5),
    "Fabric_LinenWhite": (256, weave("#ddd4c4", "#ece5d8", 48, 60, 0.95, 2.0), 0.5),
    "Fabric_Charcoal":  (256, weave("#47475a", "#565670", 49, 60, 0.95, 2.0), 0.5),
    "Rug_Runner":       (1024, g_rug, None),   # unique UV (0..1 over the rug)
    "Burlap":           (512, weave("#a89068", "#c2ab82", 52, 70, 0.95, 4.0), 0.5),
    "Wicker":           (512, weave("#9e6c3e", "#c08a52", 53, 22, 0.8, 6.0), 0.5),
    "Cardboard":        (512, g_cardboard, 1.0),
    "Tape_Kraft":       (128, flat("#d6b77e", 54, 0.5, var=0.03), 0.5),
    # --- food / plants / paper
    "Bread_Crust":      (512, g_bread, 0.3),
    "Leaf_Green":       (256, flat("#5a8a48", 55, 0.6, freq=20, var=0.12), 0.3),
    "Terracotta":       (256, flat("#b35f3c", 56, 0.85, freq=30, var=0.1, nstr=2.0), 0.5),
    "Soil_Dark":        (128, flat("#3b2a22", 57, 0.95, freq=60, var=0.2, nstr=3.0), 0.3),
    "Paper_Cream":      (256, flat("#f2ead8", 58, 0.85, var=0.02), 0.5),
    "Calendar_Print":   (512, g_calendar, None),
    "Note_Paper":       (256, g_note, None),
    # --- preserves (jar contents) / plastics / labels
    "Preserve_Berry":   (128, flat("#8e2a3c", 60, 0.3, freq=10, var=0.15), 0.3),
    "Preserve_Plum":    (128, flat("#5a2e5c", 61, 0.3, freq=10, var=0.15), 0.3),
    "Preserve_Pickle":  (128, flat("#5d6e2c", 62, 0.3, freq=10, var=0.15), 0.3),
    "Preserve_Honey":   (128, flat("#c8902c", 63, 0.25, freq=10, var=0.1), 0.3),
    "Plastic_Red":      (128, flat("#b8282a", 64, 0.3, var=0.03), 0.3),
    "Plastic_Yellow":   (128, flat("#d8b030", 65, 0.3, var=0.03), 0.3),
    "Paint_Lavender":   (128, flat("#8e7fa0", 66, 0.6, var=0.05), 0.3),
    "Paint_Teal":       (128, flat("#5f8a88", 67, 0.6, var=0.05), 0.3),
}

# Materials with extra shader settings (applied in build_scene.py)
SPECIAL = {
    "Glass_Clear": dict(transmission=1.0, ior=1.45),
    "Metal_Steel": dict(),
}


def generate_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for name, (res, gen, _tile) in MATERIALS.items():
        S = (res, res) if name != "Rug_Runner" else (res, res // 4)
        if name == "Calendar_Print":
            S = (res, int(res * 0.75))
        d = gen(S)
        H, W = S
        base = d["base"]
        rough = d["rough"] * np.ones((H, W)) if np.ndim(d["rough"]) == 0 else d["rough"]
        metal = d["metal"] * np.ones((H, W)) if np.ndim(d["metal"]) == 0 else d["metal"]
        height = d["height"]
        nstr = d.get("nstr", 2.0)
        normal = normal_from_height(height, nstr) if nstr > 0 else np.dstack(
            [np.full((H, W), .5), np.full((H, W), .5), np.ones((H, W))])
        ao = d.get("ao", ao_from_height(height, 0.5) if nstr > 0 else np.ones((H, W)))
        # quantise flat-ish maps a little: keeps PNGs small without visible banding
        save(os.path.join(out_dir, f"T_{name}_BaseColor.png"), base)
        save(os.path.join(out_dir, f"T_{name}_Normal.png"), np.round(normal * 127) / 127)
        save(os.path.join(out_dir, f"T_{name}_ORM.png"),
             np.round(np.dstack([ao, rough, metal]) * 63) / 63)
        print("texture", name, S)


if __name__ == "__main__":
    import sys
    generate_all(sys.argv[1] if len(sys.argv) > 1 else "Textures")
