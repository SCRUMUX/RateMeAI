import { Link } from 'react-router-dom';

/**
 * Privacy policy page — user-facing text rendered from
 * docs/PRIVACY_POLICY.md (kept in sync manually for now).
 *
 * Route: /privacy (added to App.tsx).
 * Legal frameworks: 152-ФЗ (RU), GDPR (EU), CCPA/CPRA (US).
 *
 * Content is intentionally rendered inline (not via a markdown fetch) to
 * avoid extra runtime dependencies and to keep the page static and
 * scrape-friendly for regulators.
 */
export default function PrivacyPolicy() {
  const lastUpdated = '2026-04-20';

  return (
    <div className="min-h-screen w-full bg-[#0B0F1A] text-[#E6EEF8]">
      <div className="max-w-[860px] mx-auto px-6 py-12">
        <div className="mb-8">
          <Link
            to="/"
            className="text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            ← На главную
          </Link>
        </div>

        <h1 className="text-[32px] font-bold mb-2">Политика конфиденциальности</h1>
        <p className="text-[13px] text-[var(--color-text-muted)] mb-10">
          Версия 1.0 · Последнее обновление: {lastUpdated}
        </p>

        <article className="prose prose-invert max-w-none space-y-6 text-[15px] leading-[1.7]">
          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">1. Общие положения</h2>
            <p>
              Настоящая Политика определяет порядок обработки персональных данных
              пользователей сервиса <strong>AI Look Studio</strong> (далее — «Сервис»),
              принадлежащего оператору <strong>[НАИМЕНОВАНИЕ ОПЕРАТОРА]</strong>
              {' '}(далее — «Оператор»), адрес: [АДРЕС ОПЕРАТОРА], ИНН [ИНН],
              e-mail: <a className="text-[#60A5FA] underline" href="mailto:privacy@ailookstudio.ru">privacy@ailookstudio.ru</a>.
            </p>
            <p>
              Политика составлена в соответствии с требованиями Федерального закона
              от 27.07.2006 № 152-ФЗ «О персональных данных» (РФ), Регламента
              Европейского парламента и Совета (ЕС) 2016/679 (GDPR) и California
              Consumer Privacy Act (CCPA/CPRA, США).
            </p>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">2. Какие данные мы обрабатываем</h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>Фотографии</strong>, которые вы загружаете в Сервис для AI-обработки
                (включая изображения с лицом).
              </li>
              <li>
                <strong>Метаданные Telegram-аккаунта</strong> (tg_user_id, username) —
                только при входе через Telegram-бот.
              </li>
              <li>
                <strong>E-mail или номер телефона</strong> — только если вы используете их
                для входа на сайт.
              </li>
              <li>
                <strong>Технические данные</strong>: хэш IP-адреса, хэш User-Agent,
                идентификатор сессии. Сырые IP/User-Agent не хранятся.
              </li>
              <li>
                <strong>Платёжные данные</strong> — обрабатываются платёжным провайдером
                (YooKassa), Оператор получает только факт оплаты и сумму.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">3. О биометрических данных</h2>
            <p>
              <strong>Важно.</strong> Оператор <u>не осуществляет обработку биометрических
              персональных данных</u> в смысле ст. 11 152-ФЗ и ст. 9 GDPR, поскольку:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                Оператор <strong>не извлекает и не хранит</strong> биометрические
                признаки (feature-векторы, ArcFace/FaceNet-эмбеддинги, геометрию лица).
              </li>
              <li>
                Оператор <strong>не использует изображение для установления
                личности</strong> пользователя (identification) и не сопоставляет его
                с государственными или частными базами лиц.
              </li>
              <li>
                Проверка «сохранения внешности» между оригиналом и сгенерированным
                изображением производится <strong>Vision Language Model</strong> как
                визуальное сравнение двух кадров без извлечения биометрических
                векторов; результат сравнения (число 0–10) не сохраняется в привязке
                к пользователю.
              </li>
              <li>
                Загруженное изображение <strong>удаляется из оперативной памяти
                и Redis-стежа не позднее чем через 15 минут</strong> после загрузки
                и никогда не попадает в долговременное хранилище.
              </li>
            </ul>
            <p>
              Если будущие изменения функциональности потребуют фактической
              биометрической идентификации, Оператор обязуется отдельно получить
              письменное согласие пользователя (ч. 1 ст. 11 152-ФЗ) и уведомить
              Роскомнадзор.
            </p>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">4. Цели обработки</h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>Генерация AI-обработанных изображений по вашему запросу.</li>
              <li>Предоставление доступа к личному кабинету и сохранённым результатам.</li>
              <li>Биллинг и учёт потреблённых кредитов.</li>
              <li>Техническая поддержка, предотвращение злоупотреблений.</li>
              <li>
                Передача изображений внешним AI-провайдерам (OpenRouter, Reve, Replicate)
                для выполнения генерации — <strong>только при вашем явном согласии</strong>.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">5. Правовые основания</h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>Согласие субъекта</strong> (п. 1 ч. 1 ст. 6 152-ФЗ, п. a ч. 1
                ст. 6 GDPR) — для основной обработки изображений.
              </li>
              <li>
                <strong>Отдельное согласие</strong> — для трансграничной передачи
                изображений внешним AI-сервисам (ст. 12 152-ФЗ, гл. V GDPR).
              </li>
              <li>
                <strong>Исполнение договора</strong> (п. b ч. 1 ст. 6 GDPR) — для
                биллинга.
              </li>
              <li>
                <strong>Законный интерес</strong> — для предотвращения злоупотреблений
                (hash-based rate limiting без сырых IP).
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">6. Возрастное ограничение</h2>
            <p>
              Сервис предназначен для лиц старше <strong>16 лет</strong>. При регистрации
              вы подтверждаете, что достигли 16-летнего возраста. Если вы младше 16 лет,
              вы не можете использовать Сервис. Это соответствует требованиям ст. 8
              GDPR и California Consumer Privacy Act (для лиц до 13 лет также
              применяется COPPA в юрисдикции США).
            </p>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">7. Сроки хранения</h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>Оригиналы загруженных фото</strong> — не более 15 минут в
                Redis-стеже, далее физически удаляются. В S3 / файловое хранилище
                оригиналы <strong>не записываются</strong>.
              </li>
              <li>
                <strong>Сгенерированные изображения</strong> — 72 часа, далее физически
                удаляются фоновым процессом <code>privacy_gc_cron</code>.
              </li>
              <li>
                <strong>Учётная запись и согласия</strong> — до момента запроса на
                удаление или в течение 1 года неактивности.
              </li>
              <li>
                <strong>Платёжные операции</strong> — 3 года (требование налогового
                законодательства РФ).
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">8. Трансграничная передача</h2>
            <p>
              При установленном согласии изображения передаются в следующие сервисы:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>OpenRouter</strong> (США) — анализ изображения моделью VLM.
              </li>
              <li>
                <strong>Reve</strong> (США) — генерация изображений.
              </li>
              <li>
                <strong>Replicate</strong> (США) — генерация изображений.
              </li>
            </ul>
            <p>
              Без согласия на трансграничную передачу API возвращает HTTP 451 и
              Сервис не выполняет внешний запрос. Вы можете отозвать согласие в
              личном кабинете; последующие операции с внешними AI не выполняются.
            </p>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">9. Ваши права</h2>
            <p>В соответствии с законодательством вы имеете право:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>Получать информацию</strong> о составе и целях обработки (ст. 14
                152-ФЗ, ст. 15 GDPR, CCPA §1798.110).
              </li>
              <li>
                <strong>Требовать удаления</strong> всех ваших данных —
                <code className="mx-1">DELETE /api/v1/users/me</code> (ст. 14 152-ФЗ,
                ст. 17 GDPR, CCPA §1798.105).
              </li>
              <li>
                <strong>Экспортировать данные</strong> в машиночитаемом виде —
                <code className="mx-1">GET /api/v1/users/me/export</code> (ст. 20 GDPR).
              </li>
              <li>
                <strong>Отозвать согласие</strong> на обработку или трансграничную
                передачу в личном кабинете.
              </li>
              <li>
                <strong>Не соглашаться на продажу данных</strong> (Oператор не продаёт
                персональные данные третьим лицам — CCPA «Do Not Sell»).
              </li>
              <li>
                <strong>Обжаловать</strong> действия Оператора в Роскомнадзор (РФ),
                Supervisory Authority вашей страны (ЕС) или California Attorney
                General (США).
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">10. AI-прозрачность</h2>
            <p>
              Все сгенерированные изображения маркируются:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>Визуальным бейджем</strong> «Сгенерировано AI» на предпросмотре
                и share-карточке.
              </li>
              <li>
                <strong>EXIF-метаданными</strong> <code>UserComment=AI-generated by AI
                Look Studio</code> в JPEG-файле.
              </li>
            </ul>
            <p>
              Эти меры соответствуют требованиям EU AI Act (Art. 50) по прозрачности
              AI-контента.
            </p>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">11. Безопасность</h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>Весь трафик — HTTPS (TLS 1.2+).</li>
              <li>Хранилища защищены приватными сетевыми сегментами Railway.</li>
              <li>Логи фильтруются PII-фильтром: image-байты и base64 не попадают в логи.</li>
              <li>IP/User-Agent хэшируются перед сохранением.</li>
              <li>
                Процесс автоматического удаления (<code>privacy_gc_cron</code>) физически
                удаляет истёкшие генерации каждые N минут.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">12. Контакты</h2>
            <p>
              Вопросы, запросы на удаление, отзыв согласия:{' '}
              <a className="text-[#60A5FA] underline" href="mailto:privacy@ailookstudio.ru">
                privacy@ailookstudio.ru
              </a>
            </p>
            <p>
              Оператор обязуется рассмотреть обращение в течение <strong>30 дней</strong>
              {' '}с момента получения.
            </p>
          </section>

          <section>
            <h2 className="text-[22px] font-semibold mt-6 mb-3">13. Изменения</h2>
            <p>
              Оператор вправе обновить Политику. Актуальная версия всегда доступна
              по адресу{' '}
              <a className="text-[#60A5FA] underline" href="https://ailookstudio.ru/privacy">
                https://ailookstudio.ru/privacy
              </a>
              . При существенных изменениях мы повторно запрашиваем согласие.
            </p>
          </section>
        </article>

        <div className="mt-16 pt-8 border-t border-white/10 text-center">
          <Link
            to="/"
            className="text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            ← На главную
          </Link>
        </div>
      </div>
    </div>
  );
}
