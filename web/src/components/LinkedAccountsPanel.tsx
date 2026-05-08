import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useApp } from '../context/AppContext';
import * as api from '../lib/api';

const PROVIDER_META: Record<string, { providerKey: string; color: string; icon: string }> = {
  telegram: { providerKey: 'telegram', color: '#229ED9', icon: 'T' },
  yandex: { providerKey: 'yandex', color: '#FC3F1D', icon: 'Я' },
  vk_id: { providerKey: 'vk_id', color: '#0077FF', icon: 'VK' },
  vk: { providerKey: 'vk', color: '#0077FF', icon: 'VK' },
  phone: { providerKey: 'phone', color: '#4ADE80', icon: '#' },
  ok: { providerKey: 'ok', color: '#EE8208', icon: 'OK' },
  web: { providerKey: 'web', color: '#6B7280', icon: 'W' },
};

export default function LinkedAccountsPanel() {
  const { identities, isAuthenticated } = useApp();
  const { t } = useTranslation('account');
  const [linkCode, setLinkCode] = useState<string | null>(null);
  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleGetCode = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.createLinkToken();
      setLinkCode(res.code);
      setLinkUrl(res.link_url);
    } catch {
      setLinkCode(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleCopy = useCallback(async () => {
    if (!linkCode) return;
    try {
      await navigator.clipboard.writeText(linkCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* fallback: user can read it */ }
  }, [linkCode]);

  if (!isAuthenticated) return null;

  return (
    <div className="flex flex-col gap-[var(--space-16)]">
      <h4 className="text-[16px] font-semibold text-[var(--color-text-primary)]">{t('linked.title')}</h4>

      <div className="flex flex-col gap-[var(--space-8)]">
        {identities.map((id) => {
          const meta = PROVIDER_META[id.provider] ?? { providerKey: id.provider, color: '#6B7280', icon: '?' };
          const providerLabel = t(`linked.providers.${meta.providerKey}`, { defaultValue: id.provider });
          const displayId = id.provider === 'web'
            ? t('linked.thisDevice')
            : (id.profile_data?.display_name
              || id.profile_data?.email
              || id.profile_data?.phone
              || id.profile_data?.first_name
              || id.external_id);
          return (
            <div
              key={`${id.provider}-${id.external_id}`}
              className="flex items-center gap-3 px-[var(--space-12)] py-[var(--space-8)] rounded-[var(--radius-8)] bg-[var(--glass-surface)]"
            >
              <span
                className="w-8 h-8 rounded-full flex items-center justify-center text-[12px] font-bold text-white shrink-0"
                style={{ background: meta.color }}
              >
                {meta.icon}
              </span>
              <div className="flex flex-col min-w-0">
                <span className="text-[14px] text-[var(--color-text-primary)] font-medium truncate">{providerLabel}</span>
                <span className="text-[12px] text-[var(--color-text-muted)] truncate">{displayId}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-col gap-[var(--space-8)]">
        {!linkCode ? (
          <button
            disabled={loading}
            onClick={handleGetCode}
            className="w-full flex items-center justify-center gap-2 px-[var(--space-16)] py-[var(--space-10)] text-[14px] rounded-[var(--radius-8)] font-medium transition-all disabled:opacity-50 bg-[var(--color-surface-2)] text-[var(--color-text-primary)] border border-[var(--color-border-base)]"
          >
            {loading ? t('linked.loading') : t('linked.getCode')}
          </button>
        ) : (
          <div className="flex flex-col gap-[var(--space-8)] items-center">
            <p className="text-[12px] text-[var(--color-text-secondary)] text-center">
              {t('linked.codeHint')}
            </p>
            <button
              onClick={handleCopy}
              className="px-6 py-3 rounded-[var(--radius-8)] text-[22px] font-mono tracking-[0.3em] font-bold transition-all bg-[var(--color-surface-2)] text-[var(--color-text-primary)] border border-[var(--color-border-base)]"
              title={t('linked.copyHint')}
            >
              {linkCode}
            </button>
            {copied && <span className="text-[12px] text-[var(--color-success-base)]">{t('linked.copied')}</span>}
            {linkUrl && (
              <p className="text-[11px] text-[var(--color-text-muted)] break-all text-center">
                {t('linked.openUrl', { url: linkUrl })}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
