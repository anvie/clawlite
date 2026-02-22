"""ClawLite CLI - Authentication Commands."""

import sys
import asyncio
import logging
import webbrowser
from typing import Optional

from auth import (
    CredentialsStore,
    Credentials,
    TokenInfo,
    OAuthPKCE,
    ANTHROPIC_OAUTH_CONFIG,
    get_anthropic_credentials,
)

logger = logging.getLogger("clawlite.cli.auth")


def cmd_auth_anthropic(args) -> int:
    """Authenticate with Anthropic (OAuth or API key)."""
    instance = getattr(args, "instance", None)
    
    # Check for logout
    if getattr(args, "logout", False):
        return _auth_logout("anthropic", instance)
    
    # Check for paste mode (manual token entry)
    if getattr(args, "paste", False):
        return _auth_paste_token("anthropic", instance)
    
    # Check for API key mode
    if getattr(args, "api_key", False):
        return _auth_api_key("anthropic", instance)
    
    # Check for refresh mode
    if getattr(args, "refresh", False):
        return _auth_refresh("anthropic", instance)
    
    # Default: OAuth flow
    return _auth_oauth("anthropic", instance)


def _auth_oauth(provider: str, instance: Optional[str] = None) -> int:
    """Run OAuth PKCE flow."""
    print(f"🔐 Authenticating with {provider.title()} (OAuth)")
    print()
    
    if provider != "anthropic":
        print(f"❌ OAuth not supported for {provider}")
        return 1
    
    config = ANTHROPIC_OAUTH_CONFIG
    oauth = OAuthPKCE(config)
    
    # Generate authorization URL
    auth_url = oauth.get_authorize_url()
    
    print(f"Opening browser for authentication...")
    print(f"If browser doesn't open, visit this URL:")
    print()
    print(f"  {auth_url}")
    print()
    
    # Try to open browser
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        logger.warning(f"Failed to open browser: {e}")
    
    print(f"Waiting for authentication (timeout: 5 minutes)...")
    print()
    
    # Wait for callback
    code = oauth.wait_for_callback(timeout=300)
    
    if not code:
        print("❌ Authentication failed or timed out")
        return 1
    
    print("✅ Authorization code received, exchanging for token...")
    
    # Exchange code for token
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        token = loop.run_until_complete(oauth.exchange_code(code))
    finally:
        loop.close()
    
    if not token:
        print("❌ Failed to exchange code for token")
        return 1
    
    # Save credentials
    store = CredentialsStore(instance)
    credentials = Credentials(
        provider=provider,
        auth_type="oauth",
        token=token,
    )
    
    # Save to instance if specified, otherwise global
    store.save(credentials, instance=bool(instance))
    
    scope = "instance" if instance else "global"
    print()
    print(f"✅ Authentication successful!")
    print(f"   Provider: {provider}")
    print(f"   Scope: {scope}")
    if instance:
        print(f"   Instance: {instance}")
    print()
    
    return 0


def _auth_paste_token(provider: str, instance: Optional[str] = None) -> int:
    """Paste a token manually."""
    print(f"🔐 Paste {provider.title()} OAuth token")
    print()
    print("Get your token by running: claude setup-token")
    print()
    
    try:
        token = input("Paste token: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n❌ Cancelled")
        return 1
    
    if not token:
        print("❌ No token provided")
        return 1
    
    # Create token info (no expiry since we don't know)
    token_info = TokenInfo(
        access_token=token,
        token_type="Bearer",
    )
    
    # Save credentials
    store = CredentialsStore(instance)
    credentials = Credentials(
        provider=provider,
        auth_type="oauth",
        token=token_info,
    )
    
    store.save(credentials, instance=bool(instance))
    
    scope = "instance" if instance else "global"
    print()
    print(f"✅ Token saved!")
    print(f"   Provider: {provider}")
    print(f"   Scope: {scope}")
    if instance:
        print(f"   Instance: {instance}")
    print()
    
    return 0


def _auth_api_key(provider: str, instance: Optional[str] = None) -> int:
    """Set API key manually."""
    print(f"🔐 Set {provider.title()} API key")
    print()
    
    try:
        api_key = input("API key: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n❌ Cancelled")
        return 1
    
    if not api_key:
        print("❌ No API key provided")
        return 1
    
    # Basic validation
    if provider == "anthropic" and not api_key.startswith("sk-ant-"):
        print("⚠️  Warning: Anthropic API keys usually start with 'sk-ant-'")
        try:
            confirm = input("Continue anyway? [y/N]: ").strip().lower()
            if confirm != "y":
                print("❌ Cancelled")
                return 1
        except (KeyboardInterrupt, EOFError):
            print("\n❌ Cancelled")
            return 1
    
    # Save credentials
    store = CredentialsStore(instance)
    credentials = Credentials(
        provider=provider,
        auth_type="api_key",
        api_key=api_key,
    )
    
    store.save(credentials, instance=bool(instance))
    
    scope = "instance" if instance else "global"
    print()
    print(f"✅ API key saved!")
    print(f"   Provider: {provider}")
    print(f"   Scope: {scope}")
    if instance:
        print(f"   Instance: {instance}")
    print()
    
    return 0


