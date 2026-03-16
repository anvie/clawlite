#!/bin/bash
# =============================================================================
# ClawLite - Send Message to User
# =============================================================================
# Wrapper script for agents to send messages via configured channels
#
# Usage:
#   ./send-message.sh <user_id> <message>
#
# Examples:
#   ./send-message.sh tg_123456789 "Waktunya shalat!"
#   ./send-message.sh wa_628123456789 "Reminder: Meeting in 5 minutes"
#
# User ID format:
#   tg_<id>   - Telegram user
#   wa_<id>   - WhatsApp user
#   <id>      - Defaults to Telegram
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAWLITE_DIR="$(dirname "$SCRIPT_DIR")"

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <user_id> <message>"
    echo "Example: $0 tg_123456789 \"Waktunya shalat!\""
    exit 1
fi

USER_ID="$1"
MESSAGE="$2"

# Send via ClawLite CLI
cd "$CLAWLITE_DIR"
.venv/bin/python -m src.cli.send -u "$USER_ID" -m "$MESSAGE"
