"""Centralized image-generation prompt builder for all modes.

Prompt structure follows the Change -> Preserve -> Quality pattern
proven to achieve 91% first-attempt success in edit-mode models.
Constants use positive framing to avoid diffusion "NO Syndrome".
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Core anchors — positive framing, no negation overload
# ---------------------------------------------------------------------------

FACE_ANCHOR = (
    "FACE IDENTITY: keep exact bone structure, nose shape, eye shape and "
    "spacing, eyebrow shape, lip shape, jawline, chin, ears, cheekbones, "
    "forehead proportions. Same face as reference, instantly recognizable. "
    "Keep original mouth expression and teeth exactly as-is."
)

BODY_ANCHOR = (
    "BODY: keep original body proportions, head-to-body ratio, shoulder "
    "width, pose, hand positions. Hands: exactly 5 fingers, natural joints."
)

SKIN_FIX = (
    "SKIN: visible pores, natural texture, subtle imperfections, "
    "subsurface scattering on ears and cheeks, healthy glow, even tone. "
    "Remove only blemishes, dark circles, and acne."
)

CAMERA = (
    "Shot on Canon EOS R5, 85mm f/1.8, shallow depth of field. "
    "Natural color grading, Kodak Portra 400 tones."
)

REALISM = (
    "Raw photograph aesthetic, real skin pores, natural grain. "
    "Professional studio-quality image indistinguishable from a real photo."
)

# ---------------------------------------------------------------------------
# Style dictionaries — enriched with materials, textures, lighting
# ---------------------------------------------------------------------------

DATING_STYLES: dict[str, str] = {
    "warm_outdoor": (
        "Background: golden-hour park or waterfront, warm backlight with "
        "soft rim light, creamy bokeh, natural green and water textures. "
        "Clothing: stylish casual, fitted, clean fabrics."
    ),
    "studio_elegant": (
        "Background: studio with soft gradient lighting, charcoal-to-warm-grey "
        "backdrop, subtle vignette. "
        "Clothing: elegant evening wear, dark tones, silk or fine wool textures."
    ),
    "cafe": (
        "Background: cozy upscale cafe, warm tungsten light, exposed brick or "
        "wood paneling, blurred bottles and candles in background. "
        "Clothing: smart-casual date outfit, earth tones, linen or cotton."
    ),
}

DATING_PERSONALITIES: dict[str, str] = {
    "warm_outdoor": "Soft relaxed eyes, warm approachable look, gentle natural expression.",
    "studio_elegant": "Strong direct gaze, squared shoulders, calm self-assured energy.",
    "cafe": "Bright engaging eyes, magnetic energy, open relaxed posture.",
}

CV_STYLES: dict[str, str] = {
    "corporate": (
        "Background: modern corner office, floor-to-ceiling windows with soft "
        "diffused daylight, neutral beige wall, clean minimalist interior. "
        "Clothing: tailored formal suit, crisp white shirt, subtle tie or scarf."
    ),
    "creative": (
        "Background: bright creative workspace, whiteboard or bookshelf slightly "
        "out of focus, warm ambient light. "
        "Clothing: smart-casual blazer over fitted shirt, relaxed professional."
    ),
    "neutral": (
        "Background: light-grey studio backdrop, even soft lighting from both sides, "
        "clean and distraction-free. "
        "Clothing: classic professional attire, solid neutral colors."
    ),
}

CV_PERSONALITIES: dict[str, str] = {
    "corporate": "Composed, trustworthy expression, professional confidence.",
    "creative": "Bold, expressive, artistic energy with confident posture.",
    "neutral": "Relaxed, approachable, open and friendly gaze.",
}

SOCIAL_STYLES: dict[str, str] = {
    "influencer": (
        "Background: trendy urban rooftop at golden hour, city skyline bokeh, "
        "warm directional light with lens flare. "
        "Clothing: stylish streetwear, statement accessories, layered textures."
    ),
    "luxury": (
        "Background: upscale lounge with marble surfaces, soft amber ambient "
        "light, velvet and brass details blurred behind. "
        "Clothing: designer outfit, fine fabrics, watches or minimal jewelry."
    ),
    "casual": (
        "Background: sunlit park with dappled tree shadows, or bright airy "
        "home interior with natural window light. "
        "Clothing: relaxed casual wear, natural cotton and linen fabrics."
    ),
    "artistic": (
        "Background: art gallery with textured walls, or vivid mural, "
        "dramatic side lighting with deep shadows. "
        "Clothing: eclectic artistic mix, bold colors, unique layering."
    ),
}

SOCIAL_PERSONALITIES: dict[str, str] = {
    "influencer": "Bright confident look, engaging direct eye contact, charismatic energy.",
    "luxury": "Elegant poise, mysterious allure, sophisticated calm expression.",
    "casual": "Genuine relaxed look, warm natural feel, approachable open vibe.",
    "artistic": "Thoughtful creative gaze, expressive intensity, unconventional character.",
}


# ---------------------------------------------------------------------------
# Prompt builders — Change -> Preserve -> Quality order
# ---------------------------------------------------------------------------

def build_dating_prompt(style: str = "") -> str:
    s = DATING_STYLES.get(style, DATING_STYLES["warm_outdoor"])
    p = DATING_PERSONALITIES.get(style, DATING_PERSONALITIES["warm_outdoor"])
    return (
        f"Enhance into a dating profile photo. "
        f"Change background, lighting, and clothing style. "
        f"Brighten eye whites subtly, add soft flattering golden-hour light. "
        f"{s} {p} "
        f"{FACE_ANCHOR} {BODY_ANCHOR} "
        f"{SKIN_FIX} {CAMERA} {REALISM}"
    )


def build_cv_prompt(style: str = "") -> str:
    s = CV_STYLES.get(style, CV_STYLES["corporate"])
    p = CV_PERSONALITIES.get(style, CV_PERSONALITIES["corporate"])
    return (
        f"Enhance into a professional headshot. "
        f"Change background to studio or office, clothing to professional attire, "
        f"add even soft studio lighting, groom hair neatly, add catchlights in eyes. "
        f"{s} {p} "
        f"{FACE_ANCHOR} {BODY_ANCHOR} "
        f"{SKIN_FIX} {CAMERA} {REALISM}"
    )


def build_social_prompt(style: str = "") -> str:
    s = SOCIAL_STYLES.get(style, SOCIAL_STYLES["influencer"])
    p = SOCIAL_PERSONALITIES.get(style, SOCIAL_PERSONALITIES["influencer"])
    return (
        f"Enhance into a social media photo. "
        f"Change background, lighting, colors, and clothing per style. "
        f"Vibrant modern aesthetic, crisp detail. "
        f"{s} {p} "
        f"{FACE_ANCHOR} {BODY_ANCHOR} "
        f"{SKIN_FIX} {CAMERA} {REALISM}"
    )


# ---------------------------------------------------------------------------
# Multi-pass step templates — same Change -> Preserve -> Quality order
# ---------------------------------------------------------------------------

STEP_TEMPLATES: dict[str, str] = {
    "background_edit": (
        "Change ONLY the background: {description}. "
        "Keep the person, clothing, pose, and body proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {CAMERA} {REALISM}"
    ),
    "clothing_edit": (
        "Change ONLY the clothing and outfit: {description}. "
        "Keep face, background, pose, and body proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {CAMERA} {REALISM}"
    ),
    "lighting_adjust": (
        "Improve ONLY the lighting and color grading: {description}. "
        "Natural studio quality, even skin tones. "
        "Keep body, pose, and proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {CAMERA} {REALISM}"
    ),
    "expression_hint": (
        "Subtle expression adjustment: {description}. "
        "Keep face shape, features, and original mouth identical. "
        "Keep body pose and proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {SKIN_FIX} {CAMERA} {REALISM}"
    ),
    "skin_correction": (
        "Minor skin tone correction and blemish removal. "
        "Keep all facial features identical. "
        "Keep body pose and proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {SKIN_FIX} {CAMERA} {REALISM}"
    ),
    "style_overall": (
        "Apply overall style enhancement: {description}. "
        "Vibrant modern aesthetic, crisp detail. "
        "Keep body proportions and pose identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {CAMERA} {REALISM}"
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
