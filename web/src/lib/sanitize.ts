// Strip HTML tags, markdown code fences, stray JSON fragments, control
// characters and collapse whitespace — mirrors src/utils/text_sanitize.py.
// We never render LLM output as HTML; this guarantees the user sees plain
// prose even if the model leaks <span style=...>, ```code```, or JSON.

const HTML_TAG_RE = /<[^<>]{0,2000}>/g;
const CODE_FENCE_RE = /```[a-zA-Z0-9_-]*\n?|```/gm;
const INLINE_CODE_RE = /`([^`\n]{1,200})`/g;
const JSON_KEY_RE = /"\s*[a-zA-Z_][a-zA-Z0-9_]*\s*"\s*:\s*/gm;
// eslint-disable-next-line no-control-regex
const ANSI_RE = /\x1b\[[0-9;]*[A-Za-z]/g;
// eslint-disable-next-line no-control-regex
const CTRL_RE = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;
const WS_RE = /[ \t]{2,}/g;
const MULTI_NEWLINE_RE = /\n{3,}/g;

function decodeEntities(text: string): string {
  return text
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&hellip;/gi, '…');
}

/**
 * Humanize an error coming from the API layer for display to end users.
 * Never leak raw JSON / HTML / stack traces into the UI — if the backend
 * body does not look like a short human sentence, fall back to ``fallback``.
 *
 * Recognises three shapes in priority order:
 *   1. ``err.detail`` is an object with a ``message`` field — the canonical
 *      shape used by FastAPI handlers like ``/api/v1/pre-analyze`` (e.g.
 *      ``{message, suggestion, code, blocking_issues}``). We render
 *      ``"<message>. <suggestion>"`` so the user sees both halves.
 *   2. ``err.detail`` is a plain string — surfaced as-is (legacy 400s).
 *   3. ``err.body`` / ``err`` is a stringified blob — sanitized and
 *      returned only if it looks like a short human sentence.
 */
export function humanizeApiError(err: unknown, fallback: string): string {
  if (!err) return fallback;

  const detail =
    typeof err === 'object' && err !== null && 'detail' in (err as Record<string, unknown>)
      ? (err as { detail?: unknown }).detail
      : undefined;

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const obj = detail as Record<string, unknown>;
    const message = typeof obj.message === 'string' ? obj.message : '';
    const suggestion = typeof obj.suggestion === 'string' ? obj.suggestion : '';
    if (message || suggestion) {
      const merged = [message, suggestion].filter(Boolean).join('. ').replace(/\.\s*\.+$/g, '.');
      const cleanedStruct = sanitizeLLMText(merged, 300);
      if (cleanedStruct && cleanedStruct.length <= 240) return cleanedStruct;
    }
  }

  if (typeof detail === 'string' && detail.trim()) {
    const cleanedStr = sanitizeLLMText(detail, 300);
    if (cleanedStr && cleanedStr.length <= 240 && !/^[\[{<]/.test(cleanedStr)) {
      return cleanedStr;
    }
  }

  const raw =
    typeof err === 'object' && err !== null && 'body' in (err as Record<string, unknown>)
      ? (err as { body?: unknown }).body
      : err;
  const cleaned = sanitizeLLMText(raw, 300);
  if (!cleaned) return fallback;
  if (cleaned.length > 240) return fallback;
  if (/^[\[{<]/.test(cleaned)) return fallback;
  if (/traceback|exception|stack|\bat [A-Za-z]/i.test(cleaned)) return fallback;
  return cleaned;
}

export function sanitizeLLMText(value: unknown, maxLen = 2000): string {
  if (value == null) return '';
  const raw = typeof value === 'string' ? value : String(value);
  if (!raw) return '';

  let text = raw
    .replace(ANSI_RE, '')
    .replace(CTRL_RE, '')
    .replace(CODE_FENCE_RE, '')
    .replace(INLINE_CODE_RE, (_m, inner: string) => inner)
    .replace(HTML_TAG_RE, '');

  text = decodeEntities(text);

  text = text
    .replace(JSON_KEY_RE, '')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, ' ')
    .replace(/\\"/g, '"');

  text = text
    .replace(WS_RE, ' ')
    .replace(MULTI_NEWLINE_RE, '\n\n')
    .trim()
    .replace(/^["']+|["']+$/g, '')
    .trim();

  if (text.length > maxLen) {
    text = text.slice(0, maxLen - 1).trimEnd() + '…';
  }
  return text;
}
