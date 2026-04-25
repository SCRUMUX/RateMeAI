import type { CategoryId, StyleItem } from '../data/styles';

export type ScenarioApiMode = 'dating' | 'cv' | 'social';
export type ScenarioType = 'core-entry' | 'standalone';
export type ScenarioEntryMode = 'app' | 'landing';

// `kind: 'inherit'` defers to the live mode catalog (loaded by AppContext
// via `getCatalogStyles(mode)`).
// `kind: 'scenario'` fetches a curated bucket from
// `/api/v1/catalog/scenario-styles?scenario=<slug>` — used for
// document-photo and tinder-pack, which are tagged with the `scenario`
// field in `data/styles.json` and excluded from the main catalog.
// `kind: 'list'` keeps a static client-side override for future cases
// where neither of the above fits; right now nothing uses it.
export type ScenarioStylesSource =
  | { kind: 'inherit'; category: CategoryId }
  | { kind: 'scenario'; slug: string }
  | { kind: 'list'; items: StyleItem[] };

export type ScenarioStep3Mode = 'styles' | 'document_formats';

export interface ScenarioDefinition {
  slug: string;
  type: ScenarioType;
  entryMode: ScenarioEntryMode;
  canonicalPath: string;
  apiMode: ScenarioApiMode;
  scoresCategory: CategoryId;
  styles: ScenarioStylesSource;
  mergeIntoCategory?: CategoryId;
  hideCategoryTabs: boolean;
  step3Mode?: ScenarioStep3Mode;
  paymentPackQty?: number;
  documentPaywall?: boolean;
  primaryCtaMainApp?: boolean;
  simplifiedAnalysis?: boolean;
}

const SCENARIO_LIST: ScenarioDefinition[] = [
  {
    slug: 'document-photo',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/dokumenty',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'document-photo' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'career',
    type: 'core-entry',
    entryMode: 'app',
    canonicalPath: '/app/career',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'inherit', category: 'cv' },
    hideCategoryTabs: true,
  },
  {
    slug: 'tinder-pack',
    type: 'core-entry',
    entryMode: 'app',
    canonicalPath: '/app/tinder-pack',
    apiMode: 'dating',
    scoresCategory: 'dating',
    styles: { kind: 'scenario', slug: 'tinder-pack' },
    mergeIntoCategory: 'dating',
    hideCategoryTabs: true,
  },
];

export const SCENARIOS_BY_SLUG: Record<string, ScenarioDefinition> = Object.fromEntries(
  SCENARIO_LIST.map(s => [s.slug, s]),
);

export function getScenario(slug: string | undefined | null): ScenarioDefinition | null {
  if (!slug) return null;
  return SCENARIOS_BY_SLUG[slug] ?? null;
}

export function listAllowedScenarioSlugs(): string[] {
  return SCENARIO_LIST.map(s => s.slug);
}

export function resolveScenarioStyles(def: ScenarioDefinition | null): StyleItem[] | null {
  if (!def) return null;
  // Both `inherit` and `scenario` are API-driven (the latter via
  // `/api/v1/catalog/scenario-styles`) and resolved by AppContext.
  // Only the legacy `list` kind ships a frozen client-side array.
  if (def.styles.kind === 'list') return def.styles.items;
  return null;
}

export const POST_PAYMENT_STORAGE_KEY = 'ailook_post_payment_path';

const SCENARIO_ROUTE_ALIASES: Record<string, string> = Object.fromEntries(
  SCENARIO_LIST.flatMap((scenario) => {
    const entries: Array<[string, string]> = [[scenario.canonicalPath, scenario.canonicalPath]];
    if (scenario.type === 'standalone') {
      entries.push([`/app/${scenario.slug}`, scenario.canonicalPath]);
    }
    return entries;
  }),
);

export function normalizePostPaymentPath(raw: string | null | undefined): string | null {
  if (raw == null || raw === '') return null;
  let path = raw.split('?')[0].trim();
  if (!path.startsWith('/')) path = `/${path}`;
  if (SCENARIO_ROUTE_ALIASES[path]) return SCENARIO_ROUTE_ALIASES[path];
  if (path === '/app') return '/app';
  if (!path.startsWith('/app/')) return null;
  const seg = path.slice('/app/'.length).split('/').filter(Boolean)[0];
  if (!seg) return '/app';
  if (!SCENARIOS_BY_SLUG[seg]) return null;
  return `/app/${seg}`;
}

export function setPostPaymentReturnPath(path: string): void {
  const normalized = normalizePostPaymentPath(path);
  if (normalized) {
    try {
      localStorage.setItem(POST_PAYMENT_STORAGE_KEY, normalized);
    } catch { /* ignore */ }
  }
}

export function getPostPaymentReturnPath(): string | null {
  try {
    return normalizePostPaymentPath(localStorage.getItem(POST_PAYMENT_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function consumePostPaymentReturnPath(): string {
  try {
    const raw = localStorage.getItem(POST_PAYMENT_STORAGE_KEY);
    localStorage.removeItem(POST_PAYMENT_STORAGE_KEY);
    return normalizePostPaymentPath(raw) ?? '/app';
  } catch {
    return '/app';
  }
}
