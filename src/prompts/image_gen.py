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
    # --- Lifestyle ---
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
    "near_car": (
        "Background: luxury sedan or sports car parked on sunlit city boulevard, "
        "warm golden reflections on polished paint, blurred urban architecture. "
        "Clothing: fitted dark jeans, crisp white crew-neck t-shirt, leather watch, "
        "aviator sunglasses pushed up on head."
    ),
    "in_car": (
        "Background: interior of modern car, soft window light streaming through "
        "windshield, leather steering wheel and dashboard blurred. "
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
        "Background: rooftop terrace at blue hour, city skyline with warm bokeh lights, "
        "modern glass railing, ambient string lights. "
        "Clothing: dark fitted blazer over black tee, tailored trousers, minimalist watch."
    ),
    # --- Sport / Active ---
    "gym_fitness": (
        "Background: modern gym with matte equipment, even overhead lighting, "
        "mirrors blurred behind. "
        "Clothing: fitted athletic tank top or compression shirt, athletic shorts, training shoes."
    ),
    "running": (
        "Background: tree-lined park path at early morning, soft diffused golden light, "
        "green foliage with dew. "
        "Clothing: lightweight running shirt, athletic shorts, running shoes, sport watch."
    ),
    "tennis": (
        "Background: outdoor tennis court, warm afternoon light, green court surface, "
        "blurred net behind. "
        "Clothing: fitted polo shirt, tennis shorts, wristband, clean white sneakers."
    ),
    "swimming_pool": (
        "Background: infinity pool edge with blue water, palm trees, resort setting, "
        "bright daylight with sparkling reflections. "
        "Clothing: fitted swim trunks, clean bare torso, optional sunglasses in hand."
    ),
    "hiking": (
        "Background: mountain trail with panoramic valley view at golden hour, "
        "rocky terrain, dramatic sky with warm clouds. "
        "Clothing: fitted outdoor jacket or fleece, hiking pants, backpack straps visible."
    ),
    # --- Atmosphere ---
    "cafe": (
        "Background: cozy upscale cafe, warm tungsten light, exposed brick or "
        "wood paneling, blurred bottles and candles in background. "
        "Clothing: smart-casual date outfit, earth tones, linen or cotton."
    ),
    "coffee_date": (
        "Background: upscale third-wave coffee shop, warm tungsten lighting, "
        "exposed wood shelving, latte art on table. "
        "Clothing: soft knit sweater or henley, dark jeans, clean casual style."
    ),
    "restaurant": (
        "Background: upscale restaurant, dim warm candlelight, dark wood and white linen, "
        "wine glass on table blurred. "
        "Clothing: tailored dark shirt or blazer, smart evening look, subtle accessories."
    ),
    "bar_lounge": (
        "Background: modern cocktail lounge, moody amber and teal lighting, "
        "bar shelves with bottles blurred behind. "
        "Clothing: dark fitted shirt, sleeves rolled, leather or fabric watch."
    ),
    "cooking": (
        "Background: bright modern kitchen, natural window light, marble countertop, "
        "fresh ingredients and herbs visible. "
        "Clothing: clean apron over casual shirt, rolled sleeves, natural domestic setting."
    ),
    "dog_lover": (
        "Background: sunlit park with green grass and trees, soft golden backlight, "
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
        "Background: contemporary art gallery, white walls with abstract art blurred, "
        "track lighting creating soft directional light. "
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
}

