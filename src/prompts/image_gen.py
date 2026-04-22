"""Centralized image-generation prompt builder for all modes.

Compact photorealistic template (v1.13): a single natural paragraph in
the 800–1200 character budget. The Reve REST API rejects oversized or
overstuffed prompts, and tag-sectioned layouts ([CHANGE]/[PRESERVE]/
[QUALITY]) waste characters without improving adherence. Two short
anchors — PRESERVE_PHOTO and QUALITY_PHOTO — cover the semantics that
previously required 10+ individual constants.
"""
from __future__ import annotations

import logging

from src.prompts.style_spec import (
    OutputAspect,
    StyleRegistry,
    StyleSpec,
    StyleVariant,
    build_spec_from_legacy,
)
from src.prompts.style_variants import STYLE_VARIANTS

logger = logging.getLogger(__name__)

# Hard cap — worker logs a warning and truncates anything above this
# before handing off to Reve. Matches the test budget in
# tests/test_prompts/test_prompt_length_budget.py.
PROMPT_MAX_LEN = 1200


# ---------------------------------------------------------------------------
# Output size resolver — aspect preset → concrete {width, height} for FAL.
# ---------------------------------------------------------------------------

# Pixel sizes per aspect. Every non-square bucket is ≈2 MP (dimensions are
# multiples of 16 for stable FLUX.2 Pro Edit inference); ``square_hd`` is
# the 1 MP document bucket. The FLUX.2 API accepts these verbatim as a
# ``{"width": W, "height": H}`` object — passing the custom shape instead
# of the preset enum gives us the exact pixel count we want rather than
# whatever the model chooses for the preset name.
_ASPECT_PIXEL_SIZE: dict[str, tuple[int, int]] = {
    "square_hd":       (1024, 1024),
    "portrait_4_3":    (1280, 1600),
    "portrait_16_9":   (1088, 1920),
    "landscape_4_3":   (1600, 1280),
    "landscape_16_9":  (1920, 1088),
}


def resolve_output_size(
    spec: StyleSpec | None,
    face_area_ratio: float | None = None,
) -> dict[str, int] | None:
    """Translate a style's ``output_aspect`` into a FAL ``image_size`` dict.

    Returns ``None`` when the spec is missing — callers should fall back to
    the provider's configured default (``portrait_4_3`` in production).

    v1.17 adaptive sizing: for ``needs_full_body`` styles with a tiny
    reference face (``face_area_ratio < 0.10``) we force the output
    down to 1 MP ``square_hd``. At 2 MP FLUX.2 Pro Edit distributes its
    "attention budget" across the full-body scene and the face ends up
    soft; at 1 MP the model has to prioritise facial detail, and
    Real-ESRGAN (or the LANCZOS fallback) restores the output
    resolution after the fact. The knob is strictly opt-in — passing
    ``face_area_ratio=None`` (legacy callers and tests) keeps the
    previous 2 MP portrait behaviour unchanged.
    """
    if spec is None:
        return None
    aspect: OutputAspect = getattr(spec, "output_aspect", "portrait_4_3")

    needs_full_body = bool(getattr(spec, "needs_full_body", False))
    if (
        needs_full_body
        and face_area_ratio is not None
        and face_area_ratio > 0.0
        and face_area_ratio < 0.10
    ):
        aspect = "square_hd"
        logger.info(
            "adaptive image_size: full-body style with small face "
            "(%.3f) → square_hd 1 MP",
            face_area_ratio,
        )

    pixels = _ASPECT_PIXEL_SIZE.get(aspect)
    if pixels is None:
        pixels = _ASPECT_PIXEL_SIZE["portrait_4_3"]
    w, h = pixels
    return {"width": w, "height": h}


# ---------------------------------------------------------------------------
# Compact anchors — one PRESERVE phrase + one QUALITY phrase.
# ---------------------------------------------------------------------------

PRESERVE_PHOTO = (
    "Preserve the exact same person from the reference photo — unmistakably "
    "recognizable as the same individual: identical face (bone structure, "
    "eye shape and color, nose, mouth, jawline, ears, hairline, hair color "
    "and parting), identical skin tone and undertone with the same natural "
    "pores and micro-asymmetry, same head-to-shoulders proportion and neck "
    "length, original pose and body proportions, hair silhouette crisp "
    "against the new background, hands with exactly five clearly separated "
    "fingers."
)

# Body-change variant: the target scene (yoga mat, beach, running track,
# etc.) inherently requires a different pose from the reference, so we must
# NOT ask FLUX to keep the original pose/framing — that contradictory signal
# is exactly what produced the disfigured "yoga_outdoor" results in
# production. Identity (face, hair, skin) is still pinned.
#
# v1.17: tightened identity anchors (eye shape and color, micro-asymmetry,
# "unmistakably the same individual") and dropped the earlier "natural
# full-body pose fitting the scene" phrasing, which gave FLUX too much
# licence to reinterpret the body. A simple "body pose fitting the new
# scene" lets the scene description drive the pose without inviting a
# plastic rewrite.
PRESERVE_PHOTO_FACE_ONLY = (
    "Preserve the exact same person's identity from the reference photo — "
    "unmistakably the same individual: identical face (bone structure, eye "
    "shape and color, nose, mouth, jawline, ears, hairline, hair color and "
    "parting), identical skin tone with the same natural pores and "
    "micro-asymmetry, same age and gender, same head-to-shoulders "
    "proportion, hair silhouette crisp. Render a body pose fitting the new "
    "scene with realistic body proportions, hands with five clearly "
    "separated fingers."
)

# Short identity-lock suffix appended at the very end of every non-emoji
# prompt. Kept under 80 chars so it rarely trips the 1200 PROMPT_MAX_LEN
# budget; positive-framing only so it passes the regression guard in
# tests/test_prompts/test_positive_framing.py. Acts as a final anchor
# for FLUX.2 Pro Edit — empirically repeating "same person as the
# reference" once more at the tail improves prompt adherence on borderline
# identity cases without extra cost.
IDENTITY_LOCK_SUFFIX = (
    "Final anchor: the output must remain the same individual as the "
    "reference photo."
)

QUALITY_PHOTO = (
    "Photorealistic unedited photograph, entire scene sharp from subject to "
    "background with textures and distant objects crisp and legible, natural "
    "true-to-life colors, even realistic lighting, deep field of focus, "
    "genuine relaxed expression, authentic skin texture."
)

DOC_PRESERVE = (
    "Preserve the exact same person from the reference photo: identical face "
    "(bone structure, eyes, nose, mouth, hairline, ear position), identical "
    "skin tone with natural pores, same hair color and length, same head "
    "shape and head-to-shoulders proportion."
)

DOC_QUALITY = (
    "Photorealistic ID-style headshot, soft even frontal studio light, clean "
    "backdrop with minimal residual shadow, true-to-life skin tones, "
    "authentic skin texture, sharp detail across the face, balanced natural "
    "color."
)

# ---------------------------------------------------------------------------
# Style dictionaries — enriched with materials, textures, lighting
# ---------------------------------------------------------------------------

