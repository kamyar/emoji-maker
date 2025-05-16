import React, { useState, FormEvent } from 'react';
import './EmojiGenerator.css';
import Toast from './Toast';

interface FormData {
  text: string;
  margin: number;
  gif: boolean;
  loop: boolean;
  frameDelay: number;
  hdr: boolean;
  hdrConfirmed: boolean;
}

const EmojiGenerator: React.FC = () => {
  const [formData, setFormData] = useState<FormData>({
    text: '',
    margin: 0,
    gif: false,
    loop: true,
    frameDelay: 100,
    hdr: false,
    hdrConfirmed: false
  });
  const [imageUrl, setImageUrl] = useState<string>('');
  const [showToast, setShowToast] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!formData.text) {
      alert('Please enter text before generating an image.');
      return;
    }

    if (formData.hdr && !formData.hdrConfirmed) {
      setShowToast(true);
      setTimeout(() => {
        window.location.href = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ';
      }, 2000);
      return;
    }

    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData)
      });

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      setImageUrl(url);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  return (
    <div className="generator">
      <form onSubmit={handleSubmit} className="form">
        <textarea
          value={formData.text}
          onChange={(e) => setFormData({ ...formData, text: e.target.value })}
          placeholder="Enter multi line text"
        />
        
        <div className="form-group">
          <label htmlFor="margin">Margin</label>
          <input
            type="number"
            id="margin"
            value={formData.margin}
            onChange={(e) => setFormData({ ...formData, margin: parseInt(e.target.value) })}
          />
        </div>

        <div className="form-group">
          <label htmlFor="hdr">HDR</label>
          <input
            type="checkbox"
            id="hdr"
            checked={formData.hdr}
            onChange={(e) => setFormData({ ...formData, hdr: e.target.checked, hdrConfirmed: false })}
          />
        </div>

        {formData.hdr && (
          <div className="form-group">
            <label htmlFor="hdrConfirmed">
              I accept responsibility for all enemies I make by generating HDR emojis
            </label>
            <input
              type="checkbox"
              id="hdrConfirmed"
              checked={formData.hdrConfirmed}
              onChange={(e) => setFormData({ ...formData, hdrConfirmed: e.target.checked })}
            />
          </div>
        )}

        <div className="form-group">
          <label htmlFor="makeGif">Make GIF</label>
          <input
            type="checkbox"
            id="makeGif"
            checked={formData.gif}
            onChange={(e) => setFormData({ ...formData, gif: e.target.checked })}
          />
        </div>

        {formData.gif && (
          <div className="gif-settings">
            <div className="form-group">
              <label htmlFor="loop">Loop</label>
              <input
                type="checkbox"
                id="loop"
                checked={formData.loop}
                onChange={(e) => setFormData({ ...formData, loop: e.target.checked })}
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="frameDelay">Frame Delay</label>
              <input
                type="number"
                id="frameDelay"
                value={formData.frameDelay}
                onChange={(e) => setFormData({ ...formData, frameDelay: parseInt(e.target.value) })}
              />
            </div>
          </div>
        )}

        <button type="submit">Generate</button>
      </form>

      {imageUrl && (
        <div className="result">
          <img src={imageUrl} alt="Generated emoji" />
          <a
            href={imageUrl}
            download={`${formData.text.split('\n').join('-')}.${formData.gif ? 'gif' : 'png'}`}
            className="download-link"
          >
            Download
          </a>
        </div>
      )}

      {showToast && (
        <Toast
          message="!!!!! ERROR !!!! Computer says no."
          onDismiss={() => setShowToast(false)}
        />
      )}
    </div>
  );
};

export default EmojiGenerator; 