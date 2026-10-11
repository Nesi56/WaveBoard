import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';
import { OBJLoader } from './vendor/OBJLoader.js';
import { STLLoader } from './vendor/STLLoader.js';

const MAX_MODEL_BYTES = 150 * 1024 * 1024;

function releaseObject(object) {
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  object.traverse((node) => {
    if (node.geometry) geometries.add(node.geometry);
    const nodeMaterials = Array.isArray(node.material) ? node.material : [node.material];
    nodeMaterials.filter(Boolean).forEach((material) => materials.add(material));
    if (node.skeleton) node.skeleton.dispose();
  });
  materials.forEach((material) => {
    Object.values(material).forEach((value) => {
      if (value?.isTexture) textures.add(value);
    });
    material.dispose();
  });
  textures.forEach((texture) => {
    texture.dispose();
    if (typeof texture.source?.data?.close === 'function') texture.source.data.close();
  });
  geometries.forEach((geometry) => geometry.dispose());
}

function makeSample() {
  const sculpture = new THREE.Mesh(
    new THREE.TorusKnotGeometry(1.02, 0.3, 180, 24, 2, 3),
    new THREE.MeshStandardMaterial({ color: 0x77ddd1, metalness: 0.28, roughness: 0.27 }),
  );
  sculpture.name = 'Wave sculpture';
  sculpture.rotation.set(0.14, 0.28, -0.16);
  return sculpture;
}

// Single-file imports stay self-contained and cannot silently request external
// textures or buffers from an unavailable USB path or internet host.
function validateGltfResources(buffer, extension) {
  let json;
  const decoder = new TextDecoder();
  if (extension === 'gltf') {
    json = JSON.parse(decoder.decode(buffer));
  } else {
    const view = new DataView(buffer);
    if (buffer.byteLength < 20 || view.getUint32(0, true) !== 0x46546c67) {
      throw new Error('This file is not a valid GLB model.');
    }
    const jsonLength = view.getUint32(12, true);
    if (view.getUint32(16, true) !== 0x4e4f534a || jsonLength > buffer.byteLength - 20) {
      throw new Error('The GLB file has an invalid model header.');
    }
    json = JSON.parse(decoder.decode(new Uint8Array(buffer, 20, jsonLength)));
  }
  for (const resource of [...(json.buffers || []), ...(json.images || [])]) {
    if (resource.uri && !resource.uri.startsWith('data:')) {
      throw new Error('This model references separate files. Export it as one GLB with embedded textures, then open it again.');
    }
  }
  const required = json.extensionsRequired || [];
  if (required.some((name) => ['KHR_draco_mesh_compression', 'EXT_meshopt_compression', 'KHR_texture_basisu'].includes(name))) {
    throw new Error('This model uses compressed geometry or textures. Export an uncompressed GLB to view it offline.');
  }
  return json;
}

