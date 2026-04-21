// Sanitiser deliberately removed: during generation pipeline recovery we
// want the raw worker `error_message` visible to the user (and ops) so
// patterns like `[stage=generate_image] ReveAPIError: ... http=400
// code=INVALID_PARAMETER_VALUE req=rsid-...` surface directly in the UI.
// Mirrors `src/bot/handlers/mode_select.py::_user_message_for_failed` —
// keep the two in sync.

const GENERIC_FAILED_MESSAGE =
  'Не удалось обработать фото. Попробуйте ещё раз.';

export function userMessageForFailed(errorMessage: string | null | undefined): string {
  if (!errorMessage) return GENERIC_FAILED_MESSAGE;
  const text = errorMessage.trim();
  if (!text) return GENERIC_FAILED_MESSAGE;
  if (text.length > 500) return text.slice(0, 497).trimEnd() + '...';
  return text;
}
