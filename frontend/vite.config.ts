import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const allowedFromEnv = (env.VITE_ALLOWED_HOSTS ?? '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
  const allowedHosts = allowedFromEnv.length
    ? allowedFromEnv
    : ['localhost', '127.0.0.1', '11gv92qt74799.vicp.fun']

  return {
    plugins: [vue()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      host: '0.0.0.0',
      port: 5174,
      strictPort: true,
      allowedHosts,
      proxy: {
        '/api': {
          target: env.VITE_API_TARGET || 'http://127.0.0.1:5006',
          changeOrigin: true,
          proxyTimeout: 600000,
          timeout: 600000,
        },
      },
    },
  }
})
