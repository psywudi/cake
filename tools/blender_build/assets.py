"""
Asset definitions. Every function returns a spec dict:
  mb      : MB mesh builder
  bevel   : bevel width (0 = none)
  col     : 'bounds' | list of ((x0,y0,z0),(x1,y1,z1)) collision boxes | None
  weld    : merge coincident verts (lathe objects)
  pivot   : text describing the pivot convention (stored as custom property)

Pivot conventions
  Architecture modules : grid corner (0,0,0). Module runs along +X, room interior is +Y,
                         the module occupies y = 0..T (T = half wall thickness).
  Wall-mounted props   : back-left-bottom corner; width +X, depth +Y (same frame as walls).
  Free props           : bottom centre.
"""
import math
import bpy
from mathutils import Matrix, Vector

from kit import MB, U, H, T, M

# door / window opening dimensions (wall-local)
DOOR = dict(x0=0.1, x1=0.9, z0=0.0, z1=2.1)        # in SM_Wall_Door_1x3
WINDOW = dict(x0=0.15, x1=0.85, z0=1.0, z1=2.2)    # in SM_Wall_Window_1x3
DOORWAY = dict(x0=0.4, x1=1.6, z0=0.0, z1=2.2)     # in SM_Wall_Doorway_2x3

PIV_GRID = "grid-corner"
PIV_BACK = "back-left-bottom"
PIV_BOTTOM = "bottom-centre"


