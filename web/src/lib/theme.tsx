/**
 * Theme switcher.
 *
 * Минимальный ThemeProvider, который пишет ``data-theme`` на
 * ``<html>``. Дефолт — пользовательский localStorage, далее
 * ``prefers-color-scheme``, далее dark.
 *
 * FOUC prevention делается inline-script-ом в ``index.html`` — этот
 * хук синхронизирует React-state с уже выставленным DOM-атрибутом.
 *
 * Полный sweep хардкодов под токены и переключаемые glass-токены
 * сделан в Theme System Overhaul 1.34.0 → 1.34.2. Светлая и тёмная
 * темы используют общий дизайн-токен набор (см. ``design-tokens.css``,
 * ``index.css`` и AICADS spec ``AICADS-/packages/core/ai-ds-styles.json``).
 *
 * 1.34.2: подписка на ``storage`` event для sync между вкладками —
 * если пользователь переключает тему в одной вкладке, остальные
 * автоматически отражают изменение.
 */
import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'theme';

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readInitialTheme(): Theme {
  if (typeof document === 'undefined') return 'dark';
  const dom = document.documentElement.dataset.theme;
  if (dom === 'light' || dom === 'dark') return dom;
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  }
  if (typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: light)').matches) {
    return 'light';
  }
  return 'dark';
}

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => readInitialTheme());

  useEffect(() => {
    if (typeof document === 'undefined') return;
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* ignore quota / disabled storage */
    }
  }, [theme]);

  // 1.34.2: cross-tab sync. If the user switches theme in another tab,
  // the storage event fires here with the new value — we update React
  // state, which in turn re-applies the data-theme attribute via the
  // effect above. Skip if newValue is null (storage cleared).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY) return;
      if (e.newValue === 'dark' || e.newValue === 'light') {
        setThemeState(e.newValue);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const value: ThemeContextValue = {
    theme,
    setTheme: setThemeState,
    toggle: () => setThemeState((prev) => (prev === 'dark' ? 'light' : 'dark')),
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within <ThemeProvider>');
  }
  return ctx;
}
