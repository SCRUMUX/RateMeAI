/**
 * PlaceholderArt (1.39.0) — минималистичные SVG-иллюстрации
 * на замену двух 800-900 kB PNG.
 *
 * Используются в empty-state «до» (PlaceholderUpload) и
 * «после» (PlaceholderUpgrade): wizard StepGenerate / StepAnalysis,
 * ReviewModal, секция Simulation на лендинге.
 *
 * Контракт:
 *  - ``stroke="currentColor"`` для контуров: цвет наследуется из
 *    ``color: var(--color-text-secondary)`` родителя, что
 *    автоматически адаптирует светлую/тёмную тему.
 *  - ``var(--color-brand-primary)`` для accent-элементов
 *    (sparkles, рамка-glow): подхватывает category-aware accent
 *    (cyan/purple/pink/orange).
 *  - ``preserveAspectRatio="xMidYMid slice"`` имитирует
 *    ``object-fit: cover`` оригинальных PNG.
 *  - Никаких хардкод-цветов и тем-фильтров — рендерится одинаково
 *    качественно на любой подложке.
 */

import { type SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * «До» — empty-state для исходной (ещё не загруженной) фото.
 * Стилизованная фоторамка + лёгкий dashed-frame, силуэт «портрета».
 */
export function PlaceholderUpload({ className, ...rest }: Props) {
  return (
    <svg
      viewBox="0 0 320 320"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label="Placeholder: photo to upload"
      className={className}
      {...rest}
    >
      {/* subtle background tint — едва заметная подложка */}
      <rect
        x="0"
        y="0"
        width="320"
        height="320"
        fill="var(--color-brand-primary)"
        opacity="0.04"
      />

      {/* dashed outer frame — «drop zone» */}
      <rect
        x="40"
        y="40"
        width="240"
        height="240"
        rx="20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeDasharray="6 8"
        opacity="0.35"
      />

      {/* solid inner frame */}
      <rect
        x="60"
        y="60"
        width="200"
        height="200"
        rx="16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        opacity="0.5"
      />

      {/* portrait silhouette — circle (head) + arc (shoulders) */}
      <circle
        cx="160"
        cy="148"
        r="32"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.0"
        opacity="0.7"
      />
      <path
        d="M104 240 C 104 200, 130 184, 160 184 C 190 184, 216 200, 216 240"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.0"
        strokeLinecap="round"
        opacity="0.7"
      />

      {/* corner accent dots — micro brand-tint */}
      <circle cx="60" cy="60" r="2.5" fill="var(--color-brand-primary)" opacity="0.7" />
      <circle cx="260" cy="60" r="2.5" fill="var(--color-brand-primary)" opacity="0.7" />
      <circle cx="60" cy="260" r="2.5" fill="var(--color-brand-primary)" opacity="0.7" />
      <circle cx="260" cy="260" r="2.5" fill="var(--color-brand-primary)" opacity="0.7" />
    </svg>
  );
}

/**
 * «После» — empty-state для улучшенного результата.
 * Та же фоторамка + sparkles/glow вокруг силуэта.
 */
export function PlaceholderUpgrade({ className, ...rest }: Props) {
  return (
    <svg
      viewBox="0 0 320 320"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label="Placeholder: enhanced photo"
      className={className}
      {...rest}
    >
      <defs>
        <radialGradient id="placeholderUpgradeGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--color-brand-primary)" stopOpacity="0.18" />
          <stop offset="65%" stopColor="var(--color-brand-primary)" stopOpacity="0.06" />
          <stop offset="100%" stopColor="var(--color-brand-primary)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* radial brand-glow background */}
      <rect x="0" y="0" width="320" height="320" fill="url(#placeholderUpgradeGlow)" />

      {/* subtle base tint */}
      <rect
        x="0"
        y="0"
        width="320"
        height="320"
        fill="var(--color-brand-primary)"
        opacity="0.02"
      />

      {/* solid frame */}
      <rect
        x="60"
        y="60"
        width="200"
        height="200"
        rx="16"
        fill="none"
        stroke="var(--color-brand-primary)"
        strokeWidth="1.6"
        opacity="0.55"
      />

      {/* portrait silhouette — head + shoulders, более акцентная */}
      <circle
        cx="160"
        cy="148"
        r="32"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        opacity="0.85"
      />
      <path
        d="M104 240 C 104 200, 130 184, 160 184 C 190 184, 216 200, 216 240"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        opacity="0.85"
      />

      {/* sparkles — 4-pointed stars, brand-color */}
      <g fill="var(--color-brand-primary)" opacity="0.85">
        <path d="M88 90 L92 100 L102 104 L92 108 L88 118 L84 108 L74 104 L84 100 Z" />
        <path d="M232 86 L235 94 L243 97 L235 100 L232 108 L229 100 L221 97 L229 94 Z" transform="scale(0.85) translate(40 12)" />
        <path d="M250 220 L254 232 L266 236 L254 240 L250 252 L246 240 L234 236 L246 232 Z" transform="scale(0.7) translate(110 70)" />
      </g>

      {/* tiny accent dots — same as upload, для визуальной симметрии */}
      <circle cx="60" cy="60" r="2.5" fill="var(--color-brand-primary)" />
      <circle cx="260" cy="60" r="2.5" fill="var(--color-brand-primary)" />
      <circle cx="60" cy="260" r="2.5" fill="var(--color-brand-primary)" />
      <circle cx="260" cy="260" r="2.5" fill="var(--color-brand-primary)" />
    </svg>
  );
}
