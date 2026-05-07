// 1.55.0 — multi-target admin. The SPA can talk to multiple FastAPI
// instances (primary / RU edge); see ``./admin-targets.ts``.
//
// 1.55.1 hotfix: routing was originally done off ``_activeTarget``
// for ALL traffic, including OAuth init, ``/users/me`` and SSE
// progress. That broke the public flow whenever an operator left
// the admin switcher on RU — Google OAuth would suddenly redirect
// to ``ru.ailookstudio.ru/auth/callback`` (often unregistered →
// "redirect_uri_mismatch"), and image URLs would resolve against
// the wrong host. Per-target routing is now path-scoped: only
// ``/api/v1/admin/*`` paths follow the switcher, everything else
// goes to ``primary`` regardless of UI state.
import i18next from 'i18next';
import {
  ACTIVE_TARGET_STORAGE_KEY,
  getAdminTarget,
  tokenStorageKey,
  type AdminTargetId,
} from './admin-targets';

function _hydrateActiveTarget(): AdminTargetId {
  if (typeof localStorage === 'undefined') return 'primary';
  const raw = localStorage.getItem(ACTIVE_TARGET_STORAGE_KEY);
  if (raw === 'ru' || raw === 'primary') return raw;
  return 'primary';
}

function _hydrateTokens(): Record<AdminTargetId, string | null> {
  const out: Record<AdminTargetId, string | null> = {
    primary: null,
    ru: null,
  };
  if (typeof localStorage === 'undefined') return out;
  // ``tokenStorageKey('primary')`` resolves to the legacy key
  // ``ailook_session_token``, so this picks up tokens written by
  // both the public OAuth flow (auth.ts) and admin login.
  out.primary = localStorage.getItem(tokenStorageKey('primary'));
  out.ru = localStorage.getItem(tokenStorageKey('ru'));
  return out;
}

let _activeTarget: AdminTargetId = _hydrateActiveTarget();
const _tokens: Record<AdminTargetId, string | null> = _hydrateTokens();

export function getActiveAdminTarget(): AdminTargetId {
  return _activeTarget;
}

export function setActiveAdminTarget(id: AdminTargetId): void {
  _activeTarget = id;
  if (typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(ACTIVE_TARGET_STORAGE_KEY, id);
    } catch { /* fine */ }
  }
}

/** Resolve the API base URL for a given target. ``getApiBase()``
 *  without arguments returns the primary base — that's the value
 *  used by SSE / image-url helpers and any non-admin code path. */
export function getApiBase(target: AdminTargetId = 'primary'): string {
  return getAdminTarget(target).apiBase;
}

/** Legacy export — kept so consumers that imported the constant
 *  before 1.55 still compile. ALWAYS resolves to primary so
 *  non-admin features (SSE, image URLs) can't be broken by the
 *  admin target switcher. */
export const API_BASE = getApiBase('primary');

/** Public token setter used by the cabinet OAuth flow. Always
 *  writes to the primary slot — non-admin code never targets RU. */
export function setToken(t: string | null): void {
  setTokenForTarget('primary', t);
}

/** Public token getter — returns the primary token. Admin code
 *  that needs the active-target token uses ``getTokenForTarget``. */
export function getToken(): string | null {
  return _tokens.primary;
}

export function setTokenForTarget(id: AdminTargetId, t: string | null): void {
  _tokens[id] = t;
  if (typeof localStorage === 'undefined') return;
  try {
    if (t) {
      localStorage.setItem(tokenStorageKey(id), t);
    } else {
      localStorage.removeItem(tokenStorageKey(id));
    }
  } catch { /* fine */ }
}

