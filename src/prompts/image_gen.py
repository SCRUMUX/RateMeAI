"""Centralized image-generation prompt builder for all modes.

Every prompt includes three mandatory blocks applied in order:
1. FACE_ANCHOR — locks facial geometry to the reference.
2. DEFECT_CORRECTION — removes skin artifacts while keeping texture.
3. SKIN_ENHANCE — overall skin improvement.

These blocks MUST appear in every dating/CV prompt. Emoji uses a
simplified version since it is cartoon-style.
"""
from __future__ import annotations

FACE_ANCHOR = (
    "ABSOLUTE IDENTITY PRESERVATION (highest priority): "
    "the person's face shape, nose bridge, nostril shape, eye shape, "
    "eye spacing, eyebrow arch, lip fullness, lip shape, jawline angle, "
    "chin shape, ear shape, forehead height, cheekbone position, and "
    "overall bone structure MUST remain identical to the reference photo. "
    "Do NOT reshape, enlarge, reduce, or reposition ANY facial feature. "
    "Do NOT change the face proportions or symmetry beyond what exists in the original. "
    "The person must be INSTANTLY and UNMISTAKABLY recognizable as the same individual."
)

DEFECT_CORRECTION = (
    "MANDATORY DEFECT CORRECTION (apply to every generation): "
    "Carefully scan the entire face area for skin imperfections and correct them: "
    "1) Under-eye area: remove dark circles, bags, spots, discoloration patches, "
    "   and any visible capillaries or pigmentation irregularities beneath the eyes. "
    "2) Skin blemishes: remove acne, pimples, blackheads, whiteheads, and acne scars. "
    "3) Spots and marks: remove age spots, sun spots, birthmarks that appear as defects, "
    "   uneven pigmentation patches, and any redness or blotchiness. "
    "4) Texture issues: smooth visible enlarged pores, reduce rough skin patches, "
    "   minimize fine lines around eyes and forehead while keeping natural skin texture. "
    "5) Facial hair cleanup: remove stray facial hairs, clean up eyebrow edges naturally. "
    "CRITICAL: all corrections must be SUBTLE and INVISIBLE — the skin must look "
    "naturally healthy, not airbrushed or plastic. Preserve natural skin texture, "
    "pore patterns, and micro-details. The result should look like the person on their "
    "BEST day with perfect lighting, not like a retouched magazine cover."
)

SKIN_ENHANCE = (
    "SKIN ENHANCEMENT: even out overall skin tone to a healthy uniform complexion. "
    "Add a subtle natural glow that suggests good health and hydration. "
    "Gently reduce wrinkle depth (NOT remove — just soften). "
    "Improve skin luminosity, especially on cheekbones and forehead. "
    "Ensure the transition between corrected and uncorrected areas is seamless. "
    "The final skin must pass the 'zoom test' — no visible editing artifacts "
    "at any zoom level. No plastic look, no airbrushed feel, no loss of skin texture."
)

PHOTOREALISM_ANCHOR = (
    "PHOTOREALISM REQUIREMENT: the final image must be indistinguishable from "
    "a real photograph taken by a professional photographer with a high-end camera. "
    "No painterly effects, no AI artifacts, no uncanny smoothness, no cartoon-like "
    "features, no unnatural glow or halo around hair/face edges. "
    "Lighting must be physically plausible. Shadows must be consistent. "
    "Hair strands, eyelashes, and fabric textures must look real."
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
        "APPROACH: enhance the existing person, do NOT create a new face. "
        f"{FACE_ANCHOR} "
        f"{DEFECT_CORRECTION} "
        f"{SKIN_ENHANCE} "
        f"{personality} "
        "Eyes: brighten the whites of the eyes, subtly enhance iris color and add "
        "natural catchlights. Remove any redness in the sclera. "
        "Teeth: if visible, whiten subtly — no Hollywood-white, just clean and natural. "
        "Hair: keep the exact hairstyle, color, and texture — just add subtle shine and "
        "fix any flyaway strands. "
        "Improve lighting to soft, flattering, directional golden-hour quality. "
        f"{style_block} "
        f"{PHOTOREALISM_ANCHOR}"
    )


def build_cv_prompt(style: str = "") -> str:
    style_block = CV_STYLES.get(style, CV_STYLES["corporate"])
    personality = CV_PERSONALITIES.get(style, CV_PERSONALITIES["corporate"])
    return (
        "Transform this portrait into a professional corporate headshot. "
        "APPROACH: enhance the existing person, do NOT create a new face. "
        f"{FACE_ANCHOR} "
        f"{DEFECT_CORRECTION} "
        f"{SKIN_ENHANCE} "
        f"{personality} "
        "Eyes: add professional studio catchlights, ensure whites are clean. "
        "Remove any redness. "
        "Teeth: if visible, clean and brighten naturally. "
        "Hair: maintain exact style and color, ensure it looks groomed and polished. "
        "Improve lighting to even, soft studio quality with controlled shadows. "
        f"{style_block} "
        f"{PHOTOREALISM_ANCHOR}"
    )


def build_emoji_prompt(base_description: str = "") -> str:
    prompt = (
        "Cartoon sticker avatar of the person from <ref>0</ref>. "
        "Keep recognizable facial proportions, face shape, hairstyle and hair color. "
        "Clean up any visible skin defects in the cartoon style — no spots or blemishes "
        "should be visible even in stylized form. "
        "Bold outlines, flat vibrant colors, friendly expression, square composition."
    )
    desc = base_description[:400]
    if desc:
        prompt = f"{prompt} Character: {desc}"
    return prompt
