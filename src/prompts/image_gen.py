"""Centralized image-generation prompt builder for all modes.

Prompts are kept concise to stay within Reve API limits (~1000 chars).
Every prompt includes FACE_ANCHOR + SKIN_FIX + REALISM blocks.
"""
from __future__ import annotations

FACE_ANCHOR = (
    "IDENTITY LOCK: preserve exact face shape, nose, eyes, eyebrows, lips, "
    "jawline, chin, ears, cheekbones, forehead. Do NOT reshape or reposition "
    "any facial feature. Person must be instantly recognizable. "
    "MOUTH RULE: keep the original mouth expression exactly as-is. "
    "Do NOT add, remove, whiten, or reshape teeth. "
    "Do NOT add a smile or change the degree of smile."
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
    "friendly": "Expression: soft relaxed eyes, warm approachable look.",
    "confident": "Expression: strong direct gaze, squared shoulders, calm confidence.",
    "charismatic": "Expression: bright engaging eyes, magnetic energy, open posture.",
}

CV_STYLES: dict[str, str] = {
    "corporate": "Background: corporate office, neutral wall. Clothing: formal suit, crisp shirt.",
    "creative": "Background: creative workspace. Clothing: smart-casual blazer, no tie.",
    "neutral": "Background: light-grey studio backdrop. Clothing: classic professional attire.",
}

CV_PERSONALITIES: dict[str, str] = {
    "corporate": "Expression: composed, trustworthy professional confidence.",
    "startup": "Expression: relaxed, approachable, open gaze.",
    "creative": "Expression: bold, expressive, artistic energy.",
}

SOCIAL_STYLES: dict[str, str] = {
    "influencer": "Background: trendy urban rooftop or scenic overlook. Clothing: stylish streetwear, statement accessories.",
    "luxury": "Background: upscale lounge, marble textures, soft ambient light. Clothing: designer outfit, watches, jewelry.",
    "casual": "Background: sunlit park, beach, or cozy home interior. Clothing: relaxed casual wear, natural fabrics.",
    "artistic": "Background: gallery, mural wall, or creative studio. Clothing: eclectic artistic mix, bold colors.",
}

SOCIAL_PERSONALITIES: dict[str, str] = {
    "influencer": "Expression: bright confident look, engaging eye contact, charismatic energy.",
    "luxury": "Expression: elegant poise, mysterious allure, sophisticated calm.",
    "casual": "Expression: genuine relaxed look, warm natural feel, approachable vibe.",
    "artistic": "Expression: thoughtful creative gaze, expressive, unconventional character.",
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


def build_social_prompt(style: str = "") -> str:
    s = SOCIAL_STYLES.get(style, SOCIAL_STYLES["influencer"])
    p = SOCIAL_PERSONALITIES.get(style, SOCIAL_PERSONALITIES["influencer"])
    return (
        f"Social media profile photo. Enhance, do NOT recreate face. "
        f"{FACE_ANCHOR} {SKIN_FIX} {p} "
        f"Vibrant colors, modern aesthetic, crisp detail. "
        f"{s} {REALISM}"
    )


STEP_TEMPLATES: dict[str, str] = {
    "background_edit": (
        "Change ONLY the background: {description}. "
        "Keep the person, clothing, and pose exactly as they are. "
        f"{FACE_ANCHOR} {REALISM}"
    ),
    "clothing_edit": (
        "Adjust ONLY the clothing/outfit: {description}. "
        "Keep face, background, and pose unchanged. "
        f"{FACE_ANCHOR} {REALISM}"
    ),
    "lighting_adjust": (
        "Improve ONLY the lighting and color grading: {description}. "
        "Natural studio quality, even skin tones. "
        f"{FACE_ANCHOR} {REALISM}"
    ),
    "expression_hint": (
        "Subtle expression adjustment: {description}. "
        "Keep identity, do not change face shape or features. "
        "Do NOT modify teeth or add smile. Keep original mouth. "
        f"{FACE_ANCHOR} {SKIN_FIX} {REALISM}"
    ),
    "skin_correction": (
        "Minor skin tone correction and blemish removal. "
        "Keep all facial features exactly the same. No plastic look. "
        f"{FACE_ANCHOR} {SKIN_FIX} {REALISM}"
    ),
    "style_overall": (
        "Apply overall style enhancement: {description}. "
        "Vibrant modern aesthetic, crisp detail. "
        f"{FACE_ANCHOR} {REALISM}"
    ),
}


def build_step_prompt(step_template: str, style: str, mode_styles: dict[str, str] | None = None) -> str:
    """Build a prompt for a single pipeline step, filling {description} from style dicts."""
    template = STEP_TEMPLATES.get(step_template, STEP_TEMPLATES.get("style_overall", ""))
    description = ""
    if mode_styles:
        description = mode_styles.get(style, next(iter(mode_styles.values()), ""))
    return template.replace("{description}", description)


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
