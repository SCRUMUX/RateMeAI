"""Centralized image-generation prompt builder for all modes.

Prompt structure follows the Change -> Preserve -> Quality pattern
proven to achieve 91% first-attempt success in edit-mode models.
Constants use positive framing to avoid diffusion "NO Syndrome".
"""
from __future__ import annotations

from src.prompts.style_spec import (
    StyleRegistry,
    build_spec_from_legacy,
)

# ---------------------------------------------------------------------------
# Core anchors — positive framing, no negation overload
# ---------------------------------------------------------------------------

IDENTITY_FIRST = (
    "CRITICAL: Preserve the person's face identity exactly as in the reference photo. "
    "The result must be immediately recognizable as the same person."
)

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
    "SKIN: keep natural skin texture with visible pores and subtle imperfections. "
    "Do not smooth or airbrush the skin. Minimal cleanup only."
)

BACKGROUND_FOCUS = (
    "BACKGROUND FOCUS: sharp and in-focus background, fully detailed, "
    "deep depth of field. The background must be as crisp as the subject."
)

CAMERA = (
    "High-quality digital photograph. Crisp detail throughout entire frame. "
    "Clean natural colors."
)

REALISM = (
    "Photorealistic result. Natural skin texture. Sharp and clean. "
    "Looks like a real unedited photo."
)

DOCUMENT_PHOTO_REALISM = (
    "Photorealistic head-and-shoulders portrait. Natural unedited photo look. "
    "Face: keep the same facial features, bone structure and natural skin texture; "
    "remove only temporary blemishes (small pimples, redness). "
    "Expression: calm neutral, mouth relaxed and closed, eyes open, looking straight at the camera. "
    "Lighting: soft even studio light, minimal shadows on face and backdrop. "
    "True-to-life skin tones, no heavy color grading, no artistic filters. "
    "Centered head-and-shoulders framing, suitable for a professional ID-style headshot."
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
        "backdrop, subtle vignette. "
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
        "Background: rooftop terrace at blue hour, city skyline with warm lights, "
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
        "wood paneling, bottles and candles in background. "
        "Clothing: smart-casual date outfit, earth tones, linen or cotton."
    ),
    "coffee_date": (
        "Background: upscale third-wave coffee shop, warm tungsten lighting, "
        "exposed wood shelving, latte art on table. "
        "Clothing: soft knit sweater or henley, dark jeans, clean casual style."
    ),
    "restaurant": (
        "Background: upscale restaurant, dim warm candlelight, dark wood and white linen, "
        "wine glass on table. "
        "Clothing: tailored dark shirt or blazer, smart evening look, subtle accessories."
    ),
    "bar_lounge": (
        "Background: modern cocktail lounge, moody amber and teal lighting, "
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
        "Background: Parisian boulevard with Eiffel Tower visible behind, "
        "morning golden light, cafe table with croissant and coffee visible. "
        "Clothing: fitted navy blazer over white tee, dark jeans, clean white sneakers."
    ),
    "nyc_brooklyn_bridge": (
        "Background: Brooklyn Bridge walkway at golden sunset, warm orange sky, "
        "Manhattan skyline visible behind. "
        "Clothing: casual fitted jacket, dark jeans, comfortable walking shoes."
    ),
    "rome_colosseum": (
        "Background: outdoor cafe terrace with Colosseum visible behind, "
        "warm Mediterranean afternoon light, cobblestone street visible. "
        "Clothing: linen shirt, light chinos, leather loafers, relaxed Italian style."
    ),
    "dubai_burj_khalifa": (
        "Background: modern Dubai boulevard with Burj Khalifa illuminated at blue hour, "
        "glass reflections, warm city lights, luxury urban atmosphere. "
        "Clothing: fitted dark shirt, tailored trousers, luxury watch, polished modern style."
    ),
    "nyc_times_square": (
        "Background: Times Square with vibrant billboards and neon lights, "
        "bustling energy, cinematic urban night atmosphere. "
        "Clothing: streetwear layers, statement jacket, fitted dark pants, designer sneakers."
    ),
    "barcelona_sagrada": (
        "Background: sunlit Barcelona terrace with Sagrada Familia spires in background, "
        "warm morning light, breakfast table with juice and pastries. "
        "Clothing: relaxed summer shirt, light chinos, straw hat, Mediterranean casual."
    ),
    "london_eye": (
        "Background: Thames embankment with London Eye visible in background, "
        "grey-blue London sky with golden patches, river reflections. "
        "Clothing: tailored overcoat or trench, dark scarf, smart casual British layers."
    ),
    "sydney_opera": (
        "Background: Sydney harbour with Opera House sails in background, "
        "sparkling blue water, bright Australian daylight. "
        "Clothing: casual smart outfit, fitted polo or button-down, clean summer style."
    ),
    "tokyo_tower": (
        "Background: minimalist Tokyo street with Tokyo Tower visible behind, "
        "cherry blossoms or clean urban aesthetic, diffused light. "
        "Clothing: minimal Japanese-inspired outfit, clean dark fitted layers."
    ),
    "sf_golden_gate": (
        "Background: Golden Gate Bridge at sunset with fog rolling in, "
        "warm orange and teal tones, Pacific Ocean behind. "
        "Clothing: fitted fleece or casual jacket, dark jeans, relaxed outdoor-casual style."
    ),
    "athens_acropolis": (
        "Background: narrow Athens street with Acropolis on hilltop in warm light, "
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
        "Background: Westminster with Big Ben and Parliament in background, "
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
        "Background: cozy late-night coffee shop interior, warm dim tungsten lighting, "
        "city lights visible through window, steaming cup on table. "
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
        "soft bokeh city lights beginning to glow, romantic open-air atmosphere. "
        "Clothing: fitted casual-smart outfit, clean lines, subtle accessories, date-ready polish."
    ),
    "tinder_pack_minimal_studio": (
        "Background: pure neutral studio backdrop soft grey-to-white gradient, "
        "even beauty-dish lighting, no clutter, portrait photographer setup. "
        "Clothing: simple fitted top in solid color, minimal jewelry, fresh grooming."
    ),
    "tinder_pack_cafe_window": (
        "Background: bright cafe interior by large window, natural daylight, "
        "plants and warm wood tones softly blurred behind. "
        "Clothing: relaxed smart-casual, soft sweater or crisp shirt, approachable style."
    ),
}

