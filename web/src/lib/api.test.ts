import { describe, it, expect } from 'vitest';
import i18next from './i18n';
import { _extractLeadingEmoji, localizeApiStyle } from './api';

describe('_extractLeadingEmoji', () => {
  it('returns the leading emoji including trailing whitespace', () => {
    expect(_extractLeadingEmoji('🎬 Кино-стиль')).toBe('🎬 ');
  });

  it('returns an empty string when there is no leading emoji', () => {
    expect(_extractLeadingEmoji('Plain label')).toBe('');
  });

  it('handles compound (ZWJ) emojis like 👨‍🚀', () => {
    expect(_extractLeadingEmoji('👨‍🚀 Astronaut')).toMatch(/^👨/u);
  });
});

describe('localizeApiStyle', () => {
  it('preserves the leading RU emoji when applying a translated label', async () => {
    // Switch to EN so _lookupStyleString returns the English string for an
    // existing key from styles.json. This reproduces the production
    // EN-build path where the API ships a RU label like "📄 Паспорт РФ"
    // and the SPA must surface "📄 Russian passport" (icon kept).
    await i18next.changeLanguage('en');
    try {
      const localized = localizeApiStyle(
        {
          key: 'passport_rf',
          label: '📄 Паспорт РФ',
          hook: 'desc',
        },
        'documents',
      );
      expect(localized.label.startsWith('📄')).toBe(true);
      expect(localized.label).toContain('Russian passport');
    } finally {
      await i18next.changeLanguage('ru');
    }
  });

  it('keeps the original label when the i18n bundle has no entry for the key', async () => {
    await i18next.changeLanguage('en');
    try {
      const localized = localizeApiStyle(
        {
          key: '__not-a-real-key__',
          label: '🌟 Custom RU label',
          hook: 'desc',
        },
        'documents',
      );
      expect(localized.label).toBe('🌟 Custom RU label');
    } finally {
      await i18next.changeLanguage('ru');
    }
  });
});
