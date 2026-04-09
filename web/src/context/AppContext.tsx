import { createContext, useContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react';
import { login, restoreToken, startOAuth } from '../lib/auth';
import * as api from '../lib/api';
import type { CategoryId } from '../data/styles';

interface Session { token: string; userId: string; usage: api.ChannelAuthResponse['usage'] }

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
  isAuthenticated: boolean;
  isSimulating: boolean;
  simulationDone: boolean;
}

interface AppActions {
  setActiveCategory: (c: CategoryId) => void;
  setSelectedStyleKey: (k: string) => void;
  uploadPhoto: (f: File) => void;
  runPreAnalyze: () => Promise<void>;
  generate: () => Promise<void>;
  share: () => Promise<api.ShareResponse | null>;
  refreshBalance: () => Promise<void>;
  clearError: () => void;
  startSimulation: () => void;
  authenticateUser: (email: string) => Promise<void>;
  loginWithOAuth: (provider: 'yandex' | 'vk-id') => Promise<void>;
  loginWithToken: (token: string) => Promise<void>;
}

const Ctx = createContext<(AppState & AppActions) | null>(null);

export function useApp() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp must be inside AppProvider');
  return v;
}

const EMAIL_KEY = 'ailook_user_email';

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

  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationDone, setSimulationDone] = useState(false);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const simTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshBalance = useCallback(async () => {
    try {
      const b = await api.getBalance();
      setBalance(b.image_credits);
    } catch { /* ignore */ }
  }, []);

  const uploadPhoto = useCallback((f: File) => {
    const preview = URL.createObjectURL(f);
    setPhoto({ file: f, preview });
    setPreAnalysis(null);
    setCurrentTask(null);
    setGeneratedImageUrl(null);
    setAfterScore(null);
    setAfterPerception(null);
    setSimulationDone(false);
    setIsSimulating(false);
  }, []);

  const runPreAnalyze = useCallback(async () => {
    if (!photo) return;
    setPreAnalysis(null);
    try {
      const modeMap: Record<CategoryId, string> = { social: 'social', cv: 'cv', dating: 'dating' };
      const res = await api.preAnalyze(photo.file, modeMap[activeCategory]);
      setPreAnalysis(res);
    } catch (e) {
      setError(e instanceof api.ApiError ? e.body : 'Pre-analyze failed');
    }
  }, [photo, activeCategory]);

  const startSimulation = useCallback(() => {
    setIsSimulating(true);
    setSimulationDone(false);
    if (simTimerRef.current) clearTimeout(simTimerRef.current);
    simTimerRef.current = setTimeout(() => {
      setIsSimulating(false);
      setSimulationDone(true);
    }, 5000);
  }, []);

  useEffect(() => () => { if (simTimerRef.current) clearTimeout(simTimerRef.current); }, []);

  const authenticateUser = useCallback(async (email: string) => {
    localStorage.setItem(EMAIL_KEY, email);
    try {
      const res = await login();
      setSession({ token: res.session_token, userId: res.user_id, usage: res.usage });
      const b = await api.getBalance();
      setBalance(b.image_credits);
      setIsAuthenticated(true);
    } catch (e) {
      throw e;
    }
  }, []);

  const loginWithOAuth = useCallback(async (provider: 'yandex' | 'vk-id') => {
    await startOAuth(provider);
  }, []);

  const loginWithToken = useCallback(async (token: string) => {
    api.setToken(token);
    try {
      const b = await api.getBalance();
      setBalance(b.image_credits);
    } catch { /* balance may not be available yet */ }
    const usage = await api.getUsage().catch(() => ({
      daily_limit: 3, used: 0, remaining: 3, is_premium: false,
    }));
    setSession({ token, userId: '', usage });
    setIsAuthenticated(true);
  }, []);

  useEffect(() => {
    const saved = restoreToken();
    if (saved) {
      loginWithToken(saved).catch(() => { /* token expired */ });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // After auth, auto-run real pre-analyze
  const prevAuthRef = useRef(false);
  useEffect(() => {
    if (isAuthenticated && !prevAuthRef.current && photo) {
      runPreAnalyze();
    }
    prevAuthRef.current = isAuthenticated;
  }, [isAuthenticated, photo, runPreAnalyze]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
  }, []);

  const startPolling = useCallback((taskId: string) => {
    stopPolling();
    pollingRef.current = setInterval(async () => {
      try {
        const t = await api.getTask(taskId);
        setCurrentTask({ taskId: t.task_id, status: t.status, result: t.result });
        if (t.status === 'completed') {
          stopPolling();
          setIsGenerating(false);
          const r = t.result as Record<string, unknown> | null;
          if (r) {
            const imgUrl = (r.generated_image_url ?? r.image_url ?? '') as string;
            if (imgUrl) setGeneratedImageUrl(imgUrl);
            const score = (r.dating_score ?? r.social_score ?? r.score ?? null) as number | null;
            if (score != null) setAfterScore(score);
            const ps = r.perception_scores as Record<string, number> | undefined;
            if (ps) setAfterPerception(ps);
          }
          refreshBalance();
        } else if (t.status === 'failed') {
          stopPolling();
          setIsGenerating(false);
          setError(t.error_message ?? 'Generation failed');
        }
      } catch { /* retry on next tick */ }
    }, 2000);
  }, [stopPolling, refreshBalance]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const generate = useCallback(async () => {
    if (!photo || !selectedStyleKey) return;
    if (balance <= 0) {
      setError('Недостаточно кредитов. Пополните баланс в разделе Тарифы.');
      return;
    }
    setIsGenerating(true);
    setError(null);
    setGeneratedImageUrl(null);
    setAfterScore(null);
    setAfterPerception(null);
    try {
      const modeMap: Record<CategoryId, string> = { social: 'social', cv: 'cv', dating: 'dating' };
      const res = await api.analyze(
        photo.file,
        modeMap[activeCategory],
        selectedStyleKey,
        preAnalysis?.pre_analysis_id,
      );
      setCurrentTask({ taskId: res.task_id, status: res.status, result: null });
      startPolling(res.task_id);
    } catch (e) {
      setIsGenerating(false);
      setError(e instanceof api.ApiError ? e.body : 'Generation failed');
    }
  }, [photo, selectedStyleKey, balance, activeCategory, preAnalysis, startPolling]);

  const share = useCallback(async () => {
    if (!currentTask?.taskId) return null;
    try {
      return await api.createShare(currentTask.taskId);
    } catch {
      return null;
    }
  }, [currentTask]);

  const clearError = useCallback(() => setError(null), []);

  const value: AppState & AppActions = {
    session, balance, photo, preAnalysis, activeCategory, selectedStyleKey,
    currentTask, isGenerating, error, generatedImageUrl, afterScore, afterPerception,
    isAuthenticated, isSimulating, simulationDone,
    setActiveCategory, setSelectedStyleKey, uploadPhoto, runPreAnalyze,
    generate, share, refreshBalance, clearError, startSimulation, authenticateUser,
    loginWithOAuth, loginWithToken,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
