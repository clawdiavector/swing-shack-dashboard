import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import './index.css'
import './theme-play.css'
import './a11y.css'
import { applyTheme, readTheme } from './lib/theme'
import { loadMe } from './lib/me'
import { classicRedirect } from './lib/classicRedirect'

// Old Classic URLs (page=… on /, /home.html, /strategy) load this build but sit
// outside /app, so the router would draw nothing. Send them to the new page.
const legacyTarget = classicRedirect(window.location.pathname, window.location.search)

if (legacyTarget) {
  window.location.replace(legacyTarget)
} else {
  applyTheme(readTheme())
  void loadMe()

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <BrowserRouter basename="/app">
        <App />
      </BrowserRouter>
    </StrictMode>,
  )
}
