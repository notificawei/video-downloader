"""
Core download engine built on yt-dlp.
Supports: YouTube, X/Twitter, Instagram, Facebook, TikTok
"""

import os
import re
import shutil
import threading
from pathlib import Path
from typing import Callable, Optional

import yt_dlp


def _find_ffmpeg() -> Optional[str]:
    """Return the directory containing ffmpeg, checking common macOS locations."""
    candidate = shutil.which("ffmpeg")
    if candidate:
        return str(Path(candidate).parent)
    for p in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
        if Path(p, "ffmpeg").exists():
            return p
    return None


_FFMPEG_LOCATION = _find_ffmpeg()

SUPPORTED_PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be"],
    "x_twitter": ["x.com", "twitter.com"],
    "instagram": ["instagram.com"],
    "facebook": ["facebook.com", "fb.watch"],
    "tiktok": ["tiktok.com", "vm.tiktok.com"],
    # Chinese platforms
    "bilibili": ["bilibili.com", "b23.tv"],
    "douyin": ["douyin.com", "v.douyin.com"],
    "xiaohongshu": ["xiaohongshu.com", "xhslink.com", "redbook.com"],
}

QUALITY_PRESETS = {
    "best": "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "audio_only": "bestaudio/best",
}

DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "VideoDownloader"


def detect_platform(url: str) -> Optional[str]:
    url_lower = url.lower()
    for platform, domains in SUPPORTED_PLATFORMS.items():
        if any(domain in url_lower for domain in domains):
            return platform
    return None


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


class DownloadProgress:
    def __init__(self):
        self.status = "idle"
        self.percent = 0.0
        self.speed = ""
        self.eta = ""
        self.filename = ""
        self.total_bytes = 0
        self.downloaded_bytes = 0
        self.error = None

    def to_dict(self):
        return {
            "status": self.status,
            "percent": round(self.percent, 1),
            "speed": self.speed,
            "eta": self.eta,
            "filename": self.filename,
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "error": self.error,
        }


