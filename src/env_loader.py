"""
Environment loader with optional encryption support.

Uses envcrypt if available (for encrypted .env values),
falls back to python-dotenv otherwise.

Usage:
    from env_loader import load_env
    load_env()  # Call once at startup
"""

import os
import logging

logger = logging.getLogger("clawlite.env")


def load_env(env_file: str = ".env") -> bool:
    """
    Load environment variables from .env file.
    
    If envcrypt is installed and configured, encrypted values
    (prefixed with 'encrypted:') will be automatically decrypted.
    
    Args:
        env_file: Path to .env file (default: ".env")
    
    Returns:
        True if loaded successfully, False otherwise
    """
    if not os.path.exists(env_file):
        logger.debug(f"No {env_file} file found, skipping")
        return False
    
    # Try envcrypt first (supports encrypted values)
    try:
        from envcrypt import EnvcryptLoader
        
        # Check if config exists
        config_path = os.path.expanduser("~/.envcrypt.yaml")
        env_key = os.environ.get("ENVCRYPT_KEY")
        
        if env_key:
            # Use key from environment (for Docker)
            loader = EnvcryptLoader.from_key(env_key)
            loader.load(env_file)
            logger.info(f"Loaded {env_file} with envcrypt (key from env)")
            return True
        elif os.path.exists(config_path):
            # Use key from config file
            loader = EnvcryptLoader.from_config()
            loader.load(env_file)
            logger.info(f"Loaded {env_file} with envcrypt")
            return True
        else:
            # envcrypt installed but not configured, fall through to dotenv
            logger.debug("envcrypt installed but not configured, using dotenv")
    
    except ImportError:
        # envcrypt not installed, fall through to dotenv
        pass
    except Exception as e:
        logger.warning(f"envcrypt failed: {e}, falling back to dotenv")
    
    # Fallback to python-dotenv
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        logger.info(f"Loaded {env_file} with dotenv")
        return True
    except ImportError:
        logger.warning("Neither envcrypt nor python-dotenv installed")
        return False
    except Exception as e:
        logger.error(f"Failed to load {env_file}: {e}")
        return False
