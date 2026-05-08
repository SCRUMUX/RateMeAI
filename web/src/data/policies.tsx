import { type ReactNode } from 'react';
import i18next from 'i18next';

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
// privacy@ailookstudio.com for an English version.
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
// ---------------------------------------------------------------------------
export function PrivacyBody() {
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
export function TermsBody() {
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
export function ConsentsBody() {
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
export function CookieBody() {
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
export function RefundBody() {
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
