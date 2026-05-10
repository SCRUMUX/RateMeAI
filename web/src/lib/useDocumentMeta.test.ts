import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  SEO_DOMAINS,
  getCanonicalOrigin,
  getPublicOrigin,
} from './useDocumentMeta';

/**
 * Variant B regression tests for the canonical-origin resolver.
 *
 * The pre-Variant-B build hard-coded ``ailookstudio.com`` as the
 * global SEO origin and used a single hostname check for the RU
 * market. We now host the global SPA on ``ailookstudio.vercel.app``
 * and the RU SPA on ``ailookstudio.ru`` (apex + ``www``). The
 * resolver MUST continue to return the right origin for every host
 * variant we deploy to, otherwise canonical / og:url will leak the
 * wrong domain into search-engine indices.
 */

const ORIGINAL_LOCATION = window.location;

function setHostname(hostname: string): void {
  Object.defineProperty(window, 'location', {
    configurable: true,
    enumerable: true,
    writable: true,
    value: {
      ...ORIGINAL_LOCATION,
      hostname,
      host: hostname,
    },
  });
}

beforeEach(() => {
  setHostname('localhost');
});

afterEach(() => {
  Object.defineProperty(window, 'location', {
    configurable: true,
    enumerable: true,
    writable: true,
    value: ORIGINAL_LOCATION,
  });
});

describe('SEO_DOMAINS', () => {
  it('points at the Variant B production domains', () => {
    expect(SEO_DOMAINS.ru).toBe('https://ailookstudio.ru');
    expect(SEO_DOMAINS.en).toBe('https://ailookstudio.vercel.app');
  });
});

describe('getCanonicalOrigin', () => {
  it('returns the RU domain for the apex hostname', () => {
    setHostname('ailookstudio.ru');
    expect(getCanonicalOrigin()).toBe(SEO_DOMAINS.ru);
  });

  it('returns the RU domain for the www alias', () => {
    setHostname('www.ailookstudio.ru');
    expect(getCanonicalOrigin()).toBe(SEO_DOMAINS.ru);
  });

  it('returns the RU domain for the legacy ru.ailookstudio.ru subdomain', () => {
    setHostname('ru.ailookstudio.ru');
    expect(getCanonicalOrigin()).toBe(SEO_DOMAINS.ru);
  });

  it('returns the global domain for the Vercel host', () => {
    setHostname('ailookstudio.vercel.app');
    expect(getCanonicalOrigin()).toBe(SEO_DOMAINS.en);
  });

  it('returns the global domain for Vercel preview subdomains', () => {
    setHostname('ratemeai-git-feature-preview.ailookstudio.vercel.app');
    expect(getCanonicalOrigin()).toBe(SEO_DOMAINS.en);
  });

  it('falls back to getPublicOrigin for unknown hosts', () => {
    setHostname('localhost');
    expect(getCanonicalOrigin()).toBe(getPublicOrigin());
  });
});
