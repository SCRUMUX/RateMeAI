# Image-gen tier surface (post Nano-Banana cleanup)

> **Historical context.** Версии v1.21–v1.71 этого документа описывали
> A/B-сетап с двумя моделями (Nano Banana 2 Edit + GPT Image 2 Edit)
> через `UnifiedImageGenProvider`. В "Remove Nano Banana, Premium
> Upscale" cleanup A/B-роутер и Nano Banana были выпилены: в
> пайплайне осталась одна модель — GPT Image 2 Edit, а продуктовый
> выбор сводится к двум tier'ам **Standard / Premium**.

## TL;DR

- Каждый `/api/v1/analyze` запрос идёт через **GPT Image 2 Edit**
  (`openai/gpt-image-2/edit`) с `image_quality=medium`. Кадр —
  native portrait 1024×1536 (`effective_aspect_ratio=2:3`).
- Продуктовый tier'ом управляет form-поле `tier`:
  - `standard` (1 кредит) — базовый рендер GPT Image 2 medium,
    без post-pass refiner'а. ≈ $0.06 / img на стороне FAL.
  - `premium` (2 кредита) — тот же базовый рендер плюс **Clarity
    Upscaler ×2 post-pass**: реально повышает разрешение фотографии
    и подтягивает чёткость кожи / волос / фона. Общая стоимость
    ≈ $0.10 / img (бюджет премиум-tier'а).
- Cross-model fallback не существует. Если GPT Image 2 фейлится
  на одну попытку, in-pipeline identity-retry с новым сидом
  пересоздаёт изображение на той же модели; никакого "силент
  switch to Nano Banana" не происходит.
- Legacy form-поле `image_model` всё ещё принимается (для
  совместимости со старыми SPA-bundle'ами и эдж-прокси), но любое
  значение схлопывается в `gpt_image_2` на бэке
  ([`apply_tier_context_fields`](../src/services/analysis_request.py)).

## Контрактная цепочка

```
UI tier pill    FormData          /analyze              Task.context        Executor
+-----------+   +-------------+   +----------------+   +----------------+   +-----------------+
| Standard  |-->| tier        |-->| validate +     |-->| tier=standard  |-->| GPT Image 2   |
|           |   | image_model |   | apply_tier_*   |   | image_model=   |   |   (medium)      |
|           |   | image_quality|  | (collapse to   |   |   gpt_image_2  |   |                 |
| Premium   |-->| tier=premium|   | gpt_image_2)   |   | image_refine=  |   | + Clarity ×2  |
+-----------+   +-------------+   +----------------+   |   clarity      |   |   (if refine)   |
                                                       +----------------+   +-----------------+
```

- `PRODUCT_TIERS_ALLOWED = {"standard", "premium"}`
- `AB_MODELS_ALLOWED = {"gpt_image_2"}` — оставлен как backwards-
  compatible frozenset; единственное допустимое значение совпадает с
  тем, что бэк всё равно подставит сам.
- Любое другое значение `image_model` тихо дропается на бэке.

## Стоимость

| Tier      | Модель        | Quality | Refiner               | FAL cost (USD/img) | Кредитов |
|-----------|---------------|---------|-----------------------|--------------------|----------|
| Standard  | gpt_image_2   | medium  | —                     | ≈ $0.06            | 1        |
| Premium   | gpt_image_2   | medium  | Clarity Upscaler ×2   | ≈ $0.10            | 2        |

Премиум-бюджет = GPT-2 medium (~$0.06) + Clarity (~$0.04). Любой
переход на `quality=high` ($0.12) убирает Premium из бюджета и
требует отдельного решения по биллингу.

Кредитный refund: если Clarity refiner упал, executor выставляет
`result_dict["premium_refine_failed"] = True`. Worker по этому
сигналу возвращает пользователю 1 из 2 зарезервированных кредитов.

## Kill-switches и ENV

| Переменная                      | По умолчанию | Что делает                                                                 |
|---------------------------------|--------------|----------------------------------------------------------------------------|
| `AB_TEST_ENABLED`               | `true`       | Кладёт tier-маршрутизацию в task ctx. При `false` `apply_tier_context_fields` — no-op. |
| `AB_DEFAULT_MODEL`              | `gpt_image_2`| Лейбл бэкенда; для совместимости. Любое значение нормализуется к `gpt_image_2`. |
| `AB_DEFAULT_QUALITY`            | `medium`     | Quality-тier для GPT Image 2 когда клиент не прислал явный.                |
| `CLARITY_REFINER_ENABLED`       | `true`       | Railway kill-switch для премиум post-pass'а. При `false` premium-rendering эквивалентен standard, но 1 кредит возвращается. |
| `CLARITY_REFINER_UPSCALE_FACTOR`| `2.0`        | Множитель ×N для Clarity. Поднять до `2` — реальное увеличение разрешения; cost остаётся в премиум-бюджете. |

## Диагностика

- `/api/v1/internal/diagnostics/image-gen-probe?provider=unified` /
  `?provider=gpt_image_2` — оба значения теперь резолвят одно и то
  же (GPT Image 2 Edit), но эндпоинт продолжает принимать оба
  параметра ради совместимости с health-скриптами.
- Метрика `IMAGE_GEN_BACKEND.backend` после cleanup'а принимает
  одно значение вида `gpt_image_2:<quality>`; именования
  Prometheus-серий сохранены.

## Что было выпилено в Nano-Banana cleanup

| Артефакт                                                | Статус   |
|----------------------------------------------------------|----------|
| `src/providers/image_gen/fal_nano_banana.py`             | Удалён   |
| `src/providers/image_gen/unified.py`                     | Удалён   |
| `factory._build_nano_banana_2` / `_build_unified_provider`| Удалены |
| `model_wrappers.wrap_for_nano_banana_2`                  | Удалён   |
| `executor._NB2_ASPECT_BUCKETS` / `_aspect_ratio_enum_for_size` | Удалены |
| `executor._OUTPUT_SIZE_BY_MODEL_FRAMING`                 | Свёрнут в `_OUTPUT_SIZE_BY_FRAMING` |
| `metrics._AB_COST_FIELDS["nano_banana_2"]`               | Удалён   |
| `config.nano_banana_model` / `model_cost_fal_nano_banana_*` | Удалены |
| `NANO_BANANA_MODEL` env / costs в `.env.example`         | Удалены  |
| Cross-model fallback (`allow_cross_model_image_fallback`) | Поле живо как config-shape no-op; функционально выключено |
