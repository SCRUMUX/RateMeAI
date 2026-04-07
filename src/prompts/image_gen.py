"""Centralized image-generation prompt builder for all modes.

Prompt structure follows the Change -> Preserve -> Quality pattern
proven to achieve 91% first-attempt success in edit-mode models.
Constants use positive framing to avoid diffusion "NO Syndrome".
"""
from __future__ import annotations

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
    "SKIN: visible pores, natural texture, subtle imperfections, "
    "subsurface scattering on ears and cheeks, healthy glow, even tone. "
    "Remove only blemishes, dark circles, and acne."
)

CAMERA = (
    "Shot on Canon EOS R5, 85mm f/4, natural depth of field with visible "
    "background details. Natural color grading, Kodak Portra 400 tones."
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
        "soft rim light, natural green and water textures visible in background. "
        "Clothing: stylish casual, fitted, clean fabrics."
    ),
    "studio_elegant": (
        "Background: studio with soft gradient lighting, charcoal-to-warm-grey "
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
        "Background: interior of modern car, soft window light streaming through "
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
        "Background: tree-lined park path at early morning, soft diffused golden light, "
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
        "Background: contemporary art gallery, white walls with abstract art visible, "
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
        "cherry blossoms or clean urban aesthetic, soft diffused light. "
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
        "soft dappled sunlight through trees, green lawns and pathway. "
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
        "soft cabin light, tray table with book or headphones. "
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
        "marble and brass details, soft ambient warm lighting, premium interior. "
        "Clothing: elevated travel outfit, quality fabrics, leather accessories, luxury watch."
    ),
    # --- Sport expanded ---
    "yoga_outdoor": (
        "Background: outdoor yoga mat on green grass or beach at sunrise, "
        "soft morning golden light, serene natural landscape, calm atmosphere. "
        "Clothing: fitted clean athletic wear, barefoot, minimal yoga outfit."
    ),
    "cycling": (
        "Background: scenic road or park trail with bicycle nearby, "
        "golden morning light, green landscape, open sky. "
        "Clothing: fitted cycling jersey or casual athletic top, sport sunglasses, helmet nearby."
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
    # Landmarks
    "paris_eiffel": "Seated at cafe table, relaxed morning gaze toward tower, warm genuine smile, worldly romantic energy.",
    "nyc_brooklyn_bridge": "Walking along bridge, wind in hair, warm sunset glow on face, adventurous confident smile.",
    "rome_colosseum": "Leaning back in cafe chair, relaxed Mediterranean expression, warm open charm, easy-going Italian energy.",
    "dubai_burj_khalifa": "Standing with city behind, composed modern gaze, subtle power smile, cosmopolitan confident energy.",
    "nyc_times_square": "Hands in pockets mid-stride, bold confident expression, urban energy, effortless cool neon-lit look.",
    "barcelona_sagrada": "Seated at terrace breakfast, relaxed sun-kissed expression, bright genuine smile, warm Mediterranean morning.",
    "london_eye": "Walking along embankment, thoughtful composed expression, subtle warm smile, elegant understated energy.",
    "sydney_opera": "Relaxed harbour-side posture, bright warm smile, fresh natural look, open confident Australian energy.",
    "tokyo_tower": "Standing in clean urban setting, calm composed gaze, subtle confident expression, minimalist refined energy.",
    "sf_golden_gate": "Standing at viewpoint, wind-touched hair, peaceful awe-inspired expression, adventurous warm smile.",
    "athens_acropolis": "Walking through narrow street, relaxed thoughtful expression, warm gentle smile, cultural explorer energy.",
    "singapore_marina_bay": "Standing with skyline behind, polished confident gaze, subtle sophisticated smile, modern cosmopolitan energy.",
    "venice_san_marco": "Walking through piazza, romantic composed expression, warm charming smile, elegant European energy.",
    "nyc_central_park": "Relaxed walking pose, genuine bright smile, warm approachable look, easy natural park energy.",
    "london_big_ben": "Standing with landmark behind, composed British elegance, subtle confident smile, refined worldly energy.",
    # Travel expanded
    "airplane_window": "Seated with window view, relaxed contemplative gaze outside, calm easy smile, excited traveler energy.",
    "train_journey": "Working or gazing out window, focused relaxed expression, calm productivity, modern explorer energy.",
    "hotel_checkin": "Standing in lobby, confident composed posture, warm arrival smile, polished traveler energy.",
    "hotel_breakfast": "Seated at panoramic table, relaxed morning expression, warm genuine smile, luxury morning energy.",
    "sea_balcony": "Standing at railing, wind in hair, peaceful bright smile, warm morning sea-breeze energy.",
    "old_town_walk": "Walking on cobblestones, curious warm expression, gentle smile, cultural wanderer energy.",
    "street_market": "Engaged with surroundings, bright curious expression, warm genuine smile, adventurous explorer energy.",
    # Atmosphere expanded
    "rainy_day": "Walking in rain, contemplative gaze, mysterious half-smile, cinematic moody confidence.",
    "night_coffee": "Seated with cup, warm intimate gaze, gentle smile, cozy late-night thoughtful energy.",
    "evening_home": "Relaxed at home, calm contented expression, warm genuine smile, comfortable domestic confidence.",
    # Status
    "car_exit": "Stepping from car, confident direct gaze, purposeful composed expression, polished arrival energy.",
    "travel_luxury": "Standing in premium interior, composed confident posture, subtle assured smile, elevated travel energy.",
    # Sport expanded
    "yoga_outdoor": "Balanced peaceful pose, serene calm expression, gentle focused energy, healthy mindful glow.",
    "cycling": "Standing beside bike, fresh energetic expression, bright confident smile, active outdoor energy.",
}

