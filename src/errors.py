"""Error handling utilities - sanitize technical errors for end users."""

import re
import logging

logger = logging.getLogger("clawlite.errors")

# Patterns to detect and sanitize
SENSITIVE_PATTERNS = [
    (r'https?://[^\s\'"]+', '[URL]'),  # URLs
    (r'api[_-]?key[=:]\s*[^\s\'"]+', '[API_KEY]'),  # API keys
    (r'token[=:]\s*[^\s\'"]+', '[TOKEN]'),  # Tokens
    (r'/home/\w+/[^\s\'"]*', '[PATH]'),  # File paths
    (r'/app/[^\s\'"]*', '[PATH]'),  # Container paths
]

# User-friendly error messages (personality-aware, casual Indonesian)
ERROR_MESSAGES = {
    "connection": "Waduh, ga bisa konek ke server AI nih. 😅 Mungkin lagi restart atau ada masalah jaringan. Coba lagi ya!",
    "timeout": "Hmm, server AI lama banget responnya. 🐢 Mungkin lagi sibuk, coba kirim ulang ya.",
    "500": "Server AI lagi bermasalah (500). 🔧 Tim lagi benerin, coba lagi nanti ya.",
    "502": "Server AI ga bisa dijangkau (502). 📡 Coba lagi dalam beberapa menit.",
    "503": "Server AI lagi sibuk banget (503). ⏳ Coba lagi dalam beberapa menit ya.",
    "429": "Kebanyakan request nih. 😅 Tunggu 30 detik dulu ya, baru coba lagi.",
    "401": "Autentikasi gagal. 🔐 Coba hubungi admin.",
    "403": "Akses ditolak. 🚫",
    "404": "Resource ga ketemu. 🔍",
    "rate limit": "Rate limit kena. ⏰ Tunggu 30 detik dulu ya.",
    "model": "Ada error di AI model. 🤖 Coba kirim ulang pesan ya.",
    "default": "Ada yang error nih. 😅 Coba kirim ulang pesan ya.",
}


def sanitize_error(error: Exception | str) -> str:
    """
    Convert technical error to user-friendly message.
    Logs the full error but returns sanitized version.
    """
    error_str = str(error).lower()
    
    # Log full error for debugging
    logger.error(f"Original error: {error}")
    
    # Match known error patterns
    for pattern, message in ERROR_MESSAGES.items():
        if pattern in error_str:
            return message
    
    # If no pattern matched, return generic message
    return ERROR_MESSAGES["default"]


def sanitize_text(text: str) -> str:
    """Remove sensitive information from text (URLs, paths, keys)."""
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def format_user_error(error: Exception | str, context: str = None) -> str:
    """Format error for display to user."""
    message = sanitize_error(error)
    if context:
        return f"❌ {context}: {message}"
    return f"❌ {message}"
