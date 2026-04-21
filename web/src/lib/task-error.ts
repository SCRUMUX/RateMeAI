// Mirrors src/bot/handlers/mode_select.py::_user_message_for_failed — keep
// the two in sync so Telegram and web give the same explanations for the
// same backend error_message shape ("[stage=<stage>] <ExcType>: <msg>").

const GENERIC_FAILED_MESSAGE =
  'Не удалось сгенерировать фото. Кредит возвращён, попробуйте ещё раз.';

const NO_FACE_MESSAGE =
  'На фото не нашлось чёткого лица. Загрузите фронтальный портрет крупным ' +
  'планом, в хорошем освещении, без размытия.';

const MULTIPLE_FACES_MESSAGE =
  'На фото несколько человек. Загрузите портрет одного человека — без ' +
  'посторонних в кадре.';

const INVALID_IMAGE_MESSAGE =
  'Не удалось открыть изображение. Загрузите фото в формате JPG или PNG, ' +
  'не меньше 400×400 пикселей и до 10 МБ.';

const STASH_EXPIRED_MESSAGE =
  'Время на обработку фото истекло. Загрузите фото ещё раз и запустите ' +
  'генерацию — кредит возвращён.';

const TRANSIENT_MESSAGE =
  'Серверы AI сейчас перегружены. Попробуйте ещё раз через минуту — ' +
  'кредит возвращён.';

const MODERATION_MESSAGE =
  'Фото не прошло проверку безопасности. Загрузите другое фото.';

const CONSENT_MESSAGE =
  'Для обработки нужны все согласия. Откройте настройки и подтвердите ' +
  'обработку данных, передачу в AI и возраст 16+.';

const INTERNAL_MESSAGE =
  'Произошла внутренняя ошибка. Мы уже разбираемся — попробуйте ещё раз ' +
  'через пару минут.';

const PROVIDER_AUTH_MESSAGE =
  'Сервис AI временно недоступен из-за проблемы с подключением к модели. ' +
  'Мы уже чиним — кредит возвращён, попробуйте позже.';

// The worker writes `error_message` as:
//   [stage=<stage>] <ExcType>: <human message>
// We want to surface the human message (Cyrillic allowed) for unknown
// patterns — so instead of a useless generic text the user still gets an
// actionable hint. The regex is intentionally loose: it tolerates missing
// stage tag and missing exception type.
function extractHumanTail(errorMessage: string): string {
  const withoutStage = errorMessage.replace(/^\[stage=[^\]]+\]\s*/i, '');
  const idx = withoutStage.indexOf(': ');
  const tail = idx >= 0 ? withoutStage.slice(idx + 2) : withoutStage;
  return tail.trim();
}

function looksHumanReadable(text: string): boolean {
  if (!text) return false;
  if (text.length < 6) return false;
  // Prefer Cyrillic sentences; avoid leaking raw Python tracebacks / keys.
  return /[А-ЯЁа-яё]/.test(text);
}

export function userMessageForFailed(errorMessage: string | null | undefined): string {
  if (!errorMessage) return GENERIC_FAILED_MESSAGE;

  const em = errorMessage.toLowerCase();

  // --- Input-quality / preprocess blockers -------------------------------

  if (
    em.includes('multiple_faces') ||
    em.includes('несколько человек') ||
    em.includes('несколько лиц')
  ) {
    return MULTIPLE_FACES_MESSAGE;
  }

  if (
    em.includes('no_face') ||
    em.includes('не обнаружено лицо') ||
    em.includes('лицо не обнаружено') ||
    em.includes('не нашлось') ||
    em.includes('face_too_small') ||
    em.includes('blurry_photo') ||
    em.includes('face_blurred') ||
    em.includes('low_resolution') ||
    em.includes('лицо слишком мал') ||
    em.includes('лицо слишком мелк') ||
    em.includes('низкое разреш') ||
    em.includes('слишком размыт') ||
    em.includes('размыт')
  ) {
    return NO_FACE_MESSAGE;
  }

  if (
    em.includes('invalid_image') ||
    em.includes('invalid image file') ||
    em.includes('unsupported format') ||
    em.includes('image too small') ||
    em.includes('не удалось открыть изображение') ||
    em.includes('неподдерживаемый формат')
  ) {
    return INVALID_IMAGE_MESSAGE;
  }

  // --- Privacy / stash lifecycle -----------------------------------------

  if (
    em.includes('task input stash') ||
    em.includes('stash expired') ||
    em.includes('must be re-submitted') ||
    em.includes('privacy retention policy')
  ) {
    return STASH_EXPIRED_MESSAGE;
  }

  // --- Provider auth / billing (non-transient) ---------------------------
  // Worker now emits "http=<code>" after unwrapping RetryError — see
  // src/workers/tasks.py::_format_task_error. 401/402/403/404 from the
  // LLM/image-gen provider are permanent on our side and need an ops fix;
  // we tell the user it's our problem and the credit was refunded.

  if (
    em.includes('http=401') ||
    em.includes('http=402') ||
    em.includes('http=403') ||
    em.includes('http=404') ||
    em.includes('insufficient_credits') ||
    em.includes('unauthorized') ||
    em.includes('invalid api key') ||
    em.includes('api key')
  ) {
    return PROVIDER_AUTH_MESSAGE;
  }

  // --- Transient provider / network issues -------------------------------

  if (
    em.includes('readtimeout') ||
    em.includes('writetimeout') ||
    em.includes('pooltimeout') ||
    em.includes('connecttimeout') ||
    em.includes('connectionerror') ||
    em.includes('timeouterror') ||
    em.includes('timeout') ||
    em.includes('http=408') ||
    em.includes('http=425') ||
    em.includes('http=429') ||
    em.includes('http=500') ||
    em.includes('http=502') ||
    em.includes('http=503') ||
    em.includes('http=504') ||
    em.includes(' 429') ||
    em.includes(']429') ||
    em.includes(':429') ||
    em.includes(' 503') ||
    em.includes(']503') ||
    em.includes(':503') ||
    em.includes(' 502') ||
    em.includes(']502') ||
    em.includes(':502') ||
    em.includes(' 504') ||
    em.includes(']504') ||
    em.includes(':504') ||
    em.includes('rate limit') ||
    em.includes('temporarily')
  ) {
    return TRANSIENT_MESSAGE;
  }

  // --- Moderation / safety -----------------------------------------------

  if (
    em.includes('content policy') ||
    em.includes('moderation') ||
    em.includes('nsfw') ||
    em.includes('модерац') ||
    em.includes('запрещ')
  ) {
    return MODERATION_MESSAGE;
  }

  // --- Consent / AI transfer guard ---------------------------------------

  if (em.includes('aitransferforbidden') || em.includes('ai_transfer')) {
    return CONSENT_MESSAGE;
  }

  if (em.includes('no_pipeline_context')) {
    return INTERNAL_MESSAGE;
  }

  // --- Unknown pattern: try to surface the human-readable tail -----------

  const tail = extractHumanTail(errorMessage);
  if (looksHumanReadable(tail)) {
    const cap = tail.length > 220 ? tail.slice(0, 217).trimEnd() + '...' : tail;
    return `Не удалось сгенерировать фото: ${cap} Кредит возвращён.`;
  }

  return GENERIC_FAILED_MESSAGE;
}
