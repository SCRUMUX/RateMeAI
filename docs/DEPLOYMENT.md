# DEPLOYMENT — RateMeAI

Инфраструктура, CI/CD, переменные окружения и чеклисты для развертывания.

---

## 1. Архитектура развертывания

```
GitHub (main)
    │
    ▼
GitHub Actions CI
    │
    ├── test (lint + pytest + tsc)
    │
    ├── deploy-backend (Railway: app → worker → bot)
    │
    └── deploy-ru (SSH → update.sh на RU edge)

Railway (primary):
    ├── app   (FastAPI, port 8000)
    ├── worker (ARQ)
    ├── bot   (aiogram)
    ├── PostgreSQL 16
    └── Redis 7

Vercel (frontend):
    └── web/dist (Vite SPA, auto-deploy on push)

RU Edge (VPS):
    ├── postgres (Docker)
    ├── redis (Docker)
    ├── app (DEPLOYMENT_MODE=edge)
    ├── nginx (SSL + static frontend)
    └── ratemeai_web_dist (named volume)
```

---

## 2. CI/CD Pipeline

Файл: `.github/workflows/ci.yml`

### Job: test

Триггер: push/PR в `main`.

1. Postgres 16 + Redis 7 service containers
2. Python 3.12: `pip install -r requirements-dev.txt` + `opencv-python-headless`
3. **Ruff lint:** `ruff check src/ tests/ --select=E,F,W --ignore=E501`
4. **Pytest:** `python -m pytest tests/ -v --tb=short` (с DATABASE_URL и REDIS_URL на service containers)
5. **Frontend typecheck:** `cd web && npm ci && npx tsc --noEmit`

### Job: deploy-backend

Только push в `main`, после `test`.

1. Установка Railway CLI
2. Set `DEPLOY_GIT_SHA` (12 символов), `EDGE_API_URL`, `INTERNAL_API_KEY` на все сервисы
3. Последовательный deploy: `railway up -s app` → `worker` → `bot`
4. Sleep 180s → health check (`GET /health`, до 8 попыток с интервалом 45s)

### Job: deploy-ru

После `test` + `deploy-backend`, только push в `main`.

1. Проверка наличия `RU_SSH_HOST`, `RU_SSH_KEY`, `RU_SSH_USER` (skip если нет)
2. SSH → sync `INTERNAL_API_KEY` в `/opt/ratemeai/.env.ru`
3. `bash /opt/ratemeai/deploy/ru/update.sh` (git pull, build web, restart)
4. Smoke tests: `/health` (SHA), `/version.json`, catalog API, auth+tasks, edge→primary connectivity

---

## 3. Railway

### Сервисы

Один `Dockerfile` (root), разные start commands:

| Сервис | Start command | Назначение |
|--------|--------------|-----------|
| app | `uvicorn src.main:app --host 0.0.0.0 --port 8000` | HTTP API |
| worker | `arq src.workers.tasks.WorkerSettings` | Background jobs |
| bot | `python -m src.bot.app` | Telegram bot |

### Dockerfile (root)

- Base: `python:3.12-slim`
- Installs: `requirements.txt` + `opencv-python-headless` + system deps (libgl1, libglib2, cmake)
- Non-root user: `appuser`
- `docker-entrypoint.sh`: fixes volume permissions when run as root
- Expose: 8000

### railway.toml

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 5
```

---

## 4. Vercel (Frontend)

### Конфигурация

`vercel.json`:
```json
{
  "framework": "vite",
  "installCommand": "cd web && npm install",
  "buildCommand": "cd web && npx vite build",
  "outputDirectory": "web/dist",
  "rewrites": [{"source": "/(.*)", "destination": "/index.html"}]
}
```

### Env vars на Vercel

| Переменная | Значение |
|-----------|---------|
| `VITE_API_BASE_URL` | `https://app-production-6986.up.railway.app` |
| `DEPLOY_GIT_SHA` | Автоматически (или вручную) |

### URL

- Production: `https://ailookstudio.vercel.app`
- Custom domain: `https://ailookstudio.ru`

---

## 5. RU Edge Server

### Docker Compose

`docker-compose.ru.yml`:
- `postgres:16-alpine` — свой экземпляр
- `redis:7-alpine` — свой экземпляр
- `app` — `DEPLOYMENT_MODE=edge`, `.env.ru`, Alembic миграции при старте
- `nginx` — SSL termination, static frontend из volume `ratemeai_web_dist`, proxy `/api` и `/storage` к app
- `web` (profile `build-only`) — Node 20 build → nginx static
- `certbot` (profile) — Let's Encrypt

### Deploy script

