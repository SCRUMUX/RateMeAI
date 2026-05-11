# Variant B — чек-лист внешних консолей (OAuth, платежи, DNS)

> Этот файл — операционный чек-лист, не code. Прохождение пунктов
> необходимо для безопасного переключения трафика по плану
> `.cursor/plans/variant-b-cms-hub_3f67f47c.plan.md`.

## Доменная модель

| Роль | Домен | Где живёт |
|---|---|---|
| Global SPA + Global API | `ailookstudio.vercel.app` | Vercel + Railway (`app-production-6986.up.railway.app`) |
| RU SPA + RU API (целевой) | `ailookstudio.ru` + `www.ailookstudio.ru` | VPS (139.100.200.203) |
| RU SPA + RU API (текущий) | `ru.ailookstudio.ru` | тот же VPS — оставляем как зеркало 2 недели после cutover |

> Важно: бэкенд RU edge в любой момент времени отдаёт OAuth
> `redirect_uri` от текущего значения `API_BASE_URL` в `.env.ru`.
> До DNS-переключения это `https://ru.ailookstudio.ru/...`,
> после — `https://ailookstudio.ru/...`. CI меняет это значение
> синхронно с тем, что записано в `RU_PUBLIC_BASE_URL` секрете.

---

## Фаза A — ДО переключения DNS (выполняется сейчас, без даунтайма)

В этой фазе RU-трафик ходит на `ru.ailookstudio.ru`. Цель —
убедиться, что **сегодня** всё работает, и подготовить будущее.

### A.1 OAuth — добавить URL для текущего и будущего домена

В каждой консоли в whitelist должны лежать **обе** записи: на
действующий `ru.ailookstudio.ru` и на будущий `ailookstudio.ru`.
Удалять старые URL **нельзя** — иначе сейчас всё сломается.

#### Google Cloud Console → Credentials → OAuth 2.0 Client

**Authorized JavaScript origins:**
```
https://ailookstudio.vercel.app
https://app-production-6986.up.railway.app
https://ru.ailookstudio.ru
https://ailookstudio.ru
https://www.ailookstudio.ru
```

**Authorized redirect URIs:**
```
https://app-production-6986.up.railway.app/api/v1/auth/google/callback
https://ru.ailookstudio.ru/api/v1/auth/google/callback
https://ailookstudio.ru/api/v1/auth/google/callback
```

#### Yandex OAuth (id.yandex.ru) → Мои приложения → Платформы

**Callback URL:**
```
https://app-production-6986.up.railway.app/api/v1/auth/yandex/callback
https://ru.ailookstudio.ru/api/v1/auth/yandex/callback
https://ailookstudio.ru/api/v1/auth/yandex/callback
```

**Scope:** `login:email login:info` — без `email` админ-гейт не пустит.

#### VK ID (id.vk.com / dev.vk.com) → Доверенные redirect URL

⚠️ **Путь — `/auth/vk-id/callback`, а НЕ `/auth/vk/callback`.**
В коде провайдер зарегистрирован как `vk-id` (см. `src/api/v1/users.py`).

```
https://app-production-6986.up.railway.app/api/v1/auth/vk-id/callback
https://ru.ailookstudio.ru/api/v1/auth/vk-id/callback
https://ailookstudio.ru/api/v1/auth/vk-id/callback
```

#### Telegram Login Widget *(если используется)*

