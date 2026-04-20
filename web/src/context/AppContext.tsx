import { createContext, useContext, useEffect, useState, useCallback, useRef, useMemo, type ReactNode } from 'react';
import { restoreToken, startOAuth, logout as authLogout } from '../lib/auth';
import * as api from '../lib/api';
import type { CategoryId, StyleItem } from '../data/styles';
import { STYLES_BY_CATEGORY } from '../data/styles';
import { restorePhotoAfterOAuth, clearPersistedPhoto } from '../lib/photo-persist';
import { rememberOAuthReturnPath } from '../lib/flow-resume';
import { normalizeImageUrl } from '../lib/image-url';
import {
  clearPendingTask,
  peekPendingTask,
  rememberPendingTask,
  rememberLastGenerationError,
  clearLastGenerationError,
  peekLastGenerationError,
  hasPendingTask,
} from '../lib/pending-task';
import {
  getScenario,
  resolveScenarioStyles,
  type ScenarioEntryMode,
  type ScenarioStep3Mode,
  type ScenarioType,
} from '../scenarios/config';

interface Session { token: string; userId: string; provider: string; usage: api.ChannelAuthResponse['usage'] }

interface PhotoState { file: File; preview: string }

interface TaskState { taskId: string; status: string; result: Record<string, unknown> | null }

interface AppState {
  session: Session | null;
  balance: number;
  photo: PhotoState | null;
  preAnalysis: api.PreAnalysisResponse | null;
  activeCategory: CategoryId;
  selectedStyleKey: string;
  currentTask: TaskState | null;
  isGenerating: boolean;
  error: string | null;
  generatedImageUrl: string | null;
  afterScore: number | null;
  afterPerception: Record<string, number> | null;
  generationMode: CategoryId | null;
  isAuthenticated: boolean;
  preAnalyzeLoading: boolean;
  noCreditsError: boolean;
  preAnalyzeError: boolean;
  taskHistory: api.TaskHistoryItem[];
  taskHistoryCount: number;
  identities: api.LinkedIdentity[];
  scenarioSlug: string | null;
  scenarioType: ScenarioType | null;
  scenarioEntryMode: ScenarioEntryMode | null;
  scenarioHideCategoryTabs: boolean;
  scenarioStep3Mode: ScenarioStep3Mode | null;
  scenarioDocumentPaywall: boolean;
  scenarioPrimaryCtaMainApp: boolean;
  scenarioSimplifiedAnalysis: boolean;
  scenarioPaymentPackQty: number | null;
  effectiveStyleList: StyleItem[];
  effectiveApiMode: string;
  hasRealAuth: boolean;
  canAccessApp: boolean;
  consentState: api.ConsentState | null;
}

interface AppActions {
  syncScenarioFromRoute: (slug: string | undefined) => void;
  setActiveCategory: (c: CategoryId) => void;
  setSelectedStyleKey: (k: string) => void;
  uploadPhoto: (f: File) => void;
  runPreAnalyze: () => Promise<void>;
  generate: (onTaskCreated?: () => void, styleKeyOverride?: string) => Promise<void>;
  share: () => Promise<api.ShareResponse | null>;
  refreshBalance: () => Promise<void>;
  clearError: () => void;
  clearGeneratedImage: () => void;
  clearNoCreditsError: () => void;
  resetGeneration: () => void;
  fetchTaskHistory: () => Promise<void>;
  loginWithOAuth: (provider: 'yandex' | 'vk-id' | 'google') => Promise<void>;
  loginWithToken: (token: string, userId?: string, provider?: string) => Promise<void>;
  logout: () => void;
  refreshIdentities: () => Promise<void>;
  fetchConsents: () => Promise<void>;
  grantConsents: (kinds: string[]) => Promise<void>;
  revokeConsents: (kinds: string[]) => Promise<void>;
}

const Ctx = createContext<(AppState & AppActions) | null>(null);

export function useApp() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp must be inside AppProvider');
  return v;
}

