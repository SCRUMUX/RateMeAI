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
| Аудитория веба | Любой `language_code` ∉ {ru,be,kk,uk,ky} | `ru,be,kk,uk,ky` |
| Домены SPA | `ailookstudio.vercel.app` | `ailookstudio.ru`, `www.ailookstudio.ru` |
| Домен API | `https://app-production-6986.up.railway.app` | тот же, что и SPA |
| Хостинг | Railway 3 сервиса (`app`, `worker`, `bot`) | VPS, `docker-compose.ru.yml` (без `bot`) |
| Postgres | Railway-managed | На том же VPS (`pgdata` volume) |
| Telegram bot | `@AI_Look_Studio_bot` (единственный, webhook) | бота нет — Telegram-трафик целиком на Railway |
| Платёжный шлюз веба | Xsolla (USD/EUR) | YooKassa (RUB) |
| Платёжный шлюз бота | Telegram Stars (XTR) | — |
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
        │ Bot:@AI_Look_Studio  │  │  (no bot service)        │
        └─────┬───────────┬────┘  └──────────┬───────────────┘
              │           │  HMAC-signed CMS push (editor→follower)
              │           └─────────────────►│
              │           ◄─────────────────│
              │            POST /internal/process-analysis (edge→primary)
              │            anonymous user, ephemeral retention
              ▼
        OpenAI / FAL.ai / external CDNs
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
* **Telegram-бот единственный** (`@AI_Look_Studio_bot` на Railway,
  webhook).  Все Telegram-юзеры — включая русскоязычных — обслуживаются
  одним процессом; `language_code` влияет только на текстовые ссылки
  (см. §4).  PII бота (`telegram_id`, `username`, `image_credits`,
  `CreditTransaction`) лежит на Railway и из RU edge **не дублируется** —
  RU edge только читает баланс при `link-token` redeem через подписанный
  internal endpoint
  ([src/api/v1/internal_bot.py](../src/api/v1/internal_bot.py)).
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
  │  OpenAI VLM scoring + FAL edit-model image gen (v1.64: GPT Image 2
  │  и Nano Banana 2 через UnifiedImageGenProvider)
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

## 4. Один бот + Telegram Stars + per-language лендинг

С 1.62.0 в проекте один Telegram-бот — `@AI_Look_Studio_bot` на
Railway, webhook-режим.  Polling из РФ невозможен (РКН блокирует
egress на `api.telegram.org`), поэтому второй бот `@RateMeAI_bot` на
VPS был снят с production.  Telegram сам открывает соединение к
нашему webhook endpoint'у, что обходит блокировку для входящего
трафика.

```text
Telegram update (любой language_code)
  │
  ▼
@AI_Look_Studio_bot (Railway, webhook)
  │
  │   UserRegistrationMiddleware → POST /api/v1/auth/telegram → Postgres (Railway)
  │
  ├── обычные хендлеры (фото, стиль, /balance …)
  │
  └── оплата:
       topup_stars  → buy_xtr:{qty}  → bot.send_invoice(currency=XTR)
                                       Telegram pre_checkout_query →
                                       handler ревалидирует payload+price
                                       по credit_packs_xtr.
       successful_payment           → POST /api/v1/internal/bot/stars/grant
                                       (X-Internal-Key, идемпотентно
                                       по telegram_payment_charge_id).
```

### Per-language лендинг

Тексты бота, которые ссылают на сайт (`link.py`, `consent.py`,
privacy URL), используют helper
`settings.resolve_landing_url(language_code)`:

* `ru`/`be`/`kk`/`uk`/`ky` → `https://ailookstudio.ru`
* всё остальное → `https://ailookstudio.vercel.app`

Конкретные URL задаются через env: `BOT_WEB_LANDING_URL_RU` и
`BOT_WEB_LANDING_URL_DEFAULT` (CI синкает оба на Railway).

### Cross-region link TG ↔ web

Когда юзер на `ailookstudio.ru` нажимает «привязать TG-аккаунт» и
вводит `link-token`, `claim-link` на RU edge после успешного merge
identity вызывает Railway-side
`GET /api/v1/internal/bot/users/{tg_id}/profile` (X-Internal-Key,
read-only), берёт оттуда `image_credits` бота и зачисляет их на
web-юзера одной транзакцией `CreditTransaction(tx_type="link_merge")`.
Дедупликация — через Redis ключ `ratemeai:bot_balance_merged:{tg_id}`.

