import streamlit as st
import yt_dlp
import tempfile
import os
from pathlib import Path

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_PATH = None

QUALITY_OPTIONS = ["Best Quality", "1080p", "720p", "480p", "Audio Only (MP3)"]
QUALITY_FORMAT_MAP = {
    "Best Quality":     "bestvideo+bestaudio/best",
    "1080p":            "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p":             "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p":             "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "Audio Only (MP3)": "bestaudio/best",
}

st.set_page_config(
    page_title="Video Downloader",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 Social Media Video Downloader")
st.caption(
    "Supports: **YouTube** · **Instagram** · **TikTok** · **Douyin** · "
    "**Facebook** · **X** · **Bilibili** · **Xiaohongshu**"
)
st.divider()

url = st.text_input(
    "Video URL",
    placeholder="https://www.youtube.com/watch?v=...",
    label_visibility="collapsed",
)

col1, col2 = st.columns([1, 1])
with col1:
    quality = st.selectbox("Quality", QUALITY_OPTIONS)
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    download_clicked = st.button("⬇️ Download", type="primary", use_container_width=True)

st.caption(
    "⚠️ Note: private or login-required videos cannot be downloaded from the web version. "
    "Use the desktop app for those."
)

if download_clicked:
    url = url.strip()
    if not url:
        st.warning("Please paste a video URL first.")
    else:
        progress_bar = st.progress(0, text="Starting download…")
        status_text = st.empty()

        try:
            tmpdir = tempfile.mkdtemp()
            is_audio = quality == "Audio Only (MP3)"

            def progress_hook(d):
                if d["status"] == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    if total > 0:
                        pct = int(downloaded / total * 100)
                        speed = d.get("_speed_str", "")
                        eta = d.get("_eta_str", "")
                        progress_bar.progress(
                            min(pct, 99),
                            text=f"Downloading… {pct}%  {speed}  ETA {eta}",
                        )

            ydl_opts = {
                "format": QUALITY_FORMAT_MAP[quality],
                "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
                "merge_output_format": "mp4",
                "progress_hooks": [progress_hook],
                "quiet": True,
                "no_warnings": True,
            }
            if FFMPEG_PATH:
                ydl_opts["ffmpeg_location"] = FFMPEG_PATH
            if is_audio:
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "video") if info else "video"

            files = os.listdir(tmpdir)
            if not files:
                st.error("Download failed: no file was produced.")
            else:
                filepath = os.path.join(tmpdir, files[0])
                with open(filepath, "rb") as f:
                    data = f.read()

                progress_bar.progress(100, text="Done!")
                status_text.success(f"✅ **{title}**")

                mime = "audio/mpeg" if is_audio else "video/mp4"
                st.download_button(
                    label="💾 Save to your computer",
                    data=data,
                    file_name=files[0],
                    mime=mime,
                    use_container_width=True,
                )

        except Exception as e:
            progress_bar.empty()
            err = str(e)
            if "Private video" in err or "login" in err.lower():
                st.error(
                    "❌ This video requires login. "
                    "Please use the desktop app with your browser cookies."
                )
            elif "not available" in err.lower():
                st.error("❌ This video is not available or the URL is invalid.")
            else:
                st.error(f"❌ Download failed: {err[:200]}")

st.divider()
st.markdown(
    "<div style='text-align:center; color:gray; font-size:12px'>"
    "Powered by <a href='https://github.com/yt-dlp/yt-dlp' target='_blank'>yt-dlp</a>"
    "</div>",
    unsafe_allow_html=True,
)
