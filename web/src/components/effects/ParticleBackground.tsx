/**
 * Ambient ParticleBackground (1.35.0).
 *
 * Subtle "digital air" layer — 250 small particles drifting on a curl-noise
 * flow field. Sits between MeshGradientBg (z:0) and EnergyField (z:2) on
 * landings only. Never on AppPage (regression risk: scroll-to-nowhere via
 * absolutely-positioned siblings inside the wizard scroll container — see
 * 1.32.0 changelog).
 *
 * Visual contract:
 *  - 1-2 px particles, opacity 0.04 - 0.15, theme-aware color via
 *    --particle-color / --particle-opacity-* tokens.
 *  - Idle motion: simplex-noise vector field, ~0.3 px/frame baseline.
 *  - Scroll input: deltaY → velocityBoost up to 1.2, plus light downward
 *    bias proportional to scroll direction. Exponential decay back to 1.0
 *    over ~1.5s after scroll stops.
 *  - No connections, no flashes, no per-particle alpha oscillation
 *    (explicitly forbidden by spec — these break the "ambient" feeling).
 *  - prefers-reduced-motion: reduce → render nothing.
 *  - mobile (innerWidth < 768) → cap density at 100.
 *  - FPS guard: rolling 60-frame avg, halve density if avg < 45.
 *
 * Implementation note: Canvas 2D, no external deps. Inline simplex-noise
 * (~3 kB minified). WebGL/three.js would add 50+ kB gzip and is overkill
 * for 250 particles at 60 FPS.
 */
import { useEffect, useRef } from 'react';

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  opacity: number;
}

// --- Inline 2D simplex noise (Stefan Gustavson, public domain).
// Compact form, no external dep. Output range [-1, 1].
const GRAD3 = [
  [1, 1], [-1, 1], [1, -1], [-1, -1],
  [1, 0], [-1, 0], [1, 0], [-1, 0],
  [0, 1], [0, -1], [0, 1], [0, -1],
];

function buildPerm(): Uint8Array {
  const p = new Uint8Array(512);
  const seed = new Uint8Array(256);
  for (let i = 0; i < 256; i++) seed[i] = i;
  for (let i = 255; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [seed[i], seed[j]] = [seed[j], seed[i]];
  }
  for (let i = 0; i < 512; i++) p[i] = seed[i & 255];
  return p;
}

function makeNoise2D() {
  const perm = buildPerm();
  const F2 = 0.5 * (Math.sqrt(3) - 1);
  const G2 = (3 - Math.sqrt(3)) / 6;
  return function noise2D(xin: number, yin: number): number {
    const s = (xin + yin) * F2;
    const i = Math.floor(xin + s);
    const j = Math.floor(yin + s);
    const t = (i + j) * G2;
    const x0 = xin - (i - t);
    const y0 = yin - (j - t);
    let i1: number, j1: number;
    if (x0 > y0) { i1 = 1; j1 = 0; } else { i1 = 0; j1 = 1; }
    const x1 = x0 - i1 + G2;
    const y1 = y0 - j1 + G2;
    const x2 = x0 - 1 + 2 * G2;
    const y2 = y0 - 1 + 2 * G2;
    const ii = i & 255;
    const jj = j & 255;
    const gi0 = perm[ii + perm[jj]] % 12;
    const gi1 = perm[ii + i1 + perm[jj + j1]] % 12;
    const gi2 = perm[ii + 1 + perm[jj + 1]] % 12;
    let n0 = 0, n1 = 0, n2 = 0;
    let t0 = 0.5 - x0 * x0 - y0 * y0;
    if (t0 >= 0) { t0 *= t0; n0 = t0 * t0 * (GRAD3[gi0][0] * x0 + GRAD3[gi0][1] * y0); }
    let t1 = 0.5 - x1 * x1 - y1 * y1;
    if (t1 >= 0) { t1 *= t1; n1 = t1 * t1 * (GRAD3[gi1][0] * x1 + GRAD3[gi1][1] * y1); }
    let t2 = 0.5 - x2 * x2 - y2 * y2;
    if (t2 >= 0) { t2 *= t2; n2 = t2 * t2 * (GRAD3[gi2][0] * x2 + GRAD3[gi2][1] * y2); }
    return 70 * (n0 + n1 + n2);
  };
}

function readThemeColor(): { r: number; g: number; b: number; opMin: number; opMax: number } {
  if (typeof document === 'undefined') {
    return { r: 255, g: 255, b: 255, opMin: 0.05, opMax: 0.15 };
  }
  const root = getComputedStyle(document.documentElement);
  const colorRaw = root.getPropertyValue('--particle-color').trim() || '255, 255, 255';
  const [r, g, b] = colorRaw.split(',').map((s) => Number(s.trim()) || 255);
  const opMin = Number(root.getPropertyValue('--particle-opacity-min').trim()) || 0.05;
  const opMax = Number(root.getPropertyValue('--particle-opacity-max').trim()) || 0.15;
  return { r, g, b, opMin, opMax };
}

