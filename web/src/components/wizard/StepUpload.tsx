import { useRef, useCallback, useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';

interface Props {
  onNext: () => void;
}

export default function StepUpload({ onNext }: Props) {
  const app = useApp();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const pendingAdvance = useRef(false);

  useEffect(() => {
    if (app.photo && pendingAdvance.current) {
      pendingAdvance.current = false;
      onNext();
    }
  }, [app.photo, onNext]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    pendingAdvance.current = true;
    app.uploadPhoto(f);
  }, [app]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (!f || !f.type.startsWith('image/')) return;
    pendingAdvance.current = true;
    app.uploadPhoto(f);
  }, [app]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  return (
    <div className="flex flex-col items-center gap-[var(--space-16)] w-full max-w-[600px] mx-auto">
      <div className="flex flex-col items-center gap-[var(--space-4)] text-center">
        <h2 className="text-[20px] tablet:text-[28px] leading-[1.2] font-semibold text-[#E6EEF8]">
          Загрузите фото
        </h2>
        <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)]">
          Проанализируем и предложим оптимальные улучшения
        </p>
      </div>

      <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileSelect} />

      {app.photo ? (
        <div className="flex flex-col items-center gap-[var(--space-12)] w-full">
          <div className="gradient-border-card glass-card rounded-[var(--radius-12)] overflow-hidden w-full max-w-[260px]">
            <div className="w-full aspect-[3/4] bg-[rgba(255,255,255,0.02)] overflow-hidden">
              <img src={app.photo.preview} alt="Загруженное фото" className="w-full h-full object-cover" />
            </div>
          </div>
          <div className="flex gap-[var(--space-12)]">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="glass-btn-ghost px-[var(--space-20)] py-[var(--space-8)] text-[13px] leading-[18px] text-[#E6EEF8] rounded-[var(--radius-pill)]"
            >
              Заменить фото
            </button>
            <button
              onClick={onNext}
              className="glass-btn-primary px-[var(--space-24)] py-[var(--space-8)] text-[13px] leading-[18px] rounded-[var(--radius-pill)]"
            >
              Далее
            </button>
          </div>
        </div>
      ) : (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          className={`gradient-border-card glass-card w-full rounded-[var(--radius-12)] cursor-pointer transition-all ${
            dragOver ? 'scale-[1.02]' : ''
          }`}
          style={dragOver ? { '--gb-color': 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.5)' } as React.CSSProperties : undefined}
        >
          <div className="flex flex-col items-center justify-center gap-[var(--space-16)] py-[var(--space-48)] tablet:py-[var(--space-64)] px-[var(--space-24)]">
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.12)' }}
            >
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="rgb(var(--accent-r), var(--accent-g), var(--accent-b))" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <div className="flex flex-col items-center gap-[var(--space-4)]">
              <span className="text-[16px] leading-[24px] font-medium text-[#E6EEF8]">
                {dragOver ? 'Отпустите файл' : 'Нажмите или перетащите фото'}
              </span>
              <span className="text-[13px] leading-[18px] text-[var(--color-text-muted)]">
                JPG, PNG — до 10 МБ
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
