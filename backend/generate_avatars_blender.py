"""
Generate 3 high-quality animated human avatars using MPFB2 inside Blender.

Run this via the Blender MCP server (execute_blender_code):
    exec(open(r'c:\\Users\\AyeBayBay\\Projects\\AI_Companion\\backend\\generate_avatars_blender.py').read())

Produces GLB files with ARKit-style morph targets (jawOpen, eyeBlink*, mouthSmile*,
mouthFrown*, browInnerUp, browDown*) consumed by frontend/src/components/HumanAvatar3D.jsx.

Requires: MPFB2 extension installed/enabled (module bl_ext.user_default.mpfb).
"""
import bpy
import math
import os
from mathutils import Vector
from bl_ext.user_default.mpfb.services.humanservice import HumanService

BASE_DIR = r'c:\Users\AyeBayBay\Projects\AI_Companion'
OUT_DIR = r'c:\Users\AyeBayBay\Projects\AI_Companion\frontend\public\avatars'

# Body-shape macros + assets + material palette per character.
CHARACTERS = [
    {
        'name': 'greg_3d',
        'macro': {'gender': 1.0, 'age': 0.5, 'muscle': 0.82, 'weight': 0.45,
                  'proportions': 0.5, 'height': 0.62, 'cupsize': 0.5, 'firmness': 0.5,
                  'race': {'asian': 0.15, 'caucasian': 0.8, 'african': 0.05}},
        'eye_color': (0.18, 0.28, 0.36),  # Blue-gray
        'skin_path': r'makehuman_system_assets_cc0\skins\young_caucasian_male\young_caucasian_male.mhmat',
        'clothes': r'makehuman_system_assets_cc0\clothes\male_casualsuit01\male_casualsuit01.mhclo',
        'shoes': r'makehuman_system_assets_cc0\clothes\shoes01\shoes01.mhclo',
        'hair': r'makehuman_system_assets_cc0\hair\short01\short01.mhclo',
    },
    {
        'name': 'tiffany_3d',
        'macro': {'gender': 0.0, 'age': 0.45, 'muscle': 0.40, 'weight': 0.46,
                  'proportions': 0.55, 'height': 0.48, 'cupsize': 0.78, 'firmness': 0.62,
                  'race': {'asian': 0.2, 'caucasian': 0.75, 'african': 0.05}},
        'eye_color': (0.15, 0.32, 0.18),  # Green
        'skin_path': r'makehuman_system_assets_cc0\skins\young_caucasian_female\young_caucasian_female.mhmat',
        'clothes': r'makehuman_system_assets_cc0\clothes\female_casualsuit01\female_casualsuit01.mhclo',
        'shoes': r'makehuman_system_assets_cc0\clothes\shoes02\shoes02.mhclo',
        'hair': r'makehuman_system_assets_cc0\hair\long01\long01.mhclo',
    },
    {
        'name': 'friendly_ai_3d',
        'macro': {'gender': 0.5, 'age': 0.5, 'muscle': 0.5, 'weight': 0.5,
                  'proportions': 0.5, 'height': 0.5, 'cupsize': 0.45, 'firmness': 0.5,
                  'race': {'asian': 0.33, 'caucasian': 0.34, 'african': 0.33}},
        'eye_color': (0.45, 0.32, 0.12),  # Glowing golden hazel
        'skin_path': r'makehuman_system_assets_cc0\skins\young_asian_female\young_asian_female.mhmat',
        'clothes': r'makehuman_system_assets_cc0\clothes\female_sportsuit01\female_sportsuit01.mhclo',
        'shoes': r'makehuman_system_assets_cc0\clothes\shoes03\shoes03.mhclo',
        'hair': r'makehuman_system_assets_cc0\hair\bob02\bob02.mhclo',
    },
]


def clear_scene():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def group_verts(obj, name, wmin=0.3):
    vgi = {vg.name: vg.index for vg in obj.vertex_groups}
    idx = vgi.get(name)
    out = []
    if idx is None:
        return out
    for v in obj.data.vertices:
        for g in v.groups:
            if g.group == idx and g.weight > wmin:
                out.append(v)
                break
    return out


def centroid(verts):
    c = Vector((0, 0, 0))
    for v in verts:
        c += v.co
    return c / len(verts)


