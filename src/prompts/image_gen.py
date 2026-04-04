"""Centralized image-generation prompt builder for all modes.

Prompts are kept concise to stay within Reve API limits (~1000 chars).
Every prompt includes FACE_ANCHOR + SKIN_FIX + REALISM blocks.
"""
from __future__ import annotations

FACE_ANCHOR = (
    "IDENTITY LOCK: preserve exact face shape, nose, eyes, eyebrows, lips, "
    "jawline, chin, ears, cheekbones, forehead. Do NOT reshape or reposition "
    "any facial feature. Person must be instantly recognizable."
)

SKIN_FIX = (
    "SKIN FIX (mandatory): remove dark circles and spots under eyes, "
    "blemishes, acne, pigmentation, redness, enlarged pores. "
    "Even out skin tone, add healthy glow. Keep realistic texture — "
    "no plastic or airbrushed look."
)

REALISM = (
    "PHOTOREALISM: must look like a real high-end photograph. "
    "No AI artifacts, no painterly effects, no unnatural glow."
)

DATING_STYLES: dict[str, str] = {
    "warm_outdoor": "Background: golden-hour outdoor, soft bokeh. Clothing: stylish casual.",
    "studio_elegant": "Background: studio, soft gradient lighting. Clothing: elegant evening, dark tones.",
    "cafe": "Background: cozy upscale cafe, warm light. Clothing: smart-casual date outfit.",
}

DATING_PERSONALITIES: dict[str, str] = {
    "friendly": "Expression: warm genuine smile, soft relaxed eyes.",
    "confident": "Expression: strong direct gaze, slight smirk, squared shoulders.",
    "charismatic": "Expression: bright magnetic smile, infectious charm.",
}

CV_STYLES: dict[str, str] = {
    "corporate": "Background: corporate office, neutral wall. Clothing: formal suit, crisp shirt.",
    "creative": "Background: creative workspace. Clothing: smart-casual blazer, no tie.",
    "neutral": "Background: light-grey studio backdrop. Clothing: classic professional attire.",
}

CV_PERSONALITIES: dict[str, str] = {
    "corporate": "Expression: composed, trustworthy professional confidence.",
    "startup": "Expression: relaxed, approachable, friendly smile.",
    "creative": "Expression: bold, expressive, artistic energy.",
}


def build_dating_prompt(style: str = "") -> str:
    s = DATING_STYLES.get(style, DATING_STYLES["warm_outdoor"])
    p = DATING_PERSONALITIES.get(style, DATING_PERSONALITIES["friendly"])
    return (
        f"Attractive dating-profile photo. Enhance, do NOT recreate face. "
        f"{FACE_ANCHOR} {SKIN_FIX} {p} "
        f"Brighten eye whites, subtle iris enhancement. "
        f"Soft flattering golden-hour lighting. {s} {REALISM}"
    )


def build_cv_prompt(style: str = "") -> str:
    s = CV_STYLES.get(style, CV_STYLES["corporate"])
    p = CV_PERSONALITIES.get(style, CV_PERSONALITIES["corporate"])
    return (
        f"Professional corporate headshot. Enhance, do NOT recreate face. "
        f"{FACE_ANCHOR} {SKIN_FIX} {p} "
        f"Studio catchlights in eyes. Hair groomed. Even soft lighting. "
        f"{s} {REALISM}"
    )


def build_emoji_prompt(base_description: str = "") -> str:
    prompt = (
        "Cartoon sticker avatar of the person from <ref>0</ref>. "
        "Keep recognizable facial proportions, face shape, hairstyle and hair color. "
        "Clean up any skin defects in cartoon style. "
        "Bold outlines, flat vibrant colors, friendly expression, square composition."
    )
    desc = base_description[:400]
    if desc:
        prompt = f"{prompt} Character: {desc}"
    return prompt
