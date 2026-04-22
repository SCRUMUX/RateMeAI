"""FAL.ai PuLID provider — identity-conditioned text-to-image (v1.18).

PuLID is a **paradigm-shift** provider compared to the FLUX.2 Pro Edit
path: instead of taking a full user photo and editing it, PuLID takes
only a *cropped face* as a reference and generates an entirely new
scene from the prompt, with a hard identity-lock on the reference face.

- **What it's good for**: scene-heavy styles where the background and
  wardrobe should be generated from scratch (motorcycle, yacht, beach,
  warm_outdoor, dating_profile, etc.). The model preserves the face
  with very high fidelity at a fraction of the Edit-model cost.

- **What it's NOT good for**: styles that must preserve the original
  photo's background or composition (``social_clean``, ``cv_portrait``,
  emoji cutouts). Those go through the Seedream edit provider instead.
  See ``src/providers/image_gen/style_router.py``.

Wire contract
-------------
    POST https://queue.fal.run/fal-ai/pulid
    {
        "reference_images": [{"image_url": "data:image/jpeg;base64,..."}],
        "prompt": "...",
        "image_size": {"width": 1024, "height": 1024} | "portrait_4_3",
        "num_inference_steps": 4,        # FLUX Lightning default
        "guidance_scale": 1.2,           # tight range 1.0-1.5
        "id_scale": 0.8,                 # identity weight; 0 = no lock
        "mode": "fidelity" | "extreme style",
        "seed": <int>
    }

Only the lowercase ``reference_images`` and ``prompt`` are required.
The response shape is standard: ``{images: [{url}]}`` with a data URI
when ``sync_mode=true`` is not supported (PuLID ignores that flag,
so we always fetch the final URL from the response body).

Pricing
-------
PuLID on FAL bills by GPU-second rather than fixed per-image. At the
default 4-step Lightning config on an H100 the empirical average is
~$0.005–$0.008 per generation at 1 MP. We estimate $0.006 in
``settings.model_cost_fal_pulid`` for budget math; real usage is
tracked via the ``ratemeai_generation_cost_usd`` histogram labelled
``backend="pulid"``.
"""
from __future__ import annotations

import asyncio
import io
import logging
import random
from typing import Any

from PIL import Image

from src.providers.base import ImageGenProvider
from src.providers.image_gen._fal_queue_base import FalQueueClient
from src.services.ai_transfer_guard import assert_external_transfer_allowed

_SEED_MAX = 2**31 - 1
_SEED_RNG = random.SystemRandom()

logger = logging.getLogger(__name__)

# PuLID accepts either a preset enum or a ``{"width", "height"}`` dict
# for ``image_size``. Mirrors the FLUX.2 Pro Edit whitelist.
_PRESET_IMAGE_SIZES = frozenset({
    "square_hd",
    "square",
    "portrait_4_3",
    "portrait_16_9",
    "landscape_4_3",
    "landscape_16_9",
})

_PULID_MODES = frozenset({"fidelity", "extreme style"})

# Default negative prompt baked into every PuLID request.
#
# v1.19 — the hybrid pipeline shipped without a negative_prompt, which
# caused two recurrent failure modes on identity_scene outputs:
#
#   1. Duplicate subjects. A scene with "reflections on water" or
#      "Marina Bay Sands" paired with prompts that mentioned the word
#      "person" 2-3 times was reliably producing twins / a floating
#      second body. Diffusion models don't understand negation, so the
#      previous ``SOLO_SUBJECT_ANCHOR`` *positive* clause ("one person
#      only, single subject in frame") was actively reinforcing the
#      concept. Moving those tokens into the negative prompt flips
#      the gradient.
#   2. Identity drift. Without a negative on "morphed face, plastic
#      skin, extra fingers", FLUX Lightning at 4 steps was happy to
#      emit plastic-looking composites.
#
# The list is intentionally concise — PuLID's CLIP tokenizer truncates
# at 128 tokens by default and a bloated negative eats budget that the
# positive prompt needs.
_DEFAULT_NEGATIVE_PROMPT = (
    "two people, multiple people, multiple subjects, duplicate person, "
    "twins, second person in background, crowd, group photo, "
    "reflection rendered as a person, floating body, dismembered limbs, "
    "extra limbs, extra arms, extra hands, deformed hands, distorted "
    "fingers, morphed face, plastic skin, oil painting, illustration, "
    "cartoon, render, cgi, low quality, blurry, out of focus, jpeg "
    "artefacts, watermark, text, logo."
)


