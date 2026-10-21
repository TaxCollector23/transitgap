import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({
  plugins:[react(),tailwindcss()], server:{port:5173},
  // Local production-build QA uses the same-origin API paths as Vercel.
  // Preview settings do not configure the deployed Vercel service.
  preview:{proxy:{'^/(health|coverage|stops|route|compare|algorithms|gaps|letters|accessibility|data-sources|mobility-profiles|geocode|mcp|admin)(/|\\?|$)':{target:'http://127.0.0.1:8000',changeOrigin:true}}},
})
