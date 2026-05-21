// Variant B (CMS hub on Railway) — every API request goes to the
// primary backend. The legacy multi-target switcher (1.55.0) is gone
// because the RU edge no longer exposes admin writes; CMS edits
// reach RU via signed replication, so the SPA only ever needs the
// Railway base URL plus the optional ``market`` query param.
import i18next from 'i18next';
import {
  getAdminTarget,
  tokenStorageKey,
  type AdminTargetId,
} from './admin-targets';

function _hydrateToken(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem(tokenStorageKey('primary'));
}

let _token: string | null = _hydrateToken();

/** Backwards-compat shim: callers that imported these used to flip
 *  between primary and RU; now both resolve to ``primary``. */
export function getActiveAdminTarget(): AdminTargetId {
  return 'primary';
}

export function setActiveAdminTarget(_id: AdminTargetId): void {
  // No-op — only ``primary`` exists in Variant B.
}

/** Resolve the API base URL. ``target`` arg kept for compatibility
 *  with pre-Variant-B callers; only ``primary`` is meaningful. */
export function getApiBase(target: AdminTargetId = 'primary'): string {
  return getAdminTarget(target).apiBase;
}

/** Legacy export — preserved so existing imports compile. */
export const API_BASE = getApiBase('primary');

export function setToken(t: string | null): void {
  setTokenForTarget('primary', t);
}

export function getToken(): string | null {
  return _token;
}

export function setTokenForTarget(_id: AdminTargetId, t: string | null): void {
  _token = t;
  if (typeof localStorage === 'undefined') return;
  try {
    if (t) {
      localStorage.setItem(tokenStorageKey('primary'), t);
    } else {
      localStorage.removeItem(tokenStorageKey('primary'));
    }
  } catch { /* fine */ }
}

export function getTokenForTarget(_id: AdminTargetId): string | null {
  return _token;
}

export interface AdminRequestOptions {
  /** Variant B leftover — the only meaningful value is ``primary``.
   *  Kept so existing call-sites do not need a sweep. */
  target?: AdminTargetId;
}

