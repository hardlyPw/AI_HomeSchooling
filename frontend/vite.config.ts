import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8080, // 여기에 8080을 적어줍니다.
    strictPort: true, // 8080이 사용 중이면 에러를 내고 다른 포트를 쓰지 않게 함
  },
})