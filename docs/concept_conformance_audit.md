# Concept Conformance Audit [ARCHIVED]

> **ARCHIVED:** This audit was created against v1.2.x and is superseded by v1.3.x changes.
> Many findings below (no embeddings, no multi-pass, no quality gates, bot language issues)
> have been addressed. Retained for historical reference only.

## Аудит соответствия RateMeAI продуктовой конституции

**Дата:** 2026-04-06
**Baseline:** Master Product Constitution v1 (AI Stylist + FLUX Pipeline Concept)
**Метод:** сопоставление каждого раздела конституции с текущей реализацией через code-backed evidence.

---

## Сводная матрица соответствия

| # | Раздел конституции | Статус | Критичность gap |
|---|-------------------|--------|----------------|
| 1 | Core Concept: AI Stylist позиционирование | ЧАСТИЧНО | P0 |
| 2 | Non-Negotiable: реализм и идентичность | ЧАСТИЧНО | P0 |
| 3 | UX принципы и flow | ЧАСТИЧНО | P0 |
| 4 | Language System (микрокопирайтинг) | НЕ СООТВЕТСТВУЕТ | P0 |
| 5 | Preset System (каталог образов) | ЧАСТИЧНО | P1 |
| 6 | Scoring System | ЧАСТИЧНО | P1 |
| 7 | Image Pipeline | НЕ СООТВЕТСТВУЕТ | P0 |
| 8 | Game Mechanics и Retention | ЧАСТИЧНО | P1 |
| 9 | Monetization | ЧАСТИЧНО | P0 |
| 10 | Observability | НЕ СООТВЕТСТВУЕТ | P1 |

---

## 1. CORE CONCEPT: AI STYLIST ПОЗИЦИОНИРОВАНИЕ

### Требование конституции

Продукт — AI-стилист, который показывает варианты восприятия в разных контекстах. Не судья, не генератор. Мягкий тон coach/stylist.

### Текущее состояние

**Частичное соответствие.**

Позитивные аспекты:
- Welcome-текст ведет с анализа восприятия: `"анализирует, как тебя воспринимают по фото"` (`src/bot/handlers/start.py`, L15).
- Режимы привязаны к жизненным сценариям: Rating, Dating, CV (`src/models/enums.py`).

Конфликтные аспекты:
- Продукт позиционирует себя как **оценщик** (`"честная оценка 0-10 с разбором"`, `start.py` L18), что ближе к judge-модели, чем к stylist.
- Нет AI Stylist entry point: вместо `"Я — твой AI-стилист"` бот начинает с `"Просто отправь мне фото"` (L23).
- Emoji-режим (`"пак стикеров с твоим лицом"`, L21) — cartoon/sticker, что конфликтует с фотореалистичным ядром продукта.

### Evidence

```
src/bot/handlers/start.py L15-25: WELCOME_TEXT
src/bot/handlers/results.py L206: "Рейтинг: {score}/10" — оценочная подача
src/prompts/image_gen.py L73-83: build_emoji_prompt — cartoon sticker, не photoreal
```

### Рекомендации

- **P0:** переформулировать WELCOME_TEXT из judge в stylist: `"Я покажу, как тебя воспринимают и как можно усилить образ"`.
- **P0:** убрать или перепозиционировать emoji-режим из основного потока.
- **P1:** добавить AI Stylist entry-сообщение перед выбором режима.

---

## 2. NON-NEGOTIABLE: РЕАЛИЗМ И ИДЕНТИЧНОСТЬ

### Требование конституции

100% узнаваемость. Фотореализм. Identity lock. Запрещены изменения формы лица. Quality gates с face similarity.

### Текущее состояние

**Частичное соответствие.**

Позитивные аспекты:
- Промпт `FACE_ANCHOR` в `src/prompts/image_gen.py` (L8-12) содержит детальный identity lock: `"preserve exact face shape, nose, eyes, eyebrows, lips, jawline, chin, ears, cheekbones, forehead. Do NOT reshape or reposition any facial feature"`.
- Промпт `REALISM` (L21-24): `"must look like a real high-end photograph. No AI artifacts, no painterly effects"`.
- Промпт `SKIN_FIX` (L14-18): `"Keep realistic texture — no plastic or airbrushed look"`.

