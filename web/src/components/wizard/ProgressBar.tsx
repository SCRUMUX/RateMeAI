export default function ProgressBar({ value, max = 10, accent = false }: { value: number; max?: number; accent?: boolean }) {
  return (
    <div className="w-full h-1.5 rounded-full glass-progress-track overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${accent ? 'glass-progress-fill' : 'glass-progress-fill-muted'}`}
        style={{ width: `${(value / max) * 100}%` }}
      />
    </div>
  );
}
