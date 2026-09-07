import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const target = process.env.PCB_API_PROXY ?? 'http://127.0.0.1:8000';
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': target, '/health': target, '/ready': target },
  },
  preview: { proxy: { '/api': target, '/health': target, '/ready': target } },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