`deploy/ru/update.sh`:
1. `git pull`
2. Build web image `--no-cache` (profile `build-only`)
3. Extract `dist/` из web container в named volume
4. Build + restart `app`
5. Restart `nginx`
6. Health check `https://ru.ailookstudio.ru/health`

### Ручной деплой

```bash
ssh user@ru-server
cd /opt/ratemeai
sudo DEPLOY_GIT_SHA=$(git rev-parse --short=12 HEAD) ./deploy/ru/update.sh
```

---

## 6. Переменные окружения

Полный список в `.env.example` (179 строк). Ниже — по категориям.

### Приложение и URL

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `APP_ENV` | `dev` / `prod` — prod включает Alembic, production CORS | `prod` |
| `APP_HOST` | Bind host | `0.0.0.0` |
| `APP_PORT` | Bind port | `8000` |
| `API_BASE_URL` | Публичный HTTPS URL API (для storage URLs, share cards) | `https://app-production-6986.up.railway.app` |
| `WEB_BASE_URL` | URL фронтенда (для OAuth redirect) | `https://ailookstudio.ru` |
| `WEB_DOMAIN` | Домен фронтенда | `ailookstudio.ru` |
| `VITE_API_BASE_URL` | API URL для frontend (build-time) | `https://app-production-6986.up.railway.app` |
| `CORS_EXTRA_ORIGINS` | Дополнительные CORS origins через запятую | |
| `DEPLOY_GIT_SHA` | Git SHA для /health и /version.json | автоматически из CI |

### База данных и Redis

| Переменная | Описание |
|-----------|----------|
| `DATABASE_URL` | PostgreSQL URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis URL (`redis://...`) |
| `TASK_INPUT_REDIS_TTL_SECONDS` | TTL для входных изображений в Redis (default 600) |

### Telegram

| Переменная | Описание |
|-----------|----------|
| `TELEGRAM_BOT_TOKEN` | Bot API token |
| `TELEGRAM_BOT_USERNAME` | Username бота (без @) |
| `BOT_WEBHOOK_URL` | Webhook URL (если не задан — polling) |
| `BOT_WEBHOOK_SECRET` | Secret для webhook verification |

### LLM (OpenRouter)

| Переменная | Описание |
|-----------|----------|
| `OPENROUTER_API_KEY` | API key |
| `OPENROUTER_BASE_URL` | Base URL (default `https://openrouter.ai/api/v1`) |
| `OPENROUTER_MODEL` | Model name (default Gemini) |

### Image Generation

| Переменная | Описание |
|-----------|----------|
| `IMAGE_GEN_PROVIDER` | `mock` / `reve` / `replicate` / `auto` |
| `IMAGE_GEN_STRENGTH` | Strength parameter для генерации |
| `REVE_*` | Reve API key, test_time_scaling |
| `REPLICATE_*` | Replicate API token, inpaint model version |

### Storage

| Переменная | Описание |
|-----------|----------|
| `STORAGE_PROVIDER` | `local` / `s3` |
| `STORAGE_LOCAL_PATH` | Путь для local storage (Docker: `/app/storage`) |
| `STORAGE_HTTP_FALLBACK_BASE` | HTTP fallback URL для worker (если нет shared volume) |
| `S3_ENDPOINT` | S3-compatible endpoint |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Credentials |
| `S3_BUCKET`, `S3_REGION` | Bucket и region |
| `S3_PUBLIC_BASE_URL` | CDN/public URL для объектов |
| `S3_PRESIGN_TTL_SECONDS` | TTL presigned URLs |

### Платежи (YooKassa)

| Переменная | Описание |
|-----------|----------|
| `YOOKASSA_SHOP_ID` | Shop ID |
| `YOOKASSA_SECRET_KEY` | Secret key |
| `CREDIT_PACKS` | Пакеты кредитов, формат `qty:price,qty:price` |

### Identity и Quality Gates

| Переменная | Описание |
|-----------|----------|
| `IDENTITY_SIMILARITY_THRESHOLD` | Порог cosine similarity (ArcFace) |
| `IDENTITY_COMPOSITE_BLEND` | Blend factor для face composite |
| `SEGMENTATION_ENABLED` | true/false — включить multi-pass |
| `AESTHETIC_THRESHOLD` | Порог aesthetic score |
| `ARTIFACT_THRESHOLD` | Порог artifact ratio |
| `PHOTOREALISM_*` | Photorealism check настройки |

### Scoring

| Переменная | Описание |
|-----------|----------|
| `SCORING_TEMPERATURE` | Температура LLM для scoring (default 0.0) |
| `SCORING_CONSENSUS_SAMPLES` | Количество consensus samples (default 1) |
| `PIPELINE_BUDGET_MAX_USD` | Max budget per pipeline run |

### Edge / Geo-split