Критичные gaps:
- **Все это — prompt-level только.** Нет verification на выходе.
- Нет face embeddings и cosine similarity check.
- Нет artifact detection на результате.
- `enhancement` metadata (`pipeline.py` L110-123) содержит `"identity_preservation": "strict"` и `"photorealism_check": "enforced"` — это **статические строки**, не результат реальных проверок.
- `has_face_heuristic()` в `src/utils/image.py` — проверяет только aspect ratio, не реальное лицо.
- Reve provider перехватывает `content_violation` (L в `reve_provider.py`), но это модерация контента, не identity verification.

### Evidence

```
src/prompts/image_gen.py L8-24: FACE_ANCHOR, SKIN_FIX, REALISM — prompt-only constraints
src/orchestrator/pipeline.py L104-123: static enhancement metadata, no real verification
src/orchestrator/pipeline.py L104: if raw and len(raw) > 100 — единственная "проверка" качества
src/utils/image.py: has_face_heuristic — aspect ratio only
```

### Рекомендации

- **P0:** интегрировать face embedding service (ArcFace), вычислять embedding на входе.
- **P0:** добавить post-generation similarity check с threshold и rejection.
- **P1:** заменить static enhancement metadata на реальные метрики.
- **P1:** заменить `has_face_heuristic` на real face detection.

---

## 3. UX ПРИНЦИПЫ И FLOW

### Требование конституции

Один экран — одна цель. 3-5 вариантов. Целевой flow: upload -> stylist entry -> мягкий анализ -> выбор направления -> результат с объяснением -> следующие образы.

### Текущее состояние

**Частичное соответствие.**

Позитивные аспекты:
- Flow в целом следует паттерну: photo -> mode select -> style select -> result.
- Количество кнопок в keyboards разумное: 4 режима, 3 стиля per mode (`src/bot/keyboards.py`).
- Loop keyboard (`keyboards.py` L52-75) дает возможность «попробовать еще» (restyle, loop).

Конфликтные аспекты:
- Нет AI Stylist entry point (шаг 2 из целевого flow отсутствует).
- Нет мягкого первичного анализа текущего образа (шаг 3 отсутствует — сразу запрос на режим).
- Результат rating не содержит объяснения, что можно улучшить, в терминах образов.
- После результата нет предложения «попробовать другие образы» в терминах stylist.

### Evidence

```
src/bot/handlers/photo.py: после загрузки фото -> сразу mode_selection_keyboard
src/bot/keyboards.py L6-16: mode_selection_keyboard — 4 кнопки без stylist entry
src/bot/handlers/results.py L195-233: _send_rating — score + perception, без "хочешь попробовать образ?"
src/bot/keyboards.py L52-75: loop_keyboard — есть restyle, но framing как "другой стиль", не "другой образ"
```

### Рекомендации

- **P0:** добавить AI Stylist entry message после загрузки фото.
- **P1:** добавить мягкий первичный анализ перед выбором режима.
- **P1:** переформулировать loop keyboard в терминах «образов», а не «стилей».

---

## 4. LANGUAGE SYSTEM (МИКРОКОПИРАЙТИНГ)

### Требование конституции

Запрещены: «сгенерировать», «генерация», «фильтр», «сделать красивее», критика.
Обязательны: «образ», «усилим восприятие», «подходит для...», «дает +X к...».

### Текущее состояние

**НЕ СООТВЕТСТВУЕТ. Основной конфликт: вся монетизация и баланс завязаны на слово «генерация».**

Полный список конфликтных user-facing строк:

