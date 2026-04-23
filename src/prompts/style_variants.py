"""Content variants for every non-document style, keyed by (mode, style).

Each entry contains 4 StyleVariant objects — short, positive-only fragments
that diversify the generation without touching identity anchors. They are
consumed by ``_build_mode_prompt`` in ``image_gen.py`` when a ``variant``
is resolved for the current request.

Document styles are intentionally not listed here: their scene must stay
rigorously uniform and any diversification would break compliance.
"""

from __future__ import annotations

from src.prompts.style_spec import StyleVariant


def _v(
    id_: str,
    scene: str,
    lighting: str,
    *,
    props: str = "",
    camera: str = "",
    male: str = "",
    female: str = "",
    weight: float = 1.0,
    concept: str = "",
) -> StyleVariant:
    # v1.18: variant ``id`` is already a short, unique slug per style
    # (e.g. ``park_golden``, ``neon_harbour``); if no explicit
    # ``concept`` was supplied we derive the concept_signature from
    # the id. Downstream tests + metrics use this for uniqueness
    # checks without every variant author having to duplicate the
    # slug in two places.
    return StyleVariant(
        id=id_,
        scene=scene,
        lighting=lighting,
        props=props,
        camera=camera,
        clothing_male_accent=male,
        clothing_female_accent=female,
        weight=weight,
        concept_signature=concept or id_,
    )


# v1.18 — additional concept rotations applied on top of every style's
# hand-written variants so every (mode, style) ships at least six
# conceptually distinct variants. These are deliberately abstract
# (lighting × time-of-day × camera) so they combine safely with any
# background description; the StyleRouter still uses the style's
# primary background and the PuLID / Seedream branches handle identity
# themselves. Each entry gets a unique concept_signature prefixed with
# ``rot_`` so tests can tell "synthesised rotation" apart from a
# hand-authored variant.
_ROTATION_POOL: tuple[StyleVariant, ...] = (
    StyleVariant(
        id="rot_blue_hour_cinematic",
        scene="same base setting at blue hour with subtle cinematic mood",
        lighting="blue-hour cinematic rim light with cool ambient fill",
        props="",
        camera="medium three-quarter shot at eye level",
        concept_signature="rot_blue_hour",
    ),
    StyleVariant(
        id="rot_overcast_soft",
        scene="same base setting under a soft overcast sky",
        lighting="soft overcast daylight, even natural diffusion",
        props="",
        camera="natural medium shot, slight three-quarter angle",
        concept_signature="rot_overcast",
    ),
    StyleVariant(
        id="rot_backlit_goldenrim",
        scene="same base setting with a warm backlit silhouette",
        lighting="strong warm backlight creating a golden rim on hair and shoulders",
        props="",
        camera="eye-level portrait framing",
        concept_signature="rot_backlit_gold",
    ),
    StyleVariant(
        id="rot_low_key_drama",
        scene="same base setting with a moody low-key palette",
        lighting="low-key dramatic key light with deep ambient shadow",
        props="",
        camera="subtle low-angle three-quarter shot",
        concept_signature="rot_low_key",
    ),
)


def _pad_variants(
    variants: tuple[StyleVariant, ...],
    *,
    target: int = 6,
) -> tuple[StyleVariant, ...]:
    """Return ``variants`` padded up to ``target`` conceptually distinct entries.

    Invariant: resulting tuple preserves original order and all existing
    ``concept_signature`` values remain unique. Padding entries are
    copied from ``_ROTATION_POOL`` with scene/clothing left empty so the
    base StyleSpec's description still drives composition; only
    lighting/camera are rotated to keep the concept different. No-op
    when the variants already meet the target or when the tuple is
    empty (document styles intentionally ship zero variants).
    """
    if not variants:
        return variants
    if len(variants) >= target:
        return variants
    seen = {(v.concept_signature or v.id or "") for v in variants}
    padded = list(variants)
    for extra in _ROTATION_POOL:
        if len(padded) >= target:
            break
        sig = extra.concept_signature or extra.id
        if sig in seen:
            continue
        seen.add(sig)
        padded.append(extra)
    return tuple(padded)


# ---------------------------------------------------------------------------
# Dating
# ---------------------------------------------------------------------------

