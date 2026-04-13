import { defineConfig, Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { writeFileSync, mkdirSync } from 'fs';

function versionJsonPlugin(): Plugin {
  return {
    name: 'version-json',
    writeBundle(options) {
      const outDir = options.dir || 'dist';
      const payload = {
        git: (process.env.DEPLOY_GIT_SHA || '').slice(0, 12),
        built_at: new Date().toISOString(),
      };
      mkdirSync(outDir, { recursive: true });
      writeFileSync(path.join(outDir, 'version.json'), JSON.stringify(payload));
    },
  };
}

export default defineConfig({
  plugins: [react(), versionJsonPlugin()],
  resolve: {
    alias: {
      '@ai-ds/core/icons': path.resolve(__dirname, 'src/icons/index.tsx'),
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