| Строка | Файл | Строка кода |
|--------|------|-------------|
| `"баланс генераций"` | `start.py` | L25 |
| `"Баланс: {credits} генераций"` | `start.py` | L58, L81 |
| `"Купи пакет, чтобы генерировать фото!"` | `start.py` | L60 |
| `"Отправь фото для генерации!"` | `start.py` | L63 |
| `"Кредиты для генерации закончились!"` | `mode_select.py` | L179 |
| `"Пакет: {qty} генераций за {price} ₽"` | `mode_select.py` | L229 |
| `"Доступно генераций: {credits}"` | `mode_select.py` | L253 |
| `"Купи пакет, чтобы генерировать фото!"` | `mode_select.py` | L256 |
| `"Отправь фото для генерации!"` | `mode_select.py` | L260 |
| `"Генерация фото недоступна — закончились кредиты."` | `results.py` | L259, L312, L360 |
| `"Баланс: 0 генераций"` | `results.py` | L184 |
| `"Баланс: {credits} генераций"` | `results.py` | L189 |
| `"{qty} фото-генераций"` (YooKassa description) | `services/payments.py` | L77 |
| `"{qty} фото — {price} ₽"` (pack label) | `services/payments.py` | L23 |
| `"Выбери стиль фото"` | `mode_select.py` | L38, L40, L68, L70, L98, L100 |

Также:
- `"честная оценка 0-10"` (start.py L18) — judge framing.
- `"оформи Premium!"` (mode_select.py L185) — при том, что Premium не продается через payment flow.

### Evidence

```
src/bot/handlers/start.py L25,58,60,63,81: "генерация/генераций" повсюду в balance-текстах
src/bot/handlers/mode_select.py L179,229,253,256,260: "генерация" в payment/balance flow
src/bot/handlers/results.py L184,189,259,312,360: "генерация" в результатах
src/services/payments.py L23,77: "фото-генераций" в YooKassa и pack labels
```

### Рекомендации

- **P0:** глобальная замена «генерация/генераций» на «улучшение/образ» во всех user-facing строках.
- **P0:** переформулировать paywall: `"Открой все стили и образы"` вместо `"Купи пакет генераций"`.
- **P0:** убрать `"честная оценка"` из welcome, заменить на stylist-framing.
- **P0:** убрать ссылку на Premium (`mode_select.py` L185) или привязать к реальному продукту.

---

## 5. PRESET SYSTEM (КАТАЛОГ ОБРАЗОВ)

### Требование конституции

Пресет = жизненный сценарий. Категории: Dating Stylist (friendly/confident/charismatic), Career Stylist (corporate/startup/creative), Social Stylist (расширение). Каждый пресет с практическим применением, delta, объяснимостью.

### Текущее состояние

**Частичное соответствие.**

Позитивные аспекты:
- Dating styles (`src/prompts/image_gen.py` L26-36): warm_outdoor, studio_elegant, cafe + personalities: friendly, confident, charismatic.
- CV styles (L38-48): corporate, creative, neutral + personalities.
- Keyboards привязывают стили к жизненным контекстам: `"На прогулке"`, `"Корпоративный"`.

Конфликтные аспекты:
- Нет Social Stylist категории (influencer, luxury, casual).
- Framing через `"стиль фото"` (mode_select.py), а не `"образ"` или `"сценарий"`.
- Результат не объясняет, что изменено в образе: `_send_dating` показывает score + impression, но без `"Что изменено: ... Как воспринимается: ..."`.
- Loop keyboard (`keyboards.py` L58): `"Привлекательнее"` и `"Другой стиль"` — не в терминах образов.

### Evidence

```
src/prompts/image_gen.py L26-48: dating/cv styles+personalities — хорошая база
src/bot/keyboards.py L19-32: dating/cv style keyboards — привязаны к контексту
src/bot/keyboards.py L58-59: loop actions — "Привлекательнее" / "Другой стиль", не "образ"
src/bot/handlers/results.py L236-284: _send_dating — нет блока "что изменено"
```

### Рекомендации

- **P1:** переименовать «стиль фото» -> «образ» в UX-текстах.
- **P1:** добавить в результат блок «Что изменено / Как воспринимается».
- **P2:** добавить Social Stylist категорию (influencer, luxury, casual).
- **P1:** переформулировать loop keyboard: `"Более уверенный образ"` вместо `"Привлекательнее"`.

---

## 6. SCORING SYSTEM

### Требование конституции

Скор = восприятие в контексте. Стабилен, воспроизводим, объясним. Delta обязательна. Привязка к практической применимости.

### Текущее состояние

**Частичное соответствие.**

Позитивные аспекты:
- Rating service (`src/services/rating.py`) выдает score + perception subscores (trust, attractiveness, emotional_expression).
- Dating service выдает dating_score + first_impression + strengths.
- CV service выдает trust + competence + hireability.
- Скоры привязаны к контекстам восприятия.

