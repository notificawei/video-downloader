#!/bin/bash
# Stops Scratch VO and removes it from login items.
set -euo pipefail

LABEL="com.scratchvo.app"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
rm -f "$PLIST"

echo "Scratch VO stopped and removed from login items."
echo "Your saved scripts and audio files were not deleted."
