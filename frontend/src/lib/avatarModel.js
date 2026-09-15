import * as THREE from 'three';
import { clone as cloneSkeleton } from 'three/examples/jsm/utils/SkeletonUtils.js';
import { isHelperMesh, morphBindings, mpfbMaterialRole } from './avatarMath.js';
import { repairBundledEyes } from './avatarEyes.js';

// Geometry, textures and unchanged authored materials remain owned by useGLTF.
// Only our private material clones and SkeletonUtils skeletons are released.
export function releaseAvatar(instance) {
  for (const material of instance.materials) material.dispose();
  for (const skeleton of instance.skeletons) skeleton.dispose();
}

export function visibleBounds(scene) {
  scene.updateMatrixWorld(true);
  scene.traverse((node) => { if (node.isSkinnedMesh) node.skeleton.update(); });
  const box = new THREE.Box3();
  const vertex = new THREE.Vector3();
  // setFromObject includes hidden helpers and conservative all-morph bounds.
  // Measure the actual rest shape (including body defaults and skinning) once.
  scene.traverseVisible((node) => {
    if (!node.isMesh || !node.geometry?.attributes.position) return;
    const count = node.geometry.attributes.position.count;
    for (let i = 0; i < count; i++) {
      node.getVertexPosition(i, vertex);
      box.expandByPoint(vertex.applyMatrix4(node.matrixWorld));
    }
  });
  if (box.isEmpty() || !Number.isFinite(box.min.y + box.max.y) || box.max.y - box.min.y < 1e-6) {
    throw new Error('The avatar has no visible, finite geometry.');
  }
  return box;
}

function motionJoint(node) {
  if (!node) return null;
  const inverseWorld = node.getWorldQuaternion(new THREE.Quaternion()).invert();
  return {
    node,
    rest: node.quaternion.clone(),
    yawAxis: new THREE.Vector3(0, 1, 0).applyQuaternion(inverseWorld),
    pitchAxis: new THREE.Vector3(1, 0, 0).applyQuaternion(inverseWorld),
    yaw: 0,
    pitch: 0,
    offset: new THREE.Quaternion(),
    target: new THREE.Quaternion(),
  };
}

export function prepareAvatar(source) {
  // scene.clone(true) copies SkinnedMesh bones by reference: never use it here.
  const scene = cloneSkeleton(source);
  const materials = new Set();
  const skeletons = new Set();
  const faces = [];
  let isMPFB = false;
  scene.traverse((node) => {
    if (Object.keys(node.morphTargetDictionary || {}).some((name) => name.startsWith('$md-'))) isMPFB = true;
  });
  const materialClones = new Map();
  const repair = (original) => {
    const role = mpfbMaterialRole(original.name, isMPFB);
    if (!role) return original;
    if (materialClones.has(original)) return materialClones.get(original);
    const material = original.clone();
    materials.add(material);
    materialClones.set(original, material);
    // Bundled skin/clothes have BLEND despite opaque RGB/full-alpha textures.
    // Hair (including bob02/short01) really has alpha: use depth-writing cutouts.
    material.transparent = false;
    material.opacity = 1;
    material.depthWrite = true;
    material.alphaTest = role === 'cutout' ? 0.35 : 0;
    if (role === 'cutout') material.side = THREE.DoubleSide;
    // Keep authored color/normal/roughness textures and double-sided clothing.
    if (role === 'eye' && !material.roughnessMap) {
      material.roughness = original.name === 'eyewhite' ? 0.24 : 0.16;
    }
    return material;
  };
  const joints = {};
  scene.traverse((node) => {
    const name = node.name.toLowerCase().replace(/^mixamorig[:_]?/, '').replace(/[ .:_-]/g, '');
    if (node.isBone && ['head', 'neck', 'neck01', 'spine03', 'chest', 'upperchest'].includes(name)) joints[name] = node;
    if ((node.isBone && /^(lefteye|righteye|eyel|eyer)$/.test(name)) ||
        (isMPFB && /^(eyel|eyer)$/.test(name))) joints[name] = node;
    if (!node.isMesh) return;
    if (isMPFB && isHelperMesh(node.name)) node.visible = false;
    if (node.skeleton) skeletons.add(node.skeleton);
    if (node.material) node.material = Array.isArray(node.material) ? node.material.map(repair) : repair(node.material);
    if (node.morphTargetInfluences) {
      // Explicit independent weights, including every non-zero body macro.
      node.morphTargetInfluences = [...node.morphTargetInfluences];
      const bindings = morphBindings(node.morphTargetDictionary, node.morphTargetInfluences);
      if (bindings.length && node.visible) faces.push({ mesh: node, bindings });
    }
    // Animated heads/hair can extend beyond static GLTF bounds.
    if (node.isSkinnedMesh) node.frustumCulled = false;
  });
  // Repair the known asset-generation eye placement defect before bounds are
  // measured; misplaced eyes otherwise also corrupt portrait normalization.
  const repairedEyes = isMPFB ? repairBundledEyes(scene) : 0;
  let box;
  try {
    box = visibleBounds(scene);
  } catch (error) {
    releaseAvatar({ materials, skeletons });
    throw error;
  }
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const scale = 2.8 / size.y;
  const offset = new THREE.Group();
  offset.position.set(-center.x, -box.min.y, -center.z);
  offset.add(scene);
  const root = new THREE.Group();
  root.scale.setScalar(scale);
  root.add(offset);
  root.updateMatrixWorld(true);
  return {
    root, materials, skeletons, faces, isMPFB, repairedEyes,
    bounds: { width: size.x * scale, height: 2.8, depth: size.z * scale },
    head: motionJoint(joints.head),
    neck: motionJoint(joints.neck || joints.neck01),
    chest: motionJoint(joints.upperchest || joints.chest || joints.spine03),
    eyes: [joints.lefteye || joints.eyel, joints.righteye || joints.eyer].filter(Boolean).map(motionJoint),
  };
}

// Add rotation relative to the bind pose, with axes corrected for the rig's
// local coordinate system. Never overwrite an authored Euler/rest transform.
export function poseJoint(joint, yaw, pitch) {
  if (!joint) return;
  joint.target.copy(joint.rest);
  joint.offset.setFromAxisAngle(joint.yawAxis, yaw);
  joint.target.multiply(joint.offset);
  joint.offset.setFromAxisAngle(joint.pitchAxis, pitch);
  joint.target.multiply(joint.offset);
  joint.node.quaternion.copy(joint.target);
}
