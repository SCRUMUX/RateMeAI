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
    ]

    for word in noise_words:
        compressed = re.sub(rf"\b{word}\b", "", compressed, flags=re.IGNORECASE)

    compressed = re.sub(r"\s+", " ", compressed).strip()

    # Fix punctuation
    compressed = re.sub(r"\s+([.,!?;:])", r"\1", compressed)
    compressed = re.sub(r"([.,!?;:])(?=[^\s])", r"\1 ", compressed)

    return compressed.strip()
