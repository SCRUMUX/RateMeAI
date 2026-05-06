import { useCallback, useEffect, useMemo, useState } from 'react';
import * as api from '../../lib/api';
import { ApiError } from '../../lib/api';
import AdminLayout from './AdminLayout';

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return '{}';
  }
}

export default function LandingAdminPage() {
  const [slugs, setSlugs] = useState<string[] | null>(null);
  const [activeSlug, setActiveSlug] = useState<string>('home');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jsonText, setJsonText] = useState<string>('{}');
  const [dirty, setDirty] = useState(false);

  const fetchSlugs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAdminLandingPages();
      setSlugs(res.slugs);
      if (res.slugs.includes(activeSlug)) return;
      if (res.slugs.length) setActiveSlug(res.slugs[0]);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setError('Доступ запрещён. Этот аккаунт не в ADMIN_USER_IDS.');
      } else if (e instanceof ApiError && e.status === 401) {
        setError('Сессия не активна. Войдите в основной кабинет и вернитесь.');
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить список страниц');
      }
      setSlugs([]);
    } finally {
      setLoading(false);
    }
  }, [activeSlug]);

  const fetchPage = useCallback(async (slug: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getAdminLandingPage(slug);
      setJsonText(pretty(res.page));
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить страницу');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchSlugs();
  }, [fetchSlugs]);

  useEffect(() => {
    void fetchPage(activeSlug);
  }, [activeSlug, fetchPage]);

  const canSave = useMemo(() => dirty && !loading, [dirty, loading]);

  const handleSave = useCallback(async () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(jsonText);
    } catch {
      setError('JSON невалиден — исправьте и попробуйте снова.');
      return;
    }
    if (!parsed || typeof parsed !== 'object') {
      setError('Страница должна быть JSON-объектом.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.putAdminLandingPage(activeSlug, parsed as Record<string, unknown>);
      setDirty(false);
      await fetchSlugs();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить');
    } finally {
      setLoading(false);
    }
  }, [activeSlug, jsonText, fetchSlugs]);

  return (
    <AdminLayout>
      <div className="flex flex-col tablet:flex-row tablet:items-start tablet:justify-between gap-[var(--space-16)] mb-[var(--space-32)]">
        <div className="flex flex-col gap-[var(--space-6)]">
          <h2 className="text-[24px] leading-[32px] font-semibold text-white">
            Landing CMS
          </h2>
          <p className="text-[13px] leading-[18px] text-[#8b95a3]">
            Источник данных: <code className="text-[#a8b1bf]">data/landing_content.json</code>. Сохраняем страницу целиком.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-[var(--space-8)]">
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
            onClick={() => fetchPage(activeSlug)}
            className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 hover:bg-white/5 text-[13px] leading-[18px]"
            disabled={loading}
          >
            Обновить
          </button>
          <button
            onClick={handleSave}
            className={`px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] text-[13px] leading-[18px] font-medium ${canSave ? 'bg-blue-600 hover:bg-blue-500' : 'bg-white/10 text-[#8b95a3] cursor-not-allowed'}`}
            disabled={!canSave}
          >
            Сохранить
          </button>
        </div>
      </div>

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
        />
      </div>
    </AdminLayout>
  );
}
