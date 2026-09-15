import * as THREE from 'three';

// The generator assigns a single iris color to nearly the entire front
// hemisphere, so the original eyes read as solid blue/green balls. Add a
// smaller iris, dark pupil and limbal edge on that EXISTING spherical cap.
// This changes only private cloned materials of the recognized bundled eyes:
// no new geometry, textures, draw calls or external assets.
export function detailBundledEye(eye) {
  let sclera;
  eye.traverse((node) => {
    if (node.material?.name === 'eyewhite') sclera = node.material.color;
  });
  if (!sclera) return;
  eye.traverse((node) => {
    const material = node.material;
    if (material?.name !== 'eye' || material.map || material.userData.avatarEyeDetail) return;
    material.userData.avatarEyeDetail = true;
    material.roughness = 0.22;
    material.onBeforeCompile = (shader) => {
      shader.uniforms.avatarScleraColor = { value: sclera };
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vAvatarEyePosition;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvAvatarEyePosition = position;');
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vAvatarEyePosition;\nuniform vec3 avatarScleraColor;')
        .replace('#include <color_fragment>', `#include <color_fragment>
          // All three recognized exports use radius-0.0135 eye spheres.
          float avatarEyeRadius = length(vAvatarEyePosition.xy) / 0.0135;
          float avatarIris = 1.0 - smoothstep(0.44, 0.48, avatarEyeRadius);
          float avatarPupil = 1.0 - smoothstep(0.17, 0.20, avatarEyeRadius);
          float avatarLimbal = 1.0 - smoothstep(0.37, 0.46, avatarEyeRadius);
          vec3 avatarIrisColor = diffuseColor.rgb * mix(0.3, 1.0, avatarLimbal);
          diffuseColor.rgb = mix(avatarScleraColor, avatarIrisColor, avatarIris);
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.004, 0.005, 0.007), avatarPupil);
        `);
    };
    material.customProgramCacheKey = () => 'bundled-mpfb-eye-detail-v1';
    material.needsUpdate = true;
  });
}

// These three bundled exports place rigid eyeballs using unmorphed landmarks:
// Greg's eyes end up at his collar, Tiffany's above her head. Recover the actual
// socket rims from their known MPFB topology, evaluated WITH body morphs.
// Never reposition eyes on arbitrary user models or an unrecognized topology.
export function repairBundledEyes(scene) {
  let body;
  scene.traverse((node) => {
    if (node.isSkinnedMesh && /^(greg|tiffany|friendly_ai)_3d\.body$/i.test(node.material?.name || '') &&
        node.morphTargetDictionary?.eyeBlinkLeft !== undefined) body = node;
  });
  const left = scene.getObjectByName('EyeL');
  const right = scene.getObjectByName('EyeR');
  if (!body?.geometry.index || !left || !right || left.isBone || right.isBone) return 0;
  scene.updateMatrixWorld(true);
  body.skeleton.update();
  const geometry = body.geometry;
  const edges = new Map();
  const index = geometry.index;
  const addEdge = (a, b) => {
    const key = a < b ? `${a}:${b}` : `${b}:${a}`;
    edges.set(key, (edges.get(key) || 0) + 1);
  };
  for (let i = 0; i < index.count; i += 3) {
    const a = index.getX(i); const b = index.getX(i + 1); const c = index.getX(i + 2);
    addEdge(a, b); addEdge(b, c); addEdge(c, a);
  }
  const neighbors = new Map();
  for (const [edge, count] of edges) {
    if (count !== 1) continue;
    const [a, b] = edge.split(':').map(Number);
    if (!neighbors.has(a)) neighbors.set(a, []);
    if (!neighbors.has(b)) neighbors.set(b, []);
    neighbors.get(a).push(b);
    neighbors.get(b).push(a);
  }
  const visited = new Set();
  const sockets = [new THREE.Box3(), new THREE.Box3()];
  const point = new THREE.Vector3();
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  for (const start of neighbors.keys()) {
    if (visited.has(start)) continue;
    const pending = [start];
    const vertices = [];
    while (pending.length) {
      const vertex = pending.pop();
      if (visited.has(vertex)) continue;
      visited.add(vertex);
      vertices.push(vertex);
      pending.push(...neighbors.get(vertex));
    }
    // Each eyelid seam in these specific assets is a 28-vertex oval. Material
    // splits produce duplicate rims, unioning both gives the same anchor.
    if (vertices.length !== 28) continue;
    const base = new THREE.Box3();
    for (const vertex of vertices) base.expandByPoint(point.fromBufferAttribute(geometry.attributes.position, vertex));
    base.getSize(size);
    base.getCenter(center);
    if (size.x < 0.015 || size.x > 0.035 || size.y > 0.016 || size.z > 0.02 ||
        Math.abs(center.x) < 0.02 || Math.abs(center.x) > 0.06 || center.y < 1.5 || center.z < 0.1) continue;
    const socket = sockets[center.x > 0 ? 0 : 1];
    for (const vertex of vertices) {
      body.getVertexPosition(vertex, point);
      socket.expandByPoint(point.applyMatrix4(body.matrixWorld));
    }
  }
  // Require both valid rims before making any changes.
  if (sockets.some((socket) => socket.isEmpty())) return 0;
  [left, right].forEach((eye, i) => {
    const socket = sockets[i];
    socket.getCenter(center);
    const eyeSize = new THREE.Box3().setFromObject(eye).getSize(size);
    // Seat the sphere just behind the rim; preserve its mesh, color and radius.
    center.z -= eyeSize.x * 0.11;
    eye.parent.worldToLocal(center);
    eye.position.copy(center);
    detailBundledEye(eye);
  });
  scene.updateMatrixWorld(true);
  return 2;
}
