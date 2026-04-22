# ARCHITECTURE — RateMeAI (v1.9.x)

Технический справочник рабочей архитектуры платформы AI Look Studio (RateMeAI).
Версия документа актуальна для кодовой базы **v1.9.2+**.

---

## 1. Обзор системы

RateMeAI — платформа AI-стилиста, которая анализирует фото пользователя и генерирует улучшенные образы для разных жизненных контекстов (знакомства, карьера, соцсети). Состоит из **Python-бэкенда** (FastAPI + ARQ + aiogram) и **React SPA** (Vite).

### Процессы

| Процесс | Технология | Назначение |
|---------|-----------|------------|
| **app** | FastAPI + Uvicorn | HTTP API, SSE, статика `/storage/` |
| **worker** | ARQ (Redis queue) | Фоновая обработка задач (LLM + генерация изображений) |
| **bot** | aiogram 3 + aiohttp | Telegram-бот (webhook или polling) |
| **postgres** | PostgreSQL 16 | Основная БД |
| **redis** | Redis 7 | Очередь задач, кеш сессий, pub/sub прогресса, кеш изображений |
| **web** | Vite + React (SPA) | Веб-интерфейс (Vercel / nginx) |

### Взаимодействие процессов

```
Telegram User ──> Bot ──HTTP──> App (API)
                                  │
Web User ──────────────────────> App (API)
                                  │
                          ┌───────┴───────┐
                          │  PostgreSQL    │
                          │  Redis        │
                          └───────┬───────┘
                                  │
                          Worker (ARQ)
                            │       │
                      OpenRouter   Reve/Replicate
                       (LLM)      (Image Gen)
```

---

## 2. Схема развертывания

### Primary (Railway)

- **app** — `uvicorn src.main:app --host 0.0.0.0 --port 8000`
- **worker** — `arq src.workers.tasks.WorkerSettings`
- **bot** — `python -m src.bot.app`
- **PostgreSQL** — Railway managed (internal URL)
- **Redis** — Railway managed (internal URL)

### Frontend (Vercel)

- SPA из `web/dist`, конфиг `vercel.json` (framework: vite, SPA rewrite на `/index.html`)
- Build: `cd web && npx vite build`
- Env var: `VITE_API_BASE_URL` указывает на Railway API

### RU Edge (VPS + Docker)

- `DEPLOYMENT_MODE=edge` — API проксирует AI-задачи на primary через `RemoteAIService`
- `docker-compose.ru.yml`: postgres, redis, app (edge), nginx (SSL + static frontend)
- Frontend собирается в Docker (`web/Dockerfile`), статика копируется в volume `ratemeai_web_dist`
- Домен: `ru.ailookstudio.ru`

### Инварианты деплоя

- app, worker, bot **всегда** деплоятся из одного коммита (одного Docker-образа)
- Версия в `src/version.py` — обязательно инкрементировать при каждом деплое
- `GET /health` возвращает `version` и опциональный `git` SHA (`DEPLOY_GIT_SHA`)
- Alembic миграции выполняются автоматически при старте в production (`src/main.py` lifespan)

---

## 3. Модель данных

ORM: SQLAlchemy 2 (async) + asyncpg. Миграции: Alembic (`alembic/versions/`).

### Таблицы

```
┌──────────────────────┐     ┌────────────────────────┐
│ users                │     │ user_identities        │
│──────────────────────│     │────────────────────────│
│ id (UUID PK)         │◄────│ user_id (FK)           │
│ telegram_id (unique) │     │ provider (varchar 20)  │
│ username             │     │ external_id (varchar)  │
│ first_name           │     │ profile_data (JSON)    │
│ is_premium (bool)    │     │ UQ(provider,external_id)│
│ image_credits (int)  │     └────────────────────────┘
│ created_at           │
└──────┬───────────────┘
       │
       ├──── tasks
       │     │ id (UUID PK), user_id (FK)
       │     │ mode, status, input_image_path
       │     │ context (JSON), result (JSON)
       │     │ share_card_path, error_message
       │     │ created_at, updated_at, completed_at
       │
       ├──── usage_logs
       │     │ user_id + usage_date (UQ), count
       │
       ├──── credit_transactions
       │     │ amount, balance_after, tx_type, payment_id
       │
       ├──── api_clients
       │     │ name, key_hash (unique), rate_limit_daily, is_active
       │
       └──── user_perception_records
             │ user_id + mode + style (UQ)
             │ warmth, presence, appeal, authenticity
```

### Статусы задач (`TaskStatus`)

`pending` → `processing` → `completed` | `failed`

### Режимы анализа (`AnalysisMode`)

`rating`, `dating`, `cv`, `social`, `emoji`

---

## 4. API Reference