DATING_PERSONALITIES: dict[str, str] = {
    "warm_outdoor": "Soft relaxed eyes, warm approachable look, gentle natural expression.",
    "studio_elegant": "Strong direct gaze, calm self-assured energy, confident expression.",
    "near_car": "Direct assured gaze, subtle half-smile, confident relaxed energy.",
    "in_car": "Warm natural smile, easy confident energy, relaxed expression.",
    "motorcycle": "Strong direct gaze, calm rugged confidence, bold energy.",
    "yacht": "Wind-touched hair, warm bright smile, open carefree energy.",
    "rooftop_city": "Composed sophisticated gaze, subtle confident smile, polished energy.",
    "gym_fitness": "Healthy glow, energetic direct look, determined confident expression.",
    "running": "Fresh energetic expression, bright alert eyes, healthy athletic glow.",
    "tennis": "Confident sporty smile, sun-kissed healthy look, athletic energy.",
    "swimming_pool": "Natural tanned skin, warm easy smile, vacation energy.",
    "hiking": "Accomplished peaceful expression, adventurous bright-eyed energy.",
    "cafe": "Bright engaging eyes, magnetic energy, relaxed warm expression.",
    "coffee_date": "Gentle attentive smile, warm inviting eye contact, cozy energy.",
    "restaurant": "Charming engaged expression, sophisticated relaxed energy, warm gaze.",
    "bar_lounge": "Mysterious half-smile, magnetic confident energy, alluring gaze.",
    "cooking": "Genuine warm smile, approachable domestic charm, playful engaging eyes.",
    "dog_lover": "Genuine bright laugh, warm open expression, kind approachable energy.",
    "travel": "Easy composed smile, cosmopolitan energy, confident worldly expression.",
    "beach_sunset": "Warm sunset light on face, peaceful genuine smile, free relaxed energy.",
    "art_gallery": "Intellectual composed expression, subtle confident gaze, cultured refined energy.",
    "street_urban": "Effortless cool expression, bold urban energy, confident gaze.",
    "concert": "Passionate creative expression, magnetic artistic energy, soulful gaze.",
    # Landmarks
    "paris_eiffel": "Warm genuine smile, worldly romantic energy, relaxed morning gaze.",
    "nyc_brooklyn_bridge": "Wind in hair, warm sunset glow on face, adventurous confident smile.",
    "rome_colosseum": "Relaxed Mediterranean expression, warm open charm, easy-going energy.",
    "dubai_burj_khalifa": "Composed modern gaze, subtle power smile, cosmopolitan confident energy.",
    "nyc_times_square": "Bold confident expression, urban energy, effortless cool look.",
    "barcelona_sagrada": "Relaxed sun-kissed expression, bright genuine smile, warm Mediterranean energy.",
    "london_eye": "Thoughtful composed expression, subtle warm smile, elegant understated energy.",
    "sydney_opera": "Bright warm smile, fresh natural look, open confident energy.",
    "tokyo_tower": "Calm composed gaze, subtle confident expression, minimalist refined energy.",
    "sf_golden_gate": "Wind-touched hair, peaceful awe-inspired expression, adventurous warm smile.",
    "athens_acropolis": "Relaxed thoughtful expression, warm gentle smile, cultural explorer energy.",
    "singapore_marina_bay": "Polished confident gaze, subtle sophisticated smile, modern cosmopolitan energy.",
    "venice_san_marco": "Romantic composed expression, warm charming smile, elegant European energy.",
    "nyc_central_park": "Genuine bright smile, warm approachable look, easy natural energy.",
    "london_big_ben": "Composed British elegance, subtle confident smile, refined worldly energy.",
    # Travel expanded
    "airplane_window": "Relaxed contemplative gaze, calm easy smile, excited traveler energy.",
    "train_journey": "Focused relaxed expression, calm thoughtful energy, modern explorer vibe.",
    "hotel_checkin": "Warm confident smile, polished traveler energy, composed expression.",
    "hotel_breakfast": "Relaxed morning expression, warm genuine smile, luxury morning energy.",
    "sea_balcony": "Wind in hair, peaceful bright smile, warm morning energy.",
    "old_town_walk": "Curious warm expression, gentle smile, cultural wanderer energy.",
    "street_market": "Bright curious expression, warm genuine smile, adventurous explorer energy.",
    # Atmosphere expanded
    "rainy_day": "Contemplative gaze, mysterious half-smile, cinematic moody confidence.",
    "night_coffee": "Warm intimate gaze, gentle smile, cozy late-night thoughtful energy.",
    "evening_home": "Calm contented expression, warm genuine smile, comfortable domestic confidence.",
    # Status
    "car_exit": "Confident direct gaze, purposeful composed expression, polished energy.",
    "travel_luxury": "Composed confident expression, subtle assured smile, elevated energy.",
    # Sport expanded
    "yoga_outdoor": "Serene calm expression, gentle focused energy, healthy mindful glow.",
    "cycling": "Fresh energetic expression, bright confident smile, active outdoor energy.",
    "tinder_pack_rooftop_golden": "Warm confident smile, magnetic eye contact, relaxed romantic energy.",
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
        "dramatic directional spotlight. "
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
        "behind, dramatic spotlight from above. "
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
        "dramatic rim light from window, expansive view behind. "
        "Clothing: tailored dark suit, strong silhouette against bright window, executive presence."
    ),
    "doc_passport_neutral": (
        "Background: flat uniform light-grey or off-white wall, even frontal lighting, "
        "no shadows on backdrop, official document photo standard, centered head-and-shoulders crop feel. "
        "Clothing: conservative solid dark top, neat collar, minimal accessories, neutral professional grooming."
    ),
    "doc_visa_compliant": (
        "Background: plain white-to-light-grey seamless backdrop, bright even lighting, "
        "high clarity, embassy-style compliant framing, shoulders square to camera. "
        "Clothing: business formal shirt or blouse, understated tie optional, clean executive appearance."
    ),
    "doc_resume_headshot": (
        "Background: soft light-grey studio or bright blurred office bokeh, "
        "flattering three-quarter or frontal portrait light, LinkedIn-standard professionalism. "
        "Clothing: tailored blazer, crisp shirt, confident but approachable business attire."
    ),
    "photo_3x4": (
        f"{DOCUMENT_PHOTO_REALISM} "
        "Composition: 3:4 portrait framing, face fills about 70-80% of the frame with a small margin above the head. "
        "Background: clean uniform light tone (white or very soft neutral grey), no gradient. "
        "No headwear. "
        "Clothing: simple solid-color top with a neat collar."
    ),
    "passport_rf": (
        f"{DOCUMENT_PHOTO_REALISM} "
        "Composition: 7:9 portrait framing, frontal pose, face fills about 70-80% of the frame with a small margin above the head. "
        "Background: clean uniform white, no texture or shadows. "
        "Even symmetrical soft lighting, no strong side shadows. "
        "Clothing: simple dark solid-color top with a neat collar, no patterns or logos."
    ),
    "visa_eu": (
        f"{DOCUMENT_PHOTO_REALISM} "
        "Composition: 7:9 portrait framing, face centered and fills about 70-80% of the frame with a small margin above the head. "
        "Background: clean uniform white or very light grey, no shadows on the backdrop. "
        "Clear contrast between subject and background. "
        "Clothing: simple solid-color business top."
    ),
    "visa_us": (
        f"{DOCUMENT_PHOTO_REALISM} "
        "Composition: strictly 1:1 square framing, face centered, fills roughly 50-70% of the frame. "
        "Background: clean uniform white, soft even frontal lighting. "
        "Sharp high-resolution look, JPEG-friendly. "
        "Clothing: simple business top, no uniform, no headwear."
    ),
    "photo_4x6": (
        f"{DOCUMENT_PHOTO_REALISM} "
        "Composition: 2:3 portrait framing, face fills about 60-75% of the frame, relaxed top margin. "
        "Background: any clean light neutral tone (white, light grey or very light blue). "
        "Softer requirements, natural adaptable composition. "
        "Clothing: tidy semi-formal or formal top, solid neutral color."
    ),
}