function prefersReducedMotion(): boolean {
  if (typeof matchMedia === 'undefined') return false;
  return matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export default function ParticleBackground() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    const noise = makeNoise2D();

    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let width = window.innerWidth;
    let height = window.innerHeight;

    function resize() {
      if (!canvas) return;
      width = window.innerWidth;
      height = window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();

    let theme = readThemeColor();
    const themeObserver = new MutationObserver(() => {
      theme = readThemeColor();
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });

    function isMobile() {
      return window.innerWidth < 768;
    }

    let targetCount = isMobile() ? 100 : 250;
    let particles: Particle[] = [];

    function makeParticle(): Particle {
      const opSpan = theme.opMax - theme.opMin;
      const size = Math.random() < 0.05 ? 3 : 1 + Math.random();
      return {
        x: Math.random() * width,
        y: Math.random() * height,
        vx: 0,
        vy: 0,
        size,
        opacity: theme.opMin + Math.random() * opSpan,
      };
    }

    function rebuildParticles(count: number) {
      particles = Array.from({ length: count }, makeParticle);
    }
    rebuildParticles(targetCount);

    let scrollBoost = 1;
    let scrollDirection = 0;
    let lastScrollY = window.scrollY;
    let lastScrollTime = performance.now();

    function onScroll() {
      const now = performance.now();
      const dy = window.scrollY - lastScrollY;
      const dt = Math.max(now - lastScrollTime, 16);
      // Pixels per ms — clamp for safety against momentum scroll spikes.
      const speed = Math.min(Math.abs(dy) / dt, 5);
      scrollBoost = Math.min(1.2, 1 + speed * 0.04);
      scrollDirection = Math.sign(dy);
      lastScrollY = window.scrollY;
      lastScrollTime = now;
    }
    window.addEventListener('scroll', onScroll, { passive: true });

    let lastResizeTime = 0;
    function onResize() {
      const now = performance.now();
      if (now - lastResizeTime < 200) return;
      lastResizeTime = now;
      resize();
      const next = isMobile() ? 100 : Math.min(targetCount, 250);
      if (particles.length !== next) {
        targetCount = next;
        rebuildParticles(next);
      }
    }
    window.addEventListener('resize', onResize);

    const fpsWindow: number[] = [];
    let lastFrameTime = performance.now();
    let degradeChecked = false;

    let raf = 0;
    let t0 = performance.now();
    const NOISE_SCALE = 0.0015;
    const TIME_SCALE = 0.00015;
    const BASE_SPEED = 0.3;
    const TAU = Math.PI * 2;

    function frame(now: number) {
      const dt = now - lastFrameTime;
      lastFrameTime = now;
      const fps = dt > 0 ? 1000 / dt : 60;
      fpsWindow.push(fps);
      if (fpsWindow.length > 60) fpsWindow.shift();

      // Gradual decay of scroll boost back to 1.0 (~1.5s).
      scrollBoost += (1 - scrollBoost) * 0.04;
      scrollDirection *= 0.92;

      // Soft FPS-based density fallback: only after ~2s warmup, only once.
      if (!degradeChecked && fpsWindow.length >= 60) {
        const avg = fpsWindow.reduce((a, b) => a + b, 0) / fpsWindow.length;
        if (avg < 45 && particles.length > 50) {
          targetCount = Math.max(50, Math.floor(particles.length / 2));
          rebuildParticles(targetCount);
        }
        degradeChecked = true;
      }

      const tt = (now - t0) * TIME_SCALE;
      ctx!.clearRect(0, 0, width, height);

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        const angle = noise(p.x * NOISE_SCALE, p.y * NOISE_SCALE + tt) * TAU;
        p.vx = Math.cos(angle) * BASE_SPEED * scrollBoost;
        p.vy = Math.sin(angle) * BASE_SPEED * scrollBoost + scrollDirection * 0.25;
        p.x += p.vx;
        p.y += p.vy;
        // Wraparound — no edge spawn artifacts.
        if (p.x < -10) p.x = width + 10;
        else if (p.x > width + 10) p.x = -10;
        if (p.y < -10) p.y = height + 10;
        else if (p.y > height + 10) p.y = -10;

        ctx!.beginPath();
        ctx!.fillStyle = `rgba(${theme.r}, ${theme.g}, ${theme.b}, ${p.opacity})`;
        ctx!.arc(p.x, p.y, p.size, 0, TAU);
        ctx!.fill();
      }

      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onResize);
      themeObserver.disconnect();
    };
  }, []);

  if (prefersReducedMotion()) return null;

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="particle-background"
      style={{
        position: 'fixed',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 1,
      }}
    />
  );
}
