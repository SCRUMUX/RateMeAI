/**
 * Pricing render test — pinned to the 1.59.5 policy where CMS may
 * only override the section heading/caption strings, never the
 * ``plans`` array. Pre-1.59 deployments shipped a ``home`` CMS
 * document with stale tariffs (1/5/15/30 photos at $0.99/$2.99/
 * $6.99/$11.99 — RU equivalent in 59/199/499/899 ₽) which the SPA
 * used to merge over the i18n defaults; ``packQty`` in those rows no
 * longer exists in ``CREDIT_PACKS*`` so every "Buy" button reaching
 * the backend ended in "Failed to create payment". The component now
 * always renders defaults from ``web/src/locales/{ru,en}/landing.json``
 * regardless of what the CMS payload contains.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import '../lib/i18n';

vi.mock('../context/AppContext', () => ({
  useApp: () => ({ canAccessApp: true }),
}));

vi.mock('../lib/api', () => ({
  createPayment: vi.fn(),
  handleCreatePaymentError: () => 'mock-error',
}));

vi.mock('../scenarios/config', () => ({
  normalizePostPaymentPath: (p: string) => p,
  getPostPaymentReturnPath: () => '/app',
}));

vi.mock('../lib/flow-resume', () => ({
  rememberFlowReturnPath: vi.fn(),
}));

import Pricing from './Pricing';
import ruLanding from '../locales/ru/landing.json';
import { type LandingPage } from '../lib/landing-cms';
import { ToastProvider } from '../components/Toast';

beforeAll(() => {
  if (!('scrollTo' in HTMLElement.prototype)) {
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
  }
});

const renderPricing = (cmsPage?: LandingPage | null) =>
  render(
    <MemoryRouter>
      <ToastProvider>
        <Pricing cmsPage={cmsPage} />
      </ToastProvider>
    </MemoryRouter>,
  );

describe('Pricing — defaults always win for plans (1.59.5)', () => {
  const ruPricing = ruLanding.pricing as Record<string, unknown> & {
    plans: Record<string, { title: string; price: string; photos: string; desc: string }>;
  };

  it('renders i18n defaults when no CMS page is provided', () => {
    renderPricing(null);
    expect(screen.getByRole('heading', { level: 2, name: ruPricing.title as string })).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack5.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack10.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack20.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack50.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack5.price)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack50.price)).toBeInTheDocument();
  });

  it('falls back per field when CMS payload has empty strings (global-server case)', () => {
    const emptyCms: LandingPage = {
      blocks: [
        {
          id: 'pricing',
          type: 'pricing',
          enabled: true,
          data: {
            title: '',
            subtitle: '',
            caption: '',
            tryFreeLabel: '',
            plans: [
              { title: '', price: '', photos: '', packQty: 5, desc: '' },
              { title: '', price: '', photos: '', packQty: 10, desc: '' },
              { title: '', price: '', photos: '', packQty: 20, desc: '' },
              { title: '', price: '', photos: '', packQty: 50, desc: '' },
            ],
          },
        },
      ],
    };
    renderPricing(emptyCms);
    expect(screen.getByText(ruPricing.plans.pack5.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack10.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack50.title)).toBeInTheDocument();
  });

  it('keeps non-empty CMS heading strings but ignores plans[]', () => {
    const customCms: LandingPage = {
      blocks: [
        {
          id: 'pricing',
          type: 'pricing',
          enabled: true,
          data: {
            title: 'Custom heading',
            // CMS still ships the legacy 1/15/30 plans — must NOT bleed into the DOM.
            plans: [
              { title: 'Custom plan', price: '99 RUB', photos: '5 photos', packQty: 5, desc: 'desc' },
              { title: 'Stale 15', price: '499 RUB', photos: '15 photos', packQty: 15, desc: 'old' },
            ],
          },
        },
      ],
    };
    renderPricing(customCms);
    expect(screen.getByText('Custom heading')).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack5.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.pack50.title)).toBeInTheDocument();
    expect(screen.queryByText('Custom plan')).toBeNull();
    expect(screen.queryByText('99 RUB')).toBeNull();
    expect(screen.queryByText('Stale 15')).toBeNull();
    expect(screen.queryByText('499 RUB')).toBeNull();
    expect(screen.queryByText('15 photos')).toBeNull();
  });
});
