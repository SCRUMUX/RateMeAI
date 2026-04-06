# Pipeline Orchestrator Spec

## Концептуальное ТЗ: миграция к многоступенчатому AI Photo Pipeline

---

## 1. ТЕКУЩЕЕ СОСТОЯНИЕ (AS-IS) — обновлено v1.3.x

### 1.1 Архитектура текущего pipeline

Пайплайн реализован в `src/orchestrator/pipeline.py` (класс `AnalysisPipeline`) и поддерживает два режима:

**Multi-pass (default при `SEGMENTATION_ENABLED=true`):**
```text
Input -> Preprocess -> LLM Analysis -> PipelinePlan -> [Step1 -> Step2 -> ... -> StepN] -> GlobalGates -> Store -> Return
```

**Single-pass (fallback):**
```text
Input -> Preprocess -> LLM Analysis -> SingleEditCall -> Store -> Return
```

**Ключевые характеристики:**
- Основной режим генерации — Reve `edit` (не `remix`). Каждый шаг вызывает `edit()` с `edit_instruction`, что обеспечивает точечные правки без полной перегенерации.
- Промпт-anchors (`FACE_ANCHOR`, `BODY_ANCHOR`, `SKIN_FIX`, `CAMERA`, `REALISM` в `src/prompts/image_gen.py`) используют positive framing (без "DO NOT"), чтобы избежать diffusion "negation blindness".
- Шаги выполняются **последовательно** — каждый получает результат предыдущего шага как input.
- Identity gate: InsightFace ArcFace embeddings используются для face similarity (telemetry-only, без блокировки). Результат всегда доставляется пользователю.
- Quality gates: face_similarity, aesthetic_score, artifact_ratio, photorealism — проверяются после всех шагов, результат с warning доставляется при непрохождении.
- MediaPipe SelfieSegmentation используется для масок (face, body, background, clothing) — маска передается как текстовая подсказка в edit mode.
- `test_time_scaling` настраивается через `REVE_TEST_TIME_SCALING` (default 5).
- Автоматический upscale: `postprocessing=[upscale(factor=2)]` добавляется по умолчанию.

### 1.2 Текущий preprocessing

Файл `src/utils/image.py`:
- Валидация формата и размера.
- `has_face_heuristic()` проверяет aspect ratio и min dimensions.
- При отсутствии лица — ошибка до начала pipeline.

### 1.3 Текущий provider layer

- `src/providers/image_gen/reve_provider.py` — основной провайдер (Reve API, edit mode с rate-limit retry).
- `src/providers/image_gen/replicate.py` — альтернативный провайдер (fallback).
- `src/providers/factory.py` — выбор провайдера (mock / reve / replicate / auto).
- Model Router: cost-aware routing с budget enforcement per pipeline.

### 1.4 Текущий scoring

- Pre-score: LLM scoring входного изображения (temperature=0, configurable consensus).
- Post-score: LLM re-scoring выходного фото через `_compute_delta`.
- Delta (до/после) вычисляется и отображается пользователю.
- Scoring temperature = 0.0, consensus samples = 1 (configurable via `SCORING_CONSENSUS_SAMPLES`).

---

## 2. ЦЕЛЕВОЕ СОСТОЯНИЕ (TO-BE)

### 2.1 Целевая архитектура

```text
Input -> Orchestrator -> PipelinePlan -> [Pass1 -> Pass2 -> ... -> PassN] -> QualityGates -> ResultAssembler -> Output
```

Каждый pass — специализированная трансформация, решающая одну задачу.

### 2.2 Сервисная схема

```
API Gateway
    |
    v
Orchestrator Service (движок планирования)
    |
    v
Pipeline Plan (JSON: список шагов)
    |
    +---> Model Router (выбор модели по cost/latency/quality)
    |         |
    |         v
    +---> Image Workers (выполнение конкретных шагов)
    |         |
    |         v
    +---> Quality Gates (проверка после каждого шага)
    |         |
    |         v
    +---> Embedding Service (face similarity)
    |
    v
Result Assembler (финальный результат + delta + explanation)
    |
    v
Storage (оригинал + промежуточные + финал)
```

### 2.3 Формат Pipeline Plan

Orchestrator генерирует JSON-план для каждого запроса:

```json
{
  "task_id": "uuid",
  "intent": "dating:warm_outdoor:friendly",
  "input_embedding": "base64-arcface-vector",
  "pipeline": [
    {
      "step": "face_preservation_pass",
      "model": "flux-img2img",
      "params": {"strength": 0.15, "mask": "face_region"},
      "gate": {"face_similarity": ">= 0.92"}
    },
    {
      "step": "background_edit",
      "model": "flux-inpaint",
      "params": {"mask": "background_region", "prompt": "golden-hour outdoor, soft bokeh"},
      "gate": {"artifact_ratio": "< 0.05"}
    },
    {
      "step": "clothing_edit",
      "model": "flux-inpaint",
      "params": {"mask": "clothing_region", "prompt": "stylish casual outfit"},
      "gate": {"face_similarity": ">= 0.90"}
    },
    {
      "step": "expression_adjustment",
      "model": "flux-controlnet",
      "params": {"control": "expression", "target": "warm genuine smile"},
      "gate": {"face_similarity": ">= 0.88", "aesthetic_score": ">= 6.0"}
    }
  ],
  "global_gates": {
    "face_similarity": ">= 0.85",
    "artifact_ratio": "< 0.03",
    "photorealism_score": ">= 7.0"
  },
  "retry_policy": {
    "max_retries": 2,
    "on_fail": "rollback_to_last_passing_step"
  },
  "cost_budget": {
    "max_total_usd": 0.15,
    "fallback_model": "reve-remix"
  }
}
```

