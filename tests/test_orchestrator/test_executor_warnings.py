"""Phase 3 (v1.27.3): executor surfaces soft-substitution warnings.

The executor reads ``CompositionIR.substitutions`` (carried out of
``build_image_prompt_v2`` via the new ``out_substitutions`` parameter)
and writes one Russian message per record into
``result_dict.generation_warnings``. The web client reads that field
in :func:`web/src/lib/api.ts:readGenerationWarnings`.

We assert on:

* the RU formatter (``_format_substitution_notice_ru``) produces the
  exact wording specified in the plan, including channel name
  translation;
* unknown channel codes fall back to the raw channel string so future
  channels do not crash the formatter.
"""

from __future__ import annotations

from src.orchestrator.executor import _format_substitution_notice_ru


def test_format_lighting_substitution_notice_ru():
    sub = {"channel": "lighting", "requested": "lasers", "applied": "warm"}
    msg = _format_substitution_notice_ru(sub)
    assert msg == (
        "Параметр «Освещение: lasers» не распознан, "
        "использован близкий вариант: «warm»."
    )


def test_format_scene_substitution_notice_ru():
    sub = {"channel": "scene", "requested": "Эверест", "applied": "crosswalk"}
    msg = _format_substitution_notice_ru(sub)
    assert "Сцена" in msg and "Эверест" in msg and "crosswalk" in msg


def test_format_unknown_channel_falls_back_to_raw_label():
    sub = {"channel": "future_knob", "requested": "x", "applied": "y"}
    msg = _format_substitution_notice_ru(sub)
    assert "future_knob" in msg
    assert "x" in msg and "y" in msg
