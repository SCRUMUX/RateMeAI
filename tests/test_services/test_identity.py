"""Tests for IdentityService (InsightFace mocked)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import numpy as np

from src.services.identity import IdentityService


def test_compare_identical_embeddings():
    svc = IdentityService(threshold=0.85)
    emb = np.random.randn(512).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    score = svc.compare(emb, emb)
    assert score >= 0.99


def test_compare_orthogonal_embeddings():
    svc = IdentityService(threshold=0.85)
    emb1 = np.zeros(512, dtype=np.float32)
    emb1[0] = 1.0
    emb2 = np.zeros(512, dtype=np.float32)
    emb2[1] = 1.0
    score = svc.compare(emb1, emb2)
    assert score < 0.01


def test_compare_none_returns_zero():
    svc = IdentityService(threshold=0.85)
    emb = np.random.randn(512).astype(np.float32)
    assert svc.compare(None, emb) == 0.0
    assert svc.compare(emb, None) == 0.0
    assert svc.compare(None, None) == 0.0


@patch("src.services.identity._image_to_array", return_value=np.zeros((100, 100, 3), dtype=np.uint8))
@patch("src.services.identity._get_app")
def test_verify_passes_when_similar(mock_get_app, _mock_img):
    face = MagicMock()
    emb = np.random.randn(512).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    face.normed_embedding = emb
    face.det_score = 0.99

    app = MagicMock()
    app.get.return_value = [face]
    mock_get_app.return_value = app

    svc = IdentityService(threshold=0.85)
    passed, sim = svc.verify(b"fake_orig", b"fake_gen")
    assert passed is True
    assert sim >= 0.99


@patch("src.services.identity._image_to_array", return_value=np.zeros((100, 100, 3), dtype=np.uint8))
@patch("src.services.identity._get_app")
def test_verify_skips_when_no_face_in_original(mock_get_app, _mock_img):
    app = MagicMock()
    app.get.return_value = []
    mock_get_app.return_value = app

    svc = IdentityService(threshold=0.85)
    passed, sim = svc.verify(b"no_face_img", b"gen_img")
    assert passed is True
    assert sim == 0.0


@patch("src.services.identity._image_to_array", return_value=np.zeros((100, 100, 3), dtype=np.uint8))
@patch("src.services.identity._get_app")
def test_verify_fails_when_no_face_in_generated(mock_get_app, _mock_img):
    face = MagicMock()
    face.normed_embedding = np.random.randn(512).astype(np.float32)
    face.det_score = 0.99

    app = MagicMock()
    app.get.side_effect = [[face], []]
    mock_get_app.return_value = app

    svc = IdentityService(threshold=0.85)
    passed, sim = svc.verify(b"orig", b"gen_no_face")
    assert passed is False
    assert sim == 0.0


@patch("src.services.identity._image_to_array", return_value=np.zeros((100, 100, 3), dtype=np.uint8))
@patch("src.services.identity._get_app")
def test_detect_face_returns_true(mock_get_app, _mock_img):
    face = MagicMock()
    face.det_score = 0.95
    app = MagicMock()
    app.get.return_value = [face]
    mock_get_app.return_value = app

    svc = IdentityService()
    assert svc.detect_face(b"has_face") is True


@patch("src.services.identity._image_to_array", return_value=np.zeros((100, 100, 3), dtype=np.uint8))
@patch("src.services.identity._get_app")
def test_detect_face_returns_false(mock_get_app, _mock_img):
    app = MagicMock()
    app.get.return_value = []
    mock_get_app.return_value = app

    svc = IdentityService()
    assert svc.detect_face(b"no_face") is False