Критичные gaps:
- **Delta отсутствует:** скор вычисляется только для входного фото. Выходное изображение не оценивается повторно.
- **Воспроизводимость:** LLM temperature = 0.7 в `src/providers/llm/openrouter.py` — стохастический результат.
- **Стабильность:** нет multi-sample consensus. Один и тот же фото может дать разный скор при повторных запросках.

### Evidence

```
src/services/rating.py: score на входном фото
src/services/dating.py: dating_score на входном фото
src/services/cv.py: trust/competence/hireability на входном фото
src/orchestrator/pipeline.py: _generate_image() не вызывает повторный scoring
src/providers/llm/openrouter.py: temperature=0.7 — stochastic
```

### Рекомендации

- **P1:** добавить post-generation re-scoring (второй вызов LLM на выходном фото).
- **P1:** вычислять delta = post_score - pre_score и показывать пользователю.
- **P2:** снизить temperature для scoring calls (0.1-0.3) для воспроизводимости.
- **P2:** рассмотреть multi-sample consensus (3 вызова, median).

---

## 7. IMAGE PIPELINE

### Требование конституции

Multi-pass orchestrated pipeline. Identity Anchor (ArcFace). Selective editing (маски). Quality gates (face similarity, artifacts, photorealism). Cost router. Decision log.

### Текущее состояние

**НЕ СООТВЕТСТВУЕТ. Single-pass, no quality gates, no identity metrics.**

Детальный gap-анализ вынесен в отдельный документ: [`pipeline_orchestrator_spec.md`](pipeline_orchestrator_spec.md).

Ключевые разрывы:
- **1 вызов** генерации вместо multi-pass (pipeline.py L84-130).
- **Нет face embeddings** — identity lock только через prompt text.
- **Нет post-gen verification** — принимается любой результат > 100 bytes.
- **Нет масок и сегментации** — один промпт пытается решить все.
- **Нет cost tracking и decision log.**
- **Static metadata** вместо реальных метрик quality.

### Evidence

```
src/orchestrator/pipeline.py L84-130: single generate() call
src/orchestrator/pipeline.py L104: quality check = len(raw) > 100
src/orchestrator/pipeline.py L110-123: static strings for enhancement
src/utils/image.py: has_face_heuristic — aspect ratio only
src/providers/factory.py: ChainImageGen — first-success, not quality-aware
```

### Рекомендации

См. [`pipeline_orchestrator_spec.md`](pipeline_orchestrator_spec.md) Stages 1-4.

---

## 8. GAME MECHANICS И RETENTION

### Требование конституции

Прогресс через образы. 1 фото = 10+ образов. Loop: результат -> лучший образ -> еще. Запрещены манипулятивные триггеры.

### Текущее состояние

**Частичное соответствие.**

Позитивные аспекты:
- Loop keyboard дает возможность restyle/retry (`src/bot/keyboards.py` L52-75).
- Action keyboard дает переключение между режимами (`keyboards.py` L35-49).
- Sharing deep link для вирального роста (`keyboards.py` L37, 54).

Конфликтные аспекты:
- Нет концепции «лучший образ» и сравнения образов.
- Нет истории сессии / прогресса (past results не показываются).
- Нет уровней, достижений, сравнения версий себя.
- Referral (`start.py` L27, L34-36) — только альтернативный welcome текст, нет вознаграждения.
- Retention messaging отсутствует (нет push-напоминаний о новых сценариях).

### Evidence

```
src/bot/keyboards.py L52-75: loop_keyboard — restyle/loop, но нет "лучший образ"
src/bot/handlers/start.py L27,34-36: referral — log only, no reward
src/models/db.py: UsageLog — per-day count only, no session history
```

### Рекомендации

- **P1:** после серии образов показывать «Твой лучший образ: X (delta +Y)».
- **P1:** хранить историю образов per user и позволять сравнивать.
- **P2:** добавить реферальные вознаграждения (бонусные образы).
- **P2:** push-уведомления о новых сценариях (если user opt-in).

---

## 9. MONETIZATION

### Требование конституции

Free = доказать ценность. Paid = расширить возможности. Paywall: `"Открой все стили и образы"`. Запрещено: блокировать базовую ценность, framing через «генерации».

