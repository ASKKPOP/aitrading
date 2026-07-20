import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import { installLanguageHeader } from './apiLanguage'
import './index.css'

// Must run before any component mounts and starts fetching.
installLanguageHeader()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
