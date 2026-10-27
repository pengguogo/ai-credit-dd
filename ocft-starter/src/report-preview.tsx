import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { PreviewApp } from '@/components/report/preview/preview-app'
import { TooltipProvider } from '@/components/ui/tooltip'
import '@/index.css'

createRoot(document.getElementById('root')!).render(<StrictMode><TooltipProvider><PreviewApp /></TooltipProvider></StrictMode>)
