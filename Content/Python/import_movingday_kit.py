"""
MovingDay asset importer (Unreal Engine 5, Python Editor Script Plugin).

Source folder (default): C:\\Users\\Administrator\\Desktop\\754\\CatPostRoom
Change SOURCE_DIR below if the assets move.

Two modes, picked automatically:

1. Kit mode  - the folder has FBX/01_Floors ... FBX/08_Pantry_Jars + Textures/T_<Name>_BaseColor|Normal|ORM.png
               (the CozyKitchen kit):
     /Game/MovingDay/Art/Environment/Floors|Walls|DoorsWindows/        SM_*
     /Game/MovingDay/Art/Furniture/Kitchen|Dining|Props|Storage|Jars/  SM_*
     /Game/MovingDay/Art/Materials/   M_MovingDay_Master, M_MovingDay_Glass, MI_<Name>
     /Game/MovingDay/Art/Textures/    T_<Name>_*

2. Generic mode - any other folder of FBX + images (searched recursively):
     /Game/MovingDay/Art/Environment/<FolderName>/Meshes/<sub folders>/   meshes
     /Game/MovingDay/Art/Environment/<FolderName>/Textures/               all images
     /Game/MovingDay/Art/Environment/<FolderName>/Materials/              MI_<Set> for every
           complete BaseColor + Normal + ORM/ARM texture set; slots without a full set keep the
           material the FBX importer builds from the textures referenced in the FBX.

Run in the editor:  Tools > Execute Python Script...  (pick this file)
Safe to run again: assets are re-imported / updated in place.
"""
import os
import re

import unreal

SOURCE_DIR = r"C:\Users\Administrator\Desktop\754\CatPostRoom"

ART = "/Game/MovingDay/Art"
KIT_FOLDERS = {
    "01_Floors": ART + "/Environment/Floors",
    "02_Walls": ART + "/Environment/Walls",
    "03_Doors_Windows": ART + "/Environment/DoorsWindows",
    "04_Kitchen_Furniture": ART + "/Furniture/Kitchen",
    "05_Dining": ART + "/Furniture/Dining",
    "06_Kitchen_Props": ART + "/Furniture/Props",
    "07_Pantry_Storage": ART + "/Furniture/Storage",
    "08_Pantry_Jars": ART + "/Furniture/Jars",
}
TRANSLUCENT = {"Glass_Clear", "Glass"}
IMAGE_EXT = (".png", ".tga", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".bmp")

# texture-set suffixes (case-insensitive), e.g. Chair_BaseColor.png, T_Chair_Albedo.tga, chair-n.png
KINDS = {
    "BaseColor": r"basecolor|base_color|albedo|diffuse|diff|color|col|bc|d",
    "Normal": r"normal|normalgl|normal_opengl|nrm|nor|n",
    "NormalDX": r"normaldx|normal_directx",
    "ORM": r"orm|arm|occlusionroughnessmetallic|occlusion_roughness_metallic",
}
SUFFIX_RE = re.compile(r"^(?:t_)?(?P<base>.+?)[_\-. ](?P<kind>%s)$" % "|".join(
    "(?:%s)" % v for v in [KINDS["NormalDX"], KINDS["ORM"], KINDS["BaseColor"], KINDS["Normal"]]), re.I)

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(msg):
    unreal.log("[MovingDay] " + msg)


def warn(msg):
    unreal.log_warning("[MovingDay] " + msg)


def safe(name):
    s = re.sub(r"[^\w]+", "_", name, flags=re.UNICODE).strip("_")
    return s or "Assets"


# ----------------------------------------------------------------------------- import helpers
def _import(files, dest, options=None):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("automated", True)
        t.set_editor_property("save", False)
        if options is not None:
            t.set_editor_property("options", options)
        tasks.append(t)
    if tasks:
        asset_tools.import_asset_tasks(tasks)
    out = []
    for t in tasks:
        out += [str(p) for p in (t.get_editor_property("imported_object_paths") or [])]
    return out


def fbx_options(with_materials):
    o = unreal.FbxImportUI()
    o.set_editor_property("import_mesh", True)
    o.set_editor_property("import_as_skeletal", False)
    o.set_editor_property("import_animations", False)
    o.set_editor_property("import_materials", with_materials)
    o.set_editor_property("import_textures", with_materials)
    o.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    sm = o.get_editor_property("static_mesh_import_data")
    sm.set_editor_property("combine_meshes", True)
    sm.set_editor_property("auto_generate_collision", not KIT_MODE)   # kit ships UCX_ hulls
    sm.set_editor_property("generate_lightmap_u_vs", not KIT_MODE)    # kit ships UV1 lightmap UVs
    sm.set_editor_property("convert_scene", True)
    sm.set_editor_property("import_uniform_scale", 1.0)
    sm.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    return o