| Env var | Railway (Global) | VPS (RU) |
|---|---|---|
| `TELEGRAM_BOT_USERNAME` | `AI_Look_Studio_bot` | — (бота нет) |
| `TELEGRAM_BOT_TOKEN` | webhook-токен от BotFather | — |
| `BOT_WEBHOOK_URL` | публичный URL Railway-app | — |
| `BOT_WEB_LANDING_URL_RU` | `https://ailookstudio.ru` | — (не использует) |
| `BOT_WEB_LANDING_URL_DEFAULT` | `https://ailookstudio.vercel.app` | — |
| `CREDIT_PACKS_XTR` | `5:25,10:45,20:85,50:200` | — |
| `INTERNAL_API_KEY` | shared с RU edge | shared с Railway (нужен для link-merge) |

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

| Состояние | DNS `ailookstudio.ru` | nginx config |
|---|---|---|
| Phase 1 — pre-cutover | → Vercel (Global SPA) | `nginx.conf` (:443 ru.ailookstudio.ru), `extra/` пустой |
| Phase 2 — после DNS cutover'а | → IP VPS | `nginx.conf` + `extra/ailookstudio-tls.conf` |
| Phase 3 — 301 со старого имени | → IP VPS | `nginx.conf` с location-блоком 301 для `ru.ailookstudio.ru` |

Переключение между Phase 1 ↔ Phase 2 авто, между Phase 2 ↔ Phase 3
— через коммит:

* `maybe_dns_cutover` ([deploy/ru/update.sh](../deploy/ru/update.sh))
  — авто-выпускает TLS-cert для `ailookstudio.ru` и копирует
  `ailookstudio-tls.conf` в named volume `nginx_extra_conf`
  (Phase 1 → Phase 2).
* Phase 2 → Phase 3 (301 с `ru.ailookstudio.ru`): редактирование
  `deploy/ru/nginx.conf` руками — заменить тело `server { listen 443;
  server_name ru.ailookstudio.ru; ... }` на
  `return 301 https://ailookstudio.ru$request_uri;`, плюс коммит.
  Это редкая операция (раз в жизни проекта), и автоматизация через
  named volume оказалась хрупкой: на первом deploy'е после переноса
  объём может быть пустым на 1-2 секунды, и nginx стартует без :443 →
  remote `Connection refused` до следующего рестарта.

---

## 8. Composition Safety Layer (CSL)

Композиционно-аномальные результаты — дорогой брак: «огромная голова на
выдуманном теле» рейтит хуже «плохого селфи». CSL — это **upstream-гейт**
между загрузкой фото и сборкой промпта, который классифицирует исходник
по 4 шкалам и заранее отрезает несовместимые комбинации `(кадр, стиль)`.
Логика разнесена по слоям так, чтобы текущий prompt assembler
([src/prompts/image_gen.py](../src/prompts/image_gen.py)) и
identity-preserve-блок остались нетронутыми.

### 8.1 Архитектура

```text
┌───────────────────────┐    ┌──────────────────────────┐
│ /api/v1/pre-analyze   │    │ /api/v1/analyze          │
│ ─ analyze_input_quality│    │ ─ hard-stop по framing   │
│   • InsightFace bbox  │    │   (server-side validation│
│   • CSL heuristic     │    │   against Redis cache)   │
│   • Pose (Phase 2)    │    │                          │
│ → InputQualityReport  │    │ → 400 framing_not_allowed│
│   .composition_class  │    │   или 202 + worker       │
│   .allowed_framings   │    └──────────────────────────┘
└──────────┬────────────┘
           │ Redis: ratemeai:preanalysis:<id> { _csl: {...} }
           ▼
┌───────────────────────┐
│ Wizard (SPA) и Bot    │
│ ─ framing buttons     │
│ ─ stylelock badges    │
│ ─ "Risky" warnings    │
│ ─ Advanced override   │
└───────────────────────┘
```

### 8.2 Классы и политика

`CompositionClass` (см. [src/services/composition_safety.py](../src/services/composition_safety.py)):

| Класс | Что в кадре | Разрешённый framing | Запретные стили (`needs_full_body`) | Риск (`needs_torso`) |
|-------|-------------|---------------------|--------------------------------------|----------------------|
| `face_closeup` | Только лицо | `portrait` | block | warn |
| `portrait` | Лицо + плечи | `portrait`, `half_body` | block | OK |
| `half_body` | До пояса | все | OK | OK |
| `full_body` | До ног | все | OK | OK |
| `unknown` | детектор не уверен | `portrait` (fail-closed safe) | block | warn |

