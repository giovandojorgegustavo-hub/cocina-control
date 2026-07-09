import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { App } from './App'
import { flushQueue } from './lib/photoQueue'

// Attempt to upload any locally queued photos at startup
void flushQueue()

// Retry the queue whenever connectivity is restored
window.addEventListener('online', () => {
  void flushQueue()
})

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('No se encontro el elemento root en el DOM')
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
