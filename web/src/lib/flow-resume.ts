import {
  consumePostPaymentReturnPath,
  getPostPaymentReturnPath,
  setPostPaymentReturnPath,
} from '../scenarios/config';

const RETURN_STEP_KEY = 'returnToStep';
const OAUTH_RETURN_KEY = 'ailook_return_after_oauth';

export type FlowStep = 'upload' | 'analysis' | 'style' | 'generate';

export function rememberFlowStep(step: FlowStep): void {
  try {
    localStorage.setItem(RETURN_STEP_KEY, step);
  } catch {
    /* ignore */
  }
}

export function peekFlowStep(): FlowStep | null {
  try {
    const raw = localStorage.getItem(RETURN_STEP_KEY);
    if (raw === 'upload' || raw === 'analysis' || raw === 'style' || raw === 'generate') {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function consumeFlowStep(): FlowStep | null {
  try {
    const value = peekFlowStep();
    if (value) {
      localStorage.removeItem(RETURN_STEP_KEY);
    }
    return value;
  } catch {
    return null;
  }
}

export function clearFlowStep(expected?: FlowStep): void {
  try {
    const current = localStorage.getItem(RETURN_STEP_KEY);
    if (!expected || current === expected) {
      localStorage.removeItem(RETURN_STEP_KEY);
    }
  } catch {
    /* ignore */
  }
}

export function hasFlowStep(): boolean {
  return peekFlowStep() !== null;
}

export function rememberFlowReturnPath(path: string): void {
  setPostPaymentReturnPath(path);
}

export function getFlowReturnPath(): string | null {
  return getPostPaymentReturnPath();
}

export function consumeFlowReturnPath(fallback = '/app'): string {
  return consumePostPaymentReturnPath() || fallback;
}

export function rememberOAuthReturnPath(path: string): void {
  if (!path) return;
  try {
    sessionStorage.setItem(OAUTH_RETURN_KEY, path);
  } catch {
    /* ignore */
  }
}

export function consumeOAuthReturnPath(fallback = '/'): string {
  try {
    const raw = sessionStorage.getItem(OAUTH_RETURN_KEY);
    if (raw) {
      sessionStorage.removeItem(OAUTH_RETURN_KEY);
      return raw;
    }
  } catch {
    /* ignore */
  }
  return fallback;
}
