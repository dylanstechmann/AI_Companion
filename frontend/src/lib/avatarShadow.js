import * as THREE from 'three';
import { HorizontalBlurShader } from 'three/examples/jsm/shaders/HorizontalBlurShader.js';
import { VerticalBlurShader } from 'three/examples/jsm/shaders/VerticalBlurShader.js';

// One contact-shadow bake per avatar/quality change, not a shadow render pass
// per animation frame. Own all offscreen resources so switching models does
// not leak render targets (nor dispose anything from the GLTF cache).
export function createAvatarShadow(resolution, width = 4) {
  const target = new THREE.WebGLRenderTarget(resolution, resolution);
  const blurTarget = new THREE.WebGLRenderTarget(resolution, resolution);
  target.texture.generateMipmaps = blurTarget.texture.generateMipmaps = false;
  const depth = new THREE.MeshDepthMaterial();
  depth.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      'vec4( vec3( 1.0 - fragCoordZ ), opacity );',
      'vec4( vec3( 0.06, 0.04, 0.09 ), ( 1.0 - fragCoordZ ) );',
    );
  };
  const horizontal = new THREE.ShaderMaterial(HorizontalBlurShader);
  const vertical = new THREE.ShaderMaterial(VerticalBlurShader);
  horizontal.depthTest = vertical.depthTest = false;
  horizontal.depthWrite = vertical.depthWrite = false;
  const geometry = new THREE.PlaneGeometry(2, 2);
  const quad = new THREE.Mesh(geometry, horizontal);
  const blurScene = new THREE.Scene();
  blurScene.add(quad);
  const screenCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 2);
  screenCamera.position.z = 1;
  const camera = new THREE.OrthographicCamera(-width / 2, width / 2, width / 2, -width / 2, 0, 3.2);
  camera.position.set(0, -0.025, 0);
  camera.up.set(0, 0, 1);
  camera.lookAt(0, 1, 0);
  camera.updateMatrixWorld();
  return {
    texture: target.texture,
    width,
    bake(gl, scene, plane) {
      const previousTarget = gl.getRenderTarget();
      const background = scene.background;
      const override = scene.overrideMaterial;
      const clearColor = gl.getClearColor(new THREE.Color());
      const clearAlpha = gl.getClearAlpha();
      const autoClear = gl.autoClear;
      const visible = plane.visible;
      try {
        plane.visible = false;
        scene.background = null;
        scene.overrideMaterial = depth;
        gl.autoClear = true;
        gl.setClearColor(0x000000, 0);
        gl.setRenderTarget(target);
        gl.render(scene, camera);
        scene.overrideMaterial = null;
        for (const amount of [2.2, 0.8]) {
          quad.material = horizontal;
          horizontal.uniforms.tDiffuse.value = target.texture;
          horizontal.uniforms.h.value = amount / 256;
          gl.setRenderTarget(blurTarget);
          gl.render(blurScene, screenCamera);
          quad.material = vertical;
          vertical.uniforms.tDiffuse.value = blurTarget.texture;
          vertical.uniforms.v.value = amount / 256;
          gl.setRenderTarget(target);
          gl.render(blurScene, screenCamera);
        }
      } finally {
        plane.visible = visible;
        scene.background = background;
        scene.overrideMaterial = override;
        gl.setRenderTarget(previousTarget);
        gl.setClearColor(clearColor, clearAlpha);
        gl.autoClear = autoClear;
      }
    },
    dispose() {
      target.dispose();
      blurTarget.dispose();
      depth.dispose();
      horizontal.dispose();
      vertical.dispose();
      geometry.dispose();
    },
  };
}
