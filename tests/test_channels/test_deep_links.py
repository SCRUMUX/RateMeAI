"""Tests for channel-aware deep link generation."""
from __future__ import annotations

from unittest.mock import patch

from src.channels.deep_links import build_deep_link, build_share_caption


@patch("src.channels.deep_links.settings")
def test_telegram_deep_link(mock_s):
    mock_s.telegram_bot_username = "TestBot"
    link = build_deep_link("uid-1", "telegram")
    assert "t.me/TestBot" in link
    assert "ref_uid-1" in link


@patch("src.channels.deep_links.settings")
def test_ok_deep_link(mock_s):
    mock_s.ok_app_id = "ok123"
    link = build_deep_link("uid-2", "ok")
    assert "ok.ru" in link
    assert "ok123" in link


@patch("src.channels.deep_links.settings")
def test_vk_deep_link(mock_s):
    mock_s.vk_app_id = "vk456"
    link = build_deep_link("uid-3", "vk")
    assert "vk.com/app" in link
    assert "vk456" in link


@patch("src.channels.deep_links.settings")
def test_web_deep_link(mock_s):
    mock_s.web_base_url = "https://ratemeai.com"
    link = build_deep_link("uid-4", "web")
    assert "ratemeai.com" in link
    assert "ref=uid-4" in link


def test_share_caption_score():
    caption = build_share_caption({"score": 8}, "telegram")
    assert "рейтинг" in caption.lower()


def test_share_caption_dating():
    caption = build_share_caption({"dating_score": 7}, "ok")
    assert "знакомств" in caption.lower()


def test_share_caption_generic():
    caption = build_share_caption({}, "web")
    assert "результат" in caption.lower()