# ----------------------------------------------------------------------------- textures
def setup_texture(tex, kind):
    if kind in ("Normal", "NormalDX"):
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("flip_green_channel", kind == "Normal")   # OpenGL -> DirectX
    elif kind == "ORM":
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        tex.set_editor_property("srgb", False)
    else:
        tex.set_editor_property("srgb", True)
    eal.save_loaded_asset(tex)


def import_texture_sets(image_files, tex_path):
    """Imports images, returns {set_name: {kind: Texture2D}}."""
    sets = {}
    for f in image_files:
        stem = os.path.splitext(os.path.basename(f))[0]
        m = SUFFIX_RE.match(stem)
        if not m:
            continue
        kind = next(k for k, v in KINDS.items() if re.fullmatch(v, m.group("kind"), re.I))
        sets.setdefault(m.group("base"), {})[kind] = f
    paths = _import(image_files, tex_path)
    by_stem = {}
    for p in paths:
        a = eal.load_asset(p)
        if isinstance(a, unreal.Texture2D):
            by_stem[a.get_name().lower()] = a
    out = {}
    for base, kinds in sets.items():
        for kind, f in kinds.items():
            stem = safe(os.path.splitext(os.path.basename(f))[0]).lower()
            tex = by_stem.get(stem) or by_stem.get(os.path.splitext(os.path.basename(f))[0].lower())
            if tex:
                setup_texture(tex, kind)
                out.setdefault(base, {})["Normal" if kind == "NormalDX" else kind] = tex
    log(f"{tex_path}: {len(paths)} textures, {len(out)} texture sets")
    return out


# ----------------------------------------------------------------------------- materials
def _param(mat, cls, name, x, y):
    e = mel.create_material_expression(mat, cls, x, y)
    e.set_editor_property("parameter_name", name)
    return e


