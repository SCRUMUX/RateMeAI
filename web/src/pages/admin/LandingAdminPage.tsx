import { useCallback, useEffect, useMemo, useState } from 'react';
import * as api from '../../lib/api';
import { ApiError, getTokenForTarget } from '../../lib/api';
import { ADMIN_TARGETS, type AdminTargetId } from '../../lib/admin-targets';
import AdminLayout from './AdminLayout';

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return '{}';
  }
}

interface PerTargetSaveResult {
  target: AdminTargetId;
  status: 'ok' | 'failed' | 'skipped';
  message: string;
}

export default function LandingAdminPage() {
  const [slugs, setSlugs] = useState<string[] | null>(null);
  const [activeSlug, setActiveSlug] = useState<string>('home');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jsonText, setJsonText] = useState<string>('{}');
  const [dirty, setDirty] = useState(false);
  // Diagnostics for the "Apply to both" button. We persist the
  // outcome of the last write per target so the operator can see
  // exactly which instance accepted/rejected the change.
  const [bothResults, setBothResults] = useState<PerTargetSaveResult[] | null>(
    null,
  );

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
    setBothResults(null);
    try {
      await api.putAdminLandingPage(activeSlug, parsed);
      setDirty(false);
      await fetchSlugs();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setError(
          'Сессия не активна на этом target. Войдите на нужном домене и вернитесь.',
        );
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось сохранить');
      }
    } finally {
      setLoading(false);
    }
  }, [activeSlug, parseDraft, fetchSlugs]);

  /**
   * "Apply to both" — the whole reason this admin gained a target
   * switcher in 1.55. Landing JSON lives on disk per instance, so a
   * single PUT only updates the current region. We fan out one
   * request per target and report each outcome; failures don't roll
   * back since per-instance disk writes can't be transactional, and
   * the operator can always retry the failing target.
   */
  const handleSaveBoth = useCallback(async () => {
    const parsed = parseDraft();
    if (!parsed) return;
    setLoading(true);
    setError(null);
    const results: PerTargetSaveResult[] = [];
    for (const t of ADMIN_TARGETS) {
      if (!getTokenForTarget(t.id)) {
        results.push({
          target: t.id,
          status: 'skipped',
          message: `Нет токена для ${t.shortLabel}. Войдите на этом target и повторите.`,
        });
        continue;
      }
      try {
        await api.putAdminLandingPage(activeSlug, parsed, { target: t.id });
        results.push({
          target: t.id,
          status: 'ok',
          message: 'Сохранено.',
        });
      } catch (e) {
        const msg =
          e instanceof ApiError
            ? `${e.status} — ${e.body.slice(0, 200) || e.message}`
            : e instanceof Error
              ? e.message
              : 'Неизвестная ошибка';
        results.push({ target: t.id, status: 'failed', message: msg });
      }
    }
    const anyOk = results.some((r) => r.status === 'ok');
    if (anyOk) {
      setDirty(false);
    }
    setBothResults(results);
    setLoading(false);
    void fetchSlugs();
  }, [activeSlug, parseDraft, fetchSlugs]);

  return (
    <AdminLayout>
      <div className="flex flex-col tablet:flex-row tablet:items-start tablet:justify-between gap-[var(--space-16)] mb-[var(--space-32)]">
        <div className="flex flex-col gap-[var(--space-6)]">
          <h2 className="text-[24px] leading-[32px] font-semibold text-white">
            Landing CMS
          </h2>
          <p className="text-[13px] leading-[18px] text-[#8b95a3]">
            Источник данных: <code className="text-[#a8b1bf]">data/landing_content.json</code> на RU edge,
            {' '}
            <code className="text-[#a8b1bf]">data/landing_content.global.json</code> на primary.
            Контент пер-серверный — тот сервер, на который сейчас указывает «Цель» в шапке, и редактируется.
            Используйте кнопку «Применить на оба», когда правка действительно одинакова для RU и EN.
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
          <button
            onClick={handleSaveBoth}
            className={`px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] text-[13px] leading-[18px] font-medium ${canSave ? 'bg-emerald-600 hover:bg-emerald-500 text-white' : 'bg-white/10 text-[#8b95a3] cursor-not-allowed'}`}
            disabled={!canSave}
            title="Записать страницу одновременно на primary и RU"
          >
            Применить на оба
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-[var(--space-16)] px-[var(--space-16)] py-[var(--space-12)] bg-red-500/10 border border-red-500/30 rounded-[var(--radius-12)] text-[13px] leading-[18px] text-red-300">
          {error}
        </div>
      )}

      {bothResults && (
        <div className="mb-[var(--space-16)] rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] p-[var(--space-16)]">
          <div className="text-[12px] uppercase tracking-wide text-[#8b95a3] mb-[var(--space-8)]">
            Результат «Применить на оба»
          </div>
          <ul className="space-y-[var(--space-6)]">
            {bothResults.map((r) => {
              const tone =
                r.status === 'ok'
                  ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30'
                  : r.status === 'skipped'
                    ? 'text-amber-200 bg-amber-500/10 border-amber-500/30'
                    : 'text-red-300 bg-red-500/10 border-red-500/30';
              const icon =
                r.status === 'ok' ? '✓' : r.status === 'skipped' ? '◇' : '✗';
              const targetMeta =
                ADMIN_TARGETS.find((t) => t.id === r.target);
              return (
                <li
                  key={r.target}
                  className={`px-[var(--space-12)] py-[var(--space-8)] rounded-[8px] border text-[13px] leading-[18px] flex items-start gap-[var(--space-8)] ${tone}`}
                >
                  <span className="font-semibold w-[16px]">{icon}</span>
                  <span className="font-medium w-[110px] shrink-0">
                    {targetMeta?.shortLabel ?? r.target}
                  </span>
                  <span className="opacity-90 break-words">{r.message}</span>
                </li>
              );
            })}
          </ul>
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
