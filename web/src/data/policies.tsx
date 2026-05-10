import { type ReactNode } from 'react';
import i18next from 'i18next';
import { getAppLanguage } from '../lib/i18n';

export type PolicyId = 'privacy' | 'terms' | 'consents' | 'cookie' | 'refund';

export interface PolicyEntry {
  id: PolicyId;
  title: string;
  shortTitle: string;
  lastUpdated: string;
  body: ReactNode;
}

// 1.57.0 — titles/shortTitles are sourced lazily from the ``policies``
// i18n namespace. Body text remains the long-form Russian legal copy
// (the documents legally apply to RU residents); on the EN build we
// surface a notice block in :class:`PolicyModal` pointing the user at
// privacy@ailookstudio.ru for an English version.
const FALLBACK_TITLES: Record<PolicyId, string> = {
  privacy: 'Политика конфиденциальности',
  terms: 'Условия использования',
  consents: 'Согласия на обработку данных',
  cookie: 'Использование cookies',
  refund: 'Возврат средств',
};

const FALLBACK_SHORT_TITLES: Record<PolicyId, string> = {
  privacy: 'Конфиденциальность',
  terms: 'Условия',
  consents: 'Согласия',
  cookie: 'Cookies',
  refund: 'Возврат',
};

function tPolicy(key: string, fallback: string): string {
  if (i18next.isInitialized && i18next.exists(key, { ns: 'policies' })) {
    return i18next.t(key, { ns: 'policies' });
  }
  return fallback;
}

export function getPolicyTitle(id: PolicyId): string {
  return tPolicy(`titles.${id}`, FALLBACK_TITLES[id]);
}

export function getPolicyShortTitle(id: PolicyId): string {
  return tPolicy(`shortTitles.${id}`, FALLBACK_SHORT_TITLES[id]);
}

export function getPolicyLastUpdated(): string {
  return tPolicy('lastUpdated', '2026-04-20');
}

const sectionH = 'text-[22px] font-semibold mt-6 mb-3';
const inlineLink = 'text-[var(--color-link-default)] underline';
const ul = 'list-disc pl-6 space-y-2';

// ---------------------------------------------------------------------------
// Privacy policy body — single source of truth for both the /privacy page
// and the in-page modal (PolicyModal).
//
// 1.59.2 — split per market: ``PrivacyBodyRu`` is the legal master copy
// for ``ailookstudio.ru`` (152-FZ + GDPR + CCPA), ``PrivacyBodyEn`` is
// the equivalent international version (rendered on the global SPA
// hosted on Vercel) with the Russian-specific references stripped.
// ``PrivacyBody`` dispatches by ``getAppLanguage()`` so the same modal/page
// renders the right language at build time.
// ---------------------------------------------------------------------------
function PrivacyBodyRu() {
  return (
    <>
      <section>
        <h2 className={sectionH}>1. Общие положения</h2>
        <p>
          Настоящая Политика определяет порядок обработки персональных данных
          пользователей сервиса <strong>Look Studio</strong> (далее — «Сервис»),
          принадлежащего оператору <strong>[НАИМЕНОВАНИЕ ОПЕРАТОРА]</strong>
          {' '}(далее — «Оператор»), адрес: [АДРЕС ОПЕРАТОРА], ИНН [ИНН],
          e-mail:{' '}
          <a className={inlineLink} href="mailto:privacy@ailookstudio.ru">privacy@ailookstudio.ru</a>.
        </p>
        <p>
          Политика составлена в соответствии с требованиями Федерального закона
          от 27.07.2006 № 152-ФЗ «О персональных данных» (РФ), Регламента
          Европейского парламента и Совета (ЕС) 2016/679 (GDPR) и California
          Consumer Privacy Act (CCPA/CPRA, США).
        </p>
      </section>

      <section>
        <h2 className={sectionH}>2. Какие данные мы обрабатываем</h2>
        <ul className={ul}>
          <li><strong>Фотографии</strong>, которые вы загружаете в Сервис для AI-обработки (включая изображения с лицом).</li>
          <li><strong>Метаданные Telegram-аккаунта</strong> (tg_user_id, username) — только при входе через Telegram-бот.</li>
          <li><strong>E-mail или номер телефона</strong> — только если вы используете их для входа на сайт.</li>
          <li><strong>Технические данные</strong>: хэш IP-адреса, хэш User-Agent, идентификатор сессии. Сырые IP/User-Agent не хранятся.</li>
          <li><strong>Платёжные данные</strong> — обрабатываются платёжным провайдером (YooKassa), Оператор получает только факт оплаты и сумму.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>3. О биометрических данных</h2>
        <p>
          <strong>Важно.</strong> Оператор <u>не осуществляет обработку биометрических
          персональных данных</u> в смысле ст. 11 152-ФЗ и ст. 9 GDPR, поскольку:
        </p>
        <ul className={ul}>
          <li>Оператор <strong>не извлекает и не хранит</strong> биометрические признаки (feature-векторы, ArcFace/FaceNet-эмбеддинги, геометрию лица).</li>
          <li>Оператор <strong>не использует изображение для установления личности</strong> пользователя и не сопоставляет его с государственными или частными базами лиц.</li>
          <li>Проверка «сохранения внешности» производится <strong>Vision Language Model</strong> как визуальное сравнение двух кадров без извлечения биометрических векторов; результат сравнения (число 0–10) не сохраняется в привязке к пользователю.</li>
          <li>Загруженное изображение <strong>удаляется из оперативной памяти и Redis-стежа не позднее чем через 15 минут</strong> после загрузки и никогда не попадает в долговременное хранилище.</li>
        </ul>
        <p>
          Если будущие изменения функциональности потребуют фактической биометрической
          идентификации, Оператор обязуется отдельно получить письменное согласие
          пользователя (ч. 1 ст. 11 152-ФЗ) и уведомить Роскомнадзор.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>4. Цели обработки</h2>
        <ul className={ul}>
          <li>Генерация AI-обработанных изображений по вашему запросу.</li>
          <li>Предоставление доступа к личному кабинету и сохранённым результатам.</li>
          <li>Биллинг и учёт потреблённых кредитов.</li>
          <li>Техническая поддержка, предотвращение злоупотреблений.</li>
          <li>Передача изображений внешним AI-провайдерам (OpenRouter, Reve, Replicate) — <strong>только при вашем явном согласии</strong>.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>5. Правовые основания</h2>
        <ul className={ul}>
          <li><strong>Согласие субъекта</strong> (п. 1 ч. 1 ст. 6 152-ФЗ, п. a ч. 1 ст. 6 GDPR) — для основной обработки изображений.</li>
          <li><strong>Отдельное согласие</strong> — для трансграничной передачи изображений внешним AI-сервисам.</li>
          <li><strong>Исполнение договора</strong> (п. b ч. 1 ст. 6 GDPR) — для биллинга.</li>
          <li><strong>Законный интерес</strong> — для предотвращения злоупотреблений (hash-based rate limiting без сырых IP).</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>6. Возрастное ограничение</h2>
        <p>
          Сервис предназначен для лиц старше <strong>16 лет</strong>. При регистрации
          вы подтверждаете, что достигли 16-летнего возраста. Если вы младше 16 лет,
          вы не можете использовать Сервис.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>7. Сроки хранения</h2>
        <ul className={ul}>
          <li><strong>Оригиналы загруженных фото</strong> — не более 15 минут в Redis-стеже, далее физически удаляются.</li>
          <li><strong>Сгенерированные изображения</strong> — 72 часа, далее физически удаляются фоновым процессом.</li>
          <li><strong>Учётная запись и согласия</strong> — до момента запроса на удаление или 1 год неактивности.</li>
          <li><strong>Платёжные операции</strong> — 3 года (требование налогового законодательства РФ).</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>8. Трансграничная передача</h2>
        <p>При установленном согласии изображения передаются в следующие сервисы:</p>
        <ul className={ul}>
          <li><strong>OpenRouter</strong> (США) — анализ изображения моделью VLM.</li>
          <li><strong>Reve</strong> (США) — генерация изображений.</li>
          <li><strong>Replicate</strong> (США) — генерация изображений.</li>
        </ul>
        <p>
          Без согласия на трансграничную передачу API возвращает HTTP 451 и Сервис
          не выполняет внешний запрос. Вы можете отозвать согласие в личном кабинете.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>9. Ваши права</h2>
        <p>В соответствии с законодательством вы имеете право:</p>
        <ul className={ul}>
          <li><strong>Получать информацию</strong> о составе и целях обработки (ст. 14 152-ФЗ, ст. 15 GDPR, CCPA §1798.110).</li>
          <li><strong>Требовать удаления</strong> всех ваших данных — <code className="mx-1">DELETE /api/v1/users/me</code>.</li>
          <li><strong>Экспортировать данные</strong> в машиночитаемом виде — <code className="mx-1">GET /api/v1/users/me/export</code>.</li>
          <li><strong>Отозвать согласие</strong> на обработку или трансграничную передачу в личном кабинете.</li>
          <li><strong>Не соглашаться на продажу данных</strong> (Оператор не продаёт персональные данные третьим лицам).</li>
          <li><strong>Обжаловать</strong> действия Оператора в Роскомнадзор (РФ), Supervisory Authority (ЕС) или California Attorney General (США).</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>10. AI-прозрачность</h2>
        <p>Все сгенерированные изображения маркируются:</p>
        <ul className={ul}>
          <li><strong>Визуальным бейджем</strong> «Сгенерировано AI» на предпросмотре и share-карточке.</li>
          <li><strong>EXIF-метаданными</strong> <code>UserComment=AI-generated by AI Look Studio</code> в JPEG-файле.</li>
        </ul>
        <p>Эти меры соответствуют требованиям EU AI Act (Art. 50) по прозрачности AI-контента.</p>
      </section>

      <section>
        <h2 className={sectionH}>11. Безопасность</h2>
        <ul className={ul}>
          <li>Весь трафик — HTTPS (TLS 1.2+).</li>
          <li>Хранилища защищены приватными сетевыми сегментами.</li>
          <li>Логи фильтруются PII-фильтром: image-байты и base64 не попадают в логи.</li>
          <li>IP/User-Agent хэшируются перед сохранением.</li>
          <li>Процесс автоматического удаления физически удаляет истёкшие генерации каждые N минут.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>12. Контакты</h2>
        <p>
          Вопросы, запросы на удаление, отзыв согласия:{' '}
          <a className={inlineLink} href="mailto:privacy@ailookstudio.ru">privacy@ailookstudio.ru</a>
        </p>
        <p>Оператор обязуется рассмотреть обращение в течение <strong>30 дней</strong>.</p>
      </section>

      <section>
        <h2 className={sectionH}>13. Изменения</h2>
        <p>
          Оператор вправе обновить Политику. Актуальная версия всегда доступна по адресу{' '}
          <a className={inlineLink} href="https://ailookstudio.ru/privacy">https://ailookstudio.ru/privacy</a>.
          При существенных изменениях мы повторно запрашиваем согласие.
        </p>
      </section>
    </>
  );
}

// ---------------------------------------------------------------------------
// Terms / public offer body — placeholder template marked for legal review.
// ---------------------------------------------------------------------------
function TermsBodyRu() {
  return (
    <>
      <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-[13px] text-yellow-200">
        Шаблон документа. Финальный текст должен быть согласован с юристом и
        содержать реквизиты юридического лица.
      </div>

      <section>
        <h2 className={sectionH}>1. Предмет соглашения</h2>
        <p>
          Настоящие Условия использования (далее — «Условия» или «Оферта»)
          регулируют отношения между <strong>[НАИМЕНОВАНИЕ ОПЕРАТОРА]</strong>
          {' '}(далее — «Оператор») и любым лицом (далее — «Пользователь»),
          использующим сервис <strong>Look Studio</strong> (далее — «Сервис»).
        </p>
        <p>
          Использование Сервиса означает безоговорочное принятие настоящих
          Условий. Если вы не согласны с Условиями — прекратите использование
          Сервиса.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>2. Описание сервиса</h2>
        <p>
          Сервис предоставляет AI-инструменты для анализа и улучшения
          фотографий: оценка восприятия, генерация улучшенных версий, подбор
          стилей под различные сценарии (соцсети, знакомства, документы,
          резюме).
        </p>
      </section>

      <section>
        <h2 className={sectionH}>3. Оплата и тарифы</h2>
        <ul className={ul}>
          <li>Оплата производится через платёжного провайдера (YooKassa и др.) — Оператор не получает данные банковской карты.</li>
          <li>Стоимость пакетов опубликована на странице{' '}
            <a className={inlineLink} href="/#тарифы">«Тарифы»</a> и может изменяться. Действует цена, актуальная на момент покупки.</li>
          <li>После оплаты на счёт Пользователя зачисляются генерационные кредиты, расходуемые при использовании Сервиса.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>4. Возврат средств</h2>
        <p>
          Возврат возможен в течение <strong>14 дней</strong> с момента оплаты,
          если кредиты не были израсходованы. Запрос на возврат направляется на
          {' '}<a className={inlineLink} href="mailto:support@ailookstudio.ru">support@ailookstudio.ru</a>{' '}
          с указанием номера операции.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>5. Ограничения и ответственность</h2>
        <ul className={ul}>
          <li>Сервис предоставляется «как есть» (as-is). Оператор не гарантирует, что результат AI-обработки полностью удовлетворит ожидания Пользователя.</li>
          <li>Запрещена загрузка чужих фото без согласия изображённых лиц, материалов с несовершеннолетними и любого иного незаконного контента.</li>
          <li>Оператор оставляет за собой право заблокировать аккаунт при нарушении Условий без возврата средств.</li>
          <li>Оператор не несёт ответственности за косвенные убытки и упущенную выгоду.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>6. Интеллектуальная собственность</h2>
        <p>
          Пользователь сохраняет права на загруженные оригинальные фотографии.
          Сгенерированные изображения предоставляются Пользователю на условиях
          неисключительной лицензии для личного и коммерческого использования
          (соцсети, резюме, аватарки и т. п.).
        </p>
      </section>

      <section>
        <h2 className={sectionH}>7. Контакты</h2>
        <p>
          Вопросы по Условиям и оплате:{' '}
          <a className={inlineLink} href="mailto:support@ailookstudio.ru">support@ailookstudio.ru</a>.
        </p>
      </section>
    </>
  );
}

// ---------------------------------------------------------------------------
// User consents body — derived from ConsentGate.tsx required kinds.
// ---------------------------------------------------------------------------
function ConsentsBodyRu() {
  return (
    <>
      <p>
        Перед началом работы Сервис запрашивает у вас три обязательных согласия.
        Каждое можно отозвать в любой момент в настройках профиля.
      </p>

      <section>
        <h2 className={sectionH}>Обработка персональных данных</h2>
        <p>
          <strong>Я даю согласие на обработку персональных данных, включая фото лица.</strong>
        </p>
        <p>
          Без этого согласия Сервис не может принять файл для обработки. Оригинал
          фото не сохраняется: после обработки он удаляется из оперативной памяти
          и Redis-стежа не позднее 15 минут с момента загрузки. Скоры и
          сгенерированное изображение хранятся не более 72 часов.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>Передача во внешние AI-сервисы</h2>
        <p>
          <strong>
            Я соглашаюсь на передачу фото во внешние AI-сервисы (OpenRouter, Reve и др.),
            в том числе за пределы РФ.
          </strong>
        </p>
        <p>
          Это юридически обязательное согласие на трансграничную передачу
          (ст. 12 152-ФЗ, гл. V GDPR). Без него API возвращает HTTP 451 и
          генерация не выполняется.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>Возрастное подтверждение</h2>
        <p>
          <strong>
            Мне 16 лет или больше. Я понимаю, что Сервис не предназначен для лиц
            младше 16 лет.
          </strong>
        </p>
        <p>
          Требование ст. 8 GDPR и внутренних политик. При ложном подтверждении
          аккаунт может быть заблокирован.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>Управление согласиями</h2>
        <p>
          Все ваши согласия видны в личном кабинете. API:
          {' '}<code className="mx-1">GET /api/v1/users/me/consents</code>,{' '}
          <code className="mx-1">POST /api/v1/users/me/consents/revoke</code>.
        </p>
      </section>
    </>
  );
}

// ---------------------------------------------------------------------------
// Cookie policy body — short summary of what we drop in the user's browser
// and how to manage it. We deliberately keep functional/security cookies
// (auth session, CSRF) and avoid third-party trackers.
// ---------------------------------------------------------------------------
function CookieBodyRu() {
  return (
    <>
      <p>
        Look Studio использует минимальный набор cookie и аналогичных
        технологий (localStorage, sessionStorage), необходимых для работы
        Сервиса и анализа базовой статистики посещений.
      </p>

      <section>
        <h2 className={sectionH}>1. Какие cookie мы используем</h2>
        <ul className={ul}>
          <li>
            <strong>Функциональные.</strong> Сессионный токен авторизации, выбор
            темы, прогресс мастера. Без них Сервис не работает; согласие на их
            установку считается данным фактом использования сайта.
          </li>
          <li>
            <strong>Аналитические (по согласию).</strong> Анонимная статистика
            посещений (Yandex.Metrica или Plausible). Используются только
            хэшированные идентификаторы устройства, без сырых IP-адресов.
          </li>
          <li>
            <strong>Платёжные.</strong> Cookie платёжного провайдера YooKassa —
            ставятся при инициации оплаты и подчиняются их политике.
          </li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>2. Сторонние сервисы</h2>
        <p>
          Мы не передаём данные пользователей рекламным сетям. Сторонние
          AI-провайдеры (см.{' '}
          <a className={inlineLink} href="/?policy=privacy">Политику конфиденциальности</a>)
          получают только содержимое запроса на генерацию и не получают
          доступа к cookie сайта.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>3. Как управлять cookie</h2>
        <ul className={ul}>
          <li>Большинство браузеров позволяют удалить cookie или запретить их через настройки.</li>
          <li>Запрет функциональных cookie приведёт к невозможности входа в личный кабинет.</li>
          <li>Согласие на аналитику можно отозвать в разделе{' '}
            <a className={inlineLink} href="/?policy=consents">«Согласия на обработку»</a>.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>4. Контакты</h2>
        <p>
          Вопросы по cookie:{' '}
          <a className={inlineLink} href="mailto:privacy@ailookstudio.ru">privacy@ailookstudio.ru</a>.
        </p>
      </section>
    </>
  );
}

// ---------------------------------------------------------------------------
// Refund policy body — extracted summary of section 4 of TermsBody, kept
// in sync (manual). The full ToS is the source of truth in case of conflict.
// ---------------------------------------------------------------------------
function RefundBodyRu() {
  return (
    <>
      <p>
        Возврат средств за покупку пакетов кредитов в Look Studio
        осуществляется на условиях, описанных ниже. Полный текст содержится в
        {' '}
        <a className={inlineLink} href="/?policy=terms">Условиях использования</a>.
      </p>

      <section>
        <h2 className={sectionH}>1. Срок и основания</h2>
        <ul className={ul}>
          <li>Запрос на возврат принимается в течение <strong>14 дней</strong> с момента оплаты.</li>
          <li>Возврат возможен только за <strong>неиспользованные кредиты</strong>. Сумма пропорциональна остатку: использованные кредиты не возвращаются.</li>
          <li>В случае технического сбоя по нашей вине кредиты автоматически возвращаются на счёт без оформления заявки.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>2. Процедура</h2>
        <ol className="list-decimal pl-6 space-y-2">
          <li>Напишите на{' '}
            <a className={inlineLink} href="mailto:support@ailookstudio.ru">support@ailookstudio.ru</a>{' '}
            или в{' '}
            <a className={inlineLink} href="https://t.me/ailookstudio_support" target="_blank" rel="noopener noreferrer">Telegram-поддержку</a>.</li>
          <li>Укажите номер операции (можно найти в письме от YooKassa) и причину возврата.</li>
          <li>Мы подтвердим обращение и инициируем возврат через платёжного провайдера.</li>
        </ol>
      </section>

      <section>
        <h2 className={sectionH}>3. Сроки рассмотрения</h2>
        <ul className={ul}>
          <li>Первичный ответ — в течение <strong>24 часов</strong> в рабочие дни.</li>
          <li>Решение по заявке — до <strong>30 календарных дней</strong> (в большинстве случаев — 1–3 дня).</li>
          <li>Срок зачисления возврата на карту определяется банком-эмитентом и обычно составляет 3–10 рабочих дней.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>4. Когда возврат невозможен</h2>
        <ul className={ul}>
          <li>Все кредиты в пакете уже израсходованы.</li>
          <li>Прошло более 14 дней с момента оплаты.</li>
          <li>Аккаунт заблокирован за нарушение Условий использования.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>5. Контакты</h2>
        <p>
          E-mail:{' '}
          <a className={inlineLink} href="mailto:support@ailookstudio.ru">support@ailookstudio.ru</a>{' '}
          · Telegram:{' '}
          <a className={inlineLink} href="https://t.me/ailookstudio_support" target="_blank" rel="noopener noreferrer">@ailookstudio_support</a>.
        </p>
      </section>
    </>
  );
}

// ===========================================================================
// EN policy bodies — served on the global SPA (ailookstudio.vercel.app or
// any custom global domain). They keep the same section structure as the
// RU master copy, but drop the Russia-specific 152-FZ / Roskomnadzor
// references and instead lead with GDPR + CCPA/CPRA. Contact addresses
// stay on ``ailookstudio.ru`` because that is the only mailbox we own
// today; replace globally when a dedicated international domain ships.
// ===========================================================================

function PrivacyBodyEn() {
  return (
    <>
      <section>
        <h2 className={sectionH}>1. General provisions</h2>
        <p>
          This Privacy Policy describes how the <strong>Look Studio</strong> service
          (the “Service”), operated by <strong>[OPERATOR NAME]</strong> (the
          “Operator”, address: [OPERATOR ADDRESS], company number: [REGISTRATION
          ID], e-mail:{' '}
          <a className={inlineLink} href="mailto:privacy@ailookstudio.ru">privacy@ailookstudio.ru</a>),
          collects, stores and protects users' personal data.
        </p>
        <p>
          The Policy is drafted in line with Regulation (EU) 2016/679 (GDPR) and
          the California Consumer Privacy Act (CCPA/CPRA, USA), and applies to
          every visitor of the Service regardless of their location.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>2. Data we process</h2>
        <ul className={ul}>
          <li><strong>Photos</strong> you upload to the Service for AI processing (including images that contain a face).</li>
          <li><strong>Telegram account metadata</strong> (tg_user_id, username) — only when you sign in through the Telegram bot.</li>
          <li><strong>E-mail or phone number</strong> — only if you use them to sign in to the website.</li>
          <li><strong>Technical data</strong>: hashed IP address, hashed User-Agent, session id. Raw IP / User-Agent are not stored.</li>
          <li><strong>Payment data</strong> — handled by the payment provider; the Operator only receives the fact of payment and the amount.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>3. About biometric data</h2>
        <p>
          <strong>Important.</strong> The Operator <u>does not process biometric
          personal data</u> within the meaning of Art. 9 GDPR, because:
        </p>
        <ul className={ul}>
          <li>The Operator <strong>does not extract or store</strong> biometric features (feature vectors, ArcFace/FaceNet embeddings, face geometry).</li>
          <li>The Operator <strong>does not use the image to identify</strong> the user, and does not match it against any government or private face database.</li>
          <li>The “appearance preservation” check is performed by a <strong>Vision Language Model</strong> as a visual comparison of two frames without extracting biometric vectors; the comparison result (a number 0–10) is not stored against the user.</li>
          <li>The uploaded image is <strong>removed from RAM and Redis no later than 15 minutes</strong> after upload, and never reaches long-term storage.</li>
        </ul>
        <p>
          Should future functionality require biometric identification, the
          Operator will request a separate written consent from the user before
          enabling it.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>4. Purposes of processing</h2>
        <ul className={ul}>
          <li>Generating AI-processed images at your request.</li>
          <li>Granting access to the personal account and saved results.</li>
          <li>Billing and tracking spent credits.</li>
          <li>Technical support, abuse prevention.</li>
          <li>Forwarding images to external AI providers (OpenRouter, Reve, Replicate) — <strong>only with your explicit consent</strong>.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>5. Legal grounds</h2>
        <ul className={ul}>
          <li><strong>Consent of the data subject</strong> (Art. 6(1)(a) GDPR) — for the core image processing.</li>
          <li><strong>Separate consent</strong> — for cross-border transfer of images to external AI services.</li>
          <li><strong>Performance of a contract</strong> (Art. 6(1)(b) GDPR) — for billing.</li>
          <li><strong>Legitimate interest</strong> — for abuse prevention (hash-based rate limiting without raw IPs).</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>6. Age limit</h2>
        <p>
          The Service is intended for users <strong>16 or older</strong>. By
          registering you confirm that you meet this age requirement. If you are
          under 16, you must not use the Service.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>7. Retention periods</h2>
        <ul className={ul}>
          <li><strong>Original uploaded photos</strong> — no longer than 15 minutes in the Redis stash, then physically deleted.</li>
          <li><strong>Generated images</strong> — 72 hours, then physically deleted by a background job.</li>
          <li><strong>Account and consent records</strong> — until you request deletion or after 1 year of inactivity.</li>
          <li><strong>Payment transactions</strong> — kept for the period required by applicable tax legislation.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>8. Cross-border transfers</h2>
        <p>If consent is granted, images are forwarded to the following services:</p>
        <ul className={ul}>
          <li><strong>OpenRouter</strong> (USA) — image analysis by a VLM model.</li>
          <li><strong>Reve</strong> (USA) — image generation.</li>
          <li><strong>Replicate</strong> (USA) — image generation.</li>
        </ul>
        <p>
          Without a cross-border transfer consent the API returns HTTP 451 and the
          Service makes no external request. You can revoke the consent at any
          time from your personal account.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>9. Your rights</h2>
        <p>You have the right to:</p>
        <ul className={ul}>
          <li><strong>Be informed</strong> about the scope and purposes of processing (Art. 15 GDPR, CCPA §1798.110).</li>
          <li><strong>Request deletion</strong> of all your data — <code className="mx-1">DELETE /api/v1/users/me</code>.</li>
          <li><strong>Export your data</strong> in machine-readable form — <code className="mx-1">GET /api/v1/users/me/export</code>.</li>
          <li><strong>Withdraw consent</strong> for processing or cross-border transfers from your account.</li>
          <li><strong>Opt out of the sale of personal data</strong> (the Operator does not sell personal data to third parties).</li>
          <li><strong>Lodge a complaint</strong> with the relevant Supervisory Authority (EU) or California Attorney General (USA).</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>10. AI transparency</h2>
        <p>Every generated image is marked:</p>
        <ul className={ul}>
          <li>With a <strong>visual badge</strong> “AI-generated” on the preview and share card.</li>
          <li>With <strong>EXIF metadata</strong> <code>UserComment=AI-generated by AI Look Studio</code> in the JPEG file.</li>
        </ul>
        <p>These measures meet the AI transparency requirements of the EU AI Act (Art. 50).</p>
      </section>

      <section>
        <h2 className={sectionH}>11. Security</h2>
        <ul className={ul}>
          <li>All traffic is HTTPS (TLS 1.2+).</li>
          <li>Storage is isolated to private network segments.</li>
          <li>Logs go through a PII filter: image bytes and base64 payloads never reach the log stream.</li>
          <li>IP / User-Agent values are hashed before being stored.</li>
          <li>An automated job physically deletes expired generations every few minutes.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>12. Contacts</h2>
        <p>
          Questions, deletion or consent withdrawal requests:{' '}
          <a className={inlineLink} href="mailto:privacy@ailookstudio.ru">privacy@ailookstudio.ru</a>
        </p>
        <p>The Operator will respond within <strong>30 days</strong>.</p>
      </section>

      <section>
        <h2 className={sectionH}>13. Changes</h2>
        <p>
          The Operator may update this Policy. The current version is always
          available at{' '}
          <a className={inlineLink} href="/privacy">/privacy</a>.
          Material changes will trigger a fresh consent prompt.
        </p>
      </section>
    </>
  );
}

function TermsBodyEn() {
  return (
    <>
      <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-[13px] text-yellow-200">
        Template document. The final wording must be reviewed by counsel and
        contain the legal entity's registration details.
      </div>

      <section>
        <h2 className={sectionH}>1. Subject of the agreement</h2>
        <p>
          These Terms of Use (the “Terms” or “Offer”) govern the relationship
          between <strong>[OPERATOR NAME]</strong> (the “Operator”) and any
          person (the “User”) using the <strong>Look Studio</strong> service
          (the “Service”).
        </p>
        <p>
          Using the Service constitutes unconditional acceptance of these
          Terms. If you do not agree with the Terms, please stop using the
          Service.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>2. Service description</h2>
        <p>
          The Service provides AI tools for photo analysis and enhancement:
          perception scoring, generation of improved variants, and style
          selection for different scenarios (social media, dating, documents,
          resume).
        </p>
      </section>

      <section>
        <h2 className={sectionH}>3. Payment and pricing</h2>
        <ul className={ul}>
          <li>Payments are processed by a third-party payment provider — the Operator does not receive payment card data.</li>
          <li>Prices are published on the{' '}
            <a className={inlineLink} href="/#pricing">Pricing</a> page and may change. The price displayed at checkout applies.</li>
          <li>Once paid, the User's account is credited with generation credits, which are spent while using the Service.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>4. Refunds</h2>
        <p>
          Refunds are available within <strong>14 days</strong> of payment if
          the credits have not been used. Refund requests should be sent to{' '}
          <a className={inlineLink} href="mailto:support@ailookstudio.ru">support@ailookstudio.ru</a>{' '}
          with the transaction id.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>5. Limitations and liability</h2>
        <ul className={ul}>
          <li>The Service is provided “as is”. The Operator does not guarantee that the AI processing result will fully match the User's expectations.</li>
          <li>Uploading other people's photos without their consent, content involving minors, or any other unlawful material is forbidden.</li>
          <li>The Operator may suspend an account for breach of these Terms without refund.</li>
          <li>The Operator is not liable for indirect damages or lost profits.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>6. Intellectual property</h2>
        <p>
          The User retains the rights to the original photos they upload.
          Generated images are licensed to the User on a non-exclusive basis
          for personal and commercial use (social media, resumes, avatars,
          and so on).
        </p>
      </section>

      <section>
        <h2 className={sectionH}>7. Contacts</h2>
        <p>
          Questions about Terms and payments:{' '}
          <a className={inlineLink} href="mailto:support@ailookstudio.ru">support@ailookstudio.ru</a>.
        </p>
      </section>
    </>
  );
}

function ConsentsBodyEn() {
  return (
    <>
      <p>
        Before you start, the Service asks you for three mandatory consents.
        Each one can be withdrawn at any time from your profile settings.
      </p>

      <section>
        <h2 className={sectionH}>Personal data processing</h2>
        <p>
          <strong>I consent to the processing of personal data, including a photo of my face.</strong>
        </p>
        <p>
          Without this consent the Service cannot accept a file for processing.
          The original photo is not retained: after processing, it is removed
          from RAM and the Redis stash within 15 minutes of upload. Scores and
          generated images are stored for no longer than 72 hours.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>Transfer to external AI services</h2>
        <p>
          <strong>
            I agree to the transfer of photos to external AI services
            (OpenRouter, Reve and similar providers), including outside my
            country.
          </strong>
        </p>
        <p>
          This is a legally required consent for cross-border transfers
          (Chapter V GDPR). Without it, the API returns HTTP 451 and no
          generation is performed.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>Age confirmation</h2>
        <p>
          <strong>
            I am 16 years of age or older. I understand that the Service is not
            intended for users under 16.
          </strong>
        </p>
        <p>
          Required by Art. 8 GDPR and our internal policies. False
          confirmation may result in account suspension.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>Managing consents</h2>
        <p>
          All your consents are visible in your personal account. API:
          {' '}<code className="mx-1">GET /api/v1/users/me/consents</code>,{' '}
          <code className="mx-1">POST /api/v1/users/me/consents/revoke</code>.
        </p>
      </section>
    </>
  );
}

function CookieBodyEn() {
  return (
    <>
      <p>
        Look Studio uses a minimal set of cookies and similar technologies
        (localStorage, sessionStorage) needed for the Service to work and to
        analyse basic visit statistics.
      </p>

      <section>
        <h2 className={sectionH}>1. Cookies we use</h2>
        <ul className={ul}>
          <li>
            <strong>Functional.</strong> Authentication session token, theme
            preference, wizard progress. The Service does not work without
            them; consent is implied by using the website.
          </li>
          <li>
            <strong>Analytics (consent-based).</strong> Anonymous visit
            statistics. Only hashed device identifiers are used; raw IP
            addresses are never stored.
          </li>
          <li>
            <strong>Payment.</strong> Cookies of the payment provider — set
            when checkout starts and governed by their policy.
          </li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>2. Third-party services</h2>
        <p>
          We do not share user data with advertising networks. External AI
          providers (see the{' '}
          <a className={inlineLink} href="/?policy=privacy">Privacy policy</a>)
          only receive the contents of the generation request and have no
          access to website cookies.
        </p>
      </section>

      <section>
        <h2 className={sectionH}>3. Managing cookies</h2>
        <ul className={ul}>
          <li>Most browsers let you delete or block cookies via settings.</li>
          <li>Blocking functional cookies will prevent you from signing in.</li>
          <li>You can withdraw analytics consent in the{' '}
            <a className={inlineLink} href="/?policy=consents">Data processing consents</a> section.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>4. Contacts</h2>
        <p>
          Questions about cookies:{' '}
          <a className={inlineLink} href="mailto:privacy@ailookstudio.ru">privacy@ailookstudio.ru</a>.
        </p>
      </section>
    </>
  );
}

function RefundBodyEn() {
  return (
    <>
      <p>
        Refunds for credit pack purchases on Look Studio follow the rules
        described below. The full text lives in the{' '}
        <a className={inlineLink} href="/?policy=terms">Terms of use</a>.
      </p>

      <section>
        <h2 className={sectionH}>1. Window and grounds</h2>
        <ul className={ul}>
          <li>Refund requests are accepted within <strong>14 days</strong> of payment.</li>
          <li>Refunds are only possible for <strong>unused credits</strong>. The amount is proportional to the remaining balance: spent credits are not refunded.</li>
          <li>If a technical failure on our side caused the issue, credits are returned to the account automatically without a refund request.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>2. Procedure</h2>
        <ol className="list-decimal pl-6 space-y-2">
          <li>Email{' '}
            <a className={inlineLink} href="mailto:support@ailookstudio.ru">support@ailookstudio.ru</a>{' '}
            or message{' '}
            <a className={inlineLink} href="https://t.me/ailookstudio_support" target="_blank" rel="noopener noreferrer">Telegram support</a>.</li>
          <li>Provide the transaction id (available in the payment confirmation email) and the reason for the refund.</li>
          <li>We acknowledge the request and trigger a refund through the payment provider.</li>
        </ol>
      </section>

      <section>
        <h2 className={sectionH}>3. Processing time</h2>
        <ul className={ul}>
          <li>Initial response — within <strong>24 hours</strong> on business days.</li>
          <li>Decision — up to <strong>30 calendar days</strong> (typically 1-3 days).</li>
          <li>Time for the refund to reach your card depends on the issuing bank, usually 3-10 business days.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>4. When a refund is not possible</h2>
        <ul className={ul}>
          <li>All credits in the pack have already been spent.</li>
          <li>More than 14 days have passed since payment.</li>
          <li>The account has been suspended for breach of the Terms of Use.</li>
        </ul>
      </section>

      <section>
        <h2 className={sectionH}>5. Contacts</h2>
        <p>
          E-mail:{' '}
          <a className={inlineLink} href="mailto:support@ailookstudio.ru">support@ailookstudio.ru</a>{' '}
          · Telegram:{' '}
          <a className={inlineLink} href="https://t.me/ailookstudio_support" target="_blank" rel="noopener noreferrer">@ailookstudio_support</a>.
        </p>
      </section>
    </>
  );
}

// ===========================================================================
// Public dispatchers — pick the per-build language at render time.
// ===========================================================================

export function PrivacyBody() {
  return getAppLanguage() === 'ru' ? <PrivacyBodyRu /> : <PrivacyBodyEn />;
}

export function TermsBody() {
  return getAppLanguage() === 'ru' ? <TermsBodyRu /> : <TermsBodyEn />;
}

export function ConsentsBody() {
  return getAppLanguage() === 'ru' ? <ConsentsBodyRu /> : <ConsentsBodyEn />;
}

export function CookieBody() {
  return getAppLanguage() === 'ru' ? <CookieBodyRu /> : <CookieBodyEn />;
}

export function RefundBody() {
  return getAppLanguage() === 'ru' ? <RefundBodyRu /> : <RefundBodyEn />;
}

const POLICY_BODIES: Record<PolicyId, ReactNode> = {
  privacy: <PrivacyBody />,
  terms: <TermsBody />,
  consents: <ConsentsBody />,
  cookie: <CookieBody />,
  refund: <RefundBody />,
};

const POLICY_IDS: PolicyId[] = ['privacy', 'terms', 'consents', 'cookie', 'refund'];

function buildPolicy(id: PolicyId): PolicyEntry {
  return {
    id,
    title: getPolicyTitle(id),
    shortTitle: getPolicyShortTitle(id),
    lastUpdated: getPolicyLastUpdated(),
    body: POLICY_BODIES[id],
  };
}

/**
 * Backwards-compat record used by ``PrivacyPolicy`` page. Prefer
 * ``getPolicy(id)`` in components so titles stay reactive to the
 * i18n bundle. Each access rebuilds the entry so titles stay in sync
 * with the active language.
 */
export const POLICIES: Record<PolicyId, PolicyEntry> = new Proxy(
  {} as Record<PolicyId, PolicyEntry>,
  {
    get(_target, prop: string): PolicyEntry | undefined {
      if (POLICY_IDS.includes(prop as PolicyId)) {
        return buildPolicy(prop as PolicyId);
      }
      return undefined;
    },
    has(_target, prop: string): boolean {
      return POLICY_IDS.includes(prop as PolicyId);
    },
    ownKeys() {
      return POLICY_IDS;
    },
    getOwnPropertyDescriptor(_target, prop: string) {
      if (POLICY_IDS.includes(prop as PolicyId)) {
        return { enumerable: true, configurable: true };
      }
      return undefined;
    },
  },
);

export function getPolicy(id: string | null | undefined): PolicyEntry | null {
  if (!id) return null;
  if (!POLICY_IDS.includes(id as PolicyId)) return null;
  return buildPolicy(id as PolicyId);
}
