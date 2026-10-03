"""
MovingDay kit importer (Unreal Engine 5, Python Editor Script Plugin).

Imports the kit (FBX + PNG; auto-detects SourceArt/MovingDay or Desktop/754) into /Game/MovingDay/Art and wires PBR materials:

  /Game/MovingDay/Art/Textures/                 T_<Name>_BaseColor / _Normal / _ORM
  /Game/MovingDay/Art/Materials/                M_MovingDay_Master, M_MovingDay_Glass, MI_<Name>
  /Game/MovingDay/Art/Environment/Floors|Walls|DoorsWindows/   SM_*
  /Game/MovingDay/Art/Furniture/Kitchen|Dining|Props|Storage|Jars/   SM_*

Run in the editor:  Tools > Execute Python Script...  (pick this file)
         or in the Output Log (Python):  import import_movingday_kit; import_movingday_kit.run()
Safe to run again: everything is re-imported / updated in place.
"""
import os
import re

import unreal

# Folder that contains FBX/ and Textures/. Leave empty to auto-detect, or set it explicitly, e.g.
# SOURCE_OVERRIDE = r"C:\Users\me\Desktop\754\CozyKitchen_Kit"
SOURCE_OVERRIDE = r""


def _find_source():
    def ok(d):
        return os.path.isdir(os.path.join(d, "FBX")) and os.path.isdir(os.path.join(d, "Textures"))

    home = os.path.expanduser("~")
    roots = [os.environ.get("MOVINGDAY_SOURCE", ""), SOURCE_OVERRIDE,
             os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()),
                          "SourceArt", "MovingDay")]
    for desk in ("Desktop", "桌面", os.path.join("OneDrive", "Desktop"), os.path.join("OneDrive", "桌面")):
        roots.append(os.path.join(home, desk, "754"))
    for r in roots:
        if not r or not os.path.isdir(r):
            continue
        if ok(r):
            return r
        for sub in sorted(os.listdir(r)):           # e.g. 754/CozyKitchen_Kit
            d = os.path.join(r, sub)
            if os.path.isdir(d) and ok(d):
                return d
    return ""


SOURCE_DIR = _find_source()
ART ="/Game/MovingDay/Art"
TEX_PATH = ART + "/Textures"
MAT_PATH = ART + "/Materials"

# FBX source folder -> content folder
MESH_FOLDERS = {
    "01_Floors": ART + "/Environment/Floors",
    "02_Walls": ART + "/Environment/Walls",
    "03_Doors_Windows": ART + "/Environment/DoorsWindows",
    "04_Kitchen_Furniture": ART + "/Furniture/Kitchen",
    "05_Dining": ART + "/Furniture/Dining",
    "06_Kitchen_Props": ART + "/Furniture/Props",
    "07_Pantry_Storage": ART + "/Furniture/Storage",
    "08_Pantry_Jars": ART + "/Furniture/Jars",
}
TRANSLUCENT = {"Glass_Clear"}

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(msg):
    unreal.log("[MovingDay] " + msg)


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
    asset_tools.import_asset_tasks(tasks)
    out = []
    for t in tasks:
        out += list(t.get_editor_property("imported_object_paths") or [])
    return out


def material_names():
    tex_dir = os.path.join(SOURCE_DIR, "Textures")
    names = sorted(f[2:-len("_BaseColor.png")] for f in os.listdir(tex_dir) if f.endswith("_BaseColor.png"))
    return names


# ----------------------------------------------------------------------------- textures
def import_textures(names):
    tex_dir = os.path.join(SOURCE_DIR, "Textures")
    files = [os.path.join(tex_dir, f) for f in sorted(os.listdir(tex_dir)) if f.lower().endswith(".png")]
    _import(files, TEX_PATH)
    for n in names:
        for suffix in ("BaseColor", "Normal", "ORM"):
            tex = eal.load_asset(f"{TEX_PATH}/T_{n}_{suffix}")
            if tex is None:
                unreal.log_warning(f"[MovingDay] missing texture T_{n}_{suffix}")
                continue
            if suffix == "Normal":
                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
                tex.set_editor_property("srgb", False)
                tex.set_editor_property("flip_green_channel", True)   # source maps are OpenGL (+Y)
            elif suffix == "ORM":
                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
                tex.set_editor_property("srgb", False)
            else:
                tex.set_editor_property("srgb", True)
            eal.save_loaded_asset(tex)
    log(f"textures: {len(files)}")


def tex(n, suffix):
    return eal.load_asset(f"{TEX_PATH}/T_{n}_{suffix}")


# ----------------------------------------------------------------------------- materials
def _param(mat, cls, name, x, y):
    e = mel.create_material_expression(mat, cls, x, y)
    e.set_editor_property("parameter_name", name)
    return e


