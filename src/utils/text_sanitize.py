"""Sanitize free-form text coming from LLM outputs before showing to users.

LLM answers occasionally contain HTML tags (``<span style=...>``), markdown
code fences, stray JSON fragments, or control characters. These are never
intended for end users — the bot and the web both expect plain Russian prose.

This module provides a small, conservative cleaner that:
  * strips HTML tags (``<tag ...>``), including self-closed and broken ones
  * removes markdown code fences (``` ``` ``` ``` and single backticks)
  * collapses leaked JSON fragments like ``"first_impression": "..."``
  * removes HTML entities (``&nbsp;`` → space, ``&amp;`` → ``&``)
  * strips ANSI / control characters
  * collapses excessive whitespace

The goal is not to be a full-fledged sanitizer (we do not render HTML) —
only to guarantee that what the user sees is plain text.
"""

from __future__ import annotations

import html
import re

_HTML_TAG_RE = re.compile(r"<[^<>]{0,2000}>")
_CODE_FENCE_RE = re.compile(r"```[a-zA-Z0-9_-]*\n?|```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`([^`\n]{1,200})`")
_JSON_KEY_RE = re.compile(r'"\s*[a-zA-Z_][a-zA-Z0-9_]*\s*"\s*:\s*', re.MULTILINE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def sanitize_llm_text(value: object, *, max_len: int = 2000) -> str:
    """Return a plain-text version of ``value`` safe to show to end users.

    Non-string inputs are coerced via ``str()`` (``None`` becomes ``""``).
    The output is trimmed to ``max_len`` characters.
    """
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    if not text:
        return ""

    text = _ANSI_RE.sub("", text)
    text = _CTRL_RE.sub("", text)

    text = _CODE_FENCE_RE.sub("", text)
    text = _INLINE_CODE_RE.sub(lambda m: m.group(1), text)

    text = _HTML_TAG_RE.sub("", text)
    text = html.unescape(text)

    text = _JSON_KEY_RE.sub("", text)
    text = text.replace("\\n", "\n").replace("\\t", " ").replace('\\"', '"')

    text = _WS_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    text = text.strip().strip('"').strip("'").strip()

    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text