DATING_STYLES: dict[str, str] = {
    # --- Lifestyle ---
    "warm_outdoor": (
        "Background: golden-hour park or waterfront, warm backlight with "
        "subtle rim light, natural green and water textures visible in background. "
        "Clothing: stylish casual, fitted, clean fabrics."
    ),
    "studio_elegant": (
        "Background: studio with smooth gradient lighting, charcoal-to-warm-grey "
        "backdrop, clean even studio falloff. "
        "Clothing: elegant evening wear, dark tones, silk or fine wool textures."
    ),
    "near_car": (
        "Background: luxury sedan or sports car parked on sunlit city boulevard, "
        "warm golden reflections on polished paint, urban architecture visible behind. "
        "Clothing: fitted dark jeans, crisp white crew-neck t-shirt, leather watch, "
        "aviator sunglasses pushed up on head."
    ),
    "in_car": (
        "Background: interior of modern car, diffused window light streaming through "
        "windshield, leather steering wheel and dashboard visible. "
        "Clothing: casual button-down shirt with rolled sleeves, subtle wrist accessory."
    ),
    "motorcycle": (
        "Background: matte-black motorcycle parked on empty road at golden hour, "
        "open landscape behind, warm rim light. "
        "Clothing: fitted leather jacket over plain tee, dark denim, motorcycle boots."
    ),
    "yacht": (
        "Background: yacht deck with turquoise sea, white railings, clear blue sky, "
        "sparkling water reflections. "
        "Clothing: white linen shirt unbuttoned at top, navy shorts or chinos, deck shoes."
    ),
    "rooftop_city": (
        "Background: rooftop terrace at blue hour, city skyline rendered in sharp legible detail with warm lights, "
        "modern glass railing, ambient string lights. "
        "Clothing: dark fitted blazer over black tee, tailored trousers, minimalist watch."
    ),
    # --- Sport / Active ---
    "gym_fitness": (
        "Background: modern gym with matte equipment, even overhead lighting, "
        "mirrors in background. "
        "Clothing: fitted athletic tank top or compression shirt, athletic shorts, training shoes."
    ),
    "running": (
        "Background: tree-lined park path at early morning, diffused golden light, "
        "green foliage with dew. "
        "Clothing: lightweight running shirt, athletic shorts, running shoes, sport watch."
    ),
    "tennis": (
        "Background: outdoor tennis court, warm afternoon light, green court surface, "
        "net visible behind. "
        "Clothing: fitted polo shirt, tennis shorts, wristband, clean white sneakers."
    ),
    "swimming_pool": (
        "Background: infinity pool edge with blue water, palm trees, resort setting, "
        "bright daylight with sparkling reflections. "
        "Clothing: fitted swim trunks, athletic build, optional sunglasses in hand."
    ),
    "hiking": (
        "Background: mountain trail with panoramic valley view at golden hour, "
        "rocky terrain, dramatic sky with warm clouds. "
        "Clothing: fitted outdoor jacket or fleece, hiking pants, backpack straps visible."
    ),
    # --- Atmosphere ---
    "cafe": (
        "Background: cozy upscale cafe, warm tungsten light, exposed brick or "
        "wood paneling, bottles and candles in background. "
        "Clothing: smart-casual date outfit, earth tones, linen or cotton."
    ),
    "coffee_date": (
        "Background: upscale third-wave coffee shop, warm tungsten lighting, "
        "exposed wood shelving, latte art on table. "
        "Clothing: soft knit sweater or henley, dark jeans, clean casual style."
    ),
    "restaurant": (
        "Background: upscale restaurant, warm candlelight with clear interior details, dark wood and white linen, "
        "wine glass on table. "
        "Clothing: tailored dark shirt or blazer, smart evening look, subtle accessories."
    ),
    "bar_lounge": (
        "Background: modern cocktail lounge, amber and teal lighting, clear interior details, "
        "bar shelves with bottles in background. "
        "Clothing: dark fitted shirt, sleeves rolled, leather or fabric watch."
    ),
    "cooking": (
        "Background: bright modern kitchen, natural window light, marble countertop, "
        "fresh ingredients and herbs visible. "
        "Clothing: clean apron over casual shirt, rolled sleeves, natural domestic setting."
    ),
    "dog_lover": (
        "Background: sunlit park with green grass and trees, warm golden backlight, "
        "open natural landscape. "
        "Clothing: relaxed casual outfit, fitted jeans, comfortable cotton shirt."
    ),
    # --- Travel / Culture ---
    "travel": (
        "Background: modern airport terminal or departure lounge, large windows with "
        "aircraft visible, clean bright interior. "
        "Clothing: travel-smart outfit, fitted jacket, comfortable trousers, carry-on bag nearby."
    ),
    "beach_sunset": (
        "Background: tropical beach at golden sunset, warm orange-pink sky, gentle waves, "
        "wet sand reflections. "
        "Clothing: unbuttoned linen shirt over tee, rolled chinos or shorts, bare feet."
    ),
    "art_gallery": (
        "Background: contemporary art gallery, white walls with large paintings visible, "
        "track lighting creating directional light. "
        "Clothing: smart turtleneck or fitted dark shirt, tailored trousers, minimalist style."
    ),
    "street_urban": (
        "Background: vibrant city street with graffiti walls, modern architecture, "
        "warm directional sunlight creating long shadows. "
        "Clothing: streetwear layers, bomber or denim jacket, fitted pants, clean sneakers."
    ),
    "concert": (
        "Background: intimate music venue or home setting with guitar or instruments visible, "
        "warm moody lighting, exposed brick or wood. "
        "Clothing: vintage band tee or flannel shirt, relaxed creative style."
    ),
    # --- Landmarks ---
    "paris_eiffel": (
        "Background: Parisian boulevard with Eiffel Tower landmark visible in sharp detail, "
        "morning golden light, cafe table with croissant and coffee visible. "
        "Clothing: fitted navy blazer over white tee, dark jeans, clean white sneakers."
    ),
    "nyc_brooklyn_bridge": (
        "Background: Brooklyn Bridge walkway at golden sunset, warm orange sky, "
        "Manhattan skyline visible behind. "
        "Clothing: casual fitted jacket, dark jeans, comfortable walking shoes."
    ),
    "rome_colosseum": (
        "Background: outdoor cafe terrace with Colosseum landmark visible in sharp detail, "
        "warm Mediterranean afternoon light, cobblestone street visible. "
        "Clothing: linen shirt, light chinos, leather loafers, relaxed Italian style."
    ),
    "dubai_burj_khalifa": (
        "Background: modern Dubai boulevard with Burj Khalifa landmark illuminated at blue hour, "
        "glass reflections, warm amber city lights, luxury urban atmosphere. "
        "Clothing: fitted dark shirt, tailored trousers, luxury watch, polished modern style."
    ),
    "nyc_times_square": (
        "Background: Times Square with vibrant billboards and neon lights, "
        "bustling atmosphere, sharp vibrant night street scene with teal and magenta neon reflections on pavement. "
        "Clothing: streetwear layers, statement jacket, fitted dark pants, designer sneakers."
    ),
    "barcelona_sagrada": (
        "Background: sunlit Barcelona terrace with Sagrada Familia landmark visible in sharp detail, "
        "warm morning light, breakfast table with juice and pastries. "
        "Clothing: relaxed summer shirt, light chinos, straw hat, Mediterranean casual."
    ),
    "london_eye": (
        "Background: Thames embankment with London Eye in background, "
        "grey-blue London sky with golden patches, river reflections. "
        "Clothing: tailored overcoat or trench, dark scarf, smart casual British layers."
    ),
    "sydney_opera": (
        "Background: Sydney harbour with Opera House sails landmark visible in sharp detail, "
        "sparkling blue water, bright Australian daylight. "
        "Clothing: casual smart outfit, fitted polo or button-down, clean summer style."
    ),
    "tokyo_tower": (
        "Background: minimalist Tokyo street with Tokyo Tower in background, "
        "cherry blossoms or clean urban aesthetic, diffused light. "
        "Clothing: minimal Japanese-inspired outfit, clean dark fitted layers."
    ),
    "sf_golden_gate": (
        "Background: Golden Gate Bridge landmark at sunset with fog rolling in, "
        "warm orange and teal tones, Pacific Ocean behind. "
        "Clothing: fitted fleece or casual jacket, dark jeans, relaxed outdoor-casual style."
    ),
    "athens_acropolis": (
        "Background: narrow Athens street with Acropolis landmark on hilltop in warm light, "
        "whitewashed walls, Mediterranean plants and bougainvillea. "
        "Clothing: relaxed white linen shirt, light trousers, leather sandals."
    ),
    "singapore_marina_bay": (
        "Background: Marina Bay Sands and Singapore skyline at night, "
        "illuminated reflections on water, modern futuristic architecture. "
        "Clothing: smart fitted shirt, tailored dark trousers, polished modern shoes."
    ),
    "venice_san_marco": (
        "Background: Piazza San Marco at golden hour, historic Venetian architecture, "
        "warm amber light, canal water reflections in distance. "
        "Clothing: elegant smart-casual, fitted blazer, quality leather shoes, refined style."
    ),
    "nyc_central_park": (
        "Background: Central Park with autumn foliage in warm tones, "
        "dappled sunlight through trees, green lawns and pathway. "
        "Clothing: casual fitted sweater, dark jeans, clean casual sneakers."
    ),
    "london_big_ben": (
        "Background: Westminster with Big Ben landmark visible in sharp detail, "
        "classic London overcast light, Thames embankment visible. "
        "Clothing: classic British smart-casual, tailored jacket, polished accessories."
    ),
    # --- Travel expanded ---
    "airplane_window": (
        "Background: airplane window seat with clouds and blue sky visible outside, "
        "dim cabin light, tray table with book or headphones. "
        "Clothing: comfortable travel outfit, quality hoodie or fitted sweater, headphones."
    ),
    "train_journey": (
        "Background: modern train interior, green landscape streaming by window, "
        "laptop on tray table, earbuds, warm natural light from window. "
        "Clothing: smart-casual travel outfit, fitted jacket, comfortable layers."
    ),
    "hotel_checkin": (
        "Background: luxury hotel lobby with marble floor, warm amber ambient lighting, "
        "modern reception area visible, luggage nearby. "
        "Clothing: travel-smart outfit, fitted blazer or quality jacket, polished casual look."
    ),
    "hotel_breakfast": (
        "Background: hotel restaurant with panoramic floor-to-ceiling windows, "
        "city or sea view, elegant breakfast table setting with fresh food. "
        "Clothing: clean casual morning outfit, quality polo or light linen shirt."
    ),
    "sea_balcony": (
        "Background: hotel or villa balcony overlooking turquoise sea, "
        "white railing, bright morning light, blue sky, tropical plants. "
        "Clothing: relaxed morning linen outfit, light cotton, fresh natural look."
    ),
    "old_town_walk": (
        "Background: charming European old-town cobblestone street, "
        "colorful facades, warm afternoon light, flower boxes on windows. "
        "Clothing: relaxed stylish outfit, light layers, comfortable leather shoes."
    ),
    "street_market": (
        "Background: vibrant outdoor street market with colorful produce and goods, "
        "warm natural light, exotic textures, bustling atmosphere. "
        "Clothing: casual travel outfit, rolled sleeves, crossbody bag, explorer vibe."
    ),
    # --- Atmosphere expanded ---
    "rainy_day": (
        "Background: city street in light rain, wet reflections on pavement, "
        "moody atmospheric light, glass surface with droplets, grey sky. "
        "Clothing: dark fitted coat or jacket, quality umbrella, polished rainy-day style."
    ),
    "night_coffee": (
        "Background: cozy late-night coffee shop interior, warm tungsten lighting, interior clearly visible, "
        "city lights through window, steaming cup on table. "
        "Clothing: dark cozy layers, quality cashmere sweater or fitted dark shirt."
    ),
    "evening_home": (
        "Background: modern apartment with warm ambient lamp lighting, "
        "city view through large window, comfortable interior, book or drink nearby. "
        "Clothing: clean quality loungewear, fitted casual pieces, relaxed domestic style."
    ),
    # --- Status ---
    "car_exit": (
        "Background: stepping out of luxury car, door open, city backdrop, "
        "natural light catching the scene, polished car interior visible. "
        "Clothing: tailored smart outfit, polished shoes, clean confident style."
    ),
    "travel_luxury": (
        "Background: first-class airport lounge or luxury resort entrance, "
        "marble and brass details, warm ambient lighting, premium interior. "
        "Clothing: elevated travel outfit, quality fabrics, leather accessories, luxury watch."
    ),
    # --- Sport expanded ---
    "yoga_outdoor": (
        "Background: outdoor yoga mat on green grass or beach at sunrise, "
        "gentle morning golden light, serene natural landscape, calm atmosphere. "
        "Clothing: fitted clean athletic wear, barefoot, minimal yoga outfit."
    ),
    "cycling": (
        "Background: scenic road or park trail with bicycle nearby, "
        "golden morning light, green landscape, open sky. "
        "Clothing: fitted cycling jersey or casual athletic top, sport sunglasses, helmet nearby."
    ),
    "tinder_pack_rooftop_golden": (
        "Background: urban rooftop terrace at golden hour, warm rim light on skyline, "
        "distant city lights clearly visible across skyline, romantic open-air atmosphere. "
        "Clothing: fitted casual-smart outfit, clean lines, subtle accessories, date-ready polish."
    ),
    "tinder_pack_minimal_studio": (
        "Background: pure neutral studio backdrop soft grey-to-white gradient, "
        "even beauty-dish lighting, empty backdrop area, clean studio setup with backdrop fully visible. "
        "Clothing: simple fitted top in solid color, minimal jewelry, fresh grooming."
    ),
    "tinder_pack_cafe_window": (
        "Background: bright cafe interior by large window, natural daylight, "
        "plants and warm wood tones visible behind, details preserved. "
        "Clothing: relaxed smart-casual, soft sweater or crisp shirt, approachable style."
    ),
}

DATING_PERSONALITIES: dict[str, str] = {
    "warm_outdoor": "Soft relaxed eyes, warm approachable look, gentle natural expression.",
    "studio_elegant": "Strong direct gaze, calm self-assured eyes, confident closed-mouth expression.",
    "near_car": "Direct assured gaze, subtle half-smile, relaxed brow and steady mouth.",
    "in_car": "Warm natural smile, easy eye crinkles, relaxed expression.",
    "motorcycle": "Strong direct gaze, calm rugged brow, bold closed-mouth line.",
    "yacht": "Wind-touched hair, warm bright smile, open carefree eyes.",
    "rooftop_city": "Composed sophisticated gaze, subtle confident smile, polished still mouth.",
    "gym_fitness": "Healthy glow, energetic direct look, determined confident expression.",
    "running": "Fresh alert eyes, bright forward gaze, healthy athletic glow.",
    "tennis": "Confident sporty smile, sun-kissed healthy look, focused ready stance.",
    "swimming_pool": "Natural tanned skin, warm easy smile, soft relaxed eyes.",
    "hiking": "Accomplished peaceful expression, adventurous bright-eyed open gaze.",
    "cafe": "Bright engaging eyes, raised eyebrow warmth, relaxed warm expression.",
    "coffee_date": "Gentle attentive smile, warm inviting eye contact, soft brow.",
    "restaurant": "Charming engaged expression, sophisticated relaxed mouth, warm gaze.",
    "bar_lounge": "Mysterious half-smile, direct steady eye contact, alluring gaze.",
    "cooking": "Genuine warm smile, approachable domestic charm, playful engaging eyes.",
    "dog_lover": "Genuine bright laugh, warm open expression, kind approachable eyes.",
    "travel": "Easy composed smile, composed worldly gaze, confident worldly expression.",
    "beach_sunset": "Warm sunset light on face, peaceful genuine smile, free relaxed eyes.",
    "art_gallery": "Intellectual composed expression, subtle confident gaze, cultured refined mouth.",
    "street_urban": "Effortless cool expression, bold urban half-smile, confident gaze.",
    "concert": "Passionate creative expression, engaged eye contact, soulful gaze.",
    # Landmarks
    "paris_eiffel": "Warm genuine smile, worldly romantic soft eyes, relaxed morning gaze.",
    "nyc_brooklyn_bridge": "Wind in hair, warm sunset glow on face, adventurous confident smile.",
    "rome_colosseum": "Relaxed Mediterranean expression, warm open charm, easy-going half-smile.",
    "dubai_burj_khalifa": "Composed modern gaze, subtle power smile, cosmopolitan confident eyes.",
    "nyc_times_square": "Bold confident expression, steady urban gaze, effortless cool look.",
    "barcelona_sagrada": "Relaxed sun-kissed expression, bright genuine smile, warm soft eyes.",
    "london_eye": "Thoughtful composed expression, subtle warm smile, elegant understated eyes.",
    "sydney_opera": "Bright warm smile, fresh natural look, open confident eyes.",
    "tokyo_tower": "Calm composed gaze, subtle confident expression, minimalist refined mouth.",
    "sf_golden_gate": "Wind-touched hair, peaceful awe-inspired expression, adventurous warm smile.",
    "athens_acropolis": "Relaxed thoughtful expression, warm gentle smile, cultural explorer eyes.",
    "singapore_marina_bay": "Polished confident gaze, subtle sophisticated smile, composed worldly eyes.",
    "venice_san_marco": "Romantic composed expression, warm charming smile, elegant European gaze.",
    "nyc_central_park": "Genuine bright smile, warm approachable look, easy natural eyes.",
    "london_big_ben": "Composed British elegance, subtle confident smile, refined worldly gaze.",
    # Travel expanded
    "airplane_window": "Relaxed contemplative gaze, calm easy smile, excited traveler eyes.",
    "train_journey": "Focused relaxed expression, calm thoughtful eyes, modern explorer half-smile.",
    "hotel_checkin": "Warm confident smile, polished traveler gaze, composed expression.",
    "hotel_breakfast": "Relaxed morning expression, warm genuine smile, luxury morning soft eyes.",
    "sea_balcony": "Wind in hair, peaceful bright smile, warm morning open eyes.",
    "old_town_walk": "Curious warm expression, gentle smile, cultural wanderer soft eyes.",
    "street_market": "Bright curious expression, warm genuine smile, adventurous explorer eyes.",
    # Atmosphere expanded
    "rainy_day": "Contemplative gaze, mysterious half-smile, moody atmospheric confidence.",
    "night_coffee": "Warm intimate gaze, gentle smile, cozy late-night thoughtful eyes.",
    "evening_home": "Calm contented expression, warm genuine smile, comfortable domestic confidence.",
    # Status
    "car_exit": "Confident direct gaze, purposeful composed expression, polished still mouth.",
    "travel_luxury": "Composed confident expression, subtle assured smile, elevated still brow.",
    # Sport expanded
    "yoga_outdoor": "Serene calm expression, gentle focused eyes, healthy mindful glow.",
    "cycling": "Fresh bright eyes, confident forward smile, active outdoor glow.",
    "tinder_pack_rooftop_golden": "Warm confident smile, engaged eye contact, relaxed romantic gaze.",
    "tinder_pack_minimal_studio": "Open genuine expression, soft approachable gaze, clean natural confidence.",
    "tinder_pack_cafe_window": "Bright easy smile, warm inviting eyes, cozy authentic charm.",
}