### 8.3 Phase 1 — эвристика

Базовый классификатор `classify_heuristic` использует `face_area_ratio`,
позицию bbox и `space_below` (свободное место под лицом в единицах высоты
лица). Пороги вынесены в ENV-переменные `CSL_*` (см.
[src/config.py](../src/config.py)). По дефолту:
- `face_closeup_face_ratio=0.30`, `face_closeup_space_below=1.0` →
  лицо ≥ 30% кадра ИЛИ под лицом меньше одной его высоты;
- `portrait_face_ratio=0.18`, `portrait_space_below=2.0`;
- `half_body_space_below=4.0`.

### 8.4 Phase 2 — MediaPipe Pose

Включается `BODY_LANDMARKS_ENABLED=true`. Lazy-load в
[src/services/body_landmarks.py](../src/services/body_landmarks.py).
Возвращает флаги `shoulders_visible / hips_visible / knees_visible`,
по которым `classify_from_landmarks` уточняет результат эвристики.
Любая ошибка (нет wheel, нет GLIBC, native crash) → `None` и fallback
на эвристику. Кеш детектора poison-on-fail — второго `import mediapipe`
не будет.

### 8.5 Phase 3 — Advanced override

Гейт ослабляется только если **оба** условия выполнены:
- ENV `COMPOSITION_SAFETY_ADVANCED_OVERRIDE=true` на сервере;
- клиент явно посылает `skip_composition_safety=true` (SPA — через
  модалку [AdvancedSettingsModal.tsx](../web/src/components/wizard/AdvancedSettingsModal.tsx),
  бот — через двухкнопочный `on_override_csl`/`on_override_csl_go`).

Сервер пишет `ctx["composition_safety_skipped"] = True` и инкрементит
`composition_override_used`. На edge→primary флаг прокидывается через
`RemoteAnalysisRequest.skip_composition_safety` — primary ре-валидирует
его против собственного `composition_safety_advanced_override`, чтобы
клиент не мог "пройти" override на VPS, если на Railway он выключен.

### 8.6 Метрики и калибровка

Три счётчика в [src/metrics.py](../src/metrics.py):

| Metric | Лейблы | Семантика |
|---|---|---|
| `composition_class_total` | `composition_class`, `source` | Сколько классификаций каждой категории сделано. `source` ∈ `heuristic|pose`. |
| `composition_block_total` | `composition_class`, `style` | Сколько раз CSL отказал в стиле для класса. Срабатывание = «политика мешает пользователю» — алертим, если конкретный стиль > 30%. |
| `composition_override_used_total` | `composition_class` | Сколько раз advanced override был принят. Низкий процент = политика откалибрована корректно. |

Калибровка порогов — оффлайн через
[scripts/calibrate_composition_thresholds.py](../scripts/calibrate_composition_thresholds.py).
Сид-датасет лежит в [data/seed_photos/composition_labels.json](../data/seed_photos/composition_labels.json).
Сами фото в git **не** коммитим (см.
`data/seed_photos/.gitignore`) — оператор кладёт JPEG'и локально и
запускает скрипт.

### 8.7 Rollout (warn → block → pose → override)

Поэтапная раскатка через ENV-флаги. Каждый шаг живёт ≥ 7 дней с
наблюдением за `composition_block_total` и user-feedback NPS до
перехода на следующий.

