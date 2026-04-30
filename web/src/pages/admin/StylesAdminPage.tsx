import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../../lib/api';
import type {
  AdminLintIssue,
  AdminLintReport,
  AdminStyleEntry,
  AdminStyleSummary,
} from '../../lib/api';
import { ApiError } from '../../lib/api';

type ModeFilter = 'all' | 'cv' | 'social' | 'dating' | string;

const MODES: ModeFilter[] = ['all', 'cv', 'social', 'dating'];
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

const EMPTY_V2_TEMPLATE: AdminStyleEntry = {
  id: '',
  mode: 'social',
  display_label: '',
  hook_text: '',
  scenario: null,
  unlock_after_generations: 0,
  is_scenario_only: false,
  schema_version: 2,
  meta: { param: 'appeal', delta_range: [0.1, 0.3] },
  background: { base: '', lock: 'flexible', overrides_allowed: [] },
  clothing: {
    default: { male: '', female: '', neutral: '' },
    allowed: [],
    gender_neutral: true,
  },
  weather: { enabled: false, allowed: [], default_na: true },
  context_slots: { lighting: [], framing: ['portrait', 'half_body', 'full_body'] },
  quality_identity: { base: '', per_model_tail: {} },
  expression: '',
  trigger: '',
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
      // Lint report is best-effort; the catalog table renders even if
      // the lint endpoint is unreachable (older deploy, etc.).
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
    setEditing({ entry: { ...EMPTY_V2_TEMPLATE }, isNew: true });
  }, []);

  const closeEdit = useCallback((dirty: boolean) => {
    if (dirty && !window.confirm('Изменения не сохранены. Закрыть редактор?')) {
      return;
    }
    setEditing(null);
  }, []);

  const handleSave = useCallback(
    async (entry: AdminStyleEntry, isNew: boolean) => {
      try {
        if (isNew) {
          await api.createAdminStyle(entry);
        } else {
          await api.updateAdminStyle(entry.id, entry);
        }
        setEditing(null);
        await fetchList();
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Не удалось сохранить';
        setError(msg);
      }
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
      setError(`Cache reloaded — ${res.count} styles`);
      await fetchList();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось обновить кэш');
    }
  }, [fetchList]);

  return (
    <div className="min-h-screen bg-[#0E1216] text-[#E6EEF8] p-6">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Style Catalog Admin</h1>
          <p className="text-sm text-[#8b95a3] mt-1">
            Source of truth: <code>data/styles.json</code>. Saves are atomic and refresh in-memory caches.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            to="/admin/conflicts"
            className="px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5 text-sm"
          >
            Conflicts report
          </Link>
          <button onClick={handleReload} className="px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5">
            Reload cache
          </button>
          <button onClick={openCreate} className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 font-medium">
            + New style
          </button>
        </div>
      </header>

      {totalIssues.dirtyStyles > 0 && (
        <div className="mb-4 px-4 py-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-sm text-amber-200 flex items-center gap-3">
          <span>
            Lint: <strong>{totalIssues.errors}</strong> errors,{' '}
            <strong>{totalIssues.warnings}</strong> warnings across{' '}
            <strong>{totalIssues.dirtyStyles}</strong> styles.
          </span>
          <button
            onClick={() => setIssuesOnly(!issuesOnly)}
            className={`ml-auto px-3 py-1 rounded border text-xs ${issuesOnly ? 'bg-amber-500/20 border-amber-500/50' : 'border-amber-500/30 hover:bg-amber-500/10'}`}
          >
            {issuesOnly ? 'Show all' : 'Show only with issues'}
          </button>
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="flex gap-3 mb-4">
        <div className="flex gap-1 rounded-lg border border-white/10 overflow-hidden">
          {MODES.map((m) => (
            <button
              key={m}
              onClick={() => setModeFilter(m)}
              className={`px-3 py-1.5 text-sm ${modeFilter === m ? 'bg-blue-600 text-white' : 'text-[#8b95a3] hover:bg-white/5'}`}
            >
              {m}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by id, label, hook…"
          className="flex-1 px-3 py-1.5 rounded-lg border border-white/10 bg-transparent text-sm focus:outline-none focus:border-blue-400"
        />
        <span className="text-sm text-[#8b95a3] self-center whitespace-nowrap">
          {loading ? 'Loading…' : `${filtered.length} / ${items?.length ?? 0}`}
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-[#8b95a3]">
            <tr>
              <th className="text-left px-3 py-2 font-medium">id</th>
              <th className="text-left px-3 py-2 font-medium">mode</th>
              <th className="text-left px-3 py-2 font-medium">label</th>
              <th className="text-left px-3 py-2 font-medium">lint</th>
              <th className="text-left px-3 py-2 font-medium">unlock</th>
              <th className="text-left px-3 py-2 font-medium">scenario</th>
              <th className="text-left px-3 py-2 font-medium">v</th>
              <th className="text-right px-3 py-2 font-medium">actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => {
              const counts = severityCounts(lintReport[s.id]);
              return (
                <tr key={s.id} className="border-t border-white/5 hover:bg-white/5">
                  <td className="px-3 py-2 font-mono text-xs">{s.id}</td>
                  <td className="px-3 py-2">{s.mode}</td>
                  <td className="px-3 py-2 truncate max-w-[280px]">{s.display_label}</td>
                  <td className="px-3 py-2">
                    {counts.errors === 0 && counts.warnings === 0 ? (
                      <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/15 border border-emerald-500/30 text-emerald-300">clean</span>
                    ) : (
                      <span className="flex gap-1">
                        {counts.errors > 0 && (
                          <span className="px-2 py-0.5 rounded text-[10px] bg-red-500/15 border border-red-500/30 text-red-300">
                            {counts.errors}E
                          </span>
                        )}
                        {counts.warnings > 0 && (
                          <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/15 border border-amber-500/30 text-amber-300">
                            {counts.warnings}W
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">{s.unlock_after_generations || '—'}</td>
                  <td className="px-3 py-2">{s.scenario ?? '—'}</td>
                  <td className="px-3 py-2">{s.schema_version}</td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => openEdit(s.id)} className="px-2 py-1 text-xs rounded border border-white/10 hover:bg-white/10 mr-2">
                      Edit
                    </button>
                    <button onClick={() => handleDelete(s.id)} className="px-2 py-1 text-xs rounded border border-red-500/30 text-red-300 hover:bg-red-500/10">
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-[#8b95a3]">
                  Ничего не найдено
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
        />
      )}
    </div>
  );
}

type V2FieldErrors = Partial<{
  background_base: string;
  clothing_default: string;
  quality_base: string;
}>;

function validateV2Draft(draft: AdminStyleEntry): V2FieldErrors {
  const errors: V2FieldErrors = {};
  if (asNumber(draft.schema_version, 1) !== 2) return errors;
  const background = asObject(draft.background);
  const clothing = asObject(draft.clothing);
  const quality = asObject(draft.quality_identity);
  if (!asString(background.base).trim()) {
    errors.background_base = 'background.base обязателен для v2';
  }
  const clothingDefault = clothing.default;
  if (typeof clothingDefault === 'string') {
    if (!clothingDefault.trim()) {
      errors.clothing_default = 'clothing.default обязателен для v2';
    }
  } else if (clothingDefault && typeof clothingDefault === 'object') {
    const dict = clothingDefault as Record<string, unknown>;
    const hasAny = ['male', 'female', 'neutral'].some(
      (k) => typeof dict[k] === 'string' && (dict[k] as string).trim() !== '',
    );
    if (!hasAny) {
      errors.clothing_default = 'clothing.default: заполните хотя бы одно поле (male / female / neutral)';
    }
  } else {
    errors.clothing_default = 'clothing.default обязателен для v2';
  }
  if (!asString(quality.base).trim()) {
    errors.quality_base = 'quality_identity.base обязателен для v2';
  }
  return errors;
}

function StyleEditModal({
  entry,
  isNew,
  onClose,
  onSave,
}: {
  entry: AdminStyleEntry;
  isNew: boolean;
  onClose: (dirty: boolean) => void;
  onSave: (entry: AdminStyleEntry) => void;
}) {
  const [tab, setTab] = useState<'basic' | 'slots' | 'v3'>('basic');
  const initialJson = useMemo(() => JSON.stringify(entry), [entry]);
  const [draft, setDraft] = useState<AdminStyleEntry>(() => structuredClone(entry));
  const [fieldErrors, setFieldErrors] = useState<V2FieldErrors>({});
  const [liveIssues, setLiveIssues] = useState<AdminLintIssue[]>([]);

  const update = useCallback(<K extends string>(key: K, value: unknown) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }, []);

  const updateNested = useCallback(
    (parent: string, child: string, value: unknown) => {
      setDraft((prev) => {
        const block = asObject(prev[parent]);
        return { ...prev, [parent]: { ...block, [child]: value } };
      });
    },
    [],
  );

  const meta = asObject(draft.meta);
  const background = asObject(draft.background);
  const clothing = asObject(draft.clothing);
  const weather = asObject(draft.weather);
  const contextSlots = asObject(draft.context_slots);
  const quality = asObject(draft.quality_identity);
  const ambient = asObject(draft.ambient);
  const isV2 = asNumber(draft.schema_version, 1) === 2;
  const isV3 = asNumber(draft.schema_version, 1) === 3;
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

  // Live lint via the backend — debounced. Only runs for existing
  // styles (we need an id to GET); for new styles we still surface
  // structural validation via the inline trigger-pool check.
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

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const errors = validateV2Draft(draft);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      // Surface the slot-tab so users see the offending field immediately.
      setTab('slots');
      return;
    }
    onSave(draft);
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <form
        onSubmit={onSubmit}
        className="bg-[#161B22] border border-white/10 rounded-xl w-full max-w-3xl max-h-[90vh] flex flex-col"
      >
        <header className="flex items-center justify-between px-5 py-3 border-b border-white/10">
          <h2 className="text-lg font-semibold">
            {isNew ? 'New style' : `Edit ${draft.id}`}
            {isDirty && <span className="ml-2 text-xs font-normal text-yellow-300">• unsaved</span>}
          </h2>
          <button type="button" onClick={() => onClose(isDirty)} className="text-[#8b95a3] hover:text-white text-2xl leading-none">
            ×
          </button>
        </header>

        <div className="flex border-b border-white/10">
          {(['basic', 'slots', 'v3'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm ${tab === t ? 'border-b-2 border-blue-400 text-white' : 'text-[#8b95a3]'}`}
            >
              {t === 'basic'
                ? 'Базовое'
                : t === 'slots'
                  ? 'Слоты v2'
                  : 'v3 / channels'}
            </button>
          ))}
        </div>

        {liveIssues.length > 0 && (
          <div className="px-5 py-3 border-b border-white/10 bg-amber-500/5 text-xs text-amber-200 space-y-1">
            <div className="font-medium uppercase tracking-wide text-amber-300">
              Lint ({liveIssues.length})
            </div>
            <ul className="space-y-0.5 max-h-32 overflow-y-auto">
              {liveIssues.map((issue, i) => (
                <li key={i} className="flex gap-2">
                  <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] ${issue.severity === 'error' ? 'bg-red-500/20 text-red-200' : 'bg-amber-500/20 text-amber-200'}`}>
                    {issue.code}
                  </span>
                  <span className="text-amber-100/80">{issue.message}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
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

              <div className="grid grid-cols-2 gap-3">
                <Field label="Mode">
                  <select
                    value={asString(draft.mode, 'social')}
                    onChange={(e) => update('mode', e.target.value)}
                    className="input"
                  >
                    <option value="cv">cv</option>
                    <option value="social">social</option>
                    <option value="dating">dating</option>
                  </select>
                </Field>
                <Field label="Schema version">
                  <select
                    value={asNumber(draft.schema_version, 1)}
                    onChange={(e) => update('schema_version', Number(e.target.value))}
                    className="input"
                  >
                    <option value={1}>v1</option>
                    <option value={2}>v2</option>
                  </select>
                </Field>
              </div>

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

              <div className="grid grid-cols-2 gap-3">
                <Field label="Scenario">
                  <select
                    value={asString(draft.scenario, '')}
                    onChange={(e) => update('scenario', e.target.value || null)}
                    className="input"
                  >
                    {SCENARIO_OPTIONS.map((opt) => (
                      <option key={opt} value={opt}>{opt || '— main catalog —'}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Unlock after generations" hint="0 = доступен сразу">
                  <input
                    type="number"
                    min={0}
                    value={asNumber(draft.unlock_after_generations, 0)}
                    onChange={(e) => update('unlock_after_generations', Number(e.target.value))}
                    className="input"
                  />
                </Field>
              </div>

              <div className="grid grid-cols-3 gap-3">
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
            </>
          )}

          {tab === 'slots' && (
            <>
              {!isV2 && (
                <div className="px-3 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded text-sm text-yellow-300">
                  Стиль v1 — поля ниже сохранятся, но движок их не использует, пока schema_version не = 2.
                </div>
              )}

              <Field label="trigger">
                <input
                  value={asString(draft.trigger)}
                  onChange={(e) => update('trigger', e.target.value)}
                  className="input"
                />
              </Field>

              <Fieldset legend="background">
                <Field label="base" error={fieldErrors.background_base}>
                  <textarea
                    rows={2}
                    value={asString(background.base)}
                    onChange={(e) => updateNested('background', 'base', e.target.value)}
                    className="input"
                  />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="lock">
                    <select
                      value={asString(background.lock, 'flexible')}
                      onChange={(e) => updateNested('background', 'lock', e.target.value)}
                      className="input"
                    >
                      <option value="flexible">flexible</option>
                      <option value="semi">semi</option>
                      <option value="locked">locked</option>
                    </select>
                  </Field>
                  <Field label="overrides_allowed (csv)">
                    <input
                      value={csvFromArray(background.overrides_allowed)}
                      onChange={(e) => updateNested('background', 'overrides_allowed', arrayFromCsv(e.target.value))}
                      className="input"
                    />
                  </Field>
                </div>
              </Fieldset>

              <Fieldset legend="clothing">
                {(() => {
                  const rawDefault = clothing.default;
                  const defaultDict =
                    typeof rawDefault === 'object' && rawDefault !== null && !Array.isArray(rawDefault)
                      ? (rawDefault as Record<string, unknown>)
                      : {
                          male: typeof rawDefault === 'string' ? rawDefault : '',
                          female: typeof rawDefault === 'string' ? rawDefault : '',
                          neutral: typeof rawDefault === 'string' ? rawDefault : '',
                        };
                  const updateDefaultKey = (key: 'male' | 'female' | 'neutral', value: string) => {
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
                  };
                  return (
                    <>
                      <Field label="default.male" error={fieldErrors.clothing_default}>
                        <input
                          value={asString(defaultDict.male)}
                          onChange={(e) => updateDefaultKey('male', e.target.value)}
                          className="input"
                          placeholder="мужской вариант, можно оставить пустым"
                        />
                      </Field>
                      <Field label="default.female">
                        <input
                          value={asString(defaultDict.female)}
                          onChange={(e) => updateDefaultKey('female', e.target.value)}
                          className="input"
                          placeholder="женский вариант, можно оставить пустым"
                        />
                      </Field>
                      <Field label="default.neutral">
                        <input
                          value={asString(defaultDict.neutral)}
                          onChange={(e) => updateDefaultKey('neutral', e.target.value)}
                          className="input"
                          placeholder="нейтральный fallback (используется, если male/female пустой)"
                        />
                      </Field>
                    </>
                  );
                })()}
                <Field label="allowed (csv)">
                  <input
                    value={csvFromArray(clothing.allowed)}
                    onChange={(e) => updateNested('clothing', 'allowed', arrayFromCsv(e.target.value))}
                    className="input"
                  />
                </Field>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={asBool(clothing.gender_neutral, true)}
                    onChange={(e) => updateNested('clothing', 'gender_neutral', e.target.checked)}
                  />
                  gender_neutral
                </label>
              </Fieldset>

              <Fieldset legend="weather">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={asBool(weather.enabled)}
                    onChange={(e) => updateNested('weather', 'enabled', e.target.checked)}
                  />
                  enabled
                </label>
                <Field label="allowed (csv)">
                  <input
                    value={csvFromArray(weather.allowed)}
                    onChange={(e) => updateNested('weather', 'allowed', arrayFromCsv(e.target.value))}
                    className="input"
                  />
                </Field>
              </Fieldset>

              <Fieldset legend="context_slots">
                {(['lighting', 'framing', 'time_of_day', 'season'] as const).map((slot) => (
                  <Field key={slot} label={`${slot} (csv)`}>
                    <input
                      value={csvFromArray(contextSlots[slot])}
                      onChange={(e) => updateNested('context_slots', slot, arrayFromCsv(e.target.value))}
                      className="input"
                    />
                  </Field>
                ))}
              </Fieldset>

              <Fieldset legend="quality_identity">
                <Field label="base" error={fieldErrors.quality_base}>
                  <textarea
                    rows={2}
                    value={asString(quality.base)}
                    onChange={(e) => updateNested('quality_identity', 'base', e.target.value)}
                    className="input"
                  />
                </Field>
                <Field label="per_model_tail (JSON)">
                  <textarea
                    rows={2}
                    defaultValue={JSON.stringify(quality.per_model_tail ?? {}, null, 2)}
                    onBlur={(e) => {
                      try {
                        const parsed = JSON.parse(e.target.value || '{}');
                        updateNested('quality_identity', 'per_model_tail', parsed);
                      } catch {
                        // keep last good value if JSON malformed; user can retry
                      }
                    }}
                    className="input font-mono text-xs"
                  />
                </Field>
              </Fieldset>
            </>
          )}

          {tab === 'v3' && (
            <>
              {!isV3 && (
                <div className="px-3 py-2 bg-blue-500/10 border border-blue-500/30 rounded text-sm text-blue-200">
                  Стиль не v3 — поля ниже сохранятся, но сэмплер их использует только когда{' '}
                  <code>schema_version = 3</code>.
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <Field
                  label="location_type"
                  hint="indoor скрывает season + weather, document скрывает все ambient-каналы"
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

              <Fieldset legend="trigger_pool">
                <p className="text-xs text-[#8b95a3]">
                  Иммутабельный мотив стиля. Сэмплер выбирает одну формулировку каждую генерацию.
                  Не должен содержать ракурс/освещение/погоду — это отдельные каналы.
                </p>
                {triggerPool.length === 0 && (
                  <div className="px-3 py-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-300">
                    v3 styles must contain at least one trigger formulation.
                  </div>
                )}
                {triggerPool.map((t, i) => (
                  <div key={i} className="flex gap-2 items-start">
                    <input
                      value={t}
                      onChange={(e) => updateTrigger(i, e.target.value)}
                      className="input flex-1"
                      placeholder='e.g. "round wall mirror in frame"'
                    />
                    <button
                      type="button"
                      onClick={() => removeTrigger(i)}
                      className="px-2 py-1.5 text-xs rounded border border-white/10 hover:bg-red-500/10 hover:border-red-500/30 hover:text-red-300"
                    >
                      −
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={addTrigger}
                  className="px-3 py-1.5 text-xs rounded border border-white/10 hover:bg-white/5"
                >
                  + add formulation
                </button>
                {triggerIssues.map((issue, i) => (
                  <div
                    key={i}
                    className="text-[11px] text-amber-300 px-2 py-1 bg-amber-500/10 border border-amber-500/30 rounded"
                  >
                    {issue.message}
                  </div>
                ))}
              </Fieldset>

              <Field label="scene_anchor" hint="Базовая сцена БЕЗ описаний света / погоды / времени суток">
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
                <p className="text-xs text-[#8b95a3]">
                  Чекбоксы определяют, какие настройки видит пользователь в StyleSettingsModal.
                  Пустой список = «не курировано», UI показывает каналы по непустым пулам (старое поведение).
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {ALL_CHANNELS.map((ch) => (
                    <label
                      key={ch}
                      className="flex items-center gap-2 text-sm px-2 py-1 rounded hover:bg-white/5"
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
                    className="text-[11px] text-red-300 px-2 py-1 bg-red-500/10 border border-red-500/30 rounded"
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
                    className="px-3 py-1.5 text-xs rounded border border-white/10 hover:bg-white/5 self-start"
                  >
                    Fill 4 seasons (spring, summer, autumn, winter)
                  </button>
                )}
                {seasonPoolIssues.map((issue, i) => (
                  <div
                    key={i}
                    className="text-[11px] text-amber-300 px-2 py-1 bg-amber-500/10 border border-amber-500/30 rounded"
                  >
                    {issue.message}
                  </div>
                ))}
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

        <footer className="flex justify-end gap-2 px-5 py-3 border-t border-white/10">
          <button type="button" onClick={() => onClose(isDirty)} className="px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5">
            Cancel
          </button>
          <button type="submit" className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 font-medium">
            Save
          </button>
        </footer>

        <style>{`
          .input {
            width: 100%;
            padding: 6px 10px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 6px;
            color: #E6EEF8;
            font-size: 13px;
          }
          .input:focus { outline: none; border-color: #60a5fa; }
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
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-xs text-[#8b95a3] uppercase tracking-wide">{label}</span>
        {hint && !error && <span className="text-[10px] text-[#5a6470]">{hint}</span>}
        {error && <span className="text-[10px] text-red-300">{error}</span>}
      </div>
      {children}
    </label>
  );
}

function Fieldset({ legend, children }: { legend: string; children: React.ReactNode }) {
  return (
    <fieldset className="border border-white/10 rounded-lg p-3 space-y-3">
      <legend className="px-2 text-xs uppercase tracking-wide text-[#8b95a3]">{legend}</legend>
      {children}
    </fieldset>
  );
}
