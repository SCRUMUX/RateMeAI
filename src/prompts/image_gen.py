"""Centralized image-generation prompt builder for all modes.

Every prompt includes FACE_ANCHOR + BODY_ANCHOR + SKIN_FIX + REALISM blocks
to ensure identity preservation, anatomical correctness, and photorealism.
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

BODY_ANCHOR = (
    "BODY PRESERVATION: keep exact original body proportions — head-to-body "
    "ratio, shoulder width, torso length, limb length. Do NOT enlarge or "
    "shrink the head relative to the body. Preserve the original pose, arm "
    "positions, and hand gestures exactly. Hands must have exactly 5 fingers "
    "with natural joint angles, no merged or extra digits. Limbs must be "
    "anatomically correct with natural length ratios. No warping, stretching, "
    "or compressing any body part. Keep natural relaxed posture."
)

SKIN_FIX = (
    "SKIN FIX (mandatory): remove dark circles and spots under eyes, "
    "blemishes, acne, pigmentation, redness, enlarged pores. "
    "Even out skin tone, add healthy glow. Keep realistic texture — "
    "no plastic or airbrushed look."
)

REALISM = (
    "PHOTOREALISM: must look like a real high-end photograph. "
    "No AI artifacts, no painterly effects, no unnatural glow. "
    "Natural skin texture, realistic lighting on skin and clothes."
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
        f"Enhance this existing photo for a dating profile. "
        f"Do NOT generate a new person — improve the SAME person in the photo. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {SKIN_FIX} {p} "
        f"Brighten eye whites, subtle iris enhancement. "
        f"Soft flattering golden-hour lighting. {s} {REALISM}"
    )


def build_cv_prompt(style: str = "") -> str:
    s = CV_STYLES.get(style, CV_STYLES["corporate"])
    p = CV_PERSONALITIES.get(style, CV_PERSONALITIES["corporate"])
    return (
        f"Enhance this existing photo into a professional headshot. "
        f"Do NOT generate a new person — improve the SAME person in the photo. "
        f"Keep the person's body, posture, and proportions exactly unchanged. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {SKIN_FIX} {p} "
        f"Studio catchlights in eyes. Hair groomed. Even soft lighting. "
        f"{s} {REALISM}"
    )


def build_social_prompt(style: str = "") -> str:
    s = SOCIAL_STYLES.get(style, SOCIAL_STYLES["influencer"])
    p = SOCIAL_PERSONALITIES.get(style, SOCIAL_PERSONALITIES["influencer"])
    return (
        f"Enhance this existing photo for social media. "
        f"Do NOT generate a new person — improve the SAME person in the photo. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {SKIN_FIX} {p} "
        f"Vibrant colors, modern aesthetic, crisp detail. "
        f"{s} {REALISM}"
    )


STEP_TEMPLATES: dict[str, str] = {
    "background_edit": (
        "Enhance this existing photo — change ONLY the background: {description}. "
        "Keep the person, clothing, pose, and body proportions exactly as they are. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {REALISM}"
    ),
    "clothing_edit": (
        "Enhance this existing photo — adjust ONLY the clothing/outfit: {description}. "
        "Keep face, background, pose, and body proportions unchanged. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {REALISM}"
    ),
    "lighting_adjust": (
        "Enhance this existing photo — improve ONLY the lighting and color grading: "
        "{description}. Natural studio quality, even skin tones. "
        "Keep body, pose, and proportions unchanged. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {REALISM}"
    ),
    "expression_hint": (
        "Enhance this existing photo — subtle expression adjustment: {description}. "
        "Keep identity, do not change face shape or features. "
        "Do NOT modify teeth or add smile. Keep original mouth. "
        "Keep body pose and proportions unchanged. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {SKIN_FIX} {REALISM}"
    ),
    "skin_correction": (
        "Enhance this existing photo — minor skin tone correction and blemish removal. "
        "Keep all facial features exactly the same. No plastic look. "
        "Keep body pose and proportions unchanged. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {SKIN_FIX} {REALISM}"
    ),
    "style_overall": (
        "Enhance this existing photo — apply overall style enhancement: {description}. "
        "Vibrant modern aesthetic, crisp detail. "
        "Keep body proportions and pose unchanged. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {REALISM}"
    ),
}


ENHANCEMENT_LEVEL_MODIFIERS: dict[int, str] = {
    1: "Apply subtle, minimal changes. Focus only on lighting and skin tone. Strength: very light.",
    2: "Apply moderate enhancement. Improve background and clothing while keeping natural look. Strength: medium.",
    3: "Apply noticeable enhancement. Include expression refinement and styling. Strength: confident.",
    4: "Apply full style transformation. Complete look overhaul with strong aesthetic. Strength: full.",
}


def build_step_prompt(
    step_template: str,
    style: str,
    mode_styles: dict[str, str] | None = None,
    enhancement_level: int = 0,
) -> str:
    """Build a prompt for a single pipeline step, filling {description} from style dicts."""
    template = STEP_TEMPLATES.get(step_template, STEP_TEMPLATES.get("style_overall", ""))
    description = ""
    if mode_styles:
        description = mode_styles.get(style, next(iter(mode_styles.values()), ""))
    prompt = template.replace("{description}", description)
    if enhancement_level and enhancement_level in ENHANCEMENT_LEVEL_MODIFIERS:
        prompt += " " + ENHANCEMENT_LEVEL_MODIFIERS[enhancement_level]
    return prompt


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