Все эндпоинты монтируются с префиксом `/api/v1` (файл `src/api/router.py`).

### Аутентификация

Два механизма (проверяются в `src/api/deps.py` → `get_auth_user`):
1. **Bearer token** — `Authorization: Bearer <session_token>` → Redis `ratemeai:session:{token}` → UUID пользователя
2. **API Key** — `X-API-Key` → SHA256(key + pepper) → `api_clients.key_hash` → пользователь

### Анализ и задачи

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/analyze` | Bearer/API | Multipart: image + mode + style + enhancement_level + pre_analysis_id. Резервирует 1 кредит, создает Task, ставит в ARQ. Возвращает 202 + task_id |
| POST | `/pre-analyze` | Bearer/API | Multipart pre-analysis (dating/cv/social). LLM-анализ без генерации. Кеш в Redis |
| GET | `/tasks` | Bearer/API | Галерея завершенных задач (пагинация) |
| GET | `/tasks/{task_id}` | Bearer/API | Детали задачи + result JSON |
| POST | `/tasks/{task_id}/refund` | Bearer/API | Возврат кредита если сгенерированное изображение недоступно |
| POST | `/share/{task_id}` | Bearer/API | Share payload: caption, deep link, image URL |

### Auth эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/auth/telegram` | Telegram WebApp init_data verification / bot registration |
| POST | `/auth/ok` | Odnoklassniki Mini App signature verification |
| POST | `/auth/vk` | VK Mini App launch params verification |
| POST | `/auth/web` | Anonymous web auth по device_id |
| POST | `/auth/yandex/init` | Yandex OAuth — возвращает authorize URL |
| GET | `/auth/yandex/callback` | Yandex OAuth callback → session → redirect на web |
| POST | `/auth/vk-id/init` | VK ID OAuth (PKCE) init |
| GET | `/auth/vk-id/callback` | VK ID callback → session → redirect |
| POST | `/auth/phone/send-code` | OTP код в Redis |
| POST | `/auth/phone/verify` | Проверка OTP → session |
| POST | `/auth/link-token` | Создать 6-символьный код привязки (authenticated) |
| POST | `/auth/claim-link` | Привязать аккаунт по коду |
| POST | `/auth/api-client` | Admin: создать B2B API key (X-Admin-Secret) |

### Пользователь и платежи

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/users/me/usage` | Bearer | Usage + credits |
| GET | `/users/me/identities` | Bearer | Связанные identity |
| POST | `/payments/create` | Bearer | Создать платеж YooKassa (pack_qty) |
| POST | `/payments/yookassa/webhook` | - | Webhook payment.succeeded → зачисление кредитов |
| GET | `/payments/balance` | Bearer | Текущий баланс кредитов |

### Каталог, engagement, SSE

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/catalog/modes` | - | Доступные режимы анализа |
| GET | `/catalog/styles?mode=` | - | Каталог стилей для режима |
| GET | `/engagement/matrix` | - | Матрица стилей (статистика) |
| GET | `/engagement/depth/me` | Bearer | Engagement depth пользователя |
| GET | `/sse/progress?task_id=&token=` | - | SSE: прогресс и завершение задачи |

### Internal API (edge → primary)

Доступны только когда `DEPLOYMENT_MODE=primary`. Auth: `X-Internal-Key`.

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/internal/ping` | Health check |
| POST | `/internal/process-analysis` | Принять задачу от edge (base64 image) |
| GET | `/internal/task/{task_id}/status` | Статус + optional generated_image_b64 |
| POST | `/internal/pre-analyze` | Pre-analysis для edge |

### Корневые маршруты (main.py)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/storage/{file_path}` | Файлы из локального хранилища + Redis/DB fallback для generated JPEG |
| GET | `/health` | Liveness: status, version, git SHA |
| GET | `/readiness` | DB + Redis check, edge: primary reachability |
| GET | `/metrics` | Prometheus (защищен в prod) |

---

## 5. Система аутентификации

### Multi-provider Identity

Единая модель: `User` (основная сущность) + `UserIdentity` (привязки к платформам).

```
User (id=UUID)
  ├── UserIdentity(provider="telegram", external_id="123456")
  ├── UserIdentity(provider="vk", external_id="789")
  ├── UserIdentity(provider="web", external_id="device-xxx")
  └── UserIdentity(provider="yandex", external_id="yandex-uid")
```

**Поддерживаемые провайдеры:** `telegram`, `ok`, `vk`, `web`, `yandex`, `vk_id`, `phone`

### Сессии

- `create_session(redis, user_id)` → `secrets.token_urlsafe(48)` → Redis `ratemeai:session:{token}` с TTL (`SESSION_TTL_SECONDS`)
- Каждый auth-эндпоинт при успехе вызывает `create_session` и возвращает `session_token`

