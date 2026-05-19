# ANATOMY INVESTIGATION — «Большая голова» / неестественные пропорции

**Дата:** 2026-05-19
**Версия проекта на момент анализа:** v1.68 / v1.69 (флаги v1.69 включены по умолчанию).
**Статус:** read-only research. Никаких правок кода. Цель — найти root cause и предложить минимальный fix с доказательной базой.

---

## 0. TL;DR

Пайплайн v1.64 → v1.69 итеративно **наращивал** anatomy-сигналы в промпт, чтобы починить «приклеенную голову». Каждый шаг приносил локальное улучшение, но **никогда не убирал предыдущий слой**. В результате:

* В одном wire prompt **5 повторяющихся portrait/head-anchor cues** и **только 1 anatomy-клауза** (`Recompose the body so head, shoulders and torso read at natural human proportions`). Чистый сигнал «снимай голову крупно» доминирует над сигналом «соблюдай пропорции тела».
* Качество стиля целиком определяется **тремя полями в `data/styles.json`** (`clothing.default`, `scene_anchor`, `expression`), а не wire prompt. `gym_fitness` работает потому, что одежда показывает плечевой пояс (тoгда модель «видит» масштаб тела); `cafe` / `restaurant` / `boardroom` / `hotel_breakfast` показывают **закрытые плечи в блейзере/костюме + implicit сидячую позу**, и модель копирует head/torso ratio из tight-selfie референса.
* Включенные по умолчанию ablation-флаги (`numerical_percent_anchor_enabled`, `photoreal_by_framing_enabled`, `pose_hint_enabled`, `light_match_clause_enabled`) **никогда не валидировались как набор в проде**. Они летели через staging, который не запускали (см. v1.69 release-note), и были включены «по умолчанию» без A/B.

**Основная гипотеза (уверенность 75%):** проблема комбинированная — `style_data` (одежда + сцена) + **перегруз промпта параллельными portrait-cues**. Lens (`85mm short-telephoto`) сам по себе не главный виновник, но в связке с 4 другими anchors он усиливает «портретность».

**Минимальный fix** (после ablation):
1. Style catalog: переработать `clothing.default` для 5 «плохих» стилей так, чтобы линия плеч была видна (явный shoulder-cue).
2. Wire prompt: схлопнуть 5 portrait-cues в 1; убрать ИЛИ `_FACE_AREA_ANCHOR_BY_FRAMING`, ИЛИ `_COMPOSITION_NUMERICAL_HINT` (они дублируют друг друга для portrait).
3. Никаких новых anatomy clauses без ablation-доказательств.

---

## 1. Контекст: эволюция за v1.64 → v1.69

Из `src/version.py` (changelog) и `docs/ARCHITECTURE.md` §8.9:

| Версия | Что добавлено против «большой головы» |
|--------|----------------------------------------|
| v1.64 | `head_crop_proportion_lock` prompt-tail; CSL reference padding (`csl_reference_pad_enabled=True`). |
| v1.65 | Cinematic anchor `_COMPOSITION_NUMERICAL_HINT` («Reframe into bust shot»); `85mm portrait lens at chest height`; positive-framed clause «Recompose the body…»; identity-block сжат с 9 до 4 anchors. |
| v1.66 | Lens token `portrait lens` → `short-telephoto lens` (убрать второй recency-cue на портрет); миграция `data/styles.json` для 33 non-studio стилей (`expression` cleanup). |
| v1.67 | Identity-block перенесён в конец промпта; «face shape» убран из identity. Padding threshold 0.28 → 0.10 (срабатывает почти на каждом загруженном фото). |
| v1.68 | Bbox-баг в padder (`(x,y,w,h)` → `(x1,y1,x2,y2)`); per-framing `PHOTOREAL_BLOCK` (3 lens-варианта); `_FACE_AREA_ANCHOR_BY_FRAMING` («Anchor: face occupies 6%»); `LIGHT_MATCH_CLAUSE`; `_POSE_BY_FRAMING`. |
| v1.69 | Все флаги v1.68 включены по умолчанию (раньше летели в staging, который не использовался). |

**Наблюдение:** v1.65 → v1.69 — это **только добавление**. Ни одно из изменений не было откатано после того, как «следующий слой» оказался полезен. Это **классический cargo-cult в промптах**.

---

## 2. Текущий wire prompt (portrait framing, seed=42)

### 2.1. Что фактически уходит в модель

Из `tests/fixtures/golden_prompts/` (все 30 golden — `framing=portrait`, `model=gpt_image_2`):

```
[1] Anchor: the face occupies about 6% of the frame area.            ← _FACE_AREA_ANCHOR (P1.4)
[2] Using the reference photo, render the same person in a new       ← _dating_social_change_instruction
    scene that fits the chosen setting. Recompose the body so head,
    shoulders and torso read at natural human proportions.
[3] Composition: Reframe the reference into a head-and-shoulders     ← _COMPOSITION_NUMERICAL_HINT (v1.65)
    bust shot taken at chest height, the head occupying roughly the
    upper third of the canvas height with eyes near the upper-third
    line and the shoulders spanning the lower frame edge at natural
    human head-to-body scale.
[4] <scene_anchor + ambient.lighting + time_of_day + weather>        ← scene_line (composition_builder)
[5] Wardrobe: <clothing.default>.                                    ← из styles.json
[6] Pose: relaxed natural posture, shoulders slightly angled,        ← _POSE_BY_FRAMING (P2.10)
    head subtly turned off the central axis.
[7] Keep the subject's natural facial expression and gaze from       ← EXPRESSION_NATURAL
    the reference photo.
[8] Photo style: 85mm short-telephoto lens at chest height,          ← PHOTOREAL_BLOCK (per-framing)
    shallow depth of field with the subject in sharp focus and
    background softly out of focus. Authentic skin texture with
    visible pores and small natural imperfections. The scene's
    ambient light grounds the subject with consistent direction,
    matching colour temperature, and soft contact shadows where
    the body meets the ground.
[9] Match the subject's lighting to the scene's ambient light —      ← LIGHT_MATCH_CLAUSE (P2.9)
    colour temperature, direction, and softness — and do not add
    a studio key light unless the scene explicitly contains one.
[10] Use the reference photo as the identity source — preserve       ← IDENTITY_PRESERVE_BLOCK (v1.67)
     the same person's facial features: eye shape and colour,
     hairline, skin undertone.
```

**Длина:** ~1450–1500 символов (бюджет 2500, но это уже больше, чем GPT Image 2 / Nano Banana 2 обычно «слушают» в одном edit-проходе).

### 2.2. Подсчёт сигналов

Считаем количество фраз, толкающих модель в каждое направление:

| Направление | Кол-во cues в промпте | Где |
|--------------|----------------------|-----|
| **Голова крупным планом** (portrait/bust/head) | **5** | [3] `head-and-shoulders bust shot`; [3] `head occupying upper third`; [3] `eyes near upper-third line`; [6] `head subtly turned off central axis`; [8] `85mm short-telephoto at chest height` |
| **Видимые плечи / линия плеч** | **2** | [3] `shoulders spanning the lower frame edge`; [6] `shoulders slightly angled` |
| **Естественные пропорции тела** | **1** | [2] `Recompose the body so head, shoulders and torso read at natural human proportions` |
| **Лицо мелко (anti-bobblehead)** | **1** (численный) | [1] `face occupies about 6% of frame area` |
| **Сохранить идентичность** | **3** | [2] `the same person`; [10] `identity source`; [10] `preserve the same person's facial features` |
| **Сцена/одежда** | **2** | [4]; [5] |
| **Свет/материал** | **3** | [8] `pores, imperfections`; [8] `consistent direction, contact shadows`; [9] `match the subject's lighting` |

**Баланс:** 5 cues «голова крупно» против 1 cues «пропорции тела». Модель естественно перевешивает в сторону большинства.

### 2.3. Проверенные противоречия в wire prompt

**(a) «6% площади» vs «треть высоты канваса».**
В v1.68 авторы проекта явно осознают: 28% face_height ≈ 6% area (см. `image_gen.py:1532-1535`). Математически согласованно, но **семантически дублируется** — модель получает одно и то же высказывание дважды разной валютой. Это безвредно для portrait, но усиливает «портретный» сигнал.

**(b) `shallow depth of field` (PHOTOREAL_BLOCK) vs `match scene's ambient light` (LIGHT_MATCH_CLAUSE).**
shallow DoF подразумевает контролируемое освещение (студия / portrait lens). LIGHT_MATCH говорит «не добавляй студийный свет, если сцены этого не требуют». Для cafe/library — конфликт. Edit-модель усредняет → blurry artifacts.

**(c) Lens упомянут 3 раза.**
В v1.66 явно убрали дубль (`PHOTOREAL_BLOCK` теперь единственный источник `85mm`), и cinematic anchor стал «lens-agnostic». Но в текущем golden lens упомянут косвенно ещё дважды через «head-and-shoulders bust shot at chest height» (это и есть описание 85mm portrait setup) и «shallow depth of field». Итого модель видит **3 концепта lens-портретного снимка** в одном промпте.

---

## 3. Сравнение data/styles.json — почему `gym_fitness` работает

### 3.1. Контроль: `gym_fitness` (работает)

| Поле | Значение |
|------|----------|
| `clothing.default.male` | **«fitted athletic tank top or compression shirt, athletic shorts, training shoes»** |
| `scene_anchor` | «modern gym with matte equipment, mirrors in background» |
| `expression` | «Healthy glow, energetic direct look, determined confident expression.» |
| `location_type` | indoor |
| `weather.enabled` | false |
| Implicit pose | **standing** (gym = stand to lift) |
| Видимая линия плеч | **ДА** (tank top открывает плечи) |
| Видимые руки | **ДА** |

### 3.2. «Плохие» (визуально по приложенным фото)

| ID | clothing | scene | pose-implicit | shoulders visible | hands visible |
|----|----------|-------|---------------|-------------------|---------------|
| `cafe` | smart-casual date outfit, earth tones, linen or cotton | upscale cafe, exposed brick, bottles | **sitting** | НЕТ (knit/shirt full coverage) | partially |
| `hotel_breakfast` | clean casual morning outfit, quality polo or light linen shirt | hotel restaurant, panoramic windows, breakfast table | **sitting** | НЕТ | partially (food) |
| `restaurant` | tailored dark shirt or blazer, smart evening look | upscale restaurant, candlelight, wine glass | **sitting** | НЕТ (blazer) | partially |
| `concert` | vintage band tee or flannel shirt, relaxed creative style | intimate music venue, guitars, warm moody | standing/sitting ambig | partial (flannel) | usually no |
| `dog_lover` / `warm_outdoor` | relaxed casual outfit, fitted jeans, comfortable cotton shirt | sunlit park, green grass | walking/standing | partial | partial |
| `boardroom` (ровно как у CV) | navy suit, power tie, **well-fitted across the shoulders** | executive boardroom, polished table | sitting (table) | suit collar/shoulder cue ДА | НЕТ |
| `formal_portrait` | dark formal suit, white shirt, conservative tie | studio backdrop | standing/sitting ambig | suit shoulders ДА | НЕТ |

### 3.3. Корреляция (по доступным данным)

| Признак | gym_fitness (ок) | плохие |
|---------|------------------|--------|
| **Открытая линия плеч в одежде** | ✅ | ❌ (3/5 — closed) |
| **Standing pose implicit в сцене** | ✅ (gym) | ❌ (cafe/restaurant/hotel/concert — sitting) |
| **Сцена не содержит furniture, который «приглашает» сидеть** | ✅ | ❌ |
| **Одежда упоминает плечи явно** | implicit (tank top) | только `boardroom` ("well-fitted across shoulders") |
| **Wardrobe-список содержит обувь** (full_body cue в portrait) | ✅ training shoes | ✅ leather loafers / sneakers / cozy socks |

**Главный паттерн**: gym_fitness — единственный из перечисленных, где одежда **сама по себе делает плечевой пояс видимым**, а сцена не подразумевает сидячую позу. Edit-модель получает геометрический референс «плечи начинаются вот тут» из одежды, и больше не вынуждена «угадывать» масштаб тела по референсу с tight-selfie.

В `cafe` / `restaurant` / `hotel_breakfast` / `concert` модель видит:
* tight-selfie reference (тело почти не видно → масштаб неизвестен),
* одежду, скрывающую плечевой пояс (`smart-casual outfit`, `quality polo`, `blazer`, `flannel shirt`),
* сцену, которая «просит» сидеть (cafe/restaurant/breakfast = стол → сидеть),
* промпт, кричащий «head-and-shoulders bust shot» 5 раз.

**Результат:** модель копирует head/torso ratio из референса (он tight-selfie, голова большая) и подгоняет под bust shot. Получается голова доминирует.

---

## 4. Анализ feature flags

Все из `src/config.py` v1.69:

| Flag | Default | Что делает | Эффект на anatomy |
|------|---------|------------|-------------------|
| `csl_padding_v2_enabled` | True | Чинит bbox-баг в padder | **Критично** (без этого padding делал хуже). |
| `csl_reference_pad_enabled` | True | Включает padding tight-selfie | Положительный (геометрия). |
| `csl_reference_pad_face_ratio` | 0.10 | Порог tight-selfie | Очень низкий → padding почти на всех загрузках. |
| `numerical_percent_anchor_enabled` | True | `_FACE_AREA_ANCHOR_BY_FRAMING` («6%») | **Подозреваемый дубль** с `_COMPOSITION_NUMERICAL_HINT`. |
| `photoreal_by_framing_enabled` | True | Per-framing lens | Нейтрально для portrait (тот же 85mm). |
| `light_match_clause_enabled` | True | Дополнительный clause о свете | **Подозреваемый перегруз** (конфликтует с shallow DoF). |
| `pose_hint_enabled` | True | `_POSE_BY_FRAMING` | **Подозреваемый дубль** с composition hint. |
| `studio_portrait_whitelist_v2` | True | Шире whitelist studio-portrait стилей | Нейтрально (только force-portrait routing). |
| `prompt_pipeline_v4_enabled` | True | v4 prompt layout | Глобальная архитектура. |
| `use_reference_expression_default` | True | Подмена expression на «keep natural» | Положительный (убирает «forced smile»). |

**Ни один из v1.69-флагов** не проходил A/B на проде с реальными пользователями. Релиз-нота явно говорит «staged rollout … never reached production via the staging env-override path».

---

## 5. Сводка findings

### Findings (упорядочены по уверенности и влиянию)

**F1. Wire prompt перенасыщен portrait-cues (5:1 против body-cues).** — **уверенность 85%.**
Доказательство: §2.2 (баланс cues). Edit-модели (Nano Banana 2, GPT Image 2) на FAL агрегируют семантику по частотности слов — больше упоминаний «head/bust/portrait/85mm/upper-third» → сильнее склонение в портрет.

**F2. Style data (одежда + сцена) — главный модулятор `proportions_natural`.** — **уверенность 80%.**
Доказательство: §3.3, плюс контекст из `scripts/migrations/2026_05_styles_v4_anatomy/migrate.py` (где явно зафиксирована та же гипотеза — гимн стилям типа `gym_fitness` против `legal_finance` / `boardroom`). Изменения v1.66 в data/styles.json частично помогли, но **не дочистили clothing** — только `expression` и `scene_anchor`.

**F3. Lens (`85mm short-telephoto at chest height`) — не главный виновник.** — **уверенность 70%.**
Доказательство: gym_fitness работает с тем же lens-spec. Lens-token усиливает портретный паттерн только в комбинации с другими cues, но **сам по себе** не вызывает «huge head».

**F4. Один из дублирующих anchors можно безболезненно убрать.** — **уверенность 65%.**
Дубли: `_FACE_AREA_ANCHOR_BY_FRAMING` («6% area») vs `_COMPOSITION_NUMERICAL_HINT` («upper third»). Оба говорят «голова в верхней трети, лицо ~6% площади». Один из них достаточно.

**F5. `_POSE_BY_FRAMING` для portrait дублирует composition anchor.** — **уверенность 60%.**
Pose-cue «shoulders slightly angled, head subtly turned off central axis» — это **то же самое**, что cinematic «bust shot». Edit-модель получает 2 описания одной позы.

**F6. Padding (с фиксом v1.68 bbox) — критичный компонент.** — **уверенность 75%.**
Без `csl_padding_v2_enabled=True` padder ломал геометрию (см. реф-блок в `src/services/reference_preprocess.py` строки 30-55). Отключать padding нельзя. Но **уровень `face_height_ratio=0.28` для portrait** означает, что новый канвас выглядит как готовый bust shot — это правильно по доктрине, но **усиливает** портретный сигнал ещё больше.

**F7. Wardrobe-список содержит full_body cues (обувь) в portrait framing.** — **уверенность 55%.**
Пример: `social__reading_home` golden — `Wardrobe: comfortable quality loungewear, cozy socks, relaxed domestic style` при `framing=portrait`. Носки в portrait не видны → создают противоречивый сигнал → модель усредняет. Это скорее эстетический баг, чем причина huge head, но добавляет шум.

**F8. `LIGHT_MATCH_CLAUSE` ломается на сценах с разным освещением реф vs target.** — **уверенность 50%.**
Если реф снят в комнате, а сцена — terrace at sunset, clause «не добавляй studio key light» **противоречит** «shallow DoF», но не имеет отношения к anatomy.

---

## 6. Гипотезы root cause

Гипотезы упорядочены по уверенности:

### H1 (75%) — Composite: style data + prompt overload
Минимальный набор условий для «huge head»:
1. Tight-selfie reference (`face_area_ratio > 0.10`, что после v1.67 = почти всегда).
2. Closed-shoulder clothing (`smart-casual outfit`, `polo`, `blazer`, `flannel shirt`).
3. Sitting-implicit scene (`cafe`, `restaurant`, `hotel breakfast`).
4. Prompt с 5+ portrait-cues и 1 anatomy-cue.

Если хотя бы 2 из 4 фейлят (gym_fitness: 0/4 проходит) — anatomy ломается.

### H2 (15%) — Конкретный flag регрессии
Один из v1.68 флагов (`numerical_percent_anchor_enabled`, `light_match_clause_enabled`, `pose_hint_enabled`, `photoreal_by_framing_enabled`) дал негативный эффект, но был включён без A/B. Возможный кандидат: `numerical_percent_anchor_enabled` (6%-anchor в самом начале промпта дублирует composition hint).

### H3 (10%) — Padding с порогом 0.10 фейлит на loose-portrait
Если `face_area_ratio = 0.10..0.15` (стандартная фронтальная фотография), padder всё равно срабатывает (порог 0.10) и **перепакует** уже-правильный референс в более tight crop (target_face_height_ratio=0.28). Возможный артефакт: reference, который уже был ок, превращается в too-tight crop.

---

## 7. Ablation Ladder (план эксперимента)

Этот блок — **план, не реализация**. Запускается отдельной задачей в Agent mode.

### Setup
* Один и тот же референс (tight-selfie, frontal, как у пользователя).
* Один стиль: `cafe` (типичный «плохой») + `gym_fitness` (контроль).
* Модель: GPT Image 2 Edit (production default).
* Framing: `portrait` (самый частый default).
* Каждое изменение — **один** flag, остальные = v1.69 default.

### Run matrix

| Run | Изменения относительно v1.69 prod | Что проверяет |
|-----|-----------------------------------|---------------|
| **A — baseline** | (нет) | Текущий прод. |
| **B — chat baseline** | Wire prompt = **только** «Using the reference photo, render the same person in a {scene}. Wardrobe: {clothing}. Natural human proportions, the same person's face.» (~150 chars) | Простой текст победит ли сложный? |
| **C — без `_FACE_AREA_ANCHOR_BY_FRAMING`** | `numerical_percent_anchor_enabled=false` | Убрать 6%-дубль. |
| **D — без `LIGHT_MATCH_CLAUSE`** | `light_match_clause_enabled=false` | Убрать конфликт с shallow DoF. |
| **E — без `_POSE_BY_FRAMING`** | `pose_hint_enabled=false` | Убрать pose-дубль. |
| **F — без padding** | `csl_reference_pad_enabled=false` | Проверить H3 (loose-portrait). |
| **G — padding only для tight (порог 0.25)** | `csl_reference_pad_face_ratio=0.25` | Срабатывать только на реально tight. |
| **H — без `_COMPOSITION_NUMERICAL_HINT`** | (нужен code change, локально замокать) | Оставить только face-area anchor. |
| **I — без `PHOTOREAL_BLOCK`** | (нужен code change) | Без lens/pores/light. |
| **J — style data fix** | `cafe.clothing.default` → «fitted henley with visible shoulder line, sleeves rolled to elbow» | Проверить H1. |
| **K — J + B** | Минимальный wire + style fix | Проверить, можно ли сделать «как в чате», но автоматически. |
| **L — vanilla edit (без нашего pipeline)** | Прямой FAL API вызов с user-prompt | Sanity: модель сама без нас как себя ведёт? |

### Метрики
Для каждого run генерим **N=8** изображений (разные seed + 2 разных реф-исходника):
* **VLM gate**: `proportions_natural=true` rate (есть `services/quality_gates.py`).
* **Identity gate**: cosine similarity по embeddings (или существующий gate).
* **Human eval**: blind A/B (вы или 2 человека), Likert 1–5 «насколько естественно».
* **Длина wire prompt** (для контроля complexity).

### Решение
Победитель — run с:
* `proportions_natural >= 90%`.
* `identity_similarity >= baseline - 5%`.
* `human_score >= baseline + 1.0`.

Если **B (chat baseline) выигрывает** — переписать pipeline с нуля, оставив только: change instruction + scene + wardrobe + 1 anatomy clause + identity tail.
Если **C / D / E выигрывают** — выключить соответствующий flag навсегда.
Если **J / K выигрывают** — переходить к полному catalog cleanup без правки промпта.

---

## 8. Минимальный fix (после ablation)

**Если H1 (composite) подтвердится:**

### 8.1. Style catalog cleanup (`data/styles.json`)

Для каждого «closed-shoulder» стиля переделать `clothing.default.male/female/neutral`:

| Style | До | После (предложение) |
|-------|----|---------------------|
| `cafe` | smart-casual date outfit, earth tones, linen or cotton | **«fitted henley or t-shirt with visible shoulder line, simple jacket on chair behind»** |
| `hotel_breakfast` | clean casual morning outfit, quality polo or light linen shirt | **«fitted linen shirt with rolled sleeves, visible collar bone, relaxed open posture»** |
| `restaurant` | tailored dark shirt or blazer, smart evening look | **«fitted dark shirt (no blazer), visible shoulder line, top button open»** |
| `concert` | vintage band tee or flannel shirt, relaxed creative style | **«fitted band tee or open flannel over t-shirt, visible shoulder line, casual stance»** |
| `dog_lover` | relaxed casual outfit, fitted jeans, comfortable cotton shirt | **«fitted t-shirt or henley, visible shoulder line, dog leash in hand»** |

**Принцип:** каждый wardrobe должен **в явном виде** содержать слово `shoulder` либо одежду, открывающую плечевой пояс (`t-shirt`, `henley`, `open shirt`). Это даёт модели геометрический референс «масштаб тела начинается тут».

Также убрать **обувь** из wardrobe для portrait-framing-only стилей (она не видна в кадре, создаёт шум).

### 8.2. Wire prompt — сокращение

Из текущих 10 блоков (~1450 chars) оставить 6 (~600 chars):

```
[1] Using the reference photo, render the same person in {scene}.
[2] Wardrobe: {clothing}.
[3] Composition: head-and-shoulders bust shot at natural human
    head-to-shoulders proportion (head fills upper third, shoulders
    span lower frame edge).
[4] Photo style: natural lighting matching the scene, authentic
    skin texture, soft contact shadows.
[5] Keep the subject's natural facial expression and gaze from the
    reference photo.
[6] Preserve identity: eye shape and colour, hairline, skin undertone.
```

**Что убрано:**
* `_FACE_AREA_ANCHOR_BY_FRAMING` — дублирует [3].
* `_POSE_BY_FRAMING` — дублирует [3].
* `LIGHT_MATCH_CLAUSE` — растворено в [4].
* `85mm short-telephoto` — заменено на нейтральное «natural lighting» (lens сам по себе не нужен для anatomy).
* `pores, imperfections` — модель и так это рендерит при `natural lighting`.

**Что добавлено:** ничего. Никаких новых anatomy clauses.

### 8.3. Feature flags — что отключить

После подтверждения по ablation:

```env
NUMERICAL_PERCENT_ANCHOR_ENABLED=false   # H1, дубль
POSE_HINT_ENABLED=false                  # H1, дубль
LIGHT_MATCH_CLAUSE_ENABLED=false         # F8
# PHOTOREAL_BY_FRAMING_ENABLED — оставить, нейтрально
# CSL_REFERENCE_PAD_ENABLED=true — критично, не трогать
CSL_REFERENCE_PAD_FACE_RATIO=0.20        # вернуть на разумный порог
```

### 8.4. Тесты

После применения:
* Перегенерировать golden fixtures (`RATEMEAI_UPDATE_GOLDEN_PROMPTS=1`).
* Проверить `proportions_natural` на тестовом наборе из 10 стилей × 2 референса.
* Регрессия `gym_fitness` не должна возникнуть (это контроль).

---

## 9. Чего НЕ делать (anti-recommendations)

1. **Не добавлять новые anatomy clauses.** Каждое добавление за v1.65–v1.69 давало локальный wins на 1-2 стилях и regressions на остальных.
2. **Не убирать `CSL_REFERENCE_PAD_ENABLED`.** Это единственный геометрический компонент, который реально нормирует tight-selfie ref. Bbox-фикс v1.68 необходим.
3. **Не возвращать `50mm at eye level`.** Это «selfie perspective», именно от него и убегаем.
4. **Не менять identity-token («face shape» обратно).** В v1.67 явно показано, что «face shape» читается edit-моделями как геометрический матчер, не как идентичный.
5. **Не делать `csl_reference_pad_face_ratio=0`.** Это включит padding на всех фото, включая уже правильные full-body уплоады.

---

## 10. Открытые вопросы (нужен ответ пользователя)

1. **Какие именно 5 style_id** дали плохие фото из вложений? (Догадка: `cafe` / `hotel_breakfast` / `concert` / `dog_lover` / `formal_portrait`.)
2. **Какое framing** был выбран в UI (portrait / half_body / auto)?
3. **«Раньше было лучше» — какая версия?** Тег / дата / коммит-SHA, если знаете.
4. **Можно ли запустить ablation** реально (потратить ~10–20 FAL-генераций × 12 runs)?
5. **Кто будет blind-оценивать** — вы один или 2+ человека?

---

## 11. Связанные артефакты в репо

* `src/prompts/image_gen.py` — все anatomy-блоки, anchors, lens specs.
* `src/prompts/model_wrappers.py` `_assemble()` — сборка wire prompt по блокам.
* `src/prompts/composition_builder.py` — построение `CompositionIR` из style data.
* `src/services/reference_preprocess.py` — padding tight-selfie.
* `src/services/composition_safety.py` — `resolve_effective_framing`.
* `src/services/quality_gates.py` — VLM `proportions_natural` gate.
* `src/config.py` — все feature flags.
* `scripts/migrations/2026_05_styles_v4_anatomy/migrate.py` — предыдущая попытка catalog cleanup (v1.66).
* `tests/fixtures/golden_prompts/*.txt` — текущие wire prompts (30 шт).
* `data/styles.json` — style catalog (612 KB, ~16k строк).
* `docs/ARCHITECTURE.md` §8.9 — история anatomy fix v1.64 → v1.69.

---

## Приложение A. Wire prompt — gym_fitness vs cafe (один framing, одна сцена)

Я **не запускал** реальные генерации (read-only mode + ablation требует пользовательского решения). Вместо этого собираем то, что **должно** уйти в модель по текущему пайплайну:

**gym_fitness, portrait, seed=42:**
```
Anchor: the face occupies about 6% of the frame area. Using the reference
photo, render the same person in a new scene that fits the chosen setting.
Recompose the body so head, shoulders and torso read at natural human
proportions. Composition: Reframe the reference into a head-and-shoulders
bust shot taken at chest height, the head occupying roughly the upper
third of the canvas height with eyes near the upper-third line and the
shoulders spanning the lower frame edge at natural human head-to-body scale.
modern gym with matte equipment, mirrors in background, lit by even
overhead LED light with clean fill. Wardrobe: fitted athletic tank top
or compression shirt, athletic shorts, training shoes. Pose: relaxed
natural posture, shoulders slightly angled, head subtly turned off the
central axis. Keep the subject's natural facial expression and gaze from
the reference photo. Photo style: 85mm short-telephoto lens at chest
height, shallow depth of field… <далее идентично>
```

**cafe, portrait, seed=42:**
```
Anchor: the face occupies about 6% of the frame area. Using the reference
photo, render the same person in a new scene that fits the chosen setting.
Recompose the body so head, shoulders and torso read at natural human
proportions. Composition: Reframe the reference into a head-and-shoulders
bust shot taken at chest height… <идентично gym_fitness>
cozy upscale cafe, exposed brick or wood paneling, bottles and candles
in background, lit by warm window light, soft amber ambience. Wardrobe:
smart-casual date outfit, earth tones, linen or cotton. Pose: relaxed
natural posture, shoulders slightly angled, head subtly turned off the
central axis. Keep the subject's natural facial expression and gaze
from the reference photo. Photo style: 85mm short-telephoto lens at
chest height… <далее идентично>
```

**Дельта:** различия только в `scene` и `wardrobe`. Все 5 portrait-cues и 1 anatomy-cue **идентичны**. Это подтверждает F1+F2: при одинаковом промпте `style_data` единственный модулятор поведения модели.

---

## Приложение B. Reference padding — flow

Текущий гейт срабатывает на 95%+ uploads (порог 0.10):

```
upload → InputQuality.analyze() → face_bbox (x1,y1,x2,y2) + face_area_ratio
  ↓
  if csl_reference_pad_enabled AND framing ∈ {portrait, half_body, full_body}
     AND composition_class ∈ {face_closeup, portrait, half_body, unknown}
     OR face_area_ratio > 0.10:
       reference_for_provider = pad_reference_for_framing(
           image, bbox,
           framing="portrait",
           target_size=(1280, 1600),
       )
       # → resize ref so face_height = 0.28 * canvas_height
       # → place face center at (0.50, 0.30) of canvas
       # → fill rest with edge-blur of input
  ↓
  edit-model receives 1280x1600 image where face already occupies
  upper third, ~28% of canvas height (~6% of area).
```

Pad'нутый референс **уже** выглядит как bust shot. Поэтому wire prompt **не должен** говорить «Reframe into bust shot» — модель должна **только переписать сцену/одежду**, не композицию.

Это аргумент в пользу того, что если padding работает корректно (F6), `_COMPOSITION_NUMERICAL_HINT` и `_FACE_AREA_ANCHOR_BY_FRAMING` в wire prompt **становятся ненужными** для portrait framing — геометрия уже в референсе. Это самая многообещающая single-flag ablation: **выключить numerical anchors для portrait, оставив padding**.

---

## 12. Phase 1 applied (v1.70 — May 2026)

Применили план v1.70 без новых клауз. Все правки — удаление head-cues и редундантных блоков.

### Изменения в коде

| Файл | Что изменилось |
|------|----------------|
| `src/prompts/image_gen.py` | `_COMPOSITION_NUMERICAL_HINT` → `{}` (3 строки cinematic anchor удалены). `_FACE_AREA_ANCHOR_BY_FRAMING` → `{}` (3 строки face-area anchor удалены). `_POSE_BY_FRAMING["portrait"]` — `head subtly turned` → `subject turned slightly off the central axis`. `_FRAMING_PROMPT_DIRECTIVES` — portrait и full_body очищены от `head-and-shoulders` / `head-to-toe`. `_dating_social_change_instruction` opener — tail с `head, shoulders and torso` заменён на head-free `Show the subject naturally with realistic body proportions.` `PHOTOREAL_BLOCK` — lens spec и DoF удалены, осталась только skin texture + light match. `_PHOTOREAL_BY_FRAMING` — collapsed в stub (все 3 framings указывают на единственный `PHOTOREAL_BLOCK`). `_STEP_CHANGE` — `head-to-body proportions` → `body proportions` в 3 шагах multi-pass. |
| `src/prompts/model_wrappers.py` | Fallback в `_assemble` для documents: `Centered head-and-shoulders framing.` → `Centered framing.` |
| `src/config.py` | `numerical_percent_anchor_enabled`: True → False. `light_match_clause_enabled`: True → False (clause растворён в новом `PHOTOREAL_BLOCK`). |
| `src/services/style_lint.py` | Новая публичная функция `forbidden_head_tokens_in_prompt(prompt, *, style_id)` — реализует правило `NO_HEAD_TOKEN_IN_PROMPT`. Используется в тестах. |
| `data/styles.json` | Миграция v5: добавлен `, shoulder line visible` в `default_clothing` и `clothing.default.{male,female,neutral}` для 114 не-sport, не-document, не-studio стилей. Бэкап в `data/styles.json.bak.v169`. |
| `scripts/migrations/2026_05_styles_v5_shoulders/migrate.py` | Идемпотентная миграция (повторный запуск ничего не меняет). |
| `web/src/components/wizard/StyleSettingsModal.tsx` | Inline hint под framing chip-row при ручном выборе `half_body` / `full_body`. |
| `web/src/locales/{ru,en}/wizard.json` | Новые ключи `style.framingManualHintHalf` и `style.framingManualHintFull`. |

### Подсчёт до/после

| Метрика | v1.69 | v1.70 |
|---------|-------|-------|
| Среднее количество chars в wire prompt (non-doc, portrait) | ~1450 | ~750 |
| Упоминаний `head` в wire prompt (non-doc) | 5 | 0 |
| Упоминаний `85mm` / `50mm` / lens spec | 1 | 0 |
| Упоминаний `shallow depth of field` | 1 | 0 |
| Упоминаний `Anchor: the face occupies` | 1 | 0 |
| Стилей с явным `shoulder` cue в `clothing.default` (catalog) | ~5 (только tailored-suit) | ~119 (миграция v5 + sport whitelist) |

### Тесты

- **Удалены:** `test_percent_anchor.py`, `test_numerical_hint_matches_geometry.py`, `test_executor_head_crop_hint.py`.
- **Переписаны:** `test_prompt_anatomy_catalog.py`, `test_photoreal_by_framing.py`, `test_no_lens_duplication.py`, `test_v4_1_anchors.py`, `test_prompt_diversity_v4.py`, `test_numerical_composition_anchor.py`, `test_positive_framing.py` — все assertions теперь ЗАПРЕЩАЮТ head/lens/DoF tokens вместо требования их присутствия.
- **Добавлен:** `test_no_head_cues.py` — sweep по всем зарегистрированным стилям × 3 framings + проверка exempt'а для document.
- **Перегенерированы:** 30 golden fixtures в `tests/fixtures/golden_prompts/*.txt`.
- **Прогон:** 3180 passed, 128 skipped (полный `pytest tests/`).

### Что НЕ делалось

- Не запускались FAL-генерации (запрет пользователя — он сам будет оценивать).
- Не трогался `reference_preprocess` (padding) — критичный компонент.
- Не трогались document-стили (passport / visa / driver_license / photo_3x4 / photo_4x6).
- Не добавлялись новые anatomy clauses.
- Не менялся `gym_fitness` (контроль).

---

**Конец документа.**