def build_master(name, translucent, sample):
    path = f"{MAT_PATH}/{name}"
    if eal.does_asset_exist(path):          # keep existing master (and any edits made to it)
        return eal.load_asset(path)
    mat =asset_tools.create_asset(name, MAT_PATH, unreal.Material, unreal.MaterialFactoryNew())
    if translucent:
        mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property("translucency_lighting_mode",
                                unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    T2D = unreal.MaterialExpressionTextureSampleParameter2D
    bc = _param(mat, T2D, "BaseColor", -700, -300)
    bc.set_editor_property("texture", tex(sample, "BaseColor"))
    nm = _param(mat, T2D, "Normal", -700, 300)
    nm.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    nm.set_editor_property("texture", tex(sample, "Normal"))
    orm = _param(mat, T2D, "ORM", -700, 0)
    orm.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    orm.set_editor_property("texture", tex(sample, "ORM"))
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


def build_instances(names, master, glass):
    out = {}
    for n in names:
        path = f"{MAT_PATH}/MI_{n}"
        mi = eal.load_asset(path) if eal.does_asset_exist(path) else asset_tools.create_asset(
            f"MI_{n}", MAT_PATH, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, glass if n in TRANSLUCENT else master)
        for p in ("BaseColor", "Normal", "ORM"):
            t = tex(n, p)
            if t:
                mel.set_material_instance_texture_parameter_value(mi, p, t)
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi)
        out[n] = mi
    log(f"material instances: {len(out)}")
    return out


# ----------------------------------------------------------------------------- meshes
def fbx_options():
    o = unreal.FbxImportUI()
    o.set_editor_property("import_mesh", True)
    o.set_editor_property("import_as_skeletal", False)
    o.set_editor_property("import_animations", False)
    o.set_editor_property("import_materials", False)
    o.set_editor_property("import_textures", False)
    o.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    sm = o.get_editor_property("static_mesh_import_data")
    sm.set_editor_property("combine_meshes", True)
    sm.set_editor_property("auto_generate_collision", False)     # UCX_ hulls ship with the FBX
    sm.set_editor_property("generate_lightmap_u_vs", False)      # UV1 "UVLightmap" ships with the FBX
    sm.set_editor_property("convert_scene", True)
    sm.set_editor_property("convert_scene_unit", False)
    sm.set_editor_property("import_uniform_scale", 1.0)
    sm.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    return o


def _match(slot, names):
    s = re.sub(r"(\.\d+)$", "", str(slot))
    s = re.sub(r"^(MI?_)", "", s)
    if s in names:
        return s
    for n in sorted(names, key=len, reverse=True):     # longest match first
        if n in s:
            return n
    return None


def fix_mesh(sm, mis, names):
    for i, m in enumerate(sm.get_editor_property("static_materials")):
        key = _match(m.get_editor_property("material_slot_name"), names)
        if key is None and m.get_editor_property("material_interface"):
            key = _match(m.get_editor_property("material_interface").get_name(), names)
        if key:
            sm.set_material(i, mis[key])
        else:
            unreal.log_warning(f"[MovingDay] {sm.get_name()}: no material for slot "
                               f"{m.get_editor_property('material_slot_name')}")
    sm.set_editor_property("light_map_coordinate_index", 1)
    sm.set_editor_property("light_map_resolution", 64)
    sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    bs = sme.get_lod_build_settings(sm, 0)
    bs.set_editor_property("generate_lightmap_u_vs", False)
    sme.set_lod_build_settings(sm, 0, bs)
    eal.save_loaded_asset(sm)


def cleanup(dest):
    """Remove materials/textures an importer may have auto-created next to the meshes."""
    for p in eal.list_assets(dest, recursive=True, include_folder=False):
        a = eal.load_asset(p)
        if a and not isinstance(a, unreal.StaticMesh):
            eal.delete_asset(p)


def import_meshes(mis, names):
    total = 0
    for src, dest in MESH_FOLDERS.items():
        folder = os.path.join(SOURCE_DIR, "FBX", src)
        if not os.path.isdir(folder):
            continue
        files = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.lower().endswith(".fbx")]
        _import(files, dest, fbx_options())
        for f in files:
            name = os.path.splitext(os.path.basename(f))[0]
            sm = eal.load_asset(f"{dest}/{name}")
            if isinstance(sm, unreal.StaticMesh):
                fix_mesh(sm, mis, names)
                total += 1
            else:
                unreal.log_warning(f"[MovingDay] import failed: {f}")
        cleanup(dest)
        log(f"{dest}: {len(files)} meshes")
    return total


def run():
    if not SOURCE_DIR:
        raise RuntimeError("[MovingDay] FBX/Textures folder not found. Set SOURCE_OVERRIDE at the top of "
                           "import_movingday_kit.py to the folder that contains FBX and Textures.")
    log(f"source: {SOURCE_DIR}")
    names = material_names()
    with unreal.ScopedSlowTask(4, "Importing MovingDay kit") as task:
        task.make_dialog(True)
        task.enter_progress_frame(1, "Textures")
        import_textures(names)
        task.enter_progress_frame(1, "Materials")
        master = build_master("M_MovingDay_Master", False, "Plaster_Lilac")
        glass = build_master("M_MovingDay_Glass", True, "Glass_Clear")
        mis = build_instances(names, master, glass)
        task.enter_progress_frame(1, "Static meshes")
        n = import_meshes(mis, names)
        task.enter_progress_frame(1, "Saving")
        eal.save_directory(ART, only_if_is_dirty=True, recursive=True)
    log(f"done: {n} static meshes, {len(names)} materials")


if __name__ == "__main__":
    run()
