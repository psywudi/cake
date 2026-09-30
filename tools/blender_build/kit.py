"""
Low-level helpers: mesh builder, materials, UVs, object creation, colliders.
"""
import math
import os
import bpy
from mathutils import Vector, Matrix

from textures import MATERIALS, SPECIAL

GRID = 1.0             # 1 grid unit (U) = 1 m. Module sizes are whole or half grid units only.
U = GRID
H = 3.0                # wall height = 3U  (walls are 1x3 modules)
T = 0.1                # wall skin owned by one room (inset from the grid line); shared walls = 2T

TEX_DIR_REL = "//Textures"
_MAT_CACHE = {}


# ============================================================================ materials
def _img(path, noncolor):
    name = os.path.basename(path)
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.load(path)
    img.colorspace_settings.name = "Non-Color" if noncolor else "sRGB"
    return img


def material(name, tex_dir_abs):
    if name in _MAT_CACHE:
        return _MAT_CACHE[name]
    mat = bpy.data.materials.new("M_" + name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes["Principled BSDF"]
    bsdf.location = (300, 0)
    out = nodes["Material Output"]
    out.location = (600, 0)

    def tex(suffix, noncolor, y):
        n = nodes.new("ShaderNodeTexImage")
        n.image = _img(os.path.join(tex_dir_abs, f"T_{name}_{suffix}.png"), noncolor)
        n.image.filepath = f"{TEX_DIR_REL}/T_{name}_{suffix}.png"
        n.location = (-500, y)
        n.label = suffix
        return n

    t_base = tex("BaseColor", False, 300)
    t_norm = tex("Normal", True, -300)
    t_orm = tex("ORM", True, 0)
    sep = nodes.new("ShaderNodeSeparateColor")
    sep.location = (-150, 0)
    nmap = nodes.new("ShaderNodeNormalMap")
    nmap.location = (-150, -300)
    links.new(t_base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(t_orm.outputs["Color"], sep.inputs["Color"])
    links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    links.new(t_norm.outputs["Color"], nmap.inputs["Color"])
    links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    sp = SPECIAL.get(name, {})
    if sp.get("transmission"):
        bsdf.inputs["Transmission Weight"].default_value = sp["transmission"]
        bsdf.inputs["IOR"].default_value = sp.get("ior", 1.45)
    tile = MATERIALS[name][2]
    mat["tile_m"] = tile if tile else 0.0
    mat["pbr_maps"] = "BaseColor(sRGB), Normal(OpenGL), ORM(R=AO,G=Rough,B=Metal)"
    # viewport colour for solid mode
    try:
        from PIL import Image
        import numpy as np
        a = np.asarray(Image.open(os.path.join(tex_dir_abs, f"T_{name}_BaseColor.png")).convert("RGB"), dtype=float) / 255
        c = (a.reshape(-1, 3).mean(0)) ** 2.2
        mat.diffuse_color = (c[0], c[1], c[2], 1.0)
    except Exception:
        pass
    _MAT_CACHE[name] = mat
    return mat


def tile_of(name):
    t = MATERIALS[name][2]
    return t if t else None


# ============================================================================ mesh builder
class MB:
    """Collects polygons with a material + optional explicit (metric) UV per face."""

    def __init__(self):
        self.V, self.F, self.FM, self.FUV = [], [], [], []
        self.mats = []

    # -- bookkeeping
    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def mark(self):
        return (len(self.V), len(self.F))

    def xform(self, mark, M):
        for i in range(mark[0], len(self.V)):
            self.V[i] = (M @ Vector(self.V[i]))[:]
        return self

    def face(self, idx, m, uvs=None):
        self.F.append(tuple(idx))
        self.FM.append(self.mi(m))
        self.FUV.append(uvs)

    def addv(self, p):
        self.V.append(tuple(p))
        return len(self.V) - 1

    # -- primitives
    def box(self, a, b, m, faces="all", mats=None):
        """Axis aligned box between corners a and b. mats: dict side->material override."""
        x0, y0, z0 = a
        x1, y1, z1 = b
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        z0, z1 = min(z0, z1), max(z0, z1)
        p = [self.addv(v) for v in [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                    (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]]
        sides = {
            "-z": (p[0], p[3], p[2], p[1]), "+z": (p[4], p[5], p[6], p[7]),
            "-y": (p[0], p[1], p[5], p[4]), "+x": (p[1], p[2], p[6], p[5]),
            "+y": (p[2], p[3], p[7], p[6]), "-x": (p[3], p[0], p[4], p[7]),
        }
        for k, f in sides.items():
            if faces != "all" and k not in faces:
                continue
            self.face(f, (mats or {}).get(k, m))
        return self

    def lathe(self, prof, m, seg=16, c=(0.0, 0.0, 0.0), cap0=True, cap1=True, mats=None):
        """Revolve a (r, z) profile (bottom->top) around Z at centre c."""
        cx, cy, cz = c
        rref = max(r for r, _ in prof) or 0.01
        circ = 2 * math.pi * rref
        # cumulative length along profile for v
        L = [0.0]
        for i in range(1, len(prof)):
            L.append(L[-1] + math.hypot(prof[i][0] - prof[i - 1][0], prof[i][1] - prof[i - 1][1]))
        rings = []
        for (r, z) in prof:
            ring = []
            for s in range(seg):
                a = 2 * math.pi * s / seg
                ring.append(self.addv((cx + r * math.cos(a), cy + r * math.sin(a), cz + z)))
            rings.append(ring)
        for i in range(len(prof) - 1):
            mm = (mats or {}).get(i, m)
            if prof[i][0] < 1e-6 and prof[i + 1][0] < 1e-6:
                continue
            for s in range(seg):
                s1 = (s + 1) % seg
                idx = (rings[i][s], rings[i][s1], rings[i + 1][s1], rings[i + 1][s])
                uvs = [(circ * s / seg, L[i]), (circ * (s + 1) / seg, L[i]),
                       (circ * (s + 1) / seg, L[i + 1]), (circ * s / seg, L[i + 1])]
                if prof[i][0] < 1e-6:   # collapse to triangle at pole
                    idx = (rings[i][0], rings[i + 1][s1], rings[i + 1][s])
                    uvs = [(circ * (s + .5) / seg, L[i]), uvs[2], uvs[3]]
                elif prof[i + 1][0] < 1e-6:
                    idx = (rings[i][s], rings[i][s1], rings[i + 1][0])
                    uvs = [uvs[0], uvs[1], (circ * (s + .5) / seg, L[i + 1])]
                self.face(idx, mm, uvs)
        if cap0 and prof[0][0] > 1e-6:
            self.face(list(reversed(rings[0])), (mats or {}).get("cap0", m))
        if cap1 and prof[-1][0] > 1e-6:
            self.face(rings[-1], (mats or {}).get("cap1", m))
        return self

    def cyl(self, c, r, h, m, seg=16, **kw):
        return self.lathe([(r, 0), (r, h)], m, seg, c, **kw)

    def quad_uv(self, pts, m, uvs):
        idx = [self.addv(p) for p in pts]
        self.face(idx, m, uvs)

    def grid_surface(self, fn, nu, nv, m, uv_scale=(1, 1), double=False):
        """Parametric surface fn(s,t)->(x,y,z), s,t in [0,1]. uv in metres via uv_scale."""
        ids = [[self.addv(fn(i / nu, j / nv)) for i in range(nu + 1)] for j in range(nv + 1)]
        for j in range(nv):
            for i in range(nu):
                q = (ids[j][i], ids[j][i + 1], ids[j + 1][i + 1], ids[j + 1][i])
                uvs = [(i / nu * uv_scale[0], j / nv * uv_scale[1]), ((i + 1) / nu * uv_scale[0], j / nv * uv_scale[1]),
                       ((i + 1) / nu * uv_scale[0], (j + 1) / nv * uv_scale[1]), (i / nu * uv_scale[0], (j + 1) / nv * uv_scale[1])]
                self.face(q, m, uvs)
                if double:
                    self.face(tuple(reversed(q)), m, list(reversed(uvs)))
        return ids

    def tube_arc(self, c, R, r, a0, a1, m, nu=10, nv=8):
        """Tube swept along an arc in the XZ plane (handles). Angles in degrees, 0 = +X."""
        cx, cy, cz = c
        A0, A1 = math.radians(a0), math.radians(a1)

        def fn(s, t):
            a = A0 + (A1 - A0) * s
            b = -2 * math.pi * t
            k = R + r * math.cos(b)
            return (cx + k * math.cos(a), cy + r * math.sin(b), cz + k * math.sin(a))
        self.grid_surface(fn, nu, nv, m, uv_scale=(abs(A1 - A0) * R, 2 * math.pi * r))
        return self

    def prism(self, poly, z0, z1, matfn):
        """Vertical prism from a CCW 2D polygon. matfn(normal, centre) -> material name."""
        n = len(poly)
        b = [self.addv((x, y, z0)) for x, y in poly]
        t = [self.addv((x, y, z1)) for x, y in poly]
        V = lambda i: Vector(self.V[i])
        faces = [list(reversed(b)), t]
        for i in range(n):
            j = (i + 1) % n
            faces.append([b[i], b[j], t[j], t[i]])
        for f in faces:
            p0, p1, p2 = V(f[0]), V(f[1]), V(f[2])
            nrm = (p1 - p0).cross(p2 - p0).normalized()
            c = sum((V(i) for i in f), Vector()) / len(f)
            self.face(f, matfn(nrm, c))
        return self

    def add_mesh(self, me, matfn):
        base = len(self.V)
        for v in me.vertices:
            self.V.append(v.co[:])
        for p in me.polygons:
            self.face([base + i for i in p.vertices], matfn(p))


# ============================================================================ objects
def _box_uv(co, n, tile):
    ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
    if az >= ax and az >= ay:
        u, v = co.x, co.y if n.z > 0 else -co.y
    elif ax >= ay:
        u, v = (co.y if n.x > 0 else -co.y), co.z
    else:
        u, v = (-co.x if n.y > 0 else co.x), co.z
    return (u / tile, v / tile)


def build(name, mb, coll, tex_dir, bevel=0.0, bevel_seg=2, smooth_angle=35, lightmap=True, props=None,
          weld=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(mb.V, [], mb.F)
    for mn in mb.mats:
        me.materials.append(material(mn, tex_dir))
    me.polygons.foreach_set("material_index", mb.FM)
    uvl = me.uv_layers.new(name="UVMap")
    me.update()
    for pi, poly in enumerate(me.polygons):
        mname = mb.mats[mb.FM[pi]]
        tile = tile_of(mname)
        exp = mb.FUV[pi]
        n = poly.normal
        for k, li in enumerate(poly.loop_indices):
            if exp is not None:
                u, v = exp[k]
                if tile:
                    u, v = u / tile, v / tile
            else:
                co = me.vertices[me.loops[li].vertex_index].co
                u, v = _box_uv(co, n, tile or 1.0)
            uvl.data[li].uv = (u, v)
    if weld:
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bm.to_mesh(me)
        bm.free()
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    if bevel > 0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = bevel_seg
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(40)
        mod.use_clamp_overlap = True
        apply_modifiers(obj)
    me = obj.data
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    if lightmap:
        lightmap_uv(obj)
    if props:
        for k, v in props.items():
            obj[k] = v
    return obj


def apply_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    newme = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.modifiers.clear()
    obj.data = newme
    name = old.name
    bpy.data.meshes.remove(old)
    newme.name = name


def lightmap_uv(obj):
    """Second, non-overlapping UV channel (lightmaps / baked AO)."""
    me = obj.data
    lm = me.uv_layers.new(name="UVLightmap")
    me.uv_layers.active = lm
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    vl.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.01, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)
    me.uv_layers.active = me.uv_layers["UVMap"]
    me.uv_layers["UVMap"].active_render = True


def ucx(obj, boxes, coll):
    """Unreal/Unity style convex collision boxes, parented to obj (UCX_<name>_NN)."""
    out = []
    for i, (a, b) in enumerate(boxes):
        mb = MB()
        mb.box(a, b, None)
        me = bpy.data.meshes.new(f"UCX_{obj.name}_{i:02d}")
        me.from_pydata(mb.V, [], mb.F)
        o = bpy.data.objects.new(me.name, me)
        coll.objects.link(o)
        o.parent = obj
        o.display_type = "WIRE"
        o.hide_render = True
        o["collider"] = "convex"
        out.append(o)
    return out


def bbox_local(obj):
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def ucx_bounds(obj, coll):
    a, b = bbox_local(obj)
    return ucx(obj, [(a, b)], coll)


def get_coll(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def linked_copy(src, coll, matrix, parent=None, name=None):
    """Linked duplicate (shares mesh data) incl. collider children."""
    o = src.copy()
    if name:
        o.name = name
    o.matrix_world = matrix
    coll.objects.link(o)
    for ch in src.children:
        c = ch.copy()
        coll.objects.link(c)
        c.parent = o
        c.matrix_parent_inverse = ch.matrix_parent_inverse.copy()
    if parent is not None:
        o.parent = parent
        o.matrix_parent_inverse = parent.matrix_world.inverted()
    return o


def M(loc=(0, 0, 0), rz=0.0, rx=0.0, ry=0.0, s=None):
    m = Matrix.Translation(Vector(loc)) @ Matrix.Rotation(math.radians(rz), 4, "Z") \
        @ Matrix.Rotation(math.radians(ry), 4, "Y") @ Matrix.Rotation(math.radians(rx), 4, "X")
    if s is not None:
        m = m @ Matrix.Diagonal(Vector((s[0], s[1], s[2], 1.0)))
    return m
