import { API_BASE } from './api';

/**
 * Ensures an image URL is absolute — prepends API_BASE for relative paths.
 * Handles cases where the backend returns relative URLs or paths without a scheme.
 */
export function normalizeImageUrl(url: string | undefined | null): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (url.startsWith('/')) return `${API_BASE}${url}`;
  return `${API_BASE}/${url}`;
}
