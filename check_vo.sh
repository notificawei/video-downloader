#!/bin/bash
# Diagnoses why http://localhost:8501 is not loading.
# Run: bash check_vo.sh

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.scratchvo.app"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/ScratchVO"
PORT=8501

pass() { echo "  OK    $1"; }
fail() { echo "  FAIL  $1"; }

echo "Scratch VO check"
echo "App folder: $APP_DIR"
echo

echo "1. App files"
if [[ -f "$APP_DIR/vo_app.py" ]]; then
    pass "vo_app.py found"
else
    fail "vo_app.py missing — you are in the wrong folder or on the wrong branch"
    echo "        cd ~/video-downloader && git checkout cursor/scratch-vo-site-61f4"
    exit 1
fi

echo
echo "2. Streamlit installed"
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
    fail "python3 not found"
    exit 1
fi
if "$PYTHON_BIN" -c "import streamlit" >/dev/null 2>&1; then
    pass "streamlit importable by $PYTHON_BIN"
else
    fail "streamlit not installed for $PYTHON_BIN"
    echo "        $PYTHON_BIN -m pip install --user streamlit"
fi

echo
echo "3. Background login item"
if [[ "$(uname)" != "Darwin" ]]; then
    echo "  SKIP  not macOS"
elif [[ -f "$PLIST" ]]; then
    pass "login item file exists"
    if launchctl list 2>/dev/null | grep -q "$LABEL"; then
        pass "login item is loaded"
    else
        fail "login item exists but is not loaded"
        echo "        bash install_autostart.sh"
        echo "        also check System Settings > General > Login Items & Extensions"
    fi
else
    fail "never installed as a login item"
    echo "        bash install_autostart.sh"
fi

echo
echo "4. Server responding on port $PORT"
if curl -sf -o /dev/null --max-time 5 "http://127.0.0.1:$PORT"; then
    pass "http://localhost:$PORT is up"
else
    fail "nothing is listening on port $PORT (this is the ERR_CONNECTION_REFUSED)"
fi

echo
echo "5. Recent errors"
if [[ -s "$LOG_DIR/scratch-vo.err.log" ]]; then
    tail -n 15 "$LOG_DIR/scratch-vo.err.log"
else
    echo "  (no error log)"
fi

echo
echo "Quickest fix if anything above failed:"
echo "  cd \"$APP_DIR\" && bash install_autostart.sh"
echo "To run it in the foreground instead (terminal must stay open):"
echo "  cd \"$APP_DIR\" && python3 -m streamlit run vo_app.py"
