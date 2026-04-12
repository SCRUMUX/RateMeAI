import { AicaIcon } from '@ai-ds/core/icons';

export default function Footer() {
  return (
    <footer className="glass-footer">
      <div className="max-w-[1200px] mx-auto flex flex-col items-center gap-[var(--space-16)] tablet:gap-[var(--space-24)] py-[var(--space-24)] tablet:py-[var(--space-36)] px-[var(--space-16)]">
        {/* Top row: links */}
        <div className="flex flex-col tablet:flex-row items-center gap-[var(--space-12)] tablet:gap-[var(--space-24)]">
          <a href="/privacy" className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors">
            Конфиденциальность
          </a>
          <a href="/terms" className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors">
            Условия
          </a>
          <a href="/api/v1/docs" target="_blank" rel="noopener noreferrer" className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)] hover:text-[#E6EEF8] transition-colors">
            API Docs
          </a>
        </div>

        {/* Bottom row: credits */}
        <div className="flex flex-col tablet:flex-row items-center gap-[var(--space-8)] tablet:gap-[var(--space-24)]">
          <span className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)]">
            Сделано
          </span>
          <a href="https://ux4ai.pro" target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-[var(--space-4)] text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[#E6EEF8] hover:text-[var(--color-brand-primary)] transition-colors"
          >
            <AicaIcon size={16} className="-rotate-45" />
            UX4AI
          </a>
          <span className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)]">
            © 2026 AI Look Studio
          </span>
        </div>
      </div>
    </footer>
  );
}