CV_PERSONALITIES: dict[str, str] = {
    "corporate": "Trustworthy direct gaze, professional confident half-smile, composed energy.",
    "boardroom": "Authoritative composed expression, leadership energy, strong confident gaze.",
    "formal_portrait": "Steady composed direct gaze, neutral professional expression, timeless authority.",
    "creative": "Bold expressive energy, artistic confident expression.",
    "startup_casual": "Approachable energetic expression, relaxed innovative confidence.",
    "coworking": "Collaborative friendly expression, modern entrepreneurial energy.",
    "standing_desk": "Focused productive expression, tech-savvy composed confidence.",
    "neutral": "Relaxed, approachable, open and friendly gaze.",
    "tech_developer": "Alert focused expression, intelligent confident gaze, calm technical authority.",
    "creative_director": "Intense creative gaze, visionary confident expression, artistic authority.",
    "medical": "Warm empathetic expression, trustworthy caring gaze, calm medical authority.",
    "legal_finance": "Authoritative steady expression, distinguished gravitas, composed gaze.",
    "architect": "Precise analytical gaze, creative professional confidence, thoughtful expression.",
    "speaker_stage": "Engaging animated expression, commanding charismatic presence, confident energy.",
    "podcast": "Natural animated expression, engaging conversational energy, authentic approachable authority.",
    "mentor": "Warm encouraging expression, wise approachable mentor energy, attentive gaze.",
    "outdoor_business": "Confident relaxed smile, modern flexible professional energy.",
    # Career expanded
    "video_call": "Engaged expression, warm professional smile, confident screen presence, trustworthy energy.",
    "glass_wall_pose": "Composed powerful gaze, modern executive energy, confident expression.",
    "analytics_review": "Sharp analytical expression, slight concentration furrow, intelligent authority.",
    "tablet_stylus": "Focused creative expression, innovative gaze, modern productive energy.",
    "notebook_ideas": "Thoughtful inspired expression, subtle focused smile, creative productive energy.",
    "coffee_break_work": "Relaxed confident smile, approachable warm expression, human professional energy.",
    "late_hustle": "Focused determined expression, intense productive gaze, ambitious driven energy.",
    # Archetypes
    "quiet_expert": "Calm wise expression, subtle knowing smile, deep understated authority.",
    "digital_nomad": "Easy confident smile, free productive expression, relaxed modern energy.",
    "entrepreneur_on_move": "Dynamic confident expression, unstoppable momentum energy, sharp gaze.",
    "intellectual": "Thoughtful composed gaze, deep contemplative expression, scholarly refined energy.",
    "man_with_mission": "Strong direct gaze, determined composed expression, visionary leadership energy.",
    # Professional moments
    "before_meeting": "Focused composed gaze, subtle prepared smile, polished professional energy.",
    "between_meetings": "Relaxed but alert expression, composed ease, efficient professional energy.",
    "business_lounge": "Composed traveler expression, confident relaxed smile, premium professional energy.",
    "decision_moment": "Strong thoughtful expression, composed decisive energy, executive vision.",
    "doc_passport_neutral": "Neutral composed expression, mouth closed relaxed, direct even gaze, official photo calm.",
    "doc_visa_compliant": "Serious neutral expression, attentive steady gaze, formal compliant demeanor.",
    "doc_resume_headshot": "Warm professional half-smile, confident approachable gaze, trustworthy executive energy.",
    "photo_3x4": "Neutral composed expression, mouth closed, eyes open, direct forward gaze, calm official demeanor.",
    "passport_rf": "Strictly neutral expression, mouth closed relaxed, eyes fully open, direct even frontal gaze, official composure.",
    "visa_eu": "Serious neutral expression, attentive steady centered gaze, formal compliant demeanor, no smile.",
    "visa_us": "Neutral calm expression, direct steady gaze, mouth closed, composed official look, no expression.",
    "photo_4x6": "Neutral relaxed expression, direct natural gaze, calm composed demeanor, mouth closed.",
}

SOCIAL_STYLES: dict[str, str] = {
    # --- Influencer ---
    "influencer": (
        "Background: trendy urban rooftop at golden hour, city skyline visible, "
        "warm directional light with lens flare. "
        "Clothing: stylish streetwear, statement accessories, layered textures."
    ),
    "influencer_urban": (
        "Background: trendy urban rooftop at golden hour, city skyline visible, "
        "warm directional light with lens flare. "
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
        "city panorama, silhouette rim light from behind, dramatic scale. "
        "Clothing: minimal dark outfit, clean silhouette against bright cityscape."
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
        "at night, dramatic metropolitan atmosphere, warm interior accent light. "
        "Clothing: elegant dark outfit, silhouette against glowing city skyline."
    ),
    "after_work": (
        "Background: city sidewalk at dusk, warm streetlights beginning to glow, "
        "office buildings behind, golden-blue transition sky. "
        "Clothing: professional outfit slightly relaxed, jacket over shoulder, end-of-day vibe."
    ),
    "evening_planning": (
        "Background: home desk at evening, warm desk lamp light, notebook and tea, "
        "calm productivity atmosphere, dim window twilight behind. "
        "Clothing: comfortable smart-casual loungewear, focused domestic vibe."
    ),
    # --- Mood ---
    "focused_mood": (
        "Background: clean minimal backdrop with dramatic close-up framing, "
        "single directional light source creating depth and shadow on face. "
        "Clothing: minimal dark outfit, all attention drawn to face and expression."
    ),
    "light_irony": (
        "Background: urban setting with interesting visual juxtaposition, "
        "slightly playful atmosphere, warm natural light, architectural context. "
        "Clothing: smart casual with personality, slight quirk in style, self-aware modern look."
    ),
}

