# Variant B — runbook сейф-релиза

> Основной план: `.cursor/plans/variant-b-cms-hub_3f67f47c.plan.md`
> (этап 9). Этот файл — операционный пошаговый сценарий, который
> исполняется человеком с правами на Railway, VPS, DNS-регистратор и
> внешние консоли.
>
> Главная цель — переключить трафик `ailookstudio.ru` с Vercel-фронта
> на RU-edge VPS, при этом **не сломав** платежи (YooKassa) и админку
> CMS (Railway-editor + RU-edge-follower).

---

## Шаг 0. Предусловия (за день до релиза)

- Все коммиты Variant B уже в `main` (CI зелёный — `test` + `deploy-backend` + `deploy-ru`).
- На Railway применены env-переменные:
  - `CMS_ROLE=editor`
  - `CMS_FOLLOWER_URLS=https://ailookstudio.ru`
  - `CMS_REPLICATION_SECRET=<secret>` (32+ байт hex)
  - `XSOLLA_RETURN_URL=https://ailookstudio.vercel.app/payment-success`
  - `WEB_BASE_URL=https://ailookstudio.vercel.app`
  - `BOT_WEB_LANDING_URL=https://ailookstudio.vercel.app`
  - `YOOKASSA_*` — отсутствуют (CI удаляет их каждый деплой).
- На VPS в `/opt/ratemeai/.env.ru` после деплоя есть:
  - `CMS_ROLE=follower`, `CMS_MASTER_URL=https://app-production-6986.up.railway.app`
  - `CMS_REPLICATION_SECRET=<тот же secret>`
  - `WEB_BASE_URL=https://ailookstudio.ru`
  - `BOT_WEB_LANDING_URL=https://ailookstudio.ru`
  - `YOOKASSA_RETURN_URL=https://ailookstudio.ru/payment-success`
- Health-checks зелёные:
  - `curl https://app-production-6986.up.railway.app/health` → `"ok"`
  - `curl https://ru.ailookstudio.ru/health` → `"ok"` (legacy-домен ещё трафик принимает)
- Резервная копия `data/landing_content.json` снята с RU-edge.

Если хоть один пункт не выполняется — остановиться и довести до конца перед DNS-переключением.

---

## Шаг 1. Подготовить TLS на VPS

На VPS (`ssh root@<vps-ip>`):

```bash
cd /opt/ratemeai
# 1.1. Убедиться, что nginx сейчас обслуживает ru.ailookstudio.ru.
docker compose -f docker-compose.ru.yml ps nginx

# 1.2. DNS A-записи `ailookstudio.ru` и `www.ailookstudio.ru` ещё
#       НЕ переключены — они смотрят в Vercel. Поэтому certbot должен
#       пройти dry-run, иначе после переключения мы будем ждать
#       выпуска ещё 5–10 минут.
sudo bash deploy/ru/setup.sh
# (или вручную, если setup.sh уже выполнялся:)
docker run --rm \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v /var/www/certbot:/var/www/certbot \
    certbot/certbot certonly --webroot \
    --webroot-path=/var/www/certbot \
    -d ailookstudio.ru -d www.ailookstudio.ru \
    --cert-name ailookstudio.ru \
    --email admin@ailookstudio.ru --agree-tos --no-eff-email --dry-run
```

> Ожидаем `dry-run` = success. Если certbot жалуется на ACME-challenge,
> значит DNS ещё видит Vercel (что нормально) — проверьте, что nginx
> на VPS принимает запросы по обоим доменам (`server_name
> ailookstudio.ru www.ailookstudio.ru ru.ailookstudio.ru`) и что
> challenge-папка `/var/www/certbot` доступна. **Не двигаемся
> дальше**, пока dry-run не зелёный.

---

## Шаг 2. Зарегистрировать новые OAuth callback URI

Параллельно (можно делать одновременно с шагом 1):

- Google Cloud Console → добавить
  `https://ailookstudio.ru/api/v1/auth/google/callback` к Authorized redirect URIs.
- Yandex OAuth → добавить
  `https://ailookstudio.ru/api/v1/auth/yandex/callback`.
- VK ID → добавить
  `https://ailookstudio.ru/api/v1/auth/vk/callback`.
- Старые URI (`ru.ailookstudio.ru/...`) **не удалять** — нужны на
  переходный период.

Подробности: `docs/VARIANT_B_EXTERNAL_CHECKLIST.md` §1.

---

## Шаг 3. Проверить CMS-репликацию end-to-end

Всё ещё до DNS-переключения, проверим webhook вручную:

```bash
# С Railway: payload + HMAC + push на VPS legacy-host (ru.ailookstudio.ru).
railway run -s app python -c "
import asyncio, json
from src.services import cms_replication, landing_store
from src.config import settings
settings.cms_follower_urls = 'https://ru.ailookstudio.ru'
doc = landing_store.load_landing_content_fresh('ru')
print(asyncio.run(cms_replication.push_to_followers('ru', doc)))
"
```

Ожидаем `{'https://ru.ailookstudio.ru': True}`. Если False —
`docker compose logs nginx app` на VPS покажет причину (HMAC mismatch
обычно = разные значения `CMS_REPLICATION_SECRET`).

---

## Шаг 4. Сменить YooKassa webhook (т-минус 5 минут до DNS)

Личный кабинет YooKassa → Настройки → Уведомления:
- сменить URL webhook на `https://ailookstudio.ru/api/v1/payments/yookassa/webhook`;
- добавить `https://ailookstudio.ru/payment-success` в whitelist
  return URLs.

> **Важно:** этот шаг делаем **за минуту до** того, как DNS начнёт
> расходиться по миру. YooKassa уже сразу будет постить на новый
> URL — а пока DNS не переключился, новый URL ещё указывает на Vercel
> и платежи зависнут. Окно простоя — 1–2 минуты, заранее
> предупредить саппорт.

---

## Шаг 5. Переключить DNS

Регистратор:
- `ailookstudio.ru` A → IP VPS
- `www.ailookstudio.ru` A → IP VPS
- `ru.ailookstudio.ru` A — **без изменений** (зеркало).

Vercel Dashboard:
- Удалить `ailookstudio.ru` из custom domains у Global-проекта
  (иначе SSL-валидация Vercel будет конкурировать с certbot).

TTL DNS-записей рекомендуется заранее снизить до 300 секунд, чтобы
переключение прошло за <5 минут.

---

## Шаг 6. Smoke-тесты после DNS

```bash
# Headers + content-length + редирект www → apex.
curl -I https://ailookstudio.ru
curl -I https://www.ailookstudio.ru        # ожидаем 301 → apex

# Health.
curl -s https://ailookstudio.ru/health     | jq .
curl -s https://ailookstudio.ru/version.json
curl -s https://ailookstudio.ru/readiness  | jq .

# Public CMS API.
curl -s "https://ailookstudio.ru/api/v1/landing/home?market=ru" | jq .

# Auth flow (создать сессию, вызвать защищённый endpoint).
curl -s -X POST https://ailookstudio.ru/api/v1/auth/web \
     -H 'content-type: application/json' \
     -d '{"device_id":"smoke"}'

# YooKassa return страница.
curl -I https://ailookstudio.ru/payment-success
```

Через UI:
- Открыть `https://ailookstudio.ru/` — должна загрузиться RU-SPA.
- Войти Google → проверить, что админка доступна (`/admin/landing`)
  именно на `ailookstudio.vercel.app`, а не на `ailookstudio.ru`
  (RU = follower).
- Сделать тестовый платёж YooKassa (минимальный пак) → проверить,
  что webhook приходит на `ailookstudio.ru` и баланс обновляется.

---

## Шаг 7. Проверить CMS-репликацию из админки

1. На `https://ailookstudio.vercel.app/admin/landing` отредактировать
   мелочь в RU-маркете (например, копирайт в footer).
2. Сохранить.
3. Через 5–15 секунд:
   - `curl -s "https://ailookstudio.ru/api/v1/landing/home?market=ru"`
     показывает новое значение.
   - Логи RU-edge: `docker compose -f docker-compose.ru.yml logs --tail=20 app`
     содержат `cms_replicate: applied market=ru rewritten=True`.
4. Если значение не подтянулось — safety-pull (раз в час) подтянет
   автоматически. Чтобы не ждать:
   ```bash
   docker compose -f docker-compose.ru.yml exec app python -c "
   import asyncio
   from src.services import cms_replication
   doc = asyncio.run(cms_replication.fetch_snapshot_from_master('ru'))
   print(doc and 'OK' or 'EMPTY')
   "
   ```

---

## Шаг 8. Мониторинг на 24 часа

- Sentry / Datadog / `docker logs nginx app` — следить за 5xx.
- YooKassa LK → отчёты: убедиться, что webhook-и доставляются
  (нет статуса "Provider error").
- Search Console: `Sitemap` для `ailookstudio.ru` подтягивается без
  ошибок (sitemap билд-степ генерирует его из `VITE_MARKET_ID=ru`).

---

## Шаг 9 (через 14 дней). Финальная чистка

После того, как старый поддомен `ru.ailookstudio.ru` фактически
больше не используется:

1. В `deploy/ru/nginx.conf` заменить блок `server_name
   ru.ailookstudio.ru;` (legacy зеркало) на простое:
   ```nginx
   server {
       listen 443 ssl;
       http2 on;
       server_name ru.ailookstudio.ru;
       ssl_certificate     /etc/letsencrypt/live/ru.ailookstudio.ru/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/ru.ailookstudio.ru/privkey.pem;
       return 301 https://ailookstudio.ru$request_uri;
   }
   ```
2. Удалить устаревшие redirect URI из Google/Yandex/VK
   (`ru.ailookstudio.ru/api/v1/auth/*/callback`).
3. Удалить `https://ru.ailookstudio.ru` из CORS в `src/main.py`.
4. Закоммитить и задеплоить.

---

## Откат

Если что-то пошло не так после DNS-переключения:

1. Откатить DNS `ailookstudio.ru` обратно на Vercel IP.
2. Вернуть YooKassa webhook на legacy URL
   (`https://ru.ailookstudio.ru/api/v1/payments/yookassa/webhook`).
3. Контент CMS на VPS не пострадал — `data/landing_content.json`
   на месте, репликация только дописывает, не удаляет.
4. Опционально: удалить новые redirect URI из OAuth-консолей, если
   подозреваем misconfiguration.

Время отката: ~10–15 минут (DNS distributuion) + 5 минут (YooKassa).
