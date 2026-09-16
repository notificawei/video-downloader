# Social Media Video Downloader + Scratch VO

Download videos from YouTube, Instagram, TikTok, Douyin, Facebook, X, Bilibili, and Xiaohongshu.

Also includes **Scratch VO**: paste an English script, generate an **offline** scratch voiceover for editing, and keep drafts in **My Scripts**. Final narration should still be recorded by the speaker.

## Scratch VO (offline, local only)

This path does **not** use Microsoft Edge TTS or any other cloud speech API. On a Mac it uses the built-in `say` command, so the script stays on your computer.

```bash
pip install -r requirements.txt
python3 -m streamlit run vo_app.py
```

Open the **local** URL Streamlit prints (`http://localhost:8501`). Do **not** deploy this to Streamlit Cloud and do **not** use a public tunnel if the script is unpublished news.

- **Generate audio** writes a WAV on this machine
- **My Scripts** stores drafts in `data/scripts.json` on this machine
- Speed defaults to **-5%** (about 165 words/minute at 0%)
- For better Mac voices: System Settings → Accessibility → Spoken Content → download an English voice while online, then you can generate fully offline

If `streamlit` is not on your PATH, keep using `python3 -m streamlit`.

## Desktop App

```bash
bash install.sh
python3 video_downloader.py
```

## Deploy Online (Streamlit Cloud) — Get a Shareable Link

### Step 1 — Push to GitHub

1. Go to [github.com](https://github.com) → **New repository** → name it `video-downloader` → **Create**
2. Open Terminal and run:

```bash
cd "/Users/wangjiawei/Desktop/video downloader vb coding"
git init
git add app.py requirements.txt
git commit -m "Add web app"
git remote add origin https://github.com/YOUR_USERNAME/video-downloader.git
git push -u origin main
```

> Replace `YOUR_USERNAME` with your GitHub username.

### Step 2 — Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
2. Click **New app**
3. Select your `video-downloader` repository
4. Set **Main file path** to `app.py` (video downloader) or `vo_app.py` (Scratch VO)
5. Click **Deploy**

You can deploy both as two Streamlit apps from the same repo by choosing a different main file each time. **My Scripts** is stored in `data/scripts.json` on the machine running the app (local runs persist; Streamlit Cloud may reset that file when the app sleeps).

After ~2 minutes you'll get a link like:
```
https://YOUR_USERNAME-video-downloader-app-xxxx.streamlit.app
```

Share that link with anyone — no installation needed on their end.

### Notes

- The web version only works for **public videos** (no login required)
- For private/login-required content, use the desktop app with browser cookies
- Free Streamlit Cloud has a 1 GB memory limit — very large files (>500 MB) may fail
