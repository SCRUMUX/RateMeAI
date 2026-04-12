import { AicaIcon, TelegramIcon, WhatsappIcon, LineIcon, OkIcon, VkIcon, ZaloIcon, ChevronRightIcon } from '@ai-ds/core/icons';
import type { FC } from 'react';

interface PlatformDef {
  name: string;
  sub: string;
  border: string;
  opacity: number;
  iconColor: string;
  Icon: FC<{ size?: number | string; className?: string; style?: React.CSSProperties }>;
  href?: string;
}

const PLATFORMS: PlatformDef[] = [
  { name: 'WEB APP', sub: 'Прямо здесь', border: 'var(--color-brand-primary)', opacity: 1, iconColor: 'var(--color-brand-primary)', Icon: ({ size, className }) => <AicaIcon size={size} className={`${className ?? ''} -rotate-45`} />, href: '#app' },
  { name: 'Telegram', sub: 'Уже запущен', border: '#229ED9', opacity: 1, iconColor: '#229ED9', Icon: TelegramIcon, href: 'https://t.me/RateMeAIBot' },
  { name: 'Одноклассники', sub: 'Мини-приложение', border: '#EE8208', opacity: 1, iconColor: '#EE8208', Icon: OkIcon, href: 'https://ok.ru/app/ratemeai' },
  { name: 'Вконтакте', sub: 'Мини-приложение', border: '#0077FF', opacity: 1, iconColor: '#0077FF', Icon: VkIcon, href: 'https://vk.com/app_ratemeai' },
  { name: 'WhatsApp', sub: 'Скоро', border: '#25D366', opacity: 0.5, iconColor: '#25D366', Icon: WhatsappIcon },
  { name: 'Zalo', sub: 'Скоро', border: '#0068FF', opacity: 0.5, iconColor: '#0068FF', Icon: ZaloIcon },
  { name: 'Line', sub: 'Скоро', border: '#06C755', opacity: 0.5, iconColor: '#06C755', Icon: LineIcon },
];

export default function Hero() {
  return (
    <section className="relative z-[2] flex flex-col items-center justify-center gap-[var(--space-40)] tablet:gap-[var(--space-96)] px-[var(--space-16)] tablet:px-[var(--space-24)] pt-[80px] tablet:pt-[120px] pb-[60px] tablet:pb-[120px]"
      style={{ minHeight: '100vh' }}
    >
      {/* Text block */}
      <div className="relative z-[2] flex flex-col items-center gap-[var(--space-12)] text-center">
        <h1 className="text-[32px] tablet:text-[48px] desktop:text-[64px] font-bold leading-[1] text-[#E6EEF8]">
          Адаптируй фото
        </h1>
        <h1 className="text-[32px] tablet:text-[48px] desktop:text-[64px] font-bold leading-[1]"
          style={{
            background: 'linear-gradient(103deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          под любой контекст.
        </h1>
        <p className="text-[16px] tablet:text-[20px] leading-[24px] tablet:leading-[28px] text-[var(--color-text-secondary)] mt-1">
          Одна загрузка — множество вариантов
        </p>
        <p className="text-[15px] tablet:text-[18px] leading-[22px] tablet:leading-[28px] text-[var(--color-text-secondary)] max-w-[660px]">
          Выбери категорию, выбери стиль — система адаптирует твоё фото и покажет скор восприятия.
          Улучшай результат с каждой генерацией. Работает в браузере и в мессенджерах.
        </p>
      </div>

      {/* Platform links */}
      <div className="relative z-[2] flex flex-col items-center gap-[var(--space-12)]">
        <p className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)]">
          Выбери удобный способ:
        </p>
        <div className="flex flex-wrap items-center justify-center gap-[var(--space-8)] tablet:gap-[var(--space-12)]">
          {PLATFORMS.map((p) => {
            const cls = "gradient-border-item glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-12)] tablet:px-[var(--space-16)] py-[var(--space-6)] tablet:py-[var(--space-8)] min-h-[36px] rounded-[var(--radius-12)] cursor-pointer no-underline";
            const style = { opacity: p.opacity, '--gb-color': p.border } as React.CSSProperties;
            const inner = (
              <>
                <div className="flex items-center gap-[6px]">
                  <p.Icon size={20} style={{ color: p.iconColor }} />
                  <div className="flex flex-col gap-[2px]">
                    <span className="text-[11px] tablet:text-[12px] leading-[14px] tablet:leading-[16px] text-[#E6EEF8]">{p.name}</span>
                    <span className="text-[10px] tablet:text-[11px] leading-[12px] tablet:leading-[14px]"
                      style={{ color: p.sub === 'Скоро' ? 'var(--color-text-muted)' : 'var(--color-brand-primary)' }}
                    >
                      {p.sub}
                    </span>
                  </div>
                </div>
                <ChevronRightIcon size={20} className="text-[var(--color-text-muted)] ml-1" />
              </>
            );
            return p.href ? (
              <a key={p.name} href={p.href} className={cls} style={style}
                {...(p.href.startsWith('http') ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
              >
                {inner}
              </a>
            ) : (
              <div key={p.name} className={cls} style={style}>
                {inner}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
