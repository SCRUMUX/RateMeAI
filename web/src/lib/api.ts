export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL ?? '').trim();

let _token: string | null = null;

export function setToken(t: string | null) { _token = t; }
export function getToken() { return _token; }

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (_token) headers.set('Authorization', `Bearer ${_token}`);
  if (!headers.has('Content-Type') && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail = text;
    try {
      const json = JSON.parse(text);
      detail = json.detail ?? json.message ?? text;
    } catch { /* not JSON — keep raw text */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, public body: string) {
    super(`API ${status}: ${body.slice(0, 200)}`);
  }
}

// -- Auth --

export interface ChannelAuthResponse {
  session_token: string;
  user_id: string;
  usage: { daily_limit: number; used: number; remaining: number; is_premium: boolean };
}

export function authWeb(deviceId: string) {
  return request<ChannelAuthResponse>('/api/v1/auth/web', {
    method: 'POST',
    body: JSON.stringify({ device_id: deviceId }),
  });
}

export interface OAuthInitResponse {
  authorize_url: string;
}

export function oauthInit(provider: 'yandex' | 'vk-id' | 'google', deviceId: string, linkCode?: string) {
  return request<OAuthInitResponse>(`/api/v1/auth/${provider}/init`, {
    method: 'POST',
    body: JSON.stringify({ device_id: deviceId, link_code: linkCode || '' }),
  });
}

// -- Balance --

export interface BalanceResponse { user_id: string; image_credits: number }

export function getBalance() {
  return request<BalanceResponse>('/api/v1/payments/balance');
}

// -- Usage --

export function getUsage() {
  return request<ChannelAuthResponse['usage']>('/api/v1/users/me/usage');
}

// -- Pre-analyze --

export interface PreAnalysisResponse {
  pre_analysis_id: string;
  mode: string;
  first_impression: string;
  score: number;
  perception_scores: Record<string, number>;
  perception_insights: Array<{
    parameter: string;
    current_level: string;
    suggestion: string;
    controllable_by: string;
  }>;
  enhancement_opportunities: string[];
}

export function preAnalyze(image: File, mode: string) {
  const fd = new FormData();
  fd.append('image', image);
  fd.append('mode', mode);
  return request<PreAnalysisResponse>('/api/v1/pre-analyze', { method: 'POST', body: fd });
}

// -- Analyze --

export interface TaskCreated {
  task_id: string;
  status: string;
  estimated_seconds: number;
}

export function analyze(
  image: File,
  mode: string,
  style: string,
  preAnalysisId?: string,
  enhancementLevel?: number,
  scenarioSlug?: string,
  scenarioType?: string,
  entryMode?: string,
) {
  const fd = new FormData();
  fd.append('image', image);
  fd.append('mode', mode);
  fd.append('style', style);
  if (preAnalysisId) fd.append('pre_analysis_id', preAnalysisId);
  if (enhancementLevel != null) fd.append('enhancement_level', String(enhancementLevel));
  if (scenarioSlug) fd.append('scenario_slug', scenarioSlug);
  if (scenarioType) fd.append('scenario_type', scenarioType);
  if (entryMode) fd.append('entry_mode', entryMode);
  return request<TaskCreated>('/api/v1/analyze', { method: 'POST', body: fd });
}

// -- Task --

export interface TaskResponse {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  mode: string;
  created_at: string;
  completed_at: string | null;
  result: Record<string, unknown> | null;
  share_card_url: string | null;
  error_message: string | null;
}

export function getTask(taskId: string) {
  return request<TaskResponse>(`/api/v1/tasks/${taskId}`);
}

// -- Task History (Storage) --

export interface TaskHistoryItem {
  task_id: string;
  mode: string;
  style: string;
  completed_at: string | null;
  input_image_url: string;
  generated_image_url: string;
  score_before: number | null;
  score_after: number | null;
  perception_scores: Record<string, number> | null;
}

export interface TaskHistoryResponse {
  items: TaskHistoryItem[];
  total_count: number;
}

export function getTaskHistory(limit = 20, offset = 0) {
  return request<TaskHistoryResponse>(`/api/v1/tasks?limit=${limit}&offset=${offset}`);
}

export interface RefundResponse { status: string; balance: number }

export function refundTask(taskId: string) {
  return request<RefundResponse>(`/api/v1/tasks/${taskId}/refund`, { method: 'POST' });
}

// -- Share --

export interface ShareResponse { image_url: string; caption: string; deep_link: string }

export function createShare(taskId: string) {
  return request<ShareResponse>(`/api/v1/share/${taskId}?channel=web`, { method: 'POST' });
}

// -- Catalog --

// TODO: Replace static styles.ts with dynamic catalog when backend catalog is finalized.
// export function getCatalogStyles(mode: string) {
//   return request<{ mode: string; count: number; styles: Array<{ key: string; label: string; hook: string; meta: Record<string, unknown> }> }>(
//     `/api/v1/catalog/styles?mode=${mode}`,
//   );
// }

// -- SSE Ticket --

export interface SseTicketResponse { ticket: string; ttl: number }

export function createSseTicket() {
  return request<SseTicketResponse>('/api/v1/sse/ticket', { method: 'POST' });
}

// -- Payments --

export function createPayment(packQty: number) {
  return request<{ payment_id: string; confirmation_url: string }>('/api/v1/payments/create', {
    method: 'POST',
    body: JSON.stringify({ pack_qty: packQty }),
  });
}

// -- Identity Linking --

export interface LinkedIdentity {
  provider: string;
  external_id: string;
  profile_data: Record<string, string | null> | null;
  created_at: string | null;
}

export interface UserIdentitiesResponse {
  user_id: string;
  identities: LinkedIdentity[];
}

export function getMyIdentities() {
  return request<UserIdentitiesResponse>('/api/v1/users/me/identities');
}

// -- Universal Link Token --

export interface LinkTokenResponse {
  code: string;
  ttl: number;
  link_url: string;
}

export function createLinkToken() {
  return request<LinkTokenResponse>('/api/v1/auth/link-token', { method: 'POST' });
}

export interface ClaimLinkResponse {
  session_token: string;
  user_id: string;
  usage: ChannelAuthResponse['usage'];
  identities: LinkedIdentity[];
}

export function claimLink(code: string, provider: string, externalId: string, profileData?: Record<string, string>) {
  return request<ClaimLinkResponse>('/api/v1/auth/claim-link', {
    method: 'POST',
    body: JSON.stringify({ code, provider, external_id: externalId, profile_data: profileData }),
  });
}

// -- Phone OTP --

export function phoneSendCode(phone: string) {
  return request<{ sent: boolean; phone: string; ttl: number }>('/api/v1/auth/phone/send-code', {
    method: 'POST',
    body: JSON.stringify({ phone }),
  });
}

export function phoneVerify(phone: string, code: string, linkCode?: string) {
  return request<ChannelAuthResponse>('/api/v1/auth/phone/verify', {
    method: 'POST',
    body: JSON.stringify({ phone, code, link_code: linkCode || '' }),
  });
}
