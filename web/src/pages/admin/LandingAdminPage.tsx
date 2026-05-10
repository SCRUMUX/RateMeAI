import { useCallback, useEffect, useMemo, useState } from 'react';
import * as api from '../../lib/api';
import { ApiError, type LandingMarket } from '../../lib/api';
import AdminLayout from './AdminLayout';

const FALLBACK_MARKETS: LandingMarket[] = ['ru', 'global'];

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return '{}';
  }
}

const MARKET_LABEL: Record<LandingMarket, string> = {
  ru: 'RU (ailookstudio.ru)',
  global: 'Global (ailookstudio.vercel.app)',
};

export default function LandingAdminPage() {
  const [markets, setMarkets] = useState<LandingMarket[]>(FALLBACK_MARKETS);
  const [activeMarket, setActiveMarket] = useState<LandingMarket>('ru');
  const [cmsRole, setCmsRole] = useState<'editor' | 'follower' | null>(null);

  const [slugs, setSlugs] = useState<string[] | null>(null);
  const [activeSlug, setActiveSlug] = useState<string>('home');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jsonText, setJsonText] = useState<string>('{}');
  const [dirty, setDirty] = useState(false);

  // Bootstrap the available markets + cms role once. The list is
  // tiny and never changes mid-session, so we cache it.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const meta = await api.listAdminLandingMarkets();
        if (cancelled) return;
        if (Array.isArray(meta.markets) && meta.markets.length) {
          setMarkets(meta.markets);
          if (!meta.markets.includes(activeMarket)) {
            setActiveMarket(meta.default ?? meta.markets[0]);
          }
        }
        setCmsRole(meta.cms_role ?? null);
      } catch {
        // Older deployments without the markets endpoint — fall back
        // to the static list and let read/write surface its own error.
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchSlugs = useCallback(async (market: LandingMarket) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAdminLandingPages(market);
      setSlugs(res.slugs);
      if (!res.slugs.includes(activeSlug)) {
        setActiveSlug(res.slugs[0] ?? 'home');
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setError(
          'Доступ запрещён. Этот аккаунт не в ADMIN_USER_IDS / ADMIN_EMAILS на Railway.',
        );
      } else if (e instanceof ApiError && e.status === 401) {
        setError('Сессия не активна. Войдите на ailookstudio.vercel.app и вернитесь.');
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить список страниц');
      }
      setSlugs([]);
    } finally {
      setLoading(false);
    }
  }, [activeSlug]);

  const fetchPage = useCallback(
    async (slug: string, market: LandingMarket) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.getAdminLandingPage(slug, market);
        setJsonText(pretty(res.page));
        setDirty(false);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить страницу');
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void fetchSlugs(activeMarket);
  }, [activeMarket, fetchSlugs]);

  useEffect(() => {
    void fetchPage(activeSlug, activeMarket);
  }, [activeSlug, activeMarket, fetchPage]);

  const canSave = useMemo(() => dirty && !loading, [dirty, loading]);
  const canEdit = cmsRole !== 'follower';

  const parseDraft = useCallback((): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(jsonText);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        setError('Страница должна быть JSON-объектом.');
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch {
      setError('JSON невалиден — исправьте и попробуйте снова.');
      return null;
    }
  }, [jsonText]);

  const handleSave = useCallback(async () => {
    const parsed = parseDraft();
    if (!parsed) return;
    setLoading(true);
    setError(null);
    try {
      await api.putAdminLandingPage(activeSlug, parsed, activeMarket);
      setDirty(false);
      await fetchSlugs(activeMarket);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        const detail = e.detail as { code?: string; message?: string } | undefined;
        if (detail?.code === 'cms_write_disabled') {
          setError(
            'Этот сервер — follower CMS. Откройте админку на Railway-домене (ailookstudio.vercel.app/admin/landing).',
          );
          return;
        }
        setError('Доступ запрещён.');
      } else if (e instanceof ApiError && e.status === 401) {
        setError('Сессия истекла. Войдите снова и повторите.');
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось сохранить');
      }
    } finally {
      setLoading(false);
    }
  }, [activeMarket, activeSlug, parseDraft, fetchSlugs]);

  return (
    <AdminLayout>
      <div className="flex flex-col tablet:flex-row tablet:items-start tablet:justify-between gap-[var(--space-16)] mb-[var(--space-32)]">
        <div className="flex flex-col gap-[var(--space-6)]">
          <h2 className="text-[24px] leading-[32px] font-semibold text-white">
            Landing CMS
          </h2>
          <p className="text-[13px] leading-[18px] text-[#8b95a3]">
            Единый CMS-хаб на Railway. Контент для каждого рынка хранится в{' '}
            <code className="text-[#a8b1bf]">data/landing_content.json</code> (RU) и{' '}
            <code className="text-[#a8b1bf]">data/landing_content.global.json</code> (Global).
            После сохранения изменения по webhook отправляются на RU edge,
            а почасовой safety-pull повторно сверяет хэши.
          </p>
          {cmsRole && (
            <p className="text-[12px] leading-[16px] text-[#8b95a3]">
              CMS role: <code className="text-[#a8b1bf]">{cmsRole}</code>
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-[var(--space-8)]">
          <select
            value={activeMarket}
            onChange={(e) => {
              if (dirty && !window.confirm('Изменения не сохранены. Переключить рынок?')) return;
              setActiveMarket(e.target.value as LandingMarket);
            }}
            className="px-[var(--space-12)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 bg-transparent text-[13px] leading-[18px] focus:outline-none focus:border-blue-400"
            title="Какой market редактируем"
          >
            {markets.map((m) => (
              <option key={m} value={m}>{MARKET_LABEL[m] ?? m}</option>
            ))}
          </select>
          <select
            value={activeSlug}
            onChange={(e) => {
              if (dirty && !window.confirm('Изменения не сохранены. Переключить страницу?')) return;
              setActiveSlug(e.target.value);
            }}
            className="px-[var(--space-12)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 bg-transparent text-[13px] leading-[18px] focus:outline-none focus:border-blue-400"
          >
            {(slugs ?? ['home']).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <button
            onClick={() => fetchPage(activeSlug, activeMarket)}
            className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 hover:bg-white/5 text-[13px] leading-[18px]"
            disabled={loading}
          >
            Обновить
          </button>
          <button
            onClick={handleSave}
            className={`px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] text-[13px] leading-[18px] font-medium ${canSave && canEdit ? 'bg-blue-600 hover:bg-blue-500' : 'bg-white/10 text-[#8b95a3] cursor-not-allowed'}`}
            disabled={!canSave || !canEdit}
            title={canEdit ? 'Сохранить изменения' : 'Read-only на follower-инстансе'}
          >
            Сохранить
          </button>
        </div>
      </div>

      {!canEdit && (
        <div className="mb-[var(--space-16)] px-[var(--space-16)] py-[var(--space-12)] bg-amber-500/10 border border-amber-500/30 rounded-[var(--radius-12)] text-[13px] leading-[18px] text-amber-200">
          Этот сервер работает в режиме <code>cms_role=follower</code>. Все правки делайте на{' '}
          <code>ailookstudio.vercel.app/admin/landing</code> — Railway автоматически продублирует
          контент сюда.
        </div>
      )}

      {error && (
        <div className="mb-[var(--space-16)] px-[var(--space-16)] py-[var(--space-12)] bg-red-500/10 border border-red-500/30 rounded-[var(--radius-12)] text-[13px] leading-[18px] text-red-300">
          {error}
        </div>
      )}

      <div className="rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] p-[var(--space-16)]">
        <div className="flex items-baseline justify-between mb-[var(--space-12)]">
          <span className="text-[11px] text-[#8b95a3] uppercase tracking-wide">Page JSON</span>
          <span className="text-[11px] text-[#5a6470]">
            {loading ? 'Загрузка…' : dirty ? 'не сохранено' : 'сохранено'}
          </span>
        </div>
        <textarea
          value={jsonText}
          onChange={(e) => { setJsonText(e.target.value); setDirty(true); }}
          className="w-full min-h-[60vh] p-[var(--space-16)] rounded-[var(--radius-8)] border border-white/10 bg-black/30 text-[12px] leading-[18px] font-mono focus:outline-none focus:border-blue-400"
          spellCheck={false}
          readOnly={!canEdit}
        />
      </div>
    </AdminLayout>
  );
}
