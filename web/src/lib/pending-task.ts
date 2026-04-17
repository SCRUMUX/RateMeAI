export interface PendingTaskState {
  taskId: string;
  apiMode: string;
  category: string;
  scenarioSlug?: string;
  startedAt: number;
}

const PENDING_TASK_KEY = 'ailook_pending_task';

function isPendingTaskState(value: unknown): value is PendingTaskState {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.taskId === 'string'
    && typeof candidate.apiMode === 'string'
    && typeof candidate.category === 'string'
    && typeof candidate.startedAt === 'number'
  );
}

export function rememberPendingTask(state: PendingTaskState): void {
  try {
    sessionStorage.setItem(PENDING_TASK_KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

export function peekPendingTask(): PendingTaskState | null {
  try {
    const raw = sessionStorage.getItem(PENDING_TASK_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isPendingTaskState(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function hasPendingTask(): boolean {
  return peekPendingTask() !== null;
}

export function clearPendingTask(expectedTaskId?: string): void {
  try {
    const current = peekPendingTask();
    if (!expectedTaskId || current?.taskId === expectedTaskId) {
      sessionStorage.removeItem(PENDING_TASK_KEY);
    }
  } catch {
    /* ignore */
  }
}

const LAST_ERROR_KEY = 'ailook_last_generation_error';

export interface LastGenerationError {
  taskId: string;
  message: string;
  at: number;
}

export function rememberLastGenerationError(taskId: string, message: string): void {
  try {
    sessionStorage.setItem(LAST_ERROR_KEY, JSON.stringify({
      taskId,
      message,
      at: Date.now(),
    } as LastGenerationError));
  } catch {
    /* ignore */
  }
}

export function peekLastGenerationError(): LastGenerationError | null {
  try {
    const raw = sessionStorage.getItem(LAST_ERROR_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<LastGenerationError>;
    if (
      parsed && typeof parsed === 'object'
      && typeof parsed.taskId === 'string'
      && typeof parsed.message === 'string'
      && typeof parsed.at === 'number'
    ) {
      return parsed as LastGenerationError;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function clearLastGenerationError(): void {
  try {
    sessionStorage.removeItem(LAST_ERROR_KEY);
  } catch {
    /* ignore */
  }
}