def R(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def Tr(x, y, z):
    return Matrix.Translation(Vector((x, y, z)))


def S(x, y, z):
    return Matrix.Diagonal(Vector((x, y, z, 1.0)))


# ============================================================================ architecture
def _wall_material(poly, length_x0):
    n = poly.normal
    c = poly.center
    if n.z > 0.9 and c.z > H - 1e-4:
        return "Trim_Cream"
    if n.y > 0.9 and c.y > T - 1e-4:
        return "Wallpaper_Sage"
    return "Plaster_Lilac"


def wall_mesh(x0, x1, openings=(), height=H):
    """Wall body x0..x1, y 0..T, z 0..height, openings cut with an exact boolean."""
    mb = MB()
    body = MB()
    body.box((x0, 0, 0), (x1, T, height), None)
    me = bpy.data.meshes.new("_tmp_wall")
    me.from_pydata(body.V, [], body.F)
    ob = bpy.data.objects.new("_tmp_wall", me)
    bpy.context.scene.collection.objects.link(ob)
    cutters = []
    for o in openings:
        cb = MB()
        cb.box((o["x0"], -0.1, o["z0"] - (0.1 if o["z0"] <= 0 else 0)), (o["x1"], T + 0.1, o["z1"]), None)
        cm = bpy.data.meshes.new("_tmp_cut")
        cm.from_pydata(cb.V, [], cb.F)
        co = bpy.data.objects.new("_tmp_cut", cm)
        bpy.context.scene.collection.objects.link(co)
        co.hide_render = True
        mod = ob.modifiers.new("Bool", "BOOLEAN")
        mod.object = co
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        cutters.append(co)
    dg = bpy.context.evaluated_depsgraph_get()
    res = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    mb.add_mesh(res, lambda p: _wall_material(p, x0))
    for o in [ob] + cutters:
        m = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(m)
    bpy.data.meshes.remove(res)
    # trims on the interior face
    segs = [(x0, x1)]
    for o in openings:
        if o["z0"] < 0.13:
            new = []
            for a, b in segs:
                if o["x1"] <= a or o["x0"] >= b:
                    new.append((a, b))
                    continue
                if o["x0"] > a:
                    new.append((a, o["x0"]))
                if o["x1"] < b:
                    new.append((o["x1"], b))
            segs = new
    for a, b in segs:
        mb.box((a, T, 0), (b, T + 0.02, 0.12), "Trim_Cream")               # baseboard
    if height >= H - 1e-4:
        mb.box((x0, T, height - 0.09), (x1, T + 0.028, height), "Trim_Cream")  # crown
    return mb


def wall_colliders(x0, x1, openings=(), height=H):
    boxes = []
    xs = [x0] + [v for o in sorted(openings, key=lambda o: o["x0"]) for v in (o["x0"], o["x1"])] + [x1]
    for i in range(0, len(xs), 2):
        if xs[i + 1] - xs[i] > 1e-4:
            boxes.append(((xs[i], 0, 0), (xs[i + 1], T, height)))
    for o in openings:
        boxes.append(((o["x0"], 0, o["z1"]), (o["x1"], T, height)))
        if o["z0"] > 0:
            boxes.append(((o["x0"], 0, 0), (o["x1"], T, o["z0"])))
    return boxes


def a_wall():
    return dict(mb=wall_mesh(0, U), col=wall_colliders(0, U), pivot=PIV_GRID, grid=(1, 3))


def _wall_mat_nc(n, c):
    if n.z > 0.9 and c.z > H - 1e-4:
        return "Trim_Cream"
    if n.y > 0.9 and c.y > T - 1e-4:
        return "Wallpaper_Sage"
    return "Plaster_Lilac"


def _corner(start):
    """Full-length (1U) inner-corner wall, mitred 45 deg at one end so that two corner
    modules meeting at a room corner close it without overlapping."""
    mb = MB()
    if start:
        poly = [(0, 0), (U, 0), (U, T), (T, T)]
        a, b = T, U
    else:
        poly = [(0, 0), (U, 0), (U - T, T), (0, T)]
        a, b = 0, U - T
    mb.prism(poly, 0, H, _wall_mat_nc)
    mb.box((a, T, 0), (b, T + 0.02, 0.12), "Trim_Cream")
    mb.box((a, T, H - 0.09), (b, T + 0.028, H), "Trim_Cream")
    return mb


def a_wall_corner_l():
    return dict(mb=_corner(True), col=wall_colliders(0, U), pivot=PIV_GRID, grid=(1, 3),
                note="inner room corner at local start (x=0), 45 deg mitre")


def a_wall_corner_r():
    return dict(mb=_corner(False), col=wall_colliders(0, U), pivot=PIV_GRID, grid=(1, 3),
                note="inner room corner at local end (x=1), 45 deg mitre")


def a_wall_half_width():
    return dict(mb=wall_mesh(0, 0.5 * U), col=wall_colliders(0, 0.5 * U), pivot=PIV_GRID, grid=(0.5, 3))


def a_wall_door():
    return dict(mb=wall_mesh(0, U, [DOOR]), col=wall_colliders(0, U, [DOOR]), pivot=PIV_GRID, grid=(1, 3),
                socket="Door_1x3")


def a_wall_window():
    return dict(mb=wall_mesh(0, U, [WINDOW]), col=wall_colliders(0, U, [WINDOW]), pivot=PIV_GRID, grid=(1, 3))


def a_wall_doorway():
    return dict(mb=wall_mesh(0, 2 * U, [DOORWAY]), col=wall_colliders(0, 2 * U, [DOORWAY]),
                pivot=PIV_GRID, grid=(2, 3), socket="Doorway_2x3")


def a_wall_half():
    """Low cut-away wall (1U x 0.5U) for diorama front edges."""
    mb = MB()
    mb.box((0, 0, 0), (U, T, 0.5), "Plaster_Lilac", mats={"+z": "Trim_Cream", "+y": "Wallpaper_Sage"})
    mb.box((0, T, 0), (U, T + 0.02, 0.12), "Trim_Cream")
    return dict(mb=mb, col=[((0, 0, 0), (U, T, 0.5))], pivot=PIV_GRID, grid=(1, 0.5))


def a_wall_post():
    mb = MB()
    mb.box((0, 0, 0), (T, T, H), "Plaster_Lilac", mats={"+z": "Trim_Cream"})
    return dict(mb=mb, col="bounds", pivot=PIV_GRID, note="outer-corner filler T x T")


def a_floor(matname):
    def f():
        mb = MB()
        mb.box((0, 0, -0.05), (U, U, 0), matname)
        return dict(mb=mb, col="bounds", pivot=PIV_GRID, grid=(1, 1))
    return f


def a_foundation():
    mb = MB()
    mb.box((0, 0, -0.35), (U, U, -0.05), "Stone_Foundation")
    return dict(mb=mb, col="bounds", pivot=PIV_GRID, grid=(1, 1))


def a_rug():
    mb = MB()
    w, l, h = 0.8, 2.8, 0.012
    x0, y0 = (U - w) / 2, (3 * U - l) / 2
    mb.quad_uv([(x0, y0, h), (x0 + w, y0, h), (x0 + w, y0 + l, h), (x0, y0 + l, h)], "Rug_Runner",
               [(0, 0), (1, 0), (1, 1), (0, 1)])
    mb.box((x0, y0, 0), (x0 + w, y0 + l, h), "Rug_Runner", faces=["-x", "+x", "-y", "+y"])
    return dict(mb=mb, col=None, pivot=PIV_GRID, grid=(1, 3))


# ---- openings
def a_doorframe():
    d = DOOR
    mb = MB()
    m = "Trim_Cream"
    j = 0.04
    mb.box((d["x0"], 0, 0), (d["x0"] + j, T, d["z1"]), m)
    mb.box((d["x1"] - j, 0, 0), (d["x1"], T, d["z1"]), m)
    mb.box((d["x0"] + j, 0, d["z1"] - j), (d["x1"] - j, T, d["z1"]), m)
    c = 0.08
    mb.box((d["x0"] - c, T, 0), (d["x0"], T + 0.025, d["z1"] + c), m)
    mb.box((d["x1"], T, 0), (d["x1"] + c, T + 0.025, d["z1"] + c), m)
    mb.box((d["x0"], T, d["z1"]), (d["x1"], T + 0.025, d["z1"] + c), m)
    # plinth blocks
    mb.box((d["x0"] - c - 0.005, T, 0), (d["x0"] + 0.005, T + 0.035, 0.16), m)
    mb.box((d["x1"] - 0.005, T, 0), (d["x1"] + c + 0.005, T + 0.035, 0.16), m)
    return dict(mb=mb, bevel=0.004, col=None, pivot=PIV_GRID, grid=(1, 3),
                note="same pivot as SM_Wall_Door_1x3; one per room side")


def a_door():
    mb = MB()
    w, h, t = DOOR["x1"] - DOOR["x0"] - 0.08, DOOR["z1"] - 0.04, 0.045
    mb.box((0, 0, 0), (w, t, h), "Wood_Oak")
    for (xa, xb) in ((0.1, w / 2 - 0.04), (w / 2 + 0.04, w - 0.1)):
        for (za, zb) in ((0.15, 0.95), (1.1, h - 0.15)):
            mb.box((xa, -0.008, za), (xb, 0, zb), "Wood_Oak")
            mb.box((xa, t, za), (xb, t + 0.008, zb), "Wood_Oak")
    knob = [(0, 0), (0.012, 0), (0.012, 0.035), (0.028, 0.045), (0.03, 0.06), (0.02, 0.07), (0, 0.072)]
    for side, rx in ((t, -90), (0, 90)):
        mk = mb.mark()
        mb.lathe(knob, "Metal_Steel", 14)
        mb.xform(mk, Tr(w - 0.08, side, 1.0) @ R("X", rx))
    # iron strap hinges + lock plate
    for z in (0.25, h - 0.35):
        mb.box((-0.005, t, z), (0.22, t + 0.006, z + 0.05), "Metal_Iron")
    mb.box((w - 0.12, t, 1.3), (w - 0.04, t + 0.01, 1.45), "Metal_Iron")
    return dict(mb=mb, bevel=0.004, weld=False, col="bounds", pivot="hinge-bottom",
                note="pivot on hinge axis; place at wall-local (DOOR.x0+0.04, T-0.05, 0)")


def a_doorframe_wide():
    d = DOORWAY
    mb = MB()
    m = "Trim_Cream"
    j = 0.04
    mb.box((d["x0"], 0, 0), (d["x0"] + j, T, d["z1"]), m)
    mb.box((d["x1"] - j, 0, 0), (d["x1"], T, d["z1"]), m)
    mb.box((d["x0"] + j, 0, d["z1"] - j), (d["x1"] - j, T, d["z1"]), m)
    c = 0.12
    mb.box((d["x0"] - c, T, 0), (d["x0"], T + 0.03, d["z1"] + c), m)
    mb.box((d["x1"], T, 0), (d["x1"] + c, T + 0.03, d["z1"] + c), m)
    mb.box((d["x0"] - c - 0.02, T, d["z1"] + c - 0.02), (d["x1"] + c + 0.02, T + 0.045, d["z1"] + c + 0.03), m)
    mb.box((d["x0"], T, d["z1"]), (d["x1"], T + 0.03, d["z1"] + c - 0.02), m)
    return dict(mb=mb, bevel=0.005, col=None, pivot=PIV_GRID, grid=(2, 3))


def a_window_frame():
    w = WINDOW
    mb = MB()
    m = "Trim_Cream"
    j = 0.04
    x0, x1, z0, z1 = w["x0"], w["x1"], w["z0"], w["z1"]
    mb.box((x0, 0, z0), (x0 + j, T, z1), m)
    mb.box((x1 - j, 0, z0), (x1, T, z1), m)
    mb.box((x0 + j, 0, z1 - j), (x1 - j, T, z1), m)
    mb.box((x0 + j, 0, z0), (x1 - j, T, z0 + j), m)
    c = 0.08
    mb.box((x0 - c, T, z0), (x0, T + 0.02, z1 + c), m)
    mb.box((x1, T, z0), (x1 + c, T + 0.02, z1 + c), m)
    mb.box((x0, T, z1), (x1, T + 0.02, z1 + c), m)
    mb.box((x0 - c - 0.03, T - 0.03, z0 - 0.04), (x1 + c + 0.03, T + 0.07, z0), m)     # sill
    mb.box((x0 - c + 0.02, T, z0 - 0.12), (x1 + c - 0.02, T + 0.02, z0 - 0.04), m)     # apron
    gy0, gy1 = T * 0.5 - 0.018, T * 0.5 + 0.018
    s = 0.035
    mb.box((x0 + j, gy0, z0 + j), (x0 + j + s, gy1, z1 - j), m)
    mb.box((x1 - j - s, gy0, z0 + j), (x1 - j, gy1, z1 - j), m)
    mb.box((x0 + j, gy0, z1 - j - s), (x1 - j, gy1, z1 - j), m)
    mb.box((x0 + j, gy0, z0 + j), (x1 - j, gy1, z0 + j + s), m)
    xm, zm = (x0 + x1) / 2, (z0 + z1) / 2
    mb.box((xm - 0.015, gy0, z0 + j), (xm + 0.015, gy1, z1 - j), m)
    mb.box((x0 + j, gy0, zm - 0.015), (x1 - j, gy1, zm + 0.015), m)
    return dict(mb=mb, bevel=0.003, col=None, pivot=PIV_GRID, grid=(1, 3))


def a_window_glass():
    w = WINDOW
    mb = MB()
    mb.box((w["x0"] + 0.06, T * 0.5 - 0.003, w["z0"] + 0.06), (w["x1"] - 0.06, T * 0.5 + 0.003, w["z1"] - 0.06),
           "Glass_Clear")
    return dict(mb=mb, col=None, pivot=PIV_GRID, grid=(1, 3))


def a_curtain_rod():
    mb = MB()
    mk = mb.mark()
    mb.lathe([(0.014, 0), (0.014, U + 0.3)], "Wood_Walnut", 10)
    for z in (0.0, U + 0.3):
        mb.lathe([(0, -0.03), (0.03, -0.015), (0.03, 0.0), (0, 0.02)], "Wood_Walnut", 10, (0, 0, z))
    mb.xform(mk, Tr(-0.15, T + 0.12, 2.4) @ R("Y", 90))
    for x in (-0.05, U + 0.05):
        mb.box((x - 0.015, T, 2.38), (x + 0.015, T + 0.13, 2.42), "Metal_Iron")
    return dict(mb=mb, weld=True, col=None, pivot=PIV_GRID, note="1U window; overhangs 0.15 each side")


def a_curtain():
    mb = MB()

    def f(s, t):
        z = -1.35 * (1 - t)
        gather = 0.35 + 0.65 * min(1.0, abs(t - 0.38) / 0.35) ** 1.5
        x = (s - 0.5) * 0.42 * gather
        y = 0.035 * math.sin(s * math.pi * 6) * (0.6 + 0.4 * gather)
        return (x, y, z)
    mb.grid_surface(f, 18, 16, "Fabric_Curtain", uv_scale=(0.42, 1.35), double=True)
    mb.box((-0.08, -0.04, -0.87), (0.08, 0.04, -0.82), "Fabric_Curtain")
    return dict(mb=mb, col=None, pivot="top-centre", note="hang from SM_Curtain_Rod_1U")


# ============================================================================ kitchen furniture
def _knob(mb, x, y, z, mat="Metal_Steel", r=0.018):
    mk = mb.mark()
    mb.lathe([(0, 0), (0.007, 0), (0.007, 0.012), (r, 0.022), (r * 0.9, 0.032), (0, 0.035)], mat, 10)
    mb.xform(mk, Tr(x, y, z) @ R("X", -90))


def _door_front(mb, x0, x1, z0, z1, y, knob_x, knob_z):
    mb.box((x0, y, z0), (x1, y + 0.02, z1), "Wood_Oak")
    mb.box((x0 + 0.06, y + 0.02, z0 + 0.07), (x1 - 0.06, y + 0.03, z1 - 0.07), "Wood_Oak")
    _knob(mb, knob_x, y + 0.02, knob_z)


def _base_carcass(mb, w, top=True):
    mb.box((0.03, 0, 0), (w - 0.03, 0.52, 0.1), "Wood_Walnut")
    mb.box((0, 0, 0.1), (w, 0.58, 0.86), "Wood_Oak")
    if top:
        mb.box((0, 0, 0.86), (w, 0.62, 0.9), "Counter_Maroon")


def a_cab_door():
    w = 0.5 * U
    mb = MB()
    _base_carcass(mb, w)
    _door_front(mb, 0.02, w - 0.02, 0.13, 0.83, 0.58, w - 0.08, 0.72)
    return dict(mb=mb, bevel=0.006, col="bounds", pivot=PIV_BACK, grid=(0.5, 1))


def a_cab_drawers():
    w = 0.5 * U
    mb = MB()
    _base_carcass(mb, w)
    for z0, z1 in ((0.13, 0.36), (0.38, 0.6), (0.62, 0.83)):
        mb.box((0.02, 0.58, z0), (w - 0.02, 0.6, z1), "Wood_Oak")
        mb.box((0.06, 0.6, z0 + 0.04), (w - 0.06, 0.607, z1 - 0.04), "Wood_Oak")
        _knob(mb, w / 2, 0.607, (z0 + z1) / 2)
    return dict(mb=mb, bevel=0.006, col="bounds", pivot=PIV_BACK, grid=(0.5, 1))


def a_cab_corner():
    """L-shaped corner base cabinet filling one 1x1 grid cell in a room corner.
    Wall frame of the wall it is placed on; the corner is at local x = 1 (end)."""
    mb = MB()
    e = U - T                 # inner face of the perpendicular wall
    d = 0.58
    L = e - d                 # x where the return leg starts
    mb.box((0.03, 0, 0), (e, 0.52, 0.1), "Wood_Walnut")
    mb.box((L + 0.06, 0.52, 0), (e, e, 0.1), "Wood_Walnut")
    mb.box((0, 0, 0.1), (e, d, 0.86), "Wood_Oak")
    mb.box((L, d, 0.1), (e, e, 0.86), "Wood_Oak")
    mb.box((0, 0, 0.86), (e, 0.62, 0.9), "Counter_Maroon")
    mb.box((L - 0.04, 0.62, 0.86), (e, e, 0.9), "Counter_Maroon")
    _door_front(mb, 0.02, L - 0.02, 0.13, 0.83, d, L - 0.08, 0.72)
    # door on the return leg, facing -X
    mk = mb.mark()
    _door_front(mb, 0.02, e - d - 0.02, 0.13, 0.83, 0, 0.08, 0.72)
    mb.xform(mk, Tr(L, d, 0) @ R("Z", 90))
    return dict(mb=mb, bevel=0.006, col=[((0, 0, 0), (e, 0.62, 0.9)), ((L - 0.04, 0.62, 0), (e, e, 0.9))],
                pivot=PIV_BACK, grid=(1, 1), note="corner at local +X end; both runs continue at grid lines")


def a_cab_sink():
    w = U
    mb = MB()
    mb.box((0.03, 0, 0), (w - 0.03, 0.52, 0.1), "Wood_Walnut")
    mb.box((0, 0, 0.1), (w, 0.58, 0.62), "Wood_Oak")
    mb.box((0, 0, 0.62), (0.2, 0.58, 0.86), "Wood_Oak")
    mb.box((w - 0.2, 0, 0.62), (w, 0.58, 0.86), "Wood_Oak")
    _door_front(mb, 0.02, w / 2 - 0.01, 0.13, 0.6, 0.58, w / 2 - 0.07, 0.5)
    _door_front(mb, w / 2 + 0.01, w - 0.02, 0.13, 0.6, 0.58, w / 2 + 0.07, 0.5)
    mb.box((0, 0, 0.86), (0.2, 0.62, 0.9), "Counter_Maroon")
    mb.box((w - 0.2, 0, 0.86), (w, 0.62, 0.9), "Counter_Maroon")
    mb.box((0.2, 0, 0.86), (w - 0.2, 0.08, 0.9), "Counter_Maroon")
    c = "Ceramic_White"
    x0, x1, y0, y1, z0, z1, t = 0.2, w - 0.2, 0.08, 0.64, 0.6, 0.92, 0.04
    mb.box((x0, y0, z0), (x1, y1, z0 + t), c)
    mb.box((x0, y1 - t, z0 + t), (x1, y1, z1), c)
    mb.box((x0, y0, z0 + t), (x1, y0 + t, z1), c)
    mb.box((x0, y0 + t, z0 + t), (x0 + t, y1 - t, z1), c)
    mb.box((x1 - t, y0 + t, z0 + t), (x1, y1 - t, z1), c)
    xm = w / 2
    mb.cyl((xm, 0.04, 0.9), 0.022, 0.24, "Metal_Steel", 12)
    mb.box((xm - 0.015, 0.02, 1.12), (xm + 0.015, 0.26, 1.15), "Metal_Steel")
    mb.box((xm - 0.015, 0.23, 1.06), (xm + 0.015, 0.26, 1.12), "Metal_Steel")
    for dx in (-0.1, 0.1):
        mb.cyl((xm + dx, 0.04, 0.9), 0.02, 0.06, "Metal_Steel", 10)
    return dict(mb=mb, bevel=0.005, col="bounds", pivot=PIV_BACK, grid=(1, 1))


def a_cab_wall():
    w = 0.5 * U
    mb = MB()
    mb.box((0, 0, 0), (w, 0.31, 0.7), "Wood_Oak")
    _door_front(mb, 0.02, w - 0.02, 0.02, 0.68, 0.31, w - 0.08, 0.1)
    mb.box((-0.01, 0, 0.7), (w + 0.01, 0.35, 0.74), "Wood_Oak")
    return dict(mb=mb, bevel=0.006, col="bounds", pivot=PIV_BACK, grid=(0.5, 0.5),
                note="mount at z = 1.45")


def a_stove():
    w = 0.5 * U
    mb = MB()
    e, s, i = "Enamel_Cream", "Metal_Steel", "Metal_Iron"
    mb.box((0, 0, 0), (w, 0.6, 0.88), e)
    mb.box((0.03, 0.6, 0.1), (w - 0.03, 0.62, 0.66), s)
    mb.box((0.1, 0.62, 0.3), (w - 0.1, 0.626, 0.56), i)
    mb.box((0.06, 0.64, 0.61), (w - 0.06, 0.66, 0.635), s)
    for x in (0.07, w - 0.08):
        mb.box((x, 0.62, 0.61), (x + 0.012, 0.645, 0.635), s)
    mb.box((0, 0, 0.88), (w, 0.6, 0.9), s)
    mb.box((0, 0, 0.9), (w, 0.06, 1.06), s)
    for x in (0.18, w - 0.18):
        for y in (0.2, 0.44):
            mb.cyl((x, y, 0.9), 0.075, 0.012, i, 16)
            mb.cyl((x, y, 0.912), 0.035, 0.012, i, 12)
    for k in range(4):
        _knob(mb, 0.1 + k * (w - 0.2) / 3, 0.6, 0.78, "Metal_Iron", 0.02)
    mb.box((0.17, 0.645, 0.36), (0.36, 0.665, 0.64), "Paint_Sage")      # tea towel
    return dict(mb=mb, bevel=0.005, col="bounds", pivot=PIV_BACK, grid=(0.5, 1))


def a_fridge():
    mb = MB()
    e, s = "Enamel_Cream", "Metal_Steel"
    mb.box((0, 0, 0.03), (0.8, 0.64, 1.85), e)
    mb.box((0.03, 0.02, 0), (0.77, 0.6, 0.03), "Metal_Iron")
    mb.box((0.01, 0.64, 1.23), (0.79, 0.69, 1.84), e)
    mb.box((0.01, 0.64, 0.05), (0.79, 0.69, 1.21), e)
    for z0, z1 in ((1.3, 1.62), (0.8, 1.14)):
        mb.box((0.06, 0.71, z0), (0.09, 0.74, z1), s)
        mb.box((0.065, 0.69, z0), (0.085, 0.71, z0 + 0.03), s)
        mb.box((0.065, 0.69, z1 - 0.03), (0.085, 0.71, z1), s)
    return dict(mb=mb, bevel=0.02, bevel_seg=3, col="bounds", pivot=PIV_BACK, grid=(1, 1))


# ============================================================================ dining
def a_table():
    mb = MB()
    w, d = 2.5, 1.0
    mb.box((-w / 2, -d / 2, 0.72), (w / 2, d / 2, 0.78), "Wood_Oak")
    mb.box((-w / 2 + 0.1, -d / 2 + 0.08, 0.62), (w / 2 - 0.1, -d / 2 + 0.11, 0.72), "Wood_Oak")
    mb.box((-w / 2 + 0.1, d / 2 - 0.11, 0.62), (w / 2 - 0.1, d / 2 - 0.08, 0.72), "Wood_Oak")
    mb.box((-w / 2 + 0.1, -d / 2 + 0.11, 0.62), (-w / 2 + 0.13, d / 2 - 0.11, 0.72), "Wood_Oak")
    mb.box((w / 2 - 0.13, -d / 2 + 0.11, 0.62), (w / 2 - 0.1, d / 2 - 0.11, 0.72), "Wood_Oak")
    for sx in (-1, 1):
        for sy in (-1, 1):
            x = sx * (w / 2 - 0.14)
            y = sy * (d / 2 - 0.12)
            mb.box((x - 0.045, y - 0.045, 0), (x + 0.045, y + 0.045, 0.72), "Wood_Oak")
    return dict(mb=mb, bevel=0.01, col="bounds", pivot=PIV_BOTTOM)


def a_chair(mat):
    def f():
        mb = MB()
        mb.box((-0.22, -0.22, 0.43), (0.22, 0.19, 0.47), mat)
        for x in (-0.2, 0.17):
            mb.box((x, -0.2, 0), (x + 0.035, -0.165, 0.43), mat)
            mb.box((x, 0.16, 0), (x + 0.035, 0.2, 0.98), mat)
        mb.box((-0.165, 0.166, 0.86), (0.17, 0.194, 0.96), mat)
        for x in (-0.11, -0.018, 0.075):
            mb.box((x, 0.17, 0.47), (x + 0.036, 0.19, 0.86), mat)
        mb.box((-0.18, -0.19, 0.14), (0.18, -0.17, 0.17), mat)
        mb.box((-0.19, -0.17, 0.12), (-0.17, 0.17, 0.15), mat)
        mb.box((0.17, -0.17, 0.12), (0.19, 0.17, 0.15), mat)
        return dict(mb=mb, bevel=0.006, col="bounds", pivot=PIV_BOTTOM, note="faces -Y")
    return f


def a_towel():
    mb = MB()
    m = "Fabric_LinenWhite"
    mb.box((-0.12, -0.035, 0.6), (0.12, -0.02, 1.0), m)
    mb.box((-0.12, -0.035, 0.98), (0.12, 0.035, 1.0), m)
    mb.box((-0.12, 0.02, 0.72), (0.12, 0.035, 1.0), m)
    return dict(mb=mb, bevel=0.006, col=None, pivot="drape: centre of chair top rail at z=0.98")


# ============================================================================ tableware / food / small props
def a_plate():
    mb = MB()
    mb.lathe([(0, 0), (0.075, 0), (0.085, 0.004), (0.12, 0.018), (0.126, 0.022), (0.118, 0.023),
              (0.08, 0.01), (0, 0.01)], "Ceramic_White", 24)
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_plate_stack():
    mb = MB()
    for k in range(6):
        mb.lathe([(0, 0), (0.075, 0), (0.085, 0.004), (0.12, 0.018), (0.126, 0.022), (0.118, 0.023),
                  (0.08, 0.01), (0, 0.01)], "Ceramic_White", 24, (0, 0, k * 0.016))
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM, col="bounds")


