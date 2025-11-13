import React from 'react';
import './App.css';
import EmojiGenerator from './components/EmojiGenerator';

function App() {
  return (
    <div className="App">
      <div className="content">
        <h1>✨ Wolt emoji generator 💙</h1>
        <EmojiGenerator />
      </div>
      <footer className="footer">
        Contribute to the project on <a href="https://github.com/kamyar/emoji-maker/">GitHub</a> 
         {" | Made with 💙❤️🩵 by "}<a href="https://kamy.me">Kamyar</a>
      </footer>
    </div>
  );
}

export default App; 