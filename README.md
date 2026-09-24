# Social Media Video Downloader + Scratch VO

Download videos from YouTube, Instagram, TikTok, Douyin, Facebook, X, Bilibili, and Xiaohongshu.

Also includes **Scratch VO**: paste an English script, generate an **offline** scratch voiceover for editing, and keep drafts in **My Scripts**. Final narration should still be recorded by the speaker.

## Scratch VO (offline, local only)

This path does **not** use Microsoft Edge TTS or any other cloud speech API. On a Mac it uses the built-in `say` command, so the script stays on your computer.

### Always-on install (recommended, no terminal to keep open)

```bash
bash install_autostart.sh
```

This registers a macOS login item, so the app runs in the background and starts again after a reboot. It is always at `http://localhost:8501` — bookmark that. It listens on `127.0.0.1` only, so nothing on the network can reach it.

To stop it and remove the login item:

```bash
bash uninstall_autostart.sh
```

### `ERR_CONNECTION_REFUSED` on localhost:8501

That means nothing is listening on the port — the app is not running. Run the checker:

```bash
bash check_vo.sh
```

It reports whether the files, Streamlit, the login item, and the port are each OK, and prints the last errors. Common causes:

- Never installed as a login item → `bash install_autostart.sh`
- macOS blocked the new background item → allow it in **System Settings → General → Login Items & Extensions**, then re-run the installer
- Streamlit missing for the `python3` in use → `python3 -m pip install --user streamlit`

### Run it manually instead

```bash
pip install -r requirements.txt
python3 -m streamlit run vo_app.py
```

This only stays up while that terminal window is running.

Do **not** deploy this to Streamlit Cloud and do **not** use a public tunnel if the script is unpublished news.

- **Generate audio** writes a WAV on this machine
- **My Scripts** stores drafts in `data/scripts.json` on this machine
- Speed defaults to **-5%** (about 165 words/minute at 0%)

### Voices sound robotic?

macOS ships only compact voices by default. Download better ones in **System Settings → Accessibility → Spoken Content → System Voice → Manage Voices** and pick English voices marked **Premium** (best) or **Enhanced**. The download is one-time; generating stays offline.

The voice list hides macOS novelty voices (Bells, Zarvox, Bubbles and friends) and sorts Premium first, then Enhanced, then basic.

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
