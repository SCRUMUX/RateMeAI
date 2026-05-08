import { useCallback, useEffect, useMemo, useState } from 'react';
import * as api from '../../lib/api';
import type {
  AdminLintIssue,
  AdminLintReport,
  AdminStyleEntry,
  AdminStyleSummary,
} from '../../lib/api';
import { ApiError, getTokenForTarget } from '../../lib/api';
import { ADMIN_TARGETS, type AdminTargetId } from '../../lib/admin-targets';
import AdminLayout from './AdminLayout';

type ModeFilter = 'all' | 'cv' | 'social' | 'dating' | string;

const MODES: ModeFilter[] = ['all', 'cv', 'social', 'dating'];
const MODE_LABELS: Record<string, string> = {
  all: 'Все',
  cv: 'Резюме',
  social: 'Соц.сети',
  dating: 'Знакомства',
};
const SCENARIO_OPTIONS = ['', 'document-photo', 'tinder-pack'];

const ALL_CHANNELS: readonly string[] = [
  'lighting',
  'weather',
  'time_of_day',
  'season',
  'framing',
  'clothing',
  'scene_override',
] as const;

const LOCATION_TYPES: readonly string[] = [
  '',
  'indoor',
  'outdoor',
  'mixed',
  'document',
] as const;

const DEFAULT_SEASONS = ['spring', 'summer', 'autumn', 'winter'];

interface PerTargetSaveResult {
  target: AdminTargetId;
  status: 'ok' | 'failed' | 'skipped';
  message: string;
}

function severityCounts(issues: AdminLintIssue[] | undefined): {
  errors: number;
  warnings: number;
} {
  if (!issues) return { errors: 0, warnings: 0 };
  let errors = 0;
  let warnings = 0;
  for (const i of issues) {
    if (i.severity === 'error') errors += 1;
    else if (i.severity === 'warning') warnings += 1;
  }
  return { errors, warnings };
}

// 2026-05: schema_version v1/v2 retired from the editor UI. The catalog
// is now 100% v3 — see data/styles.json. Legacy v2 fields (background,
// weather, context_slots) stay in JSON because style_loader_v2 still
// reads them in parallel for prompt assembly, but the editor doesn't
// expose them.
const EMPTY_V3_TEMPLATE: AdminStyleEntry = {
  id: '',
  mode: 'social',
  display_label: '',
  hook_text: '',
  scenario: null,
  unlock_after_generations: 0,
  is_scenario_only: false,
  schema_version: 3,
  meta: { param: 'appeal', delta_range: [0.1, 0.3] },
  trigger_pool: [''],
  scene_anchor: '',
  scene_overrides: [],
  background_lock: 'semi',
  ambient: { lighting: [], weather: [], time_of_day: [], season: [] },
  available_channels: [],
  location_type: '',
  clothing: {
    default: { male: '', female: '', neutral: '' },
    allowed: [],
    gender_neutral: true,
  },
  quality_identity: { base: '', per_model_tail: {} },
  expression: '',
};

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '' && !Number.isNaN(Number(value))) {
    return Number(value);
  }
  return fallback;
}

function asBool(value: unknown, fallback = false): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function csvFromArray(value: unknown): string {
  if (!Array.isArray(value)) return '';
  return value.filter((v) => typeof v === 'string').join(', ');
}

