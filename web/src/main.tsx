import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { preloadDashboard, preloadLayout } from '@/lib/data'

preloadLayout()
if (window.location.pathname !== '/guide') {
  preloadDashboard()
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
