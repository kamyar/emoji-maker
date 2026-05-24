import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';

interface StlViewerProps {
  stlBlob: Blob;
  color?: string;
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

const StlViewer: React.FC<StlViewerProps> = ({ stlBlob, color = '#667eea' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf0f0f0);

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

    stlBlob.arrayBuffer().then(buffer => {
      const geometry = parseSTL(buffer);
      const material = new THREE.MeshPhongMaterial({
        color: new THREE.Color(color),
        shininess: 40,
        specular: new THREE.Color(0x444444),
      });
      const mesh = new THREE.Mesh(geometry, material);

      geometry.computeBoundingBox();
      const box = geometry.boundingBox!;
      const center = new THREE.Vector3();
      box.getCenter(center);
      geometry.translate(-center.x, -center.y, -center.z);

      const size = new THREE.Vector3();
      box.getSize(size);
      const maxDim = Math.max(size.x, size.y, size.z);
      const fov = camera.fov * (Math.PI / 180);
      const dist = maxDim / (2 * Math.tan(fov / 2)) * 1.5;
      camera.position.set(0, 0, dist);
      camera.lookAt(0, 0, 0);
      controls.update();

      scene.add(mesh);
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
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [stlBlob, color]);

  return <div ref={containerRef} className="stl-viewer" />;
};

export default StlViewer;
