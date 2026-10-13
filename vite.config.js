import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'

const allowedHosts = ['sb-6arcjzg8cw04.vercel.run', '.vercel.run', 'localhost']
const flaskTarget = process.env.FLASK_URL || 'http://127.0.0.1:5000'

export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    host: true,
    allowedHosts,
    proxy: {
      // Every page and API route is served by Flask; Vite only serves its own module/HMR paths.
      '^/(?!src/|@vite|@react-refresh|@id/|@fs/|node_modules/|__vite).*': {
        target: flaskTarget,
        changeOrigin: false,
      },
    },
  },
  preview: {
    host: true,
    allowedHosts,
  },
})
