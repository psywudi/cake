"""
Build CozyKitchen_Modular.blend

  python build_scene.py            (with the `bpy` module installed: pip install bpy)
  blender -b -P build_scene.py     (or from a Blender install)

Options (after `--`):  --no-render   skip the preview renders
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import kit  # noqa: E402
from kit import U, H, T, MB, build, ucx, ucx_bounds, get_coll, M  # noqa: E402
import assets as A  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TEX = os.path.join(ROOT, "Textures")
BLEND = os.path.join(ROOT, "CozyKitchen_Modular.blend")
PREVIEW_DIR = os.path.join(ROOT, "Previews")
DO_RENDER = "--no-render" not in sys.argv

LIB = {}          # asset name -> object
LIB_SPEC = {}


# ============================================================================ scene setup
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.length_unit = "METERS"
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)   # so '//' relative texture paths resolve


def build_library():
    lib_root = get_coll("00_Library")
    for cat, items in A.CATEGORIES:
        coll = get_coll(cat, lib_root)
        for name, fn in items:
            spec = fn()
            props = {"asset_category": cat, "pivot": spec.get("pivot", "")}
            if spec.get("grid"):
                props["grid_size_u"] = "x".join(str(g) for g in spec["grid"])
            if spec.get("note"):
                props["note"] = spec["note"]
            if spec.get("socket"):
                props["socket_type"] = spec["socket"]
            obj = build(name, spec["mb"], coll, TEX, bevel=spec.get("bevel", 0.0),
                        bevel_seg=spec.get("bevel_seg", 2), weld=spec.get("weld", False), props=props)
            col = spec.get("col")
            if col == "bounds":
                ucx_bounds(obj, coll)
            elif col:
                ucx(obj, col, coll)
            LIB[name] = obj
            LIB_SPEC[name] = spec
            print("built", name, len(obj.data.polygons), "faces")


# ============================================================================ layout
LABEL_MAT = None


GROUND = -0.35   # top of the preview ground plane (= bottom of SM_Foundation_1x1)


def label(text, loc, size, coll, align="CENTER", rz=180.0):
    global LABEL_MAT
    if LABEL_MAT is None:
        LABEL_MAT = bpy.data.materials.new("M_EditorLabel")
        LABEL_MAT.diffuse_color = (0.12, 0.1, 0.12, 1)
        try:
            LABEL_MAT.use_nodes = True
        except Exception:
            pass
        LABEL_MAT.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.08, 0.06, 0.08, 1)
    cu = bpy.data.curves.new("LBL_" + text, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = align
    cu.materials.append(LABEL_MAT)
    o = bpy.data.objects.new("LBL_" + text, cu)
    o.location = loc
    o.rotation_euler = (0, 0, math.radians(rz))
    coll.objects.link(o)
    return o


def layout_library():
    """Rows read left->right as seen from CAM_Library (which looks toward -Y, so
    'right' on screen is world -X and 'down' on screen is world +Y).
    Fronts of wall modules / cabinets (+Y) therefore face the camera."""
    lbl = get_coll("99_Labels")
    GAP, ROW_W, CHAR = 0.3, 14.0, 0.043
    row_top = 0.0
    width = 0.0
    for cat, items in A.CATEGORIES:
        names = [n for n, _ in items]
        rows, cur, w = [], [], 0.0
        for n in names:
            a, b = kit.bbox_local(LIB[n])
            slot = max(b[0] - a[0], len(n.replace("SM_", "")) * CHAR) + GAP
            if cur and w + slot > ROW_W:
                rows.append(cur)
                cur, w = [], 0.0
            cur.append((n, slot))
            w += slot
        rows.append(cur)
        title = cat.split("_", 1)[1].replace("_", " ")
        for row in rows:
            depth = max(kit.bbox_local(LIB[n])[1][1] - kit.bbox_local(LIB[n])[0][1] for n, _ in row)
            height = max(kit.bbox_local(LIB[n])[1][2] - kit.bbox_local(LIB[n])[0][2] for n, _ in row)
            row_top += height * 0.62      # tall items would otherwise cover the row behind them in CAM_Library
            if title:
                label(title, (0.4, row_top + 0.2, GROUND + 0.002), 0.2, lbl, "RIGHT")
                title = None
            x = 0.0
            for n, slot in row:
                a, b = kit.bbox_local(LIB[n])
                cx = -(x + slot / 2)                          # screen-right = world -X
                LIB[n].location = (cx - (a[0] + b[0]) / 2, row_top - a[1], GROUND - a[2])
                label(n.replace("SM_", ""), (cx, row_top + depth + 0.14, GROUND + 0.002), 0.07, lbl)
                x += slot
                width = max(width, x)
            row_top += depth + 0.6
        row_top += 0.35
    return width, row_top


# ============================================================================ prefabs
def inst(name, coll, parent, local):
    src = LIB[name]
    o = src.copy()
    o.parent = parent
    o.matrix_parent_inverse = Matrix.Identity(4)
    o.matrix_basis = local
    coll.objects.link(o)
    for ch in src.children:
        c = ch.copy()
        c.parent = o
        coll.objects.link(c)
    return o


class Room:
    def __init__(self, name, nx, ny, loc, parent_coll):
        self.name, self.nx, self.ny = name, nx, ny
        self.coll = get_coll("PF_" + name, parent_coll)
        self.c_struct = get_coll(f"PF_{name}_Structure", self.coll)
        self.c_cut = get_coll(f"PF_{name}_CutawayWalls", self.coll)
        self.c_props = get_coll(f"PF_{name}_Props", self.coll)
        self.c_gp = get_coll(f"PF_{name}_Gameplay", self.coll)
        self.root = bpy.data.objects.new("PF_" + name, None)
        self.root.empty_display_type = "PLAIN_AXES"
        self.root.empty_display_size = 0.5
        self.root.location = loc
        self.root["prefab"] = True
        self.root["room_id"] = name
        self.root["size_u"] = f"{nx}x{ny}"
        self.root["grid_m"] = U
        self.coll.objects.link(self.root)
        self.connectors = []

    # wall frames: origin, direction, rotation
    def frame(self, side, a=0.0):
        nx, ny = self.nx * U, self.ny * U
        o, d, rz = {
            "S": ((0, 0), (1, 0), 0),
            "N": ((nx, ny), (-1, 0), 180),
            "W": ((0, ny), (0, -1), -90),
            "E": ((nx, 0), (0, 1), 90),
        }[side]
        return Matrix.Translation(Vector((o[0] + d[0] * a, o[1] + d[1] * a, 0))) @ Matrix.Rotation(math.radians(rz), 4, "Z")

    def on_wall(self, name, side, a, off=(0, 0, 0), coll=None, rz=0.0):
        m = self.frame(side, a) @ Matrix.Translation(Vector(off)) @ Matrix.Rotation(math.radians(rz), 4, "Z")
        return inst(name, coll or self.c_props, self.root, m)

    def at(self, name, x, y, z=0.0, rz=0.0, coll=None, s=None):
        m = Matrix.Translation(Vector((x, y, z))) @ Matrix.Rotation(math.radians(rz), 4, "Z")
        if s:
            m = m @ Matrix.Diagonal(Vector((s, s, s, 1)))
        return inst(name, coll or self.c_props, self.root, m)

    def walls(self, side, modules, cutaway=False):
        for k, name in modules:
            self.on_wall(name, side, k * U, coll=self.c_cut if cutaway else self.c_struct)

    def floors(self, tile):
        for i in range(self.nx):
            for j in range(self.ny):
                self.at(tile, i * U, j * U, coll=self.c_struct)
                self.at("SM_Foundation_1x1", i * U, j * U, coll=self.c_struct)

    def connector(self, side, k, conn_type, width_u, open_w, open_h):
        cx = width_u * U / 2
        base = self.frame(side, k * U) @ Matrix.Translation(Vector((cx, 0, 0)))
        idx = len(self.connectors)
        e = bpy.data.objects.new(f"CONN_{self.name}_{idx:02d}", None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.8
        e.parent = self.root
        e.matrix_basis = base @ Matrix.Rotation(math.radians(90), 4, "X")   # arrow (+Z) -> outward (-Y)
        e["connector"] = True
        e["conn_type"] = conn_type
        e["width_u"] = width_u
        e["room_id"] = self.name
        e["rule"] = "align: other connector position equal, forward opposite; same conn_type only"
        self.c_gp.objects.link(e)
        mb = MB()
        mb.box((-open_w / 2, -0.05, 0), (open_w / 2, 0.9, open_h), None)
        me = bpy.data.meshes.new(f"TRG_{self.name}_{idx:02d}")
        me.from_pydata(mb.V, [], mb.F)
        t = bpy.data.objects.new(me.name, me)
        t.parent = self.root
        t.matrix_basis = base
        t.display_type = "WIRE"
        t.hide_render = True
        t["trigger"] = True
        t["connector"] = e.name
        t["on_enter"] = "spawn_or_load_neighbour_room"
        self.c_gp.objects.link(t)
        self.connectors.append(e.name)
        return e

    def bounds(self):
        mb = MB()
        mb.box((0, 0, 0), (self.nx * U, self.ny * U, H), None)
        me = bpy.data.meshes.new(f"BOUNDS_{self.name}")
        me.from_pydata(mb.V, [], mb.F)
        b = bpy.data.objects.new(me.name, me)
        b.parent = self.root
        b.display_type = "BOUNDS"
        b.hide_render = True
        b["room_bounds"] = True
        b["use"] = "overlap test before placing a generated room"
        self.c_gp.objects.link(b)
        self.root["connectors"] = ",".join(self.connectors)


def corner_run(n):
    """Wall modules for a full side of n cells: mitred corners at both ends."""
    return [(0, "SM_Wall_1x3_CornerL")] + [(k, "SM_Wall_1x3") for k in range(1, n - 1)] + \
        [(n - 1, "SM_Wall_1x3_CornerR")]


def with_openings(n, openings):
    """openings: {k: (asset, width)} -> module list for one side (corners at both ends)."""
    mods, k = [], 0
    while k < n:
        if k in openings:
            name, w = openings[k]
            mods.append((k, name))
            k += w
            continue
        mods.append((k, "SM_Wall_1x3_CornerL" if k == 0 else "SM_Wall_1x3_CornerR" if k == n - 1 else "SM_Wall_1x3"))
        k += 1
    return mods


def build_kitchen(loc, pc):
    nx, ny = 7, 6
    r = Room("Kitchen", nx, ny, loc, pc)
    W_, N_ = nx * U, ny * U
    r.floors("SM_Floor_Checker_1x1")
    # ---- walls (k = cell index along the side's local +X)
    r.walls("S", corner_run(nx), cutaway=True)
    for k in range(nx):
        r.on_wall("SM_Wall_Low_1x05", "S", k, coll=r.c_struct)
    r.walls("N", with_openings(nx, {2: ("SM_Wall_Window_1x3", 1)}))          # window over the sink (x 4..5)
    r.walls("W", with_openings(ny, {4: ("SM_Wall_Door_1x3", 1)}))            # exterior door (y 1..2)
    r.walls("E", with_openings(ny, {3: ("SM_Wall_Doorway_2x3", 2)}))         # doorway to pantry (y 3..5)
    # ---- openings
    r.on_wall("SM_DoorFrame_1x3", "W", 4, coll=r.c_struct)
    r.on_wall("SM_Door_4Panel", "W", 4, off=(A.DOOR["x0"] + 0.04, T - 0.05, 0), coll=r.c_struct)
    r.on_wall("SM_DoorFrame_Wide_2x3", "E", 3, coll=r.c_struct)
    r.on_wall("SM_Window_Frame_1x3", "N", 2, coll=r.c_struct)
    r.on_wall("SM_Window_Glass_1x3", "N", 2, coll=r.c_struct)
    r.on_wall("SM_Curtain_Rod_1U", "N", 2)
    r.on_wall("SM_Curtain_Panel", "N", 2, off=(0.0, T + 0.12, 2.39))
    r.on_wall("SM_Curtain_Panel", "N", 2, off=(U, T + 0.12, 2.39))

    def north(x0, name, w, z=0.0):
        return r.on_wall(name, "N", W_ - (x0 + w), off=(0, T, z))

    def west(y0, name, w, z=0.0):
        return r.on_wall(name, "W", N_ - (y0 + w), off=(0, T, z))

    # ---- north run (x in metres, all on 0.5 m grid lines)
    north(0.0, "SM_Cabinet_Base_Corner_1x1", 1.0)
    for x, n in ((1.0, "SM_Cabinet_Base_Door_05"), (1.5, "SM_Cabinet_Base_Drawers_05"),
                 (2.0, "SM_Cabinet_Base_Door_05"), (2.5, "SM_Cabinet_Base_Door_05"),
                 (3.0, "SM_Cabinet_Base_Drawers_05"), (3.5, "SM_Cabinet_Base_Door_05"),
                 (5.0, "SM_Cabinet_Base_Door_05"), (5.5, "SM_Cabinet_Base_Drawers_05")):
        north(x, n, 0.5)
    north(4.0, "SM_Cabinet_Base_Sink_1", 1.0)
    fridge = north(6.0, "SM_Fridge", 0.8)
    for x in (0.5, 1.0, 1.5):
        north(x, "SM_Cabinet_Wall_05", 0.5, 1.45)
    # ---- west run
    west(4.5, "SM_Stove_05", 0.5)
    west(4.0, "SM_Cabinet_Base_Drawers_05", 0.5)
    west(4.0, "SM_Rail_Pan", 1.0, 1.6)
    west(3.0, "SM_Rail_Herb", 1.0, 2.1)
    r.on_wall("SM_Calendar", "W", N_ - 2.55, off=(0, T, 1.25))
    for k, n in ((0, "SM_Pan_Copper_S"), (1, "SM_Pan_Copper_L"), (2, "SM_Pan_Copper_S"), (3, "SM_Pan_Copper_L")):
        hx = 0.08 + k * (1.0 - 0.16) / 4
        r.on_wall(n, "W", N_ - 5.0, off=(hx, T + 0.065, 1.6 - 0.025))
    for k in range(4):
        px = 0.12 + k * (1.0 - 0.24) / 3
        r.on_wall("SM_Herb_Bundle", "W", N_ - 4.0, off=(px, T + 0.085, 2.1 + 0.02))
    r.on_wall("SM_Herb_Bundle", "N", W_ - 3.75, off=(0, T + 0.03, 2.2))
    # ---- counter clutter (counter top z = 0.9)
    cz = 0.9
    y_n = N_ - T - 0.3
    x_w = T + 0.3
    r.at("SM_Coffee_Maker", 1.3, y_n, cz, 180)
    r.at("SM_Canister_L", 1.8, y_n + 0.05, cz)
    r.at("SM_Canister_M", 2.05, y_n + 0.08, cz)
    r.at("SM_Canister_S", 2.25, y_n + 0.1, cz)
    r.at("SM_Teapot", 2.65, y_n - 0.05, cz, 200)
    r.at("SM_Cutting_Board", 3.25, y_n - 0.05, cz, 180)
    r.at("SM_Bread_Loaf", 3.2, y_n - 0.05, cz + 0.022, 170)
    r.at("SM_Bottle_Ketchup", 0.7, y_n + 0.1, cz)
    r.at("SM_Bottle_Mustard", 0.8, y_n + 0.12, cz)
    r.at("SM_Bread_Basket", 0.45, y_n - 0.1, cz, 45)
    r.at("SM_Mug", 5.3, y_n - 0.05, cz, 30)
    r.at("SM_Utensil_Crock", 5.75, y_n + 0.05, cz)
    r.at("SM_Canister_M", 0.75, N_ - T - 0.17, 2.19)
    r.at("SM_Canister_L", 1.25, N_ - T - 0.17, 2.19)
    r.at("SM_Pot_Copper", x_w, 4.63, cz + 0.024)
    r.at("SM_Pot_Copper", x_w + 0.05, 4.88, cz + 0.024, 30, s=0.75)
    r.at("SM_Plate_Stack", x_w, 4.2, cz)
    r.at("SM_Salt_Shaker", x_w + 0.05, 4.42, cz)
    fm = fridge.matrix_basis
    inst("SM_Plant_Potted", r.c_props, r.root, fm @ M((0.35, 0.3, 1.85)))
    for x, z in ((0.2, 1.55), (0.45, 1.45), (0.3, 1.0), (0.58, 0.85), (0.25, 0.6)):
        inst("SM_Note_Paper", r.c_props, r.root, fm @ M((x, 0.69, z)))
    # ---- dining
    tx, ty = 3.5, 2.6
    r.at("SM_Table_Dining", tx, ty)
    chairs = ["SM_Chair_Brick", "SM_Chair_Sage", "SM_Chair_Walnut", "SM_Chair_Sage"]
    for i, dx in enumerate((-0.9, -0.3, 0.3, 0.9)):
        c1 = r.at(chairs[i], tx + dx, ty + 0.62, 0, 0)
        r.at(chairs[(i + 1) % 4], tx + dx, ty - 0.62, 0, 180)
        if i == 1:
            inst("SM_Towel_Draped", r.c_props, r.root, c1.matrix_basis @ M((0, 0.18, -0.02)))
    ce = r.at("SM_Chair_Brick", tx + 1.55, ty, 0, -90)
    inst("SM_Towel_Draped", r.c_props, r.root, ce.matrix_basis @ M((0, 0.18, -0.02)))
    tz = 0.78
    for dx in (-0.9, -0.3, 0.3, 0.9):
        for sy in (1, -1):
            r.at("SM_Plate", tx + dx, ty + sy * 0.3, tz)
            r.at("SM_Mug" if (dx > 0) ^ (sy > 0) else "SM_Cup_Saucer", tx + dx + 0.2, ty + sy * 0.36, tz, sy * 70)
    r.at("SM_Plate", tx + 1.08, ty, tz)
    for dx, dy, rz in ((-0.9, 0.3, 20), (0.3, -0.3, 80), (0.9, 0.3, -30)):
        r.at("SM_Bread_Roll", tx + dx, ty + dy, tz + 0.01, rz)
    r.at("SM_Cutting_Board", tx - 0.15, ty, tz, 10)
    r.at("SM_Bread_Loaf", tx - 0.15, ty, tz + 0.022, 5)
    r.at("SM_Teapot", tx + 0.35, ty + 0.02, tz, 150)
    r.at("SM_Pitcher_Red", tx - 0.62, ty + 0.05, tz, 30)
    r.at("SM_Bread_Basket", tx + 0.75, ty - 0.02, tz, 10)
    r.at("SM_Bottle_Ketchup", tx + 0.55, ty + 0.12, tz)
    r.at("SM_Salt_Shaker", tx + 0.05, ty + 0.12, tz)
    r.at("SM_Salt_Shaker", tx + 0.1, ty + 0.1, tz)
    # ---- storage boxes by the door
    r.at("SM_Box_Cardboard_L", 0.5, 0.45, 0, 2)
    r.at("SM_Box_Cardboard_L", 0.53, 0.47, 0.44, -6)
    r.at("SM_Box_Cardboard_M", 1.15, 0.4, 0, 88)
    # ---- gameplay
    r.connector("W", 4, "Door_1x3", 1, A.DOOR["x1"] - A.DOOR["x0"], A.DOOR["z1"])
    r.connector("E", 3, "Doorway_2x3", 2, A.DOORWAY["x1"] - A.DOORWAY["x0"], A.DOORWAY["z1"])
    r.bounds()
    return r


def build_pantry(loc, pc):
    nx, ny = 4, 6
    r = Room("Pantry", nx, ny, loc, pc)
    WX, NY = nx * U, ny * U
    r.floors("SM_Floor_PlankGrey_1x1")
    r.walls("S", corner_run(nx), cutaway=True)
    r.walls("E", corner_run(ny), cutaway=True)
    for k in range(nx):
        r.on_wall("SM_Wall_Low_1x05", "S", k, coll=r.c_struct)
    for k in range(ny):
        r.on_wall("SM_Wall_Low_1x05", "E", k, coll=r.c_struct)
    r.walls("N", corner_run(nx))
    r.walls("W", with_openings(ny, {1: ("SM_Wall_Doorway_2x3", 2)}))         # doorway at y 3..5 (matches kitchen)
    r.on_wall("SM_DoorFrame_Wide_2x3", "W", 1, coll=r.c_struct)
    shelves = [r.on_wall("SM_Shelf_Pantry_1U", "N", a, off=(0, T, 0)) for a in (0.5, 1.5, 2.5)]
    shelves.append(r.on_wall("SM_Shelf_Pantry_1U", "W", 4.0, off=(0, T, 0)))   # y 1..2 (south of the doorway)
    shelves.append(r.on_wall("SM_Shelf_Pantry_1U", "W", 3.0, off=(0, T, 0)))   # y 2..3
    corner = r.on_wall("SM_Shelf_Pantry_Corner", "N", WX - 0.5, off=(0, T, 0))
    rnd = random.Random(3)
    jars = [n for n in LIB if n.startswith("SM_Jar_")]
    cans = ["SM_Can_Tin_Teal", "SM_Can_Tin_Lavender"]
    levels = A.a_shelf()["shelf_z"]
    for si, sh in enumerate(shelves):
        m = sh.matrix_basis
        for li, z in enumerate(levels):
            if li == 0:
                inst("SM_Crate_Wood_Low", r.c_props, r.root, m @ M((0.3, 0.2, z), rz=rnd.uniform(-4, 4)))
                inst("SM_Sack_Burlap_S", r.c_props, r.root, m @ M((0.78, 0.2, z), rz=rnd.uniform(0, 360)))
                continue
            if li == len(levels) - 1:
                inst("SM_Cloth_Stack_Charcoal" if si % 2 == 0 else "SM_Basket_Wicker_Rect", r.c_props, r.root,
                     m @ M((0.27, 0.2, z), rz=rnd.uniform(-5, 5)))
                inst("SM_Cloth_Stack_Linen" if si % 2 == 0 else "SM_Cloth_Stack_Charcoal", r.c_props, r.root,
                     m @ M((0.73, 0.2, z), rz=rnd.uniform(-5, 5)))
                continue
            x = 0.06
            while True:
                pool = cans if (li == 1 and rnd.random() < 0.5) else jars
                n = rnd.choice(pool)
                rad = {"S": 0.035, "M": 0.045, "L": 0.058}[n.split("_")[2]] if n.startswith("SM_Jar") else 0.04
                if x + rad * 2 > U - 0.05:
                    break
                for row_y in (0.12, 0.28):
                    if rnd.random() < 0.85:
                        inst(n, r.c_props, r.root, m @ M((x + rad, row_y, z), rz=rnd.uniform(0, 360)))
                x += rad * 2 + 0.012
    for z in levels[1:-1]:
        for (jx, jy) in ((0.12, 0.12), (0.28, 0.2)):
            inst(rnd.choice(jars), r.c_props, r.root, corner.matrix_basis @ M((jx, jy, z), rz=rnd.uniform(0, 360)))
    # runner from the doorway (y 3..5, centre y=4) into the pantry; rug local length +Y -> rotate to +X
    r.at("SM_Rug_Runner_1x3", 0.0, 4.5, 0, -90)
    # floor clutter
    r.at("SM_Crate_Wood", 2.5, 0.6, 0, 8)
    r.at("SM_Book_Stack", 2.5, 0.6, 0.34, 20)
    r.at("SM_Crate_Wood", 1.7, 0.5, 0, -4)
    r.at("SM_Basket_Wicker_Round", 1.72, 0.5, 0.32, 0, s=0.8)
    r.at("SM_Crate_Wood_Low", 3.45, 1.3, 0, 84)
    r.at("SM_Basket_Wicker_Round", 3.4, 2.9, 0)
    r.at("SM_Cloth_Stack_Linen", 3.4, 2.9, 0.03, 10, s=0.9)
    r.at("SM_Crate_Wood", 3.2, 5.1, 0, 2)
    r.at("SM_Crate_Wood_Low", 3.2, 5.1, 0.34, -6)
    r.at("SM_Sack_Burlap", 0.35, 5.2, 0, 30)
    r.at("SM_Sack_Burlap_S", 0.8, 2.2, 0, 100)
    r.at("SM_Sack_Burlap", 1.9, 5.1, 0, -40)
    r.connector("W", 1, "Doorway_2x3", 2, A.DOORWAY["x1"] - A.DOORWAY["x0"], A.DOORWAY["z1"])
    r.bounds()
    return r


def gameplay_templates(x, y):
    """Stand-alone connector template shown in the library."""
    c = get_coll("09_Gameplay_Templates", bpy.data.collections["00_Library"])
    r = Room.__new__(Room)
    r.name, r.nx, r.ny = "Template", 1, 1
    r.root = bpy.data.objects.new("GP_DoorConnector_Template", None)
    r.root.location = (x, y, GROUND + 0.35)
    r.root["note"] = "CONN_ empty = socket (arrow = outward). TRG_ = trigger volume. Pair only equal conn_type."
    c.objects.link(r.root)
    r.c_gp = c
    r.connectors = []
    Room.connector(r, "S", 0, "Door_1x3", 1, A.DOOR["x1"] - A.DOOR["x0"], A.DOOR["z1"])
    inst("SM_Wall_Door_1x3", c, r.root, Matrix.Identity(4))
    inst("SM_DoorFrame_1x3", c, r.root, Matrix.Identity(4))
    label("GP_DoorConnector_Template (CONN_ + TRG_)", (x + 0.625, y + 1.15, GROUND + 0.002), 0.07,
          get_coll("99_Labels"))


# ============================================================================ preview (lights, cameras, render)
def preview_setup(prefab_center, lib_center, lib_size):
    pc = get_coll("99_Preview")
    sc = bpy.context.scene
    world = bpy.data.worlds.new("W_Preview")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.86, 0.74, 0.72, 1)
    bg.inputs["Strength"].default_value = 0.55
    sun_d = bpy.data.lights.new("SUN_Key", "SUN")
    sun_d.energy = 3.2
    sun_d.color = (1.0, 0.9, 0.8)
    sun_d.angle = math.radians(4)
    sun = bpy.data.objects.new("SUN_Key", sun_d)
    sun.rotation_euler = (math.radians(52), 0, math.radians(148))
    pc.objects.link(sun)
    # ground plane
    mb = MB()
    mb.box((-200, -200, -0.36), (200, 200, -0.35), "Plaster_Lilac")
    g = bpy.data.meshes.new("Preview_Ground")
    g.from_pydata(mb.V, [], mb.F)
    gm = bpy.data.materials.new("M_PreviewGround")
    gm.diffuse_color = (0.83, 0.72, 0.7, 1)
    try:
        gm.use_nodes = True
    except Exception:
        pass
    p = gm.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.78, 0.62, 0.6, 1)
    p.inputs["Roughness"].default_value = 0.9
    g.materials.append(gm)
    go = bpy.data.objects.new("Preview_Ground", g)
    pc.objects.link(go)

    def cam(name, target, rx, rz, scale, dist=40):
        cd = bpy.data.cameras.new(name)
        cd.type = "ORTHO"
        cd.ortho_scale = scale
        cd.clip_end = 500
        co = bpy.data.objects.new(name, cd)
        rot = Matrix.Rotation(math.radians(rz), 4, "Z") @ Matrix.Rotation(math.radians(rx), 4, "X")
        view = (rot.to_3x3() @ Vector((0, 0, -1))).normalized()
        co.matrix_world = Matrix.Translation(Vector(target) - view * dist) @ rot
        pc.objects.link(co)
        return co

    c1 = cam("CAM_Prefab_Iso", prefab_center, 58, 45, 15.0)
    c2 = cam("CAM_Library", lib_center, 38, 180, lib_size)
    sc.camera = c1
    return c1, c2


def render(cam, path, res, samples=64):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6
    sc.cycles.transmission_bounces = 6
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.camera = cam
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def hide_helpers():
    vl = bpy.context.view_layer
    for o in bpy.data.objects:
        if o.name.startswith(("UCX_", "TRG_", "BOUNDS_")):
            try:
                o.hide_set(True)
            except RuntimeError:
                pass
    # cut-away (front) walls: hidden in viewport & render, toggle the collection to see them
    def walk(lc):
        if lc.name.endswith("_CutawayWalls"):
            lc.hide_viewport = True
            lc.collection.hide_render = True
        for ch in lc.children:
            walk(ch)
    walk(vl.layer_collection)


def main():
    reset()
    build_library()
    lib_w, lib_d = layout_library()
    gameplay_templates(-1.0, lib_d + H * 0.62)
    lib_d += H * 0.62 + 1.5
    pcoll = get_coll("10_Prefabs")
    # prefabs to the screen-left of the library (world +X), kitchen + pantry snapped by their connectors
    ox, oy = 9.0, 0.0
    build_kitchen((ox, oy, 0), pcoll)
    build_pantry((ox + 7 * U, oy, 0), pcoll)
    hide_helpers()
    prefab_center = (ox + 5.4, oy + 3.2, 0.9)
    lib_center = (-lib_w / 2, lib_d / 2 - 0.6, GROUND)
    c1, c2 = preview_setup(prefab_center, lib_center, lib_w * 1.06)
    bpy.context.scene.camera = c1
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
    print("saved", BLEND, "library", lib_w, "x", lib_d)
    if DO_RENDER:
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        render(c1, os.path.join(PREVIEW_DIR, "prefab_kitchen_pantry.png"), (1800, 1200), 96)
        aspect = min(1.6, max(0.6, (lib_d * 0.8) / lib_w))
        render(c2, os.path.join(PREVIEW_DIR, "asset_library.png"), (2000, int(2000 * aspect)), 48)


if __name__ == "__main__":
    main()