function arrayFromCsv(value: string): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function StylesAdminPage() {
  const [items, setItems] = useState<AdminStyleSummary[] | null>(null);
  const [lintReport, setLintReport] = useState<AdminLintReport>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [modeFilter, setModeFilter] = useState<ModeFilter>('all');
  const [issuesOnly, setIssuesOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<{ entry: AdminStyleEntry; isNew: boolean } | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.listAdminStyles();
      setItems(list);
      try {
        setLintReport(await api.lintAllAdminStyles());
      } catch {
        setLintReport({});
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setError('Доступ запрещён. Этот аккаунт не в ADMIN_USER_IDS.');
      } else if (e instanceof ApiError && e.status === 401) {
        setError('Сессия не активна. Войдите в основной кабинет и вернитесь.');
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить каталог');
      }
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchList();
  }, [fetchList]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = search.trim().toLowerCase();
    return items.filter((s) => {
      if (modeFilter !== 'all' && s.mode !== modeFilter) return false;
      if (issuesOnly && !lintReport[s.id]?.length) return false;
      if (!q) return true;
      return (
        s.id.toLowerCase().includes(q) ||
        s.display_label.toLowerCase().includes(q) ||
        s.hook_text.toLowerCase().includes(q)
      );
    });
  }, [items, modeFilter, issuesOnly, lintReport, search]);

  const totalIssues = useMemo(() => {
    let errors = 0;
    let warnings = 0;
    for (const sid of Object.keys(lintReport)) {
      const c = severityCounts(lintReport[sid]);
      errors += c.errors;
      warnings += c.warnings;
    }
    return { errors, warnings, dirtyStyles: Object.keys(lintReport).length };
  }, [lintReport]);

  const openEdit = useCallback(async (id: string) => {
    try {
      const entry = await api.getAdminStyle(id);
      setEditing({ entry, isNew: false });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить стиль');
    }
  }, []);

  const openCreate = useCallback(() => {
    setEditing({ entry: structuredClone(EMPTY_V3_TEMPLATE), isNew: true });
  }, []);

  const closeEdit = useCallback((dirty: boolean) => {
    if (dirty && !window.confirm('Изменения не сохранены. Закрыть редактор?')) {
      return;
    }
    setEditing(null);
  }, []);

  // 1.55.0: rethrow на ошибке. Раньше setError(...) рисовал баннер
  // на родительской странице, который полностью перекрывался модалкой
  // редактора (z-50 vs z-неопределён). Оператор видел "ничего не
  // произошло". Теперь модалка сама ловит исключение и показывает
  // ошибку внутри своей формы.
  const handleSave = useCallback(
    async (entry: AdminStyleEntry, isNew: boolean) => {
      if (isNew) {
        await api.createAdminStyle(entry);
      } else {
        await api.updateAdminStyle(entry.id, entry);
      }
      setEditing(null);
      await fetchList();
    },
    [fetchList],
  );

  /**
   * "Apply to both" for styles: write the entry to every declared
   * admin target (primary and RU). Each target has its own
   * ``data/styles.json`` on disk, so a single write only updates the
   * current region. Returns per-target results so the modal can
   * render a diagnostic banner.
   */
  const handleSaveBoth = useCallback(
    async (
      entry: AdminStyleEntry,
      isNew: boolean,
    ): Promise<PerTargetSaveResult[]> => {
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
          if (isNew) {
            await api.createAdminStyle(entry, { target: t.id });
          } else {
            await api.updateAdminStyle(entry.id, entry, { target: t.id });
          }
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
        await fetchList();
      }
      return results;
    },
    [fetchList],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      const ok = window.confirm(`Удалить стиль "${id}"?`);
      if (!ok) return;
      try {
        await api.deleteAdminStyle(id);
        await fetchList();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось удалить');
      }
    },
    [fetchList],
  );

  const handleReload = useCallback(async () => {
    try {
      const res = await api.reloadAdminStyles();
      setError(`Кэш перезагружен — ${res.count} стилей`);
      await fetchList();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось обновить кэш');
    }
  }, [fetchList]);

  return (
    <AdminLayout>
      <div className="flex flex-col tablet:flex-row tablet:items-start tablet:justify-between gap-[var(--space-16)] mb-[var(--space-32)]">
        <div className="flex flex-col gap-[var(--space-6)]">
          <h2 className="text-[24px] leading-[32px] font-semibold text-white">
            Каталог стилей
          </h2>
          <p className="text-[13px] leading-[18px] text-[#8b95a3]">
            Источник данных: <code className="text-[#a8b1bf]">data/styles.json</code>. Изменения сохраняются атомарно и обновляют кэш.
          </p>
        </div>
        <div className="flex flex-wrap gap-[var(--space-8)]">
          <button
            onClick={handleReload}
            className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 hover:bg-white/5 text-[13px] leading-[18px]"
          >
            Перезагрузить кэш
          </button>
          <button
            onClick={openCreate}
            className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-blue-600 hover:bg-blue-500 font-medium text-[13px] leading-[18px]"
          >
            + Новый стиль
          </button>
        </div>
      </div>

      {totalIssues.dirtyStyles > 0 && (
        <div className="mb-[var(--space-16)] px-[var(--space-16)] py-[var(--space-12)] bg-amber-500/10 border border-amber-500/30 rounded-[var(--radius-12)] text-[13px] leading-[18px] text-amber-200 flex flex-wrap items-center gap-[var(--space-12)]">
          <span>
            Линт: <strong>{totalIssues.errors}</strong> ошибок,{' '}
            <strong>{totalIssues.warnings}</strong> предупреждений в{' '}
            <strong>{totalIssues.dirtyStyles}</strong> стилях.
          </span>
          <button
            onClick={() => setIssuesOnly(!issuesOnly)}
            className={`ml-auto px-[var(--space-12)] py-[var(--space-4)] rounded-[var(--radius-pill)] border text-[12px] ${issuesOnly ? 'bg-amber-500/20 border-amber-500/50' : 'border-amber-500/30 hover:bg-amber-500/10'}`}
          >
            {issuesOnly ? 'Показать все' : 'Только с замечаниями'}
          </button>
        </div>
      )}

      {error && (
        <div className="mb-[var(--space-16)] px-[var(--space-16)] py-[var(--space-12)] bg-red-500/10 border border-red-500/30 rounded-[var(--radius-12)] text-[13px] leading-[18px] text-red-300">
          {error}
        </div>
      )}

      <div className="flex flex-col tablet:flex-row gap-[var(--space-12)] mb-[var(--space-24)]">
        <div className="flex gap-[2px] rounded-[var(--radius-pill)] border border-white/10 overflow-hidden h-[40px] p-[2px]">
          {MODES.map((m) => (
            <button
              key={m}
              onClick={() => setModeFilter(m)}
              className={`px-[var(--space-16)] text-[13px] leading-[18px] rounded-[var(--radius-pill)] transition-colors ${
                modeFilter === m
                  ? 'bg-blue-600 text-white'
                  : 'text-[#8b95a3] hover:bg-white/5 hover:text-white'
              }`}
            >
              {MODE_LABELS[m] ?? m}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по id, названию, hook…"
          className="flex-1 h-[40px] px-[var(--space-16)] rounded-[var(--radius-pill)] border border-white/10 bg-transparent text-[13px] leading-[18px] focus:outline-none focus:border-blue-400"
        />
        <span className="text-[12px] text-[#8b95a3] self-center whitespace-nowrap">
          {loading ? 'Загрузка…' : `${filtered.length} / ${items?.length ?? 0}`}
        </span>
      </div>

      <div className="overflow-x-auto rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02]">
        <table className="w-full text-[13px] leading-[18px]">
          <thead className="bg-white/[0.04] text-[#8b95a3] border-b border-white/10">
            <tr>
              <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">ID</th>
              <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Режим</th>
              <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Название</th>
              <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Линт</th>
              <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Разблокировка</th>
              <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Сценарий</th>
              <th className="text-right px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Действия</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => {
              const counts = severityCounts(lintReport[s.id]);
              const legacyVersion = s.schema_version !== 3;
              return (
                <tr key={s.id} className="border-t border-white/5 hover:bg-white/[0.03]">
                  <td className="px-[var(--space-16)] py-[var(--space-12)] font-mono text-[12px]">
                    <div className="flex items-center gap-[var(--space-8)]">
                      <span>{s.id}</span>
                      {legacyVersion && (
                        <span
                          title={`Стиль v${s.schema_version} — каталог уже на v3`}
                          className="px-[var(--space-6)] py-[1px] rounded text-[10px] bg-amber-500/15 border border-amber-500/30 text-amber-300"
                        >
                          v{s.schema_version}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)]">{s.mode}</td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)] truncate max-w-[280px]">{s.display_label}</td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)]">
                    {counts.errors === 0 && counts.warnings === 0 ? (
                      <span className="px-[var(--space-8)] py-[2px] rounded text-[10px] bg-emerald-500/15 border border-emerald-500/30 text-emerald-300">чисто</span>
                    ) : (
                      <span className="flex gap-[var(--space-4)]">
                        {counts.errors > 0 && (
                          <span className="px-[var(--space-8)] py-[2px] rounded text-[10px] bg-red-500/15 border border-red-500/30 text-red-300">
                            {counts.errors} ошиб.
                          </span>
                        )}
                        {counts.warnings > 0 && (
                          <span className="px-[var(--space-8)] py-[2px] rounded text-[10px] bg-amber-500/15 border border-amber-500/30 text-amber-300">
                            {counts.warnings} прдпр.
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)]">{s.unlock_after_generations || '—'}</td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)]">{s.scenario ?? '—'}</td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)] text-right whitespace-nowrap">
                    <button
                      onClick={() => openEdit(s.id)}
                      className="px-[var(--space-12)] py-[var(--space-6)] text-[12px] rounded-[var(--radius-pill)] border border-white/10 hover:bg-white/10 mr-[var(--space-8)]"
                    >
                      Изменить
                    </button>
                    <button
                      onClick={() => handleDelete(s.id)}
                      className="px-[var(--space-12)] py-[var(--space-6)] text-[12px] rounded-[var(--radius-pill)] border border-red-500/30 text-red-300 hover:bg-red-500/10"
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              );
            })}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-[var(--space-16)] py-[var(--space-32)] text-center text-[#8b95a3]">
                  <div className="flex flex-col gap-[var(--space-4)]">
                    <span className="text-[14px]">Ничего не найдено</span>
                    <span className="text-[12px] text-[#5a6470]">Попробуйте сбросить фильтры или поиск</span>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <StyleEditModal
          entry={editing.entry}
          isNew={editing.isNew}
          onClose={(dirty) => closeEdit(dirty)}
          onSave={(updated) => handleSave(updated, editing.isNew)}
          onSaveBoth={(updated) => handleSaveBoth(updated, editing.isNew)}
        />
      )}
    </AdminLayout>
  );
}

