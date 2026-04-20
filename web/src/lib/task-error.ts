// Mirrors src/bot/handlers/mode_select.py::_user_message_for_failed — keep
// the two in sync so Telegram and web give the same explanations for the
// same backend error_message shape ("[stage=<stage>] <ExcType>: <msg>").

const GENERIC_FAILED_MESSAGE =
  'Не удалось сгенерировать фото. Кредит возвращён, попробуйте ещё раз.';

export function userMessageForFailed(errorMessage: string | null | undefined): string {
  if (!errorMessage) return GENERIC_FAILED_MESSAGE;

  const em = errorMessage.toLowerCase();

  if (
    em.includes('no_face') ||
    em.includes('не обнаружено лицо') ||
    em.includes('лицо не обнаружено') ||
    em.includes('не нашлось') ||
    em.includes('face_too_small') ||
    em.includes('blurry_photo') ||
    em.includes('low_resolution') ||
    em.includes('лицо слишком мал') ||
    em.includes('лицо слишком мелк') ||
    em.includes('низкое разреш') ||
    em.includes('слишком размыт') ||
    em.includes('размыт')
  ) {
    return (
      'На фото не нашлось чёткого лица. Загрузите фронтальный портрет крупным ' +
      'планом, в хорошем освещении, без размытия.'
    );
  }

  if (
    em.includes('readtimeout') ||
    em.includes('writetimeout') ||
    em.includes('pooltimeout') ||
    em.includes('connecttimeout') ||
    em.includes('connectionerror') ||
    em.includes('timeouterror') ||
    em.includes('timeout') ||
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
    return (
      'Серверы AI сейчас перегружены. Попробуйте ещё раз через минуту — ' +
      'кредит возвращён.'
    );
  }

  if (
    em.includes('content policy') ||
    em.includes('moderation') ||
    em.includes('nsfw') ||
    em.includes('модерац') ||
    em.includes('запрещ')
  ) {
    return 'Фото не прошло проверку безопасности. Загрузите другое фото.';
  }

  if (em.includes('aitransferforbidden') || em.includes('ai_transfer')) {
    return (
      'Для обработки нужны все согласия. Откройте настройки и подтвердите ' +
      'обработку данных, передачу в AI и возраст 16+.'
    );
  }

  if (em.includes('no_pipeline_context')) {
    return (
      'Произошла внутренняя ошибка. Мы уже разбираемся — попробуйте ещё раз ' +
      'через пару минут.'
    );
  }

  return GENERIC_FAILED_MESSAGE;
}