DATING_PERSONALITIES: dict[str, str] = {
    "warm_outdoor": "Soft relaxed eyes, warm approachable look, gentle natural expression.",
    "studio_elegant": "Strong direct gaze, squared shoulders, calm self-assured energy.",
    "near_car": "Confident relaxed lean, one hand resting on car roof, direct assured gaze with subtle half-smile, squared shoulders.",
    "in_car": "One hand on steering wheel, relaxed driver posture, warm natural smile catching light from side window, easy confident energy.",
    "motorcycle": "Standing beside motorcycle, arms relaxed at sides, strong direct gaze, calm rugged confidence.",
    "yacht": "Relaxed seaside posture, wind-touched hair, warm bright smile, open carefree energy.",
    "rooftop_city": "Standing at railing edge, city behind, composed sophisticated gaze, subtle confident smile.",
    "gym_fitness": "Athletic stance, arms naturally at sides, healthy glow, energetic direct look with determined confident expression.",
    "running": "Mid-stride or standing pause, light sweat glow on skin, fresh energetic expression, bright alert eyes.",
    "tennis": "Racket held casually at side, relaxed athletic posture, confident sporty smile, sun-kissed healthy look.",
    "swimming_pool": "Relaxed seated or standing at pool edge, natural tanned skin, warm easy smile, vacation energy.",
    "hiking": "Standing at overlook, wind in hair, accomplished peaceful expression, adventurous bright-eyed energy.",
    "cafe": "Bright engaging eyes, magnetic energy, open relaxed posture.",
    "coffee_date": "Seated at small table, hands around warm cup, gentle attentive smile, warm inviting eye contact.",
    "restaurant": "Seated or leaning at table, soft amber light on face, charming engaged expression, sophisticated relaxed energy.",
    "bar_lounge": "Leaning at bar or seated in lounge chair, cocktail nearby, mysterious half-smile, magnetic confident energy.",
    "cooking": "Hands active with food preparation, genuine warm smile, approachable domestic charm, playful engaging eyes.",
    "dog_lover": "Kneeling or crouching near a friendly dog, genuine bright laugh, warm open expression, kind approachable energy.",
    "travel": "Standing with boarding pass or phone, confident world-traveler posture, easy composed smile, cosmopolitan energy.",
    "beach_sunset": "Walking along shoreline or standing at water edge, warm sunset light on face, peaceful genuine smile, free relaxed energy.",
    "art_gallery": "Standing thoughtfully near artwork, intellectual composed expression, subtle confident gaze, cultured refined energy.",
    "street_urban": "Walking confidently mid-stride, hands in pockets, effortless cool expression, bold urban energy.",
    "concert": "Guitar in hands or leaning against wall near instruments, passionate creative expression, magnetic artistic energy.",
}

CV_STYLES: dict[str, str] = {
    # --- Classic ---
    "corporate": (
        "Background: modern corner office, floor-to-ceiling windows with soft "
        "diffused daylight, neutral beige wall, clean minimalist interior. "
        "Clothing: tailored formal charcoal suit, crisp white shirt, subtle tie or silk scarf."
    ),
    "boardroom": (
        "Background: executive boardroom, polished dark table, leather chairs blurred, "
        "large screen or whiteboard behind, even overhead lighting. "
        "Clothing: navy suit, power tie, pocket square, cufflinks."
    ),
    "formal_portrait": (
        "Background: neutral gradient studio backdrop charcoal-to-grey, classic Rembrandt "
        "lighting with soft fill. "
        "Clothing: dark formal suit, white shirt, conservative tie, clean grooming."
    ),
    # --- Modern business ---
    "creative": (
        "Background: bright creative workspace, whiteboard or bookshelf slightly "
        "out of focus, warm ambient light. "
        "Clothing: smart-casual blazer over fitted shirt, relaxed professional."
    ),
    "startup_casual": (
        "Background: open-plan startup office, standing desks, plants, glass partitions, "
        "bright natural light. "
        "Clothing: smart casual, fitted chinos, clean button-down with rolled sleeves, no tie."
    ),
    "coworking": (
        "Background: trendy coworking loft, exposed brick, industrial lighting, "
        "community workspace blurred behind. "
        "Clothing: fitted blazer over crew-neck tee, dark jeans, modern smart-casual."
    ),
    "standing_desk": (
        "Background: minimal home office or tech workspace, monitor screens blurred, "
        "clean desk, natural window light. "
        "Clothing: premium fitted polo or cashmere sweater, clean minimalist style."
    ),
    "neutral": (
        "Background: light-grey studio backdrop, even soft lighting from both sides, "
        "clean and distraction-free. "
        "Clothing: classic professional attire, solid neutral colors."
    ),
    # --- Industries ---
    "tech_developer": (
        "Background: developer workspace, multiple monitors with code blurred, "
        "dark ambient room, LED desk lighting. "
        "Clothing: quality hoodie or fitted dark sweater, comfortable technical style."
    ),
    "creative_director": (
        "Background: design studio, mood boards and sketches blurred behind, "
        "dramatic directional spotlight. "
        "Clothing: black turtleneck, minimalist dark outfit, statement glasses optional."
    ),
    "medical": (
        "Background: clean modern clinic or hospital corridor, bright even lighting, "
        "medical equipment blurred. "
        "Clothing: white lab coat over dress shirt, stethoscope, professional medical attire."
    ),
    "legal_finance": (
        "Background: wood-paneled office or library, law books on shelves, "
        "warm ambient desk lamp, leather chair. "
        "Clothing: three-piece suit, silk tie, pocket square, classic luxury watch."
    ),
    "architect": (
        "Background: architectural studio, blueprints and scale models blurred, "
        "large drafting table, bright workspace lighting. "
        "Clothing: fitted blazer, dark turtleneck, architect glasses optional."
    ),
    # --- Expertise ---
    "speaker_stage": (
        "Background: conference stage, podium with microphone, presentation screen "
        "blurred behind, dramatic spotlight from above. "
        "Clothing: tailored suit without tie, open collar, confident speaker style."
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
        "Background: upscale outdoor cafe terrace, city street blurred behind, "
        "laptop on table, natural daylight. "
        "Clothing: linen blazer over fitted shirt, chinos, digital nomad smart-casual."
    ),
}