export function getTokenForTarget(id: AdminTargetId): string | null {
  const direct = _tokens[id];
  if (direct) return direct;
  // 1.55.5 — same-origin fallback. On the RU edge SPA build,
  // ``VITE_API_BASE_URL`` and ``VITE_ADMIN_TARGET_RU_URL`` both point
  // at ``https://ru.ailookstudio.ru``, so ``primary`` and ``ru``
  // resolve to the SAME backend. The OAuth flow always writes to the
  // primary slot (legacy ``ailook_session_token``); without this
  // fallback, switching the target dropdown to RU on the RU build
  // would leave ``hasToken`` false and the page would show
  // "Нужен вход на target «RU»" forever even though the operator IS
  // logged in and the token IS valid for the requested apiBase.
  // Fallback rule: if the requested target shares apiBase with
  // primary (i.e. same backend), reuse the primary token. Targets on
  // a different origin (the Vercel build, where primary = Railway
  // and ru = ru.ailookstudio.ru) keep strict per-target isolation —
  // a primary Railway token is NOT valid against the RU backend.
  if (id !== 'primary') {
    try {
      const primaryBase = getAdminTarget('primary').apiBase;
      const targetBase = getAdminTarget(id).apiBase;
      if (primaryBase && targetBase && primaryBase === targetBase) {
        return _tokens.primary;
      }
    } catch { /* unknown target — bail to null */ }
  }
  return null;
}

const ADMIN_PATH_PREFIX = '/api/v1/admin/';

function _isAdminPath(path: string): boolean {
  return path.startsWith(ADMIN_PATH_PREFIX);
}

export interface AdminRequestOptions {
  /** Override the routing target for this single call. Used by the
   *  CMS "Применить на оба сервера" button so a write to RU doesn't
   *  require globally switching targets. */
  target?: AdminTargetId;
}

