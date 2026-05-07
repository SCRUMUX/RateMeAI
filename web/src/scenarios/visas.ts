/**
 * Visa scenarios catalog (frontend mirror of ``data/visa_requirements.json``).
 *
 * The router and AppContext walk through ``SCENARIO_LIST`` for routing,
 * but the visa landings need a few extra fields the generic scenario
 * shape doesn't expose (country slug for the URL, hero icon, output
 * size hint to render on the landing). Keeping this static makes
 * /visa/schengen render the right hero + size hint even before the
 * API-driven ``getScenarioPublic('visa-schengen')`` resolves.
 *
 * Adding a visa = one record here + one in ``data/scenarios.json`` +
 * one in ``data/visa_requirements.json`` + landing content. No code.
 */

export interface VisaScenarioMeta {
  /** matches ``Scenario.slug`` */
  slug: string;
  /** path segment used in /visa/<countrySlug> URLs */
  countrySlug: string;
  /** ``data/landing_content.json`` page slug */
  landingSlug: string;
  /** Localised country label keys (``t(countryLabelKey)``).
   *  We keep the keys here so the generic ``VisaLanding`` doesn't need
   *  to hardcode any RU/EN text. */
  countryLabelKey: string;
  /** Hero emoji rendered on the landing when CMS doesn't override */
  icon: string;
  /** Photo size hint shown next to the hero (purely visual) */
  sizeMm: [number, number];
  /** Aspect-ratio key for the image-gen postprocess
   *  (matches ``_CV_DOCUMENT_ASPECT`` in src/orchestrator/executor.py) */
  aspectKey: string;
}

export const VISA_SCENARIOS: VisaScenarioMeta[] = [
  {
    slug: 'visa-schengen',
    countrySlug: 'schengen',
    landingSlug: 'visa-schengen',
    countryLabelKey: 'wizard:scenario.labels.visa-schengen',
    icon: '🛂',
    sizeMm: [35, 45],
    aspectKey: 'visa_schengen',
  },
  {
    slug: 'visa-usa',
    countrySlug: 'usa',
    landingSlug: 'visa-usa',
    countryLabelKey: 'wizard:scenario.labels.visa-usa',
    icon: '🇺🇸',
    sizeMm: [51, 51],
    aspectKey: 'visa_usa',
  },
  {
    slug: 'visa-uk',
    countrySlug: 'uk',
    landingSlug: 'visa-uk',
    countryLabelKey: 'wizard:scenario.labels.visa-uk',
    icon: '🇬🇧',
    sizeMm: [35, 45],
    aspectKey: 'visa_uk',
  },
  {
    slug: 'visa-canada',
    countrySlug: 'canada',
    landingSlug: 'visa-canada',
    countryLabelKey: 'wizard:scenario.labels.visa-canada',
    icon: '🇨🇦',
    sizeMm: [35, 45],
    aspectKey: 'visa_canada',
  },
  {
    slug: 'visa-japan',
    countrySlug: 'japan',
    landingSlug: 'visa-japan',
    countryLabelKey: 'wizard:scenario.labels.visa-japan',
    icon: '🇯🇵',
    sizeMm: [45, 45],
    aspectKey: 'visa_japan',
  },
  {
    slug: 'visa-china',
    countrySlug: 'china',
    landingSlug: 'visa-china',
    countryLabelKey: 'wizard:scenario.labels.visa-china',
    icon: '🇨🇳',
    sizeMm: [33, 48],
    aspectKey: 'visa_china',
  },
  {
    slug: 'visa-uae',
    countrySlug: 'uae',
    landingSlug: 'visa-uae',
    countryLabelKey: 'wizard:scenario.labels.visa-uae',
    icon: '🇦🇪',
    sizeMm: [43, 55],
    aspectKey: 'visa_uae',
  },
  {
    slug: 'visa-australia',
    countrySlug: 'australia',
    landingSlug: 'visa-australia',
    countryLabelKey: 'wizard:scenario.labels.visa-australia',
    icon: '🇦🇺',
    sizeMm: [35, 45],
    aspectKey: 'visa_australia',
  },
  {
    slug: 'visa-korea',
    countrySlug: 'korea',
    landingSlug: 'visa-korea',
    countryLabelKey: 'wizard:scenario.labels.visa-korea',
    icon: '🇰🇷',
    sizeMm: [35, 45],
    aspectKey: 'visa_korea',
  },
  {
    slug: 'visa-india',
    countrySlug: 'india',
    landingSlug: 'visa-india',
    countryLabelKey: 'wizard:scenario.labels.visa-india',
    icon: '🇮🇳',
    sizeMm: [51, 51],
    aspectKey: 'visa_india',
  },
];

const _BY_COUNTRY: Record<string, VisaScenarioMeta> = Object.fromEntries(
  VISA_SCENARIOS.map((v) => [v.countrySlug, v]),
);

export function getVisaByCountry(countrySlug: string | undefined): VisaScenarioMeta | null {
  if (!countrySlug) return null;
  return _BY_COUNTRY[countrySlug] ?? null;
}

export function listVisaCountrySlugs(): string[] {
  return VISA_SCENARIOS.map((v) => v.countrySlug);
}