| Фаза | Флаги | Что включено | Критерий перехода |
|---|---|---|---|
| **W1. Warn-only** | `COMPOSITION_SAFETY_ENABLED=false` | CSL классифицирует и пишет метрики, но UI показывает только мягкое предупреждение. Никаких блокировок. | `composition_class_total` стабилен ≥ 3 дня, нет 5xx из-за `analyze_input_quality`. |
| **W2. Block** | `COMPOSITION_SAFETY_ENABLED=true` | Hard-stop в SPA/bot/`/api/v1/analyze`. Override недоступен. | `composition_block_total` рост ≤ 2× baseline, NPS не упал > 3 п.п. |
| **W3. Pose** | `BODY_LANDMARKS_ENABLED=true` | MediaPipe Pose уточняет эвристику. Сравниваем `source="pose"` vs `source="heuristic"` в Grafana. | Расхождение Pose↔heuristic < 15% по `composition_class_total`. |
| **W4. Override** | `COMPOSITION_SAFETY_ADVANCED_OVERRIDE=true` | Пользователи-эксперты могут обойти CSL через UI/bot. | `composition_override_used_total / composition_block_total` ≤ 20% — если выше, надо ослабить политику, а не давать override. |
| **W5. Anatomy fix** | `CSL_REFERENCE_PAD_ENABLED=true` (default) | Numerical composition anchor в промпте + геометрическое padding исходника для tight-selfie → half/full-body (§8.9). `reference_padded_total` начинает считать. | `proportions_natural` pass-rate (VLM gate) на `composition_class∈{face_closeup,unknown}` входах > 90% на 7-дневном окне. |
| **W6. Anatomy v1.65** | `CSL_REFERENCE_PAD_ENABLED=true` (default), `CSL_REFERENCE_PAD_FACE_RATIO=0.28` (default) | Cinematic-vocabulary numerical anchor (`Reframe the reference into …` + `85mm portrait lens` / `35mm lens`), сжатый `IDENTITY_PRESERVE_BLOCK` (4 anchors), positive-framed proportions clause в opener; padding gate расширен на `framing=portrait`; жёсткий `half_body` fallback в executor заменён на CSL-aware auto-resolver (§8.9). Soft warning по `proportions_natural=false` без retry. | `proportions_natural` pass-rate на `framing=portrait` + `face_area_ratio>0.28` входах > 92%; `reference_padded_total{framing="portrait"}` начал расти (ранее = 0); жалоб «голова больше тела» на support ≤ 1% от total за 7 дней. |
| **W7. Style Catalog Normalization v1.66** | `CSL_REFERENCE_PAD_ENABLED=true` (default), `CSL_REFERENCE_PAD_FACE_RATIO_CV=0.22` (default) | Однопроходная JSON-миграция `data/styles.json` (см. `scripts/migrations/2026_05_styles_v4_anatomy/`): убраны portrait-pose директивы из `expression`/`scene_anchor`/`background.base` у 33 non-studio стилей (CV+dating+social); studio-portrait whitelist `_STUDIO_PORTRAIT_STYLE_KEYS = {formal_portrait, studio_elegant}` освобождён от нормализации; `85mm portrait lens` → `85mm short-telephoto lens` снимает дублирующий portrait-recency cue; CV-mode padding порог понижен до 0.22; lint правила `EXPRESSION_PORTRAIT_LEAK` / `SCENE_POSE_LEAK` / `WARDROBE_TIGHT_SUIT` защищают каталог от регрессий. | `proportions_natural` pass-rate на CV-стилях ≥ pass-rate на dating/social в течение 3 дней (раньше отставал на ~10 п.п.); жалобы «голова больше тела» на CV/career стилях ≤ 0.5% от total за 7 дней. |
| **W8. Padding Gate + Identity-Tail v1.67** | `CSL_REFERENCE_PAD_ENABLED=true` (default), `CSL_REFERENCE_PAD_FACE_RATIO=0.10` (default), `CSL_REFERENCE_PAD_FACE_RATIO_CV=0.10` (default) | Аудит v1.66 продакшна показал, что половина uploads (типичные head-and-shoulders с `face_area_ratio ≈ 0.10..0.17`, `composition_class=PORTRAIT`) проваливалась мимо padding-гейта (0.28 / 0.22) — edit-модель копировала reference layout. v1.67 расширяет гейт: composition_class trigger теперь `{face_closeup, portrait, half_body, unknown}` (раньше `{face_closeup, unknown}`), ratio threshold опущен до `0.10` для обоих режимов (CV boost схлопнулся в main threshold). Параллельно `IDENTITY_PRESERVE_BLOCK` (1) перенесён в самый хвост промпта (после `PHOTOREAL_BLOCK`) — composition владеет early-attention, identity владеет recency-bias slot'ом; (2) переписан как чисто текстурный (`preserve the same person's facial features: eye shape and colour, hairline, skin undertone`), без слова `face shape` — последнее edit-модели читали геометрически как «копируй head/torso ratio». | `reference_padded_total{composition_class="portrait"}` начал расти (ранее ≈ 0 на не-CV mode); `proportions_natural` pass-rate на portrait+half_body uploads > 95% на 7-дневном окне; жалобы «голова больше тела» / «вклеенное лицо» в support ≤ 0.2% от total за 7 дней. |

**Откат**: ставим конкретный ENV-флаг в `false`. Никаких миграций или
data-fix'ов не требуется — кеш `_csl` в Redis просто игнорится, а
старый prompt assembler принимает любой `framing` как раньше.

### 8.8 Failure modes и инварианты

- **Детектор недоступен** → `composition_class=unknown` → `allowed_framings=["portrait"]`
  (fail-closed safe). Пользователь видит "Composition cannot be detected"
  и может перезалить фото или выбрать portrait-style.
- **`pre_analysis_id` отсутствует** в запросе на `/api/v1/analyze` →
  CSL hard-stop НЕ срабатывает (legacy путь). Защиту берёт на себя
  numerical composition anchor в prompt assembler (§8.9) — гарантирует
  корректные пропорции даже без CSL-классификации.
- **Edge → primary**: `RemoteAnalysisRequest.skip_composition_safety`
  это **запрос** на override; primary всегда ре-валидирует против
  своего флага. Edge не может в одностороннем порядке «отключить» CSL.
- **Wizard стейт переживает upload**: при `uploadPhoto()` SPA сбрасывает
  `skipCompositionSafety` в false (чтобы override от прошлого фото не
  утёк на новое).

### 8.9 Anatomy fix one-pass (v1.64 → v1.65)

**Проблема**: до v1.64 на `face_closeup` входах (selfie с лицом > 30%
кадра) edit-модели (GPT Image 2 / Nano Banana 2) копировали layout
исходника и выдавали «приклеенную голову» — лицо оставалось крупным,
а тело гадалось вокруг. CSL ловила только заведомо запретные пары
`(class, style)`, но **внутри** разрешённого framing'а оставались
диспропорции. v1.64 решил это для `half_body` / `full_body` через
численный anchor + reference padding, но `framing=portrait` (дефолт
веба и большинства бот-сценариев) всё ещё ловил пограничные tight-
selfie кейсы.

**v1.65** закрывает оставшийся разрыв через четыре согласованных
изменения:

#### 1. Cinematic composition anchor (v1.65 prompt rewrite)

[src/prompts/image_gen.py](../src/prompts/image_gen.py):
`_COMPOSITION_NUMERICAL_HINT` переписан с процентных таргетов на
cinematic vocabulary с явным `Reframe …` оператором и физическим
объективом:

| framing | directive |
|---|---|
| `portrait` | Reframe the reference into a head-and-shoulders bust shot taken with an 85mm portrait lens at chest height, the head occupying the upper quarter of the canvas… |
| `half_body` | Reframe the reference into a medium waist-up shot taken with an 85mm portrait lens at chest height, both shoulders fully visible and the torso extending to the belt line… |
| `full_body` | Reframe the reference into a full-length standing shot taken with a 35mm lens from a slight low angle, head, torso, legs and feet all visible centered in the frame… |

[src/prompts/model_wrappers.py](../src/prompts/model_wrappers.py):
`_assemble` для non-document стилей вставляет этот hint **перед**
`IDENTITY_PRESERVE_BLOCK`. Порядок принципиален — composition должна
выигрывать в attention над identity-копированием. v1.65 убрал также
стадию `framing_line` из wire-prompt — она дублировала сигнал и
давала edit-моделям противоречивые директивы.

Параллельно:

* `IDENTITY_PRESERVE_BLOCK` сжат с 9 anchors до 4 (face shape, eye
  shape/colour, hairline, skin undertone) — освободившийся attention
  budget уходит на cinematic composition выше.
* `PHOTOREAL_BLOCK` сменил `50mm lens at eye level` (канонический
  «selfie perspective») на `85mm portrait lens at chest height`
  (канонический portrait-photography setup, который сжимает
  перспективу и даёт естественные пропорции).
* Opener `_dating_social_change_instruction` получил positive-framed
  proportions clause `Recompose the body so head, shoulders and
  torso read at natural human proportions` — первое предложение
  теперь несёт anatomy-директиву, что важнее всего на FAL Nano
  Banana 2 / GPT Image 2 Edit (highest-attention позиция).

#### 2. Auto-framing resolver (v1.65)

[src/services/composition_safety.py](../src/services/composition_safety.py):
новая функция `resolve_effective_framing` — единый источник истины
для «какой framing на самом деле уйдёт в модель». Используется и в
executor'е, и в боте.

Приоритет:

1. Document style → `portrait` (vendor policy, не торгуется).
2. `user_framing`, если он in `allowed_framings(composition_class)`.
3. `spec.needs_full_body` → `full_body`, если он in allowed.
4. Первый канонический framing в `(portrait, half_body, full_body)`,
   который in allowed.
5. Fail-closed-safe → `portrait`.

[src/orchestrator/executor.py](../src/orchestrator/executor.py)
больше не хардкодит `half_body` для пустого / невалидного framing'а
— решение принимает resolver. `result_dict["resolved_framing"]` и
`user_picked_framing` пишутся для UI и observability.

#### 3. Reference padding для tight selfies (v1.64 + v1.65 расширение)

[src/services/reference_preprocess.py](../src/services/reference_preprocess.py):
`pad_reference_for_framing(image_bytes, face_bbox, framing,
target_size)` — пересобирает исходник на новом холсте так, чтобы
**лицо уже было в нужной пропорции** до того, как байты уходят в
edit-модель. Алгоритм:

1. Из `face_bbox` (InsightFace, доступен из `InputQualityReport`)
   вычисляется текущая высота лица.
2. По `_FRAMING_GEOMETRY[framing]` находится target face height
   (28/15/8% canvas height) и target center Y (0.30/0.20/0.12).
3. Исходник ресайзится так, чтобы лицо достигло target size, и
   ставится на новый canvas. Пустые области заполняются
   edge-blur'ом — нейтральный фон, который модель легко перепишет.
4. Возвращаются JPEG-байты — провайдер их получает как обычный
   `reference_image`.

Числа в `_FRAMING_GEOMETRY` синхронизированы с текстовой доктриной
выше: `face_height_ratio=0.28` ≡ «upper quarter of the canvas» в
портретном anchor'е и т.д.

#### Гейт применения (v1.65)

[src/orchestrator/executor.py](../src/orchestrator/executor.py) вызывает
padding **только** когда:

```python
is_tight = (
    composition_class in ("face_closeup", "unknown")
    or face_area_ratio > settings.csl_reference_pad_face_ratio   # 0.28
)
should_pad = (
    settings.csl_reference_pad_enabled         # kill-switch
    and not _is_document                        # документы не трогаем
    and framing_norm in ("portrait", "half_body", "full_body")
    and is_tight
    and iq_bbox is not None                     # без bbox padding невозможен
)
```

v1.65 расширил gate на `portrait` (главный фикс скриншотов — раньше
самый частый кейс «дефолт portrait + tight selfie» не паддился) и
выделил отдельный, более мягкий порог `csl_reference_pad_face_ratio`
(0.28) — он не зависит от CSL FACE_CLOSEUP threshold (0.35), так
что padding срабатывает на portrait-class загрузках с выше-средним
лицом, где «огромная голова» проявляется без формального FACE_CLOSEUP.

Любая ошибка `pad_reference_for_framing` → fallback на raw байты + log.
Метрика [`reference_padded_total`](../src/metrics.py)
`{framing, composition_class}` показывает фактический объём.

#### 4. Soft VLM warning (v1.65)

Когда VLM-gate возвращает `proportions_natural=false`, executor
добавляет user-facing notice «На фото пропорции тела могут выглядеть
необычно. Попробуй фото, где видно плечи и часть торса.» —
**без retry**, фото отдаём как есть. Стоимость = $0.

#### 5. Style Catalog Normalization (v1.66)

После раскатки v1.65 одна аномалия осталась: на CV/career стилях
(`legal_finance`, `boardroom`, `corporate`, `decision_moment`,
`speaker_stage`, `intellectual`, …) пропорции по-прежнему ломались,
тогда как на lifestyle/sport стилях (`gym_fitness`, `dating_park`,
`hiking`) — нет. Корневая причина: `expression`/`scene_anchor` в
`data/styles.json` кодировали **скрытые portrait-pose директивы**
(`Authoritative steady expression`, `distinguished gravitas`,
`leadership gaze`, `executive vision`, `leather chair`, `behind a
desk`, `webcam-friendly framing`), которые семантически конкурировали
с cinematic-якорем v1.65 и побеждали из-за recency bias.

v1.66 нормализует каталог одним проходом через
[`scripts/migrations/2026_05_styles_v4_anatomy/migrate.py`](../scripts/migrations/2026_05_styles_v4_anatomy/migrate.py):

* **33 non-studio стиля** получили переписанные `expression`/
  `scene_anchor`/`background.base`: portrait-pose токены заменены на
  lifestyle-формулировки (`Confident relaxed expression, settled
  direct gaze, natural mouth line, shoulders visible in frame`).
* **Studio-portrait whitelist** `_STUDIO_PORTRAIT_STYLE_KEYS =
  {formal_portrait, studio_elegant}` в
  [`src/prompts/image_gen.py`](../src/prompts/image_gen.py) — у этих
  стилей portrait-pose phrasing легитимна (по дизайну headshot
  + Rembrandt) и сохраняется как есть.
* **PHOTOREAL_BLOCK** переписан: `85mm portrait lens` →
  `85mm short-telephoto lens`. Дублирующее слово `portrait` в
  промпте создавало recency-bias headshot pull, который перевешивал
  cinematic `bust shot` anchor.
* **CV-mode padding boost**: `csl_reference_pad_face_ratio_cv = 0.22`
  (vs default 0.28) специально для CV-режима — паспорт-стиль селфи
  чаще лежат прямо на границе `face_closeup`/`portrait`. Studio-portrait
  стили освобождены от boost'а (они и должны быть tight headshot).
* **Lint-защита**: новые правила `EXPRESSION_PORTRAIT_LEAK` /
  `SCENE_POSE_LEAK` (error-severity) и `WARDROBE_TIGHT_SUIT`
  (warning) в [`src/services/style_lint.py`](../src/services/style_lint.py)
  блокируют возврат токенов в CI. Exempt-список совпадает со studio-
  whitelist + document keys.
* **Resolver short-circuit**: studio-portrait стили теперь принудительно
  возвращают `framing=portrait` из `resolve_effective_framing`
  (зеркало document-style behaviour) — даже если CSL классифицирует
  upload как `full_body`.

Стоимость генерации не меняется: все правки — token-substitution
равной длины или короче, CV-padding boost — это preprocess.

Резервная копия `data/styles.json.bak.v165` создаётся автоматически
при первом запуске миграции; rollback = `cp .bak.v165 styles.json`.

#### 6. Padding Gate Audit & Identity Tail (v1.67)

После выкладки v1.66 production-аудит подтвердил, что «огромная
голова» **остаётся** на стандартных half-body аплоадах
(`mirror_aesthetic`, `legal_finance`, `executive_portrait`),
хотя `gym_fitness` и подобные body-cued стили выдают правильные
пропорции. Корневая диагностика — **структурная**, не контентная:

1. **Padding gate dead-zone.** v1.65/v1.66 padding активировался при
   `composition_class ∈ {face_closeup, unknown}` ИЛИ `face_area_ratio
   > 0.28` (или `> 0.22` для CV). Самая частая форма аплоада —
   полупортрет с `face_area_ratio ≈ 0.10..0.17` и `composition_class
   = PORTRAIT` — проваливалась мимо **обоих** триггеров. Без padding
   edit-модель получала сырой reference и копировала его head/torso
   ratio один-в-один; cinematic `Reframe …` директива не могла
   победить визуальный сигнал.
2. **Identity-block placement.** v1.65 ставил
   `IDENTITY_PRESERVE_BLOCK` сразу после cinematic anchor, со
   формулировкой `identical face shape, eye shape and colour …`.
   Edit-модели читали `identical face shape` **геометрически** — как
   «сохрани относительный размер головы из reference в кадре» —
   что напрямую конфликтовало с composition-якорем. Identity
   побеждал из-за позиции (early-attention) и emphatic слова
   (`identical`).

Контрольное наблюдение из аудита: `gym_fitness` работал без
проблем потому, что его `default_clothing` содержит **обязательную
body-геометрию** (`athletic tank top, athletic shorts, training
shoes`) — модель физически не может нарисовать `shoes`, не
расширив кадр на ноги, и пропорции выправляются автоматически.
Стили с слабыми body-cues (`mirror_aesthetic`: *"curated outfit with
clean lines, one statement piece"*) такой страховки не имеют.

v1.67 закрывает обе структурные дыры — без нового FAL-роундтрипа и
без правок контента стилей:

* **Padding gate расширен** (`src/orchestrator/executor.py`,
  `src/config.py`):
  - `is_tight` теперь включает `composition_class ∈ {face_closeup,
    portrait, half_body, unknown}` (раньше только `{face_closeup,
    unknown}`).
  - `csl_reference_pad_face_ratio` и `csl_reference_pad_face_ratio_cv`
    оба опущены до `0.10` (раньше 0.28 / 0.22). CV-boost схлопнулся
    в main threshold — оба режима нуждались в одинаково низком гейте.
  - Единственный путь, который теперь минует padding — это true
    `FULL_BODY` композиционный класс (лицо < 6% кадра, много места
    под подбородком). Document-стили освобождены отдельно по
    `framing` gate; studio-portrait стили резолвятся в `portrait`
    framing и padding для них работает в нужном tight-bust режиме.
* **Identity-tail reorder** (`src/prompts/model_wrappers.py`):
  `IDENTITY_PRESERVE_BLOCK` перенесён из «после composition anchor»
  в самый конец промпта, после `PHOTOREAL_BLOCK`. Composition теперь
  владеет early-attention слотом, identity — recency-bias слотом.
* **Identity wording rewrite** (`src/prompts/image_gen.py`):
  `IDENTITY_PRESERVE_BLOCK` переписан как чисто-текстурный:
  `"preserve the same person's facial features: eye shape and
  colour, hairline, skin undertone"`. Слово `face shape` (геометрия)
  удалено; слово `identical` (emphatic geometric copy cue) заменено
  на нейтральный `preserve`.

