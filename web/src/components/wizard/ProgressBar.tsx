export default function ProgressBar({ value, max = 10, accent = false, variant, delta = 0 }: { value: number; max?: number; accent?: boolean; variant?: 'default' | 'accent' | 'success'; delta?: number }) {
  const resolvedVariant = variant ?? (accent ? 'accent' : 'default');
  const cls =
    resolvedVariant === 'success' ? 'glass-progress-fill-success'
    : resolvedVariant === 'accent' ? 'glass-progress-fill'
    : 'glass-progress-fill-muted';

  const basePct = (value / max) * 100;
  const deltaPct = delta > 0 ? (Math.min(delta, max - value) / max) * 100 : 0;

  return (
    <div className="w-full h-1.5 rounded-full glass-progress-track overflow-hidden flex">
      <div
        className={`h-full shrink-0 transition-all ${cls}`}
        style={{ width: `${basePct}%` }}
      />
      {deltaPct > 0 && (
        <div
          className="h-full shrink-0 transition-all glass-progress-fill-success"
          style={{ width: `${deltaPct}%` }}
        />
      )}
    </div>
  );
}
