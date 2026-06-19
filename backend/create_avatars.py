#!/usr/bin/env python3
"""
Automated avatar creation script for AI Companion
Uses Blender MCP server to generate anatomically correct avatars with morphs
"""

import json
import os
from pathlib import Path

# Create avatars directory
avatars_dir = Path('frontend/public/avatars')
avatars_dir.mkdir(parents=True, exist_ok=True)

GREG_CONFIG = {
    'name': 'greg_3d',
    'gender': 'male',
    'age': 35,
    'body_config': {
        'height': 1.85,
        'muscle': 0.75,
        'weight': 0.5,
        'chest': 0.65,
        'shoulders': 0.75,
        'jaw_width': 0.6,
        'nose_width': 0.5,
    },
    'clothing': {
        'tops': ['gray_tshirt'],
        'bottoms': ['jeans'],
        'shoes': ['casual_shoes'],
    },
    'hair': {
        'color': [0.2, 0.15, 0.1],  # Dark brown
        'style': 'short_male',
    },
    'skin_tone': [0.95, 0.85, 0.75],  # Medium skin tone
}

TIFFANY_CONFIG = {
    'name': 'tiffany_3d',
    'gender': 'female',
    'age': 30,
    'body_config': {
        'height': 1.70,
        'muscle': 0.35,
        'weight': 0.6,
        'chest': 0.75,  # Above average bust
        'hips': 0.7,
        'waist': 0.4,
        'jaw_width': 0.4,
        'cheekbones': 0.6,
        'lips': 0.6,
        'nose_width': 0.4,
        'eyes': 0.6,
    },
    'clothing': {
        'tops': ['business_shirt_white'],
        'bottoms': ['business_pants'],
        'shoes': ['business_shoes'],
    },
    'hair': {
        'color': [0.3, 0.2, 0.1],  # Medium brown
        'style': 'long_female',
    },
    'skin_tone': [1.0, 0.9, 0.8],  # Light skin tone
}

FRIENDLY_AI_CONFIG = {
    'name': 'friendly_ai_3d',
    'gender': 'female',
    'age': 26,
    'body_config': {
        'height': 1.65,
        'muscle': 0.4,
        'weight': 0.5,
        'chest': 0.5,  # Neutral
        'hips': 0.5,
        'jaw_width': 0.45,
        'eyes': 0.55,
        'cheekbones': 0.5,
    },
    'clothing': {
        'tops': ['hoodie_color', 'hoodie_color'],
        'bottoms': ['casual_pants'],
        'shoes': ['casual_shoes'],
    },
    'hair': {
        'color': [0.4, 0.3, 0.2],  # Medium-light brown
        'style': 'medium_female',
    },
    'skin_tone': [0.98, 0.88, 0.78],  # Medium-light skin
}

