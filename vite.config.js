import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({mode}) => ({
  plugins: [react()],
  root: 'frontend',
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
}))