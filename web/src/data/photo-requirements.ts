// Single source of truth for photo requirements on the frontend.
// Keep machine codes in sync with src/services/photo_requirements.py (IssueCode).

export type IssueCode =
  | 'invalid_image'
  | 'low_resolution'
  | 'blurry_photo'
  | 'no_face'
  | 'face_too_small'
  | 'face_blurred'
  | 'multiple_faces'
  // soft warnings
  | 'face_small_warn'
  | 'face_off_center'
  | 'not_frontal'
  | 'hair_bg_similar';

export interface PhotoIssue {
  code: IssueCode;
  severity: 'block' | 'warn';
  message: string;
  suggestion: string;
}

export const REQUIREMENTS_BULLETS: string[] = [
  'Лицо крупно и по центру кадра — минимум 15% площади',
  'Анфас, без сильных поворотов головы',
  'Чёткое фото без размытия и движения',
  'Лицо не перекрыто очками-зеркалками, масками, рукой или волосами',
  'Хорошее освещение, черты лица различимы',
  'Один человек в кадре',
];

export const REJECT_BULLETS: string[] = [
  'Фото без лица или лицо слишком мелкое',
  'Размытые или шумные фото, в том числе скриншоты',
  'Несколько людей в кадре',
  'Разрешение меньше 400×400 пикселей',
  'Файл больше 10 МБ',
];

// Short bullets for compact blocks (e.g. on landings next to CTA).
export const REQUIREMENTS_SHORT: string[] = [
  'Лицо крупно и по центру (≥15%)',
  'Чёткий анфас, без масок',
  'Один человек, ≥400×400 пикселей',
];
