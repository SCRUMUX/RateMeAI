import { defineConfig, Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { writeFileSync, mkdirSync } from 'fs';

function versionJsonPlugin(): Plugin {
  const gitSha = (process.env.DEPLOY_GIT_SHA || '').slice(0, 12);
  const buildTs = Date.now().toString(36);
  const cacheBuster = gitSha || buildTs;

  return {
    name: 'version-json',
    transformIndexHtml(html) {
      return html.replace(
        /favicon\.png\?v=\w+/g,
        `favicon.png?v=${cacheBuster}`,
      );
    },
    writeBundle(options) {
      const outDir = options.dir || 'dist';
      const payload = {
        git: gitSha,
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
    rollupOptions: {
      output: {
        // 1.33.1 — split heavy/admin code into dedicated chunks.
        //
        // Why: the 1.33.0 main bundle was 717 kB. ``framer-motion``
        // alone is ~140 kB and is used everywhere on the user path,
        // but admin pages add another ~120 kB that 99% of users
        // never load. Pull both into separate chunks so the main
        // bundle drops below the Vite 500 kB warning threshold and
        // first paint pulls less JavaScript.
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('framer-motion')) return 'framer-motion';
            if (id.includes('react-router-dom') || id.includes('@remix-run')) {
              return 'router';
            }
          }
          // Admin pages are already lazy-loaded in App.tsx; this
          // keeps any shared admin-only utilities together.
          if (id.includes('/src/pages/admin/')) return 'admin';
          return undefined;
        },
      },
    },
  },
});
