import React from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import LandingPage from './LandingPage'

const App = React.lazy(() => import('./App'))
const page = window.location.pathname === '/' ? <LandingPage /> : <React.Suspense fallback={<main className="app-boot" role="status"><span className="spinner" />Opening the route planner…</main>}><App /></React.Suspense>
createRoot(document.getElementById('root')!).render(<React.StrictMode>{page}</React.StrictMode>)