DATING_VARIANTS: dict[str, tuple[StyleVariant, ...]] = {
    "warm_outdoor": (
        _v(
            "park_golden",
            "sunlit urban park with trees and pathway",
            "warm golden-hour backlight, soft rim highlights",
        ),
        _v(
            "waterfront_pier",
            "wooden pier at a calm lakefront",
            "low-angle amber sunset light, gentle reflections",
            camera="three-quarter medium shot",
        ),
        _v(
            "meadow_wildflowers",
            "open meadow with tall grass and wildflowers",
            "bright warm afternoon light, clear sky behind",
        ),
        _v(
            "autumn_alley",
            "leafy boulevard with autumn-gold foliage",
            "dappled afternoon light through tree canopy",
        ),
    ),
    "studio_elegant": (
        _v(
            "charcoal_gradient",
            "seamless charcoal-to-warm-grey studio backdrop",
            "smooth even key light with soft fill",
        ),
        _v(
            "deep_burgundy",
            "deep burgundy painted studio wall",
            "single directional warm key with subtle rim",
        ),
        _v(
            "soft_grey_panel",
            "matte soft-grey panel backdrop",
            "wide diffused beauty-dish style lighting",
        ),
        _v(
            "warm_amber_wall",
            "warm amber textured wall in photo studio",
            "golden backlight with classic portrait fill",
        ),
    ),
    "near_car": (
        _v(
            "sports_boulevard",
            "matte black sports car on a sunlit city boulevard",
            "warm golden reflections on polished paint",
            male="aviator sunglasses resting on head",
            female="aviator sunglasses resting on head",
        ),
        _v(
            "vintage_coupe_alley",
            "vintage coupe parked in a cobblestone alley",
            "soft afternoon light, warm brick tones",
        ),
        _v(
            "luxury_sedan_lot",
            "luxury sedan on a marina parking lot at golden hour",
            "warm backlight, gentle lens flare",
        ),
        _v(
            "suv_mountain_road",
            "premium SUV parked on a mountain viewpoint",
            "bright natural daylight, cool air clarity",
        ),
    ),
    "in_car": (
        _v(
            "morning_drive",
            "interior of a modern car on a quiet morning road",
            "diffused cool window light, steering wheel in view",
        ),
        _v(
            "city_window",
            "modern car interior on a city street",
            "warm reflections through the windshield",
        ),
        _v(
            "golden_hour_ride",
            "leather-trimmed car cabin at golden hour",
            "amber sunlight streaming through side window",
        ),
        _v(
            "coastal_cabin",
            "modern car cabin with coastline blurred outside",
            "bright natural daylight, soft sea blue tones",
        ),
    ),
    "motorcycle": (
        _v(
            "empty_coast_road",
            "matte-black motorcycle on an empty coastal road",
            "warm golden-hour backlight, calm sea behind",
        ),
        _v(
            "desert_highway",
            "motorcycle on a desert highway at sunset",
            "rich orange sidelight, long shadows",
        ),
        _v(
            "forest_curve",
            "sports motorcycle on a forest road curve",
            "soft dappled afternoon light through pines",
        ),
        _v(
            "urban_tunnel",
            "motorcycle parked near a modern urban underpass",
            "cool directional daylight with warm accent",
        ),
    ),
    "yacht": (
        _v(
            "turquoise_open_sea",
            "yacht deck above turquoise open sea",
            "bright midday sun, sparkling water",
        ),
        _v(
            "sunset_marina",
            "yacht deck moored in a luxury marina at sunset",
            "warm amber sidelight, reflective water",
        ),
        _v(
            "morning_coast",
            "yacht deck along a rocky coastline at morning",
            "soft cool morning light, fresh clarity",
        ),
        _v(
            "golden_hour_bay",
            "yacht deck in a quiet bay at golden hour",
            "warm low-angle sunlight, gentle ripples",
        ),
    ),
    "rooftop_city": (
        _v(
            "blue_hour_skyline",
            "rooftop terrace with city skyline at blue hour",
            "deep blue sky with warm city lights",
        ),
        _v(
            "sunset_panorama",
            "rooftop terrace overlooking a sunset panorama",
            "amber golden-hour backlight, long warm shadows",
        ),
        _v(
            "night_lights",
            "rooftop lounge at night above illuminated avenues",
            "warm ambient bulbs, sharp distant city lights",
        ),
        _v(
            "morning_city",
            "rooftop terrace at morning above a waking city",
            "soft cool diffused dawn light",
        ),
    ),
    "gym_fitness": (
        _v(
            "modern_weight_room",
            "modern gym weight area with matte equipment",
            "even overhead LED light with clean fill",
        ),
        _v(
            "functional_turf",
            "functional training floor with turf and kettlebells",
            "bright directional daylight from wide windows",
        ),
        _v(
            "mirror_studio",
            "minimalist gym studio with mirrored wall",
            "warm soft directional light, polished reflections",
        ),
        _v(
            "outdoor_calisthenics",
            "outdoor calisthenics park at golden hour",
            "warm low-angle sunlight, soft long shadows",
        ),
    ),
    "running": (
        _v(
            "forest_trail",
            "forest running trail with wood boards and pine trees",
            "dappled morning light through the canopy",
        ),
        _v(
            "beach_shoreline",
            "wet shoreline of a wide sandy beach",
            "warm sunrise backlight, gentle waves behind",
        ),
        _v(
            "city_embankment",
            "river embankment running path through a city",
            "soft cool morning light with sharp distant skyline",
        ),
        _v(
            "mountain_track",
            "alpine running track through green meadows",
            "crisp bright daylight, clear mountain air",
        ),
    ),
    "tennis": (
        _v(
            "blue_hard_court",
            "outdoor blue hard court with clean lines",
            "bright warm afternoon sunlight",
        ),
        _v(
            "clay_court",
            "red-clay tennis court at a sunny club",
            "warm directional afternoon light, long shadows",
        ),
        _v(
            "green_grass_court",
            "grass tennis court with classic green fencing",
            "soft bright afternoon light with slight haze",
        ),
        _v(
            "indoor_training",
            "indoor tennis training hall with wood ceiling",
            "even warm overhead lighting, clean interior",
        ),
    ),
    "swimming_pool": (
        _v(
            "infinity_rooftop",
            "rooftop infinity pool overlooking a skyline",
            "warm golden-hour backlight, sparkling water",
        ),
        _v(
            "tropical_villa",
            "tropical villa pool surrounded by palms",
            "bright midday sunlight, turquoise reflections",
        ),
        _v(
            "morning_lane_pool",
            "quiet lap pool with morning mist rising",
            "soft cool morning light, calm surface",
        ),
        _v(
            "spa_indoor_pool",
            "modern indoor spa pool with stone walls",
            "warm ambient amber pool lights",
        ),
    ),
    "hiking": (
        _v(
            "summit_viewpoint",
            "alpine summit viewpoint above misty valleys",
            "crisp bright daylight, cool mountain air",
        ),
        _v(
            "forest_ridge",
            "forest ridge trail with pines and a distant valley",
            "warm golden hour light between trees",
        ),
        _v(
            "lake_trail",
            "hiking trail by a clear mountain lake",
            "bright morning light with soft reflections",
        ),
        _v(
            "desert_canyon",
            "red-rock desert canyon trail",
            "warm late-afternoon sidelight, long warm shadows",
        ),
    ),
    "cafe": (
        _v(
            "artisan_corner",
            "cozy artisan cafe corner with shelves of ceramics",
            "warm window light, soft amber ambience",
            props="cup of coffee on a wooden table",
        ),
        _v(
            "bright_window_seat",
            "bright cafe window seat with potted plants",
            "diffused cool morning daylight",
        ),
        _v(
            "industrial_loft",
            "industrial loft cafe with exposed brick",
            "warm hanging bulbs with gentle spot lighting",
        ),
        _v(
            "scandi_minimal",
            "Scandinavian minimal cafe with pale wood",
            "soft even daylight, clean white surfaces",
        ),
    ),
    "coffee_date": (
        _v(
            "sunny_terrace",
            "sunny outdoor cafe terrace with greenery",
            "warm golden-hour sunlight filtering through leaves",
            props="two coffee cups on the table",
        ),
        _v(
            "window_booth",
            "window booth in a wood-trimmed cafe",
            "bright cool daylight through the window",
        ),
        _v(
            "rainy_cafe",
            "cozy cafe interior with rain-speckled window",
            "warm amber pendant lights, soft window glow",
        ),
        _v(
            "beach_kiosk",
            "wooden beach cafe kiosk near the dunes",
            "warm afternoon sun, sandy-white reflections",
        ),
    ),
    "restaurant": (
        _v(
            "fine_dining",
            "upscale fine-dining room with linen tables",
            "warm amber chandelier light with soft fill",
        ),
        _v(
            "trattoria_warm",
            "rustic trattoria with brick and wood interior",
            "warm candlelight accents, soft ambient glow",
        ),
        _v(
            "glass_terrace",
            "glass-walled restaurant terrace above a river",
            "soft blue-hour light with interior warmth",
        ),
        _v(
            "wine_cellar",
            "intimate wine-cellar dining nook with arched ceiling",
            "warm directional lamp light, rich shadows",
        ),
    ),
    "bar_lounge": (
        _v(
            "speakeasy_mood",
            "speakeasy bar with dark wood and leather",
            "warm tungsten ambient light, subtle rim",
        ),
        _v(
            "rooftop_cocktails",
            "rooftop cocktail bar with skyline behind",
            "blue-hour sky with warm candle accents",
        ),
        _v(
            "marble_counter",
            "marble-counter lounge bar with gold accents",
            "warm amber low-angle lighting",
        ),
        _v(
            "neon_lounge",
            "modern lounge with subtle neon accent lighting",
            "cool teal ambient with warm spot highlights",
        ),
    ),
    "cooking": (
        _v(
            "chef_kitchen",
            "bright modern chef kitchen with marble counters",
            "warm overhead lighting, fresh herbs on counter",
            props="wooden cutting board and vegetables",
        ),
        _v(
            "rustic_hearth",
            "rustic kitchen with stone hearth",
            "warm directional window light, copper pans",
        ),
        _v(
            "outdoor_grill",
            "outdoor garden kitchen with grill",
            "warm golden-hour backlight, fresh greens behind",
        ),
        _v(
            "loft_kitchen",
            "industrial loft kitchen with exposed beams",
            "bright daylight from tall windows",
        ),
    ),
    "dog_lover": (
        _v(
            "park_meadow",
            "grassy park meadow with a friendly golden retriever",
            "warm late-afternoon sunlight, soft backlight",
        ),
        _v(
            "city_walk",
            "tree-lined city street with a medium-sized dog",
            "bright cool daylight, dappled tree shadows",
        ),
        _v(
            "beach_shore",
            "sandy beach shoreline with a playful dog",
            "warm sunset backlight, gentle surf",
        ),
        _v(
            "home_sofa",
            "bright living room with a small dog on a sofa",
            "warm window light, cozy domestic ambience",
        ),
    ),
    "travel": (
        _v(
            "airport_lounge",
            "premium airport lounge with large windows",
            "warm ambient light with bright daylight outside",
        ),
        _v(
            "cobble_old_town",
            "cobblestone street in a historic old town",
            "warm golden-hour side light on stone walls",
        ),
        _v(
            "mountain_train",
            "mountain train platform with alpine view",
            "bright crisp daylight with cool shadows",
        ),
        _v(
            "coastal_viewpoint",
            "coastal viewpoint overlooking a turquoise bay",
            "bright midday sunlight, sparkling water",
        ),
    ),
    "beach_sunset": (
        _v(
            "tropical_palms",
            "tropical beach with palm silhouettes",
            "warm pink-orange sunset sky",
        ),
        _v(
            "pacific_cliffs",
            "pacific coast beach with coastal cliffs behind",
            "deep amber sunset light, crashing waves",
        ),
        _v(
            "white_sand_pier",
            "white-sand beach with a distant wooden pier",
            "soft warm low-angle sunlight",
        ),
        _v(
            "dune_ridge",
            "dune ridge above a wide empty beach",
            "golden-hour backlight with long sand shadows",
        ),
    ),
    "art_gallery": (
        _v(
            "white_cube",
            "white-cube gallery with large colorful paintings",
            "warm track lighting on paintings",
        ),
        _v(
            "modern_sculpture",
            "modern gallery wing with sculptures",
            "soft even daylight from skylights",
        ),
        _v(
            "classical_hall",
            "classical museum hall with gilded frames",
            "warm ambient amber light with spot accents",
        ),
        _v(
            "concrete_gallery",
            "concrete industrial gallery space",
            "clean directional gallery lighting on art",
        ),
    ),
    "street_urban": (
        _v(
            "brick_alley",
            "narrow urban alley with brick walls and murals",
            "warm directional side light",
        ),
        _v(
            "concrete_crossing",
            "modern concrete pedestrian crossing",
            "bright cool midday daylight with sharp shadows",
        ),
        _v(
            "graffiti_wall",
            "graffiti-covered wall with vivid colors",
            "warm afternoon sun, saturated tones",
        ),
        _v(
            "neon_underpass",
            "modern underpass with ambient neon tubes",
            "cool neon glow with warm accent spots",
        ),
    ),
    "concert": (
        _v(
            "rock_stage",
            "rock concert stage with silhouetted crowd",
            "warm amber stage lights with crisp rim",
        ),
        _v(
            "festival_golden",
            "open-air festival field at golden hour",
            "warm low-angle sunlight with stage visible behind",
        ),
        _v(
            "intimate_club",
            "intimate club venue with small stage",
            "warm spotlights with soft crowd glow",
        ),
        _v(
            "orchestra_hall",
            "classical concert hall with tiered seating",
            "warm ambient uplighting, rich wood tones",
        ),
    ),
    # --- Landmarks ---
    "paris_eiffel": (
        _v(
            "morning_river",
            "Seine river embankment with Eiffel Tower visible",
            "soft morning light, cool river tones",
        ),
        _v(
            "trocadero_sunset",
            "Trocadero square facing the Eiffel Tower",
            "warm sunset sidelight on Parisian stone",
        ),
        _v(
            "garden_pathway",
            "Champ de Mars garden pathway toward the tower",
            "bright afternoon daylight, green lawns",
        ),
        _v(
            "night_sparkle",
            "Seine bridge with Eiffel Tower in sharp detail at blue hour",
            "warm city lights on distant tower",
        ),
    ),
    "nyc_brooklyn_bridge": (
        _v(
            "sunrise_walkway",
            "Brooklyn Bridge walkway at sunrise",
            "soft warm sunrise backlight with cool shadows",
        ),
        _v(
            "golden_river",
            "Brooklyn Bridge with East River sparkling behind",
            "warm golden-hour light with skyline visible",
        ),
        _v(
            "blue_hour_lights",
            "Brooklyn Bridge at blue hour with city lights on",
            "warm bridge lamps with deep blue sky",
        ),
        _v(
            "morning_skyline",
            "Brooklyn Bridge walkway with Manhattan skyline",
            "bright cool morning daylight",
        ),
    ),
    "rome_colosseum": (
        _v(
            "morning_stones",
            "piazza in front of the Colosseum at morning",
            "soft warm morning light on ancient stone",
        ),
        _v(
            "sunset_arcades",
            "Colosseum arcades glowing at sunset",
            "warm amber sidelight on weathered walls",
        ),
        _v(
            "cypress_viewpoint",
            "Palatine hill viewpoint with Colosseum behind",
            "warm afternoon sunlight, cypress silhouettes",
        ),
        _v(
            "cobble_alley",
            "cobblestone street framing the Colosseum",
            "dappled late-afternoon light",
        ),
    ),
    "dubai_burj_khalifa": (
        _v(
            "downtown_fountain",
            "Downtown Dubai fountain plaza with Burj Khalifa",
            "warm sunset reflections on polished stone",
        ),
        _v(
            "skybridge_panorama",
            "skybridge terrace facing the Burj Khalifa",
            "bright desert daylight, glass reflections",
        ),
        _v(
            "blue_hour_towers",
            "Downtown Dubai avenue at blue hour",
            "warm city lights against deep blue sky",
        ),
        _v(
            "desert_overlook",
            "distant overlook with Burj Khalifa on horizon",
            "warm afternoon haze, golden tones",
        ),
    ),
    "nyc_times_square": (
        _v(
            "neon_crosswalk",
            "Times Square crosswalk with illuminated billboards",
            "vivid neon color with warm accent glow",
        ),
        _v(
            "morning_street",
            "Times Square at morning with softer foot traffic",
            "soft cool daylight with sharp signage",
        ),
        _v(
            "rain_reflections",
            "Times Square pavement reflecting billboard lights",
            "rain-wet reflections with saturated neon",
        ),
        _v(
            "blue_hour_signs",
            "Times Square at blue hour, signs blazing",
            "deep blue sky with bright screens",
        ),
    ),
    "barcelona_sagrada": (
        _v(
            "front_plaza",
            "plaza in front of the Sagrada Familia",
            "warm afternoon light on ornate facade",
        ),
        _v(
            "park_side",
            "park with palm trees framing Sagrada Familia",
            "bright Mediterranean daylight",
        ),
        _v(
            "sunset_spires",
            "Sagrada Familia spires glowing at sunset",
            "warm amber backlight on stone detail",
        ),
        _v(
            "blue_hour_facade",
            "Sagrada Familia facade at blue hour",
            "warm uplit stone with deep blue sky",
        ),
    ),
    "london_eye": (
        _v(
            "thames_walk",
            "South Bank walkway with London Eye behind",
            "soft cool afternoon daylight",
        ),
        _v(
            "sunset_river",
            "London Eye reflecting in the Thames at sunset",
            "warm sunset sidelight, gentle river tones",
        ),
        _v(
            "night_lights",
            "illuminated London Eye at night",
            "warm lamp light with cool blue river behind",
        ),
        _v(
            "morning_mist",
            "London Eye through morning mist over the Thames",
            "soft diffused cool morning light",
        ),
    ),
    "sydney_opera": (
        _v(
            "harbor_promenade",
            "harbor promenade facing the Sydney Opera House",
            "warm afternoon light on sail-shapes",
        ),
        _v(
            "ferry_view",
            "Sydney ferry deck view of the Opera House",
            "bright midday sunlight, sparkling water",
        ),
        _v(
            "blue_hour_sails",
            "Opera House sails at blue hour",
            "warm uplighting with deep blue sky",
        ),
        _v(
            "botanical_viewpoint",
            "Royal Botanic Garden viewpoint with Opera House",
            "warm golden-hour backlight, green lawns",
        ),
    ),
    "tokyo_tower": (
        _v(
            "park_pathway",
            "park pathway with Tokyo Tower behind cherry trees",
            "soft afternoon light, pink cherry accents",
        ),
        _v(
            "blue_hour_skyline",
            "Tokyo rooftop with Tokyo Tower at blue hour",
            "warm tower lights against deep blue sky",
        ),
        _v(
            "night_streets",
            "Tokyo neighborhood street with tower visible",
            "warm street lamps with cool night sky",
        ),
        _v(
            "morning_shrine",
            "Zojoji temple grounds with Tokyo Tower behind",
            "soft warm morning light on temple stone",
        ),
    ),
    "sf_golden_gate": (
        _v(
            "battery_viewpoint",
            "Battery Spencer viewpoint with Golden Gate bridge",
            "warm golden-hour light, coastal haze",
        ),
        _v(
            "fog_rolling",
            "Golden Gate bridge with rolling morning fog",
            "soft diffused cool light, muted tones",
        ),
        _v(
            "sunset_bay",
            "bay viewpoint with Golden Gate silhouette at sunset",
            "deep amber backlight, sparkling water",
        ),
        _v(
            "bridge_walkway",
            "pedestrian walkway of the Golden Gate bridge",
            "bright afternoon daylight, red steel tones",
        ),
    ),
    "athens_acropolis": (
        _v(
            "plaka_street",
            "Plaka cobblestone street with the Acropolis above",
            "warm afternoon sidelight on white stone",
        ),
        _v(
            "sunset_hill",
            "Areopagus hill with Parthenon glowing at sunset",
            "warm amber backlight, long stone shadows",
        ),
        _v(
            "morning_columns",
            "Acropolis terrace near marble columns",
            "soft warm morning light on weathered stone",
        ),
        _v(
            "cafe_rooftop",
            "rooftop cafe with the Acropolis in view",
            "warm golden-hour light, Mediterranean tones",
        ),
    ),
    "singapore_marina_bay": (
        _v(
            "skypark_panorama",
            "Skypark pool deck with Marina Bay skyline",
            "warm sunset sidelight, reflective water",
        ),
        _v(
            "helix_bridge",
            "Helix Bridge walkway with Marina Bay Sands behind",
            "blue-hour sky with warm bridge lights",
        ),
        _v(
            "gardens_bay",
            "Gardens by the Bay walkway with supertrees",
            "colorful evening uplighting with warm accents",
        ),
        _v(
            "merlion_morning",
            "Merlion Park with Marina Bay skyline behind",
            "soft bright morning light, sparkling water",
        ),
    ),
    "venice_san_marco": (
        _v(
            "morning_piazza",
            "St Mark's Square at quiet morning",
            "soft warm morning light on marble",
        ),
        _v(
            "gondola_canal",
            "Grand Canal with gondolas near St Mark's",
            "warm afternoon light on water",
        ),
        _v(
            "campanile_sunset",
            "St Mark's campanile glowing at sunset",
            "warm amber backlight on red brick",
        ),
        _v(
            "rialto_bridge",
            "Rialto bridge with canal stretched behind",
            "warm golden-hour light on stone arch",
        ),
    ),
    "nyc_central_park": (
        _v(
            "bow_bridge",
            "Central Park Bow Bridge over calm water",
            "warm afternoon light with skyline visible",
        ),
        _v(
            "autumn_pathway",
            "Central Park autumn pathway with golden foliage",
            "warm low-angle sunlight through leaves",
        ),
        _v(
            "summer_meadow",
            "Sheep Meadow in Central Park with skyline behind",
            "bright summer daylight, green grass",
        ),
        _v(
            "boathouse_morning",
            "Central Park Loeb Boathouse at morning",
            "soft cool morning light, lake reflections",
        ),
    ),
    "london_big_ben": (
        _v(
            "westminster_bridge",
            "Westminster Bridge with Big Ben visible",
            "warm afternoon sidelight on stonework",
        ),
        _v(
            "blue_hour_tower",
            "Big Ben clock tower at blue hour",
            "warm uplit tower with deep blue sky",
        ),
        _v(
            "parliament_square",
            "Parliament Square walkway facing Big Ben",
            "soft cool morning light, historic stone",
        ),
        _v(
            "thames_embankment",
            "Thames embankment with Big Ben reflected",
            "warm golden-hour light, gentle river tones",
        ),
    ),
    # --- Travel scenes ---
    "airplane_window": (
        _v(
            "cloud_ocean",
            "business-class window seat above a sea of clouds",
            "bright high-altitude sunlight, cool tones",
        ),
        _v(
            "sunset_wing",
            "window seat with wing and sunset horizon",
            "deep amber sunset light, long cabin shadows",
        ),
        _v(
            "morning_takeoff",
            "window seat during morning ascent",
            "soft cool morning light from the window",
        ),
        _v(
            "blue_hour_flight",
            "window seat with distant city lights at blue hour",
            "warm cabin accent with deep blue sky outside",
        ),
    ),
    "train_journey": (
        _v(
            "mountain_window",
            "intercity train cabin with alpine scenery outside",
            "bright crisp daylight through the window",
        ),
        _v(
            "coast_rail",
            "coastal train with sea view through window",
            "warm afternoon sunlight, sparkling water",
        ),
        _v(
            "night_express",
            "night train cabin with distant city lights passing",
            "warm cabin lamp light with cool outside",
        ),
        _v(
            "autumn_fields",
            "countryside train with autumn fields outside",
            "warm golden-hour light through the window",
        ),
    ),
    "hotel_checkin": (
        _v(
            "marble_lobby",
            "marble hotel lobby with concierge desk",
            "warm amber ambient light with crystal accents",
        ),
        _v(
            "design_hotel",
            "modern design-hotel reception with wood accents",
            "soft directional warm light, clean surfaces",
        ),
        _v(
            "boutique_entrance",
            "boutique hotel entrance with plants",
            "warm daylight with soft interior glow",
        ),
        _v(
            "rooftop_checkin",
            "rooftop hotel check-in with city view",
            "bright afternoon light, skyline behind",
        ),
    ),
    "hotel_breakfast": (
        _v(
            "terrace_sea",
            "hotel breakfast terrace overlooking the sea",
            "warm golden morning light, sparkling water",
        ),
        _v(
            "garden_cafe",
            "garden breakfast cafe with potted plants",
            "bright soft morning daylight",
        ),
        _v(
            "wood_dining",
            "wood-trimmed hotel dining room",
            "warm ambient light with natural window glow",
        ),
        _v(
            "rooftop_brunch",
            "rooftop brunch deck with city skyline",
            "warm morning sunlight, fresh clarity",
        ),
    ),
    "sea_balcony": (
        _v(
            "villa_sunset",
            "coastal villa balcony at sunset",
            "deep amber sunset light, calm sea behind",
        ),
        _v(
            "morning_coast",
            "balcony overlooking coast in the morning",
            "soft cool morning light with distant cliffs",
        ),
        _v(
            "greek_island",
            "whitewashed balcony on a Greek island",
            "bright Mediterranean daylight, turquoise sea",
        ),
        _v(
            "tropical_deck",
            "tropical resort balcony with palms",
            "warm afternoon sunlight, coconut breeze mood",
        ),
    ),
    "old_town_walk": (
        _v(
            "cobble_morning",
            "medieval old-town cobblestone street at morning",
            "soft warm morning sidelight on stone",
        ),
        _v(
            "colorful_lane",
            "colorful Mediterranean old-town lane",
            "warm afternoon light on painted facades",
        ),
        _v(
            "arched_alley",
            "stone-arched alley in a historic old town",
            "dappled sidelight through the arches",
        ),
        _v(
            "quiet_square",
            "quiet historic square with a central fountain",
            "warm golden-hour light, long soft shadows",
        ),
    ),
    "street_market": (
        _v(
            "asian_night_market",
            "bustling Asian night market with lanterns",
            "warm lantern light with cool shadows",
        ),
        _v(
            "morning_bazaar",
            "colorful morning bazaar with fresh produce",
            "bright warm morning daylight, vivid colors",
        ),
        _v(
            "european_flowers",
            "European flower market with potted blooms",
            "soft warm midday sunlight",
        ),
        _v(
            "spice_souk",
            "aromatic spice souk alley with piled spices",
            "warm ambient light with rich earth tones",
        ),
    ),
    "rainy_day": (
        _v(
            "umbrella_street",
            "wet city street with reflective pavement and umbrellas",
            "soft cool overcast light with warm shop windows",
        ),
        _v(
            "cafe_window",
            "cozy cafe window with rain streaks outside",
            "warm interior lamp light with cool window glow",
        ),
        _v(
            "plaza_reflections",
            "plaza pavement reflecting illuminated storefronts",
            "warm lamp reflections with cool ambient rain light",
        ),
        _v(
            "covered_arcade",
            "covered city arcade beside rainy street",
            "warm ambient arcade light with cool exterior",
        ),
    ),
    "night_coffee": (
        _v(
            "vintage_counter",
            "vintage cafe counter at night with copper espresso machine",
            "warm tungsten pendant light",
        ),
        _v(
            "modern_kiosk",
            "modern glass coffee kiosk on a night street",
            "cool street lights with warm interior glow",
        ),
        _v(
            "rooftop_espresso",
            "rooftop coffee bar with city lights behind",
            "warm amber lamps with distant neon",
        ),
        _v(
            "library_cafe",
            "library cafe corner with bookshelves at night",
            "warm reading-lamp light with soft shadows",
        ),
    ),
    "evening_home": (
        _v(
            "warm_living_room",
            "cozy living room with soft sofa and plants",
            "warm lamp light with faint cool window tones",
        ),
        _v(
            "loft_kitchen",
            "modern loft kitchen at evening",
            "warm pendant lights over kitchen island",
        ),
        _v(
            "reading_corner",
            "reading corner with a throw blanket",
            "warm directional reading-lamp light",
        ),
        _v(
            "balcony_dusk",
            "small balcony at dusk with warm lamp",
            "warm golden light with cool twilight sky",
        ),
    ),
    "car_exit": (
        _v(
            "hotel_portico",
            "luxury hotel portico with sedan beside",
            "warm amber canopy light",
        ),
        _v(
            "event_redcarpet",
            "event entrance with warm event lighting",
            "warm directional lamp light, stylish ambience",
        ),
        _v(
            "rooftop_garage",
            "sleek rooftop garage at golden hour",
            "warm low-angle sunlight on polished car",
        ),
        _v(
            "night_boulevard",
            "sleek sedan at a modern night boulevard",
            "cool city lights with warm accent beams",
        ),
    ),
    "travel_luxury": (
        _v(
            "private_jet",
            "private jet air-stairs with bright tarmac",
            "bright afternoon sunlight, polished fuselage",
        ),
        _v(
            "yacht_marina",
            "luxury yacht marina at golden hour",
            "warm backlight, reflective water",
        ),
        _v(
            "resort_lobby",
            "tropical resort lobby with open walls",
            "warm ambient amber light, greenery behind",
        ),
        _v(
            "helicopter_pad",
            "helicopter pad atop a coastal hotel",
            "bright sunlight with sparkling sea behind",
        ),
    ),
    "yoga_outdoor": (
        _v(
            "sunrise_beach",
            "sandy beach near gentle ocean waves",
            "warm pink-orange sunrise backlight",
            props="yoga mat on sand",
            camera="low-angle from mat",
        ),
        _v(
            "mountain_deck",
            "wooden deck above misty mountains",
            "soft cool morning diffused daylight",
            props="rolled yoga mat",
            camera="wide three-quarter view",
        ),
        _v(
            "rooftop_city",
            "urban rooftop with city skyline",
            "warm golden-hour ambient light",
            props="minimalist yoga block",
            camera="eye-level medium shot",
        ),
        _v(
            "forest_clearing",
            "sunlit pine forest clearing",
            "dappled green-gold tree light",
            props="natural-fibre mat",
            camera="medium shot low angle",
        ),
    ),
    "cycling": (
        _v(
            "coastal_road",
            "coastal road with ocean on one side",
            "warm golden-hour sidelight, sparkling water",
        ),
        _v(
            "forest_trail",
            "forest cycling trail with pines",
            "dappled afternoon light through the canopy",
        ),
        _v(
            "urban_waterfront",
            "urban waterfront cycling path with skyline",
            "bright cool morning daylight, sharp distant skyline",
        ),
        _v(
            "mountain_pass",
            "mountain pass cycling road with valleys behind",
            "warm late-afternoon sunlight with long shadows",
        ),
    ),
    "tinder_pack_rooftop_golden": (
        _v(
            "skyline_east",
            "rooftop facing an eastern city skyline",
            "warm golden-hour backlight with soft rim",
        ),
        _v(
            "skyline_west",
            "rooftop facing a western city skyline",
            "deep amber sunset sidelight",
        ),
        _v(
            "garden_rooftop",
            "rooftop with planted greenery and city behind",
            "warm directional golden-hour light",
        ),
        _v(
            "lounge_rooftop",
            "rooftop lounge with low couches and city view",
            "warm ambient amber light with city warmth",
        ),
    ),
    "tinder_pack_minimal_studio": (
        _v(
            "pure_white",
            "pure white seamless studio backdrop",
            "even soft diffused key light with gentle fill",
        ),
        _v(
            "warm_grey",
            "warm mid-grey seamless backdrop",
            "soft directional key with subtle rim",
        ),
        _v("muted_beige", "muted beige seamless backdrop", "warm even studio lighting"),
        _v(
            "soft_taupe",
            "soft taupe studio backdrop",
            "gentle portrait key with natural fill",
        ),
    ),
    "tinder_pack_cafe_window": (
        _v(
            "morning_window",
            "cafe window seat at morning",
            "soft cool morning light with warm interior glow",
        ),
        _v(
            "rainy_window",
            "cafe window seat with soft rain outside",
            "warm interior lamp light with cool window",
        ),
        _v(
            "sunny_terrace",
            "cafe window at a sunny terrace",
            "warm afternoon sunlight on the table",
        ),
        _v(
            "evening_amber",
            "cafe window seat at early evening",
            "warm amber pendant lights with soft window glow",
        ),
    ),
}


