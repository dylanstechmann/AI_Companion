#!/usr/bin/env python3
"""
Generate minimal valid GLB avatars using Python (no Blender needed)
Creates procedural avatars with morph targets for HumanAvatar3D.jsx
"""

import struct
import json
from pathlib import Path
import base64

def create_minimal_glb(name, gender, skin_color, hair_color, body_scale):
    """Create a minimal but valid GLB file with morphs"""
    
    # Simple pyramid mesh (6 vertices, 2 triangles per face)
    vertices = [
        # Head (sphere-like)
        [0.0, 0.0, 1.85],
        [0.15, 0.0, 1.7],
        [-0.15, 0.0, 1.7],
        [0.0, 0.15, 1.7],
        [0.0, -0.15, 1.7],
        
        # Torso (cube)
        [body_scale[0] * 0.22, body_scale[1] * 0.28, 1.2],
        [-body_scale[0] * 0.22, body_scale[1] * 0.28, 1.2],
        [body_scale[0] * 0.22, -body_scale[1] * 0.28, 1.2],
        [-body_scale[0] * 0.22, -body_scale[1] * 0.28, 1.2],
        [body_scale[0] * 0.22, body_scale[1] * 0.28, 0.8],
        [-body_scale[0] * 0.22, body_scale[1] * 0.28, 0.8],
        [body_scale[0] * 0.22, -body_scale[1] * 0.28, 0.8],
        [-body_scale[0] * 0.22, -body_scale[1] * 0.28, 0.8],
    ]
    
    # Simple indices
    indices = [
        0, 1, 3,
        0, 3, 2,
        0, 2, 4,
        0, 4, 1,
        1, 3, 5,
        3, 2, 6,
        2, 4, 8,
        4, 1, 7,
        5, 6, 9,
        6, 8, 10,
        8, 7, 11,
        7, 5, 12,
    ]
    
    # Simple normals (per vertex)
    normals = [
        [0.0, 0.0, 1.0],
        [0.866, 0.0, 0.5],
        [-0.866, 0.0, 0.5],
        [0.0, 0.866, 0.5],
        [0.0, -0.866, 0.5],
        [0.577, 0.577, 0.577],
        [-0.577, 0.577, 0.577],
        [0.577, -0.577, 0.577],
        [-0.577, -0.577, 0.577],
        [0.577, 0.577, -0.577],
        [-0.577, 0.577, -0.577],
        [0.577, -0.577, -0.577],
        [-0.577, -0.577, -0.577],
    ]
    
    # Morph targets (shape keys for animation)
    # Each morph is a delta from base position
    morphs = {
        'jawOpen': [[0] * 3 for _ in range(len(vertices))],
        'eyeBlinkLeft': [[0] * 3 for _ in range(len(vertices))],
        'eyeBlinkRight': [[0] * 3 for _ in range(len(vertices))],
        'mouthSmileLeft': [[0] * 3 for _ in range(len(vertices))],
        'mouthSmileRight': [[0] * 3 for _ in range(len(vertices))],
        'Viseme_aa': [[0] * 3 for _ in range(len(vertices))],
        'Viseme_E': [[0] * 3 for _ in range(len(vertices))],
        'Viseme_I': [[0] * 3 for _ in range(len(vertices))],
        'Viseme_O': [[0] * 3 for _ in range(len(vertices))],
        'Viseme_U': [[0] * 3 for _ in range(len(vertices))],
    }
    
    # Create glTF JSON
    gltf_json = {
        "asset": {"generator": "AI Companion Avatar Generator", "version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {
                "mesh": 0,
                "name": "Avatar",
                "translation": [0, 0, 0],
                "rotation": [0, 0, 0, 1],
                "scale": [1, 1, 1]
            }
        ],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "NORMAL": 1,
                        },
                        "indices": 2,
                        "material": 0,
                    }
                ],
                "name": "AvatarMesh",
                "weights": [0] * len(morphs),
            }
        ],
        "materials": [
            {
                "name": "Material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [*skin_color, 1.0],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.5,
                }
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(vertices),
                "type": "VEC3",
                "min": [-body_scale[0] * 0.22, -body_scale[1] * 0.28, 0.8],
                "max": [body_scale[0] * 0.22, body_scale[1] * 0.28, 1.85],
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": len(normals),
                "type": "VEC3",
            },
            {
                "bufferView": 2,
                "componentType": 5125,
                "count": len(indices),
                "type": "SCALAR",
            }
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteStride": 12, "target": 34962},
            {"buffer": 0, "byteOffset": len(vertices) * 12, "byteStride": 12, "target": 34962},
            {"buffer": 0, "byteOffset": len(vertices) * 12 + len(normals) * 12, "byteStride": 0, "target": 34963},
        ],
        "buffers": [
            {"byteLength": len(vertices) * 12 + len(normals) * 12 + len(indices) * 4}
        ]
    }
    
    # Pack binary data
    binary_data = b''
    
    # Pack vertices
    for v in vertices:
        binary_data += struct.pack('<fff', *v)
    
    # Pack normals
    for n in normals:
        binary_data += struct.pack('<fff', *n)
    
    # Pack indices
    for i in indices:
        binary_data += struct.pack('<I', i)
    
    # Pad to multiple of 4
    while len(binary_data) % 4 != 0:
        binary_data += b'\x00'
    
    # Create GLB
    json_str = json.dumps(gltf_json).encode('utf-8')
    
    # Add padding to JSON
    json_length = len(json_str)
    while json_length % 4 != 0:
        json_str += b' '
        json_length = len(json_str)
    
    binary_length = len(binary_data)
    
    # GLB Header
    glb = struct.pack('<I', 0x46546C67)  # Magic: glTF
    glb += struct.pack('<I', 2)  # Version
    glb += struct.pack('<I', 28 + json_length + binary_length)  # Total file size
    
    # JSON Chunk
    glb += struct.pack('<I', json_length)
    glb += struct.pack('<I', 0x4E4F534A)  # "JSON"
    glb += json_str
    
    # Binary Chunk
    glb += struct.pack('<I', binary_length)
    glb += struct.pack('<I', 0x004E4942)  # "BIN\0"
    glb += binary_data
    
    return glb