### Текущее состояние

**Частичное соответствие.**

Позитивные аспекты:
- LLM анализ доступен даже при 0 кредитов (worker пропускает image gen, но анализ выполняется — `src/workers/tasks.py` L99-105).
- Paywall не блокирует rating/scoring — только image generation.
- Credit packs через YooKassa работают корректно (`src/services/payments.py`).

Критичные конфликты:
- **Framing:** весь payment flow завязан на «генерации» (см. раздел 4 Language System).
- **Pack labels:** `"5 фото — 200 ₽"` (`payments.py` L23) — фото-центричный, не образо-центричный.
- **YooKassa description:** `"RateMeAI: {qty} фото-генераций"` (L77) — максимально конфликтует с концепцией.
- **«Premium»:** `"оформи Premium!"` в rate limit сообщении (`mode_select.py` L185), но `is_premium` не продается через payment flow — мертвая ветка UX.
- **402 handler:** bot обрабатывает HTTP 402 (`mode_select.py` L175-181), но API `/analyze` **не вызывает** `check_image_credits` (`src/api/v1/analyze.py` — dependency не подключена) — мертвый код.

### Evidence

```
src/services/payments.py L23: "{qty} фото — {price} ₽"
src/services/payments.py L77: "фото-генераций"
src/bot/handlers/mode_select.py L185: "оформи Premium!" — is_premium не продается
src/bot/handlers/mode_select.py L175-181: 402 handler — API не возвращает 402
src/api/deps.py L122-134: check_image_credits exists but unused in routes
src/workers/tasks.py L99-105: credit check + skip_image_gen в worker, не в API
```

### Рекомендации

- **P0:** переименовать pack labels: `"5 образов"` вместо `"5 фото"`.
- **P0:** сменить YooKassa description на `"RateMeAI: {qty} улучшений"`.
- **P0:** убрать «генерации» из всех payment-related строк.
- **P1:** убрать или реализовать Premium: либо подключить `is_premium` к payment flow, либо убрать текст.
- **P1:** убрать мертвый 402 handler из mode_select или подключить `check_image_credits` в API.

---

## 10. OBSERVABILITY

### Требование конституции

Pipeline trace, decision log, cost breakdown, quality report с реальными метриками.

### Текущее состояние

**НЕ СООТВЕТСТВУЕТ.**

- Логирование: стандартный Python logger с info/warning/exception messages.
- Нет structured trace (timestamps per step).
- Нет decision log (почему выбрана модель/стратегия).
- Нет cost tracking.
- Enhancement metadata (`pipeline.py` L110-123) — статичные строки, не метрики.

### Evidence

```
src/orchestrator/pipeline.py L101,124,126,129: logger.info/warning — unstructured
src/orchestrator/pipeline.py L110-123: static enhancement dict
src/workers/tasks.py L46-49: only version logging at startup
```

### Рекомендации

- **P1:** добавить structured pipeline trace (JSON) в task result.
- **P1:** логировать время каждого этапа (preprocess, analyze, generate, finalize).
- **P2:** добавить cost estimation per task.
- **P2:** заменить static enhancement на реальные quality metrics.

---

## ДОПОЛНИТЕЛЬНЫЕ НАХОДКИ

### Тестовое покрытие

| Область | Покрытие | Файл |
|---------|---------|------|
| Payments webhook + balance | Хорошее | `tests/test_api/test_payments.py` |
| Webhook security (IP) | Хорошее | `tests/test_api/test_webhook_security.py` |
| Pipeline skip_image_gen | Базовое | `tests/test_orchestrator/test_pipeline.py` |
| Rate limits (429) | **Нет** | — |
| Credit deduction в worker | **Нет** | — |
| Identity verification | **Нет** (не реализовано) | — |
| Post-gen quality gates | **Нет** (не реализовано) | — |
| Scoring delta | **Нет** (не реализовано) | — |

### Несогласованности в коде