# ---------------------------------------------------------------------------
# CV (only non-document styles)
# ---------------------------------------------------------------------------

CV_VARIANTS: dict[str, tuple[StyleVariant, ...]] = {
    "corporate": (
        _v(
            "corner_office",
            "modern corner office with floor-to-ceiling windows",
            "diffused warm daylight with soft fill",
        ),
        _v(
            "glass_boardroom_edge",
            "glass-walled corner beside a boardroom",
            "bright cool daylight with warm accent",
        ),
        _v(
            "marble_lobby",
            "executive office lobby with marble wall",
            "warm ambient amber light with clean fill",
        ),
        _v(
            "wood_library_office",
            "wood-paneled executive office",
            "warm directional lamp light with natural fill",
        ),
    ),
    "boardroom": (
        _v(
            "dark_wood_table",
            "executive boardroom with dark polished table",
            "even warm overhead lighting",
        ),
        _v(
            "glass_walled_boardroom",
            "glass-walled boardroom with city view",
            "bright cool daylight with warm interior accent",
        ),
        _v(
            "modern_light_boardroom",
            "modern light-wood boardroom",
            "soft even diffused lighting",
        ),
        _v(
            "heritage_boardroom",
            "heritage boardroom with oil paintings",
            "warm ambient amber light, rich textures",
        ),
    ),
    "formal_portrait": (
        _v(
            "charcoal_backdrop",
            "neutral charcoal-to-grey gradient studio",
            "classic Rembrandt key with gentle fill",
        ),
        _v(
            "deep_blue_backdrop",
            "deep blue studio backdrop",
            "soft clamshell portrait lighting",
        ),
        _v(
            "warm_grey_backdrop",
            "warm grey portrait backdrop",
            "butterfly key light with soft fill",
        ),
        _v(
            "textured_canvas",
            "textured painterly canvas backdrop",
            "warm low-key directional lighting",
        ),
    ),
    "creative": (
        _v(
            "bright_studio",
            "bright creative studio with whiteboard",
            "warm ambient daylight with natural fill",
        ),
        _v(
            "concept_wall",
            "open concept wall with sketches and mood art",
            "soft directional warm lighting",
        ),
        _v(
            "coworking_nook",
            "creative nook in a coworking space",
            "bright cool daylight with warm accent lamps",
        ),
        _v(
            "gallery_studio",
            "gallery-like studio with artworks",
            "warm track lighting on art",
        ),
    ),
    "startup_casual": (
        _v(
            "open_floor",
            "open-plan startup office with standing desks",
            "bright natural daylight, plants around",
        ),
        _v(
            "team_lounge",
            "startup lounge with colorful beanbags and sofas",
            "warm ambient amber light with playful accents",
        ),
        _v(
            "glass_meeting_pod",
            "glass meeting pod in a modern office",
            "bright cool daylight with warm interior",
        ),
        _v(
            "brick_loft",
            "brick-loft startup office with exposed beams",
            "warm directional daylight with clean fill",
        ),
    ),
    "coworking": (
        _v(
            "industrial_loft",
            "industrial coworking loft with exposed brick",
            "warm directional daylight with clean fill",
        ),
        _v(
            "garden_coworking",
            "coworking garden terrace",
            "bright warm afternoon sunlight, fresh greens",
        ),
        _v(
            "scandi_coworking",
            "Scandinavian-style coworking with pale wood",
            "soft even daylight, minimal palette",
        ),
        _v(
            "rooftop_coworking",
            "rooftop coworking deck with city behind",
            "warm golden-hour backlight with soft fill",
        ),
    ),
    "standing_desk": (
        _v(
            "home_office",
            "minimal home office with monitor and plant",
            "soft warm window light",
        ),
        _v(
            "tech_studio",
            "tech studio with dual monitors and ambient LED",
            "cool ambient LED with warm desk accent",
        ),
        _v(
            "architect_desk",
            "architect's standing desk with blueprints",
            "bright daylight with directional task light",
        ),
        _v(
            "art_director_desk",
            "art director's standing desk with mood board",
            "warm directional lamp light with natural fill",
        ),
    ),
    "neutral": (
        _v(
            "light_grey_studio",
            "light-grey studio backdrop, distraction-free",
            "even diffused key light from both sides",
        ),
        _v(
            "warm_beige_studio",
            "warm beige minimal backdrop",
            "soft balanced studio lighting",
        ),
        _v(
            "soft_white_studio",
            "soft white minimalist studio backdrop",
            "bright even beauty-dish style lighting",
        ),
        _v(
            "textured_grey",
            "textured grey studio backdrop with subtle grain",
            "warm even portrait lighting",
        ),
    ),
    "tech_developer": (
        _v(
            "code_monitors",
            "developer workspace with dual code monitors",
            "warm desk lamp with cool ambient LED",
        ),
        _v(
            "dark_cave_office",
            "dark home office with RGB accent lighting",
            "cool ambient LED with warm face accent",
        ),
        _v(
            "minimalist_tech",
            "minimalist tech workspace with single monitor",
            "soft even daylight with clean shadows",
        ),
        _v(
            "cafe_coding",
            "cafe table with laptop and code on screen",
            "warm afternoon window light",
        ),
    ),
    "creative_director": (
        _v(
            "moodboard_wall",
            "design studio wall with mood-boards",
            "warm directional studio light on board",
        ),
        _v(
            "sample_table",
            "table with fabric and color samples",
            "soft even warm lighting",
        ),
        _v(
            "black_studio",
            "clean black studio with minimal props",
            "single warm key light with crisp rim",
        ),
        _v(
            "art_loft",
            "art-loft studio with track lights",
            "warm track lighting with rich shadow",
        ),
    ),
    "medical": (
        _v("clean_clinic", "clean modern clinic corridor", "bright cool even lighting"),
        _v(
            "exam_room",
            "tidy exam room with medical charts",
            "soft warm ambient with cool overhead",
        ),
        _v(
            "hospital_hallway",
            "hospital hallway with bright clean surfaces",
            "bright even cool lighting",
        ),
        _v(
            "research_lab",
            "research lab corner with microscope",
            "cool ambient with warm task lamp",
        ),
    ),
    "legal_finance": (
        _v(
            "wood_library",
            "wood-paneled office with leather chair",
            "warm desk-lamp light with ambient fill",
        ),
        _v(
            "archive_shelves",
            "law-book archive shelves behind desk",
            "warm ambient amber light, rich shadows",
        ),
        _v(
            "marble_chamber",
            "marble chamber room with heritage details",
            "warm directional light with cool stone fill",
        ),
        _v(
            "city_view_office",
            "city-view executive office",
            "bright cool daylight with warm interior accent",
        ),
    ),
    "architect": (
        _v(
            "drafting_studio",
            "architectural studio with drafting table",
            "bright cool daylight with warm task lamp",
        ),
        _v(
            "model_lab",
            "scale-model lab with detailed miniatures",
            "soft directional warm lamp light",
        ),
        _v(
            "glass_office",
            "modern architect glass office",
            "bright natural daylight with clean fill",
        ),
        _v(
            "site_office",
            "construction-site office portacabin",
            "bright cool daylight with warm lamp accent",
        ),
    ),
    "speaker_stage": (
        _v(
            "keynote_stage",
            "keynote conference stage with large screen",
            "warm stage key with soft rim",
        ),
        _v(
            "panel_stage",
            "panel-discussion stage with modern seating",
            "warm ambient stage lighting",
        ),
        _v(
            "ted_style_circle",
            "round stage with a bright circular backdrop",
            "clean directional key light",
        ),
        _v(
            "festival_expo",
            "expo keynote stage with colorful backdrop",
            "warm saturated stage lighting",
        ),
    ),
    "podcast": (
        _v(
            "home_studio",
            "home podcast studio with acoustic panels",
            "warm ambient lamp light with soft fill",
        ),
        _v(
            "loft_studio",
            "loft podcast studio with exposed brick",
            "warm tungsten lamp light",
        ),
        _v(
            "minimal_booth",
            "minimalist broadcast booth with neat desk",
            "soft even diffused lighting",
        ),
        _v(
            "rooftop_podcast",
            "rooftop outdoor podcast setup",
            "warm golden-hour daylight, gentle breeze mood",
        ),
    ),
    "mentor": (
        _v(
            "bright_meeting",
            "bright meeting room with whiteboard",
            "warm ambient daylight with clean fill",
        ),
        _v(
            "coffee_mentor",
            "cafe corner for mentoring chat",
            "warm window light with amber pendant",
        ),
        _v(
            "bookshelf_office",
            "warm office with bookshelves",
            "warm directional lamp light, cozy tone",
        ),
        _v(
            "garden_meeting",
            "garden meeting nook",
            "soft afternoon daylight with green fill",
        ),
    ),
    "outdoor_business": (
        _v(
            "cafe_terrace",
            "upscale outdoor cafe terrace on a city street",
            "warm afternoon daylight with soft shadows",
        ),
        _v(
            "rooftop_meeting",
            "rooftop business nook with skyline",
            "warm golden-hour backlight",
        ),
        _v(
            "garden_office",
            "outdoor garden office with laptop",
            "soft warm morning light, fresh greens",
        ),
        _v(
            "harbor_meeting",
            "harborfront cafe with boats behind",
            "bright cool daylight with warm accent",
        ),
    ),
    "video_call": (
        _v(
            "home_setup",
            "clean home office with ring light and monitor",
            "even soft ring-light key, subtle fill",
        ),
        _v(
            "bookshelf_bg",
            "home office with neat bookshelves behind",
            "warm ambient lamp with soft key light",
        ),
        _v(
            "plant_wall",
            "home office with plant wall behind",
            "soft warm natural light, green fill",
        ),
        _v(
            "gradient_panel",
            "home office with gradient color panel behind",
            "clean even key with warm accent",
        ),
    ),
    "glass_wall_pose": (
        _v(
            "sky_city_view",
            "floor-to-ceiling glass wall facing the skyline",
            "warm golden-hour backlight, soft interior fill",
        ),
        _v(
            "blue_hour_panorama",
            "glass wall with city lights at blue hour",
            "warm interior lamp with deep blue outside",
        ),
        _v(
            "morning_panorama",
            "glass-walled office at morning with skyline",
            "soft cool morning daylight",
        ),
        _v(
            "harbor_panorama",
            "glass wall overlooking a harbor",
            "bright natural daylight with cool water tones",
        ),
    ),
    "analytics_review": (
        _v(
            "charts_monitor",
            "office desk with clean analytics on a monitor",
            "warm desk lamp with cool monitor glow",
        ),
        _v(
            "tablet_dashboard",
            "tablet dashboard on a tidy desk",
            "soft warm afternoon daylight",
        ),
        _v(
            "printed_reports",
            "desk with printed report sheets",
            "warm directional task lamp light",
        ),
        _v(
            "war_room",
            "quiet ops room with data wall",
            "cool ambient LED with warm face accent",
        ),
    ),
    "tablet_stylus": (
        _v(
            "design_desk",
            "creative desk with digital tablet and sketches",
            "soft warm directional task light",
        ),
        _v(
            "glass_desk",
            "modern glass desk with tablet",
            "bright natural daylight with clean fill",
        ),
        _v(
            "cafe_tablet",
            "cafe table with a graphics tablet",
            "warm afternoon window light",
        ),
        _v(
            "studio_tablet",
            "art studio corner with tablet on easel stand",
            "warm track lighting on sketches",
        ),
    ),
    "notebook_ideas": (
        _v(
            "cafe_window_notebook",
            "bright cafe window with notebook open",
            "soft warm window light",
        ),
        _v(
            "library_notebook",
            "library reading-desk with notebook",
            "warm ambient amber light",
        ),
        _v(
            "park_bench_notebook",
            "park bench with notebook",
            "warm golden-hour backlight",
        ),
        _v(
            "home_desk_notebook",
            "home desk with notebook and coffee",
            "soft warm natural light",
        ),
    ),
    "coffee_break_work": (
        _v(
            "modern_kitchen",
            "modern office kitchen with espresso machine",
            "bright even overhead light, clean surfaces",
        ),
        _v(
            "rooftop_break",
            "office rooftop coffee break spot",
            "warm golden-hour backlight",
        ),
        _v(
            "lounge_break",
            "office lounge with armchairs for coffee break",
            "warm ambient lamp light",
        ),
        _v(
            "patio_break",
            "office patio garden for a coffee break",
            "warm afternoon daylight, fresh greens",
        ),
    ),
    "late_hustle": (
        _v(
            "lamp_desk_night",
            "modern office desk at night with warm desk lamp",
            "warm lamp with cool city lights outside",
        ),
        _v(
            "glass_office_night",
            "glass-walled office at night with skyline",
            "warm lamp with cool city lights outside",
        ),
        _v(
            "home_night_focus",
            "home office at night, one focused lamp on",
            "warm desk lamp with cool dim ambient",
        ),
        _v(
            "rooftop_night_call",
            "rooftop office corner at night",
            "warm phone/laptop glow with cool city lights",
        ),
    ),
    "quiet_expert": (
        _v(
            "home_library",
            "home library with floor-to-ceiling bookshelves",
            "warm reading lamp with soft ambient",
        ),
        _v(
            "oak_study",
            "oak-paneled study with leather chair",
            "warm amber lamp light with rich shadows",
        ),
        _v(
            "minimalist_study",
            "minimalist study with a single shelf",
            "soft even daylight with clean fill",
        ),
        _v(
            "academic_office",
            "academic office with stacked journals",
            "warm desk lamp with soft window fill",
        ),
    ),
    "digital_nomad": (
        _v(
            "beach_cafe_workspace",
            "beach cafe with laptop and palm behind",
            "bright tropical daylight, sparkling water",
        ),
        _v(
            "mountain_cabin_work",
            "mountain cabin with laptop on wooden table",
            "soft warm morning light through window",
        ),
        _v(
            "island_balcony_work",
            "island balcony workspace with ocean view",
            "warm afternoon sunlight, sparkling water",
        ),
        _v(
            "desert_resort_work",
            "desert resort courtyard with laptop",
            "warm late-afternoon sunlight, sand tones",
        ),
    ),
    "entrepreneur_on_move": (
        _v(
            "airport_gate",
            "modern airport departure gate with phone in hand",
            "bright cool daylight with warm accent",
        ),
        _v(
            "train_platform",
            "high-speed train platform with travel bag",
            "warm afternoon daylight, sharp architecture",
        ),
        _v(
            "city_avenue_move",
            "city avenue with carry-on luggage",
            "warm golden-hour sidelight",
        ),
        _v(
            "taxi_curbside",
            "taxi curbside with modern skyline behind",
            "cool daylight with warm building reflections",
        ),
    ),
    "intellectual": (
        _v(
            "classic_library",
            "classic library with warm amber ambient",
            "warm reading lamp with ambient amber fill",
        ),
        _v(
            "bookstore_corner",
            "cozy bookstore corner with reading chair",
            "warm pendant light with soft shelves fill",
        ),
        _v(
            "university_hall",
            "university reading hall with wooden tables",
            "warm directional daylight",
        ),
        _v(
            "study_fireplace",
            "study with stone fireplace behind",
            "warm fireplace glow with soft ambient fill",
        ),
    ),
    "man_with_mission": (
        _v(
            "glass_facade",
            "glass-and-steel building facade",
            "strong directional daylight with sharp shadows",
        ),
        _v(
            "concrete_plaza",
            "modern concrete plaza with geometric shadows",
            "warm low-angle sunlight with long shadows",
        ),
        _v(
            "skyscraper_lobby",
            "skyscraper lobby with polished stone",
            "warm amber ambient with cool daylight",
        ),
        _v(
            "industrial_gate",
            "industrial gate with strong architectural lines",
            "warm golden-hour sidelight",
        ),
    ),
    "before_meeting": (
        _v(
            "office_corridor",
            "modern office corridor with glass meeting rooms",
            "bright even cool daylight",
        ),
        _v(
            "lobby_wait",
            "executive lobby with leather seating",
            "warm ambient amber light",
        ),
        _v(
            "elevator_hall",
            "modern elevator hall with polished floor",
            "warm directional interior light",
        ),
        _v(
            "rooftop_prep",
            "rooftop office corner for a pre-meeting moment",
            "warm afternoon daylight with city behind",
        ),
    ),
    "between_meetings": (
        _v(
            "hallway_phone",
            "office hallway with phone in hand",
            "bright cool daylight with warm accent",
        ),
        _v("lobby_bench", "office lobby bench with phone", "warm ambient lamp light"),
        _v(
            "glass_corner",
            "glass-walled office corner with skyline behind",
            "warm afternoon daylight",
        ),
        _v(
            "stair_landing",
            "modern staircase landing with phone in hand",
            "soft directional daylight",
        ),
    ),
    "business_lounge": (
        _v(
            "airport_lounge",
            "premium airport business lounge",
            "warm ambient amber light",
        ),
        _v(
            "hotel_club_lounge",
            "executive hotel club lounge",
            "warm lamp light with leather textures",
        ),
        _v(
            "private_lounge",
            "private club lounge with bar shelves behind",
            "warm directional bar lighting",
        ),
        _v(
            "rooftop_lounge",
            "rooftop business lounge with skyline",
            "warm golden-hour backlight",
        ),
    ),
    "decision_moment": (
        _v(
            "big_window_city",
            "tall window overlooking city skyline",
            "warm rim light with cool city outside",
        ),
        _v(
            "blue_hour_window",
            "executive window at blue hour",
            "warm interior lamp with deep blue outside",
        ),
        _v(
            "rainy_window",
            "executive window with rain-streaked glass",
            "cool overcast light with warm interior accent",
        ),
        _v(
            "sunset_window",
            "executive window at sunset",
            "warm amber sidelight with golden city below",
        ),
    ),
}


