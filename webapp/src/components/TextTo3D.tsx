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
  borderPaddingTop: number;
  borderPaddingRight: number;
  borderPaddingBottom: number;
  borderPaddingLeft: number;
  scale: number;
  color: string;
  exportFormat: 'stl' | '3mf';
}

const STORAGE_KEY = '3dtext-form';

const defaultFormData: FormData3D = {
  text: '',
  font: '',
  fontSize: 24,
  letterSpacing: 0.5,
  lineSpacing: 0,
  extrudeHeight: 4,
  addBorder: true,
  fillBorder: false,
  fillColor: '#ffffff',
  gap: 0,
  addOutline: false,
  outlineWidth: 1.0,
  keychainHole: false,
  keychainCorner: 'bottom-left',
  keychainRadius: 3,
  keychainEdgeH: 3,
  keychainEdgeV: 3,
  borderPaddingTop: 2,
  borderPaddingRight: 2,
  borderPaddingBottom: 2,
  borderPaddingLeft: 2,
  scale: 1.0,
  color: '#667eea',
  exportFormat: 'stl',
};

function loadSavedForm(): FormData3D {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return { ...defaultFormData, ...JSON.parse(saved) };
  } catch {}
  return defaultFormData;
}

const TextTo3D: React.FC = () => {
  const [formData, setFormData] = useState<FormData3D>(loadSavedForm);
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

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(formData));
  }, [formData]);

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

      const modelWidth = parseFloat(response.headers.get('X-Model-Width') || '0');
      const modelHeight = parseFloat(response.headers.get('X-Model-Height') || '0');
      const modelDepth = parseFloat(response.headers.get('X-Model-Depth') || '0');
      if (modelWidth > 0) {
        setDimensions({ width: modelWidth, height: modelHeight, depth: modelDepth });
      }

      const bambuFileId = response.headers.get('X-Bambu-File-Id');
      if (bambuFileId) {
        const fileUrl = `${window.location.origin}/api/temp-3mf/${bambuFileId}`;
        setBambuLink(`bambustudioopen://open?file=${encodeURIComponent(fileUrl)}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);

      const safeName = formData.text.split('\n')[0].substring(0, 20).replace(/\s+/g, '_');
      setDownloadUrl(url);
      setDownloadFilename(`${safeName}.${formData.exportFormat}`);

      const textStlId = response.headers.get('X-Text-Stl-Id');
      const borderStlId = response.headers.get('X-Border-Stl-Id');

      if (textStlId && borderStlId) {
        const [textRes, borderRes] = await Promise.all([
          fetch(`/api/temp-stl/${textStlId}/text`),
          fetch(`/api/temp-stl/${borderStlId}/border`),
        ]);
        if (textRes.ok && borderRes.ok) {
          const textBlob = await textRes.blob();
          const borderBlob = await borderRes.blob();
          setStlBlob(textBlob);
          setViewerParts([
            { blob: borderBlob, color: formData.fillColor },
            { blob: textBlob, color: formData.color },
          ]);
        } else {
          if (formData.exportFormat === 'stl') {
            setStlBlob(blob);
          }
        }
        setViewerLoading(false);
      } else if (formData.exportFormat === 'stl') {
        setStlBlob(blob);
        setViewerLoading(false);
      } else {
        const stlFileId = response.headers.get('X-Stl-File-Id');
        if (stlFileId) {
          const stlResponse = await fetch(`/api/temp-stl/${stlFileId}`);
          if (stlResponse.ok) {
            setStlBlob(await stlResponse.blob());
          }
        }
        setViewerLoading(false);
      }
    } catch (error) {
      setErrorMessage('Network error. Please try again.');
      setViewerLoading(false);
      console.error('Error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="generator-3d">
      <div className="generator-3d-layout">
        <form onSubmit={handleSubmit} className="form" noValidate>
          <textarea
            value={formData.text}
            onChange={(e) => setFormData({ ...formData, text: e.target.value })}
            placeholder="Enter text (use Enter for multiple lines)"
          />

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
            <div className="form-group">
              <label htmlFor="color">Text Color</label>
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
          </div>

          <div className="form-group">
            <label htmlFor="gap">Gap (%)</label>
            <input
              type="number"
              id="gap"
              value={formData.gap}
              min={0} max={50} step={1}
              onChange={(e) => setFormData({ ...formData, gap: parseFloat(e.target.value) })}
            />
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

                <div className="accordion-section accordion-nested">
                  <label className="accordion-toggle">
                    <input
                      type="checkbox"
                      id="fillBorder"
                      checked={formData.fillBorder}
                      onChange={(e) => setFormData({ ...formData, fillBorder: e.target.checked })}
                    />
                    <span>Fill</span>
                  </label>
                  {formData.fillBorder && (
                    <div className="accordion-body">
                      <div className="form-group">
                        <label htmlFor="fillColor">Fill Color</label>
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
                      <div className="accordion-section accordion-nested">
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
                                <label htmlFor="keychainEdgeH">H Edge (mm)</label>
                                <input type="number" id="keychainEdgeH"
                                  value={formData.keychainEdgeH}
                                  min={0} max={50} step={0.5}
                                  onChange={(e) => setFormData({ ...formData, keychainEdgeH: parseFloat(e.target.value) })} />
                              </div>
                            </div>
                            <div className="form-group">
                              <label htmlFor="keychainEdgeV">V Edge (mm)</label>
                              <input type="number" id="keychainEdgeV"
                                value={formData.keychainEdgeV}
                                min={0} max={50} step={0.5}
                                onChange={(e) => setFormData({ ...formData, keychainEdgeV: parseFloat(e.target.value) })} />
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <div className="accordion-section accordion-nested">
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
            {isLoading ? 'Generating...' : 'Generate 3D Text'}
          </button>
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
              <p>{isLoading ? 'Generating...' : 'Loading 3D preview...'}</p>
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
