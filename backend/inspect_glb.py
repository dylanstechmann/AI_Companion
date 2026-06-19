"""Deeper GLB inspection: asset metadata, extensions used/required, and
per-primitive morph-target attribute counts (a likely cause of GLTFLoader
failures in three.js)."""
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
    print('  asset:', g.get('asset'))
    print('  extensionsUsed:', g.get('extensionsUsed'))
    print('  extensionsRequired:', g.get('extensionsRequired'))
    print('  #accessors:', len(g.get('accessors', [])),
          '#bufferViews:', len(g.get('bufferViews', [])),
          '#images:', len(g.get('images', [])))
    for mi, mesh in enumerate(g.get('meshes', [])):
        for pi, prim in enumerate(mesh.get('primitives', [])):
            attrs = list(prim.get('attributes', {}).keys())
            ntargets = len(prim.get('targets', []))
            tkeys = set()
            for t in prim.get('targets', []):
                tkeys.update(t.keys())
            print(f'  mesh[{mi}] "{mesh.get("name")}" prim[{pi}] '
                  f'mat={prim.get("material")} attrs={attrs} '
                  f'targets={ntargets} targetAttrs={sorted(tkeys)}')
    # material alpha modes
    for m in g.get('materials', []):
        print(f'    material "{m.get("name")}": alphaMode={m.get("alphaMode", "OPAQUE")} '
              f'ext={list(m.get("extensions", {}).keys())}')
    print()