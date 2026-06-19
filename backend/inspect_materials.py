"""Extract material base colors, metallic/roughness, and texture references
from the avatar GLB files to diagnose the 'grey clay' rendering."""
import json
import struct
from pathlib import Path

AVATARS = Path('frontend/public/avatars')


def parse_glb(path: Path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from('<III', data, 0)
    assert magic == 0x46546C67
    chunk_len, chunk_type = struct.unpack_from('<II', data, 12)
    gltf = json.loads(data[20:20 + chunk_len].decode('utf-8'))
    return gltf


for glb in sorted(AVATARS.glob('*_3d.glb')):
    g = parse_glb(glb)
    print(f'=== {glb.name} ===')
    print(f'  #images={len(g.get("images", []))} #textures={len(g.get("textures", []))} #samplers={len(g.get("samplers", []))}')
    for m in g.get('materials', []):
        pbr = m.get('pbrMetallicRoughness', {})
        base = pbr.get('baseColorFactor', [1, 1, 1, 1])
        metallic = pbr.get('metallicFactor', 1.0)
        rough = pbr.get('roughnessFactor', 1.0)
        base_tex = 'baseColorTexture' in pbr
        emissive = m.get('emissiveFactor', [0, 0, 0])
        base_str = '[' + ', '.join(f'{c:.3f}' for c in base) + ']'
        print(f'  "{m.get("name")}": baseColor={base_str} '
              f'metallic={metallic} roughness={rough} baseColorTex={base_tex} '
              f'emissive={emissive} alphaMode={m.get("alphaMode", "OPAQUE")}')
    print()