"""
Core download engine built on yt-dlp.
Supports: YouTube, X/Twitter, Instagram, Facebook, TikTok
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

import requests
import yt_dlp

# Log to the same file launchd uses so errors are always visible.
_LOG_FILE = Path.home() / "Library" / "Logs" / "videoget.log"
_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def _find_ffmpeg() -> Optional[str]:
    """Return the directory containing ffmpeg, checking common macOS locations."""
    candidate = shutil.which("ffmpeg")
    if candidate:
        return str(Path(candidate).parent)
    for p in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
        if Path(p, "ffmpeg").exists():
            return p
    return None


def _find_node() -> Optional[str]:
    """Return the full path to a node/bun executable for yt-dlp's JS runtime."""
    for name in ("node", "bun"):
        candidate = shutil.which(name)
        if candidate:
            return candidate
    for p in ("/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node",
              "/opt/homebrew/bin/bun", "/usr/local/bin/bun"):
        if Path(p).exists():
            return p
    return None


def _find_wechat_cookie_file() -> Optional[str]:
    """Return a Netscape cookie file containing Tencent cookies, if one exists.

    Decrypting Chrome cookies needs macOS Keychain access, which a launchd
    agent usually cannot obtain, so an exported cookie file is the reliable
    way to authenticate WeChat Channels downloads.
    """
    for p in (
        Path.home() / "yuanbao_cookies.txt",
        Path.home() / ".config" / "savextube" / "yuanbao_cookies.txt",
        Path.home() / "Desktop" / "yuanbao_cookies.txt",
        Path(__file__).parent / "yuanbao_cookies.txt",
    ):
        if p.is_file():
            return str(p)
    return None


def _prepare_wechat_cookies() -> Optional[str]:
    """Point the WeChat plugin at a Tencent cookie file via its env var."""
    cookie_file = _find_wechat_cookie_file()
    if cookie_file:
        os.environ["YUANBAO_COOKIE_FILE"] = cookie_file
        log.info("WeChat: using Yuanbao cookie file %s", cookie_file)
    else:
        log.warning(
            "WeChat: no Yuanbao cookie file found — falling back to browser "
            "cookies, which often fail under launchd (no Keychain access)"
        )
    return cookie_file


def _read_netscape_cookie_string(path: Path, domain_filter: str) -> str:
    """Flatten a Netscape cookie file into a 'name=value; ...' header string."""
    parts = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        # Netscape files mark HttpOnly entries with a comment-style prefix.
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        domain, name, value = fields[0], fields[5], fields[6]
        if domain_filter in domain.lower():
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def _parse_cookie_file(path: Path, domain_filter: str) -> str:
    """Read a cookie file in either Netscape or raw 'name=value; ...' format.

    Browser extensions export Netscape files, but copying the Cookie request
    header straight out of DevTools is the only option on machines where
    extensions cannot be installed, so both layouts are accepted.
    """
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return ""

    # Netscape records are tab-separated; a pasted header never is.
    if "\t" not in text:
        pairs = [
            part.strip()
            for part in text.replace("\n", ";").split(";")
            if "=" in part
        ]
        return "; ".join(pairs)

    return _read_netscape_cookie_string(path, domain_filter)


def _load_douyin_cookie_string() -> Optional[str]:
    """Return a Douyin cookie header from an exported cookie file, if present.

    F2 needs a logged-in cookie to read a profile's post list. Reading it from
    Chrome requires Keychain access that a launchd agent cannot obtain, so an
    exported file is the dependable source.
    """
    for p in (
        Path.home() / "douyin_cookies.txt",
        Path.home() / "Desktop" / "douyin_cookies.txt",
        Path(__file__).parent / "douyin_cookies.txt",
    ):
        if p.is_file():
            cookie = _parse_cookie_file(p, "douyin.com")
            if cookie:
                log.info("Douyin: using cookie file %s", p)
                return cookie
            log.warning("Douyin: %s contains no douyin.com cookies", p)
    return None


def _douyin_failure_message(
    return_code: int,
    saved_items: int,
    errors: list[str],
    had_cookie_file: bool,
) -> str:
    """Build an actionable message for a Douyin profile download failure."""
    if saved_items == 0 and return_code == 0:
        reason = "抖音接口未返回任何作品"
    else:
        reason = f"F2 退出码 {return_code}"

    if not had_cookie_file:
        advice = (
            "缺少抖音登录 cookie。请在 Chrome 登录抖音后按 F12 打开开发者工具，"
            "在 Network 标签中复制任一请求的 Cookie 请求头，"
            "保存为 ~/douyin_cookies.txt 再重试。"
        )
    else:
        advice = (
            "cookie 可能已过期或该主页无公开作品。请重新导出 "
            "~/douyin_cookies.txt 后重试。"
        )

    detail = f"（{errors[-1]}）" if errors else ""
    return f"抖音主页下载失败：{reason}{detail}。{advice}"


def _find_plugin_dirs() -> list[str]:
    """Return parent directories that contain yt_dlp_plugins packages.

    When the app runs as a launchd service the Python sys.path may not include
    all user/site-packages directories, so yt-dlp can miss installed plugins.
    We find them explicitly and pass them through the plugin_dirs ydl option.
    """
    import sys

    dirs: list[str] = []

    def _add(p: Path) -> None:
        s = str(p)
        if p.is_dir() and s not in dirs:
            dirs.append(s)

    # 1. Every entry already in sys.path that has a yt_dlp_plugins sub-dir.
    for base in sys.path:
        if (Path(base) / "yt_dlp_plugins").is_dir():
            _add(Path(base))

    # 2. Common Homebrew system site-packages  (/opt/homebrew/lib/python3.x/site-packages)
    for prefix in ("/opt/homebrew/lib", "/usr/local/lib"):
        p = Path(prefix)
        if p.exists():
            for sp in p.glob("python*/site-packages"):
                if (sp / "yt_dlp_plugins").is_dir():
                    _add(sp)

    # 3. macOS user site-packages installed by `pip --user` or `--break-system-packages`
    #    Pattern: ~/Library/Python/<major.minor>/lib/python/site-packages
    user_lib = Path.home() / "Library" / "Python"
    if user_lib.exists():
        for ver_dir in user_lib.iterdir():
            sp = ver_dir / "lib" / "python" / "site-packages"
            if (sp / "yt_dlp_plugins").is_dir():
                _add(sp)

    return dirs


_FFMPEG_LOCATION = _find_ffmpeg()
_NODE_PATH = _find_node()
_PLUGIN_DIRS = _find_plugin_dirs()

log.info("ffmpeg: %s", _FFMPEG_LOCATION or "not found")
log.info("node/bun: %s", _NODE_PATH or "not found")
log.info("yt-dlp plugin dirs: %s", _PLUGIN_DIRS or "none")

SUPPORTED_PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be"],
    "x_twitter": ["x.com", "twitter.com"],
    "instagram": ["instagram.com"],
    "facebook": ["facebook.com", "fb.watch"],
    "tiktok": ["tiktok.com", "vm.tiktok.com"],
    # Chinese platforms
    "bilibili": ["bilibili.com", "b23.tv"],
    "douyin": ["douyin.com", "iesdouyin.com", "v.douyin.com"],
    "xiaohongshu": ["xiaohongshu.com", "xhslink.com", "redbook.com"],
    # WeChat Channels (via yt-dlp-patch plugin)
    "wechat": ["weixin.qq.com/sph", "channels.weixin.qq.com", "finder.video.qq.com"],
}

QUALITY_PRESETS = {
    "best": "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "audio_only": "bestaudio/best",
}

DEFAULT_OUTPUT_DIR = Path.home() / "Desktop" / "VideoDownloader"


