import { createContext, useContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react';
import { restoreToken, startOAuth, logout as authLogout } from '../lib/auth';
import * as api from '../lib/api';
import type { CategoryId } from '../data/styles';
import { restorePhotoAfterOAuth, clearPersistedPhoto } from '../lib/photo-persist';
import { normalizeImageUrl } from '../lib/image-url';

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
}

interface AppActions {
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
  loginWithOAuth: (provider: 'yandex' | 'vk-id') => Promise<void>;
  loginWithToken: (token: string, userId?: string, provider?: string) => Promise<void>;
  logout: () => void;
  refreshIdentities: () => Promise<void>;
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
  const [error, setError] = useState<string | null>(null);
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

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sseRef = useRef<EventSource | null>(null);
  const preAnalysisCacheRef = useRef<Record<string, api.PreAnalysisResponse>>({});
  const preAnalyzeInFlightRef = useRef(false);
  const preAnalyzeGenRef = useRef(0);

  const handleAuthError = useCallback((e: unknown) => {
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
    } catch (e) { handleAuthError(e); }
  }, [handleAuthError]);

  const refreshIdentities = useCallback(async () => {
    try {
      const res = await api.getMyIdentities();
      setIdentities(res.identities);
    } catch (e) { handleAuthError(e); }
  }, [handleAuthError]);

  const fetchTaskHistory = useCallback(async () => {
    try {
      const res = await api.getTaskHistory(100, 0);
      setTaskHistory(res.items);
      setTaskHistoryCount(res.total_count);
    } catch (e) { handleAuthError(e); }
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
    const modeMap: Record<CategoryId, string> = { social: 'social', cv: 'cv', dating: 'dating' };
    const mode = modeMap[activeCategory];

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
      setPreAnalyzeError(true);
      setError(e instanceof api.ApiError ? e.body : 'Pre-analyze failed');
    } finally {
      preAnalyzeInFlightRef.current = false;
      setPreAnalyzeLoading(false);
    }
  }, [photo, activeCategory]);

  const loginWithOAuth = useCallback(async (provider: 'yandex' | 'vk-id') => {
    await startOAuth(provider, photo ? {
      file: photo.file,
      mode: activeCategory,
      style: selectedStyleKey,
    } : undefined);
  }, [photo, activeCategory, selectedStyleKey]);

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
      daily_limit: 3, used: 0, remaining: 3, is_premium: false,
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

    const restored = await restorePhotoAfterOAuth();
    if (restored) {
      const preview = URL.createObjectURL(restored.file);
      setPhoto({ file: restored.file, preview });
      if (restored.mode) setActiveCategory(restored.mode as CategoryId);
      if (restored.style) setSelectedStyleKey(restored.style);
      await clearPersistedPhoto();
    }
  }, []);

  const logout = useCallback(() => {
    authLogout();
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
    const authJustBecameTrue = isAuthenticated && !prevAuthRef.current;
    const photoJustAppeared = photo && !prevPhotoRef.current;
    if (isAuthenticated && photo && (authJustBecameTrue || photoJustAppeared)) {
      runPreAnalyze();
    }
    prevAuthRef.current = isAuthenticated;
    prevPhotoRef.current = photo;
  }, [isAuthenticated, photo, runPreAnalyze]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
  }, []);

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

  const handleTaskResult = useCallback(async (taskId: string, mode: string, category: CategoryId) => {
    try {
      const t = await api.getTask(taskId);
      setCurrentTask({ taskId: t.task_id, status: t.status, result: t.result });
      if (t.status === 'completed') {
        const r = t.result as Record<string, unknown> | null;
        if (r) {
          const imgUrl = normalizeImageUrl(
            (r.generated_image_url ?? r.image_url ?? '') as string,
          );
          if (imgUrl) {
            const available = await verifyImageUrl(imgUrl);
            if (available) {
              setGeneratedImageUrl(imgUrl);
            } else {
              setError('Не удалось загрузить сгенерированное изображение. Попробуйте снова.');
            }
          } else {
            const reason = r.no_image_reason as string | undefined;
            const NO_IMAGE_MESSAGES: Record<string, string> = {
              no_credits: 'Недостаточно кредитов для генерации изображения. Пополните баланс.',
              generation_error: 'Не удалось сгенерировать изображение. Попробуйте другой стиль или фото.',
              upgrade_required: 'Для генерации изображения необходимо пополнить баланс.',
              not_applicable: 'Для данного режима генерация изображения недоступна.',
            };
            setError(NO_IMAGE_MESSAGES[reason ?? ''] ?? 'Анализ завершён без изображения.');
          }
          const { score, perception } = extractAfterScores(r, mode);
          if (score != null) setAfterScore(score);
          if (perception) setAfterPerception(perception);
        }
        setGenerationMode(category);
        setIsGenerating(false);
        refreshBalance();
        fetchTaskHistory();
      } else if (t.status === 'failed') {
        setIsGenerating(false);
        setError(t.error_message ?? 'Generation failed');
      }
    } catch {
      setIsGenerating(false);
      setError('Не удалось получить результат. Проверьте подключение и попробуйте снова.');
    }
  }, [refreshBalance, fetchTaskHistory, verifyImageUrl]);

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

  const startPolling = useCallback((taskId: string, category: CategoryId) => {
    stopPolling();
    const mode = category as string;
    const token = api.getToken();
    const sseUrl = `${api.API_BASE}/api/v1/sse/progress?task_id=${taskId}`;

    try {
      const es = new EventSource(
        token ? `${sseUrl}&token=${encodeURIComponent(token)}` : sseUrl,
      );
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

  useEffect(() => () => stopPolling(), [stopPolling]);

  const generate = useCallback(async (onTaskCreated?: () => void, styleKeyOverride?: string) => {
    const effectiveStyle = styleKeyOverride || selectedStyleKey;
    if (!photo || !effectiveStyle || isGenerating) return;
    setIsGenerating(true);
    setError(null);
    setGeneratedImageUrl(null);
    setAfterScore(null);
    setAfterPerception(null);
    try {
      const modeMap: Record<CategoryId, string> = { social: 'social', cv: 'cv', dating: 'dating' };
      const enhancementLevel = 1;
      const res = await api.analyze(
        photo.file,
        modeMap[activeCategory],
        effectiveStyle,
        preAnalysis?.pre_analysis_id,
        enhancementLevel,
      );
      setCurrentTask({ taskId: res.task_id, status: res.status, result: null });
      onTaskCreated?.();
      startPolling(res.task_id, activeCategory);
    } catch (e) {
      setIsGenerating(false);
      if (e instanceof api.ApiError && e.status === 402) {
        setNoCreditsError(true);
      } else {
        setError(e instanceof api.ApiError ? e.body : 'Generation failed');
      }
    }
  }, [photo, selectedStyleKey, activeCategory, preAnalysis, startPolling, isGenerating]);

  const share = useCallback(async () => {
    if (!currentTask?.taskId) return null;
    try {
      return await api.createShare(currentTask.taskId);
    } catch {
      return null;
    }
  }, [currentTask]);

  const clearError = useCallback(() => setError(null), []);
  const clearNoCreditsError = useCallback(() => setNoCreditsError(false), []);
  const clearGeneratedImage = useCallback(() => {
    stopPolling();
    setGeneratedImageUrl(null);
    setCurrentTask(null);
    setIsGenerating(false);
  }, [stopPolling]);

  const resetGeneration = useCallback(() => {
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
    setActiveCategory, setSelectedStyleKey, uploadPhoto, runPreAnalyze,
    generate, share, refreshBalance, clearError, clearGeneratedImage, clearNoCreditsError,
    resetGeneration, fetchTaskHistory,
    loginWithOAuth, loginWithToken, logout, refreshIdentities,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