CV_STYLES: dict[str, str] = {
    # --- Classic ---
    "corporate": (
        "Background: modern corner office, floor-to-ceiling windows with diffused "
        "diffused daylight, neutral beige wall, clean minimalist interior. "
        "Clothing: tailored formal charcoal suit, crisp white shirt, subtle tie or silk scarf."
    ),
    "boardroom": (
        "Background: executive boardroom, polished dark table, leather chairs, "
        "large screen or whiteboard behind, even overhead lighting. "
        "Clothing: navy suit, power tie, pocket square, cufflinks."
    ),
    "formal_portrait": (
        "Background: neutral gradient studio backdrop charcoal-to-grey, classic Rembrandt "
        "lighting with gentle fill. "
        "Clothing: dark formal suit, white shirt, conservative tie, clean grooming."
    ),
    # --- Modern business ---
    "creative": (
        "Background: bright creative workspace, whiteboard or bookshelf behind, "
        "warm ambient light. "
        "Clothing: smart-casual blazer over fitted shirt, relaxed professional."
    ),
    "startup_casual": (
        "Background: open-plan startup office, standing desks, plants, glass partitions, "
        "bright natural light. "
        "Clothing: smart casual, fitted chinos, clean button-down with rolled sleeves, open collar."
    ),
    "coworking": (
        "Background: trendy coworking loft, exposed brick, industrial lighting, "
        "community workspace in background. "
        "Clothing: fitted blazer over crew-neck tee, dark jeans, modern smart-casual."
    ),
    "standing_desk": (
        "Background: minimal home office or tech workspace, monitor screens behind, "
        "clean desk, natural window light. "
        "Clothing: premium fitted polo or cashmere sweater, clean minimalist style."
    ),
    "neutral": (
        "Background: light-grey studio backdrop, even lighting from both sides, "
        "clean and distraction-free. "
        "Clothing: classic professional attire, solid neutral colors."
    ),
    # --- Industries ---
    "tech_developer": (
        "Background: developer workspace, multiple monitors with code on screen, "
        "dark ambient room, LED desk lighting. "
        "Clothing: quality hoodie or fitted dark sweater, comfortable technical style."
    ),
    "creative_director": (
        "Background: design studio, mood boards and sketches behind, "
        "warm directional studio light, mood boards in clear focus. "
        "Clothing: black turtleneck, minimalist dark outfit, statement glasses optional."
    ),
    "medical": (
        "Background: clean modern clinic or hospital corridor, bright even lighting, "
        "medical equipment in background. "
        "Clothing: white lab coat over dress shirt, stethoscope, professional medical attire."
    ),
    "legal_finance": (
        "Background: wood-paneled office or library, law books on shelves, "
        "warm ambient desk lamp, leather chair. "
        "Clothing: three-piece suit, silk tie, pocket square, classic luxury watch."
    ),
    "architect": (
        "Background: architectural studio, blueprints and scale models on table, "
        "large drafting table, bright workspace lighting. "
        "Clothing: fitted blazer, dark turtleneck, architect glasses optional."
    ),
    # --- Expertise ---
    "speaker_stage": (
        "Background: conference stage, podium with microphone, presentation screen "
        "clearly visible behind, warm stage key light from above keeping both speaker and screen readable. "
        "Clothing: tailored suit with open-collar shirt, confident speaker style."
    ),
    "podcast": (
        "Background: podcast studio, professional microphone on boom arm, acoustic panels, "
        "warm ambient lighting, headphones. "
        "Clothing: smart casual, clean fitted shirt, relaxed professional look."
    ),
    "mentor": (
        "Background: bright meeting room or cafe, whiteboard with diagrams behind, "
        "warm collaborative atmosphere. "
        "Clothing: smart casual blazer, open collar shirt, approachable professional style."
    ),
    "outdoor_business": (
        "Background: upscale outdoor cafe terrace, city street behind, "
        "laptop on table, natural daylight. "
        "Clothing: linen blazer over fitted shirt, chinos, digital nomad smart-casual."
    ),
    # --- Career expanded ---
    "video_call": (
        "Background: clean home office with ring light or monitor glow, "
        "neat bookshelves behind, webcam-friendly framing, even lighting. "
        "Clothing: professional fitted shirt, crisp collar, clean grooming visible above desk."
    ),
    "glass_wall_pose": (
        "Background: modern office with floor-to-ceiling glass wall, city panorama behind, "
        "clean architectural lines, natural daylight streaming in. "
        "Clothing: tailored suit or smart business attire, confident professional silhouette."
    ),
    "analytics_review": (
        "Background: office desk with financial charts on monitor screen, "
        "organized documents, warm desk lamp, focused workspace atmosphere. "
        "Clothing: professional shirt with rolled sleeves, reading glasses optional, sharp look."
    ),
    "tablet_stylus": (
        "Background: creative workspace, digital tablet on desk with sketches visible, "
        "clean modern interior, directional task light. "
        "Clothing: smart-casual fitted dark sweater, creative professional look."
    ),
    "notebook_ideas": (
        "Background: bright cafe or office corner, quality notebook open on table, "
        "pen in hand, warm natural window light, coffee cup nearby. "
        "Clothing: smart-casual layers, clean fitted shirt, professional yet relaxed."
    ),
    "coffee_break_work": (
        "Background: modern office kitchen or lounge area, coffee machine in background, "
        "bright even lighting, clean minimalist break space. "
        "Clothing: professional attire slightly relaxed, sleeves rolled, coffee cup in hand."
    ),
    "late_hustle": (
        "Background: modern office at evening, warm desk lamp light, city lights visible "
        "through window behind, focused productive workspace atmosphere. "
        "Clothing: professional shirt with loosened collar, sleeves rolled, focused work look."
    ),
    # --- Archetypes ---
    "quiet_expert": (
        "Background: home library or study with floor-to-ceiling bookshelves, "
        "warm reading lamp, rich wood tones, intellectual atmosphere. "
        "Clothing: quality cardigan or fitted cashmere sweater, subtle glasses, refined understated."
    ),
    "digital_nomad": (
        "Background: tropical co-working space or beach cafe with laptop on table, "
        "palm trees and ocean visible through open walls, bright natural light. "
        "Clothing: casual smart lightweight shirt, relaxed professional travel style."
    ),
    "entrepreneur_on_move": (
        "Background: modern city transit hub or street, phone in hand, "
        "fast-paced urban energy, sleek architecture behind. "
        "Clothing: smart blazer over casual outfit, carry-on bag, confident traveler style."
    ),
    "intellectual": (
        "Background: classic library or bookstore, warm amber ambient lighting, "
        "books and wooden shelves behind, academic atmosphere. "
        "Clothing: turtleneck or fitted quality shirt, subtle glasses, refined academic style."
    ),
    "man_with_mission": (
        "Background: dramatic modern architectural backdrop, glass and steel building, "
        "strong directional light, purposeful atmosphere. "
        "Clothing: dark tailored outfit, minimal accessories, determined professional style."
    ),
    # --- Professional moments ---
    "before_meeting": (
        "Background: modern office corridor or glass-walled lobby, bright clean environment, "
        "meeting rooms visible behind, professional workspace atmosphere. "
        "Clothing: fresh professional attire, straightened collar, polished ready-for-action look."
    ),
    "between_meetings": (
        "Background: office hallway or cafe between meetings, phone in hand checking messages, "
        "natural window light, transitional professional moment. "
        "Clothing: professional suit with relaxed posture, jacket unbuttoned, composed ease."
    ),
    "business_lounge": (
        "Background: premium airport or hotel business lounge, marble and leather surfaces, "
        "warm lighting, laptop and documents on table. "
        "Clothing: business-casual travel outfit, quality fabrics, polished accessories."
    ),
    "decision_moment": (
        "Background: standing at large window overlooking cityscape, contemplative atmosphere, "
        "warm rim light from window, cityscape in sharp focus through the window. "
        "Clothing: tailored dark suit against bright window, face evenly lit, executive presence."
    ),
    "doc_passport_neutral": (
        "Background: flat uniform light-grey wall, evenly lit backdrop with minimal residual shadow, "
        "frontal lighting, official document photo standard. "
        "Clothing: conservative solid dark top, neat collar, minimal accessories, neutral grooming."
    ),
    "doc_visa_compliant": (
        "Background: plain light-grey seamless backdrop, bright even lighting, "
        "high clarity, embassy-style compliant framing, shoulders square to camera. "
        "Clothing: business formal shirt with subtle tie, clean executive appearance."
    ),
    "doc_resume_headshot": (
        "Background: soft light-grey studio with visible details, "
        "flattering three-quarter portrait light, LinkedIn-standard professionalism. "
        "Clothing: tailored blazer, crisp shirt, confident approachable business attire."
    ),
    "photo_3x4": (
        "Background: clean uniform matte white. "
        "Clothing: simple solid-color top with a neat collar, bare head with hair fully visible."
    ),
    "passport_rf": (
        "Background: clean uniform white, smooth matte finish, evenly lit backdrop. "
        "Clothing: simple dark solid-color top with a neat collar, solid single-color fabric, plain unbranded."
    ),
    "visa_eu": (
        "Background: clean uniform white, evenly lit backdrop. "
        "Clothing: simple solid-color business top."
    ),
    "visa_us": (
        "Background: clean uniform white, soft even frontal lighting. "
        "Clothing: simple business top, civilian attire, bare head with hair visible."
    ),
    "photo_4x6": (
        "Background: clean uniform white. "
        "Clothing: tidy business top, solid neutral color."
    ),
}