def _auth_refresh(provider: str, instance: Optional[str] = None) -> int:
    """Refresh OAuth token."""
    print(f"🔄 Refreshing {provider.title()} token...")
    
    store = CredentialsStore(instance)
    creds = store.get(provider)
    
    if not creds:
        print(f"❌ No credentials found for {provider}")
        return 1
    
    if creds.auth_type != "oauth":
        print(f"❌ Not an OAuth credential (type: {creds.auth_type})")
        return 1
    
    if not creds.token or not creds.token.refresh_token:
        print("❌ No refresh token available")
        print("   You may need to re-authenticate with: clawlite auth anthropic")
        return 1
    
    # Import refresh function
    from auth import refresh_token, ANTHROPIC_OAUTH_CONFIG
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        new_token = loop.run_until_complete(
            refresh_token(creds, ANTHROPIC_OAUTH_CONFIG)
        )
    finally:
        loop.close()
    
    if not new_token:
        print("❌ Token refresh failed")
        print("   You may need to re-authenticate with: clawlite auth anthropic")
        return 1
    
    # Update credentials
    creds.token = new_token
    store.save(creds, instance=bool(instance))
    
    print("✅ Token refreshed successfully!")
    return 0


def _auth_logout(provider: str, instance: Optional[str] = None) -> int:
    """Remove saved credentials."""
    store = CredentialsStore(instance)
    
    scope = "instance" if instance else "global"
    
    if store.delete(provider, instance=bool(instance)):
        print(f"✅ {provider.title()} credentials removed ({scope})")
        return 0
    else:
        print(f"❌ No {provider} credentials found ({scope})")
        return 1


def cmd_auth_status(args) -> int:
    """Show authentication status."""
    instance = getattr(args, "instance", None)
    
    store = CredentialsStore(instance)
    all_creds = store.list_all()
    
    print("🔐 Authentication Status")
    print()
    
    if instance:
        print(f"   Instance: {instance}")
        print()
    
    if not all_creds:
        print("   No credentials found.")
        print()
        print("   To authenticate:")
        print("     clawlite auth anthropic        # OAuth (recommended)")
        print("     clawlite auth anthropic --api-key  # API key")
        return 0
    
    for provider, info in all_creds.items():
        print(f"   {provider.title()}:")
        print(f"     Source: {info['source']}")
        print(f"     Type: {info['auth_type']}")
        
        if info['expires_at']:
            import time
            from datetime import datetime
            expires_dt = datetime.fromtimestamp(info['expires_at'])
            
            if info['is_expired']:
                print(f"     Status: ❌ Expired at {expires_dt}")
            else:
                remaining = int(info['expires_at'] - time.time())
                hours = remaining // 3600
                minutes = (remaining % 3600) // 60
                print(f"     Status: ✅ Valid ({hours}h {minutes}m remaining)")
        else:
            print(f"     Status: ✅ Valid (no expiry)")
        
        print()
    
    # Also check environment variables
    import os
    env_creds = []
    if os.getenv("ANTHROPIC_API_KEY"):
        env_creds.append("ANTHROPIC_API_KEY")
    if os.getenv("ANTHROPIC_AUTH_TOKEN"):
        env_creds.append("ANTHROPIC_AUTH_TOKEN")
    
    if env_creds:
        print("   Environment variables:")
        for var in env_creds:
            print(f"     {var}: ✅ Set")
        print()
    
    return 0


def setup_auth_parser(subparsers) -> None:
    """Set up auth subcommand parser."""
    auth_parser = subparsers.add_parser(
        "auth",
        help="Manage authentication",
        description="Authenticate with LLM providers (Anthropic)",
    )
    
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")
    
    # auth anthropic
    anthropic_parser = auth_subparsers.add_parser(
        "anthropic",
        help="Authenticate with Anthropic",
        description="Authenticate with Anthropic Claude (OAuth or API key)",
    )
    anthropic_parser.add_argument(
        "--instance", "-i",
        help="Save credentials for specific instance",
    )
    anthropic_parser.add_argument(
        "--paste", "-p",
        action="store_true",
        help="Paste token manually (from 'claude setup-token')",
    )
    anthropic_parser.add_argument(
        "--api-key", "-k",
        action="store_true",
        help="Use API key instead of OAuth",
    )
    anthropic_parser.add_argument(
        "--refresh", "-r",
        action="store_true",
        help="Refresh existing OAuth token",
    )
    anthropic_parser.add_argument(
        "--logout",
        action="store_true",
        help="Remove saved credentials",
    )
    anthropic_parser.set_defaults(func=cmd_auth_anthropic)
    
    # auth status
    status_parser = auth_subparsers.add_parser(
        "status",
        help="Show authentication status",
    )
    status_parser.add_argument(
        "--instance", "-i",
        help="Check credentials for specific instance",
    )
    status_parser.set_defaults(func=cmd_auth_status)
