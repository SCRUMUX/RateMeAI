import { useEffect, useRef, useState } from 'react';

interface MousePosition {
  x: number;
  y: number;
}

const CENTER: MousePosition = { x: 0.5, y: 0.5 };

/**
 * Tracks normalized mouse position (0..1) relative to viewport.
 * Uses rAF throttling to avoid layout thrashing.
 * Returns static center when prefers-reduced-motion is set.
 */
export function useMousePosition(): MousePosition {
  const [pos, setPos] = useState<MousePosition>(CENTER);
  const rafRef = useRef<number | null>(null);
  const latestRef = useRef<MousePosition>(CENTER);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) return;

    const onMove = (e: MouseEvent) => {
      latestRef.current = {
        x: e.clientX / window.innerWidth,
        y: e.clientY / window.innerHeight,
      };

      if (rafRef.current == null) {
        rafRef.current = requestAnimationFrame(() => {
          setPos(latestRef.current);
          rafRef.current = null;
        });
      }
    };

    window.addEventListener('mousemove', onMove, { passive: true });
    return () => {
      window.removeEventListener('mousemove', onMove);
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return pos;
}