def delete_non_body(obj):
    """Remove helper cage / joint cubes / helper eyes, keeping only the body skin and deleting vertices under clothes."""
    import bmesh
    me = obj.data
    
    # Identify delete groups for clothes (vertex groups starting with "Delete.")
    delete_group_indices = [vg.index for vg in obj.vertex_groups if vg.name.startswith('Delete.')]
    body_vg = obj.vertex_groups.get('body')
    body_idx = body_vg.index if body_vg else None
    
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    bm = bmesh.from_edit_mesh(me)
    bm.verts.ensure_lookup_table()
    
    deform_layer = bm.verts.layers.deform.active
    if not deform_layer:
        deform_layer = bm.verts.layers.deform.verify()
        
    verts_to_delete = []
    for v in bm.verts:
        weights = v[deform_layer]
        
        # Check if vertex belongs to the body
        is_body = body_idx is not None and body_idx in weights and weights[body_idx] > 0
        
        # Check if vertex is marked to be deleted by clothes masks
        under_clothes = False
        for dg_idx in delete_group_indices:
            if dg_idx in weights and weights[dg_idx] > 0.5:
                under_clothes = True
                break
                
        if not is_body or under_clothes:
            verts_to_delete.append(v)
            
    bmesh.ops.delete(bm, geom=verts_to_delete, context='VERTS')
    bmesh.update_edit_mesh(me)
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Clean up mask modifiers from the body mesh (since we deleted geometry)
    for m in list(obj.modifiers):
        if m.type == 'MASK':
            obj.modifiers.remove(m)



def build_shapekeys(obj):
    me = obj.data
    jaw = centroid(group_verts(obj, 'joint-jaw')) if group_verts(obj, 'joint-jaw') else None
    lip_verts = group_verts(obj, 'lips')
    lip_c = centroid(lip_verts)
    head_c = centroid(group_verts(obj, 'joint-head')) if group_verts(obj, 'joint-head') else lip_c + Vector((0, 0.13, 0.035))
    # Landmarks may be gone after deleting helpers; fall back to lips-based estimates.
    if jaw is None:
        jaw = lip_c + Vector((0, 0.005, -0.043))
    # Eye landmarks: estimate from lips/head if joint groups deleted
    ul_l = lip_c + Vector((0.031, -0.012, 0.078))
    ll_l = lip_c + Vector((0.032, -0.013, 0.056))
    ul_r = Vector((-ul_l.x, ul_l.y, ul_l.z))
    ll_r = Vector((-ll_l.x, ll_l.y, ll_l.z))

    if not me.shape_keys:
        obj.shape_key_add(name='Basis', from_mix=False)
    basis = me.shape_keys.key_blocks['Basis']
    upper_cut = lip_c.z + 0.006
    left_corner = max(lip_verts, key=lambda v: v.co.x).co.copy()
    right_corner = min(lip_verts, key=lambda v: v.co.x).co.copy()
    brow_z = ul_l.z + 0.022

    def add_sk(name, disp):
        if me.shape_keys and name in me.shape_keys.key_blocks:
            obj.shape_key_remove(me.shape_keys.key_blocks[name])
        sk = obj.shape_key_add(name=name, from_mix=False)
        for i, v in enumerate(me.vertices):
            d = disp(v.co)
            if d is not None:
                sk.data[i].co = basis.data[i].co + d
        sk.value = 0
        return sk

    def jaw_open(co):
        d = (co - head_c).length
        if d > 0.26 or co.z > upper_cut or co.y > head_c.y + 0.03:
            return None
        lower = jaw.z - 0.12
        f = 1.0 if co.z >= lower else max(0.0, 1 - (lower - co.z) / 0.09)
        vr = min(1.0, (upper_cut - co.z) / 0.05)
        w = vr * f
        if w <= 0:
            return None
        a = 0.55 * w
        rel = co - jaw
        ny = rel.y * math.cos(a) - rel.z * math.sin(a)
        nz = rel.y * math.sin(a) + rel.z * math.cos(a)
        disp = jaw + Vector((rel.x, ny, nz)) - co
        dl = (co - Vector((0, lip_c.y - 0.005, lip_c.z - 0.012))).length
        if dl < 0.03:
            disp += Vector((0, 0, -0.012 * (1 - dl / 0.03)))
        return disp

    def blink(co, ul, ll, side):
        if side > 0 and co.x < 0.004:
            return None
        if side < 0 and co.x > -0.004:
            return None
        d = (co - ul).length
        if d > 0.040:
            return None
        w = 1 - d / 0.040
        return Vector((0, 0, (ll.z - co.z) * w * 0.95))

    def smile(co, corner, sgn):
        d = (co - corner).length
        if d > 0.032:
            return None
        w = 1 - d / 0.032
        return Vector((0.010 * w * sgn, -0.004 * w, 0.013 * w))

    def frown(co, corner, sgn):
        d = (co - corner).length
        if d > 0.030:
            return None
        w = 1 - d / 0.030
        return Vector((0.004 * w * sgn, 0, -0.013 * w))

    def brow_inner(co):
        if co.y > head_c.y or abs(co.x) > 0.05:
            return None
        d = ((co.x) ** 2 + (co.z - brow_z) ** 2) ** 0.5
        if d > 0.045:
            return None
        return Vector((0, 0, 0.013 * (1 - d / 0.045)))

    def brow_down(co, sgn):
        if co.y > head_c.y:
            return None
        cx = 0.030 * sgn
        if (sgn > 0 and co.x < 0.004) or (sgn < 0 and co.x > -0.004):
            return None
        d = ((co.x - cx) ** 2 + (co.z - brow_z) ** 2) ** 0.5
        if d > 0.045:
            return None
        return Vector((0, 0, -0.012 * (1 - d / 0.045)))

    add_sk('jawOpen', jaw_open)
    add_sk('eyeBlinkLeft', lambda c: blink(c, ul_l, ll_l, 1))
    add_sk('eyeBlinkRight', lambda c: blink(c, ul_r, ll_r, -1))
    add_sk('mouthSmileLeft', lambda c: smile(c, left_corner, 1))
    add_sk('mouthSmileRight', lambda c: smile(c, right_corner, -1))
    add_sk('mouthFrownLeft', lambda c: frown(c, left_corner, 1))
    add_sk('mouthFrownRight', lambda c: frown(c, right_corner, -1))
    add_sk('browInnerUp', brow_inner)
    add_sk('browDownLeft', lambda c: brow_down(c, 1))
    add_sk('browDownRight', lambda c: brow_down(c, -1))
    return head_c, ul_l


