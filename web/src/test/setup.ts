/**
 * Global Vitest setup.
 *
 * Why this file exists:
 *  - jest-dom matchers (`toBeInTheDocument`, etc.) need to be registered
 *    once for all test files.
 *  - `web/src/lib/i18n.ts` initialises i18next at module-load time
 *    using `getCurrentMarketId()`, which reads
 *    `import.meta.env.VITE_MARKET_ID`. We pin the value here so tests
 *    don't depend on whatever the developer last set in `.env.local`.
 *  - Some components touch `window.matchMedia` / `IntersectionObserver`
 *    which jsdom doesn't ship by default. Provide minimal shims.
 */

import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

if (!('matchMedia' in window)) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

if (!('IntersectionObserver' in window)) {
  class MockIntersectionObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }
  (window as unknown as { IntersectionObserver: typeof MockIntersectionObserver }).IntersectionObserver =
    MockIntersectionObserver;
  (globalThis as unknown as { IntersectionObserver: typeof MockIntersectionObserver }).IntersectionObserver =
    MockIntersectionObserver;
}

if (!('ResizeObserver' in window)) {
  class MockResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  (window as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
  (globalThis as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
}

vi.stubEnv('VITE_MARKET_ID', 'ru');