CV_PERSONALITIES: dict[str, str] = {
    "corporate": "Trustworthy direct gaze, professional confident half-smile, composed still mouth.",
    "boardroom": "Authoritative composed expression, steady leadership gaze, strong confident brow.",
    "formal_portrait": "Steady composed direct gaze, neutral professional expression, timeless authority.",
    "creative": "Bold expressive gaze, artistic confident half-smile.",
    "startup_casual": "Approachable bright-eyed expression, relaxed innovative confidence.",
    "coworking": "Collaborative friendly expression, modern entrepreneurial half-smile.",
    "standing_desk": "Focused productive expression, tech-savvy composed confidence.",
    "neutral": "Relaxed, approachable, open and friendly gaze.",
    "tech_developer": "Alert focused expression, intelligent confident gaze, calm technical authority.",
    "creative_director": "Intense creative gaze, visionary confident expression, artistic authority.",
    "medical": "Warm empathetic expression, trustworthy caring gaze, calm medical authority.",
    "legal_finance": "Authoritative steady expression, distinguished gravitas, composed gaze.",
    "architect": "Precise analytical gaze, creative professional confidence, thoughtful expression.",
    "speaker_stage": "Engaging animated expression, commanding charismatic presence, confident forward gaze.",
    "podcast": "Natural animated expression, engaging conversational smile, authentic approachable authority.",
    "mentor": "Warm encouraging expression, wise approachable mentor smile, attentive gaze.",
    "outdoor_business": "Confident relaxed smile, modern flexible professional gaze.",
    # Career expanded
    "video_call": "Engaged expression, warm professional smile, confident screen presence, trustworthy soft eyes.",
    "glass_wall_pose": "Composed powerful gaze, modern executive steady brow, confident expression.",
    "analytics_review": "Sharp analytical expression, slight concentration furrow, intelligent authority.",
    "tablet_stylus": "Focused creative expression, innovative gaze, modern productive still brow.",
    "notebook_ideas": "Thoughtful inspired expression, subtle focused smile, creative productive gaze.",
    "coffee_break_work": "Relaxed confident smile, approachable warm expression, human professional soft eyes.",
    "late_hustle": "Focused determined expression, intense productive gaze, ambitious driven brow.",
    # Archetypes
    "quiet_expert": "Calm wise expression, subtle knowing smile, deep understated authority.",
    "digital_nomad": "Easy confident smile, free productive expression, relaxed modern gaze.",
    "entrepreneur_on_move": "Dynamic confident expression, purposeful forward gaze, sharp focused eyes.",
    "intellectual": "Thoughtful composed gaze, deep contemplative expression, scholarly refined brow.",
    "man_with_mission": "Strong direct gaze, determined composed expression, visionary leadership brow.",
    # Professional moments
    "before_meeting": "Focused composed gaze, subtle prepared smile, polished professional still mouth.",
    "between_meetings": "Relaxed but alert expression, composed ease, efficient professional gaze.",
    "business_lounge": "Composed traveler expression, confident relaxed smile, premium professional gaze.",
    "decision_moment": "Strong thoughtful expression, composed decisive brow, executive vision.",
    "doc_passport_neutral": "Neutral composed expression, mouth closed relaxed, direct even gaze, official photo calm.",
    "doc_visa_compliant": "Serious neutral expression, attentive steady gaze, formal compliant demeanor.",
    "doc_resume_headshot": "Warm professional half-smile, confident approachable gaze, trustworthy executive eyes.",
    "photo_3x4": "Neutral composed expression, mouth closed, eyes open, direct forward gaze, calm official demeanor.",
    "passport_rf": "Strictly neutral expression, mouth closed relaxed, eyes fully open, direct even frontal gaze, official composure.",
    "visa_eu": "Serious neutral expression, attentive steady centered gaze, formal compliant demeanor, mouth closed with a composed neutral line.",
    "visa_us": "Neutral calm expression, direct steady gaze, mouth closed, composed official look, neutral official expression with relaxed mouth.",
    "photo_4x6": "Neutral relaxed expression, direct natural gaze, calm composed demeanor, mouth closed.",
}

