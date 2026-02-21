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

# User-friendly error messages
ERROR_MESSAGES = {
    "connection": "Tidak dapat terhubung ke server. Coba lagi nanti.",
    "timeout": "Request terlalu lama. Coba lagi.",
    "500": "Server sedang bermasalah. Coba lagi nanti.",
    "502": "Server sedang bermasalah. Coba lagi nanti.",
    "503": "Server sedang sibuk. Coba lagi nanti.",
    "429": "Terlalu banyak request. Tunggu sebentar.",
    "401": "Autentikasi gagal. Hubungi admin.",
    "403": "Akses ditolak.",
    "404": "Resource tidak ditemukan.",
    "rate limit": "Terlalu banyak request. Tunggu sebentar.",
    "model": "Terjadi kesalahan pada AI. Coba lagi.",
    "default": "Terjadi kesalahan. Coba lagi nanti.",
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
