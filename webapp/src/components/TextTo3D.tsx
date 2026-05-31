import React, { useState, useEffect, FormEvent } from 'react';
import './TextTo3D.css';
import Toast from './Toast';
import StlViewer from './StlViewer';
import confetti from 'canvas-confetti';

interface FormData3D {
  text: string;
  font: string;
  fontSize: number;
  letterSpacing: number;
  lineSpacing: number;
  extrudeHeight: number;
  addBorder: boolean;
  fillBorder: boolean;
  fillColor: string;
  gap: number;
  addOutline: boolean;
  outlineWidth: number;
  keychainHole: boolean;
  keychainCorner: 'bottom-left' | 'bottom-right' | 'top-left' | 'top-right';
  keychainRadius: number;
  keychainEdgeH: number;
  keychainEdgeV: number;
  keychainThickness: number;
  screwHookHole: boolean;
  screwHookSide: 'top' | 'right' | 'bottom' | 'left';
  screwHookDiameter: number;
  screwHookDepth: number;
  screwHookOffset: number;
  borderPaddingTop: number;
  borderPaddingRight: number;
  borderPaddingBottom: number;
  borderPaddingLeft: number;
  backplate: boolean;
  backplateThickness: number;
  scale: number;
  color: string;
  exportFormat: 'stl' | '3mf';
}

interface SavedConfig {
  name: string;
  data: FormData3D;
  updatedAt: number;
}

const STORAGE_KEY = '3dtext-form';
const SAVED_CONFIGS_KEY = '3dtext-saved-configs';

function buildBambuStudioLink(fileUrl: string): string {
  const encodedFileUrl = encodeURIComponent(fileUrl);
  const platform = `${navigator.platform || ''} ${navigator.userAgent || ''}`;
  const isApplePlatform = /Mac|iPhone|iPad|iPod/i.test(platform);

  return isApplePlatform
    ? `bambustudioopen://${encodedFileUrl}`
    : `bambustudio://open?file=${encodedFileUrl}`;
}

const defaultFormData: FormData3D = {
  text: 'Wolt',
  font: 'Omnes Black',
  fontSize: 12,
  letterSpacing: 1,
  lineSpacing: 0,
  extrudeHeight: 2,
  addBorder: true,
  fillBorder: true,
  fillColor: '#ffffff',
  gap: 0.2,
  addOutline: false,
  outlineWidth: 3,
  keychainHole: false,
  keychainCorner: 'bottom-left',
  keychainRadius: 3,
  keychainEdgeH: 3,
  keychainEdgeV: 3,
  keychainThickness: 3,
  screwHookHole: false,
  screwHookSide: 'top',
  screwHookDiameter: 3,
  screwHookDepth: 6,
  screwHookOffset: 0,
  borderPaddingTop: 4,
  borderPaddingRight: 4,
  borderPaddingBottom: 4,
  borderPaddingLeft: 4,
  backplate: false,
  backplateThickness: 1,
  scale: 1,
  color: '#009de0',
  exportFormat: '3mf',
};

function loadSavedForm(): FormData3D {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return { ...defaultFormData, ...JSON.parse(saved) };
  } catch {}
  return defaultFormData;
}

function cleanConfigName(text: string): string {
  const cleaned = text
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  return cleaned || '3d-text-config';
}

function loadSavedConfigs(): SavedConfig[] {
  try {
    const saved = localStorage.getItem(SAVED_CONFIGS_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed)) {
        return parsed
          .filter(item => item?.name && item?.data)
          .map(item => ({
            name: String(item.name),
            data: { ...defaultFormData, ...item.data },
            updatedAt: Number(item.updatedAt) || Date.now(),
          }));
      }
    }
  } catch {}
  return [];
}