SOCIAL_STYLES: dict[str, str] = {
    # --- Influencer ---
    "influencer": (
        "Background: trendy urban rooftop at golden hour, city skyline clearly visible, "
        "warm directional side light, natural highlights on edges. "
        "Clothing: stylish streetwear, statement accessories, layered textures."
    ),
    "influencer_urban": (
        "Background: trendy urban rooftop at golden hour, city skyline clearly visible, "
        "warm directional side light, natural highlights on edges. "
        "Clothing: streetwear layers, statement accessories, designer sneakers."
    ),
    "influencer_minimal": (
        "Background: pure white or light beige minimalist studio, clean even lighting, "
        "Scandinavian aesthetic. "
        "Clothing: monochrome fitted outfit, one statement accessory, clean lines."
    ),
    "influencer_luxury": (
        "Background: upscale hotel lobby or lounge, marble surfaces, warm amber light, "
        "velvet and brass details. "
        "Clothing: designer outfit, fine fabrics, luxury watch or minimal gold jewelry."
    ),
    # --- Lifestyle ---
    "luxury": (
        "Background: upscale lounge with marble surfaces, warm amber ambient "
        "light, velvet and brass details in background. "
        "Clothing: designer outfit, fine fabrics, watches or minimal jewelry."
    ),
    "casual": (
        "Background: sunlit park with dappled tree shadows, or bright airy "
        "home interior with natural window light. "
        "Clothing: relaxed casual wear, natural cotton and linen fabrics."
    ),
    "morning_routine": (
        "Background: bright modern bedroom or bathroom, bright morning window light, "
        "white linens, plant on nightstand. "
        "Clothing: clean loungewear or casual morning outfit, fresh natural look."
    ),
    "fitness_lifestyle": (
        "Background: modern gym or outdoor workout area, bright natural light, "
        "clean athletic environment. "
        "Clothing: premium athletic wear, sport watch, clean sneakers, headphones around neck."
    ),
    "food_blogger": (
        "Background: beautifully plated food on marble table, restaurant or home kitchen, "
        "warm overhead lighting, fresh herbs and ingredients. "
        "Clothing: casual stylish outfit, clean smart look."
    ),
    "travel_blogger": (
        "Background: exotic location, vibrant colors, iconic landmark or tropical scenery "
        "in background, bright natural light. "
        "Clothing: travel outfit, linen shirt, hat or sunglasses, adventure accessories."
    ),
    # --- Aesthetic ---
    "artistic": (
        "Background: art gallery with large colorful paintings on white walls, "
        "warm track lighting from above, polished concrete floor. "
        "Clothing: dark fitted jacket over quality tee, dark jeans, clean artistic style."
    ),
    "golden_hour": (
        "Background: open meadow at golden hour, warm orange sunset light, "
        "tall grass and distant trees in sharp focus, clear sky. "
        "Clothing: fitted earth-tone cotton jacket over quality tee, dark jeans, clean classic casual."
    ),
    "neon_night": (
        "Background: city street at night with neon signs, vibrant pink-blue-purple "
        "reflections on wet pavement, sharp vibrant neon-lit street scene with readable signage. "
        "Clothing: dark streetwear, leather jacket or fitted dark outfit, reflective elements."
    ),
    "vintage_film": (
        "Background: retro cafe, vintage car, or old-town street, warm desaturated tones, "
        "subtle film grain, muted colors. "
        "Clothing: vintage-inspired outfit, classic cuts, earth and mustard tones."
    ),
    "dark_moody": (
        "Background: dark interior or dramatic outdoor setting, deep shadows, single "
        "directional light source, high contrast. "
        "Clothing: all-black fitted outfit, dark layers, minimal accessories."
    ),
    "pastel_soft": (
        "Background: light pastel-colored wall, bright even diffused light, "
        "warm tones, clean minimal setting. "
        "Clothing: light-colored fitted shirt, clean neutral trousers, minimal accessories."
    ),
    # --- Platforms ---
    "youtube_creator": (
        "Background: content creator setup, ring light, camera on tripod, "
        "colorful backdrop or LED panels. "
        "Clothing: bright casual outfit, branded merch style, expressive modern look."
    ),
    "linkedin_premium": (
        "Background: modern office or co-working space, clean bright environment, "
        "plants, glass partitions. "
        "Clothing: business casual, fitted blazer over quality shirt, professional but modern."
    ),
    "tinder_top": (
        "Background: natural outdoor setting with warm golden-hour backlight, "
        "simple uncluttered composition, warm tones. "
        "Clothing: casual fitted outfit that shows personality, clean attractive look."
    ),
    "instagram_aesthetic": (
        "Background: visually curated setting with cohesive color palette, "
        "architectural lines or nature patterns, balanced composition. "
        "Clothing: color-coordinated outfit matching the background palette."
    ),
    "podcast_host": (
        "Background: podcast studio, professional microphone, acoustic foam, "
        "warm studio lighting, headphones on desk. "
        "Clothing: smart casual, comfortable quality fabrics, clean modern look."
    ),
    "creative_portrait": (
        "Background: textured concrete wall with warm directional side lighting, "
        "natural shadow patterns, clean composition. "
        "Clothing: dark fitted turtleneck, one statement ring, clean minimalist creative style."
    ),
    # --- Social aesthetic ---
    "mirror_aesthetic": (
        "Background: clean modern minimalist room, indirect lighting, "
        "neutral walls, warm ambient glow, polished interior. "
        "Clothing: curated outfit with clean lines, one statement piece, polished silhouette."
    ),
    "elevator_clean": (
        "Background: modern elevator interior, stainless steel or mirrored walls, "
        "even overhead lighting, clean minimal space. "
        "Clothing: fitted smart outfit, clean sharp silhouette, polished aesthetic."
    ),
    "book_and_coffee": (
        "Background: cozy aesthetic table setting with open book and coffee cup, "
        "warm light, textured surfaces, neutral tones. "
        "Clothing: comfortable stylish layers, quality sweater, relaxed intellectual vibe."
    ),
    "shopfront": (
        "Background: stylish boutique or designer store window facade, "
        "clean architectural lines, warm display lighting, urban fashion setting. "
        "Clothing: on-trend outfit, shopping bags optional, fashion-forward street style."
    ),
    "candid_street": (
        "Background: urban street caught mid-stride, natural unposed moment, "
        "warm directional sunlight, pedestrians and architecture in scene. "
        "Clothing: effortless casual outfit, natural unstaged authentic look."
    ),
    # --- Hobbies ---
    "reading_home": (
        "Background: cozy home corner with diffused window light, comfortable armchair, "
        "bookshelves behind, warm domestic atmosphere. "
        "Clothing: comfortable quality loungewear, cozy socks, relaxed domestic style."
    ),
    "reading_cafe": (
        "Background: atmospheric bookshop cafe, books on shelves around, "
        "warm overhead pendant lights, coffee on table beside open book. "
        "Clothing: casual intellectual look, fitted sweater, comfortable smart style."
    ),
    "sketching": (
        "Background: studio or desk with sketching supplies, drawings and pencils visible, "
        "warm directional task lamp, creative workspace atmosphere. "
        "Clothing: creative casual tee, comfortable fit, artistic relaxed vibe."
    ),
    "photographer": (
        "Background: outdoor or studio setting with interesting light conditions, "
        "professional camera in hands, creative shooting environment. "
        "Clothing: practical creative outfit, dark layers, camera strap, artistic professional."
    ),
    "meditation": (
        "Background: serene outdoor garden or minimalist bright room, "
        "natural light, plants, calm zen atmosphere. "
        "Clothing: comfortable clean neutral outfit, natural tones, peaceful energy."
    ),
    "online_learning": (
        "Background: clean home desk with laptop open showing content, "
        "notes and coffee cup, focused study environment, natural light. "
        "Clothing: casual but clean fitted hoodie or sweater, headphones nearby."
    ),
    # --- Sport social ---
    "yoga_social": (
        "Background: outdoor yoga session at sunrise, mat on grass or deck, "
        "golden morning light, serene nature backdrop. "
        "Clothing: premium fitted yoga wear, clean athletic aesthetic, barefoot."
    ),
    "cycling_social": (
        "Background: scenic urban bike path or countryside road, bicycle in frame, "
        "golden light, green landscape, active lifestyle setting. "
        "Clothing: stylish cycling outfit or casual athletic top, sport sunglasses."
    ),
    # --- Cinematic / unique ---
    "panoramic_window": (
        "Background: standing before massive floor-to-ceiling window with dramatic "
        "city panorama, soft rim light from the window, face clearly lit from front, dramatic scale. "
        "Clothing: minimal dark outfit against bright cityscape, face evenly lit."
    ),
    "in_motion": (
        "Background: urban street with dynamic energy, caught walking "
        "dynamically, sense of movement and energy. "
        "Clothing: stylish casual outfit with flowing jacket or coat, dynamic movement."
    ),
    "creative_insight": (
        "Background: creative workspace with cork board and sketches on wall, "
        "warm desk lamp lighting, wooden desk with art supplies, cozy studio. "
        "Clothing: casual fitted dark shirt with rolled sleeves, dark jeans, clean creative style."
    ),
    "architecture_shadow": (
        "Background: dramatic architectural shadows and geometric light patterns, "
        "concrete or stone surfaces, bold contrast between light and dark. "
        "Clothing: minimal outfit in dark tones, strong visual contrast with light."
    ),
    "achievement_moment": (
        "Background: open rooftop or elevated space, bright expansive sky, "
        "sense of accomplishment and freedom, warm golden light. "
        "Clothing: smart outfit slightly undone in celebration, genuine joy."
    ),
    # --- Evening social ---
    "skyscraper_view": (
        "Background: high-rise interior with floor-to-ceiling windows, city lights below "
        "at night rendered with crisp distant detail, dramatic metropolitan atmosphere, warm interior accent light. "
        "Clothing: elegant dark outfit against glowing city skyline, face clearly visible."
    ),
    "after_work": (
        "Background: city sidewalk at dusk, warm streetlights beginning to glow, "
        "office buildings behind rendered sharply, golden-blue transition sky. "
        "Clothing: professional outfit slightly relaxed, jacket over shoulder, end-of-day vibe."
    ),
    "evening_planning": (
        "Background: home desk at evening, warm desk lamp light, notebook and tea, "
        "calm productivity atmosphere, dim window twilight behind. "
        "Clothing: comfortable smart-casual loungewear, focused domestic vibe."
    ),
    # --- Mood ---
    "focused_mood": (
        "Background: clean minimal backdrop fully visible, "
        "single directional key light with rich shadow on face, backdrop surfaces cleanly readable. "
        "Clothing: minimal dark outfit, all attention drawn to face and expression."
    ),
    "light_irony": (
        "Background: urban setting with interesting visual juxtaposition, "
        "slightly playful atmosphere, warm natural light, architectural context. "
        "Clothing: smart casual with personality, slight quirk in style, self-aware modern look."
    ),
}

