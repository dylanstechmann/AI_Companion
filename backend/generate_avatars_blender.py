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

OUT_DIR = r'c:\Users\AyeBayBay\Projects\AI_Companion\frontend\public\avatars'

# Body-shape macros + material palette per character.
CHARACTERS = [
    {
        'name': 'greg_3d',
        'macro': {'gender': 1.0, 'age': 0.5, 'muscle': 0.82, 'weight': 0.45,
                  'proportions': 0.5, 'height': 0.62, 'cupsize': 0.5, 'firmness': 0.5,
                  'race': {'asian': 0.15, 'caucasian': 0.8, 'african': 0.05}},
        'skin': (0.80, 0.61, 0.49), 'shirt': (0.42, 0.45, 0.50),
        'pants': (0.20, 0.26, 0.40), 'shoes': (0.10, 0.10, 0.12),
        'hair': (0.09, 0.06, 0.04), 'lips': (0.66, 0.40, 0.36),
    },
    {
        'name': 'tiffany_3d',
        'macro': {'gender': 0.0, 'age': 0.45, 'muscle': 0.40, 'weight': 0.46,
                  'proportions': 0.55, 'height': 0.48, 'cupsize': 0.78, 'firmness': 0.62,
                  'race': {'asian': 0.2, 'caucasian': 0.75, 'african': 0.05}},
        'skin': (0.92, 0.75, 0.65), 'shirt': (0.93, 0.93, 0.95),
        'pants': (0.18, 0.18, 0.22), 'shoes': (0.09, 0.09, 0.10),
        'hair': (0.33, 0.19, 0.08), 'lips': (0.80, 0.40, 0.42),
    },
    {
        'name': 'friendly_ai_3d',
        'macro': {'gender': 0.5, 'age': 0.5, 'muscle': 0.5, 'weight': 0.5,
                  'proportions': 0.5, 'height': 0.5, 'cupsize': 0.45, 'firmness': 0.5,
                  'race': {'asian': 0.33, 'caucasian': 0.34, 'african': 0.33}},
        'skin': (0.85, 0.69, 0.61), 'shirt': (0.27, 0.55, 0.63),
        'pants': (0.24, 0.24, 0.30), 'shoes': (0.90, 0.90, 0.92),
        'hair': (0.13, 0.10, 0.08), 'lips': (0.74, 0.44, 0.42),
    },
]


def clear_scene():
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
    """Remove helper cage / joint cubes / helper eyes, keeping only the body skin."""
    me = obj.data
    # drop the mask modifier (we delete geometry instead)
    for m in list(obj.modifiers):
        obj.modifiers.remove(m)
    bidx = obj.vertex_groups['body'].index
    keep = set()
    for v in me.vertices:
        if any(g.group == bidx and g.weight > 0 for g in v.groups):
            keep.add(v.index)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='OBJECT')
    for v in me.vertices:
        v.select = v.index not in keep
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.delete(type='VERT')
    bpy.ops.object.mode_set(mode='OBJECT')


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
    mats = {
        'skin': make_mat('skin', palette['skin'], 0.55),
        'shirt': make_mat('shirt', palette['shirt'], 0.75),
        'pants': make_mat('pants', palette['pants'], 0.8),
        'shoes': make_mat('shoes', palette['shoes'], 0.5),
        'hair': make_mat('hair', palette['hair'], 0.45),
        'lips': make_mat('lips', palette['lips'], 0.45),
    }
    order = ['skin', 'shirt', 'pants', 'shoes', 'hair', 'lips']
    for k in order:
        me.materials.append(mats[k])
    mi = {k: i for i, k in enumerate(order)}

    scalp_idx = {v.index for v in group_verts(obj, 'scalp', 0.5)}
    lips_idx = {v.index for v in group_verts(obj, 'lips', 0.5)}
    zmax = max(v.co.z for v in me.vertices)

    for poly in me.polygons:
        vs = poly.vertices
        c = Vector((0, 0, 0))
        for vi in vs:
            c += me.vertices[vi].co
        c /= len(vs)
        # majority membership tests
        in_scalp = sum(1 for vi in vs if vi in scalp_idx) > len(vs) / 2
        in_lips = sum(1 for vi in vs if vi in lips_idx) > len(vs) / 2
        if in_scalp:
            poly.material_index = mi['hair']
        elif in_lips:
            poly.material_index = mi['lips']
        elif c.z > 0.82 * zmax:
            poly.material_index = mi['skin']        # head + neck
        elif abs(c.x) > 0.20:
            poly.material_index = mi['skin']        # bare arms / hands
        elif c.z > 0.58 * zmax:
            poly.material_index = mi['shirt']       # torso
        elif c.z > 0.10 * zmax:
            poly.material_index = mi['pants']       # hips + legs
        else:
            poly.material_index = mi['shoes']       # feet
    me.update()


def add_eyeballs(obj, head_c, ul_l, palette):
    eye_z = ul_l.z - 0.013
    eye_y = head_c.y - 0.135
    eye_x = 0.031
    iris = make_mat('eye', (0.04, 0.04, 0.05), 0.25)
    white = make_mat('eyewhite', (0.93, 0.93, 0.92), 0.3)
    balls = []
    for sgn, nm in ((1, 'EyeL'), (-1, 'EyeR')):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0135, segments=20, ring_count=14,
                                             location=(eye_x * sgn, eye_y, eye_z))
        e = bpy.context.active_object
        e.name = nm
        e.data.materials.clear()
        e.data.materials.append(white)
        e.data.materials.append(iris)
        # front-facing iris cap = darker
        for poly in e.data.polygons:
            cc = Vector((0, 0, 0))
            for vi in poly.vertices:
                cc += e.data.vertices[vi].co
            cc /= len(poly.vertices)
            if cc.y < e.location.y - 0.006:
                poly.material_index = 1
        for poly in e.data.polygons:
            poly.use_smooth = True
        balls.append(e)
    return balls


def build_character(spec):
    clear_scene()
    obj = HumanService.create_human(mask_helpers=True, detailed_helpers=True,
                                    extra_vertex_groups=True, feet_on_ground=True,
                                    scale=0.1, macro_detail_dict=spec['macro'])
    obj.name = spec['name']
    delete_non_body(obj)
    head_c, ul_l = build_shapekeys(obj)
    assign_materials(obj, spec)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    balls = add_eyeballs(obj, head_c, ul_l, spec)

    # select body + eyeballs for export
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    for b in balls:
        b.select_set(True)
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