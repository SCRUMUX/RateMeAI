import { useEffect } from 'react';

/**
 * useReveal — global "scroll into view, fade up" controller.
 *
 * v1.50.3: добавили мягкие появления секций на лендингах.
 * Идея максимально лёгкая, чтобы не таскать framer-motion ради
 * пары fade-in:
 *
 *  • CSS-классы `.reveal` / `.reveal-stagger` (см. index.css) дают
 *    стартовое состояние (opacity:0 + translateY(16px) + scale(0.985)).
 *  • Когда нода пересекает viewport, IntersectionObserver выставляет
 *    атрибут `data-revealed="true"` — CSS transition догоняет до
 *    финального состояния.
 *  • `MutationObserver` ловит React-рендеры (Simulation/Testimonials/
 *    Pricing появляются позже Hero) и подписывает новые `.reveal`
 *    ноды на тот же IO. Это не "горячая дорога" — мутации редкие.
 *  • На `prefers-reduced-motion` — сразу выставляем атрибут всем,
 *    без анимаций и без IO.
 *
 * Хук вызывается **один раз** из корня приложения (App.tsx). Внутри
 * — true singleton, повторные вызовы no-op, а unmount тоже no-op
 * (приложение SPA, контроллер живёт пока живёт страница).
 */

let installed = false;

function shouldReduceMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function markRevealed(node: Element) {
  if (!(node instanceof HTMLElement)) return;
  node.setAttribute('data-revealed', 'true');
}

function installController() {
  if (installed || typeof document === 'undefined') return;
  installed = true;

  const reduce = shouldReduceMotion();

  if (reduce) {
    // Reduced motion → no animation at all, mark everything immediately
    // and on every future mutation as well.
    const stamp = () => {
      document
        .querySelectorAll('.reveal:not([data-revealed]), .reveal-stagger:not([data-revealed])')
        .forEach(markRevealed);
    };
    stamp();
    const mo = new MutationObserver(stamp);
    mo.observe(document.body, { childList: true, subtree: true });
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          markRevealed(entry.target);
          io.unobserve(entry.target);
        }
      }
    },
    {
      // Fire when ~15% of the element peeks into viewport. The block
      // below the fold typically has 100% by the time user scrolls
      // half a step, so this gives a natural "as I get there" pace.
      threshold: 0.15,
      // Slightly inflate the trigger zone so animations start a touch
      // before the element is technically in view — avoids that "wait,
      // why is the section blank?" microsecond on a slow scroll.
      rootMargin: '0px 0px -40px 0px',
    },
  );

  const subscribe = () => {
    document
      .querySelectorAll('.reveal:not([data-revealed]), .reveal-stagger:not([data-revealed])')
      .forEach((node) => {
        // If the node is already visible at install time (e.g. hero
        // or anything above the fold), reveal immediately without
        // waiting for IO.
        const rect = node.getBoundingClientRect();
        const inView =
          rect.top < (window.innerHeight || document.documentElement.clientHeight) &&
          rect.bottom > 0;
        if (inView) {
          markRevealed(node);
          return;
        }
        io.observe(node);
      });
  };

  subscribe();

  const mo = new MutationObserver(() => subscribe());
  mo.observe(document.body, { childList: true, subtree: true });
}

export function useReveal(): void {
  useEffect(() => {
    installController();
  }, []);
}
