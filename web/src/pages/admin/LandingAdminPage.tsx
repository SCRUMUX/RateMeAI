import { useCallback, useEffect, useMemo, useState } from 'react';
import * as api from '../../lib/api';
import { ApiError } from '../../lib/api';

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
    } catch (e) {
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
    <div className="min-h-screen bg-[#0E1216] text-[#E6EEF8] p-6">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Landing CMS Admin</h1>
          <p className="text-sm text-[#8b95a3] mt-1">
            Source of truth: <code>data/landing_content.json</code>. Сохраняем страницу целиком.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={activeSlug}
            onChange={(e) => {
              if (dirty && !window.confirm('Изменения не сохранены. Переключить страницу?')) return;
              setActiveSlug(e.target.value);
            }}
            className="px-3 py-2 rounded-lg border border-white/10 bg-transparent text-sm focus:outline-none focus:border-blue-400"
          >
            {(slugs ?? ['home']).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <button
            onClick={() => fetchPage(activeSlug)}
            className="px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5 text-sm"
            disabled={loading}
          >
            Reload
          </button>
          <button
            onClick={handleSave}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${canSave ? 'bg-blue-600 hover:bg-blue-500' : 'bg-white/10 text-[#8b95a3]'}`}
            disabled={!canSave}
          >
            Save
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4">
        <label className="block">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-xs text-[#8b95a3] uppercase tracking-wide">Page JSON</span>
            <span className="text-[11px] text-[#5a6470]">
              {loading ? 'Loading…' : dirty ? 'unsaved changes' : 'saved'}
            </span>
          </div>
          <textarea
            value={jsonText}
            onChange={(e) => { setJsonText(e.target.value); setDirty(true); }}
            className="w-full min-h-[70vh] p-3 rounded-lg border border-white/10 bg-black/30 text-xs font-mono focus:outline-none focus:border-blue-400"
            spellCheck={false}
          />
        </label>
      </div>
    </div>
  );
}