### Cross-platform linking

1. Authenticated пользователь вызывает `POST /auth/link-token` → 6-символьный код (Redis TTL 5 мин)
2. На другой платформе: OAuth/phone с параметром `link_code` → `_find_or_create_by_identity(link_to_user=...)` → identity добавляется к существующему пользователю

### Bot auth

`UserRegistrationMiddleware` (aiogram):
- При каждом сообщении/callback проверяет `_registered` set (in-memory per process)
- Если user_id не зарегистрирован: `POST /api/v1/auth/telegram` → сохраняет `session_token` в Redis как `bot_session:{telegram_id}`
- Последующие API-вызовы бота используют этот Bearer token

---

## 6. Analysis Pipeline

Основной пайплайн обработки фото. Точка входа: ARQ job `process_analysis` в `src/workers/tasks.py`.

### Общая схема

```
Worker получает task_id
    │
    ▼
Загрузка изображения (Redis cache → Storage fallback)
    │
    ▼
AnalysisPipeline.execute()
    │
    ├── 1. Preprocess (validate, normalize, face heuristic)
    │
    ├── 2. LLM Analysis
    │   ├── Redis pre-analysis cache (если pre_analysis_id)
    │   └── ModeRouter → Service.analyze() → consensus_analyze()
    │       └── OpenRouter vision API (JSON response_format)
    │
    ├── 3. Humanize scores + warnings
    │
    ├── 4. Image Generation (если есть кредиты и mode ∈ {cv, emoji, dating, social})
    │   └── ImageGenerationExecutor.single_pass()
    │       ├── PromptEngine.build_image_prompt() → edit-mode prompt
    │       ├── provider.generate() (Reve /v1/image/edit с reference_image)
    │       ├── Local postprocess (crop_to_aspect, upscale_lanczos, inject_exif_only)
    │       ├── Identity presence check (MediaPipe) + global QualityGates
    │       └── Storage upload → generated_image_url
    │
    │   (Multi-pass / per-region planning зарезервированы в
    │    src/orchestrator/advanced/ и в рантайм не подключены —
    │    см. docs/architecture/reserved.md)
    │
    ├── 5. Delta Scoring (dating/cv/social с generated image)
    │   └── DeltaScorer.compute()
    │       ├── Download generated → re-analyze via ModeRouter
    │       ├── Compute delta (post_score - pre_score)
    │       └── Compute perception_delta + authenticity
    │
    └── 6. Finalize
        ├── Share card (rating mode → ShareCardGenerator)
        ├── Persist perception records (DB gamification)
        └── ResultMerger.merge() (share metadata)
    │
    ▼
Worker persists: task.result, task.status=COMPLETED
    │
    ├── Redis: stage generated image (gen_image_cache_key)
    ├── Redis pub/sub: ratemeai:task_done:{task_id}
    ├── Usage log upsert
    └── Credit deduction/refund
```

### Ключевые компоненты

#### `src/orchestrator/pipeline.py` — `AnalysisPipeline`

Главный оркестратор single-pass рантайма. Конструирует `ModeRouter`, `ImageGenerationExecutor`, `DeltaScorer`, `ResultMerger`, `ShareCardGenerator`. Метод `execute()` реализует полную цепочку. Lazy-инициализация: `IdentityService` (MediaPipe face-presence), `QualityGateRunner`. Multi-pass планировщик, `ModelRouter` и `SegmentationService` намеренно не инициализируются — они зарезервированы в `src.orchestrator.advanced` (см. `docs/architecture/reserved.md`).

#### `src/orchestrator/router.py` — `ModeRouter`

Маршрутизация `AnalysisMode` → сервис:
- RATING → `RatingService`
- DATING → `DatingService`
- CV → `CVService`
- SOCIAL → `SocialService`
- EMOJI → `EmojiService`

Каждый сервис принимает `LLMProvider` + `PromptEngine`.

#### `src/orchestrator/advanced/` — Reserved (multi-pass)

`PipelinePlanner`, `AdvancedPipelineExecutor`, `ModelRouter`, `EnhancementLevel` / `level_for_depth` живут в `src/orchestrator/advanced/` и **не** подключены к активному рантайму. Это задел под premium HD retouch, compliance-loop для документов, N-variant генерацию и capability-based провайдерский роутинг (FLUX vs Reve). Активация — через Scenario Engine (Phase 2). Полная карта — `docs/architecture/reserved.md`.

#### `src/orchestrator/executor.py` — `ImageGenerationExecutor`

Один активный режим:
- **`single_pass()`** — единственный путь в рантайме: `PromptEngine.build_image_prompt()` → `provider.generate()` (edit-mode) → локальный postprocess (crop/upscale/EXIF) → identity presence check → global quality gates.

