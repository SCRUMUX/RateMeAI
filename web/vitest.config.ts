import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

/**
 * Vitest configuration is intentionally separate from `vite.config.ts`
 * to avoid coupling test environment config to the dev/build server.
 *
 * Highlights:
 *  - `jsdom` so React Testing Library can render components.
 *  - Setup file initialises i18next with the real RU/EN bundles so
 *    components that pull `t()` directly (instead of going through a
 *    mocked context) read realistic copy.
 *  - `globals: true` allows describe/it/expect without explicit
 *    imports, matching the developer experience in jest.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@ai-ds/core/icons': path.resolve(__dirname, 'src/icons/index.tsx'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', 'dist', 'tests/**', '.idea', '.git', '.cache'],
  },
});
