#!/usr/bin/env python3
"""
CLI interface for VideoGet downloader.
Usage:
    python cli.py <URL> [--quality best|1080p|720p|480p|audio_only] [--output DIR]
"""

import argparse
import sys
import time
from pathlib import Path

from downloader import VideoDownloader, QUALITY_PRESETS, detect_platform


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_duration(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


PLATFORM_COLORS = {
    "youtube": "\033[91m",
    "x_twitter": "\033[94m",
    "instagram": "\033[95m",
    "facebook": "\033[34m",
    "tiktok": "\033[31m",
}
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"


def print_bar(percent: float, width: int = 40) -> str:
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percent:5.1f}%"


def main():
    parser = argparse.ArgumentParser(
        prog="videoget",
        description="Download high-res videos from YouTube, X, Instagram, Facebook, TikTok",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="Video URL to download")
    parser.add_argument(
        "--quality", "-q",
        choices=list(QUALITY_PRESETS.keys()),
        default="best",
        help=f"Quality preset (default: best)\n  {chr(10).join(QUALITY_PRESETS.keys())}",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory (default: ~/Downloads/VideoDownloader)",
    )
    parser.add_argument(
        "--info", "-i",
        action="store_true",
        help="Fetch and display video info without downloading",
    )
    parser.add_argument(
        "--cookies", "-c",
        default=None,
        help="Path to cookies.txt file (required for some platforms like Instagram)",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the web UI instead",
    )

    args = parser.parse_args()

    if args.web:
        import subprocess, webbrowser, time as _t
        print(f"{BOLD}Starting web server at http://127.0.0.1:5000{RESET}")
        proc = subprocess.Popen([sys.executable, "app.py"])
        _t.sleep(1.5)
        webbrowser.open("http://127.0.0.1:5000")
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
        return

    if not args.url:
        parser.print_help()
        sys.exit(0)

    url = args.url.strip()
    platform = detect_platform(url)

    dl = VideoDownloader(output_dir=args.output)

    # ── Info mode ────────────────────────────────────────────────────────────
    if args.info:
        print(f"\n{DIM}Fetching info…{RESET}")
        info = dl.get_info(url)
        if "error" in info:
            print(f"{RED}Error: {info['error']}{RESET}")
            sys.exit(1)

        color = PLATFORM_COLORS.get(info.get("platform", ""), "")
        print(f"\n{BOLD}{color}▶ {info['title']}{RESET}")
        print(f"  Uploader  : {info['uploader']}")
        if info.get("duration"):
            print(f"  Duration  : {fmt_duration(info['duration'])}")
        if info.get("view_count"):
            print(f"  Views     : {info['view_count']:,}")
        print(f"  Platform  : {info['platform']}")
        if info.get("formats"):
            print(f"  Resolutions: {', '.join(str(f['height'])+'p' for f in info['formats'])}")
        print()
        return

    # ── Download mode ────────────────────────────────────────────────────────
    color = PLATFORM_COLORS.get(platform or "", "")
    print(f"\n{BOLD}VideoGet{RESET}  {DIM}yt-dlp powered downloader{RESET}")
    print(f"  URL      : {DIM}{url}{RESET}")
    print(f"  Platform : {color}{platform or 'auto-detect'}{RESET}")
    print(f"  Quality  : {YELLOW}{args.quality}{RESET}")
    print(f"  Save to  : {dl.output_path}\n")

    progress, download_id = dl.download(url=url, quality=args.quality, cookies_file=args.cookies)

    last_status = None
    try:
        while True:
            time.sleep(0.3)
            p = dl.get_progress(download_id)
            if not p:
                break

            status = p["status"]

            if status == "downloading":
                bar = print_bar(p["percent"])
                speed = p["speed"] or "–"
                eta = p["eta"] or "–"
                line = f"\r  {bar}  {speed}  ETA {eta}  "
                sys.stdout.write(line)
                sys.stdout.flush()

            elif status == "processing" and last_status != "processing":
                sys.stdout.write(f"\r  {print_bar(100)}  {YELLOW}Post-processing…{RESET}      \n")

            elif status == "done":
                fname = p["filename"] or ""
                sys.stdout.write(f"\r  {print_bar(100)}  {GREEN}Done!{RESET}                \n")
                if fname:
                    print(f"\n  {GREEN}✓{RESET} Saved: {BOLD}{fname}{RESET}")
                print(f"  Folder : {dl.output_path}\n")
                break

            elif status == "error":
                sys.stdout.write("\n")
                print(f"\n  {RED}✗ Error: {p['error']}{RESET}\n")
                sys.exit(1)

            last_status = status

    except KeyboardInterrupt:
        print(f"\n\n  {YELLOW}Cancelled.{RESET}\n")
        sys.exit(130)


if __name__ == "__main__":
    main()
