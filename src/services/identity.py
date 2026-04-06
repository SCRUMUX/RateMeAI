"""Face identity verification using InsightFace (ArcFace).

Computes face embeddings and compares them to ensure the generated image
preserves the identity of the original photo.
"""
from __future__ import annotations

import io
import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_app = None


def _get_app():
    """Lazy-load InsightFace app (heavy model, load once)."""
    global _app
    if _app is None:
        from insightface.app import FaceAnalysis
        _app = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
        )
        _app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("InsightFace model loaded")
    return _app


def _image_to_array(image_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(img)


class IdentityService:
    """Face identity verification via ArcFace embeddings."""

    def __init__(self, threshold: float = 0.85):
        self._threshold = threshold

    def compute_embedding(self, image_bytes: bytes) -> np.ndarray | None:
        """Extract the dominant face embedding from image bytes.

        Returns None if no face is detected.
        """
        try:
            arr = _image_to_array(image_bytes)
            app = _get_app()
            faces = app.get(arr)
            if not faces:
                logger.warning("No face detected for embedding")
                return None
            best = max(faces, key=lambda f: f.det_score)
            return best.normed_embedding
        except Exception:
            logger.exception("Failed to compute face embedding")
            return None

    def compare(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Cosine similarity between two embeddings. Returns 0.0-1.0."""
        if emb1 is None or emb2 is None:
            return 0.0
        sim = float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2) + 1e-8))
        return max(0.0, min(1.0, sim))

    def verify(self, original_bytes: bytes, generated_bytes: bytes) -> tuple[bool, float]:
        """Check if generated image preserves identity of original.

        Returns (passed, similarity_score).
        """
        emb_orig = self.compute_embedding(original_bytes)
        if emb_orig is None:
            logger.warning("No face in original — skipping identity gate")
            return True, 0.0

        emb_gen = self.compute_embedding(generated_bytes)
        if emb_gen is None:
            logger.warning("No face in generated image — identity gate failed")
            return False, 0.0

        sim = self.compare(emb_orig, emb_gen)
        passed = sim >= self._threshold
        logger.info("Identity gate: similarity=%.3f threshold=%.2f passed=%s", sim, self._threshold, passed)
        return passed, sim

    def detect_face(self, image_bytes: bytes) -> bool:
        """Check if the image contains at least one face."""
        try:
            arr = _image_to_array(image_bytes)
            app = _get_app()
            faces = app.get(arr)
            return len(faces) > 0
        except Exception:
            logger.exception("Face detection failed")
            return False
