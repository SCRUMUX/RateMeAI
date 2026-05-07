# Scenario Platform — Rollout (Stage 6)

Готово к деплою. Все локальные проверки прошли:

- `python -m ruff check src/ tests/ --select=E,F,W --ignore=E501` → All checks passed!
- `python -c "import py_compile; py_compile.compile(r'src\main.py', doraise=True)"` → OK
- `npx tsc --noEmit` (в `web/`) → OK
- `python -m pytest tests/ ...` → 1943 passed (включая новые 23 scenario-теста)

## Контур изменений

| Слой | Файлы | Эффект для прода |
|---|---|---|
| Доки | `docs/architecture/scenario_platform.md`, `_rollout.md` | Только чтение |
| i18n инфра | `web/src/locales/{ru,en}/*`, `web/src/lib/i18n.ts`, `web/src/main.tsx` | На RU edge поведение идентично, на global SPA рендерит EN для подключённых ключей |
| Scenario Engine (бэк) | `src/scenarios/`, `src/api/v1/scenarios.py`, `src/api/router.py`, `src/services/visa_compliance.py` | Новые публичные эндпоинты `/api/v1/scenarios[, /{slug}, /{slug}/compliance]` |
| Prompt overrides | `src/prompts/engine.py`, `src/orchestrator/executor.py`, `src/orchestrator/pipeline.py` | Дополнительный текст в image-prompt только при `enabled: true` визовом сценарии |
| Visa data | `data/scenarios.json`, `data/visa_requirements.json`, `data/styles.json`, `data/landing_content.json`, `web/public/sitemap.xml` | 9 визовых лендингов (Schengen, USA, UK, Canada, Japan, China, UAE, Australia, Korea, India) — SCEnabled, доступны по `/visa/<country>` |
| Visa SPA | `web/src/pages/VisaLanding.tsx`, `VisaPage.tsx`, `web/src/scenarios/visas.ts`, `config.ts`, `App.tsx` | Маршрут `/visa/:country` с обёрткой над AppPage (re-use document flow) |
| Tests | `tests/test_scenarios/*`, `tests/test_api/test_scenarios.py` | +23 unit/integration tests |

## Чек-лист деплоя

Согласно `.cursor/rules/deploy.mdc`:

1. Локально перед коммитом:
   ```powershell
   python -m ruff check src/ tests/ --select=E,F,W --ignore=E501
   cd web; npx tsc --noEmit; cd ..
   python -c "import py_compile; py_compile.compile(r'src\main.py', doraise=True)"
   python -m pytest tests/test_scenarios tests/test_api/test_scenarios.py -q
   ```
2. Коммит:
   ```powershell
   git add -A; git commit -m "feat: scenario engine + visa platform (i18n, 9 visa scenarios)"
   ```
3. Пуш на оба сервера автоматически (CI/CD):
   ```powershell
   git push origin main
   ```
4. Health-check после деплоя:
   ```powershell
   Invoke-RestMethod -Uri "https://app-production-6986.up.railway.app/health" | ConvertTo-Json
   Invoke-RestMethod -Uri "https://app-production-6986.up.railway.app/api/v1/scenarios" | ConvertTo-Json
   Invoke-WebRequest -Uri "https://ailookstudio.vercel.app/visa/schengen" -UseBasicParsing | Select-Object StatusCode
   ```
5. Smoke `https://ailookstudio.vercel.app/visa/schengen` → должна загрузиться лендинг-страница, JSON-LD виден в DevTools.

## Поэтапная альтернатива (если нужен поэтапный rollout)

Текущая работа объединена в один merge — план изначально подразумевал
один PR на этап. Если требуется поэтапный rollout, можно
интерактивно разделить через `git rebase -i` на семь логических
коммитов:

1. `docs: scenario platform architecture`
2. `feat(web): i18n infrastructure (i18next + ru/en locales)`
3. `feat: backend scenario engine (loader, registry, /api/v1/scenarios)`
4. `feat(web): VisaLanding + VisaPage + /visa/:country route`
5. `feat: 10 visa scenarios (Schengen, USA, UK, Canada, Japan, China, UAE, Australia, Korea, India)`
6. `feat: JSON-LD on document/visa landings + sitemap`
7. `test: scenario loader + visa_compliance + prompt overrides + /api/v1/scenarios`

Каждый коммит самодостаточен (тесты проходят независимо).

## Откат

`scenarios.json:enabled=false` для всех визовых scenario'ев → лендинги
отдают 404 от `/api/v1/scenarios/{slug}/compliance`, маршрут
`/visa/:country` редиректит на `/` (см. `VisaPage.tsx`). Frontend SPA
keeps shipping the static SCENARIO_LIST as a fallback, поэтому
runtime-сюрпризов при отключении бэкенд-стороны не будет.
