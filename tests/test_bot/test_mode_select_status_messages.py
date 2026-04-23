"""Regression tests for bot status-message rendering.

Бот по умолчанию отправляет сообщения с parse_mode=Markdown
(см. src/bot/app.py → DefaultBotProperties). Если в текст попадёт
машинный detail от API (например, `no_credits`), символ `_` откроет
Markdown-италик, и Telegram вернёт:

    Bad Request: can't parse entities: Can't find end of the entity
    starting at byte offset 6

… после чего бот падает в generic except и пользователь видит
«Произошла ошибка. Попробуй позже.» вместо понятного сообщения.

Поэтому во всех error-ветках `_submit_analysis` мы обязаны явно передавать
`parse_mode=None`. Этот статический тест проверяет, что данное правило
не откатят случайной правкой.
"""

from __future__ import annotations

import ast
from pathlib import Path

MODE_SELECT = (
    Path(__file__).resolve().parents[2] / "src" / "bot" / "handlers" / "mode_select.py"
)


def _collect_edit_text_calls_in(func_name: str) -> list[ast.Call]:
    tree = ast.parse(MODE_SELECT.read_text(encoding="utf-8"))
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == func_name:
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "edit_text"
                ):
                    calls.append(sub)
    return calls


def test_submit_analysis_edit_text_never_uses_markdown() -> None:
    """Все status_msg.edit_text в _submit_analysis должны идти с parse_mode=None.

    Markdown-парсер Telegram падает на служебных символах в detail от бэка
    (`no_credits`, `style_not_found`, …) — мы обязаны отключать парсинг
    явно, независимо от default parse_mode у бота.
    """
    calls = _collect_edit_text_calls_in("_submit_analysis")
    assert calls, "Could not find edit_text calls in _submit_analysis — refactor?"

    offenders: list[str] = []
    for call in calls:
        parse_mode_kw = next((k for k in call.keywords if k.arg == "parse_mode"), None)
        if parse_mode_kw is None:
            offenders.append(f"line {call.lineno}: parse_mode not passed")
            continue
        # Допускаем только parse_mode=None.
        value = parse_mode_kw.value
        if not (isinstance(value, ast.Constant) and value.value is None):
            offenders.append(
                f"line {call.lineno}: parse_mode={ast.unparse(value)} (expected None)"
            )

    assert not offenders, (
        "edit_text in error branches must disable Markdown to avoid "
        "'can't parse entities' crashes on backend details like 'no_credits'. "
        "Offending calls:\n  - " + "\n  - ".join(offenders)
    )