Мульти-пасс (`AdvancedPipelineExecutor.execute_plan`) живёт в `src/orchestrator/advanced/execute_plan.py` и в класс `ImageGenerationExecutor` не проброшен.

#### `src/orchestrator/executor.py` — `DeltaScorer`

Post-gen re-scoring: скачивает сгенерированное изображение, повторно анализирует через `ModeRouter.get_service`, вычисляет `delta` (per-metric: pre/post/delta), `perception_delta`, authenticity score. Результат мержится в `task.result`.

#### `src/orchestrator/merger.py` — `ResultMerger`

Добавляет share metadata (card_url, caption, deep_link) в финальный result dict.

#### `src/services/identity.py` — `IdentityService`

InsightFace ArcFace (`buffalo_l`): `compute_embedding`, `compare` (cosine similarity), `verify(original, generated)`, `detect_face`. Используется в pipeline для identity gating.

#### `src/services/quality_gates.py` — `QualityGateRunner`

Per-step и global gates: face_similarity (via IdentityService), NIQE score, batched LLM quality JSON (aesthetic, artifacts, photorealism). Результат: `GateResult` с pass/fail и метриками.

---

## 7. Провайдеры

### LLM — `src/providers/llm/openrouter.py`

`OpenRouterLLM`: Vision API через OpenRouter (`/chat/completions`).
- `analyze_image()` — base64 JPEG + system prompt → JSON response
- `generate_text()` — text-only completion
- Model: настраивается через `OPENROUTER_MODEL` (default: Gemini via OpenRouter)
- Retries: tenacity на HTTP ошибки

### Image Generation — `src/providers/image_gen/`

| Провайдер | Класс | Статус | Режимы |
|-----------|-------|--------|--------|
| **Reve** | `ReveImageGen` | Активный | Только `/v1/image/edit` c `reference_image` + instruction. Кроп под aspect ratio и LANCZOS-апскейл делаются локально в `src/services/postprocess.py`. |
| **Replicate** | `ReplicateImageGen` | Reserved | Upload → prediction API → poll → download. Выключен в рантайме (`IMAGE_GEN_PROVIDER=reve`). База под FLUX/FAL, см. `docs/architecture/reserved.md`. |
| **Chain** | `ChainImageGen` | Reserved | Fallback-обёртка (первый успешный результат). Вернётся через Scenario Engine (`Scenario.preferred_provider_hint`). |
| **Mock** | `MockImageGen` | Dev/test | Возвращает reference без изменений. Живёт в `src/providers/_testing/`. |

**Factory** (`src/providers/factory.py` → `get_image_gen()`):
- `IMAGE_GEN_PROVIDER=auto` → Reve напрямую (Replicate временно отключён), иначе fallback Mock в dev / ошибка в prod
- `IMAGE_GEN_PROVIDER=reve|replicate|mock` → конкретный провайдер

### Storage — `src/providers/storage/`

| Провайдер | Когда | Детали |
|-----------|-------|--------|
| `LocalStorageProvider` | `STORAGE_PROVIDER=local` (default) | Файлы на диске (`STORAGE_LOCAL_PATH`), URL через `API_BASE_URL/storage/...`. HTTP fallback для worker (`STORAGE_HTTP_FALLBACK_BASE`) |
| `S3StorageProvider` | `STORAGE_PROVIDER=s3` | aioboto3, presigned URLs, optional `S3_PUBLIC_BASE_URL` для CDN |

**Пути хранения:**
- Входные: `inputs/{user_id}/{uuid}.jpg`
- Сгенерированные: `generated/{user_id}/{task_id}.jpg`

---

## 8. Telegram Bot

Отдельный процесс (`python -m src.bot.app`). Aiogram 3 + aiohttp health server.

### Middleware

`UserRegistrationMiddleware` — перехватывает все messages/callbacks:
1. Регистрирует пользователя через `POST /api/v1/auth/telegram`
2. Кеширует Bearer token в Redis (`bot_session:{telegram_id}`)
3. Инжектирует `redis`, `api_base_url`, `api_user` в handler data

### Handlers

| Файл | Обработчики |
|------|------------|
| `start.py` | `/start` (welcome + referral), `/emoji`, `/rating`, `/balance` |
| `photo.py` | Входящее фото/документ → сохраняет file_id в Redis |
| `mode_select.py` | Выбор режима → pre-analyze → выбор стиля → `POST /analyze` → poll задачи → deliver |
| `results.py` | `deliver_result()` — форматирование и отправка результата по режимам (photo + markdown + keyboards) |
| `link.py` | Привязка аккаунтов: создание кода, ввод кода, claim |
| `fallback.py` | Catch-all для неопознанных сообщений |

