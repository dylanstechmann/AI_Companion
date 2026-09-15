import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { prepareAvatar, releaseAvatar } from '../src/lib/avatarModel.js';

// Parse real bundled geometry/rigs without WebGL or decoding images in Node.
const loader = new GLTFLoader();
loader.register(() => ({ name: 'TEST_TEXTURE_STUB', loadTexture: async () => new THREE.Texture() }));
for (const [name, expectedEyeHeight] of [['greg', 1.7673], ['tiffany', 1.4300], ['friendly_ai', 1.5525]]) {
  test(`${name}: actual bundled GLB preserves body shape, repairs both eye sockets and isolates the skeleton`, async () => {
    const bytes = await readFile(new URL(`../public/avatars/${name}_3d.glb`, import.meta.url));
    const gltf = await loader.parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '');
    const before = gltf.scene.getObjectByName('EyeL').position.clone();
    const avatar = prepareAvatar(gltf.scene);
    assert.equal(avatar.repairedEyes, 2);
    assert.ok(avatar.head);
    assert.ok(avatar.neck);
    assert.ok(avatar.chest);
    assert.equal(avatar.eyes.length, 2);
    const eye = avatar.root.getObjectByName('EyeL');
    // Undo the normalizing groups to inspect the repaired exported coordinates.
    const sourceSpace = eye.getWorldPosition(new THREE.Vector3());
    avatar.root.children[0].worldToLocal(sourceSpace);
    assert.ok(Math.abs(sourceSpace.y - expectedEyeHeight) < 0.001, `socket height was ${sourceSpace.y}`);
    assert.ok(Math.abs(sourceSpace.x) > 0.02 && Math.abs(sourceSpace.x) < 0.045);
    let detailedIris;
    eye.traverse((node) => { if (node.material?.name === 'eye') detailedIris = node.material; });
    assert.ok(detailedIris?.userData.avatarEyeDetail);
    const shader = {
      uniforms: {},
      vertexShader: '#include <common>\n#include <begin_vertex>',
      fragmentShader: '#include <common>\n#include <color_fragment>',
    };
    detailedIris.onBeforeCompile(shader);
    assert.match(shader.vertexShader, /vAvatarEyePosition = position/);
    assert.match(shader.fragmentShader, /avatarPupil/);
    assert.match(shader.fragmentShader, /avatarScleraColor, avatarIrisColor/);
    assert.ok(shader.uniforms.avatarScleraColor.value.isColor);
    assert.equal(detailedIris.map, null); // No generated texture or extra asset.
    gltf.scene.getObjectByName('EyeL').traverse((node) => {
      assert.equal(node.material?.userData.avatarEyeDetail, undefined);
    });
    assert.deepEqual(gltf.scene.getObjectByName('EyeL').position.toArray(), before.toArray());
    assert.ok(avatar.faces.some(({ mesh }) => Object.entries(mesh.morphTargetDictionary).some(
      ([key, index]) => key.startsWith('$md-') && mesh.morphTargetInfluences[index] > 0)));
    assert.equal(gltf.animations.length, 0);
    releaseAvatar(avatar);
  });
}