def _handle(mb, x, z0, z1, m, side=1, t=0.012):
    """Loop handle attached at x (body surface), spanning z0..z1, bulging towards side (+1/-1)."""
    R = (z1 - z0) / 2
    a0, a1 = (-90, 90) if side > 0 else (90, 270)
    mb.tube_arc((x, 0, z0 + R), R, t / 2, a0, a1, m)


def a_mug():
    mb = MB()
    mb.lathe([(0, 0), (0.038, 0), (0.041, 0.006), (0.041, 0.095), (0.036, 0.095), (0.035, 0.012), (0, 0.012)],
             "Ceramic_White", 16)
    _handle(mb, 0.039, 0.02, 0.08, "Ceramic_White", 1, 0.013)
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_cup_saucer():
    mb = MB()
    mb.lathe([(0, 0), (0.05, 0), (0.07, 0.01), (0.075, 0.014), (0.068, 0.014), (0.05, 0.008), (0, 0.008)],
             "Ceramic_White", 20)
    mb.lathe([(0, 0.008), (0.03, 0.008), (0.045, 0.04), (0.048, 0.062), (0.044, 0.062), (0.04, 0.042),
              (0.026, 0.016), (0, 0.016)], "Ceramic_White", 16)
    _handle(mb, 0.044, 0.022, 0.056, "Ceramic_White", 1, 0.01)
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_teapot():
    mb = MB()
    c = "Ceramic_White"
    mb.lathe([(0, 0), (0.06, 0), (0.09, 0.03), (0.1, 0.07), (0.09, 0.11), (0.065, 0.135), (0.048, 0.14),
              (0.03, 0.15), (0.015, 0.17), (0.02, 0.18), (0, 0.19)], c, 20)
    mk = mb.mark()
    mb.lathe([(0.03, 0), (0.022, 0.06), (0.013, 0.13), (0.015, 0.14)], c, 10, cap0=False)
    mb.xform(mk, Tr(0.07, 0, 0.05) @ R("Y", 50))
    _handle(mb, -0.085, 0.035, 0.125, c, -1, 0.016)
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_pitcher():
    mb = MB()
    c = "Paint_Brick"
    mb.lathe([(0, 0), (0.06, 0), (0.07, 0.05), (0.068, 0.12), (0.058, 0.19), (0.062, 0.21), (0.056, 0.21),
              (0.052, 0.19), (0.058, 0.12), (0.058, 0.02), (0, 0.02)], c, 18)
    _handle(mb, -0.062, 0.05, 0.18, c, -1, 0.018)
    mb.box((0.05, -0.012, 0.19), (0.085, 0.012, 0.205), c)
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_pot():
    mb = MB()
    c = "Metal_Copper"
    mb.lathe([(0, 0), (0.1, 0), (0.105, 0.008), (0.105, 0.12), (0.098, 0.12), (0.098, 0.01), (0, 0.01)], c, 20)
    mb.box((0.105, -0.025, 0.09), (0.14, 0.025, 0.105), "Metal_Iron")
    mb.box((-0.14, -0.025, 0.09), (-0.105, 0.025, 0.105), "Metal_Iron")
    mb.lathe([(0, 0.12), (0.102, 0.12), (0.09, 0.135), (0.03, 0.15), (0.015, 0.16), (0.02, 0.17), (0, 0.172)],
             "Metal_Copper", 20)
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM, col="bounds")


