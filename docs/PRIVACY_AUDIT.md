# PRIVACY AUDIT — RateMeAI (pre v1.10)

Аудит обработки персональных данных (фото лиц пользователей и связанных метаданных) в архитектуре RateMeAI до внедрения privacy/compliance слоя. Документ фиксирует точки обработки ПДн, полный lifecycle изображения и выявленные риски.

## 1. Точки входа изображений

| Канал | Endpoint / обработчик | Файл | Формат |
|-------|----------------------|------|--------|
| Web SPA | `POST /api/v1/analyze` | [src/api/v1/analyze.py](../src/api/v1/analyze.py) | multipart/form-data |
| Web SPA | `POST /api/v1/pre-analyze` | [src/api/v1/pre_analyze.py](../src/api/v1/pre_analyze.py) | multipart/form-data |
| Telegram | `F.photo` / `F.document` handler | [src/bot/handlers/photo.py](../src/bot/handlers/photo.py) | Telegram `file_id` → байты |
| Edge → Primary | `POST /api/v1/internal/process-analysis` | [src/api/v1/internal.py](../src/api/v1/internal.py) | base64 JSON |
| Edge → Primary | `POST /api/v1/internal/pre-analyze` | [src/api/v1/internal.py](../src/api/v1/internal.py) | base64 JSON |
| B2B API | `POST /api/v1/analyze` (+ `X-API-Key`) | [src/api/v1/analyze.py](../src/api/v1/analyze.py) | multipart/form-data |

## 2. Lifecycle изображения (до внедрения privacy-слоя)

```
Upload  →  (1) HTTP handler  →  (2) storage.upload(inputs/{user}/{uuid}.jpg)
                               →  (3) Redis task_input:{id} (TTL 3600s, base64)
                               →  (4) DB tasks.input_image_path = key (бессрочно)
                               ↓
ARQ worker  →  (5) redis.get(task_input) | fallback: storage.download
             →  (6) validate_and_normalize (PIL, EXIF теряется как побочка)
             →  (7) pipeline.execute
                    ├── LLM Analysis (OpenRouter Vision, base64) — США/ЕС
                    ├── IdentityService.compute_embedding → Redis embedding:{id} (TTL 30 min)
                    ├── Image Gen (Reve / Replicate) — внешние сервисы
                    └── DeltaScorer (по окончании генерации)
             →  (8) storage.upload(generated/{user}/{task}.jpg)
             →  (9) Redis gen_image:{id} (TTL 259200s = 72h)
             →  (10) DB tasks.result = {generated_image_url, scores, ...} (бессрочно)
             ↓
Deferred ARQ job compute_delta_scores (~30s позже)
             →  (11) storage.download(task.input_image_path)  — повторное чтение оригинала
             →  (12) LLM re-analysis + authenticity через embedding
```

## 3. Места хранения ПДн (все артефакты)

### Оригинал
| Артефакт | TTL | Где удаляется |
|----------|-----|----------------|
| `storage://inputs/{user}/{uuid}.jpg` | ∞ (в обычном flow) | Только если `policy_flags.delete_after_process=True` (сейчас — только edge → primary задачи) |
| Redis `ratemeai:task_input:{id}` | 3600s | `_cleanup_ephemeral_artifacts` после завершения |
| DB `tasks.input_image_path` | ∞ | Никогда, только CASCADE при `DELETE users` |

### Результат генерации
| Артефакт | TTL | Где удаляется |
|----------|-----|----------------|
| `storage://generated/{user}/{task}.jpg` | ∞ | Только при `delete_after_process` (edge only) |
| Redis `ratemeai:gen_image:{id}` | 259200s (72h) | TTL |
| DB `tasks.result.generated_image_url` | ∞ | Никогда |
| DB `tasks.share_card_path` (share-card PNG) | ∞ | Никогда |

### Производные / временные
| Артефакт | TTL | Комментарий |
|----------|-----|-------------|
| Redis `ratemeai:embedding:{id}` | 1800s (30 min) | InsightFace ArcFace 512-float vector, base64 numpy |
| Redis `ratemeai:preanalysis:{hash}` | 600s (10 min) | LLM результат первичного анализа |
| Redis `ratemeai:llm_cache:{market}:{mode}:{sha256}` | 600s (10 min) | Кеш vision-анализа по SHA256 изображения |
| DB `tasks.context.artifact_refs.market_input_path` | ∞ | Содержит имя storage-ключа оригинала |
| DB `user_perception_records` | ∞ | Агрегаты восприятия (не-идентифицирующие скоры) |

## 4. Точки отправки во внешние AI-сервисы

