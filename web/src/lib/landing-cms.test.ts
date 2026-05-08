import { describe, it, expect } from 'vitest';
import {
  coalesceCmsString,
  parseHero,
  parseProofCounter,
  type HeroContent,
  type ProofCounterContent,
} from './landing-cms';

describe('coalesceCmsString', () => {
  it('returns the trimmed CMS value when it has visible characters', () => {
    expect(coalesceCmsString('  Hello world  ', 'fallback')).toBe('  Hello world  ');
    expect(coalesceCmsString('Hello', 'fallback')).toBe('Hello');
  });

  it('falls back when value is missing', () => {
    expect(coalesceCmsString(undefined, 'fallback')).toBe('fallback');
    expect(coalesceCmsString(null, 'fallback')).toBe('fallback');
  });

  it('falls back when value is the empty string (the global-server case)', () => {
    expect(coalesceCmsString('', 'fallback')).toBe('fallback');
  });

  it('falls back when value is whitespace only', () => {
    expect(coalesceCmsString('   ', 'fallback')).toBe('fallback');
    expect(coalesceCmsString('\n\t', 'fallback')).toBe('fallback');
  });

  it('falls back for non-string types instead of coercing', () => {
    expect(coalesceCmsString(42, 'fallback')).toBe('fallback');
    expect(coalesceCmsString({}, 'fallback')).toBe('fallback');
    expect(coalesceCmsString([], 'fallback')).toBe('fallback');
    expect(coalesceCmsString(true, 'fallback')).toBe('fallback');
  });
});

describe('parseHero', () => {
  const fallback: HeroContent = {
    icon: 'F',
    title: 'F-title',
    gradientPhrase: 'F-grad',
    lead: 'F-lead',
    ctaLabel: 'F-cta',
    ctaMicrocopy: 'F-cta-mc',
  };

  it('returns the fallback when payload is not an object', () => {
    expect(parseHero(undefined, fallback)).toEqual(fallback);
    expect(parseHero(null, fallback)).toEqual(fallback);
    expect(parseHero('string', fallback)).toEqual(fallback);
  });

  it('keeps non-empty CMS values', () => {
    const result = parseHero(
      {
        icon: '🚀',
        title: 'Real title',
        gradientPhrase: 'Real grad',
        lead: 'Real lead',
        ctaLabel: 'Go',
        ctaMicrocopy: 'free trial',
      },
      fallback,
    );
    expect(result.title).toBe('Real title');
    expect(result.gradientPhrase).toBe('Real grad');
    expect(result.icon).toBe('🚀');
  });

  it('falls back per-field when CMS field is empty (global-server case)', () => {
    const result = parseHero(
      {
        title: '',
        gradientPhrase: '   ',
        ctaLabel: 'Go',
      },
      fallback,
    );
    expect(result.title).toBe(fallback.title);
    expect(result.gradientPhrase).toBe(fallback.gradientPhrase);
    expect(result.ctaLabel).toBe('Go');
    expect(result.lead).toBe(fallback.lead);
  });

  it('accepts both snake_case and camelCase field names', () => {
    const snake = parseHero(
      { gradient_phrase: 'snake', cta_label: 'snake', cta_microcopy: 'snake' },
      fallback,
    );
    expect(snake.gradientPhrase).toBe('snake');
    expect(snake.ctaLabel).toBe('snake');
    expect(snake.ctaMicrocopy).toBe('snake');

    const camel = parseHero(
      { gradientPhrase: 'camel', ctaLabel: 'camel', ctaMicrocopy: 'camel' },
      fallback,
    );
    expect(camel.gradientPhrase).toBe('camel');
    expect(camel.ctaLabel).toBe('camel');
    expect(camel.ctaMicrocopy).toBe('camel');
  });
});

describe('parseProofCounter', () => {
  const fallback: ProofCounterContent = {
    heading: 'F-heading',
    subheading: 'F-subheading',
    baseCount: 1234,
    counter: {
      minDelayMs: 1000,
      maxDelayMs: 2000,
      burstChance: 0.1,
      maxBurstSize: 2,
    },
  };

  it('returns the fallback when payload is missing', () => {
    expect(parseProofCounter(undefined, fallback)).toEqual(fallback);
  });

  it('falls back when heading/subheading are blank strings', () => {
    const result = parseProofCounter(
      { heading: '', subheading: '   ', baseCount: 9000 },
      fallback,
    );
    expect(result.heading).toBe(fallback.heading);
    expect(result.subheading).toBe(fallback.subheading);
    expect(result.baseCount).toBe(9000);
  });

  it('still accepts the legacy caption/subcaption keys', () => {
    const result = parseProofCounter(
      { caption: 'Legacy heading', subcaption: 'Legacy sub' },
      fallback,
    );
    expect(result.heading).toBe('Legacy heading');
    expect(result.subheading).toBe('Legacy sub');
  });
});