def make_mat(name, rgb, rough=0.6, metallic=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    bsdf.inputs['Roughness'].default_value = rough
    if 'Metallic' in bsdf.inputs:
        bsdf.inputs['Metallic'].default_value = metallic
    return mat


def assign_materials(obj, palette):
    me = obj.data
    me.materials.clear()
    skin_mat = make_mat('skin', palette['skin'], 0.55)
    lips_mat = make_mat('lips', palette['lips'], 0.45)
    me.materials.append(skin_mat)
    me.materials.append(lips_mat)
    
    lips_idx = {v.index for v in group_verts(obj, 'lips', 0.5)}
    
    for poly in me.polygons:
        vs = poly.vertices
        in_lips = sum(1 for vi in vs if vi in lips_idx) > len(vs) / 2
        if in_lips:
            poly.material_index = 1
        else:
            poly.material_index = 0
    me.update()


def add_eyeballs(obj, head_c, ul_l, palette, rig):
    mesh = obj.data
    zmin = min(v.co.z for v in mesh.vertices)
    zmax = max(v.co.z for v in mesh.vertices)
    height = zmax - zmin
    head_thresh = zmin + height * 0.86
    head_verts = [v for v in mesh.vertices if v.co.z > head_thresh]
    
    head_zmin = min(v.co.z for v in head_verts)
    head_zmax = max(v.co.z for v in head_verts)
    head_height = head_zmax - head_zmin
    head_front_y = min(v.co.y for v in head_verts)
    head_back_y = max(v.co.y for v in head_verts)
    
    eye_z_low  = head_zmin + head_height * 0.50
    eye_z_high = head_zmin + head_height * 0.75
    eye_y_thresh = head_front_y + (head_back_y - head_front_y) * 0.35
    
    eye_socket_verts = [v for v in head_verts
                        if eye_z_low < v.co.z < eye_z_high
                        and v.co.y < eye_y_thresh]
    
    left_verts  = [v for v in eye_socket_verts if v.co.x > 0.01]
    right_verts = [v for v in eye_socket_verts if v.co.x < -0.01]
    
    def centroid(verts, axis):
        return sum(getattr(v.co, axis) for v in verts) / len(verts)
    
    Y_OFFSET = -0.005
    
    if left_verts:
        lx = centroid(left_verts, 'x')
        ly = centroid(left_verts, 'y') + Y_OFFSET
        lz = centroid(left_verts, 'z')
    else:
        lx = 0.0366
        ly = -0.1333
        lz = 1.5625
        
    if right_verts:
        rx = centroid(right_verts, 'x')
        ry = centroid(right_verts, 'y') + Y_OFFSET
        rz = centroid(right_verts, 'z')
    else:
        rx = -0.0366
        ry = -0.1333
        rz = 1.5625

    iris = make_mat('eye', palette['eye_color'], 0.25)
    white = make_mat('eyewhite', (0.93, 0.93, 0.92), 0.3)
    balls = []
    
    # Left Eye
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0135, segments=20, ring_count=14, location=(lx, ly, lz))
    el = bpy.context.active_object
    el.name = 'EyeL'
    el.data.materials.clear()
    el.data.materials.append(white)
    el.data.materials.append(iris)
    for poly in el.data.polygons:
        cc = Vector((0, 0, 0))
        for vi in poly.vertices:
            cc += el.data.vertices[vi].co
        cc /= len(poly.vertices)
        if cc.y < -0.006:
            poly.material_index = 1
    for poly in el.data.polygons:
        poly.use_smooth = True
        
    # Parent to Head bone keeping transform
    if rig:
        old_matrix = el.matrix_world.copy()
        el.parent = rig
        el.parent_type = 'BONE'
        el.parent_bone = 'head'
        el.matrix_world = old_matrix
        
    balls.append(el)
    
    # Right Eye
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0135, segments=20, ring_count=14, location=(rx, ry, rz))
    er = bpy.context.active_object
    er.name = 'EyeR'
    er.data.materials.clear()
    er.data.materials.append(white)
    er.data.materials.append(iris)
    for poly in er.data.polygons:
        cc = Vector((0, 0, 0))
        for vi in poly.vertices:
            cc += er.data.vertices[vi].co
        cc /= len(poly.vertices)
        if cc.y < -0.006:
            poly.material_index = 1
    for poly in er.data.polygons:
        poly.use_smooth = True
        
    # Parent to Head bone keeping transform
    if rig:
        old_matrix = er.matrix_world.copy()
        er.parent = rig
        er.parent_type = 'BONE'
        er.parent_bone = 'head'
        er.matrix_world = old_matrix
        
    balls.append(er)
    
    return balls


