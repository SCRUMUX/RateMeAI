import { useRef, useCallback, useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { REQUIREMENTS_BULLETS, REJECT_BULLETS } from '../../data/photo-requirements';
import ConsentGate from '../ConsentGate';

interface Props {
  onNext: () => void;
}

function StepUploadBody({ onNext }: Props) {
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

  const hasPhoto = !!app.photo;

  return (
    <div className="flex flex-col gap-[var(--space-24)] w-full max-w-[800px] mx-auto">
      <div className="flex flex-col items-center gap-[var(--space-8)] text-center">
        <h2 className="text-[20px] tablet:text-[28px] leading-[1.2] font-semibold text-[#E6EEF8]">
          Загрузите фото
        </h2>
        <p className="text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)] max-w-[440px]">
          Хорошее фото — половина результата. Просто следуйте чеклисту справа.
        </p>
      </div>

      <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileSelect} />

      <div className="flex flex-col tablet:flex-row gap-[var(--space-16)] tablet:gap-[var(--space-24)] items-start">
        {/* Left column — photo / dropzone + primary CTA */}
        <div className="w-full max-w-[260px] tablet:w-[260px] tablet:max-w-[260px] mx-auto tablet:mx-0 shrink-0 flex flex-col gap-[var(--space-12)]">
          {hasPhoto ? (
            <>
              <div className="gradient-border-card glass-card rounded-[var(--radius-12)] overflow-hidden w-full">
                <div className="w-full aspect-[4/5] bg-[rgba(255,255,255,0.02)] overflow-hidden">
                  <img src={app.photo!.preview} alt="Загруженное фото" className="w-full h-full object-cover" />
                </div>
              </div>
              <button
                onClick={onNext}
                className="glass-btn-primary w-full py-[var(--space-12)] text-[15px] leading-[22px] rounded-[var(--radius-12)] font-medium"
              >
                Далее
              </button>
            </>
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
              <div className="flex flex-col items-center justify-center gap-[var(--space-16)] aspect-[4/5] px-[var(--space-16)]">
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
                  <span className="text-[15px] leading-[20px] font-medium text-[#E6EEF8] text-center">
                    {dragOver ? 'Отпустите файл' : 'Нажмите или перетащите фото'}
                  </span>
                  <span className="text-[12px] leading-[16px] text-[var(--color-text-muted)] text-center">
                    JPG, PNG — до 10 МБ
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right column — requirements + secondary CTA */}
        <div className="flex-1 flex flex-col gap-[var(--space-16)] w-full">
          <div className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-16)] tablet:p-[var(--space-20)]">
            <p className="text-left text-[13px] tablet:text-[14px] font-medium text-[#E6EEF8] mb-[var(--space-10)]">
              Требования к фото
            </p>
            <ul className="flex flex-col gap-[var(--space-8)] text-left">
              {REQUIREMENTS_BULLETS.map((text) => (
                <li
                  key={text}
                  className="flex items-start gap-[var(--space-8)] text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-secondary)]"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 18 18"
                    fill="none"
                    className="shrink-0 mt-[2px]"
                    aria-hidden="true"
                  >
                    <path
                      d="M5 9.5L7.5 12L13 6"
                      stroke="rgb(var(--accent-r),var(--accent-g),var(--accent-b))"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <span>{text}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="gradient-border-card glass-card rounded-[var(--radius-12)] p-[var(--space-16)] tablet:p-[var(--space-20)]">
            <p className="text-left text-[13px] tablet:text-[14px] font-medium text-[#FF9EAD] mb-[var(--space-10)]">
              Не будет обработано
            </p>
            <ul className="flex flex-col gap-[var(--space-8)] text-left">
              {REJECT_BULLETS.map((text) => (
                <li
                  key={text}
                  className="flex items-start gap-[var(--space-8)] text-[12px] tablet:text-[13px] leading-[16px] tablet:leading-[18px] text-[var(--color-text-muted)]"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 18 18"
                    fill="none"
                    className="shrink-0 mt-[2px]"
                    aria-hidden="true"
                  >
                    <path
                      d="M6 6L12 12M12 6L6 12"
                      stroke="#FF9EAD"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </svg>
                  <span>{text}</span>
                </li>
              ))}
            </ul>
          </div>

          {hasPhoto && (
            <button
              onClick={() => fileInputRef.current?.click()}
              className="glass-btn-ghost w-full py-[var(--space-12)] text-[14px] leading-[20px] text-[#E6EEF8] rounded-[var(--radius-12)]"
            >
              Заменить фото
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function StepUpload(props: Props) {
  return (
    <ConsentGate>
      <StepUploadBody {...props} />
    </ConsentGate>
  );
}