SOCIAL_PERSONALITIES: dict[str, str] = {
    "influencer": "Bright confident look, engaging direct eye contact, charismatic half-smile.",
    "influencer_urban": "Engaging direct eye contact, animated charismatic expression, bold confidence.",
    "influencer_minimal": "Calm confident gaze, serene sophisticated still mouth, poised expression.",
    "influencer_luxury": "Mysterious soft eyes, sophisticated calm expression, elegant still brow.",
    "luxury": "Elegant mysterious soft eyes, sophisticated calm expression.",
    "casual": "Genuine relaxed look, warm natural feel, approachable open smile.",
    "morning_routine": "Peaceful fresh morning expression, warm genuine relaxed smile.",
    "fitness_lifestyle": "Healthy glow, energetic bright expression, motivational confident smile.",
    "food_blogger": "Warm engaging expression, inviting soft eyes, bright genuine smile.",
    "travel_blogger": "Excited adventurous expression, bright wanderlust wide eyes, open smile.",
    "artistic": "Thoughtful creative gaze, expressive intensity, unconventional character.",
    "golden_hour": "Soft dreamy gaze, warm peaceful expression, ethereal golden-lit soft eyes.",
    "neon_night": "Intense direct gaze, bold edgy steady mouth, bold confident expression.",
    "vintage_film": "Nostalgic thoughtful gaze, gentle analog expression, timeless romantic soft eyes.",
    "dark_moody": "Dramatic shadow-play on face, intense mysterious gaze, powerful brooding brow.",
    "pastel_soft": "Gentle soft smile, relaxed gentle eyes, light airy expression.",
    "youtube_creator": "Animated engaging expression, bright enthusiastic creator smile.",
    "linkedin_premium": "Warm professional smile, trustworthy confident soft eyes, approachable gaze.",
    "tinder_top": "Natural genuine smile, warm attractive easy-going soft eyes.",
    "instagram_aesthetic": "Editorial confident expression, polished still mouth, striking gaze.",
    "podcast_host": "Natural conversational smile, engaging authentic attentive gaze.",
    "creative_portrait": "Intense expressive gaze, bold artistic steady brow, striking expression.",
    # Social aesthetic
    "mirror_aesthetic": "Calm confident gaze, effortless polished still mouth, composed expression.",
    "elevator_clean": "Direct gaze, composed minimal expression, sharp modern still brow.",
    "book_and_coffee": "Warm thoughtful expression, gentle intellectual smile, cozy wisdom soft eyes.",
    "shopfront": "Natural fashion expression, confident modern street-style half-smile.",
    "candid_street": "Genuine unposed look, authentic spontaneous smile, natural expression.",
    # Hobbies
    "reading_home": "Peaceful concentrated expression, warm genuine comfort, domestic intellectual gaze.",
    "reading_cafe": "Thoughtful calm expression, gentle content smile, quiet cultured soft eyes.",
    "sketching": "Creative concentrated expression, artistic focused brow, focused gaze.",
    "photographer": "Focused creative expression, professional artistic steady brow, sharp gaze.",
    "meditation": "Serene peaceful expression, calm balanced soft eyes, mindful presence.",
    "online_learning": "Engaged curious expression, productive concentration, growth-minded attentive gaze.",
    # Sport social
    "yoga_social": "Serene calm expression, healthy glow, peaceful mindful soft eyes.",
    "cycling_social": "Fresh active expression, bright confident smile, healthy outdoor glow.",
    # Cinematic
    "panoramic_window": "Contemplative expression, profound calm gaze, grand-scale composed brow.",
    "in_motion": "Confident forward gaze, dynamic purposeful stride, bold expression.",
    "creative_insight": "Excited eureka expression, bright inspired eyes, raised eyebrow insight.",
    "architecture_shadow": "Mysterious confident expression, dramatic artistic presence, partial shadow.",
    "achievement_moment": "Genuine bright celebration expression, relieved proud smile, triumphant wide eyes.",
    # Evening social
    "skyscraper_view": "Composed serene expression, elevated sophisticated still mouth, calm gaze.",
    "after_work": "Relaxed relief expression, easy warm smile, comfortable end-of-day soft eyes.",
    "evening_planning": "Focused calm expression, quiet determination, productive evening still brow.",
    # Mood
    "focused_mood": "Intense concentrated gaze, powerful focused presence, steady direct eyes.",
    "light_irony": "Subtle smirk, playful knowing expression, witty confident raised eyebrow.",
}


# ---------------------------------------------------------------------------
# Typed style registry — built from the raw dicts above
# ---------------------------------------------------------------------------

STYLE_REGISTRY = StyleRegistry()

_STYLE_OVERRIDES: dict[tuple[str, str], dict] = {
    # Gender-specific female clothing overrides
    ("social", "pastel_soft"): {
        "clothing_female_override": (
            "light pastel blouse or fitted dress, soft fabrics, "
            "delicate gold accessories, feminine elegant style"
        ),
    },
    ("dating", "swimming_pool"): {
        "clothing_female_override": (
            "elegant one-piece swimsuit, optional sunglasses, "
            "light sarong or cover-up"
        ),
    },
    ("dating", "gym_fitness"): {
        "clothing_female_override": (
            "fitted athletic top, athletic leggings, training shoes, "
            "sport watch"
        ),
    },
    ("social", "fitness_lifestyle"): {
        "clothing_female_override": (
            "premium fitted athletic top, athletic leggings, "
            "sport watch, clean sneakers, headphones around neck"
        ),
    },
}

for _key, _text in DATING_STYLES.items():
    _pers = DATING_PERSONALITIES.get(_key, "")
    _ovr = _STYLE_OVERRIDES.get(("dating", _key), {})
    STYLE_REGISTRY.register(build_spec_from_legacy(
        _key, "dating", _text, _pers,
        clothing_female_override=_ovr.get("clothing_female_override", ""),
        edit_compatible=_ovr.get("edit_compatible", True),
        complexity=_ovr.get("complexity", "simple"),
        variants=STYLE_VARIANTS.get(("dating", _key), ()),
    ))

for _key, _text in CV_STYLES.items():
    _pers = CV_PERSONALITIES.get(_key, "")
    _ovr = _STYLE_OVERRIDES.get(("cv", _key), {})
    STYLE_REGISTRY.register(build_spec_from_legacy(
        _key, "cv", _text, _pers,
        clothing_female_override=_ovr.get("clothing_female_override", ""),
        edit_compatible=_ovr.get("edit_compatible", True),
        complexity=_ovr.get("complexity", "simple"),
        variants=STYLE_VARIANTS.get(("cv", _key), ()),
    ))

for _key, _text in SOCIAL_STYLES.items():
    _pers = SOCIAL_PERSONALITIES.get(_key, "")
    _ovr = _STYLE_OVERRIDES.get(("social", _key), {})
    STYLE_REGISTRY.register(build_spec_from_legacy(
        _key, "social", _text, _pers,
        clothing_female_override=_ovr.get("clothing_female_override", ""),
        edit_compatible=_ovr.get("edit_compatible", True),
        complexity=_ovr.get("complexity", "simple"),
        variants=STYLE_VARIANTS.get(("social", _key), ()),
    ))


# ---------------------------------------------------------------------------
# Prompt builders — compact 800–1200 char photorealistic template
# ---------------------------------------------------------------------------

_DOCUMENT_STYLE_KEYS = frozenset({
    "photo_3x4",
    "passport_rf",
    "visa_eu",
    "visa_schengen",
    "visa_us",
    "photo_4x6",
    "driver_license",
    "doc_passport_neutral",
    "doc_visa_compliant",
    "doc_resume_headshot",
})


def is_document_style(style: str) -> bool:
    """True для CV-стилей «Фото на документы», где требуется строгая композиция."""
    return (style or "").strip() in _DOCUMENT_STYLE_KEYS


_DOC_COMPOSITION_HINT: dict[str, str] = {
    "photo_3x4": "3:4 portrait framing, face fills 70-80% of the frame, small margin above the head.",
    "passport_rf": "7:9 portrait framing, frontal pose, face fills 70-80% of the frame.",
    "visa_eu": "7:9 portrait framing, face centered, 70-80% of the frame.",
    "visa_schengen": "7:9 portrait framing, face centered, 70-80% of the frame.",
    "visa_us": "1:1 square framing, face centered, 50-70% of the frame.",
    "photo_4x6": "2:3 portrait framing, face fills 60-75% of the frame.",
    "driver_license": "3:4 portrait framing, face centered.",
    "doc_passport_neutral": "Centered head-and-shoulders, shoulders square to camera.",
    "doc_visa_compliant": "Centered head-and-shoulders, shoulders square to camera.",
    "doc_resume_headshot": "Head-and-shoulders business portrait framing.",
}


def _truncate(prompt: str) -> str:
    """Enforce the PROMPT_MAX_LEN budget in production."""
    if len(prompt) <= PROMPT_MAX_LEN:
        return prompt
    logger.warning(
        "prompt exceeded budget (%d > %d), truncating",
        len(prompt), PROMPT_MAX_LEN,
    )
    return prompt[:PROMPT_MAX_LEN].rstrip()


