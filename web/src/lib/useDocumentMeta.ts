import { useEffect } from 'react';
import { getCurrentMarketId } from '../config/market';

export interface DocumentMeta {
  title: string;
  description?: string;
  /** Path segment (e.g. '/znakomstva'). Combined with the current origin
   *  to produce both <link rel="canonical"> and og:url. */
  canonicalPath?: string;
  /** Absolute URL of the OpenGraph preview image. */
  ogImage?: string;
  /** When true, emits <meta name="robots" content="noindex,nofollow">. */
  noindex?: boolean;
  /** Optional JSON-LD payload(s). When provided, the hook injects
   *  <script type="application/ld+json"> tags into <head> and removes
   *  them on unmount. Use for ``Service`` / ``FAQPage`` / ``HowTo``
   *  schemas on scenario landings — Google + Yandex pick those up
   *  even on JS-rendered SPAs. */
  jsonLd?: Record<string, unknown> | Record<string, unknown>[];
  /**
   * 1.59.0 — when ``true`` (default) the hook also emits hreflang
   * link tags for ``ru`` / ``en`` / ``x-default`` so Google can pair
   * up the two regional builds (``ailookstudio.ru`` and ``ailookstudio.com``)
   * for the same path. Pass ``false`` on routes that intentionally
   * exist only on one market (e.g. ``/admin``).
   */
  emitHreflang?: boolean;
}

/**
 * 1.59.0 — single source of truth for the public domains. Used by
 * the hreflang emitter and the canonical resolver. Order:
 * ``ru`` first (the existing canonical origin), ``en`` second.
 */
export const SEO_DOMAINS = {
  ru: 'https://ailookstudio.ru',
  en: 'https://ailookstudio.com',
} as const;

const PRODUCTION_ORIGIN = SEO_DOMAINS.ru;

function ensureMetaByName(name: string): HTMLMetaElement {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute('name', name);
    document.head.appendChild(el);
  }
  return el;
}

function ensureMetaByProperty(property: string): HTMLMetaElement {
  let el = document.head.querySelector<HTMLMetaElement>(
    `meta[property="${property}"]`,
  );
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute('property', property);
    document.head.appendChild(el);
  }
  return el;
}

function ensureLinkByRel(rel: string): HTMLLinkElement {
  let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement('link');
    el.setAttribute('rel', rel);
    document.head.appendChild(el);
  }
  return el;
}

function _resolveOrigin(): string {
  // 1.59.0 — pick the canonical origin per market. RU build →
  // ailookstudio.ru, EN build → ailookstudio.com. We still honour the
  // current window origin when it matches one of the production
  // hosts so previewing on the live host doesn't switch to the other
  // domain's canonical.
  if (typeof window !== 'undefined' && window.location?.hostname) {
    const host = window.location.hostname;
    if (host.endsWith('ailookstudio.ru')) return SEO_DOMAINS.ru;
    if (host.endsWith('ailookstudio.com')) return SEO_DOMAINS.en;
  }
  return getCurrentMarketId() === 'ru' ? SEO_DOMAINS.ru : SEO_DOMAINS.en;
}

function buildCanonicalUrl(canonicalPath: string | undefined): string | null {
  if (!canonicalPath) return null;
  const origin = _resolveOrigin();
  const path = canonicalPath.startsWith('/') ? canonicalPath : `/${canonicalPath}`;
  return `${origin}${path}`;
}

function _normalizePath(canonicalPath: string): string {
  return canonicalPath.startsWith('/') ? canonicalPath : `/${canonicalPath}`;
}

const HREFLANG_ATTR = 'data-doc-meta-hreflang';

function _ensureHreflangLink(hreflang: string): HTMLLinkElement {
  let el = document.head.querySelector<HTMLLinkElement>(
    `link[${HREFLANG_ATTR}="${hreflang}"]`,
  );
  if (!el) {
    el = document.createElement('link');
    el.setAttribute('rel', 'alternate');
    el.setAttribute('hreflang', hreflang);
    el.setAttribute(HREFLANG_ATTR, hreflang);
    document.head.appendChild(el);
  }
  return el;
}

function _removeHreflangLinks(): void {
  document.head
    .querySelectorAll<HTMLLinkElement>(`link[${HREFLANG_ATTR}]`)
    .forEach((el) => {
      try { el.remove(); } catch { /* ignore */ }
    });
}