function extractAfterScores(result: Record<string, unknown>, mode: string) {
  const delta = result.delta as Record<string, { pre: number; post: number; delta: number }> | undefined;
  const percDelta = result.perception_delta as Record<string, { pre: number; post: number; delta: number }> | undefined;

  let score: number | null = null;
  if (delta) {
    if (mode === 'dating') score = delta.dating_score?.post ?? null;
    else if (mode === 'social') score = delta.social_score?.post ?? null;
    else if (mode === 'cv') {
      const vals = ['trust', 'competence', 'hireability']
        .map(k => delta[k]?.post)
        .filter((v): v is number => v != null);
      score = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    }
  }
  if (score == null) {
    score = (result.dating_score ?? result.social_score ?? result.score ?? null) as number | null;
  }

  let perception: Record<string, number> | null = null;
  if (percDelta) {
    perception = {};
    for (const [k, v] of Object.entries(percDelta)) perception[k] = v.post;
    const auth = (result.perception_scores as Record<string, number> | undefined)?.authenticity;
    if (auth != null) perception.authenticity = auth;
  } else {
    const ps = result.perception_scores as Record<string, number> | undefined;
    if (ps) perception = ps;
  }

  return { score, perception };
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [balance, setBalance] = useState(0);
  const [photo, setPhoto] = useState<PhotoState | null>(null);
  const [preAnalysis, setPreAnalysis] = useState<api.PreAnalysisResponse | null>(null);
  const [activeCategory, setActiveCategory] = useState<CategoryId>('social');
  const [selectedStyleKey, setSelectedStyleKey] = useState('');
  const [currentTask, setCurrentTask] = useState<TaskState | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(() => {
    // Если пользователь перезагрузил страницу, а фоновая генерация успела
    // упасть — подхватим маркер из sessionStorage, чтобы показать баннер ошибки.
    try {
      const last = peekLastGenerationError();
      return last && !hasPendingTask() ? last.message : null;
    } catch {
      return null;
    }
  });
  const [generatedImageUrl, setGeneratedImageUrl] = useState<string | null>(null);
  const [afterScore, setAfterScore] = useState<number | null>(null);
  const [afterPerception, setAfterPerception] = useState<Record<string, number> | null>(null);
  const [generationMode, setGenerationMode] = useState<CategoryId | null>(null);

  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [preAnalyzeLoading, setPreAnalyzeLoading] = useState(false);
  const [noCreditsError, setNoCreditsError] = useState(false);
  const [preAnalyzeError, setPreAnalyzeError] = useState(false);
  const [taskHistory, setTaskHistory] = useState<api.TaskHistoryItem[]>([]);
  const [taskHistoryCount, setTaskHistoryCount] = useState(0);
  const [identities, setIdentities] = useState<api.LinkedIdentity[]>([]);
  const [scenarioSlug, setScenarioSlug] = useState<string | null>(null);
  const [consentState, setConsentState] = useState<api.ConsentState | null>(null);

  const hasRealAuth = useMemo(
    () => identities.some(id => id.provider !== 'web'),
    [identities],
  );
  const canAccessApp = useMemo(() => {
    if (session?.provider && session.provider !== 'web') {
      return true;
    }
    return hasRealAuth;
  }, [session, hasRealAuth]);

  const scenarioDef = useMemo(() => getScenario(scenarioSlug), [scenarioSlug]);
  const scenarioType: ScenarioType | null = scenarioDef?.type ?? null;
  const scenarioEntryMode: ScenarioEntryMode | null = scenarioDef?.entryMode ?? null;
  const scenarioHideCategoryTabs = scenarioDef?.hideCategoryTabs ?? false;
  const scenarioStep3Mode: ScenarioStep3Mode | null = scenarioDef?.step3Mode ?? null;
  const scenarioDocumentPaywall = scenarioDef?.documentPaywall ?? false;
  const scenarioPrimaryCtaMainApp = scenarioDef?.primaryCtaMainApp ?? false;
  const scenarioSimplifiedAnalysis = scenarioDef?.simplifiedAnalysis ?? false;
  const scenarioPaymentPackQty = scenarioDef?.paymentPackQty ?? null;
  const modeMap: Record<CategoryId, string> = useMemo(
    () => ({ social: 'social', cv: 'cv', dating: 'dating', model: 'social', brand: 'social', memes: 'social' }),
    [],
  );
  const effectiveApiMode = useMemo(() => {
    if (scenarioDef) return scenarioDef.apiMode;
    return modeMap[activeCategory];
  }, [scenarioDef, activeCategory, modeMap]);

  const effectiveStyleList = useMemo(() => {
    const resolved = resolveScenarioStyles(scenarioDef);
    return resolved ?? STYLES_BY_CATEGORY[activeCategory];
  }, [scenarioDef, activeCategory]);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sseRef = useRef<EventSource | null>(null);
  const deltaRefreshRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // ID задачи, для которой уже поднят SSE/polling — нужно, чтобы resume-эффект
  // и refreshLiveData (focus/visibility) не пересоздавали соединение каждый раз.
  const resumedTaskIdRef = useRef<string | null>(null);
  // Периодический refresh баланса/истории пока идёт генерация.
  const historyIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const preAnalysisCacheRef = useRef<Record<string, api.PreAnalysisResponse>>({});
  const preAnalyzeInFlightRef = useRef(false);
  const preAnalyzeGenRef = useRef(0);

  const syncScenarioFromRoute = useCallback((slug: string | undefined) => {
    if (!slug) {
      setScenarioSlug(null);
      return;
    }
    const def = getScenario(slug);
    if (!def) {
      setScenarioSlug(null);
      return;
    }
    setScenarioSlug(slug);
    setActiveCategory(def.scoresCategory);
    setSelectedStyleKey('');
    preAnalysisCacheRef.current = {};
    preAnalyzeGenRef.current++;
    setPreAnalysis(null);
    setPreAnalyzeError(false);
  }, []);

  const handleAuthError = useCallback(async (e: unknown): Promise<boolean> => {
    if (e instanceof api.ApiError && e.status === 401) {
      authLogout();
      localStorage.removeItem('ailook_provider');
      setSession(null);
      setIsAuthenticated(false);
      setBalance(0);
      setError('Сессия истекла. Пожалуйста, войдите снова.');
      return true;
    }
    return false;
  }, []);

  const refreshBalance = useCallback(async () => {
    try {
      const b = await api.getBalance();
      setBalance(b.image_credits);
    } catch (e) { await handleAuthError(e); }
  }, [handleAuthError]);

  const refreshIdentities = useCallback(async () => {
    try {
      const res = await api.getMyIdentities();
      setIdentities(res.identities);
    } catch (e) { await handleAuthError(e); }
  }, [handleAuthError]);

  const fetchConsents = useCallback(async () => {
    try {
      const res = await api.getConsents();
      setConsentState(res);
    } catch (e) {
      await handleAuthError(e);
    }
  }, [handleAuthError]);

  const grantConsents = useCallback(async (kinds: string[]) => {
    const res = await api.grantConsents(kinds, 'web');
    setConsentState(res);
  }, []);

  const revokeConsents = useCallback(async (kinds: string[]) => {
    const res = await api.revokeConsents(kinds);
    setConsentState(res);
  }, []);

  const fetchTaskHistory = useCallback(async () => {
    try {
      const res = await api.getTaskHistory(100, 0);
      setTaskHistory(res.items);
      setTaskHistoryCount(res.total_count);
    } catch (e) { await handleAuthError(e); }
  }, [handleAuthError]);

  const uploadPhoto = useCallback((f: File) => {
    const preview = URL.createObjectURL(f);
    setPhoto({ file: f, preview });
    setPreAnalysis(null);
    setPreAnalyzeError(false);
    preAnalysisCacheRef.current = {};
    preAnalyzeGenRef.current++;
    setCurrentTask(null);
    setGeneratedImageUrl(null);
    setAfterScore(null);
    setAfterPerception(null);
    setGenerationMode(null);
    setPreAnalyzeLoading(false);
  }, []);

  const runPreAnalyze = useCallback(async () => {
    if (!photo || preAnalyzeInFlightRef.current) return;
    const mode = effectiveApiMode;

    const cached = preAnalysisCacheRef.current[mode];
    if (cached) {
      setPreAnalysis(cached);
      return;
    }

    preAnalyzeInFlightRef.current = true;
    const gen = ++preAnalyzeGenRef.current;
    setPreAnalysis(null);
    setPreAnalyzeError(false);
    setPreAnalyzeLoading(true);
    try {
      const res = await api.preAnalyze(photo.file, mode);
      if (gen !== preAnalyzeGenRef.current) return;
      preAnalysisCacheRef.current[mode] = res;
      setPreAnalysis(res);
    } catch (e) {
      if (gen !== preAnalyzeGenRef.current) return;
      if (e instanceof api.ApiError && e.status === 401) {
        await handleAuthError(e);
        return;
      }
      if (e instanceof api.ApiError && e.status === 451) {
        void fetchConsents();
        setPreAnalyzeError(false);
        setError('Нужно подтвердить согласия на обработку данных.');
        return;
      }
      setPreAnalyzeError(true);
      setError(e instanceof api.ApiError ? e.body : 'Pre-analyze failed');
    } finally {
      preAnalyzeInFlightRef.current = false;
      setPreAnalyzeLoading(false);
    }
  }, [photo, effectiveApiMode, handleAuthError, fetchConsents]);

  const loginWithOAuth = useCallback(async (provider: 'yandex' | 'vk-id' | 'google') => {
    const returnPath = typeof window !== 'undefined' ? `${window.location.pathname}${window.location.search}` : '';
    if (returnPath) {
      rememberOAuthReturnPath(returnPath);
    }
    await startOAuth(provider, photo ? {
      file: photo.file,
      mode: activeCategory,
      style: selectedStyleKey,
      scenarioSlug: scenarioSlug ?? undefined,
      returnPath: returnPath || undefined,
    } : undefined);
  }, [photo, activeCategory, selectedStyleKey, scenarioSlug]);

  const loginWithToken = useCallback(async (token: string, userId?: string, provider?: string) => {
    api.setToken(token);
    const prov = provider || localStorage.getItem('ailook_provider') || '';
    if (provider) localStorage.setItem('ailook_provider', provider);
    try {
      const b = await api.getBalance();
      setBalance(b.image_credits);
    } catch (e) {
      if (e instanceof api.ApiError && e.status === 401) throw e;
    }
    const usage = await api.getUsage().catch(() => ({
      daily_limit: 0, used: 0, remaining: 0, is_premium: false,
    }));
    setSession({ token, userId: userId || '', provider: prov, usage });
    setIsAuthenticated(true);

    api.getTaskHistory(100, 0).then(res => {
      setTaskHistory(res.items);
      setTaskHistoryCount(res.total_count);
    }).catch(() => {});

    api.getMyIdentities().then(res => {
      setIdentities(res.identities);
    }).catch(() => {});

    api.getConsents().then(setConsentState).catch(() => {});

    const restored = await restorePhotoAfterOAuth();
    if (restored) {
      const preview = URL.createObjectURL(restored.file);
      setPhoto({ file: restored.file, preview });
      if (restored.mode) setActiveCategory(restored.mode as CategoryId);
      if (restored.style) setSelectedStyleKey(restored.style);
      if (restored.scenarioSlug) setScenarioSlug(restored.scenarioSlug);
      if (restored.returnPath) {
        rememberOAuthReturnPath(restored.returnPath);
      }
      await clearPersistedPhoto();
    }
  }, []);

  const logout = useCallback(() => {
    authLogout();
    clearPendingTask();
    clearLastGenerationError();
    resumedTaskIdRef.current = null;
    localStorage.removeItem('ailook_provider');
    setSession(null);
    setIsAuthenticated(false);
    setBalance(0);
    setPhoto(null);
    setGeneratedImageUrl(null);
    setCurrentTask(null);
    setPreAnalysis(null);
    setAfterScore(null);
    setAfterPerception(null);
    setGenerationMode(null);
    setError(null);
    setIsGenerating(false);
    setIdentities([]);
    setScenarioSlug(null);
    setConsentState(null);
  }, []);

  useEffect(() => {
    const saved = restoreToken();
    if (saved) {
      loginWithToken(saved).catch(() => { /* token expired */ });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const prevAuthRef = useRef(false);
  const prevPhotoRef = useRef<PhotoState | null>(null);
  useEffect(() => {
    const authJustBecameTrue = canAccessApp && !prevAuthRef.current;
    const photoChanged = photo && photo !== prevPhotoRef.current;
    if (canAccessApp && photo && (authJustBecameTrue || photoChanged)) {
      runPreAnalyze();
    }
    prevAuthRef.current = canAccessApp;
    prevPhotoRef.current = photo;
  }, [canAccessApp, photo, runPreAnalyze]);

  const stopDeltaRefresh = useCallback(() => {
    if (deltaRefreshRef.current) {
      clearTimeout(deltaRefreshRef.current);
      deltaRefreshRef.current = null;
    }
  }, []);

  const stopHistoryRefresh = useCallback(() => {
    if (historyIntervalRef.current) {
      clearInterval(historyIntervalRef.current);
      historyIntervalRef.current = null;
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
    stopDeltaRefresh();
  }, [stopDeltaRefresh]);

  const verifyImageUrl = useCallback(async (url: string, retries = 3, delayMs = 2000): Promise<boolean> => {
    for (let i = 0; i < retries; i++) {
      try {
        const ok = await new Promise<boolean>((resolve) => {
          const img = new Image();
          const cleanup = () => { img.onload = null; img.onerror = null; };
          img.onload = () => { cleanup(); resolve(true); };
          img.onerror = () => { cleanup(); resolve(false); };
          img.src = url;
        });
        if (ok) return true;
      } catch { /* retry */ }
      if (i < retries - 1) await new Promise(r => setTimeout(r, delayMs * (i + 1)));
    }
    return false;
  }, []);

  const scheduleDeferredDeltaRefresh = useCallback((taskId: string, mode: string, attempt = 0) => {
    stopDeltaRefresh();
    const maxAttempts = 20;
    const delayMs = attempt < 4 ? 1500 : 3000;
    deltaRefreshRef.current = setTimeout(async () => {
      try {
        const t = await api.getTask(taskId);
        const r = t.result as Record<string, unknown> | null;
        const deltaStatus = (r?.delta_status as string | undefined) ?? '';
        if (t.status === 'completed' && deltaStatus === 'pending' && attempt < maxAttempts) {
          scheduleDeferredDeltaRefresh(taskId, mode, attempt + 1);
          return;
        }
        setCurrentTask({ taskId: t.task_id, status: t.status, result: t.result });
        if (r) {
          const { score, perception } = extractAfterScores(r, mode);
          if (score != null) setAfterScore(score);
          if (perception) setAfterPerception(perception);
        }
      } catch {
        if (attempt < maxAttempts) {
          scheduleDeferredDeltaRefresh(taskId, mode, attempt + 1);
        }
      }
    }, delayMs);
  }, [stopDeltaRefresh]);

  const handleTaskResult = useCallback(async (taskId: string, mode: string, category: CategoryId) => {
    try {
      const t = await api.getTask(taskId);
      setCurrentTask({ taskId: t.task_id, status: t.status, result: t.result });
      if (t.status === 'completed') {
        clearPendingTask(taskId);
        const r = t.result as Record<string, unknown> | null;
        if (r) {
          const imgUrl = normalizeImageUrl(
            (r.generated_image_url ?? r.image_url ?? '') as string,
          );
          if (imgUrl) {
            const available = await verifyImageUrl(imgUrl);
            if (available) {
              setGeneratedImageUrl(imgUrl);
              clearLastGenerationError();
            } else {
              const msg = 'Не удалось загрузить сгенерированное изображение. Попробуйте снова.';
              setError(msg);
              rememberLastGenerationError(taskId, msg);
              api.refundTask(taskId).then(() => refreshBalance()).catch(() => {});
            }
          } else {
            const reason = r.no_image_reason as string | undefined;
            const refunded = Boolean(r.credit_refunded);
            const NO_IMAGE_MESSAGES: Record<string, string> = {
              no_credits: 'Недостаточно кредитов для генерации изображения. Пополните баланс.',
              generation_error: refunded
                ? 'Не удалось сгенерировать изображение. Кредит возвращён — попробуйте другой стиль или фото.'
                : 'Не удалось сгенерировать изображение. Попробуйте другой стиль или фото.',
              upgrade_required: 'Для генерации изображения необходимо пополнить баланс.',
              not_applicable: 'Для данного режима генерация изображения недоступна.',
            };
            const msg = NO_IMAGE_MESSAGES[reason ?? ''] ?? 'Анализ завершён без изображения.';
            setError(msg);
            rememberLastGenerationError(taskId, msg);
            // Подстраховка на случай, если worker почему-то не вернул кредит
            // (например, упал при рефанде): endpoint идемпотентный — вернёт 409,
            // если кредит уже был возвращён, и реально списан + картинки нет —
            // иначе вернёт кредит и обновит баланс.
            if (!refunded && reason === 'generation_error') {
              api.refundTask(taskId).then(() => refreshBalance()).catch(() => {});
            }
          }
          const { score, perception } = extractAfterScores(r, mode);
          if (score != null) setAfterScore(score);
          if (perception) setAfterPerception(perception);
          if (r.delta_status === 'pending') {
            scheduleDeferredDeltaRefresh(taskId, mode);
          }
        }
        setGenerationMode(category);
        setIsGenerating(false);
        resumedTaskIdRef.current = null;
        refreshBalance();
        fetchTaskHistory();
      } else if (t.status === 'failed') {
        clearPendingTask(taskId);
        setIsGenerating(false);
        resumedTaskIdRef.current = null;
        const msg = t.error_message ?? 'Не удалось сгенерировать фото. Кредит возвращён, попробуйте ещё раз.';
        setError(msg);
        rememberLastGenerationError(taskId, msg);
        refreshBalance();
        fetchTaskHistory();
      }
    } catch {
      setIsGenerating(false);
      setError('Не удалось получить результат. Проверьте подключение и попробуйте снова.');
    }
  }, [refreshBalance, fetchTaskHistory, verifyImageUrl, scheduleDeferredDeltaRefresh]);

  const startPollingFallback = useCallback((taskId: string, mode: string, category: CategoryId) => {
    if (pollingRef.current) return;
    let errorCount = 0;
    const MAX_ERRORS = 5;
    const TIMEOUT_MS = 5 * 60 * 1000;
    const startedAt = Date.now();
    pollingRef.current = setInterval(async () => {
      if (Date.now() - startedAt > TIMEOUT_MS) {
        stopPolling();
        setIsGenerating(false);
        setError('Превышено время ожидания результата. Попробуйте снова.');
        return;
      }
      try {
        const t = await api.getTask(taskId);
        errorCount = 0;
        setCurrentTask({ taskId: t.task_id, status: t.status, result: t.result });
        if (t.status === 'completed' || t.status === 'failed') {
          stopPolling();
          await handleTaskResult(taskId, mode, category);
        }
      } catch {
        errorCount++;
        if (errorCount >= MAX_ERRORS) {
          stopPolling();
          setIsGenerating(false);
          setError('Не удалось получить результат. Проверьте подключение и попробуйте снова.');
        }
      }
    }, 3000);
  }, [stopPolling, handleTaskResult]);

  const startPolling = useCallback(async (taskId: string, category: CategoryId, apiMode: string) => {
    stopPolling();
    const mode = apiMode;
    const sseUrl = `${api.API_BASE}/api/v1/sse/progress?task_id=${taskId}`;

    try {
      const initialTask = await api.getTask(taskId);
      setCurrentTask({ taskId: initialTask.task_id, status: initialTask.status, result: initialTask.result });
      if (initialTask.status === 'completed' || initialTask.status === 'failed') {
        await handleTaskResult(taskId, mode, category);
        return;
      }

      let ticketParam = '';
      try {
        const { ticket } = await api.createSseTicket();
        ticketParam = `&ticket=${encodeURIComponent(ticket)}`;
      } catch {
        const token = api.getToken();
        if (token) ticketParam = `&token=${encodeURIComponent(token)}`;
      }

      const es = new EventSource(`${sseUrl}${ticketParam}`);
      sseRef.current = es;

      es.addEventListener('done', async (ev) => {
        stopPolling();
        await handleTaskResult(taskId, mode, category);
      });

      es.addEventListener('progress', (ev) => {
        const parts = (ev.data as string).split(':');
        if (parts.length >= 3) {
          setCurrentTask(prev => prev ? { ...prev, status: `${parts[0]} ${parts[1]}/${parts[2]}` } : prev);
        }
      });

      es.onerror = () => {
        if (sseRef.current) {
          sseRef.current.close();
          sseRef.current = null;
        }
        startPollingFallback(taskId, mode, category);
      };

      setTimeout(() => {
        if (sseRef.current === es && es.readyState !== EventSource.OPEN) {
          es.close();
          sseRef.current = null;
          startPollingFallback(taskId, mode, category);
        }
      }, 5000);

    } catch {
      startPollingFallback(taskId, mode, category);
    }
  }, [stopPolling, handleTaskResult, startPollingFallback]);

  useEffect(() => () => {
    stopPolling();
    stopHistoryRefresh();
  }, [stopPolling, stopHistoryRefresh]);

  // activeCategory нужен только как fallback при восстановлении; держим в ref,
  // чтобы не перезапускать resume-эффект при каждом переключении таба.
  const activeCategoryRef = useRef<CategoryId>(activeCategory);
  useEffect(() => {
    activeCategoryRef.current = activeCategory;
  }, [activeCategory]);

  const resumePendingIfNeeded = useCallback(() => {
    const pending = peekPendingTask();
    if (!pending || !canAccessApp) return;

    const def = pending.scenarioSlug ? getScenario(pending.scenarioSlug) : null;
    const apiMode = def?.apiMode ?? pending.apiMode;
    const category = (
      def?.scoresCategory
      ?? (pending.category === 'cv' || pending.category === 'dating' || pending.category === 'social'
        ? pending.category
        : activeCategoryRef.current)
    ) as CategoryId;

    setIsGenerating(true);
    if (pending.scenarioSlug) {
      setScenarioSlug(pending.scenarioSlug);
    }

    // Уже поднято соединение для этой задачи — не пересоздаём, чтобы не терять события.
    const alreadyRunning = resumedTaskIdRef.current === pending.taskId
      && (pollingRef.current !== null || sseRef.current !== null);
    if (alreadyRunning) return;

    resumedTaskIdRef.current = pending.taskId;
    void startPolling(pending.taskId, category, apiMode);
  }, [canAccessApp, startPolling]);

  useEffect(() => {
    resumePendingIfNeeded();
  }, [canAccessApp, resumePendingIfNeeded]);

  useEffect(() => {
    if (!canAccessApp) return;

    void refreshBalance();
    void fetchTaskHistory();

    const refreshLiveData = () => {
      void refreshBalance();
      void fetchTaskHistory();
      resumePendingIfNeeded();
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        refreshLiveData();
      }
    };

    window.addEventListener('focus', refreshLiveData);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.removeEventListener('focus', refreshLiveData);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [canAccessApp, refreshBalance, fetchTaskHistory, resumePendingIfNeeded]);

  useEffect(() => {
    // Пока идёт генерация — регулярно тянем свежий баланс и историю, чтобы
    // в "Хранилище" быстро появилось новое фото и обновился счётчик кредитов.
    if (historyIntervalRef.current) {
      clearInterval(historyIntervalRef.current);
      historyIntervalRef.current = null;
    }
    if (!isGenerating || !canAccessApp) return;

    historyIntervalRef.current = setInterval(() => {
      void fetchTaskHistory();
      void refreshBalance();
    }, 6000);

    return () => {
      if (historyIntervalRef.current) {
        clearInterval(historyIntervalRef.current);
        historyIntervalRef.current = null;
      }
    };
  }, [isGenerating, canAccessApp, fetchTaskHistory, refreshBalance]);

  const generate = useCallback(async (onTaskCreated?: () => void, styleKeyOverride?: string) => {
    const effectiveStyle = styleKeyOverride || selectedStyleKey;
    if (!photo || !effectiveStyle || isGenerating) return;
    setIsGenerating(true);
    setError(null);
    setGeneratedImageUrl(null);
    setAfterScore(null);
    setAfterPerception(null);
    clearLastGenerationError();
    resumedTaskIdRef.current = null;
    try {
      const enhancementLevel = 1;
      const res = await api.analyze(
        photo.file,
        effectiveApiMode,
        effectiveStyle,
        preAnalysis?.pre_analysis_id,
        enhancementLevel,
        scenarioSlug ?? undefined,
        scenarioType ?? undefined,
        scenarioEntryMode ?? undefined,
      );
      setCurrentTask({ taskId: res.task_id, status: res.status, result: null });
      rememberPendingTask({
        taskId: res.task_id,
        apiMode: effectiveApiMode,
        category: activeCategory,
        scenarioSlug: scenarioSlug ?? undefined,
        startedAt: Date.now(),
      });
      resumedTaskIdRef.current = res.task_id;
      onTaskCreated?.();
      startPolling(res.task_id, activeCategory, effectiveApiMode);
    } catch (e) {
      if (e instanceof api.ApiError && e.status === 401) {
        const reauthed = await handleAuthError(e);
        setIsGenerating(false);
        clearPendingTask();
        if (reauthed) {
          setError('Сессия обновлена. Попробуйте ещё раз.');
        }
      } else {
        setIsGenerating(false);
        clearPendingTask();
        if (e instanceof api.ApiError && e.status === 402) {
          setNoCreditsError(true);
        } else if (e instanceof api.ApiError && e.status === 451) {
          void fetchConsents();
          setError('Нужно подтвердить согласия на обработку данных.');
        } else {
          setError(e instanceof api.ApiError ? e.body : 'Generation failed');
        }
      }
    }
  }, [
    photo,
    selectedStyleKey,
    activeCategory,
    effectiveApiMode,
    preAnalysis,
    startPolling,
    isGenerating,
    handleAuthError,
    scenarioSlug,
    scenarioType,
    scenarioEntryMode,
    fetchConsents,
  ]);

  const share = useCallback(async () => {
    if (!currentTask?.taskId) return null;
    try {
      return await api.createShare(currentTask.taskId);
    } catch {
      return null;
    }
  }, [currentTask]);

  const clearError = useCallback(() => {
    setError(null);
    clearLastGenerationError();
  }, []);
  const clearNoCreditsError = useCallback(() => setNoCreditsError(false), []);
  const clearGeneratedImage = useCallback(() => {
    stopPolling();
    clearPendingTask();
    setGeneratedImageUrl(null);
    setCurrentTask(null);
    setIsGenerating(false);
  }, [stopPolling]);

  const resetGeneration = useCallback(() => {
    clearPendingTask();
    clearLastGenerationError();
    resumedTaskIdRef.current = null;
    setGeneratedImageUrl(null);
    setAfterScore(null);
    setAfterPerception(null);
    setCurrentTask(null);
    setIsGenerating(false);
    setGenerationMode(null);
  }, []);

  const value: AppState & AppActions = {
    session, balance, photo, preAnalysis, activeCategory, selectedStyleKey,
    currentTask, isGenerating, error, generatedImageUrl, afterScore, afterPerception,
    generationMode, isAuthenticated, preAnalyzeLoading,
    noCreditsError, preAnalyzeError, taskHistory, taskHistoryCount, identities,
    scenarioSlug, scenarioType, scenarioEntryMode, scenarioHideCategoryTabs, scenarioStep3Mode,
    scenarioDocumentPaywall, scenarioPrimaryCtaMainApp, scenarioSimplifiedAnalysis,
    scenarioPaymentPackQty, effectiveStyleList, effectiveApiMode, hasRealAuth, canAccessApp,
    consentState,
    syncScenarioFromRoute,
    setActiveCategory, setSelectedStyleKey, uploadPhoto, runPreAnalyze,
    generate, share, refreshBalance, clearError, clearGeneratedImage, clearNoCreditsError,
    resetGeneration, fetchTaskHistory,
    loginWithOAuth, loginWithToken, logout, refreshIdentities,
    fetchConsents, grantConsents, revokeConsents,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