def a_pan_hanging(r=0.12):
    def f():
        mb = MB()
        mk = mb.mark()
        mb.lathe([(0, 0), (r * 0.8, 0), (r, r * 0.38), (r - 0.006, r * 0.38), (r * 0.8 - 0.004, 0.006), (0, 0.006)],
                 "Metal_Copper", 22)
        mb.box((r - 0.01, -0.015, r * 0.3), (r + 0.24, 0.015, r * 0.3 + 0.012), "Metal_Copper")
        piv = Vector((r + 0.22, 0, r * 0.3))
        mb.xform(mk, R("Z", 90) @ R("Y", -90) @ Tr(-piv.x, -piv.y, -piv.z))
        return dict(mb=mb, weld=True, pivot="hanging hole", note="hang on SM_Rail_Pan_1U hooks")
    return f


def a_rail_pan():
    mb = MB()
    mb.box((0, 0, 0), (U, 0.03, 0.05), "Wood_Walnut")
    for k in range(5):
        x = 0.08 + k * (U - 0.16) / 4
        mb.box((x - 0.006, 0.03, 0.015), (x + 0.006, 0.07, 0.025), "Metal_Iron")
        mb.box((x - 0.006, 0.06, -0.03), (x + 0.006, 0.07, 0.025), "Metal_Iron")
    return dict(mb=mb, bevel=0.003, pivot=PIV_BACK)