CV_PERSONALITIES: dict[str, str] = {
    "corporate": "Composed upright posture, trustworthy direct gaze, professional confident half-smile.",
    "boardroom": "Seated at head of table or standing at presentation position, authoritative composed expression, leadership energy.",
    "formal_portrait": "Straight-on or slight 3/4 turn, steady composed direct gaze, neutral professional expression, timeless authority.",
    "creative": "Bold, expressive, artistic energy with confident posture.",
    "startup_casual": "Standing near whiteboard or laptop, approachable energetic expression, relaxed innovative confidence.",
    "coworking": "Seated at shared table with laptop, collaborative friendly expression, modern entrepreneurial energy.",
    "standing_desk": "Standing at desk, one hand on surface, focused productive expression, tech-savvy composed confidence.",
    "neutral": "Relaxed, approachable, open and friendly gaze.",
    "tech_developer": "Seated at workstation, alert focused expression, intelligent confident gaze, calm technical authority.",
    "creative_director": "Arms crossed or one hand on chin, intense creative gaze, visionary confident expression, artistic authority.",
    "medical": "Standing confidently, warm empathetic expression, trustworthy caring gaze, calm medical authority.",
    "legal_finance": "Seated at mahogany desk or standing near bookshelf, authoritative steady expression, distinguished gravitas.",
    "architect": "Standing over plans or holding rolled blueprint, precise analytical gaze, creative professional confidence.",
    "speaker_stage": "Hands in gesture mid-presentation, engaging animated expression, commanding charismatic stage presence.",
    "podcast": "Seated at mic, natural animated expression, engaging conversational energy, authentic approachable authority.",
    "mentor": "Leaning forward in engaged conversation pose, warm encouraging expression, wise approachable mentor energy.",
    "outdoor_business": "Seated with laptop and coffee, confident relaxed smile, modern flexible professional energy.",
}