Стоимость генерации не меняется: padding — локальный PIL preprocess,
prompt reorder сохраняет тот же набор токенов, identity rewrite
короче на 9 символов. Default A/B model и quality tier
(`gpt_image_2` / `medium`, $0.06/image) не трогаются.

Регрессионная защита: новые тесты
`test_pad_fires_on_typical_half_body_upload_v167` и
`test_pad_fires_on_half_body_class_at_low_ratio_v167` в
[`tests/test_orchestrator/test_executor_reference_padding.py`](../tests/test_orchestrator/test_executor_reference_padding.py)
пинят оба плеча гейта. Прежний `test_executor_padding_cv_mode.py`
(v1.66) удалён — он пинил CV-vs-default divergence, которой
после v1.67 больше нет.

#### Почему это работает за один проход

- **Edit-модели** (GPT Image 2 / Nano Banana 2) сильно опираются на
  layout reference'а. Если на reference'е лицо уже занимает 12%
  кадра, модель **не** может «вернуть» его к 50% без явного промпта.
- Cinematic anchor (`Reframe …`, `85mm short-telephoto lens`) + padded
  reference дают согласованный сигнал в обоих каналах (text + image),
  а identity-tail с текстурными якорями убирает остаточную тягу к
  head-and-shoulders, не загораживая composition.