def build_master(mat_path, name, translucent, sample):
    path = f"{mat_path}/{name}"
    if eal.does_asset_exist(path):          # keep an existing master (and any edits made to it)
        return eal.load_asset(path)
    mat = asset_tools.create_asset(name, mat_path, unreal.Material, unreal.MaterialFactoryNew())
    if translucent:
        mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property("translucency_lighting_mode",
                                unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    T2D = unreal.MaterialExpressionTextureSampleParameter2D
    bc = _param(mat, T2D, "BaseColor", -700, -300)
    bc.set_editor_property("texture", sample["BaseColor"])
    nm = _param(mat, T2D, "Normal", -700, 300)
    nm.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    nm.set_editor_property("texture", sample["Normal"])
    orm = _param(mat, T2D, "ORM", -700, 0)
    orm.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    orm.set_editor_property("texture", sample["ORM"])
    tint = _param(mat, unreal.MaterialExpressionVectorParameter, "Tint", -700, -500)
    tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    mul = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -350, -350)
    mel.connect_material_expressions(bc, "RGB", mul, "A")
    mel.connect_material_expressions(tint, "", mul, "B")
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(nm, "RGB", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(orm, "G", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(orm, "B", unreal.MaterialProperty.MP_METALLIC)
    if translucent:
        op = _param(mat, unreal.MaterialExpressionScalarParameter, "Opacity", -700, 600)
        op.set_editor_property("default_value", 0.2)
        mel.connect_material_property(op, "", unreal.MaterialProperty.MP_OPACITY)
    else:
        mel.connect_material_property(orm, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    return mat


def build_instances(sets, mat_path):
    full = {k: v for k, v in sets.items() if all(x in v for x in ("BaseColor", "Normal", "ORM"))}
    if not full:
        return {}
    sample = next(iter(full.values()))
    master = build_master(mat_path, "M_MovingDay_Master", False, sample)
    glass = None
    out = {}
    for n, texs in full.items():
        if n in TRANSLUCENT and glass is None:
            glass = build_master(mat_path, "M_MovingDay_Glass", True, texs)
        path = f"{mat_path}/MI_{safe(n)}"
        mi = eal.load_asset(path) if eal.does_asset_exist(path) else asset_tools.create_asset(
            f"MI_{safe(n)}", mat_path, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, glass if n in TRANSLUCENT else master)
        for p in ("BaseColor", "Normal", "ORM"):
            mel.set_material_instance_texture_parameter_value(mi, p, texs[p])
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi)
        out[n] = mi
    log(f"{mat_path}: {len(out)} material instances")
    return out


# ----------------------------------------------------------------------------- meshes
def _match(slot, names):
    s = re.sub(r"(\.\d+)$", "", str(slot))
    s = re.sub(r"^(MI?_)", "", s)
    low = {n.lower(): n for n in names}
    if s.lower() in low:
        return low[s.lower()]
    for n in sorted(names, key=len, reverse=True):     # longest name contained in the slot name
        if n.lower() in s.lower():
            return n
    return None


def fix_mesh(sm, mis):
    for i, m in enumerate(sm.get_editor_property("static_materials")):
        key = _match(m.get_editor_property("material_slot_name"), mis.keys())
        cur = m.get_editor_property("material_interface")
        if key is None and cur:
            key = _match(cur.get_name(), mis.keys())
        if key:
            sm.set_material(i, mis[key])
        elif KIT_MODE or cur is None:
            warn(f"{sm.get_name()}: no material for slot {m.get_editor_property('material_slot_name')}")
    if KIT_MODE:
        sm.set_editor_property("light_map_coordinate_index", 1)
        sm.set_editor_property("light_map_resolution", 64)
        sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        bs = sme.get_lod_build_settings(sm, 0)
        bs.set_editor_property("generate_lightmap_u_vs", False)
        sme.set_lod_build_settings(sm, 0, bs)
    eal.save_loaded_asset(sm)


def import_fbx_group(files, dest, mis):
    paths = _import(files, dest, fbx_options(with_materials=not KIT_MODE))
    meshes = [a for a in (eal.load_asset(p) for p in paths) if isinstance(a, unreal.StaticMesh)]
    for sm in meshes:
        fix_mesh(sm, mis)
    if KIT_MODE:   # the kit's materials come from MI_*, drop anything an importer created next to the meshes
        for p in eal.list_assets(dest, recursive=True, include_folder=False):
            a = eal.load_asset(p)
            if a and not isinstance(a, unreal.StaticMesh):
                eal.delete_asset(p)
    log(f"{dest}: {len(meshes)}/{len(files)} meshes")
    if len(meshes) < len(files):
        warn(f"{dest}: some FBX produced no static mesh (skeletal/empty files are skipped)")
    return len(meshes)


# ----------------------------------------------------------------------------- run
def _walk(root, exts):
    out = []
    for d, _, fs in os.walk(root):
        out += [os.path.join(d, f) for f in sorted(fs) if f.lower().endswith(exts)]
    return sorted(out)


KIT_MODE = False


def run(source=None):
    global KIT_MODE
    src = source or SOURCE_DIR
    if not os.path.isdir(src):
        raise RuntimeError(f"[MovingDay] folder not found: {src}  (edit SOURCE_DIR at the top of this script)")
    fbx_root = os.path.join(src, "FBX")
    KIT_MODE = os.path.isdir(fbx_root) and any(d in KIT_FOLDERS for d in os.listdir(fbx_root))
    fbx = _walk(src, (".fbx",))
    images = _walk(src, IMAGE_EXT)
    log(f"source: {src}  ({len(fbx)} FBX, {len(images)} images, {'kit' if KIT_MODE else 'generic'} mode)")
    if not fbx:
        raise RuntimeError(f"[MovingDay] no .fbx files under {src}")

    if KIT_MODE:
        root, tex_path, mat_path = ART, ART + "/Textures", ART + "/Materials"
    else:
        root = f"{ART}/Environment/{safe(os.path.basename(os.path.normpath(src)))}"
        tex_path, mat_path = root + "/Textures", root + "/Materials"

    with unreal.ScopedSlowTask(3, "Importing MovingDay assets") as task:
        task.make_dialog(True)
        task.enter_progress_frame(1, "Textures & materials")
        sets = import_texture_sets(images, tex_path)
        mis = build_instances(sets, mat_path)
        task.enter_progress_frame(1, "Static meshes")
        groups = {}
        for f in fbx:
            rel = os.path.relpath(os.path.dirname(f), src)
            parts = [p for p in rel.replace("\\", "/").split("/") if p not in (".", "")]
            kit_dir = next((p for p in parts if p in KIT_FOLDERS), None)
            if KIT_MODE and kit_dir:
                dest = KIT_FOLDERS[kit_dir]
            else:
                if parts and parts[0].lower() == "fbx":
                    parts = parts[1:]
                dest = "/".join([root + "/Meshes"] + [safe(p) for p in parts])
            groups.setdefault(dest, []).append(f)
        n = sum(import_fbx_group(files, dest, mis) for dest, files in groups.items())
        task.enter_progress_frame(1, "Saving")
        eal.save_directory(root, only_if_is_dirty=True, recursive=True)
    log(f"done: {n} static meshes, {len(mis)} material instances -> {root}")


if __name__ == "__main__":
    run()