def detect_platform(url: str) -> Optional[str]:
    url_lower = url.lower()
    for platform, domains in SUPPORTED_PLATFORMS.items():
        if any(domain in url_lower for domain in domains):
            return platform
    return None


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def is_douyin_profile_url(url: str) -> bool:
    """Return whether a URL identifies a Douyin user profile.

    Douyin's share button often produces a v.douyin.com short URL, so resolve
    that redirect before deciding whether it points to a profile or one post.
    """
    profile_pattern = (
        r'https?://(?:www\.)?(?:douyin|iesdouyin)\.com/(?:share/)?user/'
    )
    if re.search(profile_pattern, url, flags=re.IGNORECASE):
        return True
    if "v.douyin.com/" not in url.lower():
        return False

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
                )
            },
            allow_redirects=True,
            timeout=10,
        )
        return bool(re.search(profile_pattern, response.url, flags=re.IGNORECASE))
    except requests.RequestException:
        return False


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
        self.is_batch = False
        self.completed_items = 0

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
            "is_batch": self.is_batch,
            "completed_items": self.completed_items,
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
        output_dir: Optional[str] = None,
    ) -> dict:
        format_selector = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["best"])
        out_dir = Path(output_dir) if output_dir else self.output_dir

        opts = {
            "format": format_selector,
            "outtmpl": str(out_dir / "%(uploader)s - %(title)s [%(id)s].%(ext)s"),
            "merge_output_format": "mp4",
            **({"ffmpeg_location": _FFMPEG_LOCATION} if _FFMPEG_LOCATION else {}),
            **({"plugin_dirs": _PLUGIN_DIRS} if _PLUGIN_DIRS else {}),
            "proxy": "",  # bypass any inherited proxy env vars
            "noplaylist": True,
            "progress_hooks": [self._make_progress_hook(progress)],
            "quiet": True,
            "no_warnings": False,
            "extract_flat": False,
            "postprocessors": [],
            "writethumbnail": False,
            "retries": 3,
            "fragment_retries": 3,
            "ratelimit": None,
        }

        if platform == "youtube":
            # yt-dlp 2026+ requires a JS runtime to generate PO tokens for YouTube.
            # Pass Node.js/Bun if available; without it many formats are unavailable.
            if _NODE_PATH:
                runtime_name = "bun" if "bun" in _NODE_PATH else "node"
                opts["js_runtimes"] = [f"{runtime_name}:{_NODE_PATH}"]
            # mweb (mobile web) player client works without PO tokens and bypasses
            # most bot-detection checks that affect the default android client.
            opts["extractor_args"] = {
                "youtube": {"player_client": ["mweb", "web", "android"]}
            }

        if platform == "instagram":
            opts["noplaylist"] = False

        # Bilibili: prefer mp4 container; higher quality needs login cookies
        if platform == "bilibili":
            opts["format"] = format_selector + "/bestvideo+bestaudio/best"

        # Douyin / Xiaohongshu: disable playlist by default (share links are single videos)
        if platform in ("douyin", "xiaohongshu"):
            opts["noplaylist"] = True

        # WeChat Channels: requires Tencent cookies (from Chrome/Safari after
        # visiting yuanbao.tencent.com or WeChat Web).
        if platform == "wechat":
            opts["noplaylist"] = True
            _prepare_wechat_cookies()

        if cookies_file and Path(cookies_file).exists():
            opts["cookiefile"] = cookies_file
        elif cookies_from_browser:
            opts["cookiesfrombrowser"] = (cookies_from_browser,)

        return opts

    def get_info(self, url: str, cookies_from_browser: Optional[str] = None) -> dict:
        """Fetch video metadata without downloading."""
        ydl_opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "proxy": "",
            **({"plugin_dirs": _PLUGIN_DIRS} if _PLUGIN_DIRS else {}),
        }
        if cookies_from_browser:
            ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
        platform = detect_platform(url)
        if platform == "douyin" and is_douyin_profile_url(url):
            profile_id = re.search(r'/(?:share/)?user/([^/?#]+)', url, re.IGNORECASE)
            return {
                "title": "抖音主页全部作品",
                "uploader": f"主页 ID: {profile_id.group(1)}" if profile_id else "抖音用户主页",
                "duration": None,
                "thumbnail": "",
                "description": "将自动分页下载该主页公开发布的所有视频和图文作品。",
                "platform": "douyin",
                "view_count": None,
                "like_count": None,
                "upload_date": "",
                "formats": [],
                "webpage_url": url,
                "is_profile": True,
            }

        if platform == "youtube":
            if _NODE_PATH:
                runtime_name = "bun" if "bun" in _NODE_PATH else "node"
                ydl_opts["js_runtimes"] = [f"{runtime_name}:{_NODE_PATH}"]
            ydl_opts["extractor_args"] = {
                "youtube": {"player_client": ["mweb", "web", "android"]}
            }
        elif platform == "wechat":
            _prepare_wechat_cookies()
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
        download_profile: bool = False,
    ) -> DownloadProgress:
        platform = detect_platform(url)
        progress = DownloadProgress()
        progress.status = "starting"
        download_profile = (
            platform == "douyin"
            and (download_profile or is_douyin_profile_url(url))
        )
        progress.is_batch = download_profile

        if not download_id:
            import uuid
            download_id = str(uuid.uuid4())

        with self._lock:
            self._active_downloads[download_id] = progress

        def _run():
            if download_profile:
                self._run_douyin_profile_download(
                    url, progress, cookies_from_browser=cookies_from_browser
                )
                return

            # Download into a private temp dir so yt-dlp can freely rename/merge,
            # then move the finished file into the real output directory.
            with tempfile.TemporaryDirectory(prefix="vdl_") as tmp_dir:
                opts = self._build_ydl_opts(
                    quality, progress, platform, cookies_file, cookies_from_browser,
                    output_dir=tmp_dir,
                )
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])

                    if progress.status in ("error",):
                        return

                    # Re-encode to H.264/AAC for universal compatibility
                    # (QuickTime, Premiere Pro, VLC, etc.)
                    progress.status = "processing"
                    ffmpeg = shutil.which("ffmpeg") or (
                        str(Path(_FFMPEG_LOCATION) / "ffmpeg") if _FFMPEG_LOCATION else "ffmpeg"
                    )
                    for src in sorted(Path(tmp_dir).iterdir()):
                        if src.suffix not in (".mp4", ".m4a", ".mp3", ".webm", ".mkv"):
                            continue
                        dest = self.output_dir / src.with_suffix(".mp4").name
                        result = subprocess.run(
                            [
                                ffmpeg, "-y", "-i", str(src),
                                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                                "-c:a", "aac", "-b:a", "192k",
                                "-movflags", "+faststart",
                                str(dest),
                            ],
                            capture_output=True,
                        )
                        if result.returncode == 0:
                            progress.filename = dest.name
                        else:
                            # Fallback: just move as-is if ffmpeg fails
                            shutil.move(str(src), str(dest))
                            progress.filename = dest.name

                    progress.status = "done"
                    progress.percent = 100.0
                except yt_dlp.utils.DownloadError as e:
                    progress.status = "error"
                    progress.error = str(e)
                    log.error("DownloadError for %s: %s", url, e)
                except Exception as e:
                    progress.status = "error"
                    progress.error = f"Unexpected error: {e}"
                    log.exception("Unexpected error downloading %s", url)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        return progress, download_id

    def _run_douyin_profile_download(
        self,
        url: str,
        progress: DownloadProgress,
        cookies_from_browser: Optional[str] = None,
    ) -> None:
        """Download every public post from a Douyin profile using F2."""
        progress.status = "downloading"
        progress.filename = "正在读取抖音主页作品列表…"

        before = {
            p.resolve()
            for p in self.output_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in (".mp4", ".webm", ".jpg", ".jpeg", ".png")
        }
        command = [
            sys.executable, "-m", "f2", "dy",
            "--url", url,
            "--mode", "post",
            "--path", str(self.output_dir),
            "--interval", "all",
            "--max-counts", "0",
            "--page-counts", "20",
        ]
        cookie_string = _load_douyin_cookie_string()
        if cookie_string:
            command.extend(["--cookie", cookie_string])
        elif cookies_from_browser:
            log.warning(
                "Douyin: no cookie file found — falling back to --auto-cookie, "
                "which usually fails under launchd (no Keychain access)"
            )
            command.extend(["--auto-cookie", cookies_from_browser])

        log.info("Starting Douyin profile download: %s", url)
        recent_errors: list[str] = []
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
                if clean_line:
                    log.info("[f2] %s", clean_line)
                    if "Error" in clean_line or "错误" in clean_line:
                        recent_errors.append(clean_line)
                current = {
                    p.resolve()
                    for p in self.output_dir.rglob("*")
                    if p.is_file()
                    and p.suffix.lower() in (".mp4", ".webm", ".jpg", ".jpeg", ".png")
                }
                progress.completed_items = len(current - before)
                if progress.completed_items:
                    progress.filename = f"已保存 {progress.completed_items} 个作品"

            return_code = process.wait()

            after = {
                p.resolve()
                for p in self.output_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in (".mp4", ".webm", ".jpg", ".jpeg", ".png")
            }
            progress.completed_items = len(after - before)

            # Douyin rejects unauthenticated profile reads, and F2 does not
            # always signal that through its exit code, so saving nothing is
            # treated as a failure rather than reported as a finished download.
            if return_code != 0 or progress.completed_items == 0:
                raise RuntimeError(_douyin_failure_message(
                    return_code, progress.completed_items, recent_errors,
                    bool(cookie_string),
                ))

            progress.filename = f"已保存 {progress.completed_items} 个作品"
            progress.percent = 100.0
            progress.status = "done"
        except Exception as e:
            progress.status = "error"
            progress.error = str(e)
            log.exception("Douyin profile download failed for %s", url)

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
