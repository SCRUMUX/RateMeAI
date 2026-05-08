/**
 * i18n initialization for the SPA.
 *
 * Strategy: build-time language selection by ``VITE_MARKET_ID`` (set in
 * the Vercel build for global, in ``docker-compose.ru.yml`` for the RU
 * edge). RU edge always renders Russian, the global instance always
 * renders English. There is intentionally **no runtime language toggle**
 * in the UI — the two markets are separate deployments with separate
 * databases, so each build ships its own language.
 *
 * Hostname fallback: if the env var is missing (e.g. preview deploys),
 * we look at ``window.location.hostname``: ``ru.*`` and ``ai-look-studio.ru``
 * map to RU, everything else maps to EN.
 */

import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';
import { getCurrentMarketId } from '../config/market';

import ruCommon from '../locales/ru/common.json';
import ruErrors from '../locales/ru/errors.json';
import ruWizard from '../locales/ru/wizard.json';
import ruSeo from '../locales/ru/seo.json';
import ruLanding from '../locales/ru/landing.json';
import ruModals from '../locales/ru/modals.json';
import ruAccount from '../locales/ru/account.json';
import ruScenarios from '../locales/ru/scenarios.json';
import ruPolicies from '../locales/ru/policies.json';
import ruCatalog from '../locales/ru/catalog.json';
import ruStyles from '../locales/ru/styles.json';
import ruSocialProof from '../locales/ru/socialProof.json';
import ruTestimonials from '../locales/ru/testimonials.json';
import enCommon from '../locales/en/common.json';
import enErrors from '../locales/en/errors.json';
import enWizard from '../locales/en/wizard.json';
import enSeo from '../locales/en/seo.json';
import enLanding from '../locales/en/landing.json';
import enModals from '../locales/en/modals.json';
import enAccount from '../locales/en/account.json';
import enScenarios from '../locales/en/scenarios.json';
import enPolicies from '../locales/en/policies.json';
import enCatalog from '../locales/en/catalog.json';
import enStyles from '../locales/en/styles.json';
import enSocialProof from '../locales/en/socialProof.json';
import enTestimonials from '../locales/en/testimonials.json';

export const SUPPORTED_LANGS = ['ru', 'en'] as const;
export type AppLang = (typeof SUPPORTED_LANGS)[number];

export function getAppLanguage(): AppLang {
  const market = getCurrentMarketId();
  return market === 'ru' ? 'ru' : 'en';
}

const resources = {
  ru: {
    common: ruCommon,
    errors: ruErrors,
    wizard: ruWizard,
    seo: ruSeo,
    landing: ruLanding,
    modals: ruModals,
    account: ruAccount,
    scenarios: ruScenarios,
    policies: ruPolicies,
    catalog: ruCatalog,
    styles: ruStyles,
    socialProof: ruSocialProof,
    testimonials: ruTestimonials,
  },
  en: {
    common: enCommon,
    errors: enErrors,
    wizard: enWizard,
    seo: enSeo,
    landing: enLanding,
    modals: enModals,
    account: enAccount,
    scenarios: enScenarios,
    policies: enPolicies,
    catalog: enCatalog,
    styles: enStyles,
    socialProof: enSocialProof,
    testimonials: enTestimonials,
  },
} as const;

void i18next.use(initReactI18next).init({
  resources,
  lng: getAppLanguage(),
  fallbackLng: 'en',
  ns: [
    'common',
    'errors',
    'wizard',
    'seo',
    'landing',
    'modals',
    'account',
    'scenarios',
    'policies',
    'catalog',
    'styles',
    'socialProof',
    'testimonials',
  ],
  defaultNS: 'common',
  interpolation: { escapeValue: false },
  returnNull: false,
});

if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('lang', getAppLanguage());
}

export default i18next;
