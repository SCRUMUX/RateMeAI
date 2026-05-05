import { useEffect, useState } from 'react';
import { getLandingPage } from './api';
import type { SocialProofCounterConfig } from '../data/social-proof';

export type LandingBlockType =
  | 'api'
  | 'pricing'
  | 'footer'
  | 'social_proof'
  | 'proof_counter'
  | 'testimonials'
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

function asNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return fallback;
}

export interface ProofCounterContent {
  heading: string;
  subheading?: string;
  baseCount: number;
  counter: SocialProofCounterConfig;
}

const DEFAULT_PROOF_COUNTER_CONFIG: SocialProofCounterConfig = {
  minDelayMs: 8000,
  maxDelayMs: 36000,
  burstChance: 0.16,
  maxBurstSize: 3,
};

/**
 * Decode the `proof_counter` CMS block payload into the props shape
 * `<ProofCounter />` accepts. Any missing field falls back to a
 * sensible default so the component is never starved.
 *
 * For one rollout cycle we also accept the legacy
 * `caption`/`subcaption` field names as a fallback so an existing
 * production JSON file doesn't suddenly render with empty copy
 * during the deploy window.
 */
export function parseProofCounter(
  value: unknown,
  fallback: ProofCounterContent,
): ProofCounterContent {
  if (!value || typeof value !== 'object') return fallback;
  const obj = value as Record<string, unknown>;
  const counterRaw = obj.counter && typeof obj.counter === 'object'
    ? (obj.counter as Record<string, unknown>)
    : null;
  const counter: SocialProofCounterConfig = counterRaw
    ? {
        minDelayMs: asNumber(counterRaw.minDelayMs, fallback.counter.minDelayMs),
        maxDelayMs: asNumber(counterRaw.maxDelayMs, fallback.counter.maxDelayMs),
        burstChance: asNumber(counterRaw.burstChance, fallback.counter.burstChance),
        maxBurstSize: asNumber(counterRaw.maxBurstSize, fallback.counter.maxBurstSize),
      }
    : fallback.counter;
  const heading = (
    asString(obj.heading).trim()
    || asString(obj.caption).trim()
    || fallback.heading
  );
  const subheading = (
    asString(obj.subheading).trim()
    || asString(obj.subcaption).trim()
    || fallback.subheading
  );
  return {
    heading,
    subheading: subheading || undefined,
    baseCount: asNumber(obj.baseCount, fallback.baseCount),
    counter,
  };
}

export function defaultProofCounter(
  heading: string,
  subheading?: string,
  baseCount = 2734,
): ProofCounterContent {
  return {
    heading,
    subheading,
    baseCount,
    counter: DEFAULT_PROOF_COUNTER_CONFIG,
  };
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
