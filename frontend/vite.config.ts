import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发：5179 端口（5175 是槽位填充，不要占用）；/api 代理到教师后端 8005。
export default defineConfig({
  plugins: [react()],
  server: { port: 5179, host: '0.0.0.0', proxy: { '/api': 'http://127.0.0.1:8005' } },
})
