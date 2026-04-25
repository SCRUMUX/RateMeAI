"""Regression test: bot pins ``image_model=gpt_image_2`` in form_data.

The bot UI does not expose the A/B model picker — we ship it
exclusively through the web client (see ``web/src/data/ab-models.ts``
for the Premium/NB2 toggle). Until v1.27.2 the bot did not include
``image_model`` in its multipart form, so the server quietly fell
back to ``settings.ab_default_model``. That fallback is correct on a
clean deploy, but a manual Railway-dashboard tweak to
``AB_DEFAULT_MODEL=nano_banana_2`` (or ``AB_TEST_ENABLED=false``,
which routes to PuLID) would silently send Telegram traffic to a
non-GPT model.

Plan v1.27.2 makes the bot an *always-GPT client* by sending
``image_model=gpt_image_2`` explicitly in the analyze POST. This
test guards that decision via a static AST inspection — much faster
than spinning up the aiogram dispatcher and easier to debug than a
full integration test.
"""

from __future__ import annotations

import ast
from pathlib import Path

MODE_SELECT = (
    Path(__file__).resolve().parents[2] / "src" / "bot" / "handlers" / "mode_select.py"
)


def _form_data_assignment_in(func_name: str) -> ast.Dict | None:
    """Return the ``form_data = {...}`` dict literal inside ``func_name``.

    There is exactly one such literal — the bot's analyze-call payload.
    Returns ``None`` when the assignment cannot be located so the
    calling test fails with a structural error instead of a misleading
    KeyError.
    """
    tree = ast.parse(MODE_SELECT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == func_name:
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Assign)
                    and len(sub.targets) == 1
                    and isinstance(sub.targets[0], ast.Name)
                    and sub.targets[0].id == "form_data"
                    and isinstance(sub.value, ast.Dict)
                ):
                    return sub.value
    return None


def test_submit_analysis_pins_image_model_to_gpt_image_2() -> None:
    """``form_data`` must include ``"image_model": "gpt_image_2"``.

    If a future refactor renames the field, switches the model, or
    drops the line entirely, this test fails with a clear message
    pointing at the bot policy decision rather than at a silent
    fallback in the server-side router.
    """
    form_dict = _form_data_assignment_in("_submit_analysis")
    assert form_dict is not None, (
        "Could not locate ``form_data = {...}`` literal in "
        "_submit_analysis. Did the function get renamed or split?"
    )

    pairs: dict[str, str] = {}
    for key, value in zip(form_dict.keys, form_dict.values):
        if isinstance(key, ast.Constant) and isinstance(value, ast.Constant):
            pairs[key.value] = value.value

    assert pairs.get("image_model") == "gpt_image_2", (
        "Bot must explicitly send image_model=gpt_image_2 — bot UI has "
        "no model picker, so omitting the field defers to "
        "settings.ab_default_model which can drift via Railway dashboard. "
        f"Current literal pairs: {pairs!r}"
    )
