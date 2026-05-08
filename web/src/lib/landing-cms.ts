import { useEffect, useState } from 'react';
import { getLandingPage } from './api';
import type { SocialProofCounterConfig } from '../data/social-proof';
import type { Testimonial, ReviewCategory, TestimonialTier } from '../data/testimonials';

export type LandingBlockType =
  | 'api'
  | 'pricing'
  | 'footer'
  | 'social_proof'
  | 'proof_counter'
  | 'testimonials'
  | 'six_categories'
  | 'before_after'
  | 'hero'
  | 'how_it_works'
  | 'final_cta'
  | 'scenario_pricing';

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

/**
 * CMS values can be `""` (deliberately blanked on the global server so
 * the SPA falls back to the i18n bundle). The naive
 * `typeof v === 'string' ? v : fallback` returns the empty string and
 * skips the fallback entirely, which is what produced empty Pricing
 * cards / empty Footer copyright strings on the EN build. Use this
 * helper everywhere a CMS field might be blank.
 */
export function coalesceCmsString(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback;
  const trimmed = value.trim();
  return trimmed ? value : fallback;
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

// --- scenario-landing block parsers --------------------------------------
// All four parsers share the same shape: take the raw block payload + a
// component-side fallback, return a fully-typed object. Missing fields
// always fall back to the JSX-baked default so an empty/broken JSON
// block renders the original landing copy instead of a blank section.

export interface HeroContent {
  icon: string;
  title: string;
  gradientPhrase: string;
  lead: string;
  ctaLabel: string;
  ctaMicrocopy: string;
  titleLine1?: string;
  titleLine2?: string;
  subLead?: string;
  platformsHint?: string;
}

export function parseHero(value: unknown, fallback: HeroContent): HeroContent {
  if (!value || typeof value !== 'object') return fallback;
  const obj = value as Record<string, unknown>;
  return {
    icon: asString(obj.icon).trim() || fallback.icon,
    title: asString(obj.title).trim() || fallback.title,
    gradientPhrase:
      asString(obj.gradient_phrase).trim()
      || asString(obj.gradientPhrase).trim()
      || fallback.gradientPhrase,
    lead: asString(obj.lead).trim() || fallback.lead,
    ctaLabel:
      asString(obj.cta_label).trim()
      || asString(obj.ctaLabel).trim()
      || fallback.ctaLabel,
    ctaMicrocopy:
      asString(obj.cta_microcopy).trim()
      || asString(obj.ctaMicrocopy).trim()
      || fallback.ctaMicrocopy,
    titleLine1: asString(obj.title_line_1 || obj.titleLine1).trim() || fallback.titleLine1,
    titleLine2: asString(obj.title_line_2 || obj.titleLine2).trim() || fallback.titleLine2,
    subLead: asString(obj.sub_lead || obj.subLead).trim() || fallback.subLead,
    platformsHint: asString(obj.platforms_hint || obj.platformsHint).trim() || fallback.platformsHint,
  };
}

export interface HowItWorksStepContent {
  num: string;
  title: string;
  desc: string;
}

export interface HowItWorksContent {
  title: string;
  steps: HowItWorksStepContent[];
}

export function parseHowItWorks(
  value: unknown,
  fallback: HowItWorksContent,
): HowItWorksContent {
  if (!value || typeof value !== 'object') return fallback;
  const obj = value as Record<string, unknown>;
  const stepsRaw = Array.isArray(obj.steps) ? obj.steps : null;
  if (!stepsRaw || !stepsRaw.length) {
    return {
      title: asString(obj.title).trim() || fallback.title,
      steps: fallback.steps,
    };
  }
  const steps: HowItWorksStepContent[] = stepsRaw
    .map((raw, idx) => {
      if (!raw || typeof raw !== 'object') return null;
      const r = raw as Record<string, unknown>;
      const fb = fallback.steps[idx] || {
        num: String(idx + 1),
        title: '',
        desc: '',
      };
      return {
        num: asString(r.num).trim() || fb.num,
        title: asString(r.title).trim() || fb.title,
        desc: asString(r.desc).trim() || fb.desc,
      };
    })
    .filter((s): s is HowItWorksStepContent => !!s && (!!s.title || !!s.desc));
  return {
    title: asString(obj.title).trim() || fallback.title,
    steps: steps.length ? steps : fallback.steps,
  };
}

export interface FinalCtaContent {
  brandHeading: string;
  h2: string;
  lead: string;
  ctaSignedInLabel: string;
  ctaAnonymousLabel: string;
}

export function parseFinalCta(
  value: unknown,
  fallback: FinalCtaContent,
): FinalCtaContent {
  if (!value || typeof value !== 'object') return fallback;
  const obj = value as Record<string, unknown>;
  return {
    brandHeading:
      asString(obj.brand_heading).trim()
      || asString(obj.brandHeading).trim()
      || fallback.brandHeading,
    h2: asString(obj.h2).trim() || fallback.h2,
    lead: asString(obj.lead).trim() || fallback.lead,
    ctaSignedInLabel:
      asString(obj.cta_signed_in_label).trim()
      || asString(obj.ctaSignedInLabel).trim()
      || fallback.ctaSignedInLabel,
    ctaAnonymousLabel:
      asString(obj.cta_anonymous_label).trim()
      || asString(obj.ctaAnonymousLabel).trim()
      || fallback.ctaAnonymousLabel,
  };
}

export interface ScenarioPricingContent {
  tagline: string;
}

export function parseTestimonials(value: unknown, fallback: Testimonial[]): Testimonial[] {
  if (!value || typeof value !== 'object') return fallback;
  const obj = value as Record<string, unknown>;
  const items = obj.items;
  if (!Array.isArray(items)) return fallback;

  const parsed = items.map((raw) => {
    if (!raw || typeof raw !== 'object') return null;
    const r = raw as Record<string, unknown>;
    const dr = r.deltaRange || r.delta_range;
    return {
      id: asString(r.id),
      styleKey: asString(r.styleKey || r.style_key),
      category: (asString(r.category) || 'social') as ReviewCategory,
      nickname: asString(r.nickname),
      shortReview: asString(r.shortReview || r.short_review),
      fullReview: asString(r.fullReview || r.full_review),
      emojiReview: asString(r.emojiReview || r.emoji_review),
      avatarSeed: asString(r.avatarSeed || r.avatar_seed) || asString(r.id),
      tier: (asString(r.tier) === 'Премиум' ? 'Премиум' : 'Обычный') as TestimonialTier,
      beforeScore: asNumber(r.beforeScore || r.before_score, 0),
      afterScore: asNumber(r.afterScore || r.after_score, 0),
      deltaRange: Array.isArray(dr) && dr.length >= 2 ? [asNumber(dr[0], 0), asNumber(dr[1], 0)] : [0, 0],
      usage: 'carousel',
    } as Testimonial;
  }).filter((t): t is Testimonial => t !== null && !!t.id);

  return parsed.length > 0 ? parsed : fallback;
}

export function parseScenarioPricing(
  value: unknown,
  fallback: ScenarioPricingContent,
): ScenarioPricingContent {
  if (!value || typeof value !== 'object') return fallback;
  const obj = value as Record<string, unknown>;
  return {
    tagline: asString(obj.tagline).trim() || fallback.tagline,
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

// --- generic per-slug cache (scenario landings) ---------------------------
// Mirrors the `home` cache but keyed by slug. The `home` slug gets its
// own dedicated path (above) for backward compatibility — every landing
// component that already calls `useLandingHome()` keeps working untouched.

const slugCache = new Map<string, LandingPage | null>();
const slugPromises = new Map<string, Promise<LandingPage | null>>();
const slugSubscribers = new Map<
  string,
  Set<(page: LandingPage | null) => void>
>();

function fetchSlug(slug: string): Promise<LandingPage | null> {
  const existing = slugPromises.get(slug);
  if (existing) return existing;
  const promise = getLandingPage(slug)
    .then((res) => {
      const page = asLandingPage(res.page);
      slugCache.set(slug, page);
      slugSubscribers.get(slug)?.forEach((fn) => fn(page));
      return page;
    })
    .catch(() => {
      slugCache.set(slug, null);
      slugSubscribers.get(slug)?.forEach((fn) => fn(null));
      return null;
    });
  slugPromises.set(slug, promise);
  return promise;
}

export function useLandingPage(slug: string): LandingPage | null {
  const [page, setPage] = useState<LandingPage | null>(
    slugCache.get(slug) ?? null,
  );

  useEffect(() => {
    let cancelled = false;
    const subscriber = (value: LandingPage | null) => {
      if (!cancelled) setPage(value);
    };
    let bucket = slugSubscribers.get(slug);
    if (!bucket) {
      bucket = new Set();
      slugSubscribers.set(slug, bucket);
    }
    bucket.add(subscriber);

    const cached = slugCache.get(slug);
    if (cached !== undefined) {
      setPage(cached);
    } else {
      void fetchSlug(slug);
    }

    return () => {
      cancelled = true;
      bucket?.delete(subscriber);
    };
  }, [slug]);

  return page;
}