### Keyboards

`src/bot/keyboards.py`: scenario_keyboard (режимы), style_keyboard (пагинация стилей), post_result_keyboard (share + restyle), upgrade_keyboard (пакеты кредитов), link_wizard_keyboard.

### Polling задач

`mode_select._poll_task()`:
1. Подписка на Redis `ratemeai:task_done:{task_id}` и progress channel
2. Одновременно HTTP poll `GET /tasks/{task_id}` каждые 2-3 секунды
3. При завершении → `results.deliver_result()`

---

## 9. Web Frontend

Vite + React SPA в `web/`. Пакет: `@ailook/web`.

### Стек

- **React 18** + **React Router 6** (BrowserRouter)
- **Tailwind CSS 3** (glass design system, категорийные темы через `data-category`)
- **Framer Motion** (анимации переходов)
- **Vite** (dev server port 3000, proxy `/api` и `/storage` → localhost:8000)

### Маршруты

| Путь | Компонент | Назначение |
|------|-----------|-----------|
| `/` | `Landing` | Marketing: hero, how-it-works, simulation, pricing |
| `/app` | `AppPage` | Основной wizard: 4 шага |
| `/payment-success` | `PaymentSuccess` | После оплаты — refresh balance |
| `/auth/callback` | `AuthCallback` | OAuth return → token → navigate |
| `/link` | `LinkPage` | Привязка аккаунтов |

### AppContext (глобальное состояние)

`web/src/context/AppContext.tsx` — единственный React Context (`useApp()` hook).

**Состояние:** session, balance, photo, preAnalysis, activeCategory, selectedStyleKey, currentTask, isGenerating, generatedImageUrl, afterScore, afterPerception, generationMode, taskHistory, identities.

**Ключевые actions:** uploadPhoto, runPreAnalyze, generate, loginWithOAuth, loginWithToken, logout, refreshBalance, fetchTaskHistory.

### Wizard Flow (AppPage)

```
StepUpload          StepAnalysis         StepStyle            StepGenerate
  │                    │                    │                    │
  │ uploadPhoto()      │ runPreAnalyze()    │ setSelectedStyleKey│ generate()
  │ → blob preview     │ → POST /pre-analyze│ → style card       │ → POST /analyze
  │                    │ → scores,          │   with delta       │ → SSE progress
  │                    │   perception,      │   forecast         │ → handleTaskResult
  │                    │   opportunities    │                    │ → verify image
  │                    │                    │                    │ → show result
```

### Real-time коммуникация

1. **SSE** (`EventSource`) → `GET /api/v1/sse/progress?task_id=&token=`
   - Events: `progress` (step current/total), `done`
2. **Polling fallback** — если SSE не подключился за 5 секунд → `setInterval` 3 секунды, `GET /tasks/{task_id}`
3. Timeout: 5 минут, max 5 ошибок подряд

### OAuth photo persistence

При OAuth redirect фото сохраняется в IndexedDB (`lib/photo-persist.ts`), metadata в sessionStorage. После callback — `restorePhotoAfterOAuth()` восстанавливает файл, mode, style.

### Работа с изображениями

- `normalizeImageUrl()` (`lib/image-url.ts`): приводит relative/wrong-host `/storage/` URLs к `API_BASE`
- `verifyImageUrl()`: предзагрузка через `new Image()` перед отображением (3 retry с backoff)
- При недоступности сгенерированного изображения → `refundTask()` + refresh balance

---

## 10. Scoring и Perception

### LLM Analysis (pre-score)

Каждый сервис (`RatingService`, `DatingService`, `CVService`, `SocialService`, `EmojiService`):
1. Строит системный промпт через `PromptEngine.build(mode, context)` (русский, JSON schema)
2. Вызывает `consensus_analyze(llm, image, prompt, temperature, n)`:
   - При `n=1`: один vision-вызов OpenRouter
   - При `n>1`: N параллельных вызовов → median-merge числовых значений
3. Парсит результат в Pydantic model

### Perception параметры

Общие для dating/cv/social/rating:
- **warmth** (0-10) — теплота, дружелюбие
- **presence** (0-10) — уверенность, присутствие
- **appeal** (0-10) — привлекательность, вовлечение
- **authenticity** (0-10) — естественность (вычисляется post-gen через IdentityService)
- **perception_insights[]** — рекомендации с parameter, current_level, suggestion

### Delta Scoring (post-gen)

`DeltaScorer.compute()` (в `executor.py`):
1. Скачивает сгенерированное изображение
2. Повторно анализирует через тот же ModeRouter сервис
3. Вычисляет delta: `{metric: {pre, post, delta}}` для основных скоров и perception
4. Записывает progression в Redis (лучший скор за сессию)
5. Вычисляет authenticity через face similarity (InsightFace cosine)