def a_rail_herb():
    mb = MB()
    mb.box((0, 0, 0), (U, 0.025, 0.06), "Wood_Oak")
    for k in range(4):
        x = 0.12 + k * (U - 0.24) / 3
        mk = mb.mark()
        mb.lathe([(0.012, 0), (0.012, 0.06), (0.02, 0.065), (0, 0.075)], "Wood_Walnut", 10)
        mb.xform(mk, Tr(x, 0.025, 0.03) @ R("X", -90))
    return dict(mb=mb, bevel=0.003, weld=True, pivot=PIV_BACK)


def a_herb_bundle():
    mb = MB()
    mb.box((-0.004, -0.004, -0.06), (0.004, 0.004, 0), "Tape_Kraft")
    mb.cyl((0, 0, -0.1), 0.02, 0.05, "Tape_Kraft", 10)
    rng = [(0, 0, 0, 0), (0.03, 0.01, 15, 40), (-0.03, 0.0, -15, 150), (0.01, -0.03, 12, 250), (-0.01, 0.03, 10, 320)]
    for dx, dy, tilt, rot in rng:
        mk = mb.mark()
        mb.lathe([(0, -0.3), (0.025, -0.27), (0.05, -0.17), (0.035, -0.08), (0.01, -0.02), (0.004, 0)],
                 "Leaf_Green", 10)
        mb.xform(mk, Tr(dx, dy, -0.08) @ R("Z", rot) @ R("X", tilt))
    return dict(mb=mb, weld=True, pivot="hanging point (top)")


