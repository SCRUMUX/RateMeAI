/** @type {import('tailwindcss').Config} */
/*
 * TAILWIND CONFIGURATION - TOKEN-DRIVEN
 * =====================================
 * 
 * This configuration is designed to be fully derived from design tokens.
 * All values reference CSS custom properties to maintain single source of truth.
 * 
 * IMPORTANT: Do not add hardcoded values here.
 * All styling values must come from tokens.
 * 
 * Token Categories Mapped:
 * - colors: From Color.contract.json (semantic + primitives)
 * - fontFamily: From Typography.contract.json
 * - fontSize: From Typography.contract.json with lineHeight
 * - fontWeight: From Typography.contract.json
 * - spacing: From Space.contract.json (layout, content, control, inset)
 * - borderRadius: From Radius.contract.json
 * - boxShadow: From Effect.contract.json (elevation, focus)
 * - screens: From Layout.contract.json (breakpoints)
 */

module.exports = {
  content: {
    relative: true,
    files: [
      '../../packages/core/src/**/*.{js,ts,jsx,tsx}',
      '../../packages/core/components/**/*.{js,ts,jsx,tsx}',
      '../../packages/core/contracts/components/*.contract.json',
      './pages/**/*.{js,ts,jsx,tsx}',
      './.storybook/**/*.{js,ts,jsx,tsx}',
    ],
  },
  
  // Enable dark mode via data attribute (controlled by tokens)
  darkMode: ['class', '[data-theme="dark"]'],
  
  theme: {
    // =======================================================================
    // SCREEN BREAKPOINTS (from Layout.contract.json)
    // =======================================================================
    screens: {
      'mobile': '320px',
      'tablet': '768px',
      'desktop': '1440px',
    },
    
    extend: {
      // =====================================================================
      // COLORS (from Color.contract.json)
      // Reference CSS variables to support theming
      // =====================================================================
      colors: {
        // Background / Surface
        'bg-base': 'var(--color-bg-base)',
        'bg-muted': 'var(--color-bg-muted)',
        'surface-1': 'var(--color-surface-1)',
        'surface-2': 'var(--color-surface-2)',
        'surface-3': 'var(--color-surface-3)',
        'bg-disabled': 'var(--color-bg-disabled)',
        'surface-hover': 'var(--color-surface-hover)',
        'surface-active': 'var(--color-surface-active)',
        
        // Text
        'text-primary': 'var(--color-text-primary)',
        'text-muted': 'var(--color-text-muted)',
        'text-disabled': 'var(--color-text-disabled)',
        'text-on-brand': 'var(--color-text-on-brand)',
        
        // Brand
        'brand-primary': 'var(--color-brand-primary)',
        'brand-hover': 'var(--color-brand-hover)',
        'brand-pressed': 'var(--color-brand-pressed)',
        'brand-muted': 'var(--color-brand-muted)',
        'brand-hover-bg': 'var(--color-brand-hover-bg)',
        
        // Link
        'link-default': 'var(--color-link-default)',
        'link-hover': 'var(--color-link-hover)',
        
        // Focus
        'focus-outline': 'var(--color-focus-outline)',
        'active': 'var(--color-active)',
        
        // Border / Divider
        'border-base': 'var(--color-border-base)',
        'border-strong': 'var(--color-border-strong)',
        'divider': 'var(--color-divider)',
        
        // Semantic States
        'success-base': 'var(--color-success-base)',
        'success-surface': 'var(--color-success-surface)',
        'success-text': 'var(--color-success-text)',
        'success-hover-bg': 'var(--color-success-hover-bg)',
        
        'warning-base': 'var(--color-warning-base)',
        'warning-surface': 'var(--color-warning-surface)',
        'warning-text': 'var(--color-warning-text)',
        'warning-hover-bg': 'var(--color-warning-hover-bg)',
        
        'danger-base': 'var(--color-danger-base)',
        'danger-surface': 'var(--color-danger-surface)',
        'danger-text': 'var(--color-danger-text)',
        'danger-hover-bg': 'var(--color-danger-hover-bg)',
        
        'info-base': 'var(--color-info-base)',
        'info-surface': 'var(--color-info-surface)',
        'info-text': 'var(--color-info-text)',
        'info-hover-bg': 'var(--color-info-hover-bg)',
        
        // Data Visualization
        'viz-1': 'var(--color-viz-categorical-1)',
        'viz-2': 'var(--color-viz-categorical-2)',
        'viz-3': 'var(--color-viz-categorical-3)',
        'viz-4': 'var(--color-viz-categorical-4)',
        'viz-5': 'var(--color-viz-categorical-5)',
        'viz-6': 'var(--color-viz-categorical-6)',
        'viz-7': 'var(--color-viz-categorical-7)',
        'viz-8': 'var(--color-viz-categorical-8)',
      },
      
      // =====================================================================
      // TYPOGRAPHY (from Typography.contract.json)
      // =====================================================================
      fontFamily: {
        'base': ['var(--font-family-base)', 'Inter', 'sans-serif'],
        'mono': ['var(--font-family-mono)', 'Roboto Mono', 'monospace'],
      },
      
      fontSize: {
        // Primitive sizes with line heights
        '8': ['var(--font-size-8)', { lineHeight: 'var(--line-height-12)' }],
        '10': ['var(--font-size-10)', { lineHeight: 'var(--line-height-12)' }],
        '12': ['var(--font-size-12)', { lineHeight: 'var(--line-height-16)' }],
        '14': ['var(--font-size-14)', { lineHeight: 'var(--line-height-20)' }],
        '16': ['var(--font-size-16)', { lineHeight: 'var(--line-height-24)' }],
        '18': ['var(--font-size-18)', { lineHeight: 'var(--line-height-24)' }],
        '20': ['var(--font-size-20)', { lineHeight: 'var(--line-height-28)' }],
        '24': ['var(--font-size-24)', { lineHeight: 'var(--line-height-32)' }],
        '32': ['var(--font-size-32)', { lineHeight: 'var(--line-height-40)' }],
        
        // Semantic text styles
        'display': ['var(--font-size-32)', { lineHeight: 'var(--line-height-40)', fontWeight: 'var(--font-weight-semibold)' }],
        'h1': ['var(--font-size-24)', { lineHeight: 'var(--line-height-32)', fontWeight: 'var(--font-weight-semibold)' }],
        'h2': ['var(--font-size-20)', { lineHeight: 'var(--line-height-28)', fontWeight: 'var(--font-weight-semibold)' }],
        'h3': ['var(--font-size-18)', { lineHeight: 'var(--line-height-24)', fontWeight: 'var(--font-weight-semibold)' }],
        'h4': ['var(--font-size-16)', { lineHeight: 'var(--line-height-24)', fontWeight: 'var(--font-weight-semibold)' }],
        'body-base': ['var(--font-size-14)', { lineHeight: 'var(--line-height-20)' }],
        'body-sm': ['var(--font-size-12)', { lineHeight: 'var(--line-height-16)' }],
        'body-xs': ['var(--font-size-10)', { lineHeight: 'var(--line-height-12)' }],
        'caption-base': ['var(--font-size-12)', { lineHeight: 'var(--line-height-16)' }],
        'caption-xs': ['var(--font-size-10)', { lineHeight: 'var(--line-height-12)' }],
      },
      
      fontWeight: {
        'regular': 'var(--font-weight-regular)',
        'medium': 'var(--font-weight-medium)',
        'semibold': 'var(--font-weight-semibold)',
      },
      
      // =====================================================================
      // SPACING (from Space.contract.json)
      // =====================================================================
      spacing: {
        // Primitive spacing
        '1': 'var(--space-1)',
        '2': 'var(--space-2)',
        '3': 'var(--space-3)',
        '4': 'var(--space-4)',
        '6': 'var(--space-6)',
        '8': 'var(--space-8)',
        '9': 'var(--space-9)',
        '12': 'var(--space-12)',
        '16': 'var(--space-16)',
        '24': 'var(--space-24)',
        '32': 'var(--space-32)',
        
        // Semantic: Layout spacing (for margins between sections)
        'layout-xs': 'var(--space-layout-xs)',
        'layout-s': 'var(--space-layout-s)',
        'layout-m': 'var(--space-layout-m)',
        'layout-l': 'var(--space-layout-l)',
        'layout-xl': 'var(--space-layout-xl)',
        
        // Semantic: Content spacing (for gaps within content)
        'content-xs': 'var(--space-content-xs)',
        'content-s': 'var(--space-content-s)',
        'content-m': 'var(--space-content-m)',
        'content-l': 'var(--space-content-l)',
        
        // Semantic: Control spacing (for buttons, inputs)
        'control-xs': 'var(--space-control-xs)',
        'control-s': 'var(--space-control-s)',
        'control-m': 'var(--space-control-m)',
        'control-l': 'var(--space-control-l)',
        
        // Semantic: Inset spacing (for padding)
        'inset-xs': 'var(--space-inset-xs)',
        'inset-s': 'var(--space-inset-s)',
        'inset-m': 'var(--space-inset-m)',
        'inset-l': 'var(--space-inset-l)',
        'inset-xl': 'var(--space-inset-xl)',
        
        // Grid offsets
        'grid-offset-mobile': 'var(--grid-mobile-offset)',
        'grid-offset-tablet': 'var(--grid-tablet-offset)',
        'grid-offset-desktop': 'var(--grid-desktop-offset)',
      },
      
      // =====================================================================
      // BORDER RADIUS (from Radius.contract.json)
      // =====================================================================
      borderRadius: {
        'none': 'var(--radius-none)',
        'subtle': 'var(--radius-subtle)',
        'default': 'var(--radius-default)',
        'medium': 'var(--radius-medium)',
        'large': 'var(--radius-large)',
        'xl': 'var(--radius-xl)',
        '2xl': 'var(--radius-2xl)',
        '3xl': 'var(--radius-3xl)',
        'section': 'var(--radius-section)',
        'pill': 'var(--radius-pill)',
      },
      
      // =====================================================================
      // BORDER WIDTH (from tokens.borderWidth)
      // =====================================================================
      borderWidth: {
        'base': 'var(--border-width-base)',
        'thick': 'var(--border-width-thick)',
      },
      
      // =====================================================================
      // ASPECT RATIO (from tokens.ratio)
      // =====================================================================
      aspectRatio: {
        'square': 'var(--ratio-square)',
        '4/3': 'calc(1 / var(--ratio-4-3))',
        '16/9': 'calc(1 / var(--ratio-16-9))',
        '3/2': 'calc(1 / var(--ratio-3-2))',
      },
      
      // =====================================================================
      // BOX SHADOWS (from Effect.contract.json)
      // =====================================================================
      boxShadow: {
        // Elevation
        'elevation-1': 'var(--effect-elevation-1)',
        'elevation-2': 'var(--effect-elevation-2)',
        'elevation-3': 'var(--effect-elevation-3)',
        'elevation-glow': 'var(--effect-elevation-glow)',
        
        // Focus rings
        'focus-brand': 'var(--effect-focus-brand)',
        'focus-danger': 'var(--effect-focus-danger)',
      },
      
      // =====================================================================
      // Z-INDEX SCALE (from tokens.css)
      // =====================================================================
      zIndex: {
        'header':  'var(--z-header)',
        'popover': 'var(--z-popover)',
        'modal':   'var(--z-modal)',
        'tooltip': 'var(--z-tooltip)',
        'toast':   'var(--z-toast)',
      },
      
      // =====================================================================
      // BACKDROP BLUR (from Effect.contract.json)
      // =====================================================================
      backdropBlur: {
        'background': 'var(--effect-blur-background)',
      },
      
      // =====================================================================
      // OPACITY (for scrim effects)
      // =====================================================================
      opacity: {
        'scrim-light': '0.3',
        'scrim-strong': '0.45',
      },
      
      // =====================================================================
      // GRID CONFIGURATION (from Layout.contract.json)
      // =====================================================================
      gridTemplateColumns: {
        // Mobile: 4 columns
        'mobile': 'repeat(4, 1fr)',
        // Tablet: 8 columns
        'tablet': 'repeat(8, 1fr)',
        // Desktop: 12 columns
        'desktop': 'repeat(12, 1fr)',
      },
      
      gap: {
        'grid-mobile': 'var(--grid-mobile-gutter)',
        'grid-tablet': 'var(--grid-tablet-gutter)',
        'grid-desktop': 'var(--grid-desktop-gutter)',
      },

      keyframes: {
        shimmer: {
          '0%':   { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(200%)' },
        },
        'fade-in': {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-down': {
          '0%':   { transform: 'translateY(-8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)',    opacity: '1' },
        },
        'slide-up': {
          '0%':   { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)',   opacity: '1' },
        },
        'scale-in': {
          '0%':   { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)',    opacity: '1' },
        },
        'check-pop': {
          '0%':   { transform: 'scale(0)' },
          '60%':  { transform: 'scale(1.2)' },
          '100%': { transform: 'scale(1)' },
        },
        'accordion-open': {
          '0%':   { height: '0',    opacity: '0' },
          '100%': { height: 'var(--radix-accordion-content-height, auto)', opacity: '1' },
        },
        'accordion-close': {
          '0%':   { height: 'var(--radix-accordion-content-height, auto)', opacity: '1' },
          '100%': { height: '0', opacity: '0' },
        },
      },
      animation: {
        shimmer:          'shimmer 1.5s ease-in-out infinite',
        'fade-in':        'fade-in 150ms ease-out',
        'slide-down':     'slide-down 150ms ease-out',
        'slide-up':       'slide-up 150ms ease-out',
        'scale-in':       'scale-in 200ms ease-out',
        'dropdown-in':    'slide-down 150ms ease-out',
        'tooltip-in':     'fade-in 100ms ease-out',
        'modal-in':       'scale-in 200ms ease-out',
        'alert-in':       'slide-down 200ms ease-out',
        'check-pop':      'check-pop 200ms ease-out',
        'accordion-open': 'accordion-open 200ms ease-out',
        'accordion-close':'accordion-close 200ms ease-out',
      },
    },
  },
  
  plugins: [
    // Custom plugin to add token-based utilities
    function({ addUtilities, addComponents }) {
      // Text styles as component classes
      addComponents({
        '.text-style-display': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-32)',
          lineHeight: 'var(--line-height-40)',
          fontWeight: 'var(--font-weight-semibold)',
        },
        '.text-style-h1': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-24)',
          lineHeight: 'var(--line-height-32)',
          fontWeight: 'var(--font-weight-semibold)',
        },
        '.text-style-h2': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-20)',
          lineHeight: 'var(--line-height-28)',
          fontWeight: 'var(--font-weight-semibold)',
        },
        '.text-style-h3': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-18)',
          lineHeight: 'var(--line-height-24)',
          fontWeight: 'var(--font-weight-semibold)',
        },
        '.text-style-h4': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-16)',
          lineHeight: 'var(--line-height-24)',
          fontWeight: 'var(--font-weight-semibold)',
        },
        '.text-style-body-lg': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-16)',
          lineHeight: 'var(--line-height-24)',
          fontWeight: 'var(--font-weight-regular)',
        },
        '.text-style-body': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-14)',
          lineHeight: 'var(--line-height-20)',
          fontWeight: 'var(--font-weight-regular)',
        },
        '.text-style-body-strong': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-14)',
          lineHeight: 'var(--line-height-20)',
          fontWeight: 'var(--font-weight-semibold)',
        },
        '.text-style-body-sm': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-12)',
          lineHeight: 'var(--line-height-16)',
          fontWeight: 'var(--font-weight-regular)',
        },
        '.text-style-body-xs': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-10)',
          lineHeight: 'var(--line-height-12)',
          fontWeight: 'var(--font-weight-regular)',
        },
        '.text-style-caption': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-12)',
          lineHeight: 'var(--line-height-16)',
          fontWeight: 'var(--font-weight-medium)',
        },
        '.text-style-caption-xs': {
          fontFamily: 'var(--font-family-base)',
          fontSize: 'var(--font-size-10)',
          lineHeight: 'var(--line-height-12)',
          fontWeight: 'var(--font-weight-medium)',
        },
        '.text-style-mono': {
          fontFamily: 'var(--font-family-mono)',
          fontSize: 'var(--font-size-14)',
          lineHeight: 'var(--line-height-20)',
          fontWeight: 'var(--font-weight-regular)',
        },
      });
      
      // Themed system scrollbar
      addUtilities({
        '.scroll-area': {
          'overflow-y': 'auto',
          'scrollbar-width': 'thin',
          'scrollbar-color': 'var(--color-border-strong) transparent',
          '&::-webkit-scrollbar': { width: '6px', height: '6px' },
          '&::-webkit-scrollbar-track': { background: 'transparent' },
          '&::-webkit-scrollbar-thumb': {
            background: 'var(--color-border-strong)',
            borderRadius: '9999px',
          },
          '&::-webkit-scrollbar-thumb:hover': {
            background: 'var(--color-text-muted)',
          },
        },
      });

      // Responsive grid container — auto-switches columns/gutter/offset at breakpoints
      addUtilities({
        '.grid-container': {
          display: 'grid',
          width: '100%',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 'var(--grid-mobile-gutter)',
          paddingLeft: 'var(--grid-mobile-offset)',
          paddingRight: 'var(--grid-mobile-offset)',
          '@media (min-width: 768px)': {
            gridTemplateColumns: 'repeat(8, 1fr)',
            gap: 'var(--grid-tablet-gutter)',
            paddingLeft: 'var(--grid-tablet-offset)',
            paddingRight: 'var(--grid-tablet-offset)',
          },
          '@media (min-width: 1440px)': {
            gridTemplateColumns: 'repeat(12, 1fr)',
            gap: 'var(--grid-desktop-gutter)',
            paddingLeft: 'var(--grid-desktop-offset)',
            paddingRight: 'var(--grid-desktop-offset)',
          },
        },
        '.grid-container-mobile': {
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 'var(--grid-mobile-gutter)',
          paddingLeft: 'var(--grid-mobile-offset)',
          paddingRight: 'var(--grid-mobile-offset)',
        },
        '.grid-container-tablet': {
          display: 'grid',
          gridTemplateColumns: 'repeat(8, 1fr)',
          gap: 'var(--grid-tablet-gutter)',
          paddingLeft: 'var(--grid-tablet-offset)',
          paddingRight: 'var(--grid-tablet-offset)',
        },
        '.grid-container-desktop': {
          display: 'grid',
          gridTemplateColumns: 'repeat(12, 1fr)',
          gap: 'var(--grid-desktop-gutter)',
          paddingLeft: 'var(--grid-desktop-offset)',
          paddingRight: 'var(--grid-desktop-offset)',
        },
      });
    },
  ],
};
