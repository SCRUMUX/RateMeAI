import { Link } from 'react-router-dom';
import useDocumentMeta from '../lib/useDocumentMeta';

export default function NotFound() {
  useDocumentMeta({
    title: 'Страница не найдена · Look Studio',
    description: 'Запрошенная страница не существует. Попробуйте начать с главной.',
    noindex: true,
  });

  return (
    <div className="min-h-screen w-full bg-[var(--color-bg-base)] text-[var(--color-text-primary)] flex items-center justify-center px-[var(--space-16)]">
      <div className="max-w-[560px] w-full flex flex-col items-center text-center gap-[var(--space-16)] py-[var(--space-32)]">
        <span className="text-[64px] tablet:text-[96px] leading-none font-semibold opacity-40 tabular-nums">
          404
        </span>
        <h1 className="text-[24px] tablet:text-[32px] font-semibold leading-[1.2]">
          Страница не найдена
        </h1>
        <p className="text-[14px] tablet:text-[16px] leading-[22px] text-[var(--color-text-secondary)]">
          Возможно, ссылка устарела или была введена с ошибкой. Попробуйте
          вернуться на главную или открыть один из наших сценариев.
        </p>

        <div className="flex flex-col tablet:flex-row gap-[var(--space-12)] mt-[var(--space-8)]">
          <Link
            to="/"
            className="glass-btn-primary inline-flex items-center justify-center px-[var(--space-24)] py-[var(--space-12)] rounded-[var(--radius-12)] text-[14px] tablet:text-[15px] leading-[20px] font-medium no-underline"
          >
            На главную
          </Link>
          <Link
            to="/dokumenty"
            className="glass-btn-secondary inline-flex items-center justify-center px-[var(--space-20)] py-[var(--space-12)] rounded-[var(--radius-12)] text-[14px] leading-[20px] no-underline text-[var(--color-text-primary)]"
          >
            Фото на документы
          </Link>
        </div>

        <div className="flex flex-col tablet:flex-row gap-[var(--space-12)] text-[13px] text-[var(--color-text-muted)] mt-[var(--space-8)]">
          <Link to="/znakomstva" className="hover:text-[var(--color-text-primary)] transition-colors no-underline">
            Фото для знакомств
          </Link>
          <Link to="/rezume" className="hover:text-[var(--color-text-primary)] transition-colors no-underline">
            Фото на резюме
          </Link>
          <Link to="/privacy" className="hover:text-[var(--color-text-primary)] transition-colors no-underline">
            Политика конфиденциальности
          </Link>
        </div>
      </div>
    </div>
  );
}
