import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { prepareAvatar, releaseAvatar, poseJoint, visibleBounds } from '../src/lib/avatarModel.js';

function fixture() {
  const scene = new THREE.Group();
  const head = new THREE.Bone();
  head.name = 'head';
  const geometry = new THREE.BoxGeometry(1, 2, 0.5);
  geometry.translate(0, 1, 0);
  const position = geometry.attributes.position;
  geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(new Uint16Array(position.count * 4), 4));
  const weights = new Float32Array(position.count * 4);
  for (let i = 0; i < position.count; i++) weights[i * 4] = 1;
  geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(weights, 4));
  geometry.morphTargetsRelative = true;
  geometry.morphAttributes.position = [
    new THREE.Float32BufferAttribute(new Float32Array(position.count * 3).fill(0.1), 3),
    new THREE.Float32BufferAttribute(new Float32Array(position.count * 3), 3),
  ];
  const texture = new THREE.Texture();
  const material = new THREE.MeshStandardMaterial({ transparent: true, map: texture, roughness: 0.45 });
  material.name = 'greg_3d.body';
  const mesh = new THREE.SkinnedMesh(geometry, material);
  mesh.name = 'Human';
  mesh.morphTargetDictionary = { '$md-body': 0, jawOpen: 1 };
  mesh.morphTargetInfluences = [0.6, 0];
  scene.add(head, mesh);
  mesh.bind(new THREE.Skeleton([head]));
  const helper = new THREE.Mesh(new THREE.BoxGeometry(80, 80, 80), material);
  helper.name = 'Human.high-poly';
  scene.add(helper);
  return { scene, head, mesh, material, geometry, texture, helper };
}

test('SkeletonUtils clone owns bones, skeletons and morph weights but shares geometry/textures safely', () => {
  const source = fixture();
  const avatar = prepareAvatar(source.scene);
  const cloned = avatar.root.getObjectByName('Human');
  assert.notEqual(cloned.skeleton, source.mesh.skeleton);
  assert.notEqual(cloned.skeleton.bones[0], source.head);
  assert.equal(cloned.skeleton.bones[0], avatar.head.node);
  assert.notEqual(cloned.morphTargetInfluences, source.mesh.morphTargetInfluences);
  assert.equal(cloned.morphTargetInfluences[0], 0.6);
  cloned.morphTargetInfluences[1] = 0.5;
  assert.equal(source.mesh.morphTargetInfluences[1], 0);
  assert.equal(cloned.geometry, source.geometry);
  assert.equal(cloned.material.map, source.texture);
  assert.notEqual(cloned.material, source.material);
  assert.equal(cloned.material.transparent, false);
  assert.equal(source.material.transparent, true);
  releaseAvatar(avatar);
});

test('helpers are hidden before framing; actual morphed body has feet at zero and height 2.8', () => {
  const source = fixture();
  const avatar = prepareAvatar(source.scene);
  assert.equal(avatar.root.getObjectByName('Human.high-poly').visible, false);
  assert.equal(source.helper.visible, true);
  assert.ok(Math.abs(avatar.bounds.height - 2.8) < 1e-6);
  assert.ok(avatar.bounds.width < 2);
  const box = visibleBounds(avatar.root);
  assert.ok(Math.abs(box.min.y) < 1e-6);
  assert.ok(Math.abs(box.max.y - 2.8) < 1e-6);
  releaseAvatar(avatar);
});

test('cleanup releases private material and bone textures, never cached geometry/material/textures', () => {
  const source = fixture();
  const avatar = prepareAvatar(source.scene);
  const sharedEvents = [];
  source.geometry.addEventListener('dispose', () => sharedEvents.push('geometry'));
  source.material.addEventListener('dispose', () => sharedEvents.push('material'));
  source.texture.addEventListener('dispose', () => sharedEvents.push('texture'));
  let releasedMaterials = 0;
  let releasedBones = 0;
  avatar.materials.forEach((material) => material.addEventListener('dispose', () => releasedMaterials++));
  avatar.skeletons.forEach((skeleton) => {
    skeleton.computeBoneTexture();
    skeleton.boneTexture.addEventListener('dispose', () => releasedBones++);
  });
  releaseAvatar(avatar);
  assert.deepEqual(sharedEvents, []);
  assert.equal(releasedMaterials, avatar.materials.size);
  assert.equal(releasedBones, avatar.skeletons.size);
});

test('custom authored transparent materials remain unchanged, including MPFB accessories', () => {
  const source = fixture();
  const glass = new THREE.MeshPhysicalMaterial({ transparent: true, opacity: 0.3, transmission: 0.8 });
  glass.name = 'designer glasses';
  const accessory = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.1), glass);
  accessory.name = 'accessory';
  source.scene.add(accessory);
  const avatar = prepareAvatar(source.scene);
  assert.equal(avatar.root.getObjectByName('accessory').material, glass);
  assert.equal(glass.opacity, 0.3);
  assert.equal(glass.transmission, 0.8);
  releaseAvatar(avatar);
});

test('head gaze is independent and zero offset restores exact bind orientation', () => {
  const source = fixture();
  source.head.rotation.x = 0.1;
  const avatar = prepareAvatar(source.scene);
  const bindPose = avatar.head.rest.clone();
  poseJoint(avatar.head, 0.1, 0.05);
  assert.notDeepEqual(avatar.head.node.quaternion.toArray(), bindPose.toArray());
  assert.deepEqual(source.head.quaternion.toArray(), bindPose.toArray());
  poseJoint(avatar.head, 0, 0);
  assert.deepEqual(avatar.head.node.quaternion.toArray(), bindPose.toArray());
  releaseAvatar(avatar);
});

test('empty or malformed visible models fail clearly instead of producing invalid framing', () => {
  assert.throws(() => prepareAvatar(new THREE.Group()), /visible, finite geometry/);
});