#### Что убрано вместе с v1.64

PuLID (`fal-ai/pulid`), Seedream (`fal-ai/bytedance/seedream-v4`),
Reve (`api.reve.com`), StyleRouter (legacy роутер по
`generation_mode`), `src/services/face_crop.py` (нужен был только
PuLID-провайдеру), `_SCENE_PRESERVE_STYLE_KEYS`,
`detect_generation_mode`, `STYLE_MODE_OVERRIDE` метрика, `style_mode`
лейбл из `IMAGE_GEN_BACKEND`. Эти ветки физически не выполнялись в
проде после v1.21 (A/B-роутер всегда возвращал `gpt_image_2` /
`nano_banana_2` **до** проверки `generation_mode` в
`UnifiedImageGenProvider._pick_backend`), и держать ~7 файлов dead
code'а не было смысла. После cleanup'а primary стек строго
**FAL-only с двумя моделями** (GPT Image 2 Edit + Nano Banana 2 Edit),
выбираемыми A/B-роутером в [src/providers/factory.py](../src/providers/factory.py).

---

## 9. Известные риски и ограничения

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

## 10. Ссылки

* План: [.cursor/plans/two-region_clean_architecture_e2849f1e.plan.md](../.cursor/plans/two-region_clean_architecture_e2849f1e.plan.md)
* External checklist: [docs/VARIANT_B_EXTERNAL_CHECKLIST.md](VARIANT_B_EXTERNAL_CHECKLIST.md)
* DNS runbook: [docs/DNS_CUTOVER_RUNBOOK.md](DNS_CUTOVER_RUNBOOK.md)
* Деплой: [.cursor/rules/deploy.mdc](../.cursor/rules/deploy.mdc)
* CSL модули: [src/services/composition_safety.py](../src/services/composition_safety.py),
  [src/services/body_landmarks.py](../src/services/body_landmarks.py),
  [src/services/reference_preprocess.py](../src/services/reference_preprocess.py),
  [scripts/calibrate_composition_thresholds.py](../scripts/calibrate_composition_thresholds.py)
