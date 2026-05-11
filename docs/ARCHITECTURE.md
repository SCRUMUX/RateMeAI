# RateMeAI — Архитектура (двухрегиональная)

> Один codebase, два независимых deployment'а. Этот документ
> описывает архитектуру, домены, инварианты PII, маршрутизацию ботов
> и порядок развёртывания. Если вы здесь впервые, прочитайте его
> до того, как открывать `.env.*` или дашборды Railway/Vercel.

---

## 1. Целевая картина

Два региона работают параллельно, не пересекаясь по данным:

| Параметр | Global (Railway) | RU edge (VPS) |
|---|---|---|
| Аудитория | Любой `language_code` ∉ {ru,be,kk,uk,ky} | `ru,be,kk,uk,ky` |
| Домены SPA | `ailookstudio.vercel.app` | `ailookstudio.ru`, `www.ailookstudio.ru` (+ зеркало `ru.ailookstudio.ru` до cutover'а) |
| Домен API | `https://app-production-6986.up.railway.app` | тот же, что и SPA |
| Хостинг | Railway 3 сервиса (`app`, `worker`, `bot`) | VPS, `docker-compose.ru.yml` |
| Postgres | Railway-managed | На том же VPS (`pgdata` volume) |
| Telegram bot | `@AI_Look_Studio_bot` | `@RateMeAI_bot` |
| Платёжный шлюз | Xsolla (USD/EUR) | YooKassa (RUB) |
| Compute mode | `local` (генерация тут же) | `remote` (делегирует в Railway по `/internal/process-analysis`) |
| CMS role | `editor` (хранит мастер контента) | `follower` (только читает, синк через HMAC) |

```text
        ┌──────────────────────────────────────────┐
        │  ailookstudio.vercel.app (Global SPA)    │
        │  ailookstudio.ru        (RU SPA)         │
        └───────────────┬───────────────┬──────────┘
                        │               │
              REST/SSE  │               │  REST/SSE
                        ▼               ▼
        ┌──────────────────────┐  ┌──────────────────────────┐
        │ Railway: app+worker+ │  │  VPS: nginx + app + db   │
        │ Postgres + Redis     │  │  + Redis (no worker)     │
        │ (MARKET_ID=global)   │  │  (MARKET_ID=ru, edge)    │
        │ Bot:@AI_Look_Studio  │  │  Bot:@RateMeAI_bot       │
        └─────┬───────────┬────┘  └──────────┬───────────────┘
              │           │  HMAC-signed CMS push (editor→follower)
              │           └─────────────────►│
              │           ◄─────────────────│
              │            POST /internal/process-analysis (edge→primary)
              │            anonymous user, ephemeral retention
              ▼
        OpenAI / Replicate / external CDNs
```

---

## 2. PII-инварианты

### 2.1 Данные RU-юзеров никогда не покидают VPS

В Postgres'е RU edge лежат: `users.telegram_id`, `users.first_name`,
`user_identities.profile_data.email`, `tasks.result`, `usage_logs`.
Все эти поля **только** на VPS. Railway-Postgres о них не знает.

Принудительно поддерживается тремя контурами:

* **OAuth/Telegram-логин** возможен только на том сервере, чей домен
  указан в whitelist'е провайдера. RU OAuth → `ailookstudio.ru/api/v1/auth/*`,
  Global → `ailookstudio.vercel.app/api/v1/auth/*` (через Railway).
* **Telegram-ботов два**, и `LanguageGuardMiddleware`
  ([src/bot/middlewares/language_guard.py](../src/bot/middlewares/language_guard.py))
  отсекает кросс-региональные запросы **до**
  `UserRegistrationMiddleware`. Нет ни одной записи в чужой регион.
* **Edge → primary вызов** (см. §3) использует синтетический
  `internal_user_id = uuid5("edge-proxy.<edge_task_id>")` и пустую
  `policy_flags{data_class="regional_photo", retention_policy="ephemeral",
  delete_after_process=True}`. Реальные `telegram_id`/`email` в
  payload не уходят (см. golden-тест
  [tests/test_services/test_remote_ai_payload.py](../tests/test_services/test_remote_ai_payload.py)).

### 2.2 Picture-sanitisation на входе

Любое фото перед отправкой в модель проходит
[`PrivacyLayer.sanitize_and_normalize`](../src/services/privacy.py):

* EXIF / ICC / XMP / IPTC удаляются.
* Изображение нормализуется (max 12 MP, JPEG quality 90, sRGB).
* В оригинальном виде байты не пишутся ни в Postgres, ни в S3 —
  кладутся в Redis-stash на 15 минут и удаляются по завершении.

Это означает, что даже если бы хосты были общими, OpenAI/Replicate
получают фото без геолокации, серийника камеры, имени файла, hash'а
RAW.

### 2.3 Логи маскируют PII

[`PIIFilter`](../src/utils/log_filters.py) висит на root-логгере и
заменяет email, телефон, telegram_id, `language_code`, `first_name`,
`last_name`, `display_name` и т.п. на `[REDACTED_PII]` ещё до записи
в stdout (а значит и до Railway/Datadog).

### 2.4 Ephemeral cleanup

После завершения задачи `_cleanup_ephemeral_artifacts`
([src/workers/tasks.py](../src/workers/tasks.py)):

1. Удаляет Redis-stash с оригинальными байтами.
2. Удаляет storage-файл `input_image_path` (если был).
3. Если `delete_after_process=True` — удаляет и сгенерированный файл.
4. Зануляет `task.input_image_path = None` и поля-указатели в
   `task.result` (`generated_image_url`, `input_image_path` и т.п.) и
   делает второй `db.commit()`. После этого даже в Postgres нет
   «висячих» ссылок на удалённые файлы.

---

## 3. Edge → Primary AI delegation

RU edge сам инференс не делает (`COMPUTE_MODE=remote`). Когда
пользователь нажал «Сгенерировать», происходит следующее:

```text
SPA (ailookstudio.ru)
  │  POST /api/v1/analyze  (multipart: image + form)
  ▼
RU edge FastAPI
  │  PrivacyLayer.sanitize   ← EXIF strip здесь
  │  Task.create (Postgres VPS) — БЕЗ user_id референса на real user
  │  RemoteAIService.submit_task(image_b64, …, source=…)
  ▼
Railway primary (/api/v1/internal/process-analysis)
  │  Pydantic: extra="forbid" — режет любые лишние поля (PII firewall)
  │  internal_user_id = uuid5(NAMESPACE_DNS, f"edge-proxy.{edge_task_id}")
  │  User(internal_user_id, image_credits=999_999) ON CONFLICT DO NOTHING
  │  policy_flags.delete_after_process=True
  │  Task.create (Postgres Railway) → ARQ enqueue
  ▼
Worker (Railway)
  │  OpenAI/Replicate generate
  │  Возврат через GET /api/v1/internal/task/{id}/status — base64 + JSON
  ▼
RU edge ←  base64 ← worker
  │  Сохраняет b64 в свой Redis 72 ч + Postgres tasks.result
  │  Отдаёт SPA / боту по `/api/v1/tasks/{id}`
  ▼
SPA / bot отрисовывают результат
```

Whitelist полей, которые могут пересечь границу:

```
image_b64, mode, style, profession, enhancement_level,
pre_analysis_id, variant_id, edge_task_id, market_id,
scenario_slug, scenario_type, entry_mode, trace_id,
policy_flags, artifact_refs, image_model, image_quality,
framing, input_hints, source
```

Любое поле сверх — HTTP 422.

---

## 4. Маршрутизация ботов по языку

Бот один на регион, но архитектурно они симметричны:

```text
Telegram update ─▶ Bot
  │
  │   LanguageGuardMiddleware  (src/bot/middlewares/language_guard.py)
  │     - читает settings.telegram_bot_username
  │     - смотрит from_user.language_code
  │     - если несоответствие региону → отвечает t.me/{peer_bot}
  │       и АБОРТИТ chain. UserRegistrationMiddleware НЕ вызовется.
  │
  ▼
  UserRegistrationMiddleware → POST /api/v1/auth/telegram → Postgres
```

Регионы определяются константами в
[language_guard.py](../src/bot/middlewares/language_guard.py):

* `RU_BOT_USERNAMES = {"ratemeai_bot"}`
* `GLOBAL_BOT_USERNAMES = {"ai_look_studio_bot"}`
* `RU_LANGUAGE_CODES = {"ru","be","kk","uk","ky"}`

Чтобы middleware «знал», какой он бот, переменные окружения должны
быть проставлены CI'ем:

| Env var | Railway (Global) | VPS (RU) |
|---|---|---|
| `TELEGRAM_BOT_USERNAME` | `AI_Look_Studio_bot` | `RateMeAI_bot` |
| `PEER_BOT_USERNAME` | `RateMeAI_bot` | `AI_Look_Studio_bot` |
| `TELEGRAM_BOT_TOKEN` | новый токен от BotFather | `.env.ru` секрет |

---

## 5. CMS репликация

`ailookstudio.vercel.app/admin/landing` пишет JSON-контент в свою
БД и сразу же шлёт HMAC-подписанный webhook на
`https://ailookstudio.ru/internal/cms/replicate`. Алгоритм
описан в [src/services/cms_replication.py](../src/services/cms_replication.py).

Подстраховка: на старте FastAPI на edge запускается lifespan-таск
`_cms_safety_pull_loop`, который раз в час сам опрашивает editor'а на
случай пропущенных webhook'ов.

---

## 6. Двухступенчатая админка

`/admin/*` живёт на обоих регионах:

* `https://ailookstudio.vercel.app/admin/landing` — управляет Global
  landing'ом и видит Railway-БД пользователей.
* `https://ailookstudio.ru/admin/landing` — управляет (на самом деле
  «follower-локальная копия CMS, отображается read-only») и видит
  RU-Postgres.

Same-origin policy — почему вход на одном не виден на другом. Это
не баг, а 152-ФЗ. Чтобы оператор не путался, в
[AdminStatusBanner](../web/src/components/admin/AdminStatusBanner.tsx)
показывается:

* для **текущего** сервера: market_id, deployment_mode, привязанные
  email'ы, размер whitelist'ов;
* для **парного** сервера: кнопка «Открыть парную админку».

Whitelist общий — `ADMIN_EMAILS` GitHub-секрет, который CI синкает
в обе стороны.

---

## 7. DNS / TLS rollout

### Состояния (см. [docs/VARIANT_B_EXTERNAL_CHECKLIST.md](VARIANT_B_EXTERNAL_CHECKLIST.md))

| Состояние | DNS `ailookstudio.ru` | nginx server-blocks (extra/) |
|---|---|---|
| Phase 1 — pre-cutover | → Vercel (Global SPA) | `ru-legacy.conf` (SPA+API на ru.ailookstudio.ru) |
| Phase 2 — после DNS cutover'а | → IP VPS | `ru-legacy.conf` + `ailookstudio-tls.conf` |
| Phase 3 — 301 со старого имени | → IP VPS | `ailookstudio-tls.conf` + `ru-legacy-redirect.conf` |

Переключение фаз делает [deploy/ru/update.sh](../deploy/ru/update.sh):

* `maybe_dns_cutover` — авто-выпускает TLS-cert для `ailookstudio.ru`
  и копирует `ailookstudio-tls.conf` в named volume `nginx_extra_conf`.
* `ensure_ru_legacy_block` — каждый deploy кладёт либо `ru-legacy.conf`
  (по умолчанию), либо `ru-legacy-redirect.conf` если в env
  `RU_LEGACY_REDIRECT_ENABLED=1`.

Это позволяет переключать состояния одной GitHub Variable, без
ручного редактирования `nginx.conf`.

---

## 8. Известные риски и ограничения

* **`internal_user_id` коллизии**: uuid5 от `edge_task_id` детерминирован.
  Несколько одинаковых retry-задач → один User. Это OK, потому что у
  такого «юзера» нет PII — просто `__edge_proxy__` shell.
* **PIIFilter не покрывает третьесторонние логгеры**, которые пишут
  напрямую в stdout (например, libUV под uvloop). Это маловероятно,
  но стоит проверять при добавлении новых библиотек.
* **Same-Origin Policy** — JS на одном домене не может проверить
  статус другого. Поэтому banner показывает кнопку, а не «✅ logged in»
  для парного сервера.
* **DNS cutover требует ручного шага в Vercel Dashboard.** Снятие
  домена там нельзя автоматизировать без Vercel API key с правами
  Owner — мы намеренно отдаём этот rubber-stamp оператору.

---

## 9. Ссылки

* План: [.cursor/plans/two-region_clean_architecture_e2849f1e.plan.md](../.cursor/plans/two-region_clean_architecture_e2849f1e.plan.md)
* External checklist: [docs/VARIANT_B_EXTERNAL_CHECKLIST.md](VARIANT_B_EXTERNAL_CHECKLIST.md)
* DNS runbook: [docs/DNS_CUTOVER_RUNBOOK.md](DNS_CUTOVER_RUNBOOK.md)
* Деплой: [.cursor/rules/deploy.mdc](../.cursor/rules/deploy.mdc)
