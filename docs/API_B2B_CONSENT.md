# B2B API: обязательные consent-заголовки

Для любого запроса к `POST /api/v1/analyze` и `POST /api/v1/pre-analyze` API-клиент должен подтвердить, что конечный пользователь дал согласие на:

1. **Обработку персональных данных** (включая фото лица).
2. **Трансграничную передачу фото во внешние AI-сервисы** (OpenRouter, Reve, Replicate).

Согласия требуются по ст. 9 и ст. 12 152-ФЗ РФ и не могут быть отключены.

## Варианты интеграции

### Вариант A: inline-заголовки (recommended для B2B)

Клиент отправляет оба заголовка при каждом вызове `/analyze` / `/pre-analyze`:

```
X-API-Key: <ваш ключ>
X-Consent-Data-Processing: 1
X-Consent-AI-Transfer: 1
```

При первом вызове сервер автоматически запишет грант в таблицу `user_consents` со `source=api_header` (с SHA256 IP и User-Agent) и кэширует активное состояние на 1 час. Повторные вызовы без заголовков продолжат работать, пока согласие не отозвано.

### Вариант B: предварительный grant

Вызовите один раз:

```
POST /api/v1/users/me/consents
Authorization: Bearer <session_token>
Content-Type: application/json

{
  "kinds": ["data_processing", "ai_transfer"],
  "source": "b2b_integration"
}
```

Ответ:

```json
{
  "required": ["data_processing", "ai_transfer"],
  "granted": {
    "data_processing": {"version": "1", "granted_at": "…", "source": "b2b_integration"},
    "ai_transfer":     {"version": "1", "granted_at": "…", "source": "b2b_integration"}
  },
  "missing": [],
  "current_version": "1"
}
```

Далее `/analyze` / `/pre-analyze` работают без дополнительных заголовков.

## Отзыв

```
POST /api/v1/users/me/consents/revoke
{"kinds": ["ai_transfer"]}
```

После отзыва `ai_transfer` любой `/analyze` начнёт отдавать `451` до нового гранта.

## Коды ответов

| Код | Когда | Тело |
|-----|-----|-----|
| `202` | Задача принята | `{task_id, status, estimated_seconds}` |
| `402` | Нет кредитов | `{detail: "no_credits"}` |
| `451` | Нет одного из обязательных согласий | `{detail: {code: "consent_required", missing: [...], required: [...]}}` |

Пример 451-ответа:

```json
{
  "detail": {
    "code": "consent_required",
    "missing": ["ai_transfer"],
    "required": ["data_processing", "ai_transfer"]
  }
}
```

## Гарантии Privacy Layer (что мы делаем с загруженным фото)

1. EXIF / ICC / GPS / XMP удаляются при нормализации.
2. Оригинальные байты **никогда** не попадают в durable storage (S3 / файловая система). Они живут только в памяти и в Redis stash (TTL 15 минут).
3. ArcFace embedding кэшируется на 72 часа — это единственный долгоживущий идентичностный артефакт; он используется для delta-scoring и не даёт воссоздать оригинал.
4. Сгенерированное изображение хранится 72 часа, после чего физически удаляется GC-воркером (`privacy_gc_cron`). В `GET /tasks/{id}` появится `result.purged: true`.
5. Логи не содержат байтов / base64 / UUID — их автоматически маскирует `PIIFilter`.

## Рекомендации по дизайну клиента

- Покажите конечному пользователю текст согласий **до** первого вызова API.
- Сохраняйте локально метку «согласие получено» + дату, чтобы не отправлять заголовки без реального согласия пользователя.
- В случае 451 разбирайте `detail.missing` и показывайте пользователю соответствующий чекбокс.
- Не кэшируйте `generated_image_url` дольше 72 часов — после GC он станет недоступным.
