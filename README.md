# VideoGet — High-Res Social Media Video Downloader

Download videos in the best available quality from YouTube, X/Twitter, Instagram, Facebook, and TikTok.  
Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

---

## Supported Platforms (Phase 1 — Western)

| Platform | Notes |
|---|---|
| **YouTube** | Full quality up to 8K, playlists, shorts |
| **X / Twitter** | Videos and GIFs |
| **Instagram** | Reels, posts, stories (may need cookies) |
| **Facebook** | Public videos (may need cookies) |
| **TikTok** | Videos without watermark |

---

## Setup

### 1. Install Python dependencies

```bash
pip3 install -r requirements.txt
```

> yt-dlp is also required: `pip3 install yt-dlp`

### 2. (Recommended) Install ffmpeg

ffmpeg is needed to merge video + audio streams for the best quality.

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

---

## Usage

### Web UI (recommended)

```bash
./start.sh
```

Then open **http://127.0.0.1:5000** in your browser.

Or with a custom port:

```bash
./start.sh 8080
```

### CLI

```bash
# Download best quality
python3 cli.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Choose quality
python3 cli.py "https://youtu.be/..." --quality 1080p

# Audio only
python3 cli.py "https://youtu.be/..." --quality audio_only

# Custom output directory
python3 cli.py "https://..." --output ~/Videos

# Just show video info
python3 cli.py "https://..." --info

# With cookies (for Instagram/Facebook)
python3 cli.py "https://www.instagram.com/reel/..." --cookies ~/cookies.txt

# Launch web UI from CLI
python3 cli.py --web
```

### Quality options

| Option | Description |
|---|---|
| `best` | Best video + best audio (default) |
| `1080p` | Up to 1080p |
| `720p` | Up to 720p |
| `480p` | Up to 480p |
| `audio_only` | Audio track only (saved as m4a/mp3) |

---

## Output

All downloads are saved to `~/Downloads/VideoDownloader/` by default.  
Filenames follow the pattern: `{uploader} - {title}.mp4`

---

## Cookies (for private/age-restricted content)

Some platforms (Instagram, Facebook, age-restricted YouTube) require you to be logged in. Export cookies from your browser using a browser extension like [cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) and pass the file path:

```bash
python3 cli.py "https://..." --cookies /path/to/cookies.txt
```

---

## Architecture

```
video downloader/
├── downloader.py      # Core engine (yt-dlp wrapper, threading, progress)
├── app.py             # Flask web server + REST API
├── cli.py             # Command-line interface
├── start.sh           # Quick launcher script
├── requirements.txt
├── templates/
│   └── index.html     # Web UI HTML
└── static/
    ├── css/style.css  # Styles
    └── js/app.js      # Frontend JavaScript
```

---

## Roadmap (Phase 2 — Chinese Platforms)

- [ ] Douyin (抖音)
- [ ] Xiaohongshu / RED (小红书)
- [ ] Bilibili (哔哩哔哩)