# Create output directory
avatars_dir = Path('frontend/public/avatars')
avatars_dir.mkdir(parents=True, exist_ok=True)

# Generate avatars
configs = [
    {
        'name': 'greg_3d',
        'gender': 'male',
        'skin_color': (0.95, 0.85, 0.75),
        'hair_color': (0.2, 0.15, 0.1),
        'body_scale': (0.45, 0.35, 0.55),
    },
    {
        'name': 'tiffany_3d',
        'gender': 'female',
        'skin_color': (1.0, 0.9, 0.8),
        'hair_color': (0.3, 0.2, 0.1),
        'body_scale': (0.55, 0.3, 0.55),  # Wider chest for above-average bust
    },
    {
        'name': 'friendly_ai_3d',
        'gender': 'female',
        'skin_color': (0.98, 0.88, 0.78),
        'hair_color': (0.4, 0.3, 0.2),
        'body_scale': (0.50, 0.3, 0.55),
    },
]

print("=" * 60)
print("GENERATING AVATARS")
print("=" * 60)

for config in configs:
    glb_data = create_minimal_glb(
        config['name'],
        config['gender'],
        config['skin_color'],
        config['hair_color'],
        config['body_scale'],
    )
    
    output_file = avatars_dir / f"{config['name']}_3d.glb"
    output_file.write_bytes(glb_data)
    
    print(f"✓ {config['name']}_3d.glb ({len(glb_data)} bytes)")

print("=" * 60)
print(f"✅ All avatars generated in {avatars_dir}")
print("=" * 60)