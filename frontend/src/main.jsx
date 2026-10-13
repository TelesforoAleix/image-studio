import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

function App() {
  return (
    <main>
      <header className="studio-header">
        <h1>image studio<span className="studio-dot" aria-hidden="true">.</span></h1>
        <span className="workspace-label">Your workspace</span>
      </header>
      <section aria-labelledby="library-title">
        <div className="library-header">
          <h2 id="library-title">Asset library</h2>
          <span className="asset-count">0 assets</span>
        </div>
        <div className="empty-library">
          <span className="empty-mark" aria-hidden="true">+</span>
          <h3>No assets yet</h3>
          <p>Your reusable people, garments, objects and backgrounds will live here.</p>
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