def build_character(spec):
    clear_scene()
    obj = HumanService.create_human(mask_helpers=True, detailed_helpers=True,
                                    extra_vertex_groups=True, feet_on_ground=True,
                                    scale=0.1, macro_detail_dict=spec['macro'])
    obj.name = spec['name']
    
    # Add game_engine armature rig to rig character body
    print(f"[{spec['name']}] Adding rig...")
    rig = HumanService.add_builtin_rig(obj, "game_engine")
    
    # Load Clothes, Shoes, Hair using absolute paths
    clothes_path = os.path.join(BASE_DIR, spec['clothes'])
    shoes_path = os.path.join(BASE_DIR, spec['shoes'])
    hair_path = os.path.join(BASE_DIR, spec['hair'])
    
    print(f"[{spec['name']}] Loading clothes: {clothes_path}")
    clothes_obj = HumanService.add_mhclo_asset(clothes_path, obj, asset_type="Clothes")
    
    print(f"[{spec['name']}] Loading shoes: {shoes_path}")
    shoes_obj = HumanService.add_mhclo_asset(shoes_path, obj, asset_type="Clothes")
    
    print(f"[{spec['name']}] Loading hair: {hair_path}")
    hair_obj = HumanService.add_mhclo_asset(hair_path, obj, asset_type="Hair")
    
    # Clean the helper vertices from body skin mesh AFTER fitting assets
    delete_non_body(obj)
    
    # Build facial shape keys (morph targets) on clean body skin
    head_c, ul_l = build_shapekeys(obj)
    
    # Color body skin and lips using textured skin materials
    skin_path = os.path.join(BASE_DIR, spec['skin_path'])
    print(f"[{spec['name']}] Loading skin: {skin_path}")
    HumanService.set_character_skin(skin_path, obj)
    
    for poly in obj.data.polygons:
        poly.use_smooth = True
        
    # Generate and place eyeballs parented to head bone
    balls = add_eyeballs(obj, head_c, ul_l, spec, rig)

    # Select all character meshes + rig for GLB export
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    if rig:
        rig.select_set(True)
    for b in balls:
        b.select_set(True)
    if clothes_obj:
        clothes_obj.select_set(True)
    if shoes_obj:
        shoes_obj.select_set(True)
    if hair_obj:
        hair_obj.select_set(True)
        
    bpy.context.view_layer.objects.active = obj

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, spec['name'] + '.glb')
    bpy.ops.export_scene.gltf(
        filepath=out,
        export_format='GLB',
        use_selection=True,
        export_morph=True,
        export_apply=False,
        export_yup=True,
    )
    return out, len(obj.data.vertices)


def main():
    results = []
    for spec in CHARACTERS:
        path, vc = build_character(spec)
        results.append((spec['name'], path, vc, os.path.getsize(path)))
    for r in results:
        print('EXPORTED:', r)


main()