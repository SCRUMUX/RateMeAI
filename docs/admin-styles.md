# Admin Style Curation Guide (1.29.0)

This guide is for operators editing the style catalog through the web
admin at `/admin/styles`. The same data is available as the JSON
file `data/styles.json`, but the admin UI adds live lint, conflict
detection, and atomic saves with cache invalidation — so prefer it.

## Access

- The page is gated by the `ADMIN_USER_IDS` environment variable
  (comma-separated list of internal user UUIDs). If your account is
  not in that list you'll see a "Доступ запрещён" message.
- Auth uses the same session cookie as the main app — log in via
  the regular flow first, then navigate to `/admin/styles`.

## Catalog table

The home page (`/admin/styles`) lists every style with the
following columns:

| Column     | Meaning                                                              |
|------------|----------------------------------------------------------------------|
| `id`       | Stable identifier — never changes after creation                     |
| `mode`     | `cv` / `social` / `dating`                                           |
| `label`    | Russian display name shown to users                                  |
| `lint`     | `clean` / `NE` (errors) / `NW` (warnings) badge                      |
| `unlock`   | Number of generations needed to unlock (0 = always available)        |
| `scenario` | Optional scenario tag (e.g. `document-photo`)                        |
| `v`        | Schema version — should be `3` for new content                       |

Filters:

- **Mode chips** — switch between `all` / `cv` / `social` / `dating`.
- **Search** — fuzzy match on `id`, `label`, and `hook_text`.
- **"Show only with issues"** — appears when at least one style is
  dirty; clicking restricts the table to lint-positive rows.

Top-right buttons:

- **Conflicts report** — opens `/admin/conflicts` (see below).
- **Reload cache** — invalidates the in-memory style cache without
  redeploying. Use after a manual edit of `data/styles.json`.
- **+ New style** — opens the editor with a blank v2 template.

## Editor

Three tabs:

### Базовое (Basic)

- `id`, `mode`, `schema_version` (read-only after creation)
- `display_label`, `hook_text`, `scenario`, `unlock_after_generations`
- `meta` block (param + delta_range) — used by the analytics layer

### Слоты v2 (Slots v2)

Legacy v2 fields. **Skip this tab unless you're editing a v2-only
row.** Modern styles get curated through the **v3 / channels** tab.

### v3 / channels

The interesting tab — every field below is read by the slot sampler
when `schema_version: 3`.

#### `location_type`

Coarse classifier. Drives the lint engine:

- `indoor` — flags `season` and `weather` as conflict.
- `outdoor` — no extra rules.
- `mixed` — used for styles that span both contexts.
- `document` — flags any ambient channel as conflict (these styles
  use neutral lighting via `scene_preserve` mode).
- `""` (empty) — unclassified, lint skips location rules.

#### `trigger_pool`

The inviolable motif of the style. **3–6 equivalent English
formulations.** Examples for `mirror_aesthetic`:

```
round wall mirror in frame
oval mirror reflecting the subject
small bathroom mirror selfie composition
```

Each formulation gets a per-row warning if it contains:

- **Framing tokens** — `full-length`, `head-to-toe`, `close-up`,
  `wide shot`, `low angle`, `from above`, ...
- **Lighting tokens** — `warm light`, `soft light`, `rim light`,
  `golden hour`, `blue hour`, ...
- **Weather tokens** — `rainy`, `stormy`, `snowy`, `foggy`, ...
- **Season tokens** — `in winter`, `wintertime`, ...

Those belong in their own channel pool, not in the trigger.

> **Why?** The slot sampler picks ONE trigger per generation. If the
> trigger says "full-length mirror" and the user picked
> `framing=portrait`, the prompt now contains a contradiction —
> "full-length mirror, portrait framing". Keep triggers about WHAT
> is in the frame; let `framing` decide HOW it's shot.

#### `scene_anchor`

Single dry sentence describing the location. **No lighting / weather /
time-of-day adjectives.**

Good: `"luxury hotel lobby with marble floors and brass details"`.
Bad: `"luxury hotel lobby at golden hour with warm rim light"`.

#### `scene_overrides`

Comma-separated alternative scenes the slot sampler may roll
instead of `scene_anchor`. Useful for styles where multiple sub-
locations share the same trigger.

#### `available_channels`

Seven checkboxes:

| Channel          | Effect when checked                                                |
|------------------|--------------------------------------------------------------------|
| `lighting`       | Lighting select renders for the user                               |
| `weather`        | Weather pill group renders                                         |
| `time_of_day`    | Time-of-day pill group renders                                     |
| `season`         | Season pill group renders                                          |
| `framing`        | Framing pill group renders                                         |
| `clothing`       | Clothing free-text + chips render                                  |
| `scene_override` | Scene override free-text + chips render                            |

**Empty list = "не курировано"**: every channel with a non-empty
pool falls back to visible (legacy 1.28 behaviour). Use this for
quick-and-dirty new styles; come back later to lock the surface.

The `mirror_aesthetic` example: `["lighting", "time_of_day"]`
hides `season` (indoor — irrelevant) and `weather` (indoor — also
irrelevant), leaving the user with only the two knobs that
actually matter for a mirror selfie.

#### `ambient` pools

Four CSV inputs (lighting / weather / time_of_day / season).
Greyed out when the matching channel is unchecked. The slot
sampler picks one entry per generation; an empty pool with the
channel checked is a `EMPTY_POOL` lint error.

When `season` is checked the editor shows a **"Fill 4 seasons"**
shortcut that drops `spring, summer, autumn, winter` into the
pool — the lint engine warns when fewer than four seasons are
listed because the channel is conceptually all-or-nothing.

## Live lint banner

Every change in the editor triggers a debounced
`GET /api/v1/admin/styles/{id}/lint` (350 ms after the last
keystroke). Issues appear at the top of the modal:

- **Red badge** — error. Save still works; treat as a bug to fix
  before the style ships to users.
- **Amber badge** — warning. Informational; useful but non-blocking.

Codes:

| Code                 | Severity | Meaning                                                                |
|----------------------|----------|------------------------------------------------------------------------|
| `TRIGGER_DIRTY`      | warning  | Trigger contains framing/lighting/weather/season tokens                |
| `INDOOR_SEASON`      | error    | `location_type=indoor` style has `season` in `available_channels`      |
| `INDOOR_WEATHER`     | error    | `location_type=indoor` style has `weather` in `available_channels`     |
| `DOCUMENT_AMBIENT`   | error    | `location_type=document` style has any ambient channel enabled         |
| `SEASON_INCOMPLETE`  | warning  | `season` enabled but pool has fewer than 4 seasons                     |
| `EMPTY_POOL`         | error    | Channel enabled in `available_channels` but its ambient pool is empty  |
| `UNKNOWN_CHANNEL`    | error    | `available_channels` contains a typo (not in `CONFIGURABLE_CHANNELS`)  |
| `UNKNOWN_LOCATION`   | error    | `location_type` is set to a value outside the enum                     |
| `EMPTY_TRIGGER_POOL` | error    | v3 style with no trigger formulations                                  |

## Conflicts report

`/admin/conflicts` — three buckets:

1. **Duplicate labels** — same `display_label` after stripping
   leading emoji and lowercasing. Click any style id to jump into
   the editor.
2. **Similar labels** — Levenshtein distance ≤ 2 after
   normalisation, excluding duplicates. Catches plurals,
   accidental typos, emoji swaps. Distance 0 is impossible (those
   move to bucket 1); 1 ≈ off-by-one-letter; 2 ≈ extra/missing word.
3. **Duplicate IDs** — should always be empty (the API rejects
   duplicates on POST). If anything appears here, someone edited
   `data/styles.json` by hand and merged a conflict incorrectly.

## Common workflows

### "Add a new outdoor style"

1. Click **+ New style**, fill `id`, `mode`, `display_label`,
   `hook_text` on the Basic tab.
2. Set `schema_version` to 3.
3. On the **v3 / channels** tab:
   - `location_type=outdoor`
   - Check `lighting`, `weather`, `time_of_day`, `season`,
     `framing`, `clothing`.
   - Add 3–6 trigger formulations.
   - Write the dry `scene_anchor`.
   - Populate the four ambient pools (use "Fill 4 seasons" for
     season).
4. Save. Verify the lint banner is empty.
5. Run a test generation in the main app to confirm the prompt
   makes sense.

### "Fix `mirror_aesthetic` indoor+season conflict"

1. Open `mirror_aesthetic` from the list.
2. Switch to the **v3 / channels** tab.
3. Set `location_type=indoor`.
4. Uncheck `season`, `weather` from `available_channels`.
5. Clean up `trigger_pool` — remove any "full-length" / "tall
   standing" mentions (those are framing).
6. Save. The lint banner should clear.

### "I edited data/styles.json by hand"

1. Click **Reload cache** in the catalog header — the API
   re-parses the JSON and refreshes every in-memory cache.
2. Open the **Conflicts report** to make sure your edits did not
   create duplicates.
3. Fix any new lint issues via the editor (do **not** edit the
   JSON again — let the admin path own writes from now on).

## Operational notes

- **Saves are atomic.** The backend writes to `styles.json.tmp`
  and renames it. If the writer crashes mid-save, the previous
  good file survives.
- **Cache invalidation runs on save.** The next generation
  request sees the new style without restarting the worker.
- **The `?focus=<id>` query parameter** on the conflicts page
  jumps directly into the editor for that style (planned —
  current build still requires a manual click on the row).
- **`schema_version=3` is the canonical target.** v1 / v2 entries
  still render but their channels go through the legacy
  `variation_engine_v2` path — no random first-generation
  diversity. Upgrade rows to v3 the next time you touch them.