| Провайдер | Юрисдикция хостинга | Передаётся | Основание передачи |
|-----------|---------------------|-----------|--------------------|
| OpenRouter (Gemini / GPT-4o vision) | США | base64 JPEG (normalized) | `OPENROUTER_API_KEY` → POST `/chat/completions` |
| Reve API | США | bytes JPEG (normalized) | Официальный Python SDK (sync HTTP) |
| Replicate API | США | URL reference + prediction polling | Upload reference → prediction poll |

Во всех трёх случаях до внедрения privacy-слоя **отсутствует проверка согласия пользователя на трансграничную передачу**. Передача выполняется безусловно, если у пользователя есть кредиты.

## 5. Trans-border (Edge → Primary)

RU edge на VPS (`ru.ailookstudio.ru`) → primary на Railway (eu-west) через `RemoteAIService` ([src/services/remote_ai.py](../src/services/remote_ai.py)):
- `POST /internal/process-analysis` c `image_b64`.
- Уже присутствует механизм `policy_flags.delete_after_process=True` + `data_class="regional_photo"`, но без проверки consent.

## 6. Согласия (до внедрения)

- **Web SPA** — согласие НЕ собирается. `StepUpload` сразу открывает file picker.
- **Telegram** — согласие НЕ собирается. `handle_photo` принимает фото и сразу ставит в pipeline.
- **B2B API** — согласие НЕ декларируется в контракте. Клиент обязан только иметь `X-API-Key`.
- **Edge → Primary** — `policy_flags` передаются, но `consent_*` флагов нет.

## 7. Логирование и кеширование

### Логи
- `RequestLoggingMiddleware` ([src/api/middleware.py](../src/api/middleware.py)): method, path, status, correlation_id, elapsed. Тела запросов не логируются.
- Worker/pipeline: `logger.info` с task_id, user_id, mode, similarity score, gate results. Содержимое изображений **не** логируется.
- В prod JSON-logger (`python-json-logger`) без специальных PII-фильтров.
- **Риск**: нет формального гаранта (фильтра) того, что случайный `logger.debug(image_bytes)` не попадёт в продакшен.

### Кеши
- LLM-cache по SHA256 изображения: `ratemeai:llm_cache:{market}:{mode}:{hash}:{profession}` (TTL 10 min). Привязан к изображению косвенно (через hash), не к user_id.
- Pre-analysis cache: `ratemeai:preanalysis:{pre_id}` (TTL 10 min).
- Gen image cache: `ratemeai:gen_image:{id}` (TTL 72h).

## 8. Выявленные риски (до внедрения)

| # | Риск | Критичность |
|---|------|-------------|
| R1 | Оригинал фото хранится в `inputs/*` и DB бессрочно в основном flow | Высокая |
| R2 | Отсутствие consent flow → обработка ПДн без правового основания (152-ФЗ ст.9, GDPR Art.6) | Высокая |
| R3 | Трансграничная передача во внешние AI без явного согласия (152-ФЗ ст.12) | Высокая |
| R4 | EXIF (GPS, device UUID) удаляется только как побочка PIL re-encode — без гарантии | Средняя |
| R5 | `GET /tasks` возвращает `input_image_url` на оригинал — постоянно доступен | Средняя |
| R6 | Результаты (`generated/*`, `share_card_path`, `task.result`) не имеют TTL — хранятся бессрочно | Средняя |
| R7 | `compute_delta_scores` повторно читает оригинал через 30+ секунд — блокер удаления после preprocessing | Высокая |
| R8 | Нет PII-фильтра на уровне root-logger | Низкая |
| R9 | Edge → primary передаёт фото без `consent_ai_transfer` флага | Средняя |

## 9. Целевая модель (реализуется в privacy-compliance-layer)

- Два обязательных opt-in согласия: `data_processing` + `ai_transfer` (split consent).
- Оригинал НЕ пишется в `inputs/*`; живёт только в памяти worker + коротком Redis stash (TTL 15 min).
- InsightFace embedding становится основным persistent-объектом (Redis TTL 72h).
- `DeltaScorer` — embedding-only (без re-download оригинала).
- Cron `privacy_gc_cron` удаляет `generated/*` + `share_card_path` + зануляет URL в `task.result` через 72h.
- PII-фильтр в root-logger + redaction base64 в request-middleware.
- `ai_transfer_guard` через `ContextVar` — жёсткий block вызовов внешних AI без consent_ai_transfer.

См. план `privacy-compliance-layer` в `.cursor/plans/` и раздел 17 в [docs/ARCHITECTURE.md](ARCHITECTURE.md).
