"""Translation layer using NLLB API with glossary post-processing."""

import os
import re
import httpx

TRANSLATION_ENABLED = os.getenv("TRANSLATION_ENABLED", "false").lower() == "true"
TRANSLATION_API = os.getenv("TRANSLATION_API", "http://localhost:7655")

# Glossary for post-processing (case-insensitive replacements)
# Add domain-specific term corrections here
GLOSSARY_EN_TO_ID = {
    # Example corrections for Indonesian
    "pembayaran awal": "DP",
    "pembayaran terlebih dahulu": "DP",
    "uang muka": "DP",
}

GLOSSARY_ID_TO_EN = {
    # Example corrections for English
}


def apply_glossary(text: str, glossary: dict) -> str:
    """Apply glossary replacements (case-insensitive)."""
    result = text
    for find, replace in glossary.items():
        pattern = re.compile(re.escape(find), re.IGNORECASE)
        result = pattern.sub(replace, result)
    return result


async def translate(text: str, source: str, target: str) -> str:
    """
    Translate text using NLLB API with glossary post-processing.
    Returns original text if translation is disabled or fails.
    """
    if not TRANSLATION_ENABLED:
        return text
    
    if not text or not text.strip():
        return text
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{TRANSLATION_API}/translate",
                json={"text": text, "source": source, "target": target}
            )
            if resp.status_code == 200:
                translated = resp.json().get("translated", text)
                
                # Apply glossary post-processing
                if target == "ind_Latn":
                    translated = apply_glossary(translated, GLOSSARY_EN_TO_ID)
                elif target == "eng_Latn":
                    translated = apply_glossary(translated, GLOSSARY_ID_TO_EN)
                
                return translated
    except Exception:
        pass
    
    return text


async def translate_to_english(text: str) -> str:
    """Translate Indonesian to English."""
    return await translate(text, "ind_Latn", "eng_Latn")


async def translate_to_indonesian(text: str) -> str:
    """Translate English to Indonesian."""
    return await translate(text, "eng_Latn", "ind_Latn")
