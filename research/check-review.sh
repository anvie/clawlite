#!/bin/bash
# Check if there's a pending AutoImprove review for Aisyah

REVIEW_FILE="$(dirname "$0")/REVIEW_NEEDED.md"

if [ -f "$REVIEW_FILE" ]; then
    echo "🔔 PENDING REVIEW"
    cat "$REVIEW_FILE"
    exit 1
else
    echo "✅ No pending reviews"
    exit 0
fi