CV_STYLES: dict[str, str] = {
    # --- Classic ---
    "corporate": (
        "Background: modern corner office, floor-to-ceiling windows with soft "
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
        "lighting with soft fill. "
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
        "Clothing: smart casual, fitted chinos, clean button-down with rolled sleeves, no tie."
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
        "Background: light-grey studio backdrop, even soft lighting from both sides, "
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
        "neat bookshelves behind, webcam-friendly framing, even soft lighting. "
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
        "clean modern interior, soft directional task light. "
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
        "Background: dimly lit office at night, monitor glow on face, city lights through "
        "window behind, focused determined atmosphere. "
        "Clothing: professional shirt with loosened collar, tie undone, determined focused look."
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
        "soft warm lighting, laptop and documents on table. "
        "Clothing: business-casual travel outfit, quality fabrics, polished accessories."
    ),
    "decision_moment": (
        "Background: standing at large window overlooking cityscape, contemplative atmosphere, "
        "dramatic rim light from window, expansive view behind. "
        "Clothing: tailored dark suit, strong silhouette against bright window, executive presence."
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
    # Career expanded
    "video_call": "Facing camera with engaged expression, warm professional smile, confident screen presence, trustworthy energy.",
    "glass_wall_pose": "Standing confidently at glass wall, arms relaxed, composed powerful gaze, modern executive energy.",
    "analytics_review": "Focused on data, sharp analytical expression, slight concentration furrow, intelligent authority.",
    "tablet_stylus": "Working with tablet, focused creative expression, innovative gaze, modern productive energy.",
    "notebook_ideas": "Writing in notebook, thoughtful inspired expression, subtle focused smile, creative productive energy.",
    "coffee_break_work": "Holding coffee, relaxed confident smile, approachable warm expression, human professional energy.",
    "late_hustle": "Focused determined expression, subtle jaw set, intense productive gaze, ambitious driven energy.",
    # Archetypes
    "quiet_expert": "Seated with book, calm wise expression, subtle knowing smile, deep understated authority.",
    "digital_nomad": "Relaxed at laptop with view, easy confident smile, free productive expression, location-independent energy.",
    "entrepreneur_on_move": "Walking with purpose, phone in hand, dynamic confident expression, unstoppable momentum energy.",
    "intellectual": "Thoughtful composed gaze, slight head tilt, deep contemplative expression, scholarly refined energy.",
    "man_with_mission": "Standing with purpose, strong direct gaze, determined composed expression, visionary leadership energy.",
    # Professional moments
    "before_meeting": "Ready confident posture, focused composed gaze, subtle prepared smile, polished professional energy.",
    "between_meetings": "Checking phone, relaxed but alert expression, composed ease, efficient professional energy.",
    "business_lounge": "Seated with laptop, composed traveler expression, confident relaxed smile, premium professional energy.",
    "decision_moment": "Contemplating cityscape, strong thoughtful profile, composed decisive expression, executive vision energy.",
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
        "Background: upscale hotel lobby or lounge, marble surfaces, soft amber light, "
        "velvet and brass details. "
        "Clothing: designer outfit, fine fabrics, luxury watch or minimal gold jewelry."
    ),
    # --- Lifestyle ---
    "luxury": (
        "Background: upscale lounge with marble surfaces, soft amber ambient "
        "light, velvet and brass details in background. "
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
        "in background, bright natural light. "
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
    # --- Social aesthetic ---
    "mirror_aesthetic": (
        "Background: clean modern full-length mirror, soft indirect lighting, "
        "minimal decor, aesthetically composed reflection setting. "
        "Clothing: curated outfit with clean lines, one statement piece, polished silhouette."
    ),
    "elevator_clean": (
        "Background: modern elevator interior, stainless steel or mirrored walls, "
        "even overhead lighting, clean minimal space. "
        "Clothing: fitted smart outfit, clean sharp silhouette, polished aesthetic."
    ),
    "book_and_coffee": (
        "Background: cozy aesthetic table setting with open book and coffee cup, "
        "soft warm light, textured surfaces, neutral tones. "
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
        "Background: cozy home corner with soft window light, comfortable armchair, "
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
        "soft natural light, plants, calm zen atmosphere. "
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
        "Background: creative workspace with mood boards and inspiration pinned around, "
        "warm intimate golden lamp lighting, eureka-moment atmosphere. "
        "Clothing: casual creative outfit, sleeves rolled, passionate engaged energy."
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
        "calm productivity atmosphere, soft window twilight behind. "
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
    # Social aesthetic
    "mirror_aesthetic": "Composed mirror selfie pose, calm confident gaze at reflection, effortless polished energy.",
    "elevator_clean": "Clean confident stance, direct gaze, composed minimal expression, sharp modern energy.",
    "book_and_coffee": "Relaxed with book, warm thoughtful expression, gentle intellectual smile, cozy wisdom energy.",
    "shopfront": "Walking past or pausing, natural fashion expression, confident modern street-style energy.",
    "candid_street": "Natural mid-action expression, genuine unposed look, authentic spontaneous energy.",
    # Hobbies
    "reading_home": "Absorbed in book, peaceful concentrated expression, warm genuine comfort, domestic intellectual energy.",
    "reading_cafe": "Reading with coffee, thoughtful calm expression, gentle content smile, quiet cultured energy.",
    "sketching": "Focused on drawing, creative concentrated expression, passionate hands at work, artistic flow energy.",
    "photographer": "Looking through viewfinder or reviewing shot, focused creative expression, professional artistic energy.",
    "meditation": "Eyes closed or soft focus, serene peaceful expression, calm balanced energy, mindful presence.",
    "online_learning": "Focused on screen, engaged curious expression, productive concentration, growth-minded energy.",
    # Sport social
    "yoga_social": "Balanced pose, serene calm expression, healthy glow, peaceful mindful athletic energy.",
    "cycling_social": "Fresh active expression, bright confident smile, healthy outdoor glow, athletic lifestyle energy.",
    # Cinematic
    "panoramic_window": "Standing before panorama, contemplative silhouette expression, profound calm gaze, cinematic scale energy.",
    "in_motion": "Dynamic walking expression, confident forward gaze, kinetic unstoppable energy.",
    "creative_insight": "Excited eureka expression, bright inspired eyes, energetic creative breakthrough energy.",
    "architecture_shadow": "Face partially in shadow, mysterious confident expression, dramatic artistic presence.",
    "achievement_moment": "Genuine bright celebration expression, relieved proud smile, triumphant authentic energy.",
    # Evening social
    "skyscraper_view": "Contemplating city lights, composed serene expression, elevated sophisticated energy.",
    "after_work": "Relaxed relief expression, easy warm smile, comfortable end-of-day energy.",
    "evening_planning": "Focused calm expression, quiet determination, productive evening energy.",
    # Mood
    "focused_mood": "Intense concentrated gaze, slight furrow, powerful focused presence, magnetic intensity.",
    "light_irony": "Subtle smirk, one eyebrow slightly raised, playful knowing expression, witty confident energy.",
}


# ---------------------------------------------------------------------------
# Prompt builders — Change -> Preserve -> Quality order
# ---------------------------------------------------------------------------

def build_dating_prompt(style: str = "") -> str:
    s = DATING_STYLES.get(style, DATING_STYLES["warm_outdoor"])
    p = DATING_PERSONALITIES.get(style, DATING_PERSONALITIES["warm_outdoor"])
    return (
        f"{IDENTITY_FIRST} "
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
        f"{IDENTITY_FIRST} "
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
        f"{IDENTITY_FIRST} "
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
        f"{IDENTITY_FIRST} "
        "Change ONLY the background: {description}. "
        "Keep the person, clothing, pose, and body proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {CAMERA} {REALISM}"
    ),
    "clothing_edit": (
        f"{IDENTITY_FIRST} "
        "Change ONLY the clothing and outfit: {description}. "
        "Keep face, background, pose, and body proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {CAMERA} {REALISM}"
    ),
    "lighting_adjust": (
        f"{IDENTITY_FIRST} "
        "Improve ONLY the lighting and color grading: {description}. "
        "Natural studio quality, even skin tones. "
        "Keep body, pose, and proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {CAMERA} {REALISM}"
    ),
    "expression_hint": (
        f"{IDENTITY_FIRST} "
        "Subtle expression adjustment: {description}. "
        "Keep face shape, features, and original mouth identical. "
        "Keep body pose and proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {SKIN_FIX} {CAMERA} {REALISM}"
    ),
    "skin_correction": (
        f"{IDENTITY_FIRST} "
        "Minor skin tone correction and blemish removal. "
        "Keep all facial features identical. "
        "Keep body pose and proportions identical. "
        f"{FACE_ANCHOR} {BODY_ANCHOR} {SKIN_FIX} {CAMERA} {REALISM}"
    ),
    "style_overall": (
        f"{IDENTITY_FIRST} "
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