class FalPuLIDImageGen(FalQueueClient, ImageGenProvider):
    """FAL.ai PuLID client (identity-locked text-to-image)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/pulid",
        api_host: str = "https://queue.fal.run",
        id_scale: float = 1.0,
        pulid_mode: str = "fidelity",
        num_inference_steps: int = 25,
        guidance_scale: float = 3.5,
        default_image_size: Any = "portrait_4_3",
        negative_prompt: str | None = None,
        max_retries: int = 2,
        request_timeout: float = 180.0,
        poll_interval: float = 1.5,
    ):
        super().__init__(
            api_key,
            model=model,
            api_host=api_host,
            max_retries=max_retries,
            request_timeout=request_timeout,
            poll_interval=poll_interval,
            label="PuLID",
        )
        # v1.19 — widen id_scale / steps / guidance clamps to cover
        # PuLID's full operational range. Earlier clamps were tuned for
        # Lightning (4 steps, CFG ≤1.5) and were clipping the quality
        # preset we now ship by default.
        self._id_scale = max(0.01, min(5.0, float(id_scale)))
        mode = (pulid_mode or "fidelity").strip()
        self._mode = mode if mode in _PULID_MODES else "fidelity"
        self._steps = max(1, min(50, int(num_inference_steps)))
        self._guidance_scale = max(1.0, min(10.0, float(guidance_scale)))
        self._default_image_size = default_image_size
        self._negative_prompt = (
            negative_prompt.strip()
            if isinstance(negative_prompt, str) and negative_prompt.strip()
            else _DEFAULT_NEGATIVE_PROMPT
        )

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Body builder (PuLID-specific)
    # ------------------------------------------------------------------

    @classmethod
    def _normalize_image_size(cls, value: Any) -> Any | None:
        if isinstance(value, str):
            v = value.strip()
            if v in _PRESET_IMAGE_SIZES:
                return v
            return None
        if isinstance(value, dict):
            w, h = value.get("width"), value.get("height")
            try:
                wi, hi = int(w), int(h)
            except (TypeError, ValueError):
                return None
            if wi < 64 or hi < 64 or wi > 4096 or hi > 4096:
                return None
            return {"width": wi, "height": hi}
        return None

    def _build_body(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> dict[str, Any]:
        """Strict whitelist body for fal-ai/pulid.

        ``reference_image`` here is the cropped face (see
        ``src/services/face_crop.py``). PuLID also accepts multiple
        reference faces — we support passing additional crops via
        ``params['extra_reference_faces']`` for future use.
        """
        if not reference_image:
            raise ValueError(
                "FalPuLIDImageGen requires reference_image (face crop)"
            )

        extras = params or {}

        ref_list: list[dict[str, str]] = [
            {"image_url": self._data_url(reference_image)},
        ]
        for extra in extras.get("extra_reference_faces") or []:
            if isinstance(extra, (bytes, bytearray)) and extra:
                ref_list.append({"image_url": self._data_url(bytes(extra))})

        negative_prompt = (
            str(extras.get("negative_prompt") or "").strip()
            or self._negative_prompt
        )

        body: dict[str, Any] = {
            "prompt": prompt,
            "reference_images": ref_list,
            "num_images": 1,
            "num_inference_steps": int(
                extras.get("num_inference_steps") or self._steps,
            ),
            "guidance_scale": float(
                extras.get("guidance_scale") or self._guidance_scale,
            ),
            "id_scale": float(
                extras.get("id_scale") or self._id_scale,
            ),
            "mode": extras.get("pulid_mode") or self._mode,
            "negative_prompt": negative_prompt,
        }

        body["id_scale"] = max(0.01, min(5.0, body["id_scale"]))
        body["num_inference_steps"] = max(
            1, min(50, int(body["num_inference_steps"])),
        )
        body["guidance_scale"] = max(
            1.0, min(10.0, float(body["guidance_scale"])),
        )
        if body["mode"] not in _PULID_MODES:
            body["mode"] = "fidelity"

        # NOTE: fal-ai/pulid does **not** accept ``max_sequence_length``
        # (that's a FLUX.1 text-to-image knob, not a PuLID one). v1.19.0
        # wrongly added it and the API returned 422 on every call;
        # v1.19.1 removed it. Do not re-introduce without schema proof.

        seed = extras.get("seed")
        if isinstance(seed, int):
            body["seed"] = seed
        else:
            body["seed"] = _SEED_RNG.randrange(1, _SEED_MAX)

        size = self._normalize_image_size(extras.get("image_size"))
        if size is None:
            size = self._normalize_image_size(self._default_image_size)
        if size is not None:
            body["image_size"] = size

        return body

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _generate_sync(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> bytes:
        body = self._build_body(prompt, reference_image, params)
        logger.info(
            "FAL PuLID request model=%s prompt_len=%d mode=%s id_scale=%.2f "
            "steps=%d guidance=%.2f seed=%s size=%s neg_len=%d",
            self._model, len(prompt or ""), body.get("mode"),
            body.get("id_scale"), body.get("num_inference_steps"),
            body.get("guidance_scale", 0.0),
            body.get("seed"), body.get("image_size", "default"),
            len(body.get("negative_prompt") or ""),
        )
        return self._run_queue_sync(body)

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        assert_external_transfer_allowed("fal_pulid")
        raw = await asyncio.to_thread(
            self._generate_sync, prompt, reference_image, params,
        )
        if raw and len(raw) > 100:
            return raw
        try:
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            return buf.getvalue()
        except Exception as exc:
            raise RuntimeError(
                f"FAL PuLID: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalPuLIDImageGen"]
