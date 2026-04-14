# DEVELOPMENT — RateMeAI

Руководство разработчика: локальный запуск, структура проекта, тесты, конвенции.

---

## 1. Структура проекта

```
RateMEAI/
├── .cursor/
│   ├── plans/              # Cursor AI планы
│   └── rules/              # Cursor правила (язык, деплой)
├── .github/
│   └── workflows/
│       └── ci.yml          # CI/CD pipeline
├── alembic/
│   ├── versions/           # Миграции (001–008+)
│   ├── env.py              # Alembic config (reads settings.database_url)
│   └── script.py.mako      # Migration template
├── deploy/
│   └── ru/                 # RU edge: nginx, docker-compose, setup/update scripts
├── docs/
│   ├── ARCHITECTURE.md     # Техническая архитектура
│   ├── DEPLOYMENT.md       # Деплой и инфраструктура
│   ├── DEVELOPMENT.md      # Этот файл
│   └── master_product_constitution.md  # Продуктовая конституция
├── scripts/
│   └── deploy.ps1          # PowerShell deploy helper
├── sdk/
│   ├── __init__.py
│   └── client.py           # Python SDK клиент для API
├── src/
│   ├── api/                # FastAPI routes и middleware
│   │   ├── v1/
│   │   │   ├── analyze.py      # POST /analyze, /pre-analyze
│   │   │   ├── users.py        # Все /auth/* эндпоинты + /users/me/*
│   │   │   ├── tasks.py        # GET /tasks, /tasks/{id}, /tasks/{id}/refund
│   │   │   ├── payments.py     # /payments/* + webhook
│   │   │   ├── share.py        # POST /share/{id}
│   │   │   ├── engagement.py   # /engagement/*
│   │   │   ├── catalog.py      # /catalog/modes, /catalog/styles
│   │   │   ├── sse.py          # SSE /sse/progress
│   │   │   └── internal.py     # /internal/* (edge→primary)
│   │   ├── deps.py             # Зависимости: get_db, get_redis, get_auth_user, check_credits
│   │   ├── middleware.py       # RequestLoggingMiddleware
│   │   └── router.py          # Монтирование всех v1 routers
│   ├── bot/                # Telegram bot
│   │   ├── app.py              # Создание бота, dispatcher, webhook/polling
│   │   ├── handlers/
│   │   │   ├── start.py        # /start, /emoji, /rating, /balance
│   │   │   ├── photo.py        # Прием фото
│   │   │   ├── mode_select.py  # Выбор режима/стиля → analyze → poll → deliver
│   │   │   ├── results.py      # Форматирование и отправка результатов
│   │   │   ├── link.py         # Привязка аккаунтов
│   │   │   └── fallback.py     # Catch-all
│   │   ├── keyboards.py        # Inline keyboards
│   │   └── middleware.py       # UserRegistrationMiddleware
│   ├── channels/           # Платформенные модули
│   │   ├── dispatcher.py       # Мультиканальные уведомления
│   │   ├── deep_links.py       # Deep links для share
│   │   ├── telegram_notify.py  # Telegram sendMessage API
│   │   ├── ok_auth.py          # OK signature verification
│   │   ├── vk_auth.py          # VK launch params verification
│   │   ├── vk_id_auth.py       # VK ID OAuth
│   │   └── yandex_auth.py      # Yandex OAuth
│   ├── models/
│   │   ├── db.py               # SQLAlchemy ORM модели
│   │   ├── enums.py            # AnalysisMode, TaskStatus
│   │   └── schemas.py          # Pydantic schemas (RatingResult, DatingResult, ...)
│   ├── orchestrator/       # Пайплайн обработки
│   │   ├── pipeline.py         # AnalysisPipeline — главный оркестратор
│   │   ├── planner.py          # PipelinePlanner — multi-pass plan
│   │   ├── executor.py         # ImageGenerationExecutor + DeltaScorer
│   │   ├── router.py           # ModeRouter — mode → service
│   │   └── merger.py           # ResultMerger — share metadata
│   ├── prompts/            # LLM промпты
│   │   ├── engine.py           # PromptEngine — фасад
│   │   ├── rating.py           # Rating analysis prompt
│   │   ├── dating.py           # Dating analysis prompt
│   │   ├── cv.py               # CV analysis prompt
│   │   ├── social.py           # Social analysis prompt
│   │   ├── emoji.py            # Emoji sticker prompt
│   │   ├── perception.py       # Shared perception scoring fields
│   │   ├── image_gen.py        # Image generation prompts, styles, anchors
│   │   └── style_spec.py       # StyleSpec, StyleRegistry
│   ├── providers/
│   │   ├── llm/
│   │   │   └── openrouter.py   # OpenRouterLLM — vision + text
│   │   ├── image_gen/
│   │   │   ├── reve_provider.py    # Reve edit/remix/create
│   │   │   ├── replicate.py        # Replicate prediction API
│   │   │   ├── chain.py            # ChainImageGen — fallback chain
│   │   │   └── mock.py             # Mock (passthrough)
│   │   ├── storage/
│   │   │   ├── local.py            # Local filesystem storage
│   │   │   └── s3.py               # S3-compatible storage
│   │   ├── factory.py          # get_storage(), get_image_gen(), get_llm()
│   │   └── base.py             # Abstract base classes
│   ├── services/
│   │   ├── rating.py           # RatingService
│   │   ├── dating.py           # DatingService
│   │   ├── cv.py               # CVService
│   │   ├── social.py           # SocialService
│   │   ├── emoji.py            # EmojiService
│   │   ├── identity.py         # IdentityService (InsightFace ArcFace)
│   │   ├── quality_gates.py    # QualityGateRunner
│   │   ├── payments.py         # YooKassa integration
│   │   ├── sessions.py         # Redis session CRUD
│   │   ├── remote_ai.py        # RemoteAIService (edge→primary)
│   │   ├── style_catalog.py    # STYLE_CATALOG (API response format)
│   │   └── share_card.py       # ShareCardGenerator (PIL)
│   ├── utils/
│   │   ├── image.py            # validate_and_normalize, has_face_heuristic
│   │   ├── consensus.py        # consensus_analyze (median-merge)
│   │   ├── security.py         # NSFW extraction, hash helpers
│   │   └── results.py          # humanize_result_scores, score utils
│   ├── workers/
│   │   └── tasks.py            # ARQ jobs: process_analysis, reconcile_stuck_tasks
│   ├── config.py               # Settings (Pydantic BaseSettings)
│   ├── main.py                 # FastAPI app, lifespan, /storage, /health
│   ├── version.py              # APP_VERSION = "X.Y.Z"
│   └── metrics.py              # Prometheus counters
├── tests/
│   ├── test_api/               # API integration tests
│   ├── test_channels/
│   ├── test_orchestrator/
│   ├── test_providers/
│   ├── test_services/
│   ├── test_utils/
│   ├── test_workers/
│   └── conftest.py             # Shared fixtures
├── web/                    # React SPA
│   ├── public/                 # Favicon, images, placeholders
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Landing.tsx         # Marketing page
│   │   │   ├── AppPage.tsx         # Main wizard (4 steps)
│   │   │   ├── PaymentSuccess.tsx  # Post-payment
│   │   │   ├── AuthCallback.tsx    # OAuth return
│   │   │   └── LinkPage.tsx        # Account linking
│   │   ├── components/
│   │   │   ├── sections/           # NavBar, Hero, HowItWorks, Simulation, Pricing, Footer
│   │   │   ├── steps/              # StepUpload, StepAnalysis, StepStyle, StepGenerate
│   │   │   ├── AuthModal.tsx
│   │   │   ├── StorageModal.tsx
│   │   │   ├── ReviewModal.tsx
│   │   │   ├── CategoryTabs.tsx
│   │   │   ├── ProgressBar.tsx
│   │   │   ├── LinkedAccountsPanel.tsx
│   │   │   └── Toast.tsx
│   │   ├── context/
│   │   │   └── AppContext.tsx       # Глобальное состояние (useApp)
│   │   ├── lib/
│   │   │   ├── api.ts              # HTTP client (fetch + auth)
│   │   │   ├── auth.ts             # Token management, OAuth
│   │   │   ├── image-url.ts        # normalizeImageUrl
│   │   │   └── photo-persist.ts    # IndexedDB photo persistence
│   │   ├── data/
│   │   │   ├── styles.ts           # STYLES_BY_CATEGORY, PARAMS_BY_MODE
│   │   │   ├── testimonials.ts     # Landing testimonials
│   │   │   └── ai-facts.ts         # Loading screen facts
│   │   ├── icons/                  # SVG icon components
│   │   ├── assets/                 # Logo, images
│   │   ├── App.tsx                 # Router + providers
│   │   ├── main.tsx                # Entry point
│   │   └── index.css               # Tailwind + glass design system
│   ├── Dockerfile              # Node 20 build → nginx serve
│   ├── nginx.conf              # Frontend nginx config
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.cjs
│   └── postcss.config.cjs
├── Dockerfile                  # Backend: Python 3.12
├── docker-compose.yml          # Full local stack
├── docker-compose.ru.yml       # RU edge stack
├── docker-entrypoint.sh
├── alembic.ini
├── railway.toml
├── vercel.json
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
├── .env.example                # Все env vars с описанием
├── .env.ru.example             # RU edge env vars
└── README.md
```

---

## 2. Локальный запуск

### Через Docker Compose (полный стек)

```bash
cp .env.example .env
# Заполните секреты: TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY, и т.д.
# API_BASE_URL — публичный HTTPS если тестируете Telegram media

docker compose up --build
```

Сервисы:
- API: `http://localhost:8000`
- Health: `http://localhost:8000/health`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

### Frontend (dev mode)

```bash
cd web
npm install
npm run dev
```

- Dev server: `http://localhost:3000`
- Proxy: `/api` → `http://localhost:8000`, `/storage` → `http://localhost:8000`

### Только backend (без Docker)

```bash
# Нужны запущенные PostgreSQL и Redis
export DATABASE_URL=postgresql+asyncpg://ratemeai:ratemeai@localhost:5432/ratemeai
export REDIS_URL=redis://localhost:6379/0
export APP_ENV=dev

# API
uvicorn src.main:app --reload --port 8000

# Worker (отдельный терминал)
arq src.workers.tasks.WorkerSettings

# Bot (отдельный терминал, опционально)
python -m src.bot.app
```

---

## 3. Тесты

### Python

```bash
python -m pytest tests/ -v --tb=short
```

Интеграционные тесты (`tests/test_api/`) требуют PostgreSQL + Redis. Если сервисы не запущены — тесты пропускаются (skipped).

```bash
# Запустить с БД
docker compose up -d postgres redis
python -m pytest tests/ -v --tb=short
```

### Linting

```bash
# Ruff (как в CI)
python -m ruff check src/ tests/ --select=E,F,W --ignore=E501

# С автоисправлением
python -m ruff check src/ tests/ --select=E,F,W --ignore=E501 --fix
```

### Frontend typecheck

```bash
cd web
npx tsc --noEmit
```

---

## 4. Конвенции

### Windows / PowerShell

Разработка ведется на Windows. PowerShell не поддерживает:
- `&&` — используйте `;` или отдельные вызовы
- Heredoc `<<'EOF'` — используйте `-m "message"` для git commit
- `head`, `tail` — используйте `Select-Object -First N`

### Версионирование

- Версия в `src/version.py`: `APP_VERSION = "X.Y.Z"`
- Инкрементируйте при каждом значимом деплое
- Проверяется через `/health` — расхождение = проблема

### Git workflow

- Основная ветка: `main`
- Push в main → автоматический деплой через CI
- Для крупных изменений: feature branch → PR → merge в main

### Линтинг

CI запускает ruff с `--select=E,F,W --ignore=E501`. Код не пройдет CI если есть ошибки ruff.

---

## 5. Гайды

### Добавление нового режима анализа

1. **Enum:** Добавить в `src/models/enums.py` → `AnalysisMode`
2. **Prompt:** Создать `src/prompts/{mode}.py` с `build_prompt(context) -> str`
3. **Service:** Создать `src/services/{mode}.py` с `{Mode}Service.analyze(image_bytes, **kwargs)`
4. **Schema:** Добавить Pydantic model в `src/models/schemas.py`
5. **Engine:** Зарегистрировать в `src/prompts/engine.py` → `_PROMPT_MAP`
6. **Router:** Добавить маппинг в `src/orchestrator/router.py` → `ModeRouter`
7. **Image prompts (если нужны):** Добавить стили в `src/prompts/image_gen.py`, зарегистрировать в `_IMAGE_PROMPT_MAP`
8. **Planner:** Добавить step templates в `src/orchestrator/planner.py` (если multi-pass)
9. **Bot:** Добавить клавиатуры в `src/bot/keyboards.py`, обработчик результата в `results.py`
10. **Web:** Добавить категорию в `web/src/data/styles.ts`, обновить `CategoryId` type
11. **Catalog:** Обновить `src/services/style_catalog.py`
12. **Тесты:** Добавить в `tests/`

### Добавление нового стиля к существующему режиму

1. Добавить ключ + описание в соответствующий dict (`DATING_STYLES`, `CV_STYLES`, `SOCIAL_STYLES`) в `src/prompts/image_gen.py`
2. Добавить personality в `{MODE}_PERSONALITIES`
3. Если нужны overrides (edit_compatible, female clothing) — `_STYLE_OVERRIDES`
4. `StyleSpec` будет построен автоматически через `build_spec_from_legacy`
5. Обновить `STYLE_CATALOG` в `src/services/style_catalog.py`
6. Обновить `web/src/data/styles.ts` → `STYLES_BY_CATEGORY`
7. Обновить bot keyboards если они ограничивают набор стилей

### Добавление нового auth-провайдера

1. Создать verification модуль в `src/channels/{provider}_auth.py`
2. Добавить auth эндпоинт в `src/api/v1/users.py`:
   - Верификация подписи/callback
   - `_find_or_create_by_identity(db, provider="{name}", external_id=...)`
   - `_auth_response(redis, user)` → session token
3. Зарегистрировать route в `src/api/router.py`
4. Добавить provider в `UserIdentity.provider` допустимые значения
5. Если OAuth — добавить init + callback эндпоинты, state в Redis
6. Frontend: обновить `lib/auth.ts` → `startOAuth()`, добавить кнопку в `AuthModal`
7. Bot: при необходимости обновить `middleware.py`

### Добавление миграции

```bash
# Сгенерировать из изменений ORM моделей
alembic revision --autogenerate -m "описание изменения"

# Ревью файла
# Файл появится в alembic/versions/

# Push в main — миграция применится автоматически на обоих серверах
```

Миграции в production запускаются при старте `app` процесса (`src/main.py` lifespan).
В dev используется `Base.metadata.create_all` (без Alembic).

---

## 6. Ключевые зависимости

### Python (`requirements.txt`)

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| fastapi | 0.115.6 | HTTP framework |
| uvicorn | 0.34.0 | ASGI server |
| aiogram | 3.15.0 | Telegram bot framework |
| arq | 0.26.1 | Redis job queue |
| sqlalchemy | 2.0.36 | ORM (async) |
| asyncpg | 0.30.0 | PostgreSQL async driver |
| redis | 5.2.1 | Redis client |
| pillow | >=12.1.1 | Image processing |
| httpx | 0.28.1 | Async HTTP client |
| pydantic-settings | 2.7.1 | Settings management |
| alembic | 1.14.1 | DB migrations |
| yookassa | 3.4.0 | Payment SDK |
| reve | 0.1.2 | Reve image gen SDK |
| aioboto3 | 13.4.0 | Async S3 client |
| insightface | >=0.7.3 | Face analysis (ArcFace) |
| onnxruntime | >=1.17.0 | ML inference |
| mediapipe | >=0.10.0 | Segmentation |
| prometheus-fastapi-instrumentator | >=7.0.0 | Metrics |
| tenacity | 9.0.0 | Retries |

### Frontend (`web/package.json`)

| Пакет | Назначение |
|-------|-----------|
| react | UI framework |
| react-dom | DOM rendering |
| react-router-dom | Client-side routing |
| framer-motion | Animations |
| tailwind-merge | Tailwind class merging |
| vite | Build tool |
| tailwindcss | CSS framework |
| typescript | Type checking |