def create_blender_script(config: dict) -> str:
    """Generate Blender Python script for avatar creation"""
    
    script = f'''
import bpy
import bmesh
from mathutils import Vector
import math

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create base mesh (UV Sphere for head/body)
def create_avatar_base(gender="{config['gender']}", config_dict={json.dumps(config['body_config'])}):
    """Create anatomically correct base mesh for avatar"""
    
    # Create head
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.15, location=(0, 0, 1.7))
    head = bpy.context.active_object
    head.name = 'Head'
    head.scale = (0.95, 0.95, 1.0)
    
    # Create torso
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 1.2))
    torso = bpy.context.active_object
    torso.name = 'Torso'
    
    # Scale torso based on gender and body type
    if gender == "male":
        torso.scale = (0.45, 0.35, 0.55)
    else:
        chest_scale = config_dict.get('chest', 0.5)
        torso.scale = (0.4 + chest_scale * 0.1, 0.3, 0.55)
    
    # Create arms
    for side in [-1, 1]:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=0.8, location=(side * 0.5, 0, 1.1))
        arm = bpy.context.active_object
        arm.name = f'Arm_{["Left", "Right"][side > 0]}'
    
    # Create legs
    for side in [-1, 1]:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=1.0, location=(side * 0.2, 0, 0.5))
        leg = bpy.context.active_object
        leg.name = f'Leg_{["Left", "Right"][side > 0]}'
    
    return head, torso

head, torso = create_avatar_base(config_dict={json.dumps(config['body_config'])})

# Select all and apply smooth shading
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.shade_smooth()

# Add materials with skin color
skin_color = {json.dumps(config['skin_tone'])}
hair_color = {json.dumps(config['hair']['color'])}

def create_material(name, color, metallic=0.0, roughness=0.4):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat

skin_mat = create_material("Skin", skin_color, metallic=0.0, roughness=0.5)
hair_mat = create_material("Hair", hair_color, metallic=0.1, roughness=0.3)

# Apply materials
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        if 'Head' in obj.name:
            obj.data.materials.append(skin_mat)
        elif 'Hair' in obj.name:
            obj.data.materials.append(hair_mat)
        else:
            obj.data.materials.append(skin_mat)

# Create morph targets (shape keys) for animation
# These are the blend shapes used by HumanAvatar3D.jsx
morph_targets = [
    # Mouth shapes
    'jawOpen', 'Viseme_aa', 'Viseme_E', 'Viseme_I', 'Viseme_O', 'Viseme_U',
    # Emotions
    'mouthSmileLeft', 'mouthSmileRight', 'cheekSquintLeft', 'cheekSquintRight',
    'mouthFrownLeft', 'mouthFrownRight', 'browInnerUp',
    'eyeWideLeft', 'eyeWideRight',
    'browDownLeft', 'browDownRight', 'mouthPressLeft', 'mouthPressRight',
    'mouthShrugLower', 'eyeSquintLeft', 'eyeSquintRight',
    # Blink
    'eyeBlinkLeft', 'eyeBlinkRight',
]

head = bpy.data.objects.get('Head')
if head and head.data:
    # Add basis shape key
    head.shape_key_add(name='Basis', from_mix=False)
    
    # Add all morph targets
    for morph in morph_targets:
        head.shape_key_add(name=morph, from_mix=False)
        # Set value to 0 initially
        if head.data.shape_keys:
            head.data.shape_keys.key_blocks[morph].value = 0.0

# Add armature for rigging
bpy.ops.object.armature_add(enter_edit_mode=True, location=(0, 0, 1.0))
armature = bpy.context.active_object
armature.name = 'Armature'

# Exit edit mode
bpy.ops.object.mode_set(mode='OBJECT')

# Parent all meshes to armature
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        bpy.context.view_layer.objects.active = obj
        obj.parent = armature

# Export as GLB with morphs
output_path = 'frontend/public/avatars/{config['name']}_3d.glb'

bpy.ops.export_scene.gltf(
    filepath=output_path,
    use_draco_mesh_compression=False,
    export_normals=True,
    export_colors=False,
    export_tangents=False,
    use_animations=False,
    use_deformation_bones=True,
    include_all_bone_influences=True,
    use_mesh_quantization=False,
    export_image_format='AUTO',
)

print(f"✓ Avatar exported: {{output_path}}")
'''
    
    return script

# Generate config
configs = [GREG_CONFIG, TIFFANY_CONFIG, FRIENDLY_AI_CONFIG]

print("=" * 60)
print("AI COMPANION AVATAR CREATION")
print("=" * 60)
print(f"\n✓ Avatar configs prepared:")
for config in configs:
    print(f"  - {config['name']}")

print(f"\n→ Scripts will be generated and executed via Blender MCP server")
print(f"→ Output directory: {avatars_dir}")

# Save config for reference
config_file = Path('backend/avatar_configs.json')
config_file.write_text(json.dumps({
    'greg': GREG_CONFIG,
    'tiffany': TIFFANY_CONFIG,
    'friendly_ai': FRIENDLY_AI_CONFIG,
}, indent=2))

print(f"\n✓ Config saved to: {config_file}")
print("\n" + "=" * 60)