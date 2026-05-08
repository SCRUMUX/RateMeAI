import { Link } from 'react-router-dom';
import { AicaIcon, TelegramIcon, WhatsappIcon, LineIcon, OkIcon, VkIcon, ZaloIcon, ChevronRightIcon } from '@ai-ds/core/icons';
import type { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { useMemo } from 'react';
import { findBlock, parseHero, type LandingPage } from '../lib/landing-cms';

interface PlatformDef {
  name: string;
  subKey: 'webApp' | 'telegram' | 'ok' | 'vk' | 'comingSoon';
  border: string;
  opacity: number;
  iconColor: string;
  Icon: FC<{ size?: number | string; className?: string; style?: React.CSSProperties }>;
  href?: string;
  internal?: boolean;
}

const PLATFORMS: PlatformDef[] = [
  { name: 'WEB APP', subKey: 'webApp', border: 'var(--color-brand-primary)', opacity: 1, iconColor: 'var(--color-brand-primary)', Icon: ({ size, className }) => <AicaIcon size={size} className={`${className ?? ''} -rotate-45`} />, href: '/app', internal: true },
  { name: 'Telegram', subKey: 'telegram', border: '#229ED9', opacity: 1, iconColor: '#229ED9', Icon: TelegramIcon, href: 'https://t.me/RateMeAI_bot' },
  { name: 'OK', subKey: 'ok', border: '#EE8208', opacity: 1, iconColor: '#EE8208', Icon: OkIcon, href: 'https://ok.ru/app/ratemeai' },
  { name: 'VK', subKey: 'vk', border: '#0077FF', opacity: 1, iconColor: '#0077FF', Icon: VkIcon, href: 'https://vk.com/app_ratemeai' },
  { name: 'WhatsApp', subKey: 'comingSoon', border: '#25D366', opacity: 0.5, iconColor: '#25D366', Icon: WhatsappIcon },
  { name: 'Zalo', subKey: 'comingSoon', border: '#0068FF', opacity: 0.5, iconColor: '#0068FF', Icon: ZaloIcon },
  { name: 'Line', subKey: 'comingSoon', border: '#06C755', opacity: 0.5, iconColor: '#06C755', Icon: LineIcon },
];

export interface HeroProps {
  cmsPage?: LandingPage | null;
}

export default function Hero({ cmsPage }: HeroProps = {}) {
  const { t } = useTranslation('landing');
  
  const content = useMemo(() => {
    const fallback = {
      icon: '',
      title: '',
      titleLine1: t('hero.titleLine1'),
      titleLine2: t('hero.titleLine2'),
      gradientPhrase: '',
      lead: t('hero.lead'),
      subLead: t('hero.subLead'),
      ctaLabel: '',
      ctaMicrocopy: '',
      platformsHint: t('hero.platformsHint'),
    };
    return parseHero(findBlock(cmsPage ?? undefined, 'hero')?.data, fallback);
  }, [cmsPage, t]);

  return (
    <section className="relative z-[2] flex flex-col items-center justify-center gap-[var(--space-40)] tablet:gap-[var(--space-96)] px-[var(--space-16)] tablet:px-[var(--space-24)] landing-hero-py"
      style={{ minHeight: '100vh' }}
    >
      {/* Text block */}
      <div className="relative z-[2] flex flex-col items-center gap-[var(--space-12)] text-center">
        <h1 className="landing-h1 text-[var(--color-text-primary)] flex flex-col gap-[var(--space-4)]">
          <span>{content.titleLine1}</span>
          <span
            style={{
              background: 'linear-gradient(103deg, rgb(var(--accent-r), var(--accent-g), var(--accent-b)) 4%, rgb(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b)) 103%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            {content.titleLine2}
          </span>
        </h1>
        <p className="landing-lead mt-1">
          {content.lead}
        </p>
        <p className="landing-lead max-w-[660px]">
          {content.subLead}
        </p>
      </div>

      {/* Platform links */}
      <div className="relative z-[2] flex flex-col items-center gap-[var(--space-12)]">
        <p className="text-[14px] tablet:text-[16px] leading-[20px] tablet:leading-[24px] text-[var(--color-text-secondary)]">
          {content.platformsHint}
        </p>
        <div className="flex flex-wrap items-center justify-center gap-[var(--space-8)] tablet:gap-[var(--space-12)]">
          {PLATFORMS.map((p) => {
            const cls = "gradient-border-item glass-btn-ghost flex items-center gap-[var(--space-4)] px-[var(--space-12)] tablet:px-[var(--space-16)] py-[var(--space-6)] tablet:py-[var(--space-8)] min-h-[36px] rounded-[var(--radius-12)] cursor-pointer no-underline";
            const style = { opacity: p.opacity, '--gb-color': p.border } as React.CSSProperties;
            const subLabel = t(`hero.platforms.${p.subKey}`);
            const inner = (
              <>
                <div className="flex items-center gap-[6px]">
                  <p.Icon size={20} style={{ color: p.iconColor }} />
                  <div className="flex flex-col gap-[2px]">
                    <span className="text-[11px] tablet:text-[12px] leading-[14px] tablet:leading-[16px] text-[var(--color-text-primary)]">{p.name}</span>
                    <span className="text-[10px] tablet:text-[11px] leading-[12px] tablet:leading-[14px]"
                      style={{ color: p.subKey === 'comingSoon' ? 'var(--color-text-muted)' : 'var(--color-brand-primary)' }}
                    >
                      {subLabel}
                    </span>
                  </div>
                </div>
                <ChevronRightIcon size={20} className="text-[var(--color-text-muted)] ml-1" />
              </>
            );
            return p.href && p.internal ? (
              <Link key={p.name} to={p.href} className={cls + ' no-underline'} style={style}>
                {inner}
              </Link>
            ) : p.href ? (
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
