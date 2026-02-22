"""Authentication module for ClawLite.

Handles OAuth PKCE flow and credential management for LLM providers.
Supports both global and per-instance credentials.

Resolution order:
1. Instance credentials (~/.clawlite/instances/<name>/credentials.json)
2. Global credentials (~/.clawlite/credentials.json)
3. Environment variables (fallback)
"""

import os
import json
import time
import secrets
import hashlib
import base64
import logging
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs, urlparse
import threading

import httpx

logger = logging.getLogger("clawlite.auth")

# Paths
CLAWLITE_HOME = Path.home() / ".clawlite"
GLOBAL_CREDENTIALS_FILE = CLAWLITE_HOME / "credentials.json"
INSTANCES_DIR = CLAWLITE_HOME / "instances"

# OAuth config for Anthropic
# These are discovered from Claude Code CLI's OAuth flow
ANTHROPIC_OAUTH_CONFIG = {
    "authorize_url": "https://console.anthropic.com/oauth/authorize",
    "token_url": "https://console.anthropic.com/oauth/token",
    "client_id": "claude-cli",  # Claude Code's public client ID
    "redirect_port": 54545,
    "redirect_uri": "http://localhost:54545/callback",
    "scope": "user:inference",
}


@dataclass
class TokenInfo:
    """OAuth token information."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_at: Optional[float] = None  # Unix timestamp
    scope: Optional[str] = None
    
    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if token is expired (with buffer for safety)."""
        if not self.expires_at:
            return False  # No expiry info, assume valid
        return time.time() > (self.expires_at - buffer_seconds)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "TokenInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass 
