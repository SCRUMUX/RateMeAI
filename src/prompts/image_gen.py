"""Centralized image-generation prompt builder for all modes."""
from __future__ import annotations

FACE_ANCHOR = (
    "STRICT IDENTITY RULE: the person's face shape, nose, eyes, eyebrows, "
    "lips, jawline, ears, and bone structure MUST remain pixel-identical to "
    "the reference photo. Do NOT reshape, resize, or reposition any facial "
    "feature. The person must be instantly recognizable."
)

SKIN_ENHANCE = (
    "Enhance skin: remove blemishes, acne, and dark spots; even out skin "
    "tone; reduce visible pores and under-eye circles; add a healthy natural "
    "glow. Smooth wrinkles gently while keeping skin texture realistic — "
    "no plastic or airbrushed look."
)

DATING_STYLES: dict[str, str] = {
    "warm_outdoor": (
        "Background: warm golden-hour outdoor scene with soft bokeh "
        "(park, city sunset, or seaside). "
        "Clothing: stylish casual outfit that flatters the person."
    ),
    "studio_elegant": (
        "Background: professional studio with soft gradient lighting. "
        "Clothing: elegant evening outfit (dark tones, well-fitted)."
    ),
    "cafe": (
        "Background: cozy upscale café or wine bar with warm ambient light. "
        "Clothing: smart-casual date-night outfit."
    ),
}

DATING_PERSONALITIES: dict[str, str] = {
    "friendly": "Expression: warm genuine smile, soft relaxed eyes, open and inviting body language.",
    "confident": "Expression: strong direct gaze, slight knowing smirk, squared shoulders conveying power.",
    "charismatic": "Expression: bright magnetic smile reaching the eyes, dynamic energy, infectious charm.",
}

CV_STYLES: dict[str, str] = {
    "corporate": (
        "Background: clean modern corporate office, neutral grey/white wall. "
        "Clothing: formal business suit with tie or blazer, crisp white shirt."
    ),
    "creative": (
        "Background: modern creative workspace with subtle design elements. "
        "Clothing: smart-casual — neat blazer over a crew-neck, no tie."
    ),
    "neutral": (
        "Background: solid light-grey professional studio backdrop. "
        "Clothing: classic professional attire appropriate for the industry."
    ),
}

CV_PERSONALITIES: dict[str, str] = {
    "corporate": "Expression: composed, trustworthy, measured professional confidence.",
    "startup": "Expression: relaxed and approachable, slight friendly smile, tech-savvy modern vibe.",
    "creative": "Expression: bold, expressive, confident artistic energy with a hint of unconventionality.",
}


def build_dating_prompt(style: str = "") -> str:
    style_block = DATING_STYLES.get(style, DATING_STYLES["warm_outdoor"])
    personality = DATING_PERSONALITIES.get(style, DATING_PERSONALITIES["friendly"])
    return (
        "Transform this portrait into an attractive dating-profile photo. "
        f"{SKIN_ENHANCE} "
        f"{personality} "
        "Brighten the whites of the eyes and subtly enhance iris color. "
        "Improve lighting to soft, flattering, directional golden-hour quality. "
        f"{style_block} "
        f"{FACE_ANCHOR} "
        "The final image must be indistinguishable from a real high-end photograph."
    )


def build_cv_prompt(style: str = "") -> str:
    style_block = CV_STYLES.get(style, CV_STYLES["corporate"])
    personality = CV_PERSONALITIES.get(style, CV_PERSONALITIES["corporate"])
    return (
        "Transform this portrait into a professional corporate headshot. "
        f"{SKIN_ENHANCE} "
        f"{personality} "
        "Improve lighting to even, soft studio quality with catchlights in eyes. "
        f"{style_block} "
        f"{FACE_ANCHOR} "
        "The final image must look like a real executive portrait by a professional photographer."
    )


def build_emoji_prompt(base_description: str = "") -> str:
    prompt = (
        "Cartoon sticker avatar of the person from <ref>0</ref>. "
        "Keep recognizable facial proportions, face shape, hairstyle and hair color. "
        "Bold outlines, flat vibrant colors, friendly expression, square composition."
    )
    desc = base_description[:400]
    if desc:
        prompt = f"{prompt} Character: {desc}"
    return prompt
