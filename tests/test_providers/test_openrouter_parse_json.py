"""Regression tests for OpenRouterLLM._parse_json (v1.14.2).

Gemini (via OpenRouter) occasionally returns a JSON array ``[{...}]``
despite the ``response_format: json_object`` hint. Before 1.14.2 that
made ``_parse_json`` return a ``list``, which then propagated into
``QualityGateRunner._get_quality_metrics`` and crashed with
``AttributeError: 'list' object has no attribute 'get'``. The exception
was swallowed, identity_match silently "passed", and a mismatched photo
was delivered to the user.

These tests pin the contract:
    * single-item list containing a dict → unwrapped to that dict
    * any other non-dict shape → explicit ``ValueError``
so the failure surfaces as ``quality_check_failed`` instead of a silent
bypass.
"""

from __future__ import annotations

import json

import pytest

from src.providers.llm.openrouter import OpenRouterLLM


def test_parse_json_returns_dict_as_is():
    text = json.dumps({"identity_match": 8.5, "aesthetic_score": 7.0})
    assert OpenRouterLLM._parse_json(text) == {
        "identity_match": 8.5,
        "aesthetic_score": 7.0,
    }


def test_parse_json_strips_markdown_code_fence():
    text = '```json\n{"ok": true}\n```'
    assert OpenRouterLLM._parse_json(text) == {"ok": True}


def test_parse_json_unwraps_single_item_list_of_dict():
    """Gemini occasionally wraps the object in ``[...]``; unwrap it."""
    text = json.dumps([{"identity_match": 9.0, "details": "same person"}])
    assert OpenRouterLLM._parse_json(text) == {
        "identity_match": 9.0,
        "details": "same person",
    }


def test_parse_json_raises_on_empty_list():
    with pytest.raises(ValueError, match="non-object JSON"):
        OpenRouterLLM._parse_json("[]")


def test_parse_json_raises_on_multi_item_list():
    with pytest.raises(ValueError, match="non-object JSON"):
        OpenRouterLLM._parse_json(json.dumps([{"a": 1}, {"b": 2}]))


def test_parse_json_raises_on_list_of_non_dict():
    with pytest.raises(ValueError, match="non-object JSON"):
        OpenRouterLLM._parse_json(json.dumps(["not", "a", "dict"]))


def test_parse_json_raises_on_bare_scalar():
    with pytest.raises(ValueError, match="non-object JSON"):
        OpenRouterLLM._parse_json("42")
