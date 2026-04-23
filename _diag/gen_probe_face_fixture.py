"""Helper: regenerate src/api/v1/_fixtures/probe_face.py from the base64 blob.

Input:  _diag/_probe_face_b64.txt (one big chunked base64 JPEG)
Output: src/api/v1/_fixtures/__init__.py, src/api/v1/_fixtures/probe_face.py
"""

from __future__ import annotations

import os
import textwrap

HEADER = '''"""PuLID smoke-probe fixture - small base64 JPEG with a clearly detectable face.

Used by :func:`image_gen_probe` in ``identity_scene`` mode. The image is a
256x256 AI-generated portrait (no real person - sourced from
``thispersondoesnotexist.com``, which emits CC0 StyleGAN samples) encoded
inline so CI probe calls have zero network dependencies and no risk of
leaking user content. facexlib inside fal-ai/pulid reliably detects the
face in this image.

Size: ~12.6 KB decoded / ~19 KB base64. Regenerate with
``_diag/gen_probe_face_fixture.py`` if a better fixture is ever needed.
"""
from __future__ import annotations

import base64

# 256x256 JPEG, ~12.6 KB. Chunked for readability; stripped of whitespace
# at decode time.
_PROBE_FACE_B64 = (
'''

FOOTER = ''')


def probe_face_jpeg() -> bytes:
    """Return the raw bytes of the PuLID identity-scene smoke-probe face."""
    return base64.b64decode(_PROBE_FACE_B64)
'''


def main() -> None:
    raw = open("_diag/_probe_face_b64.txt").read().replace("\n", "").strip()
    chunks = textwrap.wrap(raw, 70)
    body = "\n".join(f'    "{c}"' for c in chunks)

    os.makedirs("src/api/v1/_fixtures", exist_ok=True)
    # Ensure package marker exists (empty is fine).
    init_path = "src/api/v1/_fixtures/__init__.py"
    if not os.path.exists(init_path):
        with open(init_path, "w") as fh:
            fh.write("")

    with open(
        "src/api/v1/_fixtures/probe_face.py",
        "w",
        encoding="utf-8",
        newline="\n",
    ) as fh:
        fh.write(HEADER + body + FOOTER)

    print("wrote src/api/v1/_fixtures/probe_face.py")


if __name__ == "__main__":
    main()
