import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@mantine/core/styles.css'
import '@fontsource/poppins/400.css'
import '@fontsource/poppins/400-italic.css'
import '@fontsource/poppins/600.css'
import '@fontsource/anton/400.css'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