async function request<T>(
  path: string,
  init: RequestInit & AdminRequestOptions = {},
): Promise<T> {
  const { target: _ignored, ...fetchInit } = init as RequestInit & AdminRequestOptions;
  const apiBase = getAdminTarget('primary').apiBase;
  const token = _token;

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

export type LandingMarket = 'ru' | 'global';

export interface AdminLandingPagesList {
  market: LandingMarket;
  slugs: string[];
}

export interface AdminLandingMarketsResponse {
  markets: LandingMarket[];
  default: LandingMarket;
  cms_role: 'editor' | 'follower';
}

export interface AdminLandingPageResponse {
  market: LandingMarket;
  slug: string;
  page: Record<string, unknown>;
}

function _marketQuery(market?: LandingMarket): string {
  return market ? `?market=${market}` : '';
}

export function listAdminLandingMarkets() {
  return request<AdminLandingMarketsResponse>('/api/v1/admin/landing/markets');
}

export function listAdminLandingPages(market?: LandingMarket) {
  return request<AdminLandingPagesList>(
    `/api/v1/admin/landing/pages${_marketQuery(market)}`,
  );
}

export function getAdminLandingPage(slug: string, market?: LandingMarket) {
  return request<AdminLandingPageResponse>(
    `/api/v1/admin/landing/pages/${encodeURIComponent(slug)}${_marketQuery(market)}`,
  );
}

export function putAdminLandingPage(
  slug: string,
  page: Record<string, unknown>,
  market?: LandingMarket,
) {
  return request<{ status: string; market: LandingMarket; slug: string }>(
    `/api/v1/admin/landing/pages/${encodeURIComponent(slug)}${_marketQuery(market)}`,
    { method: 'PUT', body: JSON.stringify({ page }) },
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

export function oauthInit(
  provider: 'yandex' | 'vk-id' | 'google',
  deviceId: string,
  linkCode?: string,
  returnPath?: string,
) {
  return request<OAuthInitResponse>(`/api/v1/auth/${provider}/init`, {
    method: 'POST',
    body: JSON.stringify({
      device_id: deviceId,
      link_code: linkCode || '',
      return_path: returnPath || '',
    }),
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
  /** Face area divided by image area (0..1). Powers style × reference
   * compatibility heuristics on the client. */
  face_area_ratio?: number;
  /** Composition Safety Layer — one of
   * ``face_closeup`` / ``portrait`` / ``half_body`` / ``full_body`` /
   * ``unknown``. ``unknown`` triggers the fail-closed-safe policy
   * (portrait-only framings, full-body styles hidden). */
  composition_class?: string;
  /** Framings the user may safely pick given the upload's composition.
   * Defaults to ``['portrait']`` on older backends that don't report
   * the CSL fields yet. */
  allowed_framings?: string[];
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

/**
 * v1.72 — product-tier pill that replaces the раздельный выбор модели
 * (Nano Banana 2 vs GPT Image 2) на «Стандарт / Премиум». Стандарт
 * — это `gpt_image_2 + medium` (1 credit). Премиум — тот же базовый
 * рендер, но с Clarity refiner post-pass (2 credits, ~$0.10/img на
 * стороне FAL). Если кнопка премиум выбрана, бэк жёстко прибивает
 * `image_model=gpt_image_2` и игнорирует `imageModel`, чтобы платный
 * апгрейд не съезжал на Nano Banana по ошибке (см.
 * `src/services/analysis_request.py::apply_ab_test_context_fields`).
 */
export type AbProductTier = 'standard' | 'premium';

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
  /**
   * v1.72: продуктовый tier «standard / premium». Если не задан —
   * бэк интерпретирует запрос как ``standard`` (1 кредит). Premium
   * автоматически добавляет Clarity refiner и резервирует 2 кредита.
   */
  tier?: AbProductTier;
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
  /**
   * Composition Safety Layer override — when true, the wizard's
   * "Advanced settings" toggle asked the server to skip the
   * framing / style hard-stop. The server still requires
   * ``settings.composition_safety_advanced_override=True`` on the
   * deployment, so a client cannot bypass CSL on its own.
   */
  skipCompositionSafety?: boolean;
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
  if (options.skipCompositionSafety) {
    fd.append('skip_composition_safety', 'true');
  }
  fd.append('image_model', options.imageModel ?? 'gpt_image_2');
  fd.append('image_quality', options.imageQuality ?? 'low');
  if (options.tier) fd.append('tier', options.tier);
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
  /** Composition Safety Layer — style requires a visible torso + legs
   * (beach, yoga, running, etc.). Locked from the picker when the
   * upload's ``composition_class`` is FACE_CLOSEUP / PORTRAIT /
   * UNKNOWN. */
  needs_full_body?: boolean;
  /** Composition Safety Layer — style requires a visible torso /
   * shoulders (luxury suit, boardroom, formal portrait). Soft-warned
   * on tight head-crop uploads but still selectable. */
  needs_torso?: boolean;
}

export interface CatalogStylesResponse {
  mode: string;
  count: number;
  styles: CatalogStyleEntry[];
  schema: 'v1' | 'v2';
}

/**
 * 1.59.0 — i18n localisation for catalog responses.
 *
 * The backend `/api/v1/catalog/styles` endpoint returns Russian
 * ``label`` and ``hook`` strings (the master copy lives in
 * ``data/styles.json``). On the global build we want the English
 * versions from ``web/src/locales/en/styles.json`` instead, with the
 * server payload acting as a fallback for keys that do not have a
 * translation yet. This helper performs the lookup; both
 * ``getCatalogStyles`` and ``getScenarioStyles`` route their results
 * through it.
 *
 * The i18n bundle is shaped as
 * ``styles:<category>.<style_key>.{name,desc}``. ``category`` is the
 * style's mode for the regular catalog (``dating`` / ``cv`` /
 * ``social`` / ``model`` / ``brand`` / ``memes``). Document and visa
 * styles live under the ``documents`` namespace regardless of the
 * scenario they belong to, so the helper falls through both
 * candidates and the legacy ``items.<key>`` shape.
 */
const STYLE_FALLBACK_CATEGORIES = ['documents', 'dating', 'cv', 'social', 'model', 'brand', 'memes'];

function _lookupStyleString(category: string | undefined, key: string, field: 'name' | 'desc'): string | null {
  const candidates: string[] = [];
  if (category) candidates.push(`styles:${category}.${key}.${field}`);
  for (const cat of STYLE_FALLBACK_CATEGORIES) {
    if (cat !== category) candidates.push(`styles:${cat}.${key}.${field}`);
  }
  for (const path of candidates) {
    if (i18next.exists(path)) {
      const v = i18next.t(path);
      if (typeof v === 'string' && v.trim()) return v;
    }
  }
  return null;
}

// 1.59.1 — preserve the leading emoji from the original (RU) label.
//
// Translations in `web/src/locales/en/styles.json` are pure text
// without emojis — but `AppContext.tsx` extracts the wizard icon by
// matching a leading emoji in `style.label`. If we just swapped the
// label, the EN catalog ended up with the ✨ fallback for every
// style. We now lift the emoji from the original payload (which
// always carries the RU master copy from `data/styles.json`) and
// prepend it to the translated text so the icon stays per-style on
// both builds.
export function _extractLeadingEmoji(text: string): string {
  return text.match(/^[\p{Emoji}\u200d]+\s*/u)?.[0] ?? '';
}

export function localizeApiStyle<T extends { key: string; label: string; hook: string }>(
  entry: T,
  category?: string,
): T {
  const localizedLabel = _lookupStyleString(category, entry.key, 'name');
  const localizedHook = _lookupStyleString(category, entry.key, 'desc');
  let nextLabel = entry.label;
  if (localizedLabel) {
    const leadingEmoji = _extractLeadingEmoji(entry.label);
    nextLabel = `${leadingEmoji}${localizedLabel}`;
  }
  return {
    ...entry,
    label: nextLabel,
    hook: localizedHook ?? entry.hook,
  };
}

export async function getCatalogStyles(mode: string): Promise<CatalogStylesResponse> {
  const res = await request<CatalogStylesResponse>(
    `/api/v1/catalog/styles?mode=${mode}&schema=v2`,
  );
  return { ...res, styles: res.styles.map((s) => localizeApiStyle(s, mode)) };
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

export async function getScenarioStyles(
  scenarioSlug: string,
): Promise<ScenarioStylesResponse> {
  const res = await request<ScenarioStylesResponse>(
    `/api/v1/catalog/scenario-styles?scenario=${encodeURIComponent(scenarioSlug)}&schema=v2`,
  );
  // Each entry carries its own ``mode``; pass it as the category hint
  // so document-photo styles read from ``styles:documents.*`` and
  // dating styles read from ``styles:dating.*``.
  return { ...res, styles: res.styles.map((s) => localizeApiStyle(s, s.mode)) };
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

export function createPayment(packQty: number) {
  return request<{ payment_id: string; confirmation_url: string }>('/api/v1/payments/create', {
    method: 'POST',
    body: JSON.stringify({ pack_qty: packQty }),
  });
}

/** Normalize payment creation errors for alerts/toasts. */
function _tr(key: string, fallback: string): string {
  if (i18next.isInitialized && i18next.exists(key, { ns: 'errors' })) {
    return i18next.t(key, { ns: 'errors' });
  }
  return fallback;
}

export function handleCreatePaymentError(e: unknown): string {
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

// Phone OTP API was removed from the web client because the backend
// only logs OTP codes (no SMS provider).  The /auth/phone/* endpoints
// remain on the API behind ``PHONE_AUTH_ENABLED=false`` (returns 503),
// ready to be re-wired once an SMS provider is integrated.
