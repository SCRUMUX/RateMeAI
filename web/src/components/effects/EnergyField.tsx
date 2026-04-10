import { useSpring, useScroll, useTransform, motion, useReducedMotion } from 'framer-motion';
import { useMousePosition } from '../../hooks/useMousePosition';

type BlobType = 'accent' | 'secondary' | 'neutral';

const BLOBS: { size: number; type: BlobType; opacity: number; x: string; y: string; factor: number; scrollFactor: number }[] = [
  { size: 550, type: 'accent',    opacity: 0.07, x: '10%',  y: '5vh',   factor: 0.02,  scrollFactor: -0.08 },
  { size: 450, type: 'secondary', opacity: 0.05, x: '75%',  y: '15vh',  factor: 0.035, scrollFactor: 0.06 },
  { size: 380, type: 'neutral',   opacity: 0.04, x: '50%',  y: '45vh',  factor: 0.04,  scrollFactor: -0.12 },
  { size: 500, type: 'accent',    opacity: 0.05, x: '80%',  y: '80vh',  factor: 0.025, scrollFactor: 0.10 },
  { size: 420, type: 'secondary', opacity: 0.06, x: '15%',  y: '120vh', factor: 0.03,  scrollFactor: -0.07 },
  { size: 480, type: 'accent',    opacity: 0.04, x: '60%',  y: '160vh', factor: 0.045, scrollFactor: 0.09 },
  { size: 400, type: 'secondary', opacity: 0.05, x: '25%',  y: '200vh', factor: 0.02,  scrollFactor: -0.11 },
  { size: 520, type: 'accent',    opacity: 0.04, x: '70%',  y: '250vh', factor: 0.035, scrollFactor: 0.08 },
  { size: 360, type: 'secondary', opacity: 0.04, x: '40%',  y: '300vh', factor: 0.04,  scrollFactor: -0.06 },
  { size: 440, type: 'neutral',   opacity: 0.05, x: '85%',  y: '340vh', factor: 0.03,  scrollFactor: 0.10 },
];

function blobColor(type: BlobType, opacity: number): string {
  switch (type) {
    case 'accent':    return `rgba(var(--accent-r), var(--accent-g), var(--accent-b), ${opacity})`;
    case 'secondary': return `rgba(var(--accent-sec-r), var(--accent-sec-g), var(--accent-sec-b), ${opacity})`;
    case 'neutral':   return `rgba(60, 20, 180, ${opacity})`;
  }
}

export default function EnergyField() {
  const mouse = useMousePosition();
  const prefersReduced = useReducedMotion();
  const { scrollY } = useScroll();

  const mx = (mouse.x - 0.5) * 2;
  const my = (mouse.y - 0.5) * 2;

  if (prefersReduced) {
    return null;
  }

  return (
    <div className="energy-field" aria-hidden="true">
      {BLOBS.map((blob, i) => (
        <EnergyBlob key={i} mx={mx} my={my} scrollY={scrollY} color={blobColor(blob.type, blob.opacity)} size={blob.size} x={blob.x} y={blob.y} factor={blob.factor} scrollFactor={blob.scrollFactor} />
      ))}
    </div>
  );
}

interface EnergyBlobProps {
  size: number;
  color: string;
  x: string;
  y: string;
  factor: number;
  scrollFactor: number;
  mx: number;
  my: number;
  scrollY: ReturnType<typeof useScroll>['scrollY'];
}

function EnergyBlob({ size, color, x, y, factor, scrollFactor, mx, my, scrollY }: EnergyBlobProps) {
  const mouseOffsetX = mx * factor * 100;
  const mouseOffsetY = my * factor * 100;

  const springX = useSpring(mouseOffsetX, { stiffness: 40, damping: 30 });
  const springY = useSpring(mouseOffsetY, { stiffness: 40, damping: 30 });

  springX.set(mouseOffsetX);
  springY.set(mouseOffsetY);

  const scrollOffset = useTransform(scrollY, (v) => v * scrollFactor);

  return (
    <motion.div
      style={{
        position: 'absolute',
        width: size,
        height: size,
        left: x,
        top: y,
        borderRadius: '50%',
        background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
        filter: 'blur(var(--blur-bg))',
        willChange: 'transform',
        x: springX,
        y: scrollOffset,
        translateX: '-50%',
      }}
    />
  );
}