# ---------------------------------------------------------------------------
# Social
# ---------------------------------------------------------------------------

SOCIAL_VARIANTS: dict[str, tuple[StyleVariant, ...]] = {
    "influencer": (
        _v(
            "rooftop_golden",
            "urban rooftop with city skyline at golden hour",
            "warm directional sidelight, natural edge highlights",
        ),
        _v(
            "neon_street",
            "neon-lit urban street at night",
            "vivid neon color with warm accent",
        ),
        _v(
            "boutique_hotel_lobby",
            "boutique hotel lobby with fashion mood",
            "warm amber ambient with soft spot light",
        ),
        _v(
            "courtyard_art",
            "art-filled courtyard with murals",
            "warm afternoon sidelight",
        ),
    ),
    "influencer_urban": (
        _v(
            "downtown_rooftop",
            "downtown rooftop with skyline at golden hour",
            "warm directional sidelight",
        ),
        _v(
            "metro_platform",
            "modern metro platform with clean lines",
            "cool fluorescent with warm accent",
        ),
        _v(
            "alley_mural",
            "stylish alley with colorful mural",
            "warm afternoon sidelight",
        ),
        _v("skatepark_sunset", "urban skatepark at sunset", "warm low-angle sunlight"),
    ),
    "influencer_minimal": (
        _v(
            "pure_white",
            "pure white minimalist studio",
            "bright even diffused key light",
        ),
        _v(
            "beige_scandi",
            "beige Scandinavian studio with soft textures",
            "soft warm key with clean fill",
        ),
        _v(
            "taupe_backdrop",
            "taupe seamless backdrop with a chair",
            "gentle directional key, minimal palette",
        ),
        _v(
            "soft_grey_minimal",
            "soft grey minimalist studio",
            "warm even portrait lighting",
        ),
    ),
    "influencer_luxury": (
        _v(
            "marble_hotel_lobby",
            "upscale hotel lobby with marble floor",
            "warm amber ambient with brass accents",
        ),
        _v(
            "velvet_lounge",
            "velvet lounge with rich textures",
            "warm directional lamp with crystal accent",
        ),
        _v(
            "private_yacht",
            "private yacht deck at golden hour",
            "warm backlight, reflective water",
        ),
        _v(
            "penthouse_balcony",
            "penthouse balcony with city skyline",
            "warm golden-hour sidelight",
        ),
    ),
    "luxury": (
        _v(
            "marble_lounge",
            "upscale lounge with marble and brass",
            "warm ambient amber light",
        ),
        _v(
            "wine_library",
            "wine library with cellar shelves",
            "warm lamp light, rich shadows",
        ),
        _v(
            "tailor_atelier",
            "tailor's atelier with fabric rolls",
            "warm directional lamp light",
        ),
        _v(
            "penthouse_living",
            "penthouse living room with skyline behind",
            "warm interior lamps with golden-hour fill",
        ),
    ),
    "casual": (
        _v(
            "sunny_park",
            "sunlit park with dappled tree shadows",
            "warm dappled afternoon light",
        ),
        _v(
            "bright_home", "bright airy home interior", "soft warm natural window light"
        ),
        _v("cafe_bench", "warm cafe bench with plants", "soft amber afternoon light"),
        _v("beach_board", "casual beach boardwalk", "bright warm afternoon daylight"),
    ),
    "morning_routine": (
        _v(
            "bright_bedroom",
            "bright modern bedroom with white linens",
            "soft bright morning window light",
        ),
        _v(
            "plant_bathroom",
            "modern bathroom with plants and soft tones",
            "bright even morning daylight",
        ),
        _v(
            "kitchen_coffee_morning",
            "bright kitchen with fresh morning coffee",
            "warm morning sunlight on counter",
        ),
        _v(
            "balcony_morning",
            "cozy balcony with morning tea",
            "soft warm morning light, fresh air mood",
        ),
    ),
    "fitness_lifestyle": (
        _v(
            "glass_gym",
            "modern glass-walled gym with bright natural light",
            "bright directional daylight",
        ),
        _v(
            "outdoor_park_fitness",
            "outdoor workout area in a park",
            "warm golden-hour backlight",
        ),
        _v(
            "studio_class",
            "boutique fitness studio with mirrored wall",
            "warm directional spotlight, polished reflections",
        ),
        _v(
            "beach_training",
            "beach shoreline training spot",
            "warm sunrise backlight, gentle waves",
        ),
    ),
    "food_blogger": (
        _v(
            "marble_table_plate",
            "beautifully plated food on marble table",
            "warm overhead soft light, fresh herbs nearby",
        ),
        _v(
            "rustic_wood_table",
            "rustic wood table with earthy plating",
            "warm directional daylight with shadow",
        ),
        _v(
            "chef_counter",
            "chef counter at modern restaurant",
            "warm amber pendant with clean fill",
        ),
        _v(
            "garden_brunch",
            "outdoor garden brunch table",
            "bright warm daylight, leafy backdrop",
        ),
    ),
    "travel_blogger": (
        _v(
            "tropical_landmark",
            "tropical landmark at golden hour",
            "warm backlight with soft shadow",
        ),
        _v(
            "snow_mountain",
            "snow-capped mountain viewpoint",
            "bright crisp daylight, cool air",
        ),
        _v(
            "colorful_town",
            "colorful old-town lane with painted walls",
            "warm afternoon sidelight",
        ),
        _v(
            "desert_dunes",
            "sand dunes at golden hour",
            "warm low-angle light with long shadows",
        ),
    ),
    "artistic": (
        _v(
            "white_cube",
            "white-cube gallery with colorful paintings",
            "warm track lighting on art",
        ),
        _v(
            "loft_studio",
            "art loft with exposed brick and paint rolls",
            "warm directional studio light",
        ),
        _v(
            "sculpture_hall",
            "sculpture hall with marble pieces",
            "soft even gallery lighting",
        ),
        _v(
            "mural_wall",
            "bright mural wall in an arts district",
            "warm afternoon sidelight",
        ),
    ),
    "golden_hour": (
        _v(
            "meadow_gold",
            "open meadow at golden hour with tall grass",
            "warm orange low-angle sunlight",
        ),
        _v(
            "beach_gold",
            "wide beach at golden hour",
            "deep amber backlight with sparkling water",
        ),
        _v(
            "forest_gold",
            "forest clearing at golden hour",
            "warm golden light filtering through trees",
        ),
        _v(
            "lake_gold",
            "calm lake at golden hour with reflective surface",
            "warm sunset backlight, still water",
        ),
    ),
    "neon_night": (
        _v(
            "wet_pavement",
            "city street with wet pavement reflecting neon",
            "vivid neon with reflective rain",
        ),
        _v(
            "asian_alley",
            "Asian night alley with signs in sharp detail",
            "saturated neon with warm accent",
        ),
        _v(
            "arcade_lights",
            "game arcade exterior with neon marquee",
            "vivid saturated neon color",
        ),
        _v(
            "subway_neon",
            "subway entrance with neon signage",
            "cool neon with warm accent glow",
        ),
    ),
    "vintage_film": (
        _v(
            "retro_cafe",
            "retro diner cafe interior",
            "warm desaturated tones, soft grain",
        ),
        _v(
            "vintage_car_street",
            "street with a classic 60s car",
            "warm muted afternoon light",
        ),
        _v(
            "old_cinema",
            "old cinema facade with vintage neon",
            "warm desaturated tones with subtle grain",
        ),
        _v(
            "retro_diner_booth",
            "retro diner booth seat",
            "warm tungsten light, nostalgic palette",
        ),
    ),
    "dark_moody": (
        _v(
            "low_key_room",
            "dark low-key interior with deep shadows",
            "single directional key with rich shadow",
        ),
        _v(
            "stone_corridor",
            "moody stone corridor with single light source",
            "directional warm key with deep shadow",
        ),
        _v(
            "fog_street",
            "foggy night street with single lamppost",
            "warm lamppost light with cool ambient fog",
        ),
        _v(
            "metal_studio",
            "dark metal studio with one rim light",
            "single rim light with warm accent",
        ),
    ),
    "pastel_soft": (
        _v("pink_wall", "soft pink minimal backdrop", "bright even diffused light"),
        _v(
            "mint_wall",
            "mint-green minimal backdrop",
            "soft even daylight, calm palette",
        ),
        _v("lavender_wall", "lavender minimal backdrop", "warm soft diffused lighting"),
        _v("cream_wall", "cream minimal backdrop", "bright even soft lighting"),
    ),
    "youtube_creator": (
        _v(
            "ring_light_setup",
            "content creator setup with ring light",
            "bright even ring-light key with color accents",
        ),
        _v(
            "led_panels",
            "creator studio with LED panels",
            "warm LED with cool accent beams",
        ),
        _v(
            "colorful_backdrop",
            "colorful printed backdrop with props",
            "bright even soft lighting, vivid palette",
        ),
        _v(
            "desk_setup",
            "creator desk with mic and monitor",
            "warm directional desk light with ambient LED",
        ),
    ),
    "linkedin_premium": (
        _v(
            "modern_office",
            "modern office with plants and glass",
            "bright natural daylight",
        ),
        _v(
            "coworking_linkedin",
            "coworking space with warm ambient light",
            "warm ambient amber with clean fill",
        ),
        _v(
            "glass_room_linkedin",
            "glass-walled room with skyline behind",
            "bright cool daylight with warm accent",
        ),
        _v(
            "boutique_hotel_linkedin",
            "boutique hotel meeting corner",
            "warm ambient light with leather textures",
        ),
    ),
    "tinder_top": (
        _v(
            "park_golden",
            "sunlit park with warm golden-hour backlight",
            "warm low-angle sunlight",
        ),
        _v(
            "waterfront_sunset",
            "waterfront pier at sunset",
            "warm amber backlight, reflective water",
        ),
        _v("cafe_window_tinder", "bright cafe window seat", "soft warm window light"),
        _v(
            "rooftop_afternoon",
            "rooftop terrace at warm afternoon",
            "warm directional afternoon sunlight",
        ),
    ),
    "instagram_aesthetic": (
        _v(
            "monochrome_palette",
            "curated monochrome setting",
            "soft even balanced lighting",
        ),
        _v(
            "earth_tones",
            "earth-tone curated setting with balanced palette",
            "warm afternoon daylight",
        ),
        _v("pastel_palette", "pastel curated setting", "bright soft diffused light"),
        _v(
            "saturated_palette",
            "saturated curated setting with bold color",
            "warm directional light with vivid tones",
        ),
    ),
    "podcast_host": (
        _v(
            "home_podcast_studio",
            "home podcast studio with acoustic foam",
            "warm ambient lamp with soft fill",
        ),
        _v(
            "loft_podcast_studio",
            "loft podcast studio with brick wall",
            "warm tungsten pendant light",
        ),
        _v(
            "glass_podcast_studio",
            "glass-walled podcast studio",
            "warm directional lamp with clean fill",
        ),
        _v(
            "on_location_podcast",
            "on-location recording setup",
            "warm natural daylight with ambient fill",
        ),
    ),
    "creative_portrait": (
        _v(
            "concrete_texture",
            "textured concrete wall",
            "warm directional sidelight with soft shadow",
        ),
        _v(
            "painted_wall_portrait",
            "hand-painted colorful wall",
            "warm directional side light",
        ),
        _v(
            "wood_panel_portrait",
            "wood panel wall with vertical slats",
            "soft warm directional key light",
        ),
        _v(
            "velvet_portrait",
            "deep velvet drape as backdrop",
            "warm single directional key with rim",
        ),
    ),
    "mirror_aesthetic": (
        _v(
            "modern_bedroom_mirror",
            "modern bedroom with mirror and plants",
            "soft warm ambient light",
        ),
        _v(
            "closet_mirror",
            "walk-in closet with full-length mirror",
            "warm directional closet light",
        ),
        _v(
            "hotel_mirror",
            "hotel bathroom mirror with marble",
            "warm ambient amber light",
        ),
        _v(
            "studio_mirror", "studio with full-length mirror", "soft even warm lighting"
        ),
    ),
    "elevator_clean": (
        _v(
            "steel_elevator",
            "modern elevator with stainless steel walls",
            "even overhead cool light",
        ),
        _v(
            "mirrored_elevator",
            "mirrored-walls elevator",
            "warm overhead light with clean reflections",
        ),
        _v(
            "black_elevator",
            "black matte elevator with gold trim",
            "warm ambient amber with soft spot",
        ),
        _v(
            "glass_elevator",
            "glass panoramic elevator with skyline behind",
            "bright natural daylight with warm accent",
        ),
    ),
    "book_and_coffee": (
        _v(
            "home_reading_corner",
            "cozy reading corner with open book",
            "warm lamp light with soft ambient",
        ),
        _v(
            "cafe_reading",
            "cafe table with open book and coffee",
            "warm window light with amber pendant",
        ),
        _v(
            "library_reading",
            "library table with open book and coffee",
            "warm reading lamp with cool ambient",
        ),
        _v(
            "garden_reading",
            "garden bench with open book and coffee",
            "soft warm morning light",
        ),
    ),
    "shopfront": (
        _v(
            "designer_boutique",
            "designer boutique window facade",
            "warm display lighting with clean lines",
        ),
        _v(
            "vintage_shop",
            "vintage shopfront with colorful window",
            "warm afternoon sidelight",
        ),
        _v(
            "bookstore_front",
            "bookstore facade with neat display",
            "warm ambient amber light",
        ),
        _v(
            "coffee_shop_front",
            "coffee shop facade with plant accents",
            "warm afternoon daylight",
        ),
    ),
    "candid_street": (
        _v(
            "morning_street_walk",
            "urban street caught mid-stride in morning",
            "soft cool morning light with warm accents",
        ),
        _v(
            "golden_hour_walk",
            "urban street at golden hour",
            "warm low-angle sidelight",
        ),
        _v(
            "crosswalk_candid",
            "modern crosswalk caught candidly",
            "warm afternoon daylight with crisp shadows",
        ),
        _v(
            "rainy_candid",
            "rainy street candid with umbrella nearby",
            "soft cool overcast with warm shop windows",
        ),
    ),
    "reading_home": (
        _v(
            "armchair_window",
            "armchair by a bright window with book",
            "warm diffused window light",
        ),
        _v(
            "fireplace_reading",
            "fireplace nook with a throw blanket",
            "warm fireplace glow with soft ambient fill",
        ),
        _v(
            "plant_corner",
            "plant-filled reading corner",
            "soft warm natural light, green fill",
        ),
        _v(
            "bed_reading",
            "bed reading nook with pillows",
            "warm bedside lamp with soft ambient",
        ),
    ),
    "reading_cafe": (
        _v(
            "classic_bookstore_cafe",
            "classic bookstore cafe with shelves",
            "warm pendant light with soft shelves fill",
        ),
        _v(
            "modern_quiet_cafe",
            "modern quiet cafe with minimalist shelves",
            "soft cool daylight with warm accent",
        ),
        _v(
            "library_style_cafe",
            "library-style cafe with tall shelves",
            "warm ambient amber light",
        ),
        _v(
            "garden_cafe_reading",
            "garden cafe reading spot",
            "soft warm afternoon daylight",
        ),
    ),
    "sketching": (
        _v(
            "desk_sketching",
            "creative desk with pencils and sketches",
            "warm directional task lamp",
        ),
        _v(
            "cafe_sketching",
            "cafe table with open sketchbook",
            "soft warm window light",
        ),
        _v(
            "studio_sketching",
            "art studio corner with easel sketches",
            "warm track lighting on sketches",
        ),
        _v(
            "park_bench_sketching",
            "park bench with sketchbook",
            "warm golden-hour backlight",
        ),
    ),
    "photographer": (
        _v(
            "studio_photo",
            "studio with camera on tripod and backdrop",
            "soft even studio lighting",
        ),
        _v(
            "urban_street_photo",
            "urban street shoot location",
            "warm afternoon sidelight",
        ),
        _v(
            "nature_photo",
            "nature location with camera in hands",
            "warm golden-hour backlight",
        ),
        _v(
            "coastal_photo",
            "coastal shoot location with cliffs behind",
            "warm late-afternoon sidelight",
        ),
    ),
    "meditation": (
        _v("garden_zen", "serene zen garden with stones", "soft warm morning light"),
        _v(
            "minimal_room_meditation",
            "minimal bright room for meditation",
            "soft even daylight with plant fill",
        ),
        _v(
            "beach_meditation",
            "quiet beach shoreline at sunrise",
            "warm pink sunrise backlight",
        ),
        _v(
            "forest_meditation",
            "forest clearing for meditation",
            "soft dappled morning light",
        ),
    ),
    "online_learning": (
        _v(
            "home_desk_study",
            "home desk with laptop and notes",
            "soft warm natural light",
        ),
        _v(
            "cafe_study",
            "cafe table with laptop for study",
            "warm window light with amber pendant",
        ),
        _v(
            "library_study",
            "library table with laptop and books",
            "warm reading lamp with ambient fill",
        ),
        _v(
            "garden_study",
            "garden nook with laptop on lap",
            "soft warm afternoon daylight",
        ),
    ),
    "yoga_social": (
        _v(
            "sunrise_deck_social",
            "outdoor wooden deck at sunrise",
            "warm pink-orange sunrise backlight",
            props="yoga mat on the deck",
        ),
        _v(
            "beach_yoga_social",
            "quiet beach near gentle waves",
            "warm soft morning light",
            props="yoga mat on the sand",
        ),
        _v(
            "forest_yoga_social",
            "forest clearing on soft moss",
            "dappled green-gold morning light",
            props="natural-fibre mat",
        ),
        _v(
            "rooftop_yoga_social",
            "urban rooftop with skyline",
            "warm golden-hour ambient light",
            props="minimalist yoga block",
        ),
    ),
    "cycling_social": (
        _v(
            "coast_road_social",
            "scenic coastal road with ocean alongside",
            "warm sunset sidelight",
        ),
        _v(
            "countryside_social",
            "countryside road with green fields",
            "soft warm afternoon daylight",
        ),
        _v(
            "urban_path_social",
            "urban waterfront cycling path",
            "bright cool morning daylight",
        ),
        _v(
            "mountain_pass_social",
            "mountain pass cycling road",
            "warm late-afternoon sidelight",
        ),
    ),
    "panoramic_window": (
        _v(
            "city_panorama_day",
            "floor-to-ceiling window with city panorama",
            "warm directional interior light with cool city outside",
        ),
        _v(
            "blue_hour_panoramic",
            "panoramic window at blue hour",
            "warm interior light with deep blue outside",
        ),
        _v(
            "sunset_panoramic",
            "panoramic window at sunset",
            "warm amber sidelight with golden city below",
        ),
        _v(
            "rainy_panoramic",
            "panoramic window with rainy city outside",
            "cool overcast with warm interior accent",
        ),
    ),
    "in_motion": (
        _v(
            "street_stride_motion",
            "urban street caught mid-stride",
            "warm afternoon sidelight",
        ),
        _v(
            "rainy_motion",
            "rainy street with dynamic energy",
            "cool overcast with warm shop windows",
        ),
        _v(
            "night_motion",
            "city street at night with motion",
            "warm street lamps with cool ambient",
        ),
        _v(
            "golden_hour_motion",
            "urban street at golden hour",
            "warm low-angle sidelight",
        ),
    ),
    "creative_insight": (
        _v(
            "cork_board_studio",
            "creative studio with cork board and sketches",
            "warm desk-lamp lighting",
        ),
        _v(
            "plants_creative_desk",
            "creative desk with plants and art supplies",
            "soft warm natural light",
        ),
        _v(
            "loft_creative_studio",
            "loft creative studio with exposed brick",
            "warm tungsten lamp light",
        ),
        _v(
            "minimal_creative",
            "minimal creative desk with notebook and laptop",
            "soft even daylight",
        ),
    ),
    "architecture_shadow": (
        _v(
            "concrete_geometry",
            "dramatic concrete architectural shadows",
            "strong directional warm light",
        ),
        _v(
            "stone_geometry",
            "stone wall with geometric light patterns",
            "warm golden-hour sidelight with sharp shadow",
        ),
        _v(
            "glass_shadow",
            "glass building with geometric reflections",
            "warm afternoon sidelight",
        ),
        _v(
            "brutalist_shadow",
            "brutalist architecture with bold shadow",
            "strong warm directional sunlight",
        ),
    ),
    "achievement_moment": (
        _v(
            "rooftop_sky",
            "open rooftop with bright expansive sky",
            "warm golden-hour backlight",
        ),
        _v(
            "mountain_summit",
            "mountain summit viewpoint",
            "bright crisp daylight, cool mountain air",
        ),
        _v(
            "stadium_win",
            "empty stadium stands with celebratory feel",
            "warm directional stadium light",
        ),
        _v(
            "elevated_balcony",
            "elevated balcony with city below",
            "warm golden-hour sidelight",
        ),
    ),
    "skyscraper_view": (
        _v(
            "highrise_blue",
            "high-rise interior at blue hour with city lights",
            "warm interior accent with deep blue sky",
        ),
        _v(
            "highrise_sunset",
            "high-rise interior at sunset",
            "warm amber sidelight with golden city",
        ),
        _v(
            "highrise_rainy",
            "high-rise interior with rainy city below",
            "cool overcast with warm interior accent",
        ),
        _v(
            "highrise_day",
            "high-rise interior at day with skyline",
            "bright cool daylight with warm accent",
        ),
    ),
    "after_work": (
        _v(
            "city_dusk_walk",
            "city sidewalk at dusk with streetlights",
            "warm streetlights with cool blue sky",
        ),
        _v(
            "bar_entrance",
            "entrance to a lounge bar at dusk",
            "warm amber doorway light",
        ),
        _v("rooftop_unwind", "rooftop after-work unwind", "warm sunset sidelight"),
        _v("pier_sunset", "city pier at sunset", "warm amber backlight, cool water"),
    ),
    "evening_planning": (
        _v(
            "home_desk_evening",
            "home desk with notebook and tea",
            "warm lamp light with cool dim ambient",
        ),
        _v(
            "kitchen_planning",
            "kitchen table with notebook and tea",
            "warm pendant light with soft ambient",
        ),
        _v(
            "living_room_planning",
            "living room sofa with notebook",
            "warm reading-lamp light",
        ),
        _v(
            "balcony_planning",
            "balcony seat with notebook at evening",
            "warm twilight light with soft cool ambient",
        ),
    ),
    "focused_mood": (
        _v(
            "black_backdrop",
            "clean black minimal backdrop",
            "single directional key with rich shadow",
        ),
        _v(
            "charcoal_mood",
            "charcoal minimal backdrop",
            "warm single key with subtle rim",
        ),
        _v(
            "deep_blue_mood",
            "deep blue minimal backdrop",
            "single warm directional key",
        ),
        _v(
            "warm_grey_mood",
            "warm grey minimal backdrop",
            "soft single key with gentle fill",
        ),
    ),
    "light_irony": (
        _v(
            "mural_street_irony",
            "urban mural street with playful art",
            "warm afternoon daylight with vivid colors",
        ),
        _v(
            "alley_irony",
            "narrow alley with colorful details",
            "warm directional sidelight",
        ),
        _v(
            "shopfront_irony",
            "quirky shopfront with small display",
            "warm display lighting with soft ambient",
        ),
        _v(
            "park_playful_irony",
            "park corner with playful architecture",
            "warm afternoon sidelight",
        ),
    ),
}


# ---------------------------------------------------------------------------
# Aggregated lookup
# ---------------------------------------------------------------------------

STYLE_VARIANTS: dict[tuple[str, str], tuple[StyleVariant, ...]] = {
    **{("dating", k): _pad_variants(v) for k, v in DATING_VARIANTS.items()},
    **{("cv", k): _pad_variants(v) for k, v in CV_VARIANTS.items()},
    **{("social", k): _pad_variants(v) for k, v in SOCIAL_VARIANTS.items()},
}


def variants_for(mode: str, style: str) -> tuple[StyleVariant, ...]:
    """Return registered variants for (mode, style), empty tuple if none."""
    return STYLE_VARIANTS.get((mode, style), ())
