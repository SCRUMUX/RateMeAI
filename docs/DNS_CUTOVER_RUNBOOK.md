# DNS cut-over runbook — `ailookstudio.ru` (Vercel → VPS)

Эта шпаргалка нужна **только в момент** переключения. Полная картина —
в `docs/VARIANT_B_EXTERNAL_CHECKLIST.md`. Здесь — минимум кликов.

## TL;DR (что делать руками)

1. **Vercel Dashboard → ваш Global-проект → Settings → Domains:**
   удалить `ailookstudio.ru` и `www.ailookstudio.ru` из доменов
   проекта (отвязать от Vercel-приложения).

2. **Vercel Dashboard → Domains → `ailookstudio.ru` → DNS Records:**
   удалить все существующие A/AAAA для `@` и `www`, прописать:

   | Type | Name | Value | TTL |
   |---|---|---|---|
   | A | `@` | **`139.100.200.203`** | 60 |
   | A | `www` | **`139.100.200.203`** | 60 |

3. Подождать 1–10 минут, пока DNS пропагируется.

4. Сделать любой push в `main` (или вручную `Re-run all jobs` для
   последнего CI-run'а в [GitHub Actions](https://github.com/SCRUMUX/RateMeAI/actions)).
   Этого достаточно — VPS сам:
   - запросит SSL-сертификат у Let's Encrypt,
   - подключит TLS-блок в nginx,
   - сделает graceful reload.

5. Открыть https://ailookstudio.ru — должна загрузиться RU SPA.

## Что я проверил автоматически (вы ничего не делаете)

- На VPS уже работает `ru.ailookstudio.ru` с правильным backend'ом
  и всеми OAuth credentials. Если DNS-переключение не сработает —
  старый адрес продолжит работать.
- `deploy/ru/nginx.conf` имеет «ленивый» include для TLS-блока
  `ailookstudio.ru` — пока сертификата нет, nginx стартует без
  попытки его загрузить.
- `deploy/ru/update.sh::maybe_dns_cutover` — идемпотентная функция,
  которая срабатывает только когда DNS уже указывает на VPS.

## Если что-то пошло не так

### CI-job `deploy-ru` зелёный, но в логе нет `[cut-over] ✅`

Значит DNS ещё не пропагировался на runner'е GitHub Actions.
Проверьте локально:
```powershell
Resolve-DnsName ailookstudio.ru -Type A -DnsOnly
Resolve-DnsName www.ailookstudio.ru -Type A -DnsOnly
```
Должно быть `139.100.200.203`. Если ещё нет — подождите ещё 5 минут
и сделайте `git commit --allow-empty -m "trigger" && git push`.

### `[cut-over] WARN: certbot failed`

Чаще всего это rate-limit Let's Encrypt (5 неуспешных попыток в час
для одного домена). Подождите час и повторите push.

Альтернатива — выпустить cert вручную на VPS:
```bash
ssh root@VPS
docker run --rm \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v ratemeai_certbot_www:/var/www/certbot \
    certbot/certbot certonly --webroot --webroot-path=/var/www/certbot \
        -d ailookstudio.ru -d www.ailookstudio.ru \
        --cert-name ailookstudio.ru \
        --email admin@ailookstudio.ru --agree-tos --no-eff-email
```
Потом снова push в `main` — update.sh установит TLS-include и сделает reload.

### Откат

Если совсем плохо — верните DNS-записи в Vercel на исходные:

| Type | Name | Value |
|---|---|---|
| A | `@` | `76.76.21.21` (или любой Vercel anycast) |
| A | `www` | `76.76.21.21` |

И верните домен в Vercel-проект (Settings → Domains → Add).
RU-сервер продолжит работать на `ru.ailookstudio.ru`.

## После успешного cutover'а

См. `docs/VARIANT_B_EXTERNAL_CHECKLIST.md` Фаза C —
через 24 часа подчистить старые OAuth URI и настроить 301-редирект
`ru.ailookstudio.ru → ailookstudio.ru`.
