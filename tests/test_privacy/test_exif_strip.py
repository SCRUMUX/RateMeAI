"""PrivacyLayer.sanitize_and_normalize must unconditionally strip metadata."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from src.services.privacy import PrivacyLayer


def _jpeg_with_exif(size: tuple[int, int] = (1200, 1600)) -> bytes:
    """Build a JPEG carrying an EXIF block (camera make/model + fake GPS)."""
    img = Image.new("RGB", size, color=(180, 120, 90))

    # Build an EXIF container with PIL's native API.
    exif = img.getexif()
    exif[0x010F] = "TestCam"  # Make
    exif[0x0110] = "UnitTest"  # Model
    exif[0x8825] = {  # GPSInfo IFD
        1: "N",
        2: (55.0, 45.0, 0.0),
        3: "E",
        4: (37.0, 37.0, 0.0),
    }
    exif_bytes = exif.tobytes()

    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes, quality=92)
    return buf.getvalue()


def _reload(raw: bytes) -> Image.Image:
    return Image.open(io.BytesIO(raw))


def test_sanitize_strips_exif_tags():
    src = _jpeg_with_exif()

    original = _reload(src)
    assert len(original.getexif()) > 0, "sanity: source jpeg must carry EXIF"

    sanitized = PrivacyLayer.sanitize_and_normalize(src)
    cleaned = _reload(sanitized.bytes_)

    leaked = dict(cleaned.getexif())
    # Any private tag that PIL stamps (e.g. orientation) is fine; but the
    # identifying keys we planted must all be gone.
    assert 0x010F not in leaked, f"Make tag leaked: {leaked}"
    assert 0x0110 not in leaked, f"Model tag leaked: {leaked}"
    assert 0x8825 not in leaked, f"GPSInfo tag leaked: {leaked}"
    assert cleaned.info.get("icc_profile") in (b"", None, b""), "ICC must be absent"


def test_sanitize_rejects_too_small_image():
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), color=(0, 0, 0)).save(buf, format="JPEG")
    with pytest.raises(ValueError):
        PrivacyLayer.sanitize_and_normalize(buf.getvalue())


def test_sanitize_preserves_usable_dimensions():
    buf = io.BytesIO()
    Image.new("RGB", (1500, 1500), color=(0, 0, 0)).save(buf, format="JPEG")
    sanitized = PrivacyLayer.sanitize_and_normalize(buf.getvalue())

    out = _reload(sanitized.bytes_)
    assert min(out.size) >= 100
    assert max(out.size) <= 2048