type V3FieldErrors = Partial<{
  trigger_pool: string;
  scene_anchor: string;
  clothing_default: string;
}>;

function validateV3Draft(draft: AdminStyleEntry): V3FieldErrors {
  const errors: V3FieldErrors = {};
  const triggerPool = Array.isArray(draft.trigger_pool)
    ? (draft.trigger_pool as unknown[]).filter(
        (v) => typeof v === 'string' && (v as string).trim() !== '',
      )
    : [];
  if (triggerPool.length === 0) {
    errors.trigger_pool = 'Нужна хотя бы одна формулировка trigger_pool';
  }
  if (!asString(draft.scene_anchor).trim()) {
    errors.scene_anchor = 'scene_anchor обязателен';
  }
  const clothing = asObject(draft.clothing);
  const clothingDefault = clothing.default;
  if (typeof clothingDefault === 'string') {
    if (!clothingDefault.trim()) {
      errors.clothing_default = 'clothing.default не может быть пустым';
    }
  } else if (clothingDefault && typeof clothingDefault === 'object') {
    const dict = clothingDefault as Record<string, unknown>;
    const hasAny = ['male', 'female', 'neutral'].some(
      (k) => typeof dict[k] === 'string' && (dict[k] as string).trim() !== '',
    );
    if (!hasAny) {
      errors.clothing_default = 'Заполните хотя бы одно из полей male / female / neutral';
    }
  } else {
    errors.clothing_default = 'clothing.default обязателен';
  }
  // quality_identity.base is no longer mandatory; an empty value correctly falls back to default
  return errors;
}

function StyleEditModal({
  entry,
  isNew,
  onClose,
  onSave,
  onSaveBoth,
}: {
  entry: AdminStyleEntry;
  isNew: boolean;
  onClose: (dirty: boolean) => void;
  onSave: (entry: AdminStyleEntry) => Promise<void>;
  onSaveBoth: (entry: AdminStyleEntry) => Promise<PerTargetSaveResult[]>;
}) {
  const [tab, setTab] = useState<'basic' | 'fields'>('basic');
  const initialJson = useMemo(() => JSON.stringify(entry), [entry]);
  const [draft, setDraft] = useState<AdminStyleEntry>(() => structuredClone(entry));
  const [fieldErrors, setFieldErrors] = useState<V3FieldErrors>({});
  const [liveIssues, setLiveIssues] = useState<AdminLintIssue[]>([]);
  // 1.55.0: API errors and validation banners now live INSIDE the
  // modal (see also handleSave above). Without this, errors from
  // POST/PUT /admin/styles vanished behind the modal overlay and
  // the operator had no idea why "Save" didn't seem to do anything.
  const [saveError, setSaveError] = useState<string | null>(null);
  const [validationBanner, setValidationBanner] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // per_model_tail is a JSON object; we keep a string buffer the
  // user types into and only commit the parsed value on each keystroke
  // when JSON parses cleanly. Replaces the previous defaultValue +
  // onBlur trick that silently lost edits if the user clicked
  // "Save" before blurring the textarea.
  const initialTailJson = JSON.stringify(
    asObject(entry.quality_identity).per_model_tail ?? {},
    null,
    2,
  );
  const [tailBuffer, setTailBuffer] = useState<string>(initialTailJson);
  const [tailJsonValid, setTailJsonValid] = useState<boolean>(true);
  const [bothResults, setBothResults] = useState<PerTargetSaveResult[] | null>(
    null,
  );

  const update = useCallback(<K extends string>(key: K, value: unknown) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }, []);

  const meta = asObject(draft.meta);
  const clothing = asObject(draft.clothing);
  const quality = asObject(draft.quality_identity);
  const ambient = asObject(draft.ambient);
  const deltaRange = Array.isArray(meta.delta_range) ? (meta.delta_range as number[]) : [0.1, 0.3];
  const isDirty = JSON.stringify(draft) !== initialJson;

  const triggerPool = useMemo<string[]>(
    () => (Array.isArray(draft.trigger_pool) ? (draft.trigger_pool as string[]).filter((v) => typeof v === 'string') : []),
    [draft.trigger_pool],
  );

  const sceneOverrides = useMemo<string[]>(
    () => (Array.isArray(draft.scene_overrides) ? (draft.scene_overrides as string[]).filter((v) => typeof v === 'string') : []),
    [draft.scene_overrides],
  );

  const availableChannels = useMemo<string[]>(
    () => (Array.isArray(draft.available_channels) ? (draft.available_channels as string[]).filter((v) => typeof v === 'string') : []),
    [draft.available_channels],
  );

  // Live lint via the backend, debounced. Only runs for existing
  // styles since we need an id to GET; for new styles we still
  // surface structural validation on submit.
  useEffect(() => {
    if (isNew) {
      setLiveIssues([]);
      return;
    }
    const handle = window.setTimeout(() => {
      api
        .lintOneAdminStyle(entry.id)
        .then(setLiveIssues)
        .catch(() => setLiveIssues([]));
    }, 350);
    return () => window.clearTimeout(handle);
  }, [draft, entry.id, isNew]);

  const issuesByField = useMemo(() => {
    const out: Record<string, AdminLintIssue[]> = {};
    for (const issue of liveIssues) {
      const key = issue.field || 'general';
      if (!out[key]) out[key] = [];
      out[key].push(issue);
    }
    return out;
  }, [liveIssues]);

  const triggerIssues = issuesByField['trigger_pool'] ?? [];
  const channelIssues = issuesByField['available_channels'] ?? [];
  const seasonPoolIssues = issuesByField['ambient.season'] ?? [];

  const toggleChannel = useCallback(
    (channel: string, on: boolean) => {
      setDraft((prev) => {
        const current = Array.isArray(prev.available_channels)
          ? (prev.available_channels as string[]).filter((c) => typeof c === 'string')
          : [];
        if (on && !current.includes(channel)) {
          return { ...prev, available_channels: [...current, channel] };
        }
        if (!on && current.includes(channel)) {
          return { ...prev, available_channels: current.filter((c) => c !== channel) };
        }
        return prev;
      });
    },
    [],
  );

  const updateTrigger = useCallback((idx: number, value: string) => {
    setDraft((prev) => {
      const list = Array.isArray(prev.trigger_pool)
        ? [...(prev.trigger_pool as string[])]
        : [];
      list[idx] = value;
      return { ...prev, trigger_pool: list };
    });
  }, []);

  const addTrigger = useCallback(() => {
    setDraft((prev) => {
      const list = Array.isArray(prev.trigger_pool) ? [...(prev.trigger_pool as string[])] : [];
      return { ...prev, trigger_pool: [...list, ''] };
    });
  }, []);

  const removeTrigger = useCallback((idx: number) => {
    setDraft((prev) => {
      const list = Array.isArray(prev.trigger_pool) ? [...(prev.trigger_pool as string[])] : [];
      list.splice(idx, 1);
      return { ...prev, trigger_pool: list };
    });
  }, []);

  const updateAmbientChannel = useCallback((channel: string, csv: string) => {
    setDraft((prev) => {
      const block = asObject(prev.ambient);
      return { ...prev, ambient: { ...block, [channel]: arrayFromCsv(csv) } };
    });
  }, []);

  const fillFourSeasons = useCallback(() => {
    setDraft((prev) => {
      const block = asObject(prev.ambient);
      return { ...prev, ambient: { ...block, season: [...DEFAULT_SEASONS] } };
    });
  }, []);

  const updateSceneOverrides = useCallback((csv: string) => {
    setDraft((prev) => ({ ...prev, scene_overrides: arrayFromCsv(csv) }));
  }, []);

  const updateClothingDefault = useCallback(
    (key: 'male' | 'female' | 'neutral', value: string) => {
      setDraft((prev) => {
        const block = asObject(prev.clothing);
        const prevDefault =
          typeof block.default === 'object' && block.default !== null && !Array.isArray(block.default)
            ? (block.default as Record<string, unknown>)
            : {};
        return {
          ...prev,
          clothing: {
            ...block,
            default: {
              male: asString(prevDefault.male),
              female: asString(prevDefault.female),
              neutral: asString(prevDefault.neutral),
              [key]: value,
            },
          },
        };
      });
    },
    [],
  );

  const updateClothingArray = useCallback((key: 'allowed', csv: string) => {
    setDraft((prev) => {
      const block = asObject(prev.clothing);
      return { ...prev, clothing: { ...block, [key]: arrayFromCsv(csv) } };
    });
  }, []);

  const updateClothingFlag = useCallback((key: 'gender_neutral', value: boolean) => {
    setDraft((prev) => {
      const block = asObject(prev.clothing);
      return { ...prev, clothing: { ...block, [key]: value } };
    });
  }, []);

  const updateQualityBase = useCallback((value: string) => {
    setDraft((prev) => {
      const block = asObject(prev.quality_identity);
      return { ...prev, quality_identity: { ...block, base: value } };
    });
  }, []);

  // Buffered, controlled JSON editor for per_model_tail. We commit the
  // parsed value on every keystroke that yields valid JSON, but always
  // keep the raw string buffer so the user can fix typos mid-edit.
  const updateTailBuffer = useCallback((raw: string) => {
    setTailBuffer(raw);
    try {
      const parsed = JSON.parse(raw.trim() || '{}');
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        setTailJsonValid(true);
        setDraft((prev) => {
          const block = asObject(prev.quality_identity);
          return { ...prev, quality_identity: { ...block, per_model_tail: parsed } };
        });
      } else {
        setTailJsonValid(false);
      }
    } catch {
      setTailJsonValid(false);
    }
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    setValidationBanner(null);
    const errors = validateV3Draft(draft);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      setTab('fields');
      // Build a friendly summary so the operator immediately sees WHY
      // saving was blocked instead of having to scan every fieldset.
      const labels: Record<keyof V3FieldErrors, string> = {
        trigger_pool: 'trigger_pool',
        scene_anchor: 'scene_anchor',
        clothing_default: 'clothing.default',
      };
      const parts = (Object.keys(errors) as (keyof V3FieldErrors)[])
        .map((k) => labels[k])
        .filter(Boolean);
      setValidationBanner(
        `Не сохранено: исправьте поля — ${parts.join(', ')}.`,
      );
      return;
    }
    if (!tailJsonValid) {
      setTab('fields');
      setValidationBanner('Не сохранено: per_model_tail содержит невалидный JSON.');
      return;
    }
    setSaving(true);
    try {
      await onSave(draft);
    } catch (err) {
      // Surface backend errors (422 / 409 / 500 / 403 etc.) right
      // here in the modal — previously they vanished behind the
      // overlay and the operator thought "Save" was a no-op.
      const msg = err instanceof Error ? err.message : 'Не удалось сохранить';
      setSaveError(msg);
    } finally {
      setSaving(false);
    }
  };

  const onSubmitBoth = async () => {
    setSaveError(null);
    setValidationBanner(null);
    setBothResults(null);
    const errors = validateV3Draft(draft);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      setTab('fields');
      setValidationBanner('Не сохранено: исправьте поля (см. вкладку «Поля стиля»).');
      return;
    }
    if (!tailJsonValid) {
      setTab('fields');
      setValidationBanner('Не сохранено: per_model_tail содержит невалидный JSON.');
      return;
    }
    setSaving(true);
    try {
      const results = await onSaveBoth(draft);
      setBothResults(results);
      const allOk = results.every((r) => r.status === 'ok');
      if (!allOk) {
        const failed = results.filter((r) => r.status !== 'ok').length;
        setSaveError(
          `Записано не везде: ${failed} target(ов) с проблемами — см. список ниже.`,
        );
      }
    } finally {
      setSaving(false);
    }
  };

  const rawDefault = clothing.default;
  const defaultDict =
    typeof rawDefault === 'object' && rawDefault !== null && !Array.isArray(rawDefault)
      ? (rawDefault as Record<string, unknown>)
      : {
          male: typeof rawDefault === 'string' ? rawDefault : '',
          female: typeof rawDefault === 'string' ? rawDefault : '',
          neutral: typeof rawDefault === 'string' ? rawDefault : '',
        };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-[var(--space-16)]">
      <form
        onSubmit={onSubmit}
        className="bg-[#161B22] border border-white/10 rounded-[var(--radius-12)] w-full max-w-3xl max-h-[90vh] flex flex-col"
      >
        <header className="flex items-center justify-between px-[var(--space-24)] py-[var(--space-16)] border-b border-white/10">
          <h2 className="text-[16px] leading-[24px] font-semibold">
            {isNew ? 'Новый стиль' : `Изменить ${draft.id}`}
            {isDirty && <span className="ml-[var(--space-8)] text-[12px] font-normal text-yellow-300">• не сохранено</span>}
          </h2>
          <button type="button" onClick={() => onClose(isDirty)} className="text-[#8b95a3] hover:text-white text-[24px] leading-none">
            ×
          </button>
        </header>

        <div className="flex border-b border-white/10">
          {(['basic', 'fields'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-[var(--space-20)] py-[var(--space-12)] text-[13px] leading-[18px] ${tab === t ? 'border-b-2 border-blue-400 text-white' : 'text-[#8b95a3] hover:text-white'}`}
            >
              {t === 'basic' ? 'Базовое' : 'Поля стиля'}
            </button>
          ))}
        </div>

        {validationBanner && (
          <div
            role="alert"
            className="px-[var(--space-24)] py-[var(--space-12)] border-b border-red-500/30 bg-red-500/15 text-[13px] leading-[18px] text-red-200 font-medium"
          >
            {validationBanner}
          </div>
        )}

        {saveError && (
          <div
            role="alert"
            className="px-[var(--space-24)] py-[var(--space-12)] border-b border-red-500/30 bg-red-500/15 text-[13px] leading-[18px] text-red-200"
          >
            <div className="font-semibold mb-[2px]">Ошибка сохранения</div>
            <div className="opacity-90 break-words">{saveError}</div>
          </div>
        )}

        {bothResults && (
          <div className="px-[var(--space-24)] py-[var(--space-12)] border-b border-white/10 bg-white/[0.02] text-[12px] leading-[16px]">
            <div className="font-medium uppercase tracking-wide text-[#8b95a3] mb-[var(--space-6)]">
              Результат «Применить на оба»
            </div>
            <ul className="space-y-[var(--space-4)]">
              {bothResults.map((r) => {
                const tone =
                  r.status === 'ok'
                    ? 'text-emerald-300'
                    : r.status === 'skipped'
                      ? 'text-amber-300'
                      : 'text-red-300';
                const icon =
                  r.status === 'ok' ? '✓' : r.status === 'skipped' ? '◇' : '✗';
                const targetMeta = ADMIN_TARGETS.find(
                  (t) => t.id === r.target,
                );
                return (
                  <li key={r.target} className={`flex items-start gap-[var(--space-8)] ${tone}`}>
                    <span className="font-semibold w-[14px]">{icon}</span>
                    <span className="font-medium w-[80px] shrink-0">
                      {targetMeta?.shortLabel ?? r.target}
                    </span>
                    <span className="opacity-90 break-words">{r.message}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {liveIssues.length > 0 && (
          <div className="px-[var(--space-24)] py-[var(--space-12)] border-b border-white/10 bg-amber-500/5 text-[12px] leading-[16px] text-amber-200 space-y-[var(--space-4)]">
            <div className="font-medium uppercase tracking-wide text-amber-300">
              Линт ({liveIssues.length})
            </div>
            <ul className="space-y-[2px] max-h-32 overflow-y-auto">
              {liveIssues.map((issue, i) => (
                <li key={i} className="flex gap-[var(--space-8)]">
                  <span className={`shrink-0 px-[var(--space-6)] py-[1px] rounded text-[10px] ${issue.severity === 'error' ? 'bg-red-500/20 text-red-200' : 'bg-amber-500/20 text-amber-200'}`}>
                    {issue.code}
                  </span>
                  <span className="text-amber-100/80">{issue.message}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-[var(--space-24)] space-y-[var(--space-16)]">
          {tab === 'basic' && (
            <>
              <Field label="ID" hint={isNew ? 'Только латиница, цифры, _' : 'ID нельзя менять'}>
                <input
                  required
                  disabled={!isNew}
                  pattern="[a-z0-9_]+"
                  value={asString(draft.id)}
                  onChange={(e) => update('id', e.target.value)}
                  className="input"
                />
              </Field>

              <Field label="Режим (mode)">
                <select
                  value={asString(draft.mode, 'social')}
                  onChange={(e) => update('mode', e.target.value)}
                  className="input"
                >
                  <option value="cv">cv (резюме)</option>
                  <option value="social">social (соц.сети)</option>
                  <option value="dating">dating (знакомства)</option>
                </select>
              </Field>

              <Field label="Display label" hint="Формат: emoji + название (напр. «🎨 Креативный директор»)">
                <input
                  value={asString(draft.display_label)}
                  onChange={(e) => update('display_label', e.target.value)}
                  className="input"
                />
              </Field>

              <Field label="Hook text">
                <textarea
                  rows={2}
                  value={asString(draft.hook_text)}
                  onChange={(e) => update('hook_text', e.target.value)}
                  className="input"
                />
              </Field>

              <div className="grid grid-cols-2 gap-[var(--space-12)]">
                <Field label="Сценарий">
                  <select
                    value={asString(draft.scenario, '')}
                    onChange={(e) => update('scenario', e.target.value || null)}
                    className="input"
                  >
                    {SCENARIO_OPTIONS.map((opt) => (
                      <option key={opt} value={opt}>{opt || '— основной каталог —'}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Разблокировка после N генераций" hint="0 = доступен сразу">
                  <input
                    type="number"
                    min={0}
                    value={asNumber(draft.unlock_after_generations, 0)}
                    onChange={(e) => update('unlock_after_generations', Number(e.target.value))}
                    className="input"
                  />
                </Field>
              </div>

              <div className="grid grid-cols-3 gap-[var(--space-12)]">
                <Field label="meta.param">
                  <select
                    value={asString(meta.param, 'appeal')}
                    onChange={(e) => update('meta', { ...meta, param: e.target.value })}
                    className="input"
                  >
                    {['appeal', 'warmth', 'presence', 'trust', 'competence', 'hireability'].map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </Field>
                <Field label="meta.delta_range[0]">
                  <input
                    type="number"
                    step={0.01}
                    value={deltaRange[0] ?? 0}
                    onChange={(e) => update('meta', { ...meta, delta_range: [Number(e.target.value), deltaRange[1] ?? 0] })}
                    className="input"
                  />
                </Field>
                <Field label="meta.delta_range[1]">
                  <input
                    type="number"
                    step={0.01}
                    value={deltaRange[1] ?? 0}
                    onChange={(e) => update('meta', { ...meta, delta_range: [deltaRange[0] ?? 0, Number(e.target.value)] })}
                    className="input"
                  />
                </Field>
              </div>

              <div className="grid grid-cols-2 gap-[var(--space-12)]">
                <Field
                  label="location_type"
                  hint="indoor скрывает season + weather, document — все ambient-каналы"
                >
                  <select
                    value={asString(draft.location_type, '')}
                    onChange={(e) => update('location_type', e.target.value)}
                    className="input"
                  >
                    {LOCATION_TYPES.map((t) => (
                      <option key={t || 'unset'} value={t}>
                        {t || '— не задан —'}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="background_lock">
                  <select
                    value={asString(draft.background_lock, 'semi')}
                    onChange={(e) => update('background_lock', e.target.value)}
                    className="input"
                  >
                    <option value="flexible">flexible</option>
                    <option value="semi">semi</option>
                    <option value="locked">locked</option>
                  </select>
                </Field>
              </div>
            </>
          )}

          {tab === 'fields' && (
            <>
              <Fieldset legend="trigger_pool" error={fieldErrors.trigger_pool}>
                <p className="text-[12px] leading-[16px] text-[#8b95a3]">
                  Иммутабельный мотив стиля. Сэмплер выбирает одну формулировку
                  каждую генерацию. Не должен содержать ракурс/освещение/погоду —
                  это отдельные каналы.
                </p>
                {triggerPool.length === 0 && (
                  <div className="px-[var(--space-12)] py-[var(--space-6)] bg-red-500/10 border border-red-500/30 rounded text-[11px] text-red-300">
                    Нужна минимум одна формулировка trigger_pool.
                  </div>
                )}
                {triggerPool.map((t, i) => (
                  <div key={i} className="flex gap-[var(--space-8)] items-start">
                    <input
                      value={t}
                      onChange={(e) => updateTrigger(i, e.target.value)}
                      className="input flex-1"
                      placeholder='напр. "round wall mirror in frame"'
                    />
                    <button
                      type="button"
                      onClick={() => removeTrigger(i)}
                      className="px-[var(--space-12)] py-[var(--space-6)] text-[12px] rounded border border-white/10 hover:bg-red-500/10 hover:border-red-500/30 hover:text-red-300"
                    >
                      −
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={addTrigger}
                  className="px-[var(--space-12)] py-[var(--space-6)] text-[12px] rounded border border-white/10 hover:bg-white/5 self-start"
                >
                  + добавить формулировку
                </button>
                {triggerIssues.map((issue, i) => (
                  <div
                    key={i}
                    className="text-[11px] text-amber-300 px-[var(--space-8)] py-[var(--space-4)] bg-amber-500/10 border border-amber-500/30 rounded"
                  >
                    {issue.message}
                  </div>
                ))}
              </Fieldset>

              <Field label="scene_anchor" hint="Базовая сцена БЕЗ описаний света / погоды / времени суток" error={fieldErrors.scene_anchor}>
                <textarea
                  rows={2}
                  value={asString(draft.scene_anchor)}
                  onChange={(e) => update('scene_anchor', e.target.value)}
                  className="input"
                />
              </Field>

              <Field label="scene_overrides (csv)" hint="Альтернативные сцены, сэмплер ротирует">
                <input
                  value={sceneOverrides.join(', ')}
                  onChange={(e) => updateSceneOverrides(e.target.value)}
                  className="input"
                />
              </Field>

              <Fieldset legend="available_channels">
                <p className="text-[12px] leading-[16px] text-[#8b95a3]">
                  Чекбоксы определяют, какие настройки видит пользователь в StyleSettingsModal.
                  Пустой список = «не курировано», UI показывает каналы по непустым пулам.
                </p>
                <div className="grid grid-cols-2 gap-[var(--space-4)]">
                  {ALL_CHANNELS.map((ch) => (
                    <label
                      key={ch}
                      className="flex items-center gap-[var(--space-8)] text-[13px] leading-[18px] px-[var(--space-8)] py-[var(--space-4)] rounded hover:bg-white/5"
                    >
                      <input
                        type="checkbox"
                        checked={availableChannels.includes(ch)}
                        onChange={(e) => toggleChannel(ch, e.target.checked)}
                      />
                      <span>{ch}</span>
                    </label>
                  ))}
                </div>
                {channelIssues.map((issue, i) => (
                  <div
                    key={i}
                    className="text-[11px] text-red-300 px-[var(--space-8)] py-[var(--space-4)] bg-red-500/10 border border-red-500/30 rounded"
                  >
                    {issue.message}
                  </div>
                ))}
              </Fieldset>

              <Fieldset legend="ambient pools">
                {(['lighting', 'weather', 'time_of_day', 'season'] as const).map((ch) => {
                  const enabled = availableChannels.length === 0 || availableChannels.includes(ch);
                  const csv = csvFromArray(ambient[ch]);
                  return (
                    <Field
                      key={ch}
                      label={`ambient.${ch} (csv)`}
                      hint={enabled ? '' : 'канал отключён в available_channels — пул не используется'}
                    >
                      <input
                        value={csv}
                        onChange={(e) => updateAmbientChannel(ch, e.target.value)}
                        className={`input ${enabled ? '' : 'opacity-50'}`}
                      />
                    </Field>
                  );
                })}
                {availableChannels.includes('season') && (
                  <button
                    type="button"
                    onClick={fillFourSeasons}
                    className="px-[var(--space-12)] py-[var(--space-6)] text-[12px] rounded border border-white/10 hover:bg-white/5 self-start"
                  >
                    Заполнить 4 сезона
                  </button>
                )}
                {seasonPoolIssues.map((issue, i) => (
                  <div
                    key={i}
                    className="text-[11px] text-amber-300 px-[var(--space-8)] py-[var(--space-4)] bg-amber-500/10 border border-amber-500/30 rounded"
                  >
                    {issue.message}
                  </div>
                ))}
              </Fieldset>

              <Fieldset legend="clothing" error={fieldErrors.clothing_default}>
                <Field label="default.male">
                  <input
                    value={asString(defaultDict.male)}
                    onChange={(e) => updateClothingDefault('male', e.target.value)}
                    className="input"
                    placeholder="мужской вариант, можно оставить пустым"
                  />
                </Field>
                <Field label="default.female">
                  <input
                    value={asString(defaultDict.female)}
                    onChange={(e) => updateClothingDefault('female', e.target.value)}
                    className="input"
                    placeholder="женский вариант, можно оставить пустым"
                  />
                </Field>
                <Field label="default.neutral">
                  <input
                    value={asString(defaultDict.neutral)}
                    onChange={(e) => updateClothingDefault('neutral', e.target.value)}
                    className="input"
                    placeholder="нейтральный fallback (если male/female пустые)"
                  />
                </Field>
                <Field label="allowed (csv)">
                  <input
                    value={csvFromArray(clothing.allowed)}
                    onChange={(e) => updateClothingArray('allowed', e.target.value)}
                    className="input"
                  />
                </Field>
                <label className="flex items-center gap-[var(--space-8)] text-[13px] leading-[18px]">
                  <input
                    type="checkbox"
                    checked={asBool(clothing.gender_neutral, true)}
                    onChange={(e) => updateClothingFlag('gender_neutral', e.target.checked)}
                  />
                  gender_neutral
                </label>
              </Fieldset>

              <Fieldset legend="quality_identity">
                <Field label="base" hint="Если пусто, используется дефолтный хвост качества для модели">
                  <textarea
                    rows={2}
                    value={asString(quality.base)}
                    onChange={(e) => updateQualityBase(e.target.value)}
                    className="input"
                  />
                </Field>
                <Field
                  label="per_model_tail (JSON)"
                  hint={tailJsonValid ? 'object вида {"model_name": "tail string"}' : undefined}
                  error={tailJsonValid ? undefined : 'Невалидный JSON object'}
                >
                  <textarea
                    rows={3}
                    value={tailBuffer}
                    onChange={(e) => updateTailBuffer(e.target.value)}
                    className={`input font-mono text-[12px] ${tailJsonValid ? '' : 'border-red-500/50'}`}
                    spellCheck={false}
                  />
                </Field>
              </Fieldset>

              <Field label="expression">
                <input
                  value={asString(draft.expression)}
                  onChange={(e) => update('expression', e.target.value)}
                  className="input"
                />
              </Field>
            </>
          )}
        </div>

        <footer className="flex flex-wrap justify-end gap-[var(--space-8)] px-[var(--space-24)] py-[var(--space-16)] border-t border-white/10">
          <button
            type="button"
            onClick={() => onClose(isDirty)}
            disabled={saving}
            className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 hover:bg-white/5 text-[13px] leading-[18px] disabled:opacity-50"
          >
            Отмена
          </button>
          <button
            type="submit"
            disabled={saving}
            className={`px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] font-medium text-[13px] leading-[18px] ${
              saving
                ? 'bg-white/10 text-[#8b95a3] cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-500 text-white'
            }`}
          >
            {saving ? 'Сохраняем…' : 'Сохранить'}
          </button>
          <button
            type="button"
            onClick={() => void onSubmitBoth()}
            disabled={saving}
            title="Записать стиль одновременно на primary и RU"
            className={`px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] font-medium text-[13px] leading-[18px] ${
              saving
                ? 'bg-white/10 text-[#8b95a3] cursor-not-allowed'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white'
            }`}
          >
            {saving ? 'Сохраняем…' : 'Применить на оба'}
          </button>
        </footer>

        <style>{`
          .input {
            width: 100%;
            padding: 8px 12px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 8px;
            color: #E6EEF8;
            font-size: 13px;
            line-height: 18px;
          }
          .input:focus { outline: none; border-color: #60a5fa; }
          .input:disabled { opacity: 0.6; cursor: not-allowed; }
        `}</style>
      </form>
    </div>
  );
}

function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between mb-[var(--space-6)] gap-[var(--space-8)]">
        <span className="text-[11px] text-[#8b95a3] uppercase tracking-wide">{label}</span>
        {hint && !error && <span className="text-[10px] text-[#5a6470]">{hint}</span>}
        {error && <span className="text-[10px] text-red-300">{error}</span>}
      </div>
      {children}
    </label>
  );
}

function Fieldset({
  legend,
  error,
  children,
}: {
  legend: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="border border-white/10 rounded-[var(--radius-12)] p-[var(--space-16)] space-y-[var(--space-12)]">
      <legend className="px-[var(--space-8)] text-[11px] uppercase tracking-wide text-[#8b95a3]">
        {legend}
        {error && <span className="ml-[var(--space-8)] text-red-300 normal-case tracking-normal">{error}</span>}
      </legend>
      {children}
    </fieldset>
  );
}