SOCIAL_PERSONALITIES: dict[str, str] = {
    "influencer": "Bright confident look, engaging direct eye contact, charismatic energy.",
    "influencer_urban": "Engaging direct eye contact, charismatic high-energy expression, bold confidence.",
    "influencer_minimal": "Calm confident gaze, serene sophisticated energy, poised expression.",
    "influencer_luxury": "Mysterious allure, sophisticated calm expression, elegant energy.",
    "luxury": "Elegant mysterious allure, sophisticated calm expression.",
    "casual": "Genuine relaxed look, warm natural feel, approachable open vibe.",
    "morning_routine": "Peaceful fresh morning expression, warm genuine relaxed smile.",
    "fitness_lifestyle": "Healthy glow, energetic bright expression, motivational confident energy.",
    "food_blogger": "Warm engaging expression, inviting energy, bright genuine smile.",
    "travel_blogger": "Excited adventurous expression, bright wanderlust energy, open smile.",
    "artistic": "Thoughtful creative gaze, expressive intensity, unconventional character.",
    "golden_hour": "Soft dreamy gaze, warm peaceful expression, ethereal golden-lit energy.",
    "neon_night": "Intense direct gaze, cinematic edgy energy, bold confident expression.",
    "vintage_film": "Nostalgic thoughtful gaze, gentle analog expression, timeless romantic energy.",
    "dark_moody": "Dramatic shadow-play on face, intense mysterious gaze, powerful brooding energy.",
    "pastel_soft": "Gentle soft smile, relaxed gentle energy, light airy expression.",
    "youtube_creator": "Animated engaging expression, bright enthusiastic creator energy.",
    "linkedin_premium": "Warm professional smile, trustworthy confident energy, approachable gaze.",
    "tinder_top": "Natural genuine smile, warm attractive easy-going energy.",
    "instagram_aesthetic": "Editorial confident expression, polished energy, striking gaze.",
    "podcast_host": "Natural conversational smile, engaging authentic host energy.",
    "creative_portrait": "Intense expressive gaze, bold artistic energy, striking expression.",
    # Social aesthetic
    "mirror_aesthetic": "Calm confident gaze, effortless polished energy, composed expression.",
    "elevator_clean": "Direct gaze, composed minimal expression, sharp modern energy.",
    "book_and_coffee": "Warm thoughtful expression, gentle intellectual smile, cozy wisdom energy.",
    "shopfront": "Natural fashion expression, confident modern street-style energy.",
    "candid_street": "Genuine unposed look, authentic spontaneous energy, natural expression.",
    # Hobbies
    "reading_home": "Peaceful concentrated expression, warm genuine comfort, domestic intellectual energy.",
    "reading_cafe": "Thoughtful calm expression, gentle content smile, quiet cultured energy.",
    "sketching": "Creative concentrated expression, artistic flow energy, focused gaze.",
    "photographer": "Focused creative expression, professional artistic energy, sharp gaze.",
    "meditation": "Serene peaceful expression, calm balanced energy, mindful presence.",
    "online_learning": "Engaged curious expression, productive concentration, growth-minded energy.",
    # Sport social
    "yoga_social": "Serene calm expression, healthy glow, peaceful mindful energy.",
    "cycling_social": "Fresh active expression, bright confident smile, healthy outdoor glow.",
    # Cinematic
    "panoramic_window": "Contemplative expression, profound calm gaze, cinematic scale energy.",
    "in_motion": "Confident forward gaze, dynamic unstoppable energy, bold expression.",
    "creative_insight": "Excited eureka expression, bright inspired eyes, energetic creative energy.",
    "architecture_shadow": "Mysterious confident expression, dramatic artistic presence, partial shadow.",
    "achievement_moment": "Genuine bright celebration expression, relieved proud smile, triumphant energy.",
    # Evening social
    "skyscraper_view": "Composed serene expression, elevated sophisticated energy, calm gaze.",
    "after_work": "Relaxed relief expression, easy warm smile, comfortable end-of-day energy.",
    "evening_planning": "Focused calm expression, quiet determination, productive evening energy.",
    # Mood
    "focused_mood": "Intense concentrated gaze, powerful focused presence, magnetic intensity.",
    "light_irony": "Subtle smirk, playful knowing expression, witty confident energy.",
}


