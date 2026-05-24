import React, { useState, useEffect } from 'react';
import './App.css';
import EmojiGenerator from './components/EmojiGenerator';
import TextTo3D from './components/TextTo3D';

type Tab = 'emoji' | '3dtext';

function getInitialTab(): Tab {
  const hash = window.location.hash.replace('#', '');
  return hash === '3dtext' ? '3dtext' : 'emoji';
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>(getInitialTab);

  useEffect(() => {
    window.location.hash = activeTab;
  }, [activeTab]);

  return (
    <div className="App">
      <div className="content">
        <h1>{activeTab === 'emoji' ? '✨ Wolt emoji generator 💙' : '🧊 3D Text Generator'}</h1>
        <div className="tabs">
          <button
            type="button"
            className={`tab-button ${activeTab === 'emoji' ? 'active' : ''}`}
            onClick={() => setActiveTab('emoji')}
          >
            Emoji
          </button>
          <button
            type="button"
            className={`tab-button ${activeTab === '3dtext' ? 'active' : ''}`}
            onClick={() => setActiveTab('3dtext')}
          >
            3D Text
          </button>
        </div>
        {activeTab === 'emoji' ? <EmojiGenerator /> : <TextTo3D />}
      </div>
      <footer className="footer">
        Contribute to the project on <a href="https://github.com/kamyar/emoji-maker/">GitHub</a>
         {" | Made with 💙❤️🩵 by "}<a href="https://kamy.me">Kamyar</a>
      </footer>
    </div>
  );
}

export default App;