def a_utensil_crock():
    mb = MB()
    mb.lathe([(0, 0), (0.055, 0), (0.06, 0.14), (0.052, 0.14), (0.048, 0.012), (0, 0.012)], "Ceramic_White", 16)
    for ang, dx in ((8, -0.02), (-6, 0.02), (14, 0.0)):
        mk = mb.mark()
        mb.box((-0.006, -0.004, 0.01), (0.006, 0.004, 0.24), "Wood_Oak")
        mb.lathe([(0, 0), (0.02, 0.01), (0.022, 0.04), (0, 0.06)], "Wood_Oak", 8, (0, 0, 0.23))
        mb.xform(mk, Tr(dx, 0, 0) @ R("Y", ang) @ R("Z", ang * 7))
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_canister(r, h):
    def f():
        mb = MB()
        mb.lathe([(0, 0), (r, 0), (r, h), (r * 0.9, h)], "Enamel_Cream", 18, cap1=True)
        mb.lathe([(r * 1.03, h), (r * 1.03, h + 0.025), (r * 0.3, h + 0.03), (r * 0.25, h + 0.05),
                  (0, h + 0.055)], "Wood_Oak", 18)
        return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)
    return f


def a_coffee_maker():
    mb = MB()
    i = "Metal_Iron"
    mb.box((-0.09, -0.1, 0), (0.09, 0.1, 0.03), i)
    mb.box((-0.09, -0.1, 0.03), (0.09, -0.02, 0.33), i)
    mb.box((-0.09, -0.1, 0.26), (0.09, 0.09, 0.33), i)
    mb.lathe([(0, 0.03), (0.055, 0.03), (0.065, 0.08), (0.05, 0.16), (0.04, 0.17), (0, 0.17)],
             "Glass_Clear", 16, (0, 0.035, 0))
    mb.lathe([(0, 0.035), (0.05, 0.035), (0.058, 0.08), (0, 0.1)], "Wood_Walnut", 16, (0, 0.035, 0))
    return dict(mb=mb, bevel=0.005, weld=False, pivot=PIV_BOTTOM)


def a_bottle(mat):
    def f():
        mb = MB()
        mb.lathe([(0, 0), (0.03, 0), (0.033, 0.015), (0.033, 0.12), (0.022, 0.15), (0.014, 0.16), (0, 0.16)], mat, 16)
        mb.lathe([(0, 0.155), (0.016, 0.155), (0.016, 0.18), (0.006, 0.19), (0, 0.2)], "Ceramic_White", 12)
        return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)
    return f


def a_cutting_board():
    mb = MB()
    mb.box((-0.18, -0.12, 0), (0.18, 0.12, 0.022), "Wood_Oak")
    mb.box((0.18, -0.035, 0), (0.27, 0.035, 0.022), "Wood_Oak")
    return dict(mb=mb, bevel=0.008, pivot=PIV_BOTTOM)


def a_bread_loaf(scale=1.9):
    def f():
        mb = MB()
        mk = mb.mark()
        mb.lathe([(0, 0), (0.06, 0), (0.075, 0.02), (0.072, 0.05), (0.05, 0.076), (0.02, 0.085), (0, 0.086)],
                 "Bread_Crust", 16)
        mb.xform(mk, S(scale, 1, 1))
        return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)
    return f


def a_bread_roll():
    mb = MB()
    mk = mb.mark()
    mb.lathe([(0, 0), (0.03, 0), (0.042, 0.015), (0.038, 0.035), (0.02, 0.048), (0, 0.05)], "Bread_Crust", 12)
    mb.xform(mk, S(1.35, 1, 1))
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_bread_basket():
    mb = MB()
    mk = mb.mark()
    mb.lathe([(0, 0), (0.1, 0), (0.13, 0.06), (0.135, 0.07), (0.125, 0.07), (0.095, 0.012), (0, 0.012)],
             "Wicker", 20)
    mb.xform(mk, S(1.35, 1, 1))
    for dx, dy, rz in ((-0.06, 0.0, 10), (0.06, 0.01, -20), (0.0, -0.02, 80)):
        mk = mb.mark()
        mb.lathe([(0, 0), (0.03, 0), (0.042, 0.015), (0.038, 0.035), (0.02, 0.048), (0, 0.05)], "Bread_Crust", 12)
        mb.xform(mk, Tr(dx, dy, 0.02) @ R("Z", rz) @ S(1.35, 1, 1))
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_salt():
    mb = MB()
    mb.lathe([(0, 0), (0.018, 0), (0.02, 0.05), (0.014, 0.065), (0, 0.07)], "Ceramic_White", 12)
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_plant():
    mb = MB()
    mb.lathe([(0, 0), (0.06, 0), (0.08, 0.13), (0.088, 0.13), (0.088, 0.155), (0.078, 0.155), (0.072, 0.14),
              (0, 0.14)], "Terracotta", 18)
    mb.cyl((0, 0, 0.14), 0.074, 0.005, "Soil_Dark", 18)
    for k in range(9):
        mk = mb.mark()
        L = 0.16 + 0.05 * ((k * 7) % 3)
        mb.lathe([(0, 0), (0.025, L * 0.25), (0.022, L * 0.7), (0, L)], "Leaf_Green", 8)
        mb.xform(mk, Tr(0, 0, 0.14) @ R("Z", k * 40) @ R("X", 20 + (k % 3) * 18) @ S(0.3, 1, 1))
    return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)


def a_calendar():
    mb = MB()
    w, h = 0.3, 0.4
    mb.quad_uv([(-w / 2, 0.006, 0), (w / 2, 0.006, 0), (w / 2, 0.006, h), (-w / 2, 0.006, h)], "Calendar_Print",
               [(0, 0), (1, 0), (1, 1), (0, 1)])
    mb.box((-w / 2, 0, 0), (w / 2, 0.006, h), "Paper_Cream", faces=["-y", "+z", "-z", "+x", "-x"])
    mb.box((-0.004, 0, h + 0.01), (0.004, 0.012, h + 0.03), "Metal_Iron")
    return dict(mb=mb, pivot="back-bottom-centre (wall mounted)")


def a_note():
    mb = MB()
    w, h = 0.1, 0.12
    mb.quad_uv([(-w / 2, 0.002, 0), (w / 2, 0.002, 0), (w / 2, 0.002, h), (-w / 2, 0.002, h)], "Note_Paper",
               [(0, 0), (1, 0), (1, 1), (0, 1)])
    mb.box((-w / 2, 0, 0), (w / 2, 0.002, h), "Paper_Cream", faces=["-y", "+z", "-z", "+x", "-x"])
    mk = mb.mark()
    mb.cyl((0, 0, 0), 0.012, 0.008, "Plastic_Red", 10)
    mb.xform(mk, Tr(0, 0.002, h - 0.015) @ R("X", -90))
    return dict(mb=mb, weld=True, pivot="back-bottom-centre (fridge / wall)")


