# AGENTS.md

## Cursor Cloud specific instructions

VideoGet is a Python/Flask web app + CLI that downloads social-media videos via `yt-dlp`
(re-encoding to H.264/AAC mp4 with `ffmpeg`). There is no build step, no test suite, and no
linter configured in this repo; `python -m py_compile app.py cli.py downloader.py` is a quick
syntax sanity check.

Dependencies (installed by the startup update script) live in a virtualenv at `.venv`.
Always `source .venv/bin/activate` before running anything. System `ffmpeg` and `node`
(`/exec-daemon/node`) are already present and auto-detected by `downloader.py`.

### Running the services
- Web UI + REST API: `python app.py --host 127.0.0.1 --port 5000` (or `./start.sh [PORT]`),
  then open `http://127.0.0.1:5000`. Run it under tmux if you need it to stay alive.
- CLI: `python cli.py "<url>" --quality best` (see `README.md` for all flags/quality presets).

### Non-obvious gotchas
- `downloader.py` hardcodes a macOS log path `~/Library/Logs/videoget.log` and opens it at
  import time. On Linux that directory does not exist, so importing the module (and therefore
  starting the app/CLI) fails with `FileNotFoundError` unless `~/Library/Logs/` exists. The
  update script creates it; if you ever wipe `$HOME`, recreate it with `mkdir -p ~/Library/Logs`.
- Downloads are written to `~/Desktop/VideoDownloader/` by default (created automatically).
- YouTube is currently broken with the installed `yt-dlp` (2026.7.x): `downloader.py` passes
  `js_runtimes` as a list (`["node:/path"]`), but this yt-dlp version expects a dict, so YouTube
  `get_info`/`download` raise `ValueError: Invalid js_runtimes format`. Non-YouTube platforms
  (TikTok, X/Twitter, Instagram, Facebook, etc.) do not hit this path and work. Use a non-YouTube
  URL for smoke tests. (Also note datacenter IPs are frequently bot-blocked by YouTube even when
  the code path works.)
- The web UI auto-selects "Chrome" browser cookies for several platforms; in a headless VM there
  is no Chrome profile, so leave the cookie dropdown on "None" when testing public videos.
- Quality presets like `720p` use `bestvideo[height<=720]+bestaudio/best[height<=720]`, which some
  TikTok videos don't satisfy (combined-format only). Use `best` when a preset returns
  "Requested format is not available".
