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
  'Лицо крупно, по центру (≥ 15%)',
  'Анфас, без сильных поворотов',
  'Чёткое фото, без размытия',
  'Лицо открыто, без масок',
  'Один человек, хорошее освещение',
];

export const REJECT_BULLETS: string[] = [
  'Без лица или лицо слишком мелкое',
  'Размытые и шумные снимки',
  'Несколько людей в кадре',
  'Разрешение меньше 400×400',
  'Файл больше 10 МБ',
];

// Short bullets for compact blocks (e.g. on landings next to CTA).
export const REQUIREMENTS_SHORT: string[] = [
  'Лицо крупно и по центру (≥15%)',
  'Чёткий анфас, без масок',
  'Один человек, ≥400×400 пикселей',
];