# ============================================================================ pantry / storage
def a_shelf():
    mb = MB()
    w, d, h = U, 0.4, 2.2
    m = "Wood_Oak"
    mb.box((0, 0, 0), (0.03, d, h), m)
    mb.box((w - 0.03, 0, 0), (w, d, h), m)
    for z in (0.06, 0.48, 0.9, 1.32, 1.74, 2.14):
        mb.box((0.03, 0, z), (w - 0.03, d, z + 0.035), m)
    mb.box((0.03, d - 0.03, 0), (w - 0.03, d, 0.06), m)
    mb.box((0.03, 0, 1.0), (w - 0.03, 0.015, 1.1), m)
    return dict(mb=mb, bevel=0.004, col=[((0, 0, 0), (w, d, h))], pivot=PIV_BACK, grid=(1, 0.5),
                shelf_z=[0.095, 0.515, 0.935, 1.355, 1.775, 2.175])


def a_shelf_corner():
    mb = MB()
    d, h = 0.4, 2.2
    m = "Wood_Oak"
    for z in (0.06, 0.48, 0.9, 1.32, 1.74, 2.14):
        mb.box((0, 0, z), (d, d, z + 0.035), m)
    mb.box((0, d - 0.03, 0), (0.03, d, h), m)
    return dict(mb=mb, bevel=0.004, col=[((0, 0, 0), (d, d, h))], pivot=PIV_BACK, grid=(0.5, 0.5))


def a_jar(r, h, fill_mat, lid_mat, fill=0.8):
    def f():
        mb = MB()
        mb.lathe([(0, 0), (r, 0), (r, h * 0.84), (r * 0.82, h * 0.93), (r * 0.82, h)], "Glass_Clear", 16, cap1=False)
        mb.lathe([(0, 0.004), (r - 0.004, 0.004), (r - 0.004, h * fill)], fill_mat, 16)
        mb.lathe([(r * 0.86, h - 0.004), (r * 0.86, h + 0.018), (r * 0.8, h + 0.022), (0, h + 0.022)], lid_mat, 16,
                 cap0=True)
        return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)
    return f


def a_can(label):
    def f():
        mb = MB()
        mb.lathe([(0, 0), (0.038, 0), (0.04, 0.006), (0.04, 0.104), (0.038, 0.11), (0, 0.11)], "Metal_Steel", 18)
        mb.lathe([(0.0405, 0.018), (0.0405, 0.092)], label, 18, cap0=False, cap1=False)
        return dict(mb=mb, weld=True, pivot=PIV_BOTTOM)
    return f


def a_crate(w, d, h, name_low=False):
    def f():
        mb = MB()
        m = "Wood_Crate"
        t = 0.018
        mb.box((-w / 2, -d / 2, 0), (w / 2, d / 2, t), m)
        n = 2 if h < 0.25 else 3
        gap = 0.02
        sh = (h - t - gap * (n - 1)) / n
        for k in range(n):
            z0 = t + k * (sh + gap)
            mb.box((-w / 2, -d / 2, z0), (w / 2, -d / 2 + t, z0 + sh), m)
            mb.box((-w / 2, d / 2 - t, z0), (w / 2, d / 2, z0 + sh), m)
            mb.box((-w / 2, -d / 2 + t, z0), (-w / 2 + t, d / 2 - t, z0 + sh), m)
            mb.box((w / 2 - t, -d / 2 + t, z0), (w / 2, d / 2 - t, z0 + sh), m)
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * (w / 2 - 0.02), sy * (d / 2 - 0.02)
                mb.box((x - 0.02, y - 0.02, 0), (x + 0.02, y + 0.02, h), m)
        mb.box((-0.02, -d / 2 - 0.012, t), (0.02, -d / 2, h), m)
        mb.box((-0.02, d / 2, t), (0.02, d / 2 + 0.012, h), m)
        return dict(mb=mb, bevel=0.003, col="bounds", pivot=PIV_BOTTOM)
    return f


def a_sack(sc=1.0):
    def f():
        mb = MB()
        mk = mb.mark()
        p = [(0, 0), (0.15, 0.005), (0.19, 0.08), (0.2, 0.2), (0.16, 0.31), (0.07, 0.37), (0.035, 0.395),
             (0.05, 0.43), (0.06, 0.46), (0.03, 0.47), (0, 0.47)]
        mb.lathe([(r * sc, z * sc) for r, z in p], "Burlap", 16)
        mb.lathe([(0.04 * sc, 0.38 * sc), (0.042 * sc, 0.4 * sc)], "Tape_Kraft", 12, cap0=False, cap1=False)
        mb.xform(mk, S(1.1, 0.9, 1))
        return dict(mb=mb, weld=True, col="bounds", pivot=PIV_BOTTOM)
    return f


def a_basket_round():
    mb = MB()
    mb.lathe([(0, 0), (0.17, 0), (0.21, 0.22), (0.225, 0.23), (0.225, 0.25), (0.2, 0.25), (0.185, 0.025),
              (0, 0.025)], "Wicker", 24)
    return dict(mb=mb, weld=True, col="bounds", pivot=PIV_BOTTOM)


def a_basket_rect():
    mb = MB()
    w, d, h, t = 0.5, 0.36, 0.2, 0.02
    m = "Wicker"
    mb.box((-w / 2, -d / 2, 0), (w / 2, d / 2, t), m)
    mb.box((-w / 2, -d / 2, t), (w / 2, -d / 2 + t, h), m)
    mb.box((-w / 2, d / 2 - t, t), (w / 2, d / 2, h), m)
    mb.box((-w / 2, -d / 2 + t, t), (-w / 2 + t, d / 2 - t, h), m)
    mb.box((w / 2 - t, -d / 2 + t, t), (w / 2, d / 2 - t, h), m)
    mb.box((-w / 2 - 0.01, -d / 2 - 0.01, h - 0.02), (w / 2 + 0.01, d / 2 + 0.01, h + 0.005), m)
    return dict(mb=mb, bevel=0.006, col="bounds", pivot=PIV_BOTTOM)


def a_cloth_stack(mat, n=4):
    def f():
        mb = MB()
        for k in range(n):
            mk = mb.mark()
            mb.box((-0.19, -0.14, 0), (0.19, 0.14, 0.055), mat)
            mb.xform(mk, Tr(0.01 * ((k * 3) % 3 - 1), 0.008 * ((k * 5) % 3 - 1), k * 0.056) @ R("Z", (k % 2) * 3 - 1.5))
        return dict(mb=mb, bevel=0.018, bevel_seg=3, col="bounds", pivot=PIV_BOTTOM)
    return f


