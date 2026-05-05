import { useEffect, type RefObject } from 'react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  'audio[controls]',
  'video[controls]',
  '[contenteditable]:not([contenteditable="false"])',
].join(',');

function getFocusable(container: HTMLElement): HTMLElement[] {
  const nodes = container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
  return Array.from(nodes).filter((el) => {
    if (el.hasAttribute('disabled')) return false;
    if (el.getAttribute('aria-hidden') === 'true') return false;
    // Skip elements that are actually invisible (display:none, hidden, etc.).
    const rect = el.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0 || el === document.activeElement;
  });
}

/**
 * Trap keyboard focus inside the given container while `active` is true,
 * and restore focus to the previously focused element on close.
 *
 * Why a custom hook instead of focus-trap-react: we already wrap our modals
 * with framer-motion + portal, and the bundle budget for landing pages is
 * tight. ~50 lines of plain DOM is enough for our two modals.
 */
export default function useFocusTrap(
  active: boolean,
  containerRef: RefObject<HTMLElement | null>,
): void {
  useEffect(() => {
    if (!active) return;
    const initial = containerRef.current;
    if (!initial) return;
    // Narrow once and capture so closures (handleKeyDown, rAF) don't have to
    // re-check the ref every iteration. TS doesn't preserve narrowing across
    // closure boundaries, so we lock it via an explicit `HTMLElement` const.
    const trap: HTMLElement = initial;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    // Defer initial focus by one frame so the dialog's enter animation has
    // started (otherwise the focus ring jumps before the modal is on screen).
    const initialFocusFrame = requestAnimationFrame(() => {
      const focusables = getFocusable(trap);
      const target = focusables[0] ?? trap;
      if (target === trap && trap.tabIndex < 0) {
        trap.tabIndex = -1;
      }
      target.focus({ preventScroll: true });
    });

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Tab') return;
      const focusables = getFocusable(trap);
      if (focusables.length === 0) {
        event.preventDefault();
        trap.focus({ preventScroll: true });
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const activeEl = document.activeElement as HTMLElement | null;

      if (event.shiftKey) {
        if (activeEl === first || !activeEl || !trap.contains(activeEl)) {
          event.preventDefault();
          last.focus({ preventScroll: true });
        }
      } else if (activeEl === last) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    }

    document.addEventListener('keydown', handleKeyDown, true);

    return () => {
      cancelAnimationFrame(initialFocusFrame);
      document.removeEventListener('keydown', handleKeyDown, true);
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus({ preventScroll: true });
      }
    };
  }, [active, containerRef]);
}