# ---------------------------------------------------------------------------
# Typed style registry — built from the raw dicts above
# ---------------------------------------------------------------------------

STYLE_REGISTRY = StyleRegistry()

_STYLE_OVERRIDES: dict[tuple[str, str], dict] = {
    # Edit-incompatible: require impossible pose/geometry changes
    ("social", "mirror_aesthetic"): {"edit_compatible": False},
    ("social", "cycling_social"): {"edit_compatible": False},
    ("dating", "cycling"): {"edit_compatible": False},
    ("social", "in_motion"): {"edit_compatible": False},
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
    ))

for _key, _text in CV_STYLES.items():
    _pers = CV_PERSONALITIES.get(_key, "")
    _ovr = _STYLE_OVERRIDES.get(("cv", _key), {})
    STYLE_REGISTRY.register(build_spec_from_legacy(
        _key, "cv", _text, _pers,
        clothing_female_override=_ovr.get("clothing_female_override", ""),
        edit_compatible=_ovr.get("edit_compatible", True),
        complexity=_ovr.get("complexity", "simple"),
    ))

for _key, _text in SOCIAL_STYLES.items():
    _pers = SOCIAL_PERSONALITIES.get(_key, "")
    _ovr = _STYLE_OVERRIDES.get(("social", _key), {})
    STYLE_REGISTRY.register(build_spec_from_legacy(
        _key, "social", _text, _pers,
        clothing_female_override=_ovr.get("clothing_female_override", ""),
        edit_compatible=_ovr.get("edit_compatible", True),
        complexity=_ovr.get("complexity", "simple"),
    ))