/** Create a local, touch-friendly 3D scene. The container must have a height. */
export async function createModelViewer(container, options = {}) {
  if (!(container instanceof HTMLElement)) throw new Error('A model viewer container is required.');

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x111b26);
  scene.fog = new THREE.Fog(0x111b26, 13, 29);
  const camera = new THREE.PerspectiveCamera(39, 1, 0.05, 80);
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'low-power' });
  } catch {
    throw new Error('3D graphics are unavailable. Enable hardware acceleration in your browser and try again.');
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.domElement.setAttribute('aria-label', '3D model. Drag to rotate; scroll or pinch to zoom.');
  renderer.domElement.setAttribute('role', 'img');
  renderer.domElement.tabIndex = 0;
  Object.assign(renderer.domElement.style, { width: '100%', height: '100%', display: 'block', touchAction: 'none' });
  container.append(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.09;
  controls.rotateSpeed = 0.75;
  controls.zoomSpeed = 0.9;
  controls.panSpeed = 0.6;
  controls.minDistance = 1.1;
  controls.maxDistance = 24;
  controls.maxPolarAngle = Math.PI * 0.92;
  controls.autoRotate = false;
  controls.autoRotateSpeed = 0.65;
  controls.touches.ONE = THREE.TOUCH.ROTATE;
  controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;

  scene.add(new THREE.HemisphereLight(0xe5f6ff, 0x263c53, 2.6));
  const key = new THREE.DirectionalLight(0xf4ffff, 3.4);
  key.position.set(4, 7, 5);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x64dfd6, 2.2);
  rim.position.set(-5, 3, -4);
  scene.add(rim);
  const fill = new THREE.DirectionalLight(0x9ebcff, 1.0);
  fill.position.set(-3, 0, 3);
  scene.add(fill);

  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(16, 64),
    new THREE.MeshStandardMaterial({ color: 0x152230, roughness: 1, metalness: 0 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -1.82;
  scene.add(floor);
  const grid = new THREE.GridHelper(28, 28, 0x395363, 0x283e4d);
  grid.position.y = -1.813;
  grid.material.transparent = true;
  grid.material.opacity = 0.38;
  scene.add(grid);

  // A soft radial contact shadow costs only one small texture, with no shadow map.
  const shadowCanvas = document.createElement('canvas');
  shadowCanvas.width = 128;
  shadowCanvas.height = 128;
  const shadowContext = shadowCanvas.getContext('2d');
  const gradient = shadowContext.createRadialGradient(64, 64, 2, 64, 64, 64);
  gradient.addColorStop(0, 'rgba(0,0,0,0.6)');
  gradient.addColorStop(0.4, 'rgba(0,0,0,0.3)');
  gradient.addColorStop(1, 'rgba(0,0,0,0)');
  shadowContext.fillStyle = gradient;
  shadowContext.fillRect(0, 0, 128, 128);
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(5.4, 5.4),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(shadowCanvas), transparent: true, depthWrite: false }),
  );
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = -1.805;
  scene.add(shadow);

  let model = null;
  let disposed = false;
  let mode = 'solid';
  let frameId = 0;
  let activeFrames = 0;
  let loadVersion = 0;
  let activeRequest = null;
  let previousTime = 0;
  let visible = true;
  let modelRadius = 1.8;

  function requestRender(frames = 1) {
    if (disposed) return;
    activeFrames = Math.max(activeFrames, frames);
    if (!frameId && visible && !document.hidden) frameId = requestAnimationFrame(render);
  }

  function render(time) {
    // Keep a sentinel while controls.update emits change events, so those events
    // cannot enqueue a second animation loop during an active render.
    frameId = -1;
    if (disposed || !visible || document.hidden) { frameId = 0; return; }
    const delta = previousTime ? Math.min((time - previousTime) / 1000, 0.1) : 1 / 60;
    previousTime = time;
    controls.update(delta);
    renderer.render(scene, camera);
    activeFrames = Math.max(0, activeFrames - 1);
    frameId = 0;
    if (controls.autoRotate || activeFrames > 0) frameId = requestAnimationFrame(render);
  }

  function reset() {
    if (disposed) return;
    const verticalFov = THREE.MathUtils.degToRad(camera.fov);
    const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * camera.aspect);
    const distance = modelRadius / Math.sin(Math.min(verticalFov, horizontalFov) / 2) * 1.1;
    camera.position.copy(new THREE.Vector3(0.75, 0.44, 1).normalize().multiplyScalar(distance));
    camera.near = 0.05;
    camera.far = Math.max(80, distance * 6);
    camera.updateProjectionMatrix();
    controls.target.set(0, 0, 0);
    controls.minDistance = 1.1;
    controls.maxDistance = Math.max(24, distance * 2.5);
    controls.update();
    controls.saveState();
    requestRender(40);
  }

  function setMode(nextMode) {
    mode = nextMode === 'wireframe' ? 'wireframe' : 'solid';
    if (!model) return;
    model.traverse((node) => {
      const materials = Array.isArray(node.material) ? node.material : [node.material];
      materials.filter(Boolean).forEach((material) => {
        if ('wireframe' in material) material.wireframe = mode === 'wireframe';
      });
    });
    requestRender();
  }

  function showModel(nextModel, name) {
    nextModel.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(nextModel);
    const size = box.getSize(new THREE.Vector3());
    const extent = Math.max(size.x, size.y, size.z);
    if (!Number.isFinite(extent) || extent <= 0) {
      releaseObject(nextModel);
      throw new Error('The model contains no visible 3D geometry.');
    }
    const center = box.getCenter(new THREE.Vector3());
    const wrapper = new THREE.Group();
    wrapper.add(nextModel);
    wrapper.scale.setScalar(3.2 / extent);
    wrapper.position.copy(center).multiplyScalar(-3.2 / extent);
    if (model) {
      scene.remove(model);
      releaseObject(model);
    }
    model = wrapper;
    scene.add(model);
    model.updateMatrixWorld(true);
    const normalizedBox = new THREE.Box3().setFromObject(model);
    modelRadius = normalizedBox.getBoundingSphere(new THREE.Sphere()).radius;
    floor.position.y = normalizedBox.min.y - 0.17;
    grid.position.y = floor.position.y + 0.007;
    shadow.position.y = floor.position.y + 0.014;
    setMode(mode);
    reset();
    options.onStatus?.(name);
  }

  async function load(url, filename = '') {
    if (disposed) return false;
    const currentLoad = ++loadVersion;
    activeRequest?.abort();
    activeRequest = new AbortController();
    const extension = (filename || String(url).split(/[?#]/)[0]).split('.').pop().toLowerCase();
    try {
      if (!['glb', 'gltf', 'obj', 'stl'].includes(extension)) {
        throw new Error('Choose a GLB, embedded GLTF, OBJ, or STL model.');
      }
      options.onStatus?.(`Opening ${filename || 'model'}…`);
      const response = await fetch(url, { signal: activeRequest.signal });
      if (!response.ok) throw new Error(`The model could not be opened (${response.status}).`);
      if (Number(response.headers.get('content-length') || 0) > MAX_MODEL_BYTES) {
        throw new Error('Choose a model smaller than 150 MB for this viewer.');
      }
      const buffer = await response.arrayBuffer();
      if (buffer.byteLength > MAX_MODEL_BYTES) throw new Error('Choose a model smaller than 150 MB for this viewer.');
      if (disposed || currentLoad !== loadVersion) return false;
      let nextModel;
      if (extension === 'obj') {
        nextModel = new OBJLoader().parse(new TextDecoder().decode(buffer));
        nextModel.traverse((node) => {
          if (!node.isMesh) return;
          const oldMaterials = Array.isArray(node.material) ? node.material : [node.material];
          oldMaterials.forEach((material) => material.dispose());
          node.material = new THREE.MeshStandardMaterial({ color: 0x87d6cf, roughness: 0.42, metalness: 0.12, side: THREE.DoubleSide });
        });
      } else if (extension === 'stl') {
        const geometry = new STLLoader().parse(buffer);
        if (!geometry.attributes.normal) geometry.computeVertexNormals();
        nextModel = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0x87d6cf, roughness: 0.42, metalness: 0.12, side: THREE.DoubleSide }));
      } else {
        validateGltfResources(buffer, extension);
        const manager = new THREE.LoadingManager();
        manager.setURLModifier((resourceUrl) => {
          if (/^(data:|blob:)/i.test(resourceUrl)) return resourceUrl;
          throw new Error('Export a single GLB with embedded textures to view this model.');
        });
        const result = await new GLTFLoader(manager).parseAsync(buffer, '');
        nextModel = result.scene;
      }
      if (disposed || currentLoad !== loadVersion) {
        releaseObject(nextModel);
        return false;
      }
      showModel(nextModel, filename || 'Untitled model');
      return true;
    } catch (error) {
      if (error.name === 'AbortError' || disposed || currentLoad !== loadVersion) return false;
      options.onError?.(error);
      throw error;
    }
  }

  function resize() {
    if (disposed) return;
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    requestRender();
  }

  const handleChange = () => requestRender();
  const handleStart = () => requestRender(60);
  const handleEnd = () => requestRender(45);
  const handleVisibility = () => {
    previousTime = 0;
    if (!document.hidden) requestRender();
  };
  const handleContextLost = (event) => {
    event.preventDefault();
    options.onError?.(new Error('The graphics connection was interrupted. Reopen the 3D viewer.'));
  };
  const handleContextMenu = (event) => event.preventDefault();
  controls.addEventListener('change', handleChange);
  controls.addEventListener('start', handleStart);
  controls.addEventListener('end', handleEnd);
  document.addEventListener('visibilitychange', handleVisibility);
  renderer.domElement.addEventListener('webglcontextlost', handleContextLost);
  renderer.domElement.addEventListener('contextmenu', handleContextMenu);
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container);
  const intersectionObserver = new IntersectionObserver((entries) => {
    visible = entries[0].isIntersecting;
    if (visible) { previousTime = 0; requestRender(); }
  });
  intersectionObserver.observe(container);

  resize();
  showModel(makeSample(), 'Wave sculpture');

  return {
    load,
    reset,
    setMode,
    setAutoRotate(enabled) {
      controls.autoRotate = Boolean(enabled);
      requestRender();
    },
    resize,
    dispose() {
      if (disposed) return;
      disposed = true;
      ++loadVersion;
      activeRequest?.abort();
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      document.removeEventListener('visibilitychange', handleVisibility);
      renderer.domElement.removeEventListener('webglcontextlost', handleContextLost);
      renderer.domElement.removeEventListener('contextmenu', handleContextMenu);
      controls.dispose();
      releaseObject(scene);
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
}