SOCIAL_STYLES: dict[str, str] = {
    # --- Influencer ---
    "influencer": (
        "Background: trendy urban rooftop at golden hour, city skyline bokeh, "
        "warm directional light with lens flare. "
        "Clothing: stylish streetwear, statement accessories, layered textures."
    ),
    "influencer_urban": (
        "Background: trendy urban rooftop at golden hour, city skyline bokeh, "
        "warm directional light with lens flare. "
        "Clothing: streetwear layers, statement accessories, designer sneakers."
    ),
    "influencer_minimal": (
        "Background: pure white or light beige minimalist studio, clean even lighting, "
        "Scandinavian aesthetic. "
        "Clothing: monochrome fitted outfit, one statement accessory, clean lines."
    ),
    "influencer_luxury": (
        "Background: upscale hotel lobby or lounge, marble surfaces, soft amber light, "
        "velvet and brass details. "
        "Clothing: designer outfit, fine fabrics, luxury watch or minimal gold jewelry."
    ),
    # --- Lifestyle ---
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
    "morning_routine": (
        "Background: bright modern bedroom or bathroom, soft morning window light, "
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
        "blurred behind, bright natural light. "
        "Clothing: travel outfit, linen shirt, hat or sunglasses, adventure accessories."
    ),
    # --- Aesthetic ---
    "artistic": (
        "Background: art gallery with textured walls, or vivid mural, "
        "dramatic side lighting with deep shadows. "
        "Clothing: eclectic artistic mix, bold colors, unique layering."
    ),
    "golden_hour": (
        "Background: open field or waterfront at golden hour, warm orange-pink backlight, "
        "lens flare, silhouetted trees. "
        "Clothing: earthy neutral tones, flowing natural fabrics, bohemian or classic casual."
    ),
    "neon_night": (
        "Background: city street at night with neon signs, vibrant pink-blue-purple "
        "reflections on wet pavement, cinematic lighting. "
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
        "Background: pastel-colored wall or soft floral setting, bright even diffused light, "
        "airy cotton-candy aesthetic. "
        "Clothing: light pastel outfit, soft fabrics, delicate accessories."
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
        "Background: natural outdoor setting with soft golden-hour backlight, "
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
        "Background: abstract or textured wall, dramatic split lighting, "
        "bold color accent, artistic composition. "
        "Clothing: eclectic creative outfit, bold patterns or statement piece, unconventional style."
    ),
}

SOCIAL_PERSONALITIES: dict[str, str] = {
    "influencer": "Bright confident look, engaging direct eye contact, charismatic energy.",
    "influencer_urban": "Confident power pose, engaging direct eye contact, charismatic high-energy expression.",
    "influencer_minimal": "Poised centered stance, calm confident gaze, serene sophisticated energy.",
    "influencer_luxury": "Elegant composed posture, mysterious allure, sophisticated calm expression.",
    "luxury": "Elegant poise, mysterious allure, sophisticated calm expression.",
    "casual": "Genuine relaxed look, warm natural feel, approachable open vibe.",
    "morning_routine": "Holding coffee mug near window, peaceful fresh morning expression, warm genuine relaxed smile.",
    "fitness_lifestyle": "Post-workout confident stance, healthy glow, energetic bright expression, motivational energy.",
    "food_blogger": "Smiling over beautiful dish, hands presenting food, warm engaging foodie expression, inviting energy.",
    "travel_blogger": "Arms open or pointing at view, excited adventurous expression, bright wanderlust energy.",
    "artistic": "Thoughtful creative gaze, expressive intensity, unconventional character.",
    "golden_hour": "Soft dreamy gaze into distance, warm peaceful expression, ethereal golden-lit energy.",
    "neon_night": "Bold confident stance, intense direct gaze, cinematic edgy energy.",
    "vintage_film": "Nostalgic thoughtful gaze, gentle analog expression, timeless romantic energy.",
    "dark_moody": "Dramatic shadow-play on face, intense mysterious gaze, powerful brooding energy.",
    "pastel_soft": "Gentle soft smile, relaxed gentle energy, light airy expression.",
    "youtube_creator": "Animated engaging expression, hands in gesture, bright enthusiastic creator energy.",
    "linkedin_premium": "Confident approachable headshot pose, warm professional smile, trustworthy LinkedIn-ready energy.",
    "tinder_top": "Natural genuine smile, relaxed approachable posture, warm attractive easy-going energy.",
    "instagram_aesthetic": "Artfully posed, editorial confident expression, Instagram-worthy polished energy.",
    "podcast_host": "Seated at mic setup, natural conversational smile, engaging authentic host energy.",
    "creative_portrait": "Unconventional pose or angle, intense expressive gaze, bold artistic energy.",
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