# ---------------------------------------------------------------------------
# Prompt builders — Change -> Preserve -> Quality order
# Uses StyleSpec for structured, gender-aware prompt construction.
# ---------------------------------------------------------------------------

def _build_mode_prompt(mode: str, style: str, gender: str, change_instruction: str) -> str:
    """Shared builder logic for all modes using the typed StyleSpec registry."""
    spec = STYLE_REGISTRY.get_or_default(mode, style)
    clothing = spec.clothing_for(gender)
    if not spec.edit_compatible:
        bg = spec.background.split(",")[0] if "," in spec.background else spec.background
        return (
            f"{IDENTITY_FIRST} "
            f"{change_instruction} "
            f"{BACKGROUND_FOCUS} Background: {bg}. Clothing: {clothing}. "
            f"{spec.expression} "
            f"{BODY_ANCHOR} {SKIN_FIX} {FACE_ANCHOR} {CAMERA} {REALISM}"
        )
    return (
        f"{IDENTITY_FIRST} "
        f"{change_instruction} "
        f"{BACKGROUND_FOCUS} Background: {spec.background}. Clothing: {clothing}. "
        f"{spec.expression} "
        f"{BODY_ANCHOR} {SKIN_FIX} {FACE_ANCHOR} {CAMERA} {REALISM}"
    )


def build_dating_prompt(style: str = "", gender: str = "male") -> str:
    return _build_mode_prompt(
        "dating", style, gender,
        "Change ONLY background and clothing. Keep the person's face, pose, and body identical.",
    )


