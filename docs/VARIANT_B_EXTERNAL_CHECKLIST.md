# Variant B — чек-лист внешних консолей (OAuth, платежи, DNS)

> Этот файл — операционный чек-лист, не code. Прохождение пунктов
> необходимо для безопасного переключения трафика по плану
> `.cursor/plans/variant-b-cms-hub_3f67f47c.plan.md`.
>
> Доменная модель Variant B:
> - **Global SPA** — `https://ailookstudio.vercel.app`
> - **RU SPA + edge API** — `https://ailookstudio.ru`
> - **Railway API (CMS hub editor)** — `https://app-production-6986.up.railway.app`
> - **Legacy** — `https://ru.ailookstudio.ru` (зеркало RU edge на 2 недели,
>   потом 301 → `ailookstudio.ru`).

---

## 1. OAuth провайдеры

`redirect_uri` собирается на бэкенде из `settings.api_base_url`
(см. `src/api/v1/users.py`), поэтому сами URL уже корректные —
нужно **зарегистрировать** их у провайдеров.

### 1.1 Google Cloud Console

Console → APIs & Services → Credentials → OAuth 2.0 Client.

**Authorized JavaScript origins (добавить):**
- `https://ailookstudio.vercel.app`
- `https://ailookstudio.ru`
- `https://www.ailookstudio.ru`

**Authorized redirect URIs (должны существовать):**
- `https://app-production-6986.up.railway.app/api/v1/auth/google/callback`
- `https://ailookstudio.ru/api/v1/auth/google/callback`
- `https://ru.ailookstudio.ru/api/v1/auth/google/callback` *(удалить через
  2 недели после переключения DNS)*

### 1.2 Yandex OAuth (id.yandex.ru)

Console → Мои приложения → ваше приложение → Платформы.

**Callback URL — добавить оба:**
- `https://app-production-6986.up.railway.app/api/v1/auth/yandex/callback`
- `https://ailookstudio.ru/api/v1/auth/yandex/callback`

**Scope:** `login:email login:info` (без email-а админ-гейт не пустит).

### 1.3 VK ID (dev.vk.com)

ID-приложение → Настройки → Доверенные redirect URI.

**Добавить:**
- `https://app-production-6986.up.railway.app/api/v1/auth/vk/callback`
- `https://ailookstudio.ru/api/v1/auth/vk/callback`

### 1.4 Telegram Login Widget *(если используется)*

`@BotFather` → `/setdomain` для бота:
- основной: `ailookstudio.ru`
- дополнительный (если поддержка multi-domain недоступна, делайте
  через alias-бота для Global): `ailookstudio.vercel.app`.

---

## 2. Платежи

### 2.1 YooKassa (RU edge → `ailookstudio.ru`)

Личный кабинет YooKassa → Настройки → Уведомления / Возвраты.

**Webhook URL:** установить
`https://ailookstudio.ru/api/v1/payments/yookassa/webhook`.

**Допустимые return URLs (whitelist):**
- `https://ailookstudio.ru/payment-success`
- `https://www.ailookstudio.ru/payment-success`
- *(на период миграции)* `https://ru.ailookstudio.ru/payment-success`

**Важно:** менять webhook **после** перевода DNS `ailookstudio.ru`
на VPS. Иначе YooKassa будет постить в Vercel и платежи потеряются.

**Railway:** очистить `YOOKASSA_*` переменные у сервисов `app` /
`worker` / `bot` — Global-пользователи не должны попадать в
YooKassa flow.

### 2.2 Xsolla (Global → Railway)

Publisher Account → Webhooks.

**Webhook URL:** оставить
`https://app-production-6986.up.railway.app/api/v1/payments/xsolla/webhook`.

**Return URL (`XSOLLA_RETURN_URL` в Railway env):**
`https://ailookstudio.vercel.app/payment-success`.

**На VPS:** не задавать `XSOLLA_*` — Xsolla отключён на edge.

### 2.3 Telegram Stars / прочие провайдеры

Callback URL не имеют, конфигурация не требуется.

---

## 3. DNS

| Запись | Значение | Когда менять |
| --- | --- | --- |
| `ailookstudio.ru` A | IP VPS | После того, как RU edge готов и certbot выпустил cert |
| `www.ailookstudio.ru` A | IP VPS | Одновременно |
| `ru.ailookstudio.ru` A | IP VPS | Без изменений (зеркало) |
| `ailookstudio.vercel.app` | Vercel default | Не трогать |

Vercel Dashboard:
- удалить `ailookstudio.ru` из custom domains у Global-проекта
  (после переключения DNS — иначе SSL Vercel будет конфликтовать
  с certbot на VPS).

---

## 4. CMS replication secret

GitHub → Settings → Secrets and variables → Actions:
- добавить `CMS_REPLICATION_SECRET` (random 32+ байт hex). CI
  синкит этот секрет одновременно в Railway (`app`/`worker`) и в
  `.env.ru` на VPS — оба должны видеть одинаковое значение,
  иначе HMAC-проверка упадёт.

Проверка после деплоя:
```bash
# На VPS
docker compose -f docker-compose.ru.yml exec app \
    python -c "from src.config import settings; print(settings.resolved_cms_replication_secret[:8])"
# На Railway
railway run -s app python -c "from src.config import settings; print(settings.resolved_cms_replication_secret[:8])"
```
Префиксы должны совпасть.

---

## 5. Telegram Bot webhooks

### 5.1 Global bot (Railway)

Если в long-polling режиме — без изменений. Если webhook:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://app-production-6986.up.railway.app/telegram/webhook"
```

### 5.2 RU bot (VPS)

Если webhook:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://ailookstudio.ru/telegram/webhook"
```

---

## 6. SEO / поисковики

### 6.1 Google Search Console

- Зарегистрировать `https://ailookstudio.vercel.app` как новый
  property и подтвердить (Vercel автоматом создаст DNS TXT).
- В property `https://ailookstudio.ru` обновить sitemap →
  `https://ailookstudio.ru/sitemap.xml` (генерируется build-step'ом).

### 6.2 Yandex.Webmaster

- В property `ailookstudio.ru` обновить sitemap аналогично.
- *(опционально)* Добавить `ailookstudio.vercel.app`.

---

## 7. Порядок выполнения чек-листа

Выполнять синхронно с этапами `rollout` плана:

1. До переключения DNS:
   - §1 (OAuth — добавить новые redirect URI, **не** удалять старые),
   - §4 (CMS replication secret),
   - §5 (Telegram, если меняется webhook),
   - §6 (Search Console — зарегистрировать новые property).
2. В момент переключения DNS:
   - §3 (DNS A-записи + удалить domain из Vercel),
   - §2.1 (YooKassa webhook + return URLs).
3. После 24h smoke-теста:
   - §1 — удалить устаревшие redirect URI (`ru.ailookstudio.ru`),
   - перевести `ru.ailookstudio.ru` на 301-редирект (см. nginx.conf).