`@BotFather` → `/setdomain` для бота. Можно указывать только один
домен — выбирайте **`ailookstudio.ru`** (поменяется бесшовно после
DNS-cutover'а), либо временно `ru.ailookstudio.ru`.

### A.2 CMS replication secret

GitHub → Settings → Secrets and variables → Actions:
- `CMS_REPLICATION_SECRET` — random 32+ байт hex. CI синкит этот
  секрет в Railway (`app`/`worker`) и в `.env.ru` на VPS.

Проверка после деплоя:
```bash
# На Railway
railway run -s app python -c "from src.config import settings; print(settings.resolved_cms_replication_secret[:8])"
# На VPS
ssh root@VPS 'docker compose -f /opt/ratemeai/docker-compose.ru.yml exec -T app python -c "from src.config import settings; print(settings.resolved_cms_replication_secret[:8])"'
```
Префиксы должны совпасть.

### A.3 OAuth credentials на VPS (один раз)

В GitHub Secrets должны быть:
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` *(уже есть)*
- `YANDEX_CLIENT_ID`, `YANDEX_CLIENT_SECRET` *(если пусто — кнопка
  Yandex на ru.ailookstudio.ru возвращает HTTP 503)*
- `VK_ID_APP_ID`, `VK_ID_APP_SECRET` *(именно такие имена; старые
  `VK_CLIENT_*` Pydantic игнорирует — поле в коде называется
  `vk_id_app_id`, см. [src/config.py:413-415](src/config.py))*
- `VK_SERVICE_TOKEN` *(опционально, для VK Mini App)*

CI синкает их в `.env.ru` через `deploy-ru` job (см.
[.github/workflows/ci.yml](.github/workflows/ci.yml)). Если Yandex/VK
креды добавлены вручную прямо на VPS — CI их не перезаписывает
(sync только при наличии секрета в GitHub). При смене схемы имён CI
автоматически удалит устаревшие `VK_CLIENT_*` строки из `.env.ru`.

Smoke-проверка после деплоя (в PowerShell):
```powershell
$body = @{ device_id = "diag-1" } | ConvertTo-Json
foreach ($prov in "google","yandex","vk-id") {
    "=== $prov ==="
    Invoke-WebRequest -Uri "https://ru.ailookstudio.ru/api/v1/auth/$prov/init" `
        -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
}
```
Ожидаем `200 OK` для всех трёх.

### A.4 Search Console

- Зарегистрируйте `https://ailookstudio.vercel.app` как новую property
  в Google Search Console (Vercel автоматом подтвердит DNS TXT).
- В Yandex.Webmaster property `ailookstudio.ru` уже работает — sitemap
  будет доступен после DNS-cutover'а.

---

## Фаза B — переключение DNS (момент даунтайма)

⚠️ Перед этой фазой убедитесь, что Фаза A полностью пройдена.

### B.1 Снизить TTL заранее

За **24 часа** до cutover'а зайдите в **Vercel Dashboard → Domains
→ ailookstudio.ru → DNS Records** и понизьте TTL у A-записи до
**60 секунд** (минимум, что разрешает Vercel). Это ускорит
переключение, потому что старые ответы перестанут жить в кэшах
резолверов.

### B.2 Открепить домен от Vercel-проекта

В Vercel Dashboard → ваш Global-проект → Domains:
- удалите `ailookstudio.ru` и `www.ailookstudio.ru` из доменов
  Global-проекта.
  - Vercel автоматически снимет SSL и перестанет претендовать на
    обработку запросов по этому имени.
  - Выпустить cert на VPS до этого шага не получится: пока Vercel
    держит домен, ACME HTTP-01 challenge будет уходить на Vercel.

### B.3 Поменять A-записи в Vercel DNS

Vercel Dashboard → Domains → ailookstudio.ru → DNS Records:

| Тип | Name | Value | TTL |
|---|---|---|---|
| A | `@` (или пусто = apex) | `139.100.200.203` | 60 |
| A | `www` | `139.100.200.203` | 60 |

Удалите все существующие A/AAAA записи для `@` и `www`,
указывающие на Vercel (`76.76.21.21` и т.п.).

NS-серверы (`ns1.vercel-dns.com`, `ns2.vercel-dns.com`) **не
трогайте** — Vercel продолжает быть DNS-провайдером.

### B.4 Дождаться пропагации и автоматического cutover'а

После смены A-записи:

1. Подождите 1–10 минут, пока DNS пропагируется.
2. Проверьте:
   ```powershell
   Resolve-DnsName ailookstudio.ru -Type A
   Resolve-DnsName www.ailookstudio.ru -Type A
   ```
   Оба должны вернуть `139.100.200.203`.
3. Запустите **любой** push в `main` (или вручную re-run последнего
   deploy в GitHub Actions). `deploy/ru/update.sh` сам:
   - обнаружит, что DNS указывает на VPS;
   - запросит Let's Encrypt-сертификат на `ailookstudio.ru` + `www`;
   - подключит TLS server-block в nginx;
   - сделает graceful reload.

   В логе CI ищите блок `--- DNS cut-over check (ailookstudio.ru) ---`
   и строку `[cut-over] ✅ https://ailookstudio.ru/health → 200`.

   Если cutover не сработал автоматически (например, certbot rate-limit) —
   повторный push в `main` повторит попытку. Скрипт идемпотентен.

### B.5 YooKassa — сменить webhook URL

Личный кабинет YooKassa → Настройки → Уведомления:
- **Webhook URL:** `https://ailookstudio.ru/api/v1/payments/yookassa/webhook`
- Старый URL (`https://ru.ailookstudio.ru/...`) можно оставить ещё
  на 1 неделю как backup, потом удалить.

YooKassa → Возвраты → Допустимые return URLs:
- `https://ailookstudio.ru/payment-success`
- `https://www.ailookstudio.ru/payment-success`
- *(переходный период)* `https://ru.ailookstudio.ru/payment-success`

---

## Фаза C — После DNS (через 24 часа после cutover'а)

### C.1 Удалить устаревшие OAuth redirect URI

Только когда убедились, что `https://ailookstudio.ru/...` стабильно
работает 24+ часов:

- Google Cloud Console → удалите `https://ru.ailookstudio.ru/api/v1/auth/google/callback`
- Yandex OAuth → удалите `https://ru.ailookstudio.ru/api/v1/auth/yandex/callback`
- VK ID → удалите `https://ru.ailookstudio.ru/api/v1/auth/vk-id/callback`

### C.2 Включить 301 `ru.ailookstudio.ru → ailookstudio.ru`

Server-блок для `ru.ailookstudio.ru` живёт прямо в
[deploy/ru/nginx.conf](../deploy/ru/nginx.conf). Чтобы перевести его
в 301-режим:

1. Откройте [deploy/ru/nginx.conf](../deploy/ru/nginx.conf).
2. Найдите блок `server { listen 443 ssl; ... server_name ru.ailookstudio.ru; ... }`.
3. Замените всё его содержимое (от первой `ssl_certificate` до закрывающей `}`)
   на:

   ```nginx
   ssl_certificate     /etc/letsencrypt/live/ru.ailookstudio.ru/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/ru.ailookstudio.ru/privkey.pem;
   ssl_protocols TLSv1.2 TLSv1.3;
   ssl_ciphers HIGH:!aNULL:!MD5;

   return 301 https://ailookstudio.ru$request_uri;
   ```

4. Commit + push в `main`. CI делает `git pull` на VPS,
   `update.sh` рестартует nginx → 301 активен.

**Note:** в 1.60.0 была попытка автоматизировать это через named
volume и GitHub Variable, но nginx стартовал с пустым extra-каталогом
на 1-2 секунды (`Connection refused` для https://ru.ailookstudio.ru).
Решение откатили — простой коммит в `nginx.conf` (раз в жизни
проекта) надёжнее.

Обновите `RU_PUBLIC_BASE_URL` Secret на `https://ailookstudio.ru`,
если он ещё стоит на старом значении (а также `CMS_FOLLOWER_URLS`
для Railway).

### C.3 Search Console / Webmaster

- Yandex.Webmaster: добавьте новый sitemap `https://ailookstudio.ru/sitemap.xml`.
- Google Search Console: верните на ту же property `ailookstudio.ru`,
  обновите sitemap.

### C.4 Telegram bots — two-region layout

Проект работает с **двумя независимыми Telegram-ботами**:

| Регион | Bot username | Хостинг | TELEGRAM_BOT_TOKEN | PEER_BOT_USERNAME |
|---|---|---|---|---|
| RU | `@RateMeAI_bot` | VPS | задаётся в `.env.ru` | `AI_Look_Studio_bot` |
| Global | `@AI_Look_Studio_bot` | Railway (`bot` service) | Railway env var | `RateMeAI_bot` |

Middleware [src/bot/middlewares/language_guard.py](src/bot/middlewares/language_guard.py)
перехватывает первое сообщение от каждого пользователя и проверяет
`from_user.language_code`. Если язык не соответствует региону бота
(например, `ru`-юзер написал Global-боту), middleware отвечает
коротким сообщением со ссылкой на «правильного» бота и обрывает
chain — `UserRegistrationMiddleware` НЕ вызывается, никаких записей
в Postgres не появляется. Это краеугольный камень PII-сегрегации:
RU-пользователи никогда не попадают в Railway-БД, и наоборот.

#### Шаги по миграции:

1. `/revoke` в @BotFather для старого скомпрометированного токена,
   получить свежий для `@AI_Look_Studio_bot`.
2. На Railway: `railway env set TELEGRAM_BOT_TOKEN=<новый_токен> -s bot`
   (либо через Dashboard, скриншот «Service → Variables → bot»).
3. CI автоматически проставит `TELEGRAM_BOT_USERNAME=AI_Look_Studio_bot`
   и `PEER_BOT_USERNAME=RateMeAI_bot` на Railway (services `bot` и `app`).
4. На VPS: CI автоматически проставит `TELEGRAM_BOT_USERNAME=RateMeAI_bot`
   и `PEER_BOT_USERNAME=AI_Look_Studio_bot` в `.env.ru`.
5. Webhook RU-бота:
   ```bash
   curl -X POST "https://api.telegram.org/bot<RU_TOKEN>/setWebhook" \
        -d "url=https://ailookstudio.ru/telegram/webhook" \
        -d "secret_token=<RU_BOT_WEBHOOK_SECRET>"
   ```
6. Webhook Global-бота:
   ```bash
   curl -X POST "https://api.telegram.org/bot<GLOBAL_TOKEN>/setWebhook" \
        -d "url=https://app-production-6986.up.railway.app/telegram/webhook" \
        -d "secret_token=<GLOBAL_BOT_WEBHOOK_SECRET>"
   ```
   `*_BOT_WEBHOOK_SECRET` должны различаться между регионами.

> Бесплатные boundary-проверки: попробуйте написать `/start` каждому
> боту с языковой настройкой Telegram-клиента, противоположной
> региону бота. Должен прилететь короткий приветственный текст с
> ссылкой `t.me/<другой_бот>` и никакой регистрации не происходит.

---

## Приложение — где смотреть, какой `redirect_uri` шлёт бэкенд

Если что-то не работает, единственный надёжный способ узнать
**точный** URL — спросить у самого бэкенда:

```powershell
$body = @{ device_id = "diag-$(Get-Random)" } | ConvertTo-Json
Add-Type -AssemblyName System.Web
foreach ($prov in "google","yandex","vk-id") {
    "=== $prov ==="
    $r = Invoke-WebRequest "https://ru.ailookstudio.ru/api/v1/auth/$prov/init" `
        -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
    $j = $r.Content | ConvertFrom-Json
    if ($j.authorize_url -match "redirect_uri=([^&]+)") {
        "redirect_uri: " + [System.Web.HttpUtility]::UrlDecode($matches[1])
    }
}
```

Замените `ru.ailookstudio.ru` на `ailookstudio.ru` после cutover'а.
Этот же URL должен лежать в whitelist'е соответствующего провайдера.