const TextTo3D: React.FC = () => {
  const [formData, setFormData] = useState<FormData3D>(loadSavedForm);
  const [savedConfigs, setSavedConfigs] = useState<SavedConfig[]>(loadSavedConfigs);
  const [configName, setConfigName] = useState(() => cleanConfigName(loadSavedForm().text));
  const [selectedConfigName, setSelectedConfigName] = useState('');
  const [availableFonts, setAvailableFonts] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [downloadFilename, setDownloadFilename] = useState('');
  const [stlBlob, setStlBlob] = useState<Blob | null>(null);
  const [viewerParts, setViewerParts] = useState<{blob: Blob; color: string}[]>([]);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [bambuLink, setBambuLink] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState<{ width: number; height: number; depth: number } | null>(null);
  const [showValidationToast, setShowValidationToast] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [finalElapsed, setFinalElapsed] = useState<number | null>(null);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(formData));
  }, [formData]);

  useEffect(() => {
    localStorage.setItem(SAVED_CONFIGS_KEY, JSON.stringify(savedConfigs));
  }, [savedConfigs]);

  useEffect(() => {
    fetch('/api/fonts')
      .then(res => res.json())
      .then(data => {
        setAvailableFonts(data.fonts);
        if (data.fonts.length > 0) {
          setFormData(prev => ({
            ...prev,
            font: data.fonts.includes(prev.font) ? prev.font : data.fonts[0],
          }));
        }
      })
      .catch(err => console.error('Failed to load fonts:', err));
  }, []);

  useEffect(() => {
    if (!isLoading) return;
    setFinalElapsed(null);
    setElapsed(0);
    const t0 = Date.now();
    const id = setInterval(() => setElapsed(((Date.now() - t0) / 1000)), 100);
    return () => { clearInterval(id); setFinalElapsed((Date.now() - t0) / 1000); };
  }, [isLoading]);

  useEffect(() => {
    if (downloadUrl) {
      confetti({
        particleCount: 100,
        spread: 70,
        origin: { y: 0.6 },
        colors: ['#667eea', '#764ba2', '#ffffff', '#00cdbc', '#ff3008']
      });
    }
  }, [downloadUrl]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!formData.text.trim()) {
      setShowValidationToast(true);
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);
    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    setDownloadUrl(null);
    setBambuLink(null);
    setStlBlob(null);
    setViewerParts([]);
    setViewerLoading(true);
    setDimensions(null);

    try {
      const response = await fetch('/api/generate-3d', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const errData = await response.json();
        setErrorMessage(errData.error || 'Generation failed');
        return;
      }

      const data = await response.json();

      if (data.dimensions.width > 0) {
        setDimensions(data.dimensions);
      }

      if (data.bambuFileId) {
        const fileUrl = `${window.location.origin}/api/temp-3mf/${data.bambuFileId}`;
        setBambuLink(buildBambuStudioLink(fileUrl));
      }

      const downloadBytes = Uint8Array.from(atob(data.download), c => c.charCodeAt(0));
      const blob = new Blob([downloadBytes]);
      const url = URL.createObjectURL(blob);
      setDownloadUrl(url);
      setDownloadFilename(data.filename);

      if (data.textStl && data.borderStl) {
        const textBytes = Uint8Array.from(atob(data.textStl), c => c.charCodeAt(0));
        const borderBytes = Uint8Array.from(atob(data.borderStl), c => c.charCodeAt(0));
        const textBlob = new Blob([textBytes]);
        const borderBlob = new Blob([borderBytes]);
        setStlBlob(textBlob);
        setViewerParts([
          { blob: borderBlob, color: formData.fillColor },
          { blob: textBlob, color: formData.color },
        ]);
      } else if (data.textStl) {
        const textBytes = Uint8Array.from(atob(data.textStl), c => c.charCodeAt(0));
        setStlBlob(new Blob([textBytes]));
      }
      setViewerLoading(false);
    } catch (error) {
      setErrorMessage('Network error. Please try again.');
      setViewerLoading(false);
      console.error('Error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyConfig = () => {
    navigator.clipboard.writeText(JSON.stringify(formData, null, 2));
  };

  const handleSaveConfig = () => {
    const name = (configName.trim() || cleanConfigName(formData.text)).slice(0, 80);
    const nextConfig = { name, data: formData, updatedAt: Date.now() };
    setSavedConfigs(prev => {
      const withoutCurrent = prev.filter(config => config.name !== name);
      return [nextConfig, ...withoutCurrent].sort((a, b) => b.updatedAt - a.updatedAt);
    });
    setConfigName(name);
    setSelectedConfigName(name);
  };

  const handleLoadConfig = () => {
    const config = savedConfigs.find(item => item.name === selectedConfigName);
    if (!config) return;
    setFormData(config.data);
    setConfigName(config.name);
  };

  const handleDeleteConfig = () => {
    if (!selectedConfigName) return;
    setSavedConfigs(prev => prev.filter(config => config.name !== selectedConfigName));
    setSelectedConfigName('');
  };

  const handleResetDefaults = () => {
    localStorage.removeItem(STORAGE_KEY);
    setFormData({ ...defaultFormData, font: formData.font || defaultFormData.font });
  };

  return (
    <div className="generator-3d">
      <div className="generator-3d-layout">
        <form onSubmit={handleSubmit} className="form" noValidate>
          <div className="saved-configs">
            <div className="saved-config-row">
              <label htmlFor="configName">Config</label>
              <input
                type="text"
                id="configName"
                value={configName}
                placeholder={cleanConfigName(formData.text)}
                onChange={(e) => setConfigName(e.target.value)}
              />
              <button type="button" className="secondary-action" onClick={handleSaveConfig}>
                Save
              </button>
            </div>
            {savedConfigs.length > 0 && (
              <div className="saved-config-row">
                <label htmlFor="savedConfig">Saved</label>
                <select
                  id="savedConfig"
                  className="form-select"
                  value={selectedConfigName}
                  onChange={(e) => setSelectedConfigName(e.target.value)}
                >
                  <option value="">Choose config</option>
                  {savedConfigs.map(config => (
                    <option key={config.name} value={config.name}>{config.name}</option>
                  ))}
                </select>
                <button type="button" className="secondary-action" onClick={handleLoadConfig} disabled={!selectedConfigName}>
                  Load
                </button>
                <button type="button" className="secondary-action danger" onClick={handleDeleteConfig} disabled={!selectedConfigName}>
                  Delete
                </button>
              </div>
            )}
          </div>

          <textarea
            value={formData.text}
            onChange={(e) => {
              const text = e.target.value;
              setFormData({ ...formData, text });
              if (!configName.trim() || configName === cleanConfigName(formData.text)) {
                setConfigName(cleanConfigName(text));
              }
            }}
            placeholder="Enter text (use Enter for multiple lines)"
          />

          <div className="form-row font-color-row">
            <div className="form-group">
              <label htmlFor="font">Font</label>
              <select
                id="font"
                value={formData.font}
                onChange={(e) => setFormData({ ...formData, font: e.target.value })}
                className="form-select"
              >
                {availableFonts.map(f => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="color">Text</label>
              <input
                type="text"
                id="color"
                value={formData.color}
                placeholder="#667eea"
                onChange={(e) => setFormData({ ...formData, color: e.target.value })}
                style={/^#[0-9a-fA-F]{6}$/.test(formData.color) ? {
                  backgroundColor: formData.color,
                  color: parseInt(formData.color.slice(1, 3), 16) * 0.299
                    + parseInt(formData.color.slice(3, 5), 16) * 0.587
                    + parseInt(formData.color.slice(5, 7), 16) * 0.114 > 150
                    ? '#000' : '#fff',
                } : undefined}
              />
            </div>
            <div className="form-group">
              <label htmlFor="fillColor">Secondary</label>
              <input
                type="text"
                id="fillColor"
                value={formData.fillColor}
                placeholder="#ffffff"
                onChange={(e) => setFormData({ ...formData, fillColor: e.target.value })}
                style={/^#[0-9a-fA-F]{6}$/.test(formData.fillColor) ? {
                  backgroundColor: formData.fillColor,
                  color: parseInt(formData.fillColor.slice(1, 3), 16) * 0.299
                    + parseInt(formData.fillColor.slice(3, 5), 16) * 0.587
                    + parseInt(formData.fillColor.slice(5, 7), 16) * 0.114 > 150
                    ? '#000' : '#fff',
                } : undefined}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="fontSize">Font Size</label>
              <input
                type="number"
                id="fontSize"
                value={formData.fontSize}
                min={1} max={200} step={1}
                onChange={(e) => setFormData({ ...formData, fontSize: parseFloat(e.target.value) })}
              />
            </div>
            <div className="form-group">
              <label htmlFor="letterSpacing">Letter Spacing</label>
              <input
                type="number"
                id="letterSpacing"
                value={formData.letterSpacing}
                min={-5} max={50} step={0.5}
                onChange={(e) => setFormData({ ...formData, letterSpacing: parseFloat(e.target.value) })}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="lineSpacing">Line Spacing</label>
              <input
                type="number"
                id="lineSpacing"
                value={formData.lineSpacing}
                min={-50} max={100} step={1}
                onChange={(e) => setFormData({ ...formData, lineSpacing: parseFloat(e.target.value) })}
              />
            </div>
            <div className="form-group">
              <label htmlFor="extrudeHeight">Extrude Height</label>
              <input
                type="number"
                id="extrudeHeight"
                value={formData.extrudeHeight}
                min={0.5} max={50} step={0.5}
                onChange={(e) => setFormData({ ...formData, extrudeHeight: parseFloat(e.target.value) })}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="scale">Scale</label>
              <input
                type="number"
                id="scale"
                value={formData.scale}
                min={0.1} max={10} step={0.1}
                onChange={(e) => setFormData({ ...formData, scale: parseFloat(e.target.value) })}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="gap">Gap (mm)</label>
            <input
              type="number"
              id="gap"
              value={formData.gap}
              min={0} max={5} step={0.1}
              onChange={(e) => setFormData({ ...formData, gap: parseFloat(e.target.value) })}
            />
          </div>

          <div className="accordion-section">
            <label className="accordion-toggle">
              <input
                type="checkbox"
                id="screwHookHole"
                checked={formData.screwHookHole}
                onChange={(e) => setFormData({ ...formData, screwHookHole: e.target.checked })}
              />
              <span>Screw Hook Hole</span>
            </label>
            {formData.screwHookHole && (
              <div className="accordion-body">
                <div className="form-group">
                  <label htmlFor="screwHookSide">Side</label>
                  <select
                    id="screwHookSide"
                    className="form-select"
                    value={formData.screwHookSide}
                    onChange={(e) => setFormData({ ...formData, screwHookSide: e.target.value as FormData3D['screwHookSide'] })}
                  >
                    <option value="top">Top</option>
                    <option value="right">Right</option>
                    <option value="bottom">Bottom</option>
                    <option value="left">Left</option>
                  </select>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="screwHookDiameter">Hole Size (mm)</label>
                    <input type="number" id="screwHookDiameter"
                      value={formData.screwHookDiameter}
                      min={0.5} max={20} step={0.1}
                      onChange={(e) => setFormData({ ...formData, screwHookDiameter: parseFloat(e.target.value) })} />
                  </div>
                  <div className="form-group">
                    <label htmlFor="screwHookDepth">Depth (mm)</label>
                    <input type="number" id="screwHookDepth"
                      value={formData.screwHookDepth}
                      min={0.5} max={100} step={0.5}
                      onChange={(e) => setFormData({ ...formData, screwHookDepth: parseFloat(e.target.value) })} />
                  </div>
                </div>
                <div className="form-group">
                  <label htmlFor="screwHookOffset">Center Offset (mm)</label>
                  <input type="number" id="screwHookOffset"
                    value={formData.screwHookOffset}
                    min={-200} max={200} step={0.5}
                    onChange={(e) => setFormData({ ...formData, screwHookOffset: parseFloat(e.target.value) })} />
                </div>
              </div>
            )}
          </div>

          <div className="accordion-section">
            <label className="accordion-toggle">
              <input
                type="checkbox"
                id="addBorder"
                checked={formData.addBorder}
                onChange={(e) => setFormData({ ...formData, addBorder: e.target.checked })}
              />
              <span>Border</span>
            </label>
            {formData.addBorder && (
              <div className="accordion-body">
                <div className="border-padding-group">
                  <label>Padding</label>
                  <div className="padding-inputs">
                    <div className="padding-input padding-input-top">
                      <label htmlFor="borderPaddingTop">Top</label>
                      <input type="number" id="borderPaddingTop" value={formData.borderPaddingTop}
                        min={0} max={50} step={0.5}
                        onChange={(e) => setFormData({ ...formData, borderPaddingTop: parseFloat(e.target.value) })} />
                    </div>
                    <div className="padding-input padding-input-left">
                      <label htmlFor="borderPaddingLeft">Left</label>
                      <input type="number" id="borderPaddingLeft" value={formData.borderPaddingLeft}
                        min={0} max={50} step={0.5}
                        onChange={(e) => setFormData({ ...formData, borderPaddingLeft: parseFloat(e.target.value) })} />
                    </div>
                    <div className="padding-input padding-input-right">
                      <label htmlFor="borderPaddingRight">Right</label>
                      <input type="number" id="borderPaddingRight" value={formData.borderPaddingRight}
                        min={0} max={50} step={0.5}
                        onChange={(e) => setFormData({ ...formData, borderPaddingRight: parseFloat(e.target.value) })} />
                    </div>
                    <div className="padding-input padding-input-bottom">
                      <label htmlFor="borderPaddingBottom">Bottom</label>
                      <input type="number" id="borderPaddingBottom" value={formData.borderPaddingBottom}
                        min={0} max={50} step={0.5}
                        onChange={(e) => setFormData({ ...formData, borderPaddingBottom: parseFloat(e.target.value) })} />
                    </div>
                  </div>
                </div>

              </div>
            )}
          </div>

          <div className="accordion-section">
            <label className="accordion-toggle">
              <input
                type="checkbox"
                id="keychainHole"
                checked={formData.keychainHole}
                onChange={(e) => setFormData({ ...formData, keychainHole: e.target.checked })}
              />
              <span>Keychain Hole</span>
            </label>
            {formData.keychainHole && (
              <div className="accordion-body">
                <div className="form-group">
                  <label htmlFor="keychainCorner">Corner</label>
                  <select
                    id="keychainCorner"
                    className="form-select"
                    value={formData.keychainCorner}
                    onChange={(e) => setFormData({ ...formData, keychainCorner: e.target.value as FormData3D['keychainCorner'] })}
                  >
                    <option value="bottom-left">Bottom Left</option>
                    <option value="bottom-right">Bottom Right</option>
                    <option value="top-left">Top Left</option>
                    <option value="top-right">Top Right</option>
                  </select>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="keychainRadius">Radius (mm)</label>
                    <input type="number" id="keychainRadius"
                      value={formData.keychainRadius}
                      min={1} max={20} step={0.5}
                      onChange={(e) => setFormData({ ...formData, keychainRadius: parseFloat(e.target.value) })} />
                  </div>
                  <div className="form-group">
                    <label htmlFor="keychainThickness">Thickness (mm)</label>
                    <input type="number" id="keychainThickness"
                      value={formData.keychainThickness}
                      min={0.5} max={20} step={0.5}
                      onChange={(e) => setFormData({ ...formData, keychainThickness: parseFloat(e.target.value) })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="keychainEdgeH">Horizontal Distance (mm)</label>
                    <input type="number" id="keychainEdgeH"
                      value={formData.keychainEdgeH}
                      min={0} max={50} step={0.5}
                      onChange={(e) => setFormData({ ...formData, keychainEdgeH: parseFloat(e.target.value) })} />
                  </div>
                  <div className="form-group">
                    <label htmlFor="keychainEdgeV">Vertical Distance (mm)</label>
                    <input type="number" id="keychainEdgeV"
                      value={formData.keychainEdgeV}
                      min={0} max={50} step={0.5}
                      onChange={(e) => setFormData({ ...formData, keychainEdgeV: parseFloat(e.target.value) })} />
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="accordion-section">
            <label className="accordion-toggle">
              <input
                type="checkbox"
                id="addOutline"
                checked={formData.addOutline}
                onChange={(e) => setFormData({ ...formData, addOutline: e.target.checked })}
              />
              <span>Outline</span>
            </label>
            {formData.addOutline && (
              <div className="accordion-body">
                <div className="form-group">
                  <label htmlFor="outlineWidth">Width (mm)</label>
                  <input type="number" id="outlineWidth"
                    value={formData.outlineWidth}
                    min={0.2} max={10} step={0.1}
                    onChange={(e) => setFormData({ ...formData, outlineWidth: parseFloat(e.target.value) })} />
                </div>
              </div>
            )}
          </div>

          <div className="accordion-section">
            <label className="accordion-toggle">
              <input
                type="checkbox"
                id="backplate"
                checked={formData.backplate}
                onChange={(e) => setFormData({ ...formData, backplate: e.target.checked })}
              />
              <span>Backplate</span>
            </label>
            {formData.backplate && (
              <div className="accordion-body">
                <div className="form-group">
                  <label htmlFor="backplateThickness">Thickness (mm)</label>
                  <input type="number" id="backplateThickness"
                    value={formData.backplateThickness}
                    min={0.2} max={10} step={0.1}
                    onChange={(e) => setFormData({ ...formData, backplateThickness: parseFloat(e.target.value) })} />
                </div>
              </div>
            )}
          </div>

          <div className="form-group">
            <label>Format</label>
            <div className="toggle-buttons format-toggles">
              <button
                type="button"
                className={`toggle-button ${formData.exportFormat === 'stl' ? 'active' : ''}`}
                onClick={() => setFormData({ ...formData, exportFormat: 'stl' })}
              >
                STL
              </button>
              <button
                type="button"
                className={`toggle-button ${formData.exportFormat === '3mf' ? 'active' : ''}`}
                onClick={() => setFormData({ ...formData, exportFormat: '3mf' })}
              >
                3MF
              </button>
            </div>
          </div>

          <button type="submit" disabled={isLoading}>
            {isLoading ? `Generating... ${elapsed.toFixed(1)}s` : 'Generate 3D Text'}
          </button>

          {window.location.hostname === 'localhost' && (
            <>
              <button type="button" className="debug-btn" onClick={handleCopyConfig}>
                Copy Config
              </button>
              <button type="button" className="debug-btn" onClick={handleResetDefaults}>
                Reset Defaults
              </button>
            </>
          )}
        </form>

        <div className="preview-panel">
          {stlBlob ? (
            <div className="viewer-wrapper" onPointerDown={(e) => {
              const hints = e.currentTarget.querySelector('.viewer-hints');
              if (hints) hints.classList.add('hidden');
            }}>
              <StlViewer stlBlob={stlBlob} color={formData.color} parts={viewerParts.length > 0 ? viewerParts : undefined} />
              <div className="viewer-hints">
                <span>Drag to rotate</span>
                <span>Scroll to zoom</span>
                <span>Right-drag to pan</span>
              </div>
            </div>
          ) : viewerLoading || isLoading ? (
            <div className="stl-viewer viewer-loading">
              <p>{isLoading ? `Generating... ${elapsed.toFixed(1)}s` : 'Loading 3D preview...'}</p>
            </div>
          ) : (
            <div className="stl-viewer viewer-placeholder">
              <p>3D preview will appear here</p>
            </div>
          )}

          {errorMessage && (
            <div className="panel-error">
              <p className="error-message">{errorMessage}</p>
            </div>
          )}

          {dimensions && (
            <div className="dimensions-info">
              <span>{dimensions.width} mm</span>
              <span>&times;</span>
              <span>{dimensions.height} mm</span>
              <span>&times;</span>
              <span>{dimensions.depth} mm</span>
              {finalElapsed !== null && <span className="elapsed-time">({finalElapsed.toFixed(1)}s)</span>}
            </div>
          )}

          {downloadUrl && (
            <div className="result-actions">
              <a href={downloadUrl} download={downloadFilename} className="download-link">
                Download {formData.exportFormat.toUpperCase()}
              </a>
              {bambuLink && (
                <a href={bambuLink} className="download-link bambu-link">
                  🎋 Open in Bambu Studio
                </a>
              )}
            </div>
          )}
        </div>
      </div>

      {showValidationToast && (
        <Toast
          message="Please enter text before generating."
          onDismiss={() => setShowValidationToast(false)}
        />
      )}
    </div>
  );
};

export default TextTo3D;