def a_book_stack():
    mb = MB()
    specs = [("Paint_Teal", 0.24, 0.17, 0.035, 0), ("Paint_Brick", 0.22, 0.16, 0.03, 6), ("Paint_Sage", 0.23, 0.155, 0.04, -4)]
    z = 0
    for mat, w, d, h, rot in specs:
        mk = mb.mark()
        mb.box((-w / 2, -d / 2, 0), (w / 2, d / 2, h), mat)
        mb.box((-w / 2 + 0.005, -d / 2 + 0.003, 0.004), (w / 2 - 0.003, d / 2 - 0.003, h - 0.004), "Paper_Cream")
        mb.box((-w / 2, -d / 2, 0), (-w / 2 + 0.006, d / 2, h), mat)
        mb.xform(mk, Tr(0, 0, z) @ R("Z", rot))
        z += h
    return dict(mb=mb, bevel=0.002, pivot=PIV_BOTTOM)


def a_cardboard(w, d, h):
    def f():
        mb = MB()
        mb.box((-w / 2, -d / 2, 0), (w / 2, d / 2, h), "Cardboard")
        mb.box((-w / 2 - 0.002, -0.004, h - 0.001), (w / 2 + 0.002, 0.004, h + 0.002), "Metal_Iron")
        mb.box((-w / 2 - 0.003, -0.035, h - 0.1), (w / 2 + 0.003, 0.035, h + 0.003), "Tape_Kraft",
               faces=["+z", "-x", "+x"])
        return dict(mb=mb, bevel=0.008, col="bounds", pivot=PIV_BOTTOM)
    return f


# ============================================================================ registry
CATEGORIES = [
    ("01_Floors", [
        ("SM_Floor_Checker_1x1", a_floor("Floor_Checker")),
        ("SM_Floor_PlankGrey_1x1", a_floor("Floor_PlankGrey")),
        ("SM_Foundation_1x1", a_foundation),
        ("SM_Rug_Runner_1x3", a_rug),
    ]),
    ("02_Walls", [
        ("SM_Wall_1x3", a_wall),
        ("SM_Wall_1x3_CornerL", a_wall_corner_l),
        ("SM_Wall_1x3_CornerR", a_wall_corner_r),
        ("SM_Wall_05x3", a_wall_half_width),
        ("SM_Wall_Door_1x3", a_wall_door),
        ("SM_Wall_Window_1x3", a_wall_window),
        ("SM_Wall_Doorway_2x3", a_wall_doorway),
        ("SM_Wall_Low_1x05", a_wall_half),
        ("SM_Wall_OuterPost", a_wall_post),
    ]),
    ("03_Doors_Windows", [
        ("SM_DoorFrame_1x3", a_doorframe),
        ("SM_Door_4Panel", a_door),
        ("SM_DoorFrame_Wide_2x3", a_doorframe_wide),
        ("SM_Window_Frame_1x3", a_window_frame),
        ("SM_Window_Glass_1x3", a_window_glass),
        ("SM_Curtain_Rod_1U", a_curtain_rod),
        ("SM_Curtain_Panel", a_curtain),
    ]),
    ("04_Kitchen_Furniture", [
        ("SM_Cabinet_Base_Door_05", a_cab_door),
        ("SM_Cabinet_Base_Drawers_05", a_cab_drawers),
        ("SM_Cabinet_Base_Corner_1x1", a_cab_corner),
        ("SM_Cabinet_Base_Sink_1", a_cab_sink),
        ("SM_Cabinet_Wall_05", a_cab_wall),
        ("SM_Stove_05", a_stove),
        ("SM_Fridge", a_fridge),
    ]),
    ("05_Dining", [
        ("SM_Table_Dining", a_table),
        ("SM_Chair_Sage", a_chair("Paint_Sage")),
        ("SM_Chair_Brick", a_chair("Paint_Brick")),
        ("SM_Chair_Walnut", a_chair("Wood_Walnut")),
        ("SM_Towel_Draped", a_towel),
    ]),
    ("06_Kitchen_Props", [
        ("SM_Plate", a_plate),
        ("SM_Plate_Stack", a_plate_stack),
        ("SM_Mug", a_mug),
        ("SM_Cup_Saucer", a_cup_saucer),
        ("SM_Teapot", a_teapot),
        ("SM_Pitcher_Red", a_pitcher),
        ("SM_Pot_Copper", a_pot),
        ("SM_Pan_Copper_S", a_pan_hanging(0.1)),
        ("SM_Pan_Copper_L", a_pan_hanging(0.13)),
        ("SM_Rail_Pan", a_rail_pan),
        ("SM_Rail_Herb", a_rail_herb),
        ("SM_Herb_Bundle", a_herb_bundle),
        ("SM_Utensil_Crock", a_utensil_crock),
        ("SM_Canister_S", a_canister(0.055, 0.1)),
        ("SM_Canister_M", a_canister(0.07, 0.14)),
        ("SM_Canister_L", a_canister(0.085, 0.19)),
        ("SM_Coffee_Maker", a_coffee_maker),
        ("SM_Bottle_Ketchup", a_bottle("Plastic_Red")),
        ("SM_Bottle_Mustard", a_bottle("Plastic_Yellow")),
        ("SM_Salt_Shaker", a_salt),
        ("SM_Cutting_Board", a_cutting_board),
        ("SM_Bread_Loaf", a_bread_loaf()),
        ("SM_Bread_Roll", a_bread_roll),
        ("SM_Bread_Basket", a_bread_basket),
        ("SM_Plant_Potted", a_plant),
        ("SM_Calendar", a_calendar),
        ("SM_Note_Paper", a_note),
    ]),
    ("07_Pantry_Storage", [
        ("SM_Shelf_Pantry_1U", a_shelf),
        ("SM_Shelf_Pantry_Corner", a_shelf_corner),
        ("SM_Crate_Wood", a_crate(0.6, 0.45, 0.34)),
        ("SM_Crate_Wood_Low", a_crate(0.55, 0.4, 0.2)),
        ("SM_Box_Cardboard_L", a_cardboard(0.62, 0.46, 0.44)),
        ("SM_Box_Cardboard_M", a_cardboard(0.46, 0.4, 0.34)),
        ("SM_Sack_Burlap", a_sack(1.0)),
        ("SM_Sack_Burlap_S", a_sack(0.7)),
        ("SM_Basket_Wicker_Round", a_basket_round),
        ("SM_Basket_Wicker_Rect", a_basket_rect),
        ("SM_Cloth_Stack_Charcoal", a_cloth_stack("Fabric_Charcoal")),
        ("SM_Cloth_Stack_Linen", a_cloth_stack("Fabric_LinenWhite", 3)),
        ("SM_Book_Stack", a_book_stack),
    ]),
    ("08_Pantry_Jars", [
        (f"SM_Jar_{sz}_{fl}", a_jar(r, h, "Preserve_" + fl, lid))
        for sz, r, h in (("S", 0.035, 0.08), ("M", 0.045, 0.12), ("L", 0.058, 0.17))
        for fl, lid in (("Berry", "Metal_Copper"), ("Plum", "Paint_Lavender"), ("Pickle", "Metal_Steel"),
                        ("Honey", "Paint_Teal"))
    ] + [
        ("SM_Can_Tin_Teal", a_can("Paint_Teal")),
        ("SM_Can_Tin_Lavender", a_can("Paint_Lavender")),
    ]),
]