def _build_mode_prompt(
    mode: str,
    style: str,
    gender: str,
    change_instruction: str,
    input_hints: dict | None = None,
    variant: StyleVariant | None = None,
) -> str:
    """Assemble a compact photorealistic paragraph.

    Layout: change line → Background/Clothing → expression → [framing hint
    if head-crop × full-body] → PRESERVE → QUALITY. No section tags, no
    redundant anchors, no conditional DoF — one natural paragraph that the
    generation model parses cleanly and stays well under 1200 chars.

    When ``variant`` is provided, its scene/lighting/props/camera/clothing
    accent override (or append to) the fields from the base :class:`StyleSpec`
    to diversify the generation without touching identity anchors.
    """
    style_key_norm = (style or "").strip()
    is_doc = mode == "cv" and style_key_norm in _DOCUMENT_STYLE_KEYS

    spec = STYLE_REGISTRY.get_or_default(mode, style)
    clothing = spec.clothing_for(gender)
    bg = spec.background

    if variant is not None and not is_doc:
        if variant.scene:
            bg = variant.scene
        accent = variant.clothing_accent_for(gender)
        if accent:
            clothing = f"{clothing}, {accent}" if clothing else accent

    parts: list[str] = [change_instruction]
    if bg:
        parts.append(f"Background: {bg}.")
    if clothing:
        parts.append(f"Clothing: {clothing}.")
    if variant is not None and not is_doc:
        if variant.lighting:
            parts.append(f"Lighting: {variant.lighting}.")
        if variant.props:
            parts.append(f"Props: {variant.props}.")
        if variant.camera:
            parts.append(f"Camera: {variant.camera}.")
    if spec.expression:
        parts.append(spec.expression)

    # NOTE: the previous "Framing note: keep upper-body crop, do not
    # extend the body" for head-crop inputs × ``needs_full_body`` styles
    # has been removed. It contradicted the scene description (yoga,
    # beach, running) and produced "headshot in yoga clothes" outputs
    # at 1024 px. FLUX.2 Pro Edit at 2 MP invents the lower body
    # consistently with the scene; identity is held by
    # ``PRESERVE_PHOTO_FACE_ONLY`` instead.

    if is_doc:
        composition = _DOC_COMPOSITION_HINT.get(
            style_key_norm,
            "Centered head-and-shoulders framing.",
        )
        parts.append(f"Composition: {composition}")
        parts.append(DOC_PRESERVE)
        parts.append(DOC_QUALITY)
    else:
        # Full-body scenes (yoga, beach, running, hiking, ...) require a new
        # pose that differs from the reference; the default PRESERVE_PHOTO
        # pins "original pose and body proportions" and creates a
        # contradiction for FLUX Kontext Pro. Fall back to the face-only
        # variant for those styles.
        if getattr(spec, "needs_full_body", False):
            parts.append(PRESERVE_PHOTO_FACE_ONLY)
        else:
            parts.append(PRESERVE_PHOTO)
        parts.append(QUALITY_PHOTO)

    parts.append(IDENTITY_LOCK_SUFFIX)

    prompt = " ".join(p.strip() for p in parts if p and p.strip())
    return _truncate(prompt)


def _dating_social_change_instruction(mode: str, style: str) -> str:
    """Pick the base change-instruction for dating/social styles.

    Full-body scenes (yoga, beach, running...) intentionally change the
    pose — asking the model to also keep it "identical to the reference"
    was the contradictory signal that destabilised FLUX Kontext Pro in
    production. We drop that clamp for ``needs_full_body`` styles while
    still pinning identity.
    """
    spec = STYLE_REGISTRY.get(mode, style)
    if spec is not None and spec.needs_full_body:
        return (
            "Place the person from the reference photo into the new scene "
            "described below, adopting a natural pose that fits the scene, "
            "while maintaining the exact same facial features, bone "
            "structure, skin tone and head-to-body proportions of the "
            "reference subject."
        )
    return (
        "Change the background and clothing of the person in the reference "
        "photo while maintaining the exact same facial features, bone "
        "structure, skin tone and head-to-body proportions, keeping the "
        "original pose."
    )


def build_dating_prompt(
    style: str = "", gender: str = "male", input_hints: dict | None = None,
    variant: StyleVariant | None = None,
) -> str:
    return _build_mode_prompt(
        "dating", style, gender,
        _dating_social_change_instruction("dating", style),
        input_hints=input_hints,
        variant=variant,
    )


def build_cv_prompt(
    style: str = "", gender: str = "male", input_hints: dict | None = None,
    variant: StyleVariant | None = None,
) -> str:
    style_key = (style or "").strip()
    if style_key in _DOCUMENT_STYLE_KEYS:
        change_instruction = (
            "Replace the background with a clean neutral backdrop and clothing "
            "with a simple solid-color top, minimal plain accessories, bare "
            "head, while maintaining the same facial features, skin tone and "
            "head-to-body proportions. Head centered, shoulders straight, eyes "
            "open looking at the camera, mouth relaxed and closed."
        )
    else:
        change_instruction = (
            "Change the background and clothing to professional attire of the "
            "person in the reference photo while maintaining the same facial "
            "features, skin tone and head-to-body proportions, keeping the "
            "original pose."
        )
    return _build_mode_prompt(
        "cv", style_key, gender, change_instruction,
        input_hints=input_hints, variant=variant,
    )


def build_social_prompt(
    style: str = "", gender: str = "male", input_hints: dict | None = None,
    variant: StyleVariant | None = None,
) -> str:
    return _build_mode_prompt(
        "social", style, gender,
        _dating_social_change_instruction("social", style),
        input_hints=input_hints,
        variant=variant,
    )


def resolve_style_variant(mode: str, style: str, variant_id: str) -> StyleVariant | None:
    """Return the registered StyleVariant for (mode, style, variant_id).

    Returns ``None`` for unknown combinations or for document styles —
    callers can treat that as "fall back to the base style".
    """
    if not variant_id:
        return None
    if mode == "cv" and (style or "").strip() in _DOCUMENT_STYLE_KEYS:
        return None
    spec = STYLE_REGISTRY.get(mode, style)
    if spec is None:
        return None
    return spec.variant_by_id(variant_id)


# ---------------------------------------------------------------------------
# Multi-pass step templates — compact single-paragraph variants
# ---------------------------------------------------------------------------

_STEP_CHANGE: dict[str, str] = {
    "background_edit": "Change the background to {description} while maintaining facial features, skin tone and head-to-body proportions, keeping clothing and pose of the person in the reference photo.",
    "clothing_edit": "Change the clothing to {description} while maintaining facial features, skin tone and head-to-body proportions, keeping the original background and pose.",
    "lighting_adjust": "Adjust the lighting and color grading to {description} while maintaining facial features and skin tone of the person in the reference photo.",
    "expression_hint": "Apply subtle expression adjustment toward {description} while maintaining facial features and skin tone.",
    "skin_correction": "Apply minor skin tone refinement and blemish cleanup while maintaining facial features and skin undertone of the person in the reference photo.",
    "style_overall": "Apply overall style enhancement toward {description} while maintaining facial features, skin tone and head-to-body proportions.",
}

STEP_TEMPLATES: dict[str, str] = {
    key: f"{change} {PRESERVE_PHOTO} {QUALITY_PHOTO}"
    for key, change in _STEP_CHANGE.items()
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
    mode: str = "dating",
    gender: str = "male",
    enhancement_level: int = 0,
) -> str:
    """Build a prompt for a single pipeline step using the StyleSpec registry."""
    template = STEP_TEMPLATES.get(step_template, STEP_TEMPLATES.get("style_overall", ""))
    spec = STYLE_REGISTRY.get_or_default(mode, style)
    if step_template == "expression_hint":
        description = spec.expression
    else:
        clothing = spec.clothing_for(gender)
        description = f"Background: {spec.background}. Clothing: {clothing}."
    prompt = template.replace("{description}", description)
    if enhancement_level and enhancement_level in ENHANCEMENT_LEVEL_MODIFIERS:
        prompt += " " + ENHANCEMENT_LEVEL_MODIFIERS[enhancement_level]
    return prompt


_EMOJI_GENDER_HINT = {
    "male": "Male character, masculine silhouette, short or styled hair as in the reference.",
    "female": "Female character, feminine silhouette, hair styled as in the reference.",
}


def build_emoji_prompt(base_description: str = "", gender: str = "") -> str:
    gender_key = (gender or "").strip().lower()
    gender_line = _EMOJI_GENDER_HINT.get(gender_key, "")
    prompt = (
        "Cartoon-styled version of the same person from the reference photo. "
        "Sticker avatar while maintaining exact facial proportions, face shape, "
        "eye shape and color, hairstyle and hair color, and skin tone in "
        "cartoon style — the sticker must be instantly recognizable as the "
        "same person. Render clean even skin in cartoon style. "
        "Bold outlines, flat vibrant colors, friendly expression, square composition."
    )
    if gender_line:
        prompt = f"{prompt} {gender_line}"
    desc = base_description[:400]
    if desc:
        prompt = f"{prompt} Character: {desc}"
    return prompt