1. **`check_image_credits`** определена в `src/api/deps.py` L122-134, но не используется ни в одном route. Bot обрабатывает 402, но API его не возвращает.
2. **`check_nsfw`** определена в `src/utils/security.py`, но нигде не вызывается. Используется только `extract_nsfw_from_analysis` (inline check внутри LLM-ответа).
3. **`is_premium`** влияет на rate limits (`deps.py` L99), но не может быть установлено через payment flow.
4. **Filename delivery:** `dating_improved.jpg`, `cv_improved.jpg` (`results.py` L268, L320) — технические имена, видимые клиенту в некоторых Telegram-клиентах.

---

## ПРИОРИТИЗИРОВАННЫЙ ROADMAP

### P0 — Критичные (концептуальная целостность)

| # | Задача | Файлы | Effort |
|---|--------|-------|--------|
| P0.1 | Глобальная замена «генерация» -> «улучшение/образ» в user-facing строках | `start.py`, `mode_select.py`, `results.py`, `payments.py` | S |
| P0.2 | Переформулировать WELCOME_TEXT в AI Stylist framing | `start.py` | S |
| P0.3 | Переформулировать paywall/pack labels | `payments.py`, `mode_select.py`, `keyboards.py` | S |
| P0.4 | Интегрировать face embedding service (ArcFace) | новый `services/identity.py`, `utils/image.py` | L |
| P0.5 | Добавить post-gen identity gate (cosine similarity) | `pipeline.py` | M |
| P0.6 | Убрать/перепозиционировать emoji из основного потока | `keyboards.py`, `start.py` | S |

### P1 — Важные (архитектурная зрелость)

| # | Задача | Файлы | Effort |
|---|--------|-------|--------|
| P1.1 | Добавить structured pipeline trace | `pipeline.py` | M |
| P1.2 | Post-gen re-scoring и delta computation | `pipeline.py`, services | M |
| P1.3 | AI Stylist entry message + мягкий первичный анализ | `photo.py`, `mode_select.py` | M |
| P1.4 | Переименовать «стиль» -> «образ» в UX | `keyboards.py`, `mode_select.py` | S |
| P1.5 | Добавить «Что изменено / Как воспринимается» в результат | `results.py` | M |
| P1.6 | Убрать мертвый код (402 handler, unused check_image_credits, Premium ref) | `mode_select.py`, `deps.py` | S |
| P1.7 | Реальная face detection вместо has_face_heuristic | `utils/image.py` | M |
| P1.8 | «Лучший образ» tracking и сравнение | `results.py`, `mode_select.py`, DB | L |

### P2 — Развитие (масштабирование)

| # | Задача | Файлы | Effort |
|---|--------|-------|--------|
| P2.1 | Social Stylist категория (influencer, luxury, casual) | `image_gen.py`, `keyboards.py`, `enums.py` | M |
| P2.2 | Multi-pass pipeline (Stages 3-4 из pipeline spec) | `pipeline.py`, new `planner.py`, `segmentation.py` | XL |
| P2.3 | Cost/latency-aware model routing | `factory.py`, new `model_router.py` | L |
| P2.4 | Реферальные вознаграждения | `start.py`, `payments.py`, DB | M |
| P2.5 | Scoring reproducibility (lower temp, consensus) | `openrouter.py`, services | M |
| P2.6 | B2B-ready pipeline contract (plan JSON + QA report) | API, docs | L |

### Effort legend: S = 1-2 часа, M = 0.5-1 день, L = 2-3 дня, XL = 1-2 недели.

---

## DEFINITION OF DONE: СООТВЕТСТВИЕ КОНЦЕПТУ

Продукт считается соответствующим конституции, когда:

- [ ] Ни одна user-facing строка не содержит слов «генерация», «генерировать», «фильтр».
- [ ] Welcome message позиционирует бота как AI-стилиста.
- [ ] Paywall продает «образы/стили», не «генерации/фото».
- [ ] Face embedding вычисляется для каждого входного фото.
- [ ] Post-gen identity check выполняется и логируется.
- [ ] Результат с face similarity < threshold не доставляется пользователю.
- [ ] Каждый результат содержит блок «Что изменено / Как воспринимается».
- [ ] Delta score (до/после) показывается пользователю.
- [ ] Pipeline trace с timestamps сохраняется в task result.
- [ ] Emoji-режим отделен от основного фотореалистичного потока.
- [ ] Нет мертвого кода (402 handler, unused deps, Premium без продукта).