---

## 3. GAP-АНАЛИЗ (AS-IS vs TO-BE)

### 3.1 Identity Anchor

| Аспект | Текущее | Целевое | Gap |
|--------|---------|---------|-----|
| Face detection на входе | `has_face_heuristic` — только aspect ratio | Real face detection (MTCNN/RetinaFace) + embedding | Критичный |
| Face embedding | Отсутствует | ArcFace embedding при загрузке, хранится в task context | Критичный |
| Post-gen identity check | Отсутствует | Cosine similarity embedding vs original >= threshold | Критичный |
| Rejection при drift | Отсутствует | Автоматический retry/rollback при similarity < threshold | Критичный |

### 3.2 Layered Processing

| Аспект | Текущее | Целевое | Gap |
|--------|---------|---------|-----|
| Количество проходов | 1 (single call) | N (по плану оркестратора) | Архитектурный |
| Разделение задач | Один промпт решает все | Один pass = одна задача | Архитектурный |
| Промежуточное хранение | Нет | Сохранение результата каждого шага | Средний |
| Возможность отката | Нет | Rollback к последнему passing step | Средний |

### 3.3 Selective Editing

| Аспект | Текущее | Целевое | Gap |
|--------|---------|---------|-----|
| Сегментация | Отсутствует | Маски: face / background / clothing | Архитектурный |
| Inpainting | Не используется | Локальные правки через flux-inpaint | Архитектурный |
| Face region protection | Только prompt-level | Маска + embedding verification | Критичный |

### 3.4 Quality Gates

| Аспект | Текущее | Целевое | Gap |
|--------|---------|---------|-----|
| Face similarity metric | Нет | ArcFace cosine >= threshold | Критичный |
| Artifact detection | Нет | Perceptual Artifact Ratio | Средний |
| Aesthetic scoring | Нет | LAION Aesthetics или аналог | Средний |
| Photorealism check | Нет (prompt-level только) | ML classifier (real vs AI) | Средний |
| Retry/rollback policy | Один retry по exception | По метрикам с budget | Средний |

### 3.5 Model Router

| Аспект | Текущее | Целевое | Gap |
|--------|---------|---------|-----|
| Выбор модели | Config-level (reve/replicate/chain) | Динамический по cost/latency/quality | Средний |
| Cost tracking | Нет | Per-step cost logging | Средний |
| Fallback strategy | ChainImageGen: первый успешный | Quality-aware fallback с threshold | Средний |
| Budget limit | Нет | Max cost per pipeline run | Низкий |

### 3.6 Observability

| Аспект | Текущее | Целевое | Gap |
|--------|---------|---------|-----|
| Pipeline trace | Logger info messages | Structured trace с timestamps | Средний |
| Decision log | Нет | JSON log: почему выбран шаг/модель/retry | Средний |
| Cost breakdown | Нет | Per-step и total cost | Низкий |
| Quality report | Static strings | Реальные метрики в task result | Средний |

### 3.7 Scoring и Delta

| Аспект | Текущее | Целевое | Gap |
|--------|---------|---------|-----|
| Pre-score | Есть (LLM) | Есть | OK |
| Post-score | Нет | LLM re-scoring выходного фото | Критичный |
| Delta computation | Нет | post_score - pre_score с breakdown | Критичный |
| Reproducibility | temperature=0.7 | temperature=0 + consensus (multi-sample) | Средний |

---

## 4. ПЛАН МИГРАЦИИ (ПОЭТАПНЫЙ)

### Stage 1: Telemetry + Decision Logs (P1)

**Цель:** получить видимость текущего pipeline без изменения логики генерации.

**Изменения:**
- Добавить structured logging в `pipeline.py`:
  - start/end timestamps для каждого этапа (_preprocess, _analyze, _generate_image, _finalize).
  - Размер входных/выходных данных.
  - Параметры промпта и провайдера.
- Заменить static `enhancement` metadata на реальные данные:
  - Провайдер, время генерации, размер результата.
- Добавить cost estimation (если API возвращает usage metrics).
- Логировать pipeline trace как JSON в task result.

**Файлы:** `src/orchestrator/pipeline.py`, `src/providers/image_gen/reve_provider.py`.

**Definition of Done:**
- [ ] Каждый task в БД содержит `pipeline_trace` с timestamps и параметрами.
- [ ] Лог содержит structured JSON для каждого этапа.

---

### Stage 2: Identity Metrics + Post-Gen Gating (P0/P1)

**Цель:** ввести измеримую проверку идентичности и возможность отклонения плохих результатов.

