# Social Media Video Downloader

Download videos from YouTube, Instagram, TikTok, Douyin, Facebook, X, Bilibili, and Xiaohongshu.

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
4. Set **Main file path** to `app.py`
5. Click **Deploy**

After ~2 minutes you'll get a link like:
```
https://YOUR_USERNAME-video-downloader-app-xxxx.streamlit.app
```

Share that link with anyone — no installation needed on their end.

### Notes

- The web version only works for **public videos** (no login required)
- For private/login-required content, use the desktop app with browser cookies
- Free Streamlit Cloud has a 1 GB memory limit — very large files (>500 MB) may fail
