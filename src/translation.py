"""Translation layer using NLLB API with glossary post-processing."""

import re
import httpx
import logging

from .config import get as config_get

logger = logging.getLogger("clawlite.translation")


def is_translation_enabled() -> bool:
    """Check if translation is enabled in config."""
    return config_get('translation.enabled', False)


def get_api_url() -> str:
    """Get translation API URL from config."""
    return config_get('translation.api_url', 'http://127.0.0.1:7655')


def get_user_lang() -> str:
    """Get user language code."""
    return config_get('translation.user_lang', 'ind_Latn')


def get_llm_lang() -> str:
    """Get LLM language code."""
    return config_get('translation.llm_lang', 'eng_Latn')


# For backward compatibility
TRANSLATION_ENABLED = is_translation_enabled()


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
    if not is_translation_enabled():
        return text
    
    if not text or not text.strip():
        return text
    
    api_url = get_api_url()
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{api_url}/translate",
                json={"text": text, "source": source, "target": target}
            )
            if resp.status_code == 200:
                translated = resp.json().get("translated", text)
                
                # Apply glossary post-processing
                if target == "ind_Latn":
                    translated = apply_glossary(translated, GLOSSARY_EN_TO_ID)
                elif target == "eng_Latn":
                    translated = apply_glossary(translated, GLOSSARY_ID_TO_EN)
                
                logger.debug(f"Translated ({source}->{target}): '{text[:50]}...' -> '{translated[:50]}...'")
                return translated
            else:
                logger.warning(f"Translation API returned {resp.status_code}")
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
    
    return text


async def translate_to_english(text: str) -> str:
    """Translate user language to English (for LLM)."""
    return await translate(text, get_user_lang(), get_llm_lang())


async def translate_to_indonesian(text: str) -> str:
    """Translate English to user language (for response)."""
    return await translate(text, get_llm_lang(), get_user_lang())