**Изменения:**
- Интегрировать face detection (MTCNN или RetinaFace) в preprocessing:
  - Заменить `has_face_heuristic` на реальную детекцию.
  - Вычислять ArcFace embedding для входного фото.
  - Хранить embedding в task context.
- Добавить post-generation gate в `_generate_image`:
  - Вычислить embedding для результата.
  - Сравнить cosine similarity с оригиналом.
  - При similarity < threshold: retry (до max_retries) или reject.
- Добавить post-generation LLM re-scoring:
  - Повторный вызов scoring service на выходном фото.
  - Вычисление delta.
  - Включение delta в результат для пользователя.

**Новые зависимости:**
- `insightface` или `facenet-pytorch` для ArcFace embeddings.
- Опционально: `onnxruntime` для inference.

**Файлы:** `src/utils/image.py`, `src/orchestrator/pipeline.py`, новый `src/services/identity.py`.

**Definition of Done:**
- [ ] Face embedding вычисляется для каждого входного фото.
- [ ] Post-gen face similarity проверяется и логируется.
- [ ] Результат с similarity < threshold не доставляется пользователю.
- [ ] Delta score включается в ответ бота.

---

### Stage 3: Selective Editing + Multi-Pass (P1/P2)

**Цель:** перейти от single-pass к multi-pass генерации с локальным редактированием.

**Изменения:**
- Интегрировать сегментацию (SAM или BiSeNet) для разделения фото на регионы:
  - Face region (защищенная зона).
  - Background region.
  - Clothing region.
- Реализовать Orchestrator Service:
  - `src/orchestrator/planner.py` — генерация pipeline plan на основе intent и текущих метрик.
  - Планировщик выбирает шаги на основе mode/style.
- Реализовать multi-pass execution:
  - Каждый pass вызывает model с маской конкретного региона.
  - Промежуточный результат сохраняется в storage.
  - Identity gate проверяется после каждого pass.
- Перевести providers на поддержку inpainting:
  - FLUX img2img с масками.
  - Reve edit mode (уже есть `use_edit` param).

**Файлы:** новый `src/orchestrator/planner.py`, обновление `pipeline.py`, новый `src/utils/segmentation.py`.

**Definition of Done:**
- [ ] Pipeline plan генерируется для каждого запроса.
- [ ] Фон, одежда и лицо обрабатываются отдельными проходами.
- [ ] Identity gate проверяется после каждого прохода.
- [ ] Промежуточные результаты сохраняются и доступны для отката.

---

### Stage 4: Cost/Latency-Aware Model Routing + Fallback (P2)

**Цель:** оптимизировать стоимость и latency через smart routing.

**Изменения:**
- Расширить Model Router:
  - Динамический выбор модели на основе: тип задачи, бюджет, latency требование.
  - Конфигурируемые threshold-ы per-model.
- Добавить cost tracking:
  - Per-step cost estimation.
  - Budget enforcement (max cost per pipeline run).
  - Автоматический fallback на cheaper model при приближении к budget.
- Реализовать quality-aware fallback:
  - Если основная модель дает result ниже quality threshold — переключение на альтернативу.
  - Если все модели ниже threshold — reject с объяснением.

**Файлы:** `src/providers/factory.py`, новый `src/orchestrator/model_router.py`.

**Definition of Done:**
- [ ] Model Router выбирает модель динамически.
- [ ] Cost логируется per-step и per-pipeline.
- [ ] Budget enforcement работает.
- [ ] Fallback переключается по quality, а не только по availability.

---

## 5. ОТКРЫТЫЕ ВОПРОСЫ

1. **Пороговые значения:** какие cosine similarity thresholds оптимальны? Необходимо A/B тестирование (рекомендуемый стартовый порог: 0.85 для global, 0.90 для per-step).
2. **Минимизация вызовов FLUX:** как комбинировать операции, чтобы снизить количество passes без потери качества?
3. **Fallback-пайплайны:** какие запасные модели использовать при недоступности FLUX? Текущий Reve remix может быть first-fallback.
4. **Latency budget:** допустимое время обработки для пользователя. Текущее: 15-30 секунд (из UX-сообщения в боте). Multi-pass может увеличить время — нужна стратегия (прогресс-бар, промежуточные результаты).
5. **Инфраструктура для embeddings:** self-hosted ArcFace vs API-сервис? Cost/latency трейдоффы.

---

## 6. ЗАВИСИМОСТИ И РИСКИ

| Риск | Вероятность | Impact | Митигация |
|------|------------|--------|-----------|
| Увеличение latency при multi-pass | Высокая | Средний | Параллелизация независимых passes, прогресс-бар |
| Рост стоимости на пользователя | Средняя | Высокий | Cost router, budget limits, caching промежуточных результатов |
| ArcFace drift при изменении выражения | Средняя | Средний | Отдельный threshold для expression pass, weighted similarity |
| Сложность отладки multi-pass | Средняя | Средний | Pipeline trace + decision log + промежуточные snapshots |
| Зависимость от FLUX availability | Средняя | Высокий | Fallback chain с quality gates |
