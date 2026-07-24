#!/usr/bin/env bash
# Quick launcher for VideoGet web UI
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PORT="${1:-5000}"

echo ""
echo "  VideoGet – Video Downloader"
echo "  Launching web UI at http://127.0.0.1:$PORT"
echo "  Press Ctrl+C to stop"
echo ""

python3 app.py --port "$PORT"
