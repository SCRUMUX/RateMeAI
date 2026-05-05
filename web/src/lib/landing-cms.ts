import { useEffect, useState } from 'react';
import { getLandingPage } from './api';

export type LandingBlockType =
  | 'api'
  | 'pricing'
  | 'footer'
  | 'social_proof'
  | 'six_categories'
  | 'before_after';

export interface LandingBlock {
  id: string;
  type: LandingBlockType | string;
  enabled?: boolean;
  data?: Record<string, unknown>;
}

export interface LandingPage {
  blocks?: LandingBlock[];
}

export type FooterAction = 'link' | 'policy' | 'support';

export type FooterItem =
  | { label: string; action: 'link'; href: string; external?: boolean }
  | { label: string; action: 'policy'; policyId: string }
  | { label: string; action: 'support' };

export interface FooterSocialItem {
  label: string;
  href: string;
  icon?: string;
}

export interface FooterSupportContacts {
  telegram_url?: string;
  email?: string;
  faq?: Array<{ q: string; a: string }>;
}

export function asLandingPage(raw: unknown): LandingPage {
  if (!raw || typeof raw !== 'object') return {};
  return raw as LandingPage;
}

export function listBlocks(page: LandingPage | null | undefined): LandingBlock[] {
  const blocks = page?.blocks;
  if (!Array.isArray(blocks)) return [];
  return blocks.filter((b): b is LandingBlock => !!b && typeof b === 'object');
}

export function findBlock(page: LandingPage | null | undefined, type: string): LandingBlock | null {
  for (const b of listBlocks(page)) {
    if ((b.type || '') === type && (b.enabled ?? true)) return b;
  }
  return null;
}

// --- shared parsers --------------------------------------------------------

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

export function parseSupportContacts(value: unknown): FooterSupportContacts {
  if (!value || typeof value !== 'object') return {};
  const obj = value as Record<string, unknown>;
  const faq: Array<{ q: string; a: string }> = [];
  if (Array.isArray(obj.faq)) {
    for (const raw of obj.faq) {
      if (!raw || typeof raw !== 'object') continue;
      const r = raw as Record<string, unknown>;
      const q = asString(r.q).trim();
      const a = asString(r.a).trim();
      if (q && a) faq.push({ q, a });
    }
  }
  return {
    telegram_url: asString(obj.telegram_url) || undefined,
    email: asString(obj.email) || undefined,
    faq: faq.length ? faq : undefined,
  };
}

// --- shared cache for the home page ---------------------------------------
// All landings (Landing, DocumentPhotoLanding, DatingPhotoLanding,
// ResumePhotoLanding) need the same `home` page (Footer in particular).
// We coalesce concurrent fetches and cache the result for the session.

let homeCache: LandingPage | null = null;
let homePromise: Promise<LandingPage | null> | null = null;
const subscribers = new Set<(page: LandingPage | null) => void>();

function fetchHome(): Promise<LandingPage | null> {
  if (homePromise) return homePromise;
  homePromise = getLandingPage('home')
    .then((res) => {
      const page = asLandingPage(res.page);
      homeCache = page;
      subscribers.forEach((fn) => fn(page));
      return page;
    })
    .catch(() => {
      homeCache = null;
      subscribers.forEach((fn) => fn(null));
      return null;
    });
  return homePromise;
}

export function useLandingHome(): LandingPage | null {
  const [page, setPage] = useState<LandingPage | null>(homeCache);

  useEffect(() => {
    let cancelled = false;
    const subscriber = (value: LandingPage | null) => {
      if (!cancelled) setPage(value);
    };
    subscribers.add(subscriber);
    if (homeCache) {
      setPage(homeCache);
    } else {
      void fetchHome();
    }
    return () => {
      cancelled = true;
      subscribers.delete(subscriber);
    };
  }, []);

  return page;
}