/**
 * Apply per-route meta tags for SEO + OpenGraph. SPA-only (no SSR), so
 * crawlers that execute JS (Googlebot, YandexBot v2024+) will see the
 * updated tags. Static crawlers fall back to whatever ships in
 * `web/index.html`.
 */
export default function useDocumentMeta(meta: DocumentMeta): void {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = meta.title;

    const description = (meta.description ?? '').trim();
    if (description) {
      ensureMetaByName('description').setAttribute('content', description);
      ensureMetaByProperty('og:description').setAttribute('content', description);
    }

    ensureMetaByProperty('og:title').setAttribute('content', meta.title);
    ensureMetaByProperty('og:type').setAttribute('content', 'website');

    const canonicalUrl = buildCanonicalUrl(meta.canonicalPath);
    if (canonicalUrl) {
      ensureLinkByRel('canonical').setAttribute('href', canonicalUrl);
      ensureMetaByProperty('og:url').setAttribute('content', canonicalUrl);
    }

    // 1.59.0 — hreflang alternates for the RU/EN regional builds.
    // The path is identical on both deployments (the SPA routes are
    // shared); only the origin differs. Always emit ``x-default``
    // pointing at the global EN host because that is the
    // language-agnostic landing for international searches.
    _removeHreflangLinks();
    if (meta.canonicalPath && (meta.emitHreflang ?? true)) {
      const path = _normalizePath(meta.canonicalPath);
      _ensureHreflangLink('ru-ru').setAttribute('href', `${SEO_DOMAINS.ru}${path}`);
      _ensureHreflangLink('ru').setAttribute('href', `${SEO_DOMAINS.ru}${path}`);
      _ensureHreflangLink('en').setAttribute('href', `${SEO_DOMAINS.en}${path}`);
      _ensureHreflangLink('x-default').setAttribute('href', `${SEO_DOMAINS.en}${path}`);
      const ogLocale = ensureMetaByProperty('og:locale');
      ogLocale.setAttribute('content', getCurrentMarketId() === 'ru' ? 'ru_RU' : 'en_US');
      const ogLocaleAlt = document.head.querySelector<HTMLMetaElement>(
        'meta[property="og:locale:alternate"]',
      ) ?? document.createElement('meta');
      ogLocaleAlt.setAttribute('property', 'og:locale:alternate');
      ogLocaleAlt.setAttribute(
        'content',
        getCurrentMarketId() === 'ru' ? 'en_US' : 'ru_RU',
      );
      if (!ogLocaleAlt.parentElement) document.head.appendChild(ogLocaleAlt);
    }

    if (meta.ogImage) {
      ensureMetaByProperty('og:image').setAttribute('content', meta.ogImage);
      ensureMetaByName('twitter:card').setAttribute('content', 'summary_large_image');
      ensureMetaByName('twitter:image').setAttribute('content', meta.ogImage);
    }

    const robots = ensureMetaByName('robots');
    robots.setAttribute('content', meta.noindex ? 'noindex,nofollow' : 'index,follow');

    const ldNodes: HTMLScriptElement[] = [];
    if (meta.jsonLd) {
      const payloads = Array.isArray(meta.jsonLd) ? meta.jsonLd : [meta.jsonLd];
      for (const payload of payloads) {
        const node = document.createElement('script');
        node.type = 'application/ld+json';
        node.setAttribute('data-doc-meta', '1');
        node.textContent = JSON.stringify(payload);
        document.head.appendChild(node);
        ldNodes.push(node);
      }
    }

    return () => {
      document.title = previousTitle;
      for (const node of ldNodes) {
        try { node.remove(); } catch { /* ignore */ }
      }
      // We don't strip individual meta tags — the next page's effect will
      // overwrite them. Leaving a stale tag for a microtask between unmount
      // and the next mount is fine (and avoids flicker for crawlers).
    };
  }, [
    meta.title,
    meta.description,
    meta.canonicalPath,
    meta.ogImage,
    meta.noindex,
    meta.jsonLd,
    meta.emitHreflang,
  ]);
}

// Reference to silence unused-import linter when PRODUCTION_ORIGIN is not used directly.
void PRODUCTION_ORIGIN;