class Credentials:
    """Credentials for a provider."""
    provider: str
    auth_type: str  # "api_key" or "oauth"
    api_key: Optional[str] = None
    token: Optional[TokenInfo] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    
    def to_dict(self) -> dict:
        data = {
            "provider": self.provider,
            "auth_type": self.auth_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.api_key:
            data["api_key"] = self.api_key
        if self.token:
            data["token"] = self.token.to_dict()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "Credentials":
        token_data = data.get("token")
        token = TokenInfo.from_dict(token_data) if token_data else None
        return cls(
            provider=data.get("provider", ""),
            auth_type=data.get("auth_type", ""),
            api_key=data.get("api_key"),
            token=token,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


class CredentialsStore:
    """Manages credential storage and retrieval."""
    
    def __init__(self, instance_name: Optional[str] = None):
        """
        Initialize credentials store.
        
        Args:
            instance_name: If set, use instance-specific credentials
        """
        self.instance_name = instance_name
        self._ensure_dirs()
    
    def _ensure_dirs(self):
        """Ensure credential directories exist."""
        CLAWLITE_HOME.mkdir(parents=True, exist_ok=True)
        if self.instance_name:
            instance_dir = INSTANCES_DIR / self.instance_name
            instance_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_credentials_path(self, instance: bool = False) -> Path:
        """Get path to credentials file."""
        if instance and self.instance_name:
            return INSTANCES_DIR / self.instance_name / "credentials.json"
        return GLOBAL_CREDENTIALS_FILE
    
    def _load_credentials_file(self, path: Path) -> Dict[str, Credentials]:
        """Load credentials from a file."""
        if not path.exists():
            return {}
        
        try:
            with open(path) as f:
                data = json.load(f)
            
            credentials = {}
            for provider, cred_data in data.get("credentials", {}).items():
                credentials[provider] = Credentials.from_dict(cred_data)
            return credentials
        except Exception as e:
            logger.warning(f"Failed to load credentials from {path}: {e}")
            return {}
    
    def _save_credentials_file(self, path: Path, credentials: Dict[str, Credentials]):
        """Save credentials to a file."""
        data = {
            "version": 1,
            "credentials": {
                provider: cred.to_dict() 
                for provider, cred in credentials.items()
            }
        }
        
        # Write atomically
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        tmp_path.rename(path)
        
        # Secure permissions (readable only by owner)
        path.chmod(0o600)
    
    def get(self, provider: str) -> Optional[Credentials]:
        """
        Get credentials for a provider.
        
        Resolution order:
        1. Instance credentials (if instance_name set)
        2. Global credentials
        3. Returns None (caller should check env vars)
        """
        # Try instance credentials first
        if self.instance_name:
            instance_creds = self._load_credentials_file(
                self._get_credentials_path(instance=True)
            )
            if provider in instance_creds:
                logger.debug(f"Using instance credentials for {provider}")
                return instance_creds[provider]
        
        # Try global credentials
        global_creds = self._load_credentials_file(GLOBAL_CREDENTIALS_FILE)
        if provider in global_creds:
            logger.debug(f"Using global credentials for {provider}")
            return global_creds[provider]
        
        return None
    
    def save(self, credentials: Credentials, instance: bool = False):
        """
        Save credentials for a provider.
        
        Args:
            credentials: Credentials to save
            instance: If True and instance_name set, save to instance file
        """
        path = self._get_credentials_path(instance=instance and bool(self.instance_name))
        
        all_creds = self._load_credentials_file(path)
        
        credentials.updated_at = time.time()
        if not credentials.created_at:
            credentials.created_at = credentials.updated_at
        
        all_creds[credentials.provider] = credentials
        self._save_credentials_file(path, all_creds)
        
        logger.info(f"Saved {credentials.provider} credentials to {path}")
    
    def delete(self, provider: str, instance: bool = False) -> bool:
        """Delete credentials for a provider."""
        path = self._get_credentials_path(instance=instance and bool(self.instance_name))
        
        all_creds = self._load_credentials_file(path)
        if provider in all_creds:
            del all_creds[provider]
            self._save_credentials_file(path, all_creds)
            logger.info(f"Deleted {provider} credentials from {path}")
            return True
        return False
    
    def list_all(self) -> Dict[str, Dict[str, Any]]:
        """List all credentials with their source."""
        result = {}
        
        # Global credentials
        global_creds = self._load_credentials_file(GLOBAL_CREDENTIALS_FILE)
        for provider, cred in global_creds.items():
            result[provider] = {
                "source": "global",
                "auth_type": cred.auth_type,
                "expires_at": cred.token.expires_at if cred.token else None,
                "is_expired": cred.token.is_expired() if cred.token else False,
            }
        
        # Instance credentials (override global)
        if self.instance_name:
            instance_creds = self._load_credentials_file(
                self._get_credentials_path(instance=True)
            )
            for provider, cred in instance_creds.items():
                result[provider] = {
                    "source": f"instance:{self.instance_name}",
                    "auth_type": cred.auth_type,
                    "expires_at": cred.token.expires_at if cred.token else None,
                    "is_expired": cred.token.is_expired() if cred.token else False,
                }
        
        return result


class OAuthPKCE:
    """OAuth 2.0 PKCE flow implementation."""
    
    def __init__(self, config: dict):
        self.config = config
        self.code_verifier = None
        self.code_challenge = None
        self.state = None
        self._auth_code = None
        self._error = None
    
    def _generate_pkce(self):
        """Generate PKCE code verifier and challenge."""
        # Generate code verifier (43-128 chars)
        self.code_verifier = secrets.token_urlsafe(32)
        
        # Generate code challenge (SHA256 hash, base64url encoded)
        digest = hashlib.sha256(self.code_verifier.encode()).digest()
        self.code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        
        # Generate state for CSRF protection
        self.state = secrets.token_urlsafe(16)
    
    def get_authorize_url(self) -> str:
        """Get the authorization URL to open in browser."""
        self._generate_pkce()
        
        params = {
            "client_id": self.config["client_id"],
            "redirect_uri": self.config["redirect_uri"],
            "response_type": "code",
            "scope": self.config.get("scope", ""),
            "state": self.state,
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256",
        }
        
        return f"{self.config['authorize_url']}?{urlencode(params)}"
    
    def _create_callback_handler(self):
        """Create HTTP request handler for OAuth callback."""
        oauth = self
        
        class CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress logging
            
            def do_GET(self):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                
                if "code" in params:
                    # Verify state
                    received_state = params.get("state", [None])[0]
                    if received_state != oauth.state:
                        oauth._error = "State mismatch - possible CSRF attack"
                        self._send_response("❌ Authentication failed: state mismatch", 400)
                        return
                    
                    oauth._auth_code = params["code"][0]
                    self._send_response("✅ Authentication successful! You can close this window.")
                
                elif "error" in params:
                    oauth._error = params.get("error_description", params["error"])[0]
                    self._send_response(f"❌ Authentication failed: {oauth._error}", 400)
                
                else:
                    self._send_response("❌ Invalid callback", 400)
            
            def _send_response(self, message: str, status: int = 200):
                self.send_response(status)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                
                html = f"""<!DOCTYPE html>
<html>
<head>
    <title>ClawLite Auth</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; 
               display: flex; justify-content: center; align-items: center;
               height: 100vh; margin: 0; background: #1a1a2e; color: #eee; }}
        .container {{ text-align: center; padding: 2rem; }}
        h1 {{ font-size: 3rem; margin-bottom: 1rem; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{message}</h1>
        <p>You can close this window and return to the terminal.</p>
    </div>
</body>
</html>"""
                self.wfile.write(html.encode())
        
        return CallbackHandler
    
    def wait_for_callback(self, timeout: int = 300) -> Optional[str]:
        """
        Start local server and wait for OAuth callback.
        
        Returns auth code on success, None on failure.
        """
        port = self.config["redirect_port"]
        
        handler = self._create_callback_handler()
        server = HTTPServer(("localhost", port), handler)
        server.timeout = timeout
        
        # Handle one request
        logger.debug(f"Waiting for OAuth callback on port {port}")
        server.handle_request()
        server.server_close()
        
        if self._error:
            logger.error(f"OAuth error: {self._error}")
            return None
        
        return self._auth_code
    
    async def exchange_code(self, code: str) -> Optional[TokenInfo]:
        """Exchange authorization code for tokens."""
        data = {
            "grant_type": "authorization_code",
            "client_id": self.config["client_id"],
            "code": code,
            "redirect_uri": self.config["redirect_uri"],
            "code_verifier": self.code_verifier,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config["token_url"],
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.status_code} {response.text}")
                return None
            
            token_data = response.json()
            
            # Calculate expiry time
            expires_in = token_data.get("expires_in")
            expires_at = time.time() + expires_in if expires_in else None
            
            return TokenInfo(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_type=token_data.get("token_type", "Bearer"),
                expires_at=expires_at,
                scope=token_data.get("scope"),
            )


async def refresh_token(credentials: Credentials, config: dict) -> Optional[TokenInfo]:
    """Refresh an expired OAuth token."""
    if not credentials.token or not credentials.token.refresh_token:
        logger.warning("No refresh token available")
        return None
    
    data = {
        "grant_type": "refresh_token",
        "client_id": config["client_id"],
        "refresh_token": credentials.token.refresh_token,
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            config["token_url"],
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.status_code} {response.text}")
            return None
        
        token_data = response.json()
        
        expires_in = token_data.get("expires_in")
        expires_at = time.time() + expires_in if expires_in else None
        
        return TokenInfo(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", credentials.token.refresh_token),
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=expires_at,
            scope=token_data.get("scope"),
        )


def get_anthropic_credentials(instance_name: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """
    Get Anthropic credentials (API key or OAuth token).
    
    Resolution order:
    1. Instance credentials
    2. Global credentials  
    3. Environment variables
    
    Returns:
        Tuple of (api_key, auth_token) - one will be set, other None
    """
    store = CredentialsStore(instance_name)
    creds = store.get("anthropic")
    
    if creds:
        if creds.auth_type == "oauth" and creds.token:
            # Check if token needs refresh
            if creds.token.is_expired():
                logger.info("OAuth token expired, attempting refresh...")
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                new_token = loop.run_until_complete(
                    refresh_token(creds, ANTHROPIC_OAUTH_CONFIG)
                )
                
                if new_token:
                    creds.token = new_token
                    store.save(creds)
                    logger.info("Token refreshed successfully")
                else:
                    logger.warning("Token refresh failed, may need to re-authenticate")
            
            return (None, creds.token.access_token)
        
        elif creds.auth_type == "api_key" and creds.api_key:
            return (creds.api_key, None)
    
    # Fallback to environment variables
    api_key = os.getenv("ANTHROPIC_API_KEY")
    auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")
    
    if auth_token:
        return (None, auth_token)
    elif api_key:
        return (api_key, None)
    
    return (None, None)
