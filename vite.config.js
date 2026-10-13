import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'

const allowedHosts = ['sb-6arcjzg8cw04.vercel.run', '.vercel.run', 'localhost']

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    host: true,
    allowedHosts,
  },
  preview: {
    host: true,
    allowedHosts,
  },
})
