#!/bin/bash
# Installs Scratch VO as a background login item on macOS.
# After this, the app is always at http://localhost:8501 with no terminal open.
set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "This installer is for macOS. On other systems run: python3 -m streamlit run vo_app.py"
    exit 1
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$(command -v python3)"
LABEL="com.scratchvo.app"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/ScratchVO"
PORT=8501

echo "Installing Scratch VO from: $APP_DIR"

if ! "$PYTHON_BIN" -c "import streamlit" >/dev/null 2>&1; then
    echo "Installing Streamlit and the neural voice engine…"
    if ! "$PYTHON_BIN" -m pip install --user -q -r "$APP_DIR/requirements-vo.txt"; then
        echo
        echo "Could not install dependencies. Try running this line by itself:"
        echo "  $PYTHON_BIN -m pip install --user streamlit piper-tts"
        exit 1
    fi
fi

echo "Checking for a good voice…"
if ! "$PYTHON_BIN" -c "
import sys
sys.path.insert(0, '$APP_DIR')
from tts_lib import installed_piper_voices, download_piper_voice, DEFAULT_PIPER_VOICE
if not installed_piper_voices():
    print('Downloading ' + DEFAULT_PIPER_VOICE + ' (one time, about 110 MB)…')
    download_piper_voice(DEFAULT_PIPER_VOICE)
print('Voice ready.')
"; then
    echo "Could not download a neural voice. The app will still run with system voices."
    echo "You can download one later from the app's 'Add better voices' section."
fi

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>-m</string>
        <string>streamlit</string>
        <string>run</string>
        <string>$APP_DIR/vo_app.py</string>
        <string>--server.address=127.0.0.1</string>
        <string>--server.port=$PORT</string>
        <string>--server.headless=true</string>
        <string>--browser.gatherUsageStats=false</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$APP_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/scratch-vo.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/scratch-vo.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"

echo "Waiting for the app to start…"
for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:$PORT" >/dev/null 2>&1; then
        echo
        echo "Scratch VO is running at http://localhost:$PORT"
        echo "It starts automatically when you log in. No terminal needed."
        echo "To stop it:  bash \"$APP_DIR/uninstall_autostart.sh\""
        open "http://localhost:$PORT" 2>/dev/null || true
        exit 0
    fi
    sleep 1
done

echo
echo "The app did not answer on port $PORT. Last lines of the error log:"
echo "---"
tail -n 20 "$LOG_DIR/scratch-vo.err.log" 2>/dev/null || echo "(no error log was written)"
echo "---"
echo "If macOS asked about a new background item, allow it in"
echo "System Settings > General > Login Items & Extensions, then run this installer again."
exit 1