| Переменная | Описание |
|-----------|----------|
| `DEPLOYMENT_MODE` | `primary` / `edge` |
| `REMOTE_AI_BACKEND_URL` | URL primary API (для edge) |
| `INTERNAL_API_KEY` | Shared key для internal API |
| `EDGE_API_URL` | URL edge (для bot payment routing) |

### Auth провайдеры

| Переменная | Описание |
|-----------|----------|
| `OK_APP_SECRET` | Odnoklassniki app secret |
| `VK_APP_SECRET` | VK Mini App secret |
| `VK_ID_APP_ID`, `VK_ID_APP_SECRET`, `VK_ID_REDIRECT_URI` | VK ID OAuth |
| `YANDEX_CLIENT_ID`, `YANDEX_CLIENT_SECRET`, `YANDEX_REDIRECT_URI` | Yandex OAuth |
| `SMS_*` | SMS provider для phone OTP |
| `ADMIN_SECRET` | Secret для создания API keys |
| `API_KEY_PEPPER` | Pepper для хеширования API keys |
| `SESSION_TTL_SECONDS` | TTL сессий (default 604800 = 7 дней) |

---

## 7. Чеклисты

### Перед коммитом / пушем

1. **Ruff lint:** `python -m ruff check src/ tests/ --select=E,F,W --ignore=E501`
2. **Typecheck frontend:** `cd web && npx tsc --noEmit`
3. **Проверка Python синтаксиса:** `python -c "import py_compile; py_compile.compile(r'src\main.py', doraise=True)"`
4. **ReadLints** на измененных файлах
5. **Bump version** в `src/version.py` (при значимых изменениях)
6. Коммит: `git add <files>; git commit -m "тип: описание"`
7. Push: `git push origin main`

### После деплоя (Railway)

1. `GET https://app-production-6986.up.railway.app/health` → version + status "ok"
2. Worker logs: `Worker started RateMeAI version=X.Y.Z` — та же version что и API
3. Bot: `/start` в Telegram → ответ без ошибок

### После деплоя (RU Edge)

1. `GET https://ru.ailookstudio.ru/health` → version + git SHA
2. `GET https://ru.ailookstudio.ru/version.json` → frontend build SHA
3. `GET https://ru.ailookstudio.ru/api/v1/catalog/styles?mode=dating` → 200
4. `GET https://ru.ailookstudio.ru/readiness` → `primary_reachable: true`

### Добавление миграции

1. `alembic revision --autogenerate -m "description"`
2. Ревью файла в `alembic/versions/`
3. Push в main — миграция применится автоматически на обоих серверах при старте

---

## 8. Troubleshooting

### Worker не обрабатывает задачи

- Проверить что worker и app одной версии (`/health` vs worker logs)
- Проверить `REDIS_URL` — worker и app должны использовать один Redis
- Проверить Redis connectivity: `redis-cli -u $REDIS_URL ping`

### "File not found: inputs/..."

- Worker не может найти входное изображение
- Причина: разные версии app/worker (новый протокол Redis cache vs старый storage-only)
- Решение: redeploy все сервисы из одного коммита

### Telegram бот не отправляет фото

- `API_BASE_URL` должен быть публичным HTTPS (не localhost, не private IP)
- Telegram серверы скачивают файл по URL — приватные адреса не работают
- Caption max 1024 символов — если длиннее, `send_photo` падает

### Edge: analysis timeout

- Проверить `REMOTE_AI_BACKEND_URL` и `INTERNAL_API_KEY`
- `GET /readiness` на edge → `primary_reachable`
- Primary должен быть доступен по HTTPS с edge сервера

### Frontend не видит API

- `VITE_API_BASE_URL` должен быть задан на Vercel (build-time variable)
- Для RU: nginx проксирует `/api` → `http://app:8000`
- CORS: проверить `CORS_EXTRA_ORIGINS` если кастомный домен

### Миграции не применились

- В production (`APP_ENV=prod`) миграции запускаются автоматически при старте app
- В dev используется `create_all` (без Alembic)
- Проверить: `GET /readiness` → если DB check fails, миграция могла упасть
- Ручной запуск: `alembic upgrade head`

---

## 9. Мониторинг

### Endpoints

| URL | Назначение |
|-----|-----------|
| `/health` | Версия, статус, git SHA |
| `/readiness` | DB + Redis + primary (edge) |
| `/metrics` | Prometheus (prod: auth required) |

### Логи

- Railway: встроенный log viewer
- RU Edge: `docker compose -f docker-compose.ru.yml logs -f app`
- Worker: отдельные логи (`docker compose logs -f worker`)

### Ключевые метрики

- `tasks_processed_total{mode, status}` — количество обработанных задач
- `pipeline_duration_seconds` — время обработки
- HTTP request duration/count (Prometheus instrumentator)