class VideoDownloader:
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._active_downloads: dict[str, DownloadProgress] = {}
        self._lock = threading.Lock()

    def _make_progress_hook(self, progress: DownloadProgress) -> Callable:
        def hook(d):
            if d["status"] == "downloading":
                progress.status = "downloading"
                try:
                    downloaded = d.get("downloaded_bytes", 0) or 0
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    progress.downloaded_bytes = downloaded
                    progress.total_bytes = total
                    if total > 0:
                        progress.percent = (downloaded / total) * 100
                    else:
                        # Fall back to the percent string yt-dlp provides
                        pct_str = d.get("_percent_str", "0%").strip().replace("%", "")
                        try:
                            progress.percent = float(pct_str)
                        except ValueError:
                            pass
                    progress.speed = d.get("_speed_str", "").strip()
                    progress.eta = d.get("_eta_str", "").strip()
                    fn = d.get("filename", "")
                    if fn:
                        progress.filename = Path(fn).name
                except Exception:
                    pass
            elif d["status"] == "finished":
                progress.status = "processing"
                progress.percent = 100.0
                fn = d.get("filename", "")
                if fn:
                    progress.filename = Path(fn).name
            elif d["status"] == "error":
                progress.status = "error"
                progress.error = str(d.get("error", "Unknown error"))

        return hook

    def _build_ydl_opts(
        self,
        quality: str,
        progress: DownloadProgress,
        platform: Optional[str],
        cookies_file: Optional[str] = None,
        cookies_from_browser: Optional[str] = None,
    ) -> dict:
        format_selector = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["best"])

        opts = {
            "format": format_selector,
            "outtmpl": str(self.output_dir / "%(uploader)s - %(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            **({"ffmpeg_location": _FFMPEG_LOCATION} if _FFMPEG_LOCATION else {}),
            "proxy": "",  # bypass any inherited proxy env vars
            "noplaylist": True,
            "progress_hooks": [self._make_progress_hook(progress)],
            "quiet": True,
            "no_warnings": False,
            "extract_flat": False,
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                },
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                },
            ],
            "writethumbnail": False,
            "retries": 3,
            "fragment_retries": 3,
            "ratelimit": None,
        }

        if platform == "instagram":
            opts["noplaylist"] = False

        # Bilibili: prefer mp4 container; higher quality needs login cookies
        if platform == "bilibili":
            opts["format"] = format_selector + "/bestvideo+bestaudio/best"

        # Douyin / Xiaohongshu: disable playlist by default (share links are single videos)
        if platform in ("douyin", "xiaohongshu"):
            opts["noplaylist"] = True

        if cookies_file and Path(cookies_file).exists():
            opts["cookiefile"] = cookies_file
        elif cookies_from_browser:
            opts["cookiesfrombrowser"] = (cookies_from_browser,)

        return opts

    def get_info(self, url: str, cookies_from_browser: Optional[str] = None) -> dict:
        """Fetch video metadata without downloading."""
        ydl_opts: dict = {"quiet": True, "no_warnings": True, "proxy": ""}
        if cookies_from_browser:
            ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return {"error": "Could not retrieve video info"}

                formats = []
                for f in info.get("formats") or []:
                    height = f.get("height")
                    if height:
                        formats.append(
                            {
                                "format_id": f.get("format_id", ""),
                                "ext": f.get("ext", ""),
                                "height": height,
                                "width": f.get("width"),
                                "fps": f.get("fps"),
                                "vcodec": f.get("vcodec", "none"),
                                "acodec": f.get("acodec", "none"),
                                "filesize": f.get("filesize"),
                            }
                        )

                # Deduplicate heights and sort descending
                seen = set()
                unique_formats = []
                for f in sorted(formats, key=lambda x: x["height"], reverse=True):
                    if f["height"] not in seen:
                        seen.add(f["height"])
                        unique_formats.append(f)

                return {
                    "title": info.get("title", "Unknown"),
                    "uploader": info.get("uploader") or info.get("channel", "Unknown"),
                    "duration": info.get("duration"),
                    "thumbnail": info.get("thumbnail", ""),
                    "description": (info.get("description") or "")[:300],
                    "platform": detect_platform(url) or info.get("extractor", ""),
                    "view_count": info.get("view_count"),
                    "like_count": info.get("like_count"),
                    "upload_date": info.get("upload_date", ""),
                    "formats": unique_formats[:10],
                    "webpage_url": info.get("webpage_url", url),
                }
            except yt_dlp.utils.DownloadError as e:
                return {"error": str(e)}
            except Exception as e:
                return {"error": f"Unexpected error: {e}"}

    def download(
        self,
        url: str,
        quality: str = "best",
        download_id: str = "",
        cookies_file: Optional[str] = None,
        cookies_from_browser: Optional[str] = None,
    ) -> DownloadProgress:
        platform = detect_platform(url)
        progress = DownloadProgress()
        progress.status = "starting"

        if not download_id:
            import uuid
            download_id = str(uuid.uuid4())

        with self._lock:
            self._active_downloads[download_id] = progress

        def _run():
            opts = self._build_ydl_opts(quality, progress, platform, cookies_file, cookies_from_browser)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                if progress.status not in ("error",):
                    progress.status = "done"
                    progress.percent = 100.0
            except yt_dlp.utils.DownloadError as e:
                progress.status = "error"
                progress.error = str(e)
            except Exception as e:
                progress.status = "error"
                progress.error = f"Unexpected error: {e}"

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        return progress, download_id

    def get_progress(self, download_id: str) -> Optional[dict]:
        with self._lock:
            p = self._active_downloads.get(download_id)
        return p.to_dict() if p else None

    def list_downloads(self) -> list[dict]:
        with self._lock:
            return [
                {"id": k, **v.to_dict()}
                for k, v in self._active_downloads.items()
            ]

    @property
    def output_path(self) -> str:
        return str(self.output_dir)
