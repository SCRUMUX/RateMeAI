/**
 * Pricing render test — focuses on the CMS-fallback path that broke
 * 1.57.0 (empty global-server JSON => empty plan cards) and that
 * 1.58.0 fixed via `mergePlans` + `coalesceCmsString`.
 *
 * The test renders <Pricing /> with an "empty" CMS payload (mimicking
 * the global-server `landing_content.global.json`) and asserts that
 * the i18n defaults from `web/src/locales/ru/landing.json` show up in
 * the DOM. We use the RU bundle because `setup.ts` pins
 * `VITE_MARKET_ID=ru` and `landing.json` always carries the RU master
 * copy that the EN build inherits via `mergeDeep` at build time.
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
      <Pricing cmsPage={cmsPage} />
    </MemoryRouter>,
  );

describe('Pricing — CMS fallback', () => {
  const ruPricing = ruLanding.pricing as Record<string, unknown> & {
    plans: Record<string, { title: string; price: string; photos: string; desc: string }>;
  };

  it('renders i18n defaults when no CMS page is provided', () => {
    renderPricing(null);
    expect(screen.getByRole('heading', { level: 2, name: ruPricing.title as string })).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.try.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.refresh.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.boost.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.transform.title)).toBeInTheDocument();
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
              { title: '', price: '', photos: '', packQty: 1, desc: '' },
              { title: '', price: '', photos: '', packQty: 5, desc: '' },
              { title: '', price: '', photos: '', packQty: 15, desc: '' },
              { title: '', price: '', photos: '', packQty: 30, desc: '' },
            ],
          },
        },
      ],
    };
    renderPricing(emptyCms);
    expect(screen.getByText(ruPricing.plans.try.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.boost.title)).toBeInTheDocument();
    expect(screen.getByText(ruPricing.plans.transform.title)).toBeInTheDocument();
  });

  it('keeps non-empty CMS values', () => {
    const customCms: LandingPage = {
      blocks: [
        {
          id: 'pricing',
          type: 'pricing',
          enabled: true,
          data: {
            title: 'Custom heading',
            plans: [
              { title: 'Custom plan', price: '99 RUB', photos: '1 photo', packQty: 1, desc: 'desc' },
            ],
          },
        },
      ],
    };
    renderPricing(customCms);
    expect(screen.getByText('Custom heading')).toBeInTheDocument();
    expect(screen.getByText('Custom plan')).toBeInTheDocument();
    expect(screen.getByText('99 RUB')).toBeInTheDocument();
  });
});