async function request<T>(
  path: string,
  init: RequestInit & AdminRequestOptions = {},
): Promise<T> {
  const { target, ...fetchInit } = init as RequestInit & AdminRequestOptions;
  // Path-scoped target selection: admin endpoints follow the
  // operator's chosen target, everything else stays on primary so
  // OAuth/SSE/cabinet keep working regardless of admin UI state.
  let targetId: AdminTargetId;
  if (target) {
    targetId = target;
  } else if (_isAdminPath(path)) {
    targetId = _activeTarget;
  } else {
    targetId = 'primary';
  }
  const apiBase = getAdminTarget(targetId).apiBase;
  // 1.55.5 — use ``getTokenForTarget`` so the same-origin fallback
  // (RU build: primary===ru) actually attaches the Authorization
  // header when the operator routes admin traffic via target=ru.
  const token = getTokenForTarget(targetId);

  const headers = new Headers(fetchInit.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (!headers.has('Content-Type') && !(fetchInit.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${apiBase}${path}`, { ...fetchInit, headers });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail: unknown = text;
    let body: string = text;
    try {
      const json = JSON.parse(text);
      detail = json.detail ?? json.message ?? json;
      body = typeof detail === 'string' ? detail : JSON.stringify(detail);
    } catch { /* not JSON — keep raw text */ }

    // Global block detector. Backend signals a soft-blocked account by
    // responding 403 with detail = { code: "account_blocked", reason }.
    // We dispatch a CustomEvent that App.tsx listens for to render the
    // full-screen "Аккаунт заблокирован" overlay — no per-component
    // try/catch needed.
    if (
      res.status === 403
      && typeof detail === 'object'
      && detail !== null
      && (detail as { code?: unknown }).code === 'account_blocked'
    ) {
      const reason = (detail as { reason?: unknown }).reason;
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
        window.dispatchEvent(
          new CustomEvent('account-blocked', {
            detail: { reason: typeof reason === 'string' ? reason : '' },
          }),
        );
      }
    }
    throw new ApiError(res.status, body, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: string,
    public detail?: unknown,
  ) {
    super(`API ${status}: ${body.slice(0, 200)}`);
  }
}

// -- Landing CMS (public) --

export interface LandingPageResponse {
  slug: string;
  page: Record<string, unknown>;
}

export function getLandingPage(slug: string) {
  return request<LandingPageResponse>(`/api/v1/landing/pages/${encodeURIComponent(slug)}`);
}

// -- Scenarios (public registry) --
//
// Phase 2 scenario engine: SPA used to keep a hardcoded list in
// ``web/src/scenarios/config.ts``. The list is still the source of
// truth for routing/wizard wiring (it ships before the build can
// reach the API), but flags like ``enabled``, ``output_spec`` and
// ``paywall.pack_qty`` are now sourced from this endpoint with the
// hardcoded entry as a fallback. Visa scenarios live ONLY in the API
// payload — they never need a code change to come online.

export interface ApiScenarioPaywall {
  pack_qty: number;
  show_paywall: boolean;
}

export interface ApiScenarioOutputSpec {
  size_mm: [number, number] | null;
  dpi: number;
  background_color: string;
  head_height_mm: [number, number] | null;
  aspect_key: string | null;
}

export interface ApiScenarioAnalysisDisplay {
  mode: 'score' | 'approval_probability';
  success_probability_after_pct: number | null;
  label_key: string | null;
}

export interface ApiScenario {
  slug: string;
  kind: 'core' | 'document' | 'visa';
  api_mode: 'rating' | 'dating' | 'cv' | 'social' | 'emoji';
  pipeline_profile: 'simple' | 'advanced';
  step3_mode: 'styles' | 'document_formats';
  landing_slug: string | null;
  enabled: boolean;
  paywall: ApiScenarioPaywall | null;
  output_spec: ApiScenarioOutputSpec | null;
  analysis_display?: ApiScenarioAnalysisDisplay | null;
}

export interface ScenariosListResponse {
  scenarios: ApiScenario[];
  count: number;
}

export interface ScenarioGetResponse {
  scenario: ApiScenario;
}

export interface ScenarioComplianceResponse {
  slug: string;
  kind: string;
  checklist: VisaComplianceItem[];
  output_spec: ApiScenarioOutputSpec | null;
}

export function listScenarios() {
  return request<ScenariosListResponse>('/api/v1/scenarios');
}

export function getScenarioPublic(slug: string) {
  return request<ScenarioGetResponse>(
    `/api/v1/scenarios/${encodeURIComponent(slug)}`,
  );
}

export function getScenarioCompliance(slug: string) {
  return request<ScenarioComplianceResponse>(
    `/api/v1/scenarios/${encodeURIComponent(slug)}/compliance`,
  );
}

// -- Landing CMS (admin) --

export interface AdminLandingPagesList {
  slugs: string[];
}

export function listAdminLandingPages(opts: AdminRequestOptions = {}) {
  return request<AdminLandingPagesList>('/api/v1/admin/landing/pages', opts);
}

export function getAdminLandingPage(slug: string, opts: AdminRequestOptions = {}) {
  return request<LandingPageResponse>(
    `/api/v1/admin/landing/pages/${encodeURIComponent(slug)}`,
    opts,
  );
}

export function putAdminLandingPage(
  slug: string,
  page: Record<string, unknown>,
  opts: AdminRequestOptions = {},
) {
  return request<{ status: string; slug: string }>(
    `/api/v1/admin/landing/pages/${encodeURIComponent(slug)}`,
    { ...opts, method: 'PUT', body: JSON.stringify({ page }) },
  );
}

export interface ConsentState {
  required: string[];
  granted: Record<string, { version: string; granted_at: string; source: string }>;
  missing: string[];
  current_version: string;
}

export function getConsents() {
  return request<ConsentState>('/api/v1/users/me/consents');
}

export function grantConsents(kinds: string[], source = 'web') {
  return request<ConsentState>('/api/v1/users/me/consents', {
    method: 'POST',
    body: JSON.stringify({ kinds, source }),
  });
}

export function revokeConsents(kinds: string[]) {
  return request<ConsentState>('/api/v1/users/me/consents/revoke', {
    method: 'POST',
    body: JSON.stringify({ kinds }),
  });
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

export interface InputQualityIssue {
  code: string;
  severity: 'block' | 'warn';
  message: string;
  suggestion: string;
}

export interface InputQualityPublic {
  can_generate: boolean;
  soft_warnings: InputQualityIssue[];
  blocking_issues: InputQualityIssue[];
}

export interface VisaComplianceItem {
  rule: string;
  status: 'pending' | 'passed' | 'warn' | 'failed' | string;
}

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
  input_quality?: InputQualityPublic | null;
  approval_probability?: number | null;
  visa_compliance?: VisaComplianceItem[] | null;
  analysis_display_mode?: string | null;
}

export function preAnalyze(image: File, mode: string, scenarioSlug?: string | null) {
  const fd = new FormData();
  fd.append('image', image);
  fd.append('mode', mode);
  if (scenarioSlug) fd.append('scenario_slug', scenarioSlug);
  return request<PreAnalysisResponse>('/api/v1/pre-analyze', { method: 'POST', body: fd });
}

// -- Analyze --

export interface TaskCreated {
  task_id: string;
  status: string;
  estimated_seconds: number;
}

export type AbImageModel = 'nano_banana_2' | 'gpt_image_2';
export type AbImageQuality = 'low' | 'medium' | 'high';

export interface AnalyzeOptions {
  preAnalysisId?: string;
  enhancementLevel?: number;
  scenarioSlug?: string;
  scenarioType?: string;
  entryMode?: string;
  /** v1.22: A/B путь стал дефолтным. Если не задано — бэк подставит ``gpt_image_2``. */
  imageModel?: AbImageModel;
  /** v1.22: tier качества. Если не задано — бэк подставит ``low``. */
  imageQuality?: AbImageQuality;
  framing?: string;
  inputHints?: Record<string, any>;
  /**
   * Stage 3 of the prompt-pipeline-overhaul (2026-05) — optional seed
   * for the v3 slot sampler. ``undefined`` means "fresh roll"; the UI
   * supplies a freshly randomised int when the user clicks
   * «Другой вариант» so the same `(style, hints, seed)` triple does
   * not get rolled again on a regen.
   */
  seed?: number;
}

export function analyze(
  image: File,
  mode: string,
  style: string,
  options: AnalyzeOptions = {},
) {
  const fd = new FormData();
  fd.append('image', image);
  fd.append('mode', mode);
  fd.append('style', style);
  if (options.preAnalysisId) fd.append('pre_analysis_id', options.preAnalysisId);
  if (options.enhancementLevel != null) fd.append('enhancement_level', String(options.enhancementLevel));
  if (options.scenarioSlug) fd.append('scenario_slug', options.scenarioSlug);
  if (options.scenarioType) fd.append('scenario_type', options.scenarioType);
  if (options.entryMode) fd.append('entry_mode', options.entryMode);
  if (options.framing) fd.append('framing', options.framing);
  if (options.inputHints) fd.append('input_hints', JSON.stringify(options.inputHints));
  if (options.seed != null && Number.isFinite(options.seed)) {
    fd.append('seed', String(Math.trunc(options.seed)));
  }
  fd.append('image_model', options.imageModel ?? 'gpt_image_2');
  fd.append('image_quality', options.imageQuality ?? 'low');
  return request<TaskCreated>('/api/v1/analyze', { method: 'POST', body: fd });
}

// -- Task --

// v1.27.3: shape we actually rely on in the result body. The field is
// still typed as the loose ``Record<string, unknown>`` below for
// historic compatibility, but consumers can use
// ``readGenerationWarnings`` to extract the post-generation notices.
export interface TaskResultBody extends Record<string, unknown> {
  generation_warnings?: string[];
}

export function readGenerationWarnings(
  result: Record<string, unknown> | null | undefined,
): string[] {
  if (!result) return [];
  const raw = (result as TaskResultBody).generation_warnings;
  if (!Array.isArray(raw)) return [];
  return raw.filter((s): s is string => typeof s === 'string' && s.length > 0);
}

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

/**
 * prompt-pipeline-overhaul (May 2026): the v3 slot sampler rolls
 * trigger / lighting / weather / time_of_day / season / clothing per
 * generation. The backend whitelists these keys before exposing
 * them, so missing-or-unrecognised channels simply do not appear in
 * the record. Treat ``undefined`` as "channel was not rolled" (e.g.
 * a v1/v2 generation in pre-overhaul history).
 */
export type ResolvedSlots = Partial<{
  trigger: string;
  scene: string;
  lighting: string;
  weather: string;
  time_of_day: string;
  season: string;
  clothing: string;
  expression: string;
  random_picks: Record<string, string>;
  user_overrides: Record<string, string>;
  substitutions: Array<{ channel: string; requested: string; applied: string }>;
}>;

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
  purged?: boolean;
  /** Absent for pre-v3 history rows. */
  resolved_slots?: ResolvedSlots | null;
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
//
// All catalog endpoints use ?schema=v2 — backend keeps a v1 default for
// older clients, but the Cabinet web app is now exclusively on the
// slot-based view (StylesSheet groups, StyleSettingsModal options).

export interface CatalogStyleEntry {
  key: string;
  label: string;
  hook: string;
  meta: Record<string, unknown>;
  unlock_after_generations: number;
  schema_version: 1 | 2;
}

export interface CatalogStylesResponse {
  mode: string;
  count: number;
  styles: CatalogStyleEntry[];
  schema: 'v1' | 'v2';
}

export function getCatalogStyles(mode: string) {
  return request<CatalogStylesResponse>(`/api/v1/catalog/styles?mode=${mode}&schema=v2`);
}

// Styles that live behind a specific scenario page (e.g. /dokumenty,
// /tinder-pack). The backend filters them out of the main mode catalog
// so they don't pollute the regular wizard, and serves them through
// /api/v1/catalog/scenario-styles?scenario=<slug>.

export interface ScenarioStyleEntry extends CatalogStyleEntry {
  mode: string;
}

export interface ScenarioStylesResponse {
  scenario: string;
  count: number;
  styles: ScenarioStyleEntry[];
  schema: 'v1' | 'v2';
}

export function getScenarioStyles(scenarioSlug: string) {
  return request<ScenarioStylesResponse>(
    `/api/v1/catalog/scenario-styles?scenario=${encodeURIComponent(scenarioSlug)}&schema=v2`,
  );
}

// v2 slot payload returned by /api/v1/catalog/styles/{id}/options?schema=v2
// Keep aligned with src/services/style_catalog._v2_slots_from_raw().

export interface StyleOptionsV2Payload {
  schema_version: 2;
  trigger: string;
  context_slots: Partial<{
    lighting: string[];
    framing: string[];
    time_of_day: string[];
    season: string[];
  }> & Record<string, string[]>;
  weather: { enabled: boolean; allowed: string[]; default_na: boolean };
  clothing: { default: string; allowed: string[]; gender_neutral: boolean };
  background: { base: string; lock: 'unlocked' | 'soft' | 'locked'; overrides_allowed: string[] };
}

// v3 slot payload (prompt-pipeline-overhaul, 2026-05) returned by
// /api/v1/catalog/styles/{id}/options?schema=v3. Mirrors
// src/services/style_catalog._v3_slots_from_raw().
//
// Diff vs v2:
// - ``trigger`` (string) → ``trigger_pool`` (list of equivalent
//   formulations). The slot sampler picks one per generation; the user
//   cannot disable the channel — it is the immutable headline motif.
// - ``context_slots`` (lighting / framing / time / season) flattened
//   into ``ambient`` (lighting / weather / time_of_day / season).
//   ``framing`` lives at the top level because it is structural.
// - ``background`` (base + overrides_allowed) collapsed into
//   ``scene_anchor`` (the dry, light/weather-free baseline) plus
//   ``scene_overrides`` (alternative anchors the user may pin).

export interface StyleOptionsV3Payload {
  schema_version: 3;
  trigger_pool: string[];
  scene_anchor: string;
  scene_overrides: string[];
  background_lock: 'unlocked' | 'semi' | 'locked';
  ambient: {
    lighting: string[];
    weather: string[];
    time_of_day: string[];
    season: string[];
  };
  clothing: { default: string; allowed: string[]; gender_neutral: boolean };
  framing: string[];
  expression: string;
  /**
   * 1.29.0 — explicit list of channels the operator wants surfaced
   * to the user. When non-empty the modal hides every channel that
   * is NOT in this list, and the SlotSampler skips them. When empty
   * the un-curated heuristic kicks in (channel visible iff its pool
   * is non-empty) — keeps backwards compatibility with 1.28.
   *
   * Allowed entries: ``"lighting"`` | ``"weather"`` |
   * ``"time_of_day"`` | ``"season"`` | ``"framing"`` |
   * ``"clothing"`` | ``"scene_override"``.
   */
  available_channels: string[];
  /**
   * 1.29.0 — coarse-grained classifier (``"indoor"`` / ``"outdoor"`` /
   * ``"mixed"`` / ``"document"``) used by the admin lint engine.
   * Empty string = unclassified.
   */
  location_type: string;
}

export interface StyleOptionsV1Payload {
  schema_version: 1;
  // Legacy allowed_variations dict (lighting / scene / clothing / framing).
  [key: string]: unknown;
}

export interface StyleOptionsResponse {
  style_id: string;
  schema_version: 1 | 2 | 3;
  options: StyleOptionsV3Payload | StyleOptionsV2Payload | Record<string, string[]>;
}

// Stage 3 of the prompt-pipeline-overhaul (2026-05): the modal asks
// for v3 first; the catalog endpoint downgrades to v2/v1 transparently
// when a style hasn't been migrated yet (impossible right now — every
// row is v3 — but kept for forward compatibility with admin imports).
export function getStyleOptions(styleId: string) {
  return request<StyleOptionsResponse>(`/api/v1/catalog/styles/${styleId}/options?schema=v3`);
}

// -- SSE Ticket --

export interface SseTicketResponse { ticket: string; ttl: number }

export function createSseTicket() {
  return request<SseTicketResponse>('/api/v1/sse/ticket', { method: 'POST' });
}

// -- Payments --

/**
 * Публичный URL российской витрины, где живёт платёжный контур (ЮKassa).
 * Оплата обрабатывается ТОЛЬКО этим сервером, потому что ЮKassa принимает
 * вебхуки исключительно с российских IP. На основном домене эндпоинт
 * /api/v1/payments/create возвращает 410 (payments_disabled_on_primary).
 */
export const RU_PAYMENTS_SITE_URL = 'https://ru.ailookstudio.ru';

export function createPayment(packQty: number) {
  return request<{ payment_id: string; confirmation_url: string }>('/api/v1/payments/create', {
    method: 'POST',
    body: JSON.stringify({ pack_qty: packQty }),
  });
}

/**
 * Нормализует ошибку создания платежа в человекочитаемое сообщение.
 * Если сервер вернул 410 (primary без YooKassa), редиректим на RU-домен
 * вместо alert — пользователь сразу попадает туда, где реально можно
 * оплатить, без загадочных «Ошибка создания платежа».
 */
function _tr(key: string, fallback: string): string {
  if (i18next.isInitialized && i18next.exists(key, { ns: 'errors' })) {
    return i18next.t(key, { ns: 'errors' });
  }
  return fallback;
}

export function handleCreatePaymentError(e: unknown): string {
  if (e instanceof ApiError && e.status === 410) {
    try {
      const returnUrl = `${RU_PAYMENTS_SITE_URL}/#тарифы`;
      window.location.href = returnUrl;
    } catch {
      /* fall through */
    }
    return _tr(
      'payment.redirect_ru',
      'Оплата принимается только через ru.ailookstudio.ru — перенаправляем…',
    );
  }
  return _tr('payment.create_failed', 'Не удалось создать платёж. Попробуй ещё раз.');
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

// -- Admin (style catalog CRUD) --
//
// Gated server-side by ADMIN_USER_IDS — non-admin sessions get a plain
// 403. The admin web page does not pre-flight that check; it just calls
// listAdminStyles() and shows the error if the request 403s.

export interface AdminStyleSummary {
  id: string;
  mode: string;
  display_label: string;
  hook_text: string;
  scenario: string | null;
  unlock_after_generations: number;
  is_scenario_only: boolean;
  schema_version: number;
}

export type AdminStyleEntry = Record<string, unknown> & {
  id: string;
  mode: string;
};

export function listAdminStyles(opts: AdminRequestOptions = {}) {
  return request<AdminStyleSummary[]>('/api/v1/admin/styles', opts);
}

export function getAdminStyle(styleId: string, opts: AdminRequestOptions = {}) {
  return request<AdminStyleEntry>(
    `/api/v1/admin/styles/${encodeURIComponent(styleId)}`,
    opts,
  );
}

export function createAdminStyle(
  payload: AdminStyleEntry,
  opts: AdminRequestOptions = {},
) {
  return request<AdminStyleEntry>('/api/v1/admin/styles', {
    ...opts,
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateAdminStyle(
  styleId: string,
  patch: Partial<AdminStyleEntry>,
  opts: AdminRequestOptions = {},
) {
  return request<AdminStyleEntry>(
    `/api/v1/admin/styles/${encodeURIComponent(styleId)}`,
    { ...opts, method: 'PUT', body: JSON.stringify(patch) },
  );
}

export function deleteAdminStyle(
  styleId: string,
  opts: AdminRequestOptions = {},
) {
  return request<void>(
    `/api/v1/admin/styles/${encodeURIComponent(styleId)}`,
    { ...opts, method: 'DELETE' },
  );
}

export function reloadAdminStyles(opts: AdminRequestOptions = {}) {
  return request<{ status: string; count: number }>(
    '/api/v1/admin/styles/reload',
    { ...opts, method: 'POST' },
  );
}

// -- Admin: lint + conflict report (1.29.0) --
//
// The lint engine surfaces structured issues for the editor inline
// warnings; the conflict scanner powers the dedicated
// /admin/conflicts page. Both endpoints are read-only and gated by
// ADMIN_USER_IDS the same way as the CRUD surface above.

export interface AdminLintIssue {
  code: string;
  severity: 'error' | 'warning';
  message: string;
  field: string;
  detail: Record<string, unknown>;
}

export type AdminLintReport = Record<string, AdminLintIssue[]>;

export interface AdminDuplicateLabel {
  label: string;
  normalised: string;
  ids: string[];
}

export interface AdminSimilarLabel {
  id_a: string;
  id_b: string;
  label_a: string;
  label_b: string;
  distance: number;
}

export interface AdminConflictReport {
  duplicate_labels: AdminDuplicateLabel[];
  similar_labels: AdminSimilarLabel[];
  duplicate_ids: string[];
}

export function lintAllAdminStyles() {
  return request<AdminLintReport>('/api/v1/admin/styles/lint');
}

export function lintOneAdminStyle(styleId: string) {
  return request<AdminLintIssue[]>(
    `/api/v1/admin/styles/${encodeURIComponent(styleId)}/lint`,
  );
}

export function listAdminStyleConflicts() {
  return request<AdminConflictReport>('/api/v1/admin/styles/conflicts');
}

// ---------------------------------------------------------------------------
// Admin: diagnostic ping (1.55.4). Authenticated but NOT admin-gated.
// Tells the caller why they would (or wouldn't) pass require_admin on
// the currently-selected target. Used by AdminLayout to render an
// actionable banner instead of a silent 403 page.
// ---------------------------------------------------------------------------

export interface AdminWhoamiResponse {
  user_id: string;
  is_admin: boolean;
  matched_via: 'user_id' | 'email' | null;
  identity_emails: string[];
  whitelist_size: { user_ids: number; emails: number };
  deployment_mode: string;
  market_id: string;
  git: string | null;
}

export function adminWhoami(opts: AdminRequestOptions = {}) {
  return request<AdminWhoamiResponse>('/api/v1/admin/_whoami', opts);
}

// ---------------------------------------------------------------------------
// Admin: Users tab — list/inspect users, adjust credits, ledger refunds.
// All endpoints gated by require_admin (UUID or email whitelist). Photo
// paths are intentionally never returned from the backend.
// ---------------------------------------------------------------------------

export interface AdminUserSummary {
  id: string;
  telegram_id: number | null;
  username: string | null;
  first_name: string | null;
  is_premium: boolean;
  image_credits: number;
  created_at: string | null;
  providers: string[];
  emails: string[];
  primary_email: string | null;
  total_generations: number;
  last_task_at: string | null;
  last_seen: string | null;
  blocked_at: string | null;
  blocked_reason: string | null;
  blocked_by: string | null;
}

export interface AdminUserListResponse {
  items: AdminUserSummary[];
  count: number;
  query: string;
  limit: number;
}

export interface AdminUserIdentity {
  provider: string;
  external_id: string;
  email?: string | null;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  created_at?: string | null;
}

export interface AdminUserTransaction {
  id: number;
  amount: number;
  balance_after: number;
  tx_type: string;
  payment_id: string | null;
  created_at: string | null;
}

export interface AdminUserTask {
  id: string;
  mode: string;
  status: string;
  created_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

export interface AdminUserDetailResponse {
  user: AdminUserSummary;
  identities: AdminUserIdentity[];
  transactions: AdminUserTransaction[];
  tasks: AdminUserTask[];
}

export interface AdminCreditAdjustResponse {
  status: string;
  tx_type: 'admin_grant' | 'admin_debit';
  before: number;
  after: number;
  amount: number;
  transaction_id: number;
}

export interface AdminRefundResponse {
  status: string;
  tx_type: 'admin_refund';
  before: number;
  after: number;
  credits: number;
  transaction_id: number;
}

export function listAdminUsers(params: { q?: string; limit?: number } = {}) {
  const search = new URLSearchParams();
  if (params.q) search.set('q', params.q);
  if (params.limit) search.set('limit', String(params.limit));
  const qs = search.toString();
  return request<AdminUserListResponse>(
    `/api/v1/admin/users${qs ? `?${qs}` : ''}`,
  );
}

export function getAdminUser(userId: string) {
  return request<AdminUserDetailResponse>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}`,
  );
}

export function adminAdjustCredits(
  userId: string,
  body: { amount: number; reason: string },
) {
  return request<AdminCreditAdjustResponse>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/credits`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}

export function adminRefund(
  userId: string,
  body: { credits: number; payment_id?: string; note: string },
) {
  return request<AdminRefundResponse>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/refund`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}

export interface AdminBlockResponse {
  status: string;
  blocked_at: string | null;
  blocked_reason: string | null;
  blocked_by: string | null;
}

export function adminBlockUser(userId: string, reason: string) {
  return request<AdminBlockResponse>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/block`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
    },
  );
}

export function adminUnblockUser(userId: string) {
  return request<{ status: string; blocked_at: null }>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/unblock`,
    { method: 'POST' },
  );
}

export interface AdminDeleteResponse {
  deleted: boolean;
  artefacts: {
    tasks: number;
    generated_files: number;
    share_cards: number;
    consents: number;
    identities: number;
    perception_records: number;
  };
}

export function adminDeleteUser(userId: string) {
  return request<AdminDeleteResponse>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}`,
    { method: 'DELETE' },
  );
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
