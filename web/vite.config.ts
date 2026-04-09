import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@ai-ds/core/components': path.resolve(__dirname, '../AICADS-/packages/core/components/index.ts'),
      '@ai-ds/core/icons': path.resolve(__dirname, '../AICADS-/packages/core/components/icons/index.tsx'),
      '@ai-ds/core/hooks': path.resolve(__dirname, '../AICADS-/packages/core/hooks/index.ts'),
      '@ai-ds/core/shared': path.resolve(__dirname, '../AICADS-/packages/core/components/primitives/_shared/index.ts'),
      '@ai-ds/core/blocks': path.resolve(__dirname, '../AICADS-/packages/core/components/blocks/index.ts'),
      '@ai-ds/core/layout': path.resolve(__dirname, '../AICADS-/packages/core/layout/index.ts'),
      '@ai-ds/core/behaviors': path.resolve(__dirname, '../AICADS-/packages/core/behaviors/index.ts'),
      '@ai-ds/core/utils': path.resolve(__dirname, '../AICADS-/packages/core/utils/token-resolver.ts'),
      '@ai-ds/core': path.resolve(__dirname, '../AICADS-/packages/core/src/index.ts'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/storage': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
