import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

interface MeshPart {
  blob: Blob;
  color: string;
}

interface StlViewerProps {
  stlBlob: Blob;
  color?: string;
  parts?: MeshPart[];
}

const AXIS_OPACITY_KEY = 'stl-viewer-axis-opacity';

function loadAxisOpacity(): number {
  try {
    const saved = localStorage.getItem(AXIS_OPACITY_KEY);
    if (saved !== null) {
      const value = Number(saved);
      if (Number.isFinite(value)) {
        return Math.min(1, Math.max(0, value));
      }
    }
  } catch {}
  return 1;
}

function createLabelSprite(
  text: string,
  color: string,
  opacity: number,
  scale = 4,
  fontSize = 48,
): THREE.Sprite {
  const canvas = document.createElement('canvas');
  const size = 128;
  canvas.width = size;
  canvas.height = size;

  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.clearRect(0, 0, size, size);
    ctx.strokeStyle = `rgba(255, 255, 255, ${0.86 * opacity})`;
    ctx.lineWidth = Math.max(4, fontSize * 0.12);
    ctx.lineJoin = 'round';
    ctx.globalAlpha = opacity;
    ctx.fillStyle = color;
    ctx.font = `700 ${fontSize}px Arial, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.strokeText(text, size / 2, size / 2);
    ctx.fillText(text, size / 2, size / 2);
  }

  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
  });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(scale, scale, 1);
  sprite.renderOrder = 1000;
  return sprite;
}

function createAxisLine(
  from: THREE.Vector3,
  to: THREE.Vector3,
  color: number,
  opacity = 0.9,
): THREE.Line {
  const geometry = new THREE.BufferGeometry().setFromPoints([from, to]);
  const material = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity,
    depthTest: false,
  });
  const line = new THREE.Line(geometry, material);
  line.renderOrder = 999;
  return line;
}

function createMillimeterAxes(size: THREE.Vector3, opacity: number): THREE.Group {
  const helper = new THREE.Group();
  const maxDim = Math.max(size.x, size.y, size.z, 10);
  const extent = Math.max(10, Math.ceil((maxDim * 0.65 + 5) / 5) * 5);
  const tick = Math.max(1.2, extent * 0.035);
  const tickCount = Math.floor(extent / 5);
  const numberScale = Math.max(1.8, Math.min(3.2, extent * 0.05));
  const numberOffset = tick * 2.2;

  const axes = [
    {
      label: 'X',
      color: 0xe53935,
      cssColor: '#e53935',
      direction: new THREE.Vector3(1, 0, 0),
      tickA: new THREE.Vector3(0, tick, 0),
      tickB: new THREE.Vector3(0, 0, tick),
    },
    {
      label: 'Y',
      color: 0x2e7d32,
      cssColor: '#2e7d32',
      direction: new THREE.Vector3(0, 1, 0),
      tickA: new THREE.Vector3(tick, 0, 0),
      tickB: new THREE.Vector3(0, 0, tick),
    },
    {
      label: 'Z',
      color: 0x1565c0,
      cssColor: '#1565c0',
      direction: new THREE.Vector3(0, 0, 1),
      tickA: new THREE.Vector3(tick, 0, 0),
      tickB: new THREE.Vector3(0, tick, 0),
    },
  ];

  axes.forEach(({ label, color, cssColor, direction, tickA, tickB }) => {
    helper.add(createAxisLine(
      direction.clone().multiplyScalar(-extent),
      direction.clone().multiplyScalar(extent),
      color,
      0.95 * opacity,
    ));

    for (let i = -tickCount; i <= tickCount; i++) {
      if (i === 0) continue;
      const center = direction.clone().multiplyScalar(i * 5);
      const markerLength = i % 2 === 0 ? 1 : 0.65;
      const value = i * 5;
      helper.add(createAxisLine(
        center.clone().sub(tickA.clone().multiplyScalar(markerLength)),
        center.clone().add(tickA.clone().multiplyScalar(markerLength)),
        color,
        0.55 * opacity,
      ));
      helper.add(createAxisLine(
        center.clone().sub(tickB.clone().multiplyScalar(markerLength)),
        center.clone().add(tickB.clone().multiplyScalar(markerLength)),
        color,
        0.35 * opacity,
      ));

      const tickLabel = createLabelSprite(String(value), cssColor, opacity, numberScale, 34);
      tickLabel.position.copy(
        center.clone()
          .add(tickA.clone().normalize().multiplyScalar(numberOffset))
          .add(tickB.clone().normalize().multiplyScalar(numberOffset * 0.45)),
      );
      helper.add(tickLabel);
    }

    const axisLabel = createLabelSprite(label, cssColor, opacity, 4, 48);
    axisLabel.position.copy(direction.clone().multiplyScalar(extent + 4));
    helper.add(axisLabel);
  });

  const originLabel = createLabelSprite('0', '#333333', opacity, 3, 42);
  originLabel.scale.set(3, 3, 1);
  originLabel.position.set(0, 0, 0);
  helper.add(originLabel);

  return helper;
}

function parseSTL(buffer: ArrayBuffer): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  const dv = new DataView(buffer);
  const numTriangles = dv.getUint32(80, true);
  const vertices = new Float32Array(numTriangles * 9);
  const normals = new Float32Array(numTriangles * 9);

  for (let i = 0; i < numTriangles; i++) {
    const offset = 84 + i * 50;
    const nx = dv.getFloat32(offset, true);
    const ny = dv.getFloat32(offset + 4, true);
    const nz = dv.getFloat32(offset + 8, true);

    for (let v = 0; v < 3; v++) {
      const vOffset = offset + 12 + v * 12;
      vertices[i * 9 + v * 3] = dv.getFloat32(vOffset, true);
      vertices[i * 9 + v * 3 + 1] = dv.getFloat32(vOffset + 4, true);
      vertices[i * 9 + v * 3 + 2] = dv.getFloat32(vOffset + 8, true);
      normals[i * 9 + v * 3] = nx;
      normals[i * 9 + v * 3 + 1] = ny;
      normals[i * 9 + v * 3 + 2] = nz;
    }
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
  return geometry;
}

const StlViewer: React.FC<StlViewerProps> = ({ stlBlob, color = '#667eea', parts }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const axisRef = useRef<THREE.Group | null>(null);
  const sizeRef = useRef<THREE.Vector3 | null>(null);
  const axisOpacityRef = useRef(loadAxisOpacity());
  const [axisOpacity, setAxisOpacity] = useState(loadAxisOpacity);

  useEffect(() => {
    try {
      localStorage.setItem(AXIS_OPACITY_KEY, String(axisOpacity));
    } catch {}
    axisOpacityRef.current = axisOpacity;
  }, [axisOpacity]);

  useEffect(() => {
    const scene = sceneRef.current;
    const size = sizeRef.current;
    if (!scene || !size) return;

    if (axisRef.current) {
      scene.remove(axisRef.current);
      axisRef.current = null;
    }

    if (axisOpacity > 0) {
      const axis = createMillimeterAxes(size, axisOpacity);
      axisRef.current = axis;
      scene.add(axis);
    }
  }, [axisOpacity]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf0f0f0);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 10000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    scene.add(new THREE.AmbientLight(0xffffff, 0.8));
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
    dirLight.position.set(10, 10, 10);
    scene.add(dirLight);
    const backLight = new THREE.DirectionalLight(0xffffff, 0.3);
    backLight.position.set(-10, -5, -10);
    scene.add(backLight);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;

    const meshesToLoad = parts && parts.length > 0
      ? parts.map(p => ({ blob: p.blob, color: p.color }))
      : [{ blob: stlBlob, color }];

    Promise.all(meshesToLoad.map(async ({ blob, color: c }) => {
      const buffer = await blob.arrayBuffer();
      const geometry = parseSTL(buffer);
      const material = new THREE.MeshPhongMaterial({
        color: new THREE.Color(c),
        shininess: 40,
        specular: new THREE.Color(0x444444),
      });
      return new THREE.Mesh(geometry, material);
    })).then(meshes => {
      const group = new THREE.Group();
      meshes.forEach(m => group.add(m));

      const box = new THREE.Box3().setFromObject(group);
      const center = new THREE.Vector3();
      box.getCenter(center);
      group.position.sub(center);

      const size = new THREE.Vector3();
      box.getSize(size);
      sizeRef.current = size;
      const currentAxisOpacity = axisOpacityRef.current;
      if (currentAxisOpacity > 0) {
        const axis = createMillimeterAxes(size, currentAxisOpacity);
        axisRef.current = axis;
        scene.add(axis);
      }
      const maxDim = Math.max(size.x, size.y, size.z);
      const fov = camera.fov * (Math.PI / 180);
      const dist = maxDim / (2 * Math.tan(fov / 2)) * 1.5;
      camera.position.set(0, 0, dist);
      camera.lookAt(0, 0, 0);
      controls.update();

      scene.add(group);
    });

    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      controls.dispose();
      renderer.dispose();
      sceneRef.current = null;
      axisRef.current = null;
      sizeRef.current = null;
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [stlBlob, color, parts]);

  return (
    <div className="stl-viewer-shell">
      <div ref={containerRef} className="stl-viewer" />
      <label className="coordinate-opacity-control">
        <span>Axes</span>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={axisOpacity}
          onChange={(e) => setAxisOpacity(Number(e.target.value))}
          aria-label="Coordinate axes opacity"
        />
        <span>{Math.round(axisOpacity * 100)}%</span>
      </label>
    </div>
  );
};

export default StlViewer;
