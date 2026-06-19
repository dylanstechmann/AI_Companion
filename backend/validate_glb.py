"""Validate exported avatar GLBs: parse the binary glTF, list meshes,
primitives, material names, and morph target names. Confirms the files are
structurally valid and carry the ARKit-style morph targets the frontend needs.
"""
import json
import struct
from pathlib import Path

AVATARS = Path('frontend/public/avatars')
EXPECTED_MORPHS = {
    'jawOpen', 'eyeBlinkLeft', 'eyeBlinkRight', 'mouthSmileLeft',
    'mouthSmileRight', 'mouthFrownLeft', 'mouthFrownRight',
    'browInnerUp', 'browDownLeft', 'browDownRight',
}


def parse_glb(path: Path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from('<III', data, 0)
    assert magic == 0x46546C67, f'{path.name}: bad magic (not a GLB)'
    # First chunk = JSON
    chunk_len, chunk_type = struct.unpack_from('<II', data, 12)
    assert chunk_type == 0x4E4F534A, f'{path.name}: first chunk is not JSON'
    gltf = json.loads(data[20:20 + chunk_len].decode('utf-8'))
    return gltf


report = []
for glb in sorted(AVATARS.glob('*_3d.glb')):
    report.append(f'=== {glb.name} ({glb.stat().st_size/1_000_000:.2f} MB) ===')
    gltf = parse_glb(glb)
    materials = [m.get('name', '?') for m in gltf.get('materials', [])]
    report.append(f'  materials ({len(materials)}): {materials}')
    morph_names_all = set()
    for mesh in gltf.get('meshes', []):
        prim_count = len(mesh.get('primitives', []))
        # morph target names live in mesh.extras.targetNames
        tnames = mesh.get('extras', {}).get('targetNames', [])
        has_targets = any('targets' in p for p in mesh.get('primitives', []))
        morph_names_all.update(tnames)
        report.append(
            f'  mesh "{mesh.get("name", "?")}": {prim_count} primitive(s), '
            f'morphs={len(tnames)} {"(targets present)" if has_targets else ""}'
        )
        if tnames:
            report.append(f'    targetNames: {tnames}')
    missing = EXPECTED_MORPHS - morph_names_all
    if missing:
        report.append(f'  WARNING: missing expected morphs: {sorted(missing)}')
    else:
        report.append('  OK: all expected ARKit morph targets present')
    report.append('')

out = '\n'.join(report)
Path('backend/glb_validation.txt').write_text(out, encoding='utf-8')
print(out)