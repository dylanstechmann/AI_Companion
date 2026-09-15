import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-600.css';
import '@fontsource/inter/latin-700.css';
const AvatarStudio = React.lazy(() => import('./components/AvatarStudio.jsx'));
const showStudio = import.meta.env.VITE_AVATAR_PREVIEW === 'true' || window.location.hash === '#avatar-studio';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {showStudio
      ? <React.Suspense fallback={<div role="status">Loading avatar studio…</div>}><AvatarStudio /></React.Suspense>
      : <App />}
  </React.StrictMode>
);
