import { useEffect } from 'react';

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
}

const PRODUCTION_ORIGIN = 'https://ailookstudio.ru';

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

function buildCanonicalUrl(canonicalPath: string | undefined): string | null {
  if (!canonicalPath) return null;
  // Use the production origin for canonicals so preview deploys / local dev
  // don't pollute search index with multiple URLs for the same page.
  const origin = typeof window !== 'undefined' && window.location.origin && window.location.hostname.endsWith('ailookstudio.ru')
    ? window.location.origin
    : PRODUCTION_ORIGIN;
  const path = canonicalPath.startsWith('/') ? canonicalPath : `/${canonicalPath}`;
  return `${origin}${path}`;
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

    if (meta.ogImage) {
      ensureMetaByProperty('og:image').setAttribute('content', meta.ogImage);
      ensureMetaByName('twitter:card').setAttribute('content', 'summary_large_image');
      ensureMetaByName('twitter:image').setAttribute('content', meta.ogImage);
    }

    const robots = ensureMetaByName('robots');
    robots.setAttribute('content', meta.noindex ? 'noindex,nofollow' : 'index,follow');

    return () => {
      document.title = previousTitle;
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
  ]);
}
