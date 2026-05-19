"""Prompt compression utilities."""

import re


def compress_prompt(prompt: str) -> str:
    """Compress a prompt by removing semantic noise and deduplicating terms.

    Preserves visual anchors (scene, identity, lighting, pose).
    """
    if not prompt:
        return prompt

    # Remove extra whitespace
    compressed = re.sub(r"\s+", " ", prompt).strip()

    # Remove filler words
    noise_words = [
        "a picture of",
        "an image of",
        "a photo of",
        "photograph of",
        "showing",
        "depicting",
        "featuring",
        "where we can see",
        "in the background",
        "in the foreground",
        "looking like",
        "it is",
        "there is",
        "there are",
        "we see",
    ]

    for word in noise_words:
        compressed = re.sub(rf"\b{word}\b", "", compressed, flags=re.IGNORECASE)

    # Deduplicate consecutive identical words (case-insensitive)
    # e.g. "beautiful beautiful sunset" -> "beautiful sunset"
    compressed = re.sub(r"\b(\w+)(?:\s+\1\b)+", r"\1", compressed, flags=re.IGNORECASE)

    # Remove redundant synonyms (simple mapping)
    synonyms = {
        r"\b(very|extremely|highly)\s+(very|extremely|highly)\b": r"\1",
        r"\b(beautiful|gorgeous|stunning)\s+(beautiful|gorgeous|stunning)\b": r"\1",
        r"\b(realistic|photorealistic|hyperrealistic)\s+(realistic|photorealistic|hyperrealistic)\b": r"\1",
        r"\b(sharp|crisp|clear)\s+(sharp|crisp|clear)\b": r"\1",
    }

    for pattern, replacement in synonyms.items():
        compressed = re.sub(pattern, replacement, compressed, flags=re.IGNORECASE)

    compressed = re.sub(r"\s+", " ", compressed).strip()

    # Fix punctuation (remove spaces before punctuation, remove duplicate commas).
    # The "insert space after punctuation" rule must NOT fire between digits
    # — splitting ``2.5%`` into ``2. 5%`` or ``5,000`` into ``5, 000`` would
    # corrupt percentage anchors (v1.68 face-area anchor) and numeric specs.
    # Hence the negative lookbehind ``(?<!\d)`` that keeps decimals intact.
    compressed = re.sub(r"\s+([.,!?;:])", r"\1", compressed)
    compressed = re.sub(r"(?<!\d)([.,!?;:])(?=[^\s])", r"\1 ", compressed)
    compressed = re.sub(r",(\s*,)+", ",", compressed)
    compressed = re.sub(r"\.(\s*\.)+", ".", compressed)

    # Clean up leading/trailing punctuation
    compressed = re.sub(r"^[.,!?;:\s]+", "", compressed)

    return compressed.strip()
