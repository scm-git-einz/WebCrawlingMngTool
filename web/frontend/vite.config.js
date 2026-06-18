import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import { readFileSync, existsSync } from 'fs'

function loadEnvFile() {
  const envPath = resolve(__dirname, '..', '..', '.env')
  const vars = {}
  if (!existsSync(envPath)) return vars
  readFileSync(envPath, 'utf-8').split('\n').forEach(line => {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) return
    const idx = trimmed.indexOf('=')
    if (idx > 0) vars[trimmed.slice(0, idx).trim()] = trimmed.slice(idx + 1).trim()
  })
  return vars
}

const env = loadEnvFile()
const serverHost = env.API_HOST || env.SERVER_HOST || '10.149.67.179'
const serverPort = env.SERVER_PORT || '8000'
const webPort = parseInt(env.WEB_PORT || '5173', 10)

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: webPort,
    proxy: {
      '/api': {
        target: `http://${serverHost}:${serverPort}`,
        changeOrigin: true,
      },
    },
  },
})
