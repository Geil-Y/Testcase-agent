import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { JobProvider } from './hooks/JobContext'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename="/console">
      <JobProvider>
        <App />
      </JobProvider>
    </BrowserRouter>
  </StrictMode>,
)