### Конфигурация

- `SCORING_TEMPERATURE` — температура LLM для scoring (default 0.0)
- `SCORING_CONSENSUS_SAMPLES` — количество параллельных вызовов для consensus (default 1)

---

## 11. Стили и режимы

### Каталог стилей

Определен в `src/prompts/image_gen.py`:

| Режим | Стили | Personalities |
|-------|-------|--------------|
| **Dating** | warm_outdoor, studio_elegant, cafe, landmark_*, travel_*, sport_*, evening_*, и др. | friendly, confident, charismatic |
| **CV** | corporate, boardroom, creative, startup, industry_*, career_*, и др. | professional, approachable, authoritative |
| **Social** | influencer, luxury, casual, artistic, platform_*, aesthetic_*, hobby_*, и др. | expressive, sophisticated, relaxed |
| **Emoji** | 12 фиксированных эмоций (happy, sad, angry, surprised, ...) | — |
| **Rating** | — (только анализ, без генерации стилей) | — |

### StyleSpec и Registry

`src/prompts/style_spec.py`:
- `StyleSpec` — background, clothing (male/female), lighting, expression, flags
- `StyleRegistry` — регистрация/поиск по key, mode-aware defaults
- `STYLE_REGISTRY` в `image_gen.py` — заполняется через `build_spec_from_legacy`

### Промпт-архитектура для генерации

Prompt = Identity anchors + Mode-specific change + Style-specific details:

```
[IDENTITY_FIRST] → Лицо = неприкосновенно
[FACE_ANCHOR]    → Сохранить exact face shape, features
[BODY_ANCHOR]    → Proportions, build, skin tone
[SKIN_FIX]       → Realistic texture, no plastic
[BACKGROUND]     → Style-specific background instruction
[CLOTHING]       → Gender-aware clothing for style
[CAMERA]         → Professional photography settings
[REALISM]        → Must look like real photo, no AI artifacts
```

Reserved multi-pass путь использует `STEP_TEMPLATES` (background_edit, clothing_edit, lighting_adjust, expression_hint, skin_correction, style_overall) и `ENHANCEMENT_LEVEL_MODIFIERS` (уровни 1-4) из `src/prompts/image_gen.py`. В активном single-pass рантайме эти шаблоны не вызываются — см. `docs/architecture/reserved.md`.

---

## 12. Платежи

### Credit Lifecycle

```
Новый пользователь → image_credits = 1 (starter)
    │
    ├── POST /analyze → check_credits → reserve 1 credit (immediate deduct)
    │   │
    │   ├── Generation success → credit stays deducted
    │   ├── Generation failure → refund credit
    │   └── No credits (skip_image_gen) → analysis only, no deduction
    │
    └── YooKassa payment → webhook → credits += pack_quantity
```

### YooKassa интеграция

- `POST /payments/create` → `Payment.create(amount, description, confirmation redirect)` → `confirmation_url`
- `POST /payments/yookassa/webhook` → `payment.succeeded` → `CreditTransaction(tx_type="purchase")` + `user.image_credits += qty`
- Пакеты: `CREDIT_PACKS` env var, формат `qty:price_rub,qty:price_rub`

---

## 13. Edge Architecture

### Primary vs Edge

| Аспект | Primary (Railway) | Edge (RU VPS) |
|--------|-------------------|---------------|
| `DEPLOYMENT_MODE` | `primary` | `edge` |
| AI обработка | Локально (worker) | Проксируется на primary |
| Internal API | Доступен (`/internal/*`) | Вызывает primary |
| Миграции | `alembic upgrade head` | `alembic upgrade head` (своя БД) |
| Платежи | YooKassa | YooKassa (свои ключи) |
| Auth | Все провайдеры | Все провайдеры |

### RemoteAIService (`src/services/remote_ai.py`)

Edge-only клиент. При `POST /analyze` на edge:
1. `RemoteAIService.submit_task()` → `POST /internal/process-analysis` на primary (base64 image)
2. `poll_result()` → `GET /internal/task/{id}/status` каждые 2 секунды, до 180 секунд
3. Возвращает result + optional `generated_image_b64`
4. Edge сохраняет изображение в свое storage

### Edge reconciler

`_edge_reconciler_loop()` в `main.py` — фоновая задача, которая находит зависшие tasks (>5 мин в processing) и помечает failed с возвратом кредита.

---

## 14. Redis Key Schema

| Pattern | TTL | Назначение |
|---------|-----|-----------|
| `ratemeai:session:{token}` | `SESSION_TTL_SECONDS` | User session → UUID |
| `ratemeai:task_input:{task_id}` | `TASK_INPUT_REDIS_TTL_SECONDS` | Входное изображение (base64) |
| `ratemeai:gen_image:{task_id}` | 1 час | Сгенерированное изображение (base64) |
| `ratemeai:preanalysis:{hash}` | 10 мин | Кеш pre-analysis результата |
| `ratemeai:progress:{task_id}` | — | Pub/sub channel: прогресс задачи |
| `ratemeai:task_done:{task_id}` | — | Pub/sub channel: завершение задачи |
| `ratemeai:embedding:{task_id}` | 30 мин | Face embedding (base64 numpy) |
| `bot_session:{telegram_id}` | 7 дней | Bearer token для bot API calls |
| `bot_edge_session:{telegram_id}` | 7 дней | Edge Bearer token (bot payments) |
| `oauth_state:{state}` | 5 мин | OAuth state → user_id/link_code |
| `phone_otp:{phone}` | 5 мин | OTP код для phone auth |
| `link_code:{code}` | 5 мин | Link code → target user_id |
| `ratemeai:score_progression:{user}:{mode}` | 24 часа | Best score tracking per session |

---

## 15. Метрики и мониторинг

### Prometheus

`prometheus_fastapi_instrumentator` для HTTP метрик. Кастомные счетчики в `src/metrics.py`:
- `tasks_processed_total` (label: mode, status)
- `pipeline_duration_seconds`
- Pipeline trace (timestamps per step) сохраняется в `task.result`

### Health checks

- `GET /health` — version, status, git SHA
- `GET /readiness` — DB connection, Redis ping, edge: primary reachability + internal ping

### Logging

- Production: JSON structured logs (`python-json-logger`)
- Dev: plain text logs
- `RequestLoggingMiddleware`: X-Request-Id, request timing

---

## 16. Middleware chain (FastAPI)

Порядок (last added = outermost = first to run):

1. **`_IframeHeadersMiddleware`** — `X-Frame-Options: ALLOWALL`, CSP `frame-ancestors` для OK/VK iframes
2. **`CORSMiddleware`** — production allowlist + Railway regex; dev: `*`
3. **`RequestLoggingMiddleware`** — X-Request-Id, timing log
4. **Prometheus Instrumentator** — wraps routes для метрик

Per-route dependencies (не middleware): `get_db`, `get_redis`, `get_auth_user`, `check_credits`, `require_consents`.

---

## 17. Privacy Layer & Consent Gate

Слой реализует требования 152-ФЗ и минимизацию ПДн: оригинал фото не хранится, внешние AI вызываются только при явном согласии пользователя, логи не содержат ПДн.

### Модель данных

- `UserConsent(user_id, kind, version, source, ip_hash, user_agent_hash, granted_at, revoked_at)` — аудит-след (см. миграцию `009_user_consents.py`)
- `Task.input_image_path` теперь **nullable**: оригинал в durable storage не пишется
- Активные согласия кэшируются в Redis `ratemeai:consent:{user_id}` (TTL 1 час)

### Kinds согласий

| Kind | Что покрывает | Чем блокируется |
|-----|-----|-----|
| `data_processing` | Обработка ПДн, включая фото лица | Любой `/analyze`, `/pre-analyze` |
| `ai_transfer` | Передача во внешние AI (OpenRouter / Reve / Replicate), в т.ч. за пределы РФ | Вызов `LLM.analyze_image`, `ImageGen.generate` |

Оба — **обязательные, независимые** (можно отозвать только `ai_transfer`, оставив `data_processing`). Формальная основа — ст. 12 152-ФЗ (трансграничная передача — отдельное согласие).

### Gate-компоненты

- **Backend**: `src/api/deps.py::require_consents` → HTTP 451 `{code: "consent_required", missing: [...]}` при отсутствии согласий. Для B2B API-клиентов поддерживаются заголовки `X-Consent-Data-Processing` / `X-Consent-AI-Transfer` (автогрант+persist).
- **Web**: `web/src/components/ConsentGate.tsx` оборачивает `StepUpload` — без активных согласий загрузка фото заблокирована. 451 в `AppContext` вызывает re-fetch состояния.
- **Telegram**: `src/bot/handlers/consent.py` + pre-check в `handle_photo` — inline-кнопки, блокируют обработку до грантов.
- **Edge → Primary** (`/internal/*`): `_assert_consent_flags` проверяет `policy_flags.consent_data_processing` + `consent_ai_transfer` из запроса, иначе 451. Edge прокладывает флаги из `Task.policy_flags` через `RemoteAIService`.

### Guard трансграничной передачи

`src/services/ai_transfer_guard.py`:
- `task_context_scope(context)` — ContextVar-обёртка, активируется в `AnalysisPipeline.execute` и в local `/pre-analyze`
- `assert_external_transfer_allowed()` вызывается в `OpenRouter.analyze_image`, `ReveProvider.generate`, `ReplicateProvider.generate`. Без активного согласия — `AITransferForbiddenError` → 451/fail.

### Privacy Layer (бытие данных)

`src/services/privacy.py::PrivacyLayer`:
1. `sanitize_and_normalize(raw)` → удаляет EXIF / ICC / GPS / XMP, нормализует размер, перекодирует в JPEG. Использует `src/utils/image.py::validate_and_normalize` с явной очисткой `img.info`, `exif=b""`, `icc_profile=None`.
2. `stash_for_pipeline(sanitized, task_id, market_id)` → кладёт санитизированные байты в Redis `ratemeai:task_input:{task}:{market}` (TTL 15 мин). **Durable storage не задействуется.**
3. `cache_embedding(embedding, task_id, market_id)` → сохраняет ArcFace embedding на 72 часа (`ratemeai:embedding:{task}:{market}`). Это единственный долгоживущий идентичностный артефакт.

### Жизненный цикл артефактов

| Артефакт | Где живёт | TTL |
|-----|-----|-----|
| Оригинальное фото | Только память процесса / Redis stash | до конца `process_analysis` (≤ 15 мин) |
| Sanitized bytes | Redis | 15 мин |
| ArcFace embedding | Redis | 72 часа |
| Pre-analysis (LLM) | Redis `ratemeai:preanalysis:{id}:{market}` | 30 мин |
| Generated image | Local FS / Redis cache | 72 часа (GC `privacy_gc_cron` удаляет файлы и нулит `generated_image_url` в `Task.result`, выставляя `_purged_at`) |
| `Task.input_image_path` | Postgres | `NULL` для всех новых задач |
| `UserConsent` | Postgres | бессрочно (аудит) |

### Worker GC

`src/workers/tasks.py::privacy_gc_cron`:
- Запускается периодически (cron из `worker.py`)
- Находит задачи старше 72 ч со сгенерированным изображением
- Физически удаляет `generated/*.jpg` и `share_card_path`, нулит URL-ы в `Task.result`, выставляет `result._purged_at`
- Frontend видит `purged: true` в `GET /tasks` и отображает плашку «Результат удалён по политике хранения»

`_cleanup_ephemeral_artifacts` (обычный worker path): всегда удаляет Redis `task_input` и любые legacy `input_image_path` (для задач, созданных до включения privacy layer).

### Delta scoring без оригинала

`src/orchestrator/executor.py::DeltaScorer.compute` больше не принимает `original_bytes`:
- "Before"-скор берётся из сохранённого `pre-analysis` (уже есть `perception_scores`)
- Authenticity compare — по кэшированному embedding (Redis, 72 ч)
- Повторный LLM-анализ оригинала выключен — ничего не пишем, не передаём, не восстанавливаем

### Логи

`src/utils/log_filters.py::PIIFilter` навешен на root logger и stream handler. Перехватывает:
- `bytes / bytearray / memoryview` в `args` → `[REDACTED_BYTES len=N]`
- Base64 чанки длиной ≥ 200 символов → `[REDACTED_IMG]`
- `data:image/*;base64,...` URLs → `[REDACTED_IMG]`
- Поля с именами `image_bytes / image_b64 / raw_bytes / file_bytes / image` → `[REDACTED_IMG]`

`RequestLoggingMiddleware` дополнительно маскирует UUID в `request.url.path` (`/tasks/{id}` вместо конкретного task_id).

### Политика флагов (Task.policy_flags)

Обязательный набор для user-facing задач:
```
{
  "cache_allowed": true,
  "delete_after_process": true,
  "retention_policy": "privacy_72h",
  "data_class": "user_photo",
  "single_provider_call": true,
  "consent_data_processing": true,
  "consent_ai_transfer": true
}
```
Edge-прокси прокладывает consent-флаги из запроса; primary отказывает с 451, если их нет.

### Чек-лист верификации после деплоя

1. `GET /api/v1/users/me/consents` без грантов → `missing: [data_processing, ai_transfer]`
2. `POST /api/v1/analyze` без грантов → `451 {code: consent_required}`
3. После гранта: `/analyze` → 202, `storage.upload` **не вызывается** для `inputs/*`
4. `GET /api/v1/tasks/{id}` → `result.input_image_url/_path` = `null`
5. Через 72 ч: `result.purged: true`, файлы `generated/*.jpg` физически удалены
6. `docker logs app | grep -E 'base64|[A-Za-z0-9+/=]{200,}'` → 0 совпадений
