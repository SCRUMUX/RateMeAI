export default function ProgressBar({ value, max = 10, accent = false, variant }: { value: number; max?: number; accent?: boolean; variant?: 'default' | 'accent' | 'success' }) {
  const resolvedVariant = variant ?? (accent ? 'accent' : 'default');
  const cls =
    resolvedVariant === 'success' ? 'glass-progress-fill-success'
    : resolvedVariant === 'accent' ? 'glass-progress-fill'
    : 'glass-progress-fill-muted';

  return (
    <div className="w-full h-1.5 rounded-full glass-progress-track overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${cls}`}
        style={{ width: `${(value / max) * 100}%` }}
      />
    </div>
  );
}
