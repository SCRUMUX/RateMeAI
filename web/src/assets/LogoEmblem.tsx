/**
 * LogoEmblem (1.39.0) — векторный logo на замену 582 kB PNG.
 *
 * Геометрический monogram «AI Look Studio» (двойное кольцо +
 * стилизованные «AI») использует ``currentColor`` для текстовой
 * monogram'ы и ``var(--color-brand-primary)`` для accent-rings.
 * Автоматически адаптируется к:
 *  - тёмная/светлая тема (через ``color: var(--color-text-primary)``
 *    родителя),
 *  - активная категория (cyan/purple/pink/orange — через
 *    ``--color-brand-primary``).
 *
 * Никаких ``mixBlendMode``, никаких theme-фильтров — рендерится
 * чисто на любой подложке.
 */

import { type SVGProps } from 'react';

interface Props extends SVGProps<SVGSVGElement> {
  withGlow?: boolean;
}

export default function LogoEmblem({ withGlow = true, ...rest }: Props) {
  return (
    <svg
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="AI Look Studio"
      role="img"
      {...rest}
    >
      {withGlow ? (
        <defs>
          <filter id="aiLookStudioGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="1.6" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
      ) : null}

      <g filter={withGlow ? 'url(#aiLookStudioGlow)' : undefined}>
        {/* outer ring — soft accent */}
        <circle
          cx="32"
          cy="32"
          r="29"
          fill="none"
          stroke="var(--color-brand-primary)"
          strokeWidth="1.2"
          opacity="0.28"
        />
        {/* inner ring — brand emphasis */}
        <circle
          cx="32"
          cy="32"
          r="24"
          fill="none"
          stroke="var(--color-brand-primary)"
          strokeWidth="1.6"
        />

        {/* «A» — triangle apex */}
        <path
          d="M19.5 41.5 L25 22.5 L30.5 41.5"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        {/* «A» horizontal bar */}
        <line
          x1="21.6"
          y1="34.8"
          x2="28.4"
          y2="34.8"
          stroke="currentColor"
          strokeWidth="2.0"
          strokeLinecap="round"
        />

        {/* «I» vertical stem */}
        <line
          x1="38.5"
          y1="22.5"
          x2="38.5"
          y2="41.5"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
        {/* «I» top serif */}
        <line
          x1="35.6"
          y1="22.5"
          x2="41.4"
          y2="22.5"
          stroke="currentColor"
          strokeWidth="2.0"
          strokeLinecap="round"
        />
        {/* «I» bottom serif */}
        <line
          x1="35.6"
          y1="41.5"
          x2="41.4"
          y2="41.5"
          stroke="currentColor"
          strokeWidth="2.0"
          strokeLinecap="round"
        />

        {/* corner accents — micro cyan dots, придают «tech» текстуру */}
        <circle cx="32" cy="3.5" r="1.2" fill="var(--color-brand-primary)" opacity="0.6" />
        <circle cx="32" cy="60.5" r="1.2" fill="var(--color-brand-primary)" opacity="0.6" />
        <circle cx="3.5" cy="32" r="1.2" fill="var(--color-brand-primary)" opacity="0.6" />
        <circle cx="60.5" cy="32" r="1.2" fill="var(--color-brand-primary)" opacity="0.6" />
      </g>
    </svg>
  );
}
