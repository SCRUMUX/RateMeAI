import i18next from 'i18next';
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
    slug: 'dating-photo',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/znakomstva',
    apiMode: 'dating',
    scoresCategory: 'dating',
    styles: { kind: 'inherit', category: 'dating' },
    hideCategoryTabs: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'resume-photo',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/rezume',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'inherit', category: 'cv' },
    hideCategoryTabs: true,
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
  // ----- Visa scenarios -----
  // Phase 3a: Schengen pilot. Visa scenarios are a thin reuse of the
  // document-photo flow (`step3Mode: 'document_formats'`) — the actual
  // document format catalog comes from the API
  // (``/api/v1/catalog/scenario-styles?scenario=<slug>``) so adding a
  // new visa is data-only on this side: append a record below + add
  // a corresponding entry in ``data/scenarios.json`` and seed
  // ``data/landing_content.json`` with the localised copy.
  {
    slug: 'visa-schengen',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/schengen',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-schengen' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'visa-usa',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/usa',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-usa' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'visa-uk',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/uk',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-uk' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'visa-canada',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/canada',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-canada' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'visa-japan',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/japan',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-japan' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'visa-china',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/china',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-china' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'visa-uae',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/uae',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-uae' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'visa-australia',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/australia',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-australia' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'visa-korea',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/korea',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-korea' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
  {
    slug: 'visa-india',
    type: 'standalone',
    entryMode: 'landing',
    canonicalPath: '/visa/india',
    apiMode: 'cv',
    scoresCategory: 'cv',
    styles: { kind: 'scenario', slug: 'visa-india' },
    hideCategoryTabs: true,
    step3Mode: 'document_formats',
    paymentPackQty: 5,
    documentPaywall: true,
    primaryCtaMainApp: true,
    simplifiedAnalysis: true,
  },
];

export const SCENARIOS_BY_SLUG: Record<string, ScenarioDefinition> = Object.fromEntries(
  SCENARIO_LIST.map(s => [s.slug, s]),
);

// Human-readable labels for scenarios — used by Footer/Products column,
// SEO links, etc. The labels are sourced from the i18n bundle
// (``wizard.scenario.labels.<slug>``) so RU edge and global SPA can
// ship different copy without forking the scenario list. The static
// map below stays as a typed fallback for unit tests / non-React
// contexts where i18next has not been initialised.
export const SCENARIO_LABELS_FALLBACK: Record<string, string> = {
  'document-photo': 'Фото на документы',
  'dating-photo': 'Фото для знакомств',
  'resume-photo': 'Фото на резюме',
  'tinder-pack': 'Tinder Pack',
  career: 'Карьера',
  'visa-schengen': 'Фото на шенгенскую визу',
  'visa-usa': 'Фото на визу США',
  'visa-uk': 'Фото на визу Великобритании',
  'visa-canada': 'Фото на визу Канады',
  'visa-japan': 'Фото на визу Японии',
  'visa-china': 'Фото на визу Китая',
  'visa-uae': 'Фото на визу ОАЭ',
  'visa-australia': 'Фото на визу Австралии',
  'visa-korea': 'Фото на визу Южной Кореи',
  'visa-india': 'Фото на визу Индии',
};

export function getScenarioLabel(slug: string): string {
  const key = `scenario.labels.${slug}`;
  if (i18next.isInitialized && i18next.exists(key, { ns: 'wizard' })) {
    return i18next.t(key, { ns: 'wizard' });
  }
  return SCENARIO_LABELS_FALLBACK[slug] ?? slug;
}

export function listScenariosForFooter(): Array<{ slug: string; label: string; href: string }> {
  // 1.50.6: only standalone landing scenarios (entryMode === 'landing')
  // are surfaced in the footer. Core-entry scenarios (career,
  // tinder-pack) are internal app sub-flows and don't have a public
  // landing page worth advertising in the footer "Products" column.
  return SCENARIO_LIST
    .filter((s) => s.entryMode === 'landing')
    .map((s) => ({
      slug: s.slug,
      label: getScenarioLabel(s.slug),
      href: s.canonicalPath,
    }));
}

export function getScenario(slug: string | undefined | null): ScenarioDefinition | null {
  if (!slug) return null;
  return SCENARIOS_BY_SLUG[slug] ?? null;
}

// Mirror of ``src/services/visa_compliance.is_approval_probability_scenario``:
// scenarios with ``analysis_display.mode == "approval_probability"`` (visas
// + document-photo) render the headline metric as "Probability of approval %"
// instead of "score / 10". The static check looks at the scenario slug —
// the live ``analysis_display`` block from ``/api/v1/scenarios/{slug}`` is
// the authoritative source but is not always available before the SPA hydrates,
// so we accept a slug fallback that matches the seeded ``data/scenarios.json``.
const APPROVAL_PROBABILITY_SLUGS = new Set<string>([
  'document-photo',
  'visa-schengen',
  'visa-usa',
  'visa-uk',
  'visa-canada',
  'visa-japan',
  'visa-china',
  'visa-uae',
  'visa-australia',
  'visa-korea',
  'visa-india',
]);

export function isApprovalProbabilityScenario(
  scenario: ScenarioDefinition | string | null | undefined,
): boolean {
  if (!scenario) return false;
  const slug = typeof scenario === 'string' ? scenario : scenario.slug;
  return APPROVAL_PROBABILITY_SLUGS.has(slug);
}

export function getApprovalProbabilityAfterPct(
  scenario: ScenarioDefinition | string | null | undefined,
): number | null {
  // Default success probability after improvement, mirroring the
  // ``success_probability_after_pct: 98.9`` block written into
  // ``data/scenarios.json`` for every approval-probability scenario.
  return isApprovalProbabilityScenario(scenario) ? 98.9 : null;
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
