"""Regression tests for the bot's ``/analyze`` payload.

The Telegram client never exposes the web modal (framing, input hints,
scenario picker), so ``_submit_analysis`` is the only place where the
bot can match the web's payload contract. Drift here was the root cause
of the "oversized head, pasted face" regression after the A/B cutover:
the executor's compatibility default ``framing='half_body'`` (see
``src/orchestrator/executor.py``) is wrong for Telegram previews — they
are tight head-and-shoulders crops and need ``framing='portrait'`` (or
``full_body`` for styles flagged ``needs_full_body``).

The previous version of this file pinned ``image_model='gpt_image_2'``
in ``form_data``. That decision was reverted: the bot now omits
``image_model`` and lets ``apply_ab_test_context_fields`` apply
``settings.ab_default_model`` (the same default anonymous web clients
use), so the channel-agnostic Premium rollout doesn't need a bot
deploy. The current invariants are:

1. ``form_data`` carries ``mode``, ``enhancement_level``, ``source``,
   ``framing`` and ``input_hints`` keys.
2. ``framing`` is computed dynamically (a function call, not a string
   constant) — never hard-coded.
3. ``input_hints`` is a JSON string (a ``json.dumps`` call) — that is
   the contract executor.modal_framing reads.
4. ``enhancement_level`` for photo modes is pinned to ``1``; only the
   ``emoji`` branch runs the depth-based ladder.
5. ``image_model`` is NOT in the payload — the server-side default
   path is the single source of truth.
"""

from __future__ import annotations

import ast
from pathlib import Path

MODE_SELECT = (
    Path(__file__).resolve().parents[2] / "src" / "bot" / "handlers" / "mode_select.py"
)


def _submit_analysis_node() -> ast.AsyncFunctionDef:
    tree = ast.parse(MODE_SELECT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_submit_analysis"
        ):
            return node
    raise AssertionError(
        "Could not locate _submit_analysis in mode_select.py — did it get renamed?"
    )


def _form_data_assignment() -> ast.Dict:
    node = _submit_analysis_node()
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Assign)
            and len(sub.targets) == 1
            and isinstance(sub.targets[0], ast.Name)
            and sub.targets[0].id == "form_data"
            and isinstance(sub.value, ast.Dict)
        ):
            return sub.value
    raise AssertionError(
        "form_data literal not found inside _submit_analysis — did the function get split?"
    )


def _form_data_keys() -> set[str]:
    form_dict = _form_data_assignment()
    keys: set[str] = set()
    for key in form_dict.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
    return keys


def test_form_data_carries_framing_and_input_hints() -> None:
    """Bot must forward ``framing`` + ``input_hints`` to mirror the web modal.

    Without these two fields the executor falls back to
    ``framing='half_body'`` (compatibility default) on Telegram
    previews — that is the head-crop × half-body clash that produces
    the "oversized head, pasted face" failure mode reported by users
    after the A/B cutover.
    """
    keys = _form_data_keys()
    required = {
        "mode",
        "enhancement_level",
        "source",
        "framing",
        "input_hints",
    }
    missing = required - keys
    assert not missing, (
        f"form_data is missing required keys for web↔bot payload parity: {missing!r}. "
        f"Current keys: {keys!r}"
    )


def test_form_data_does_not_pin_image_model() -> None:
    """Bot must NOT pin ``image_model`` — server default is the source of truth.

    Channel-agnostic policy: ``apply_ab_test_context_fields`` reads
    ``settings.ab_default_model`` (currently ``gpt_image_2``).
    Pinning ``image_model`` in the bot would silently lock Telegram
    traffic to a model that the server-side default can no longer
    move without a bot deploy.
    """
    keys = _form_data_keys()
    assert "image_model" not in keys, (
        "form_data must not include image_model — defer to "
        "settings.ab_default_model so Premium rollouts stay server-side. "
        f"Current keys: {keys!r}"
    )


def test_framing_is_computed_dynamically_not_constant() -> None:
    """``framing`` value must be a function call (per-style), not a literal.

    The bot picks framing from the StyleSpec via ``_framing_for_style``
    — pinning a constant would break ``needs_full_body`` styles
    (yoga / beach / running etc.).
    """
    form_dict = _form_data_assignment()
    framing_value: ast.AST | None = None
    for key, value in zip(form_dict.keys, form_dict.values):
        if isinstance(key, ast.Constant) and key.value == "framing":
            framing_value = value
            break
    assert framing_value is not None, "framing key not present in form_data"
    assert not isinstance(framing_value, ast.Constant), (
        "framing must be derived from the StyleSpec via "
        "_framing_for_style(mode, style); it is currently a literal "
        f"{ast.dump(framing_value)!r}."
    )


def test_input_hints_is_json_dumps_call() -> None:
    """``input_hints`` must be a ``json.dumps`` call — that is the wire format.

    executor.modal_framing reads the framing slot out of the parsed
    JSON; a raw dict would land in the form as ``str(dict)`` and the
    server-side parser would reject it.
    """
    form_dict = _form_data_assignment()
    hints_value: ast.AST | None = None
    for key, value in zip(form_dict.keys, form_dict.values):
        if isinstance(key, ast.Constant) and key.value == "input_hints":
            hints_value = value
            break
    assert hints_value is not None, "input_hints key not present in form_data"
    assert isinstance(hints_value, ast.Call), (
        "input_hints must be a json.dumps(...) call; current value is "
        f"{ast.dump(hints_value)!r}."
    )
    func = hints_value.func
    qualified = (
        f"{func.value.id}.{func.attr}"
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
        else getattr(func, "id", "")
    )
    assert qualified.endswith("dumps"), (
        f"input_hints must be JSON-serialized via json.dumps; got {qualified!r}."
    )


def test_enhancement_level_pinned_to_one_for_photo_modes() -> None:
    """``enhancement_level`` follows depth only for ``emoji``; photo modes use ``1``.

    For photo modes (dating/cv/social) ``enhancement_level`` only
    travels into the LLM analysis builder and perturbs
    ``base_description`` unpredictably — that drift was masked by the
    pre-v1.64 StyleRouter + CodeFormer post-chain but surfaces on the
    unified A/B path. Web pins it to ``1`` for the same reason
    (``web/src/context/AppContext.tsx``). Emoji is the only mode
    where the depth ladder actually feeds
    ``ENHANCEMENT_LEVEL_MODIFIERS`` in the prompt template.
    """
    node = _submit_analysis_node()
    source = ast.get_source_segment(MODE_SELECT.read_text(encoding="utf-8"), node) or ""
    assert 'mode == "emoji"' in source, (
        "_submit_analysis must branch on ``mode == 'emoji'`` and only "
        "use level_for_depth there. Current source does not contain "
        "that branch — photo modes will keep escalating depth into the "
        "LLM analysis prompt."
    )
    assert "enh_level = 1" in source, (
        "_submit_analysis must pin enh_level = 1 for non-emoji modes. "
        "Current source does not contain that assignment."
    )
