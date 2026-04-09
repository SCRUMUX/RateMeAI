import { API_BASE } from './api';

const STORAGE_PATH_RE = /\/storage\/.+/;

/**
 * Ensures an image URL is absolute and points to the correct API origin.
 * Handles localhost URLs stored in DB, relative paths, and whitespace.
 */
export function normalizeImageUrl(url: string | undefined | null): string {
  if (!url) return '';
  const trimmed = url.trim();

  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    const match = trimmed.match(STORAGE_PATH_RE);
    if (match) return `${API_BASE}${match[0]}`;
    return trimmed;
  }

  if (trimmed.startsWith('/')) return `${API_BASE}${trimmed}`;
  return `${API_BASE}/${trimmed}`;
}