_DOCUMENT_STYLE_KEYS = frozenset({
    "photo_3x4",
    "passport_rf",
    "visa_eu",
    "visa_schengen",
    "visa_us",
    "photo_4x6",
    "driver_license",
})


def is_document_style(style: str) -> bool:
    """True для CV-стилей «Фото на документы», где требуется строгая композиция."""
    return (style or "").strip() in _DOCUMENT_STYLE_KEYS


def build_cv_prompt(style: str = "", gender: str = "male") -> str:
    style_key = (style or "").strip()
    if style_key in _DOCUMENT_STYLE_KEYS:
        change_instruction = (
            "Style: professional ID-style headshot. "
            "Replace only the background with a clean uniform neutral backdrop "
            "(white or very light grey, no shadows, no gradient). "
            "Replace clothing with a simple neutral top (solid white or light-grey shirt/blouse), "
            "no patterns, no accessories, no headwear; keep glasses only if already worn. "
            "Keep the person's face, hair, skin tone and body proportions the same as in the reference. "
            "Keep the head centered, shoulders straight, looking at the camera. "
            "Do not add makeup, do not smooth the skin, and do not change the expression beyond the style notes."
        )
    else:
        change_instruction = (
            "Change ONLY background and clothing to professional attire. "
            "Keep the person's face, pose, and body identical."
        )
    return _build_mode_prompt("cv", style_key, gender, change_instruction)


def build_social_prompt(style: str = "", gender: str = "male") -> str:
    return _build_mode_prompt(
        "social", style, gender,
        "Change ONLY background and clothing. Keep the person's face, pose, and body identical.",
    )


# ---------------------------------------------------------------------------
# Multi-pass step templates — same Change -> Preserve -> Quality order
# ---------------------------------------------------------------------------

STEP_TEMPLATES: dict[str, str] = {
    "background_edit": (
        f"{IDENTITY_FIRST} "
        "Change ONLY the background: {description}. "
        f"{BACKGROUND_FOCUS} "
        "Keep the person, clothing, pose, and body proportions identical. "
        f"{BODY_ANCHOR} {FACE_ANCHOR} {CAMERA} {REALISM}"
    ),
    "clothing_edit": (
        f"{IDENTITY_FIRST} "
        "Change ONLY the clothing: {description}. "
        f"{BACKGROUND_FOCUS} "
        "Keep face, background, pose, and body proportions identical. "
        f"{BODY_ANCHOR} {FACE_ANCHOR} {CAMERA} {REALISM}"
    ),
    "lighting_adjust": (
        f"{IDENTITY_FIRST} "
        "Improve ONLY lighting and color grading: {description}. "
        f"{BACKGROUND_FOCUS} "
        "Warm flattering light, natural studio quality, even skin tones. "
        f"{BODY_ANCHOR} {FACE_ANCHOR} {CAMERA} {REALISM}"
    ),
    "expression_hint": (
        f"{IDENTITY_FIRST} "
        "Subtle expression adjustment: {description}. "
        f"{BACKGROUND_FOCUS} "
        "Keep face shape, features, and original mouth identical. "
        f"{BODY_ANCHOR} {FACE_ANCHOR} {CAMERA} {REALISM}"
    ),
    "skin_correction": (
        f"{IDENTITY_FIRST} "
        "Minor skin tone correction and blemish removal. "
        f"{BACKGROUND_FOCUS} "
        "Keep all facial features identical. "
        f"{BODY_ANCHOR} {SKIN_FIX} {FACE_ANCHOR} {CAMERA} {REALISM}"
    ),
    "style_overall": (
        f"{IDENTITY_FIRST} "
        "Apply overall style enhancement: {description}. "
        f"{BACKGROUND_FOCUS} "
        "Cohesive style, crisp detail. Keep body proportions and pose identical. "
        f"{BODY_ANCHOR} {FACE_ANCHOR} {CAMERA} {REALISM}"
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
