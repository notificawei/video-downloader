"""
Flask web server — REST API + static file serving for the video downloader UI.
"""

import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from downloader import VideoDownloader, QUALITY_PRESETS, SUPPORTED_PLATFORMS, detect_platform

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

downloader = VideoDownloader()


# ── Static pages ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/info", methods=["POST"])
def api_info():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    cookies_from_browser = (data.get("cookies_from_browser") or "").strip() or None
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    info = downloader.get_info(url, cookies_from_browser=cookies_from_browser)
    return jsonify(info)


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    quality = (data.get("quality") or "best").strip()
    cookies_file = (data.get("cookies_file") or "").strip() or None
    cookies_from_browser = (data.get("cookies_from_browser") or "").strip() or None

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    if quality not in QUALITY_PRESETS:
        quality = "best"

    download_id = str(uuid.uuid4())
    _progress, did = downloader.download(
        url=url,
        quality=quality,
        download_id=download_id,
        cookies_file=cookies_file,
        cookies_from_browser=cookies_from_browser,
    )

    return jsonify({"download_id": did, "status": "started", "output_dir": downloader.output_path})


@app.route("/api/progress/<download_id>")
def api_progress(download_id):
    progress = downloader.get_progress(download_id)
    if progress is None:
        return jsonify({"error": "Download not found"}), 404
    return jsonify(progress)


@app.route("/api/downloads")
def api_downloads():
    return jsonify(downloader.list_downloads())


@app.route("/api/platforms")
def api_platforms():
    return jsonify(
        {
            "western": {
                k: v
                for k, v in SUPPORTED_PLATFORMS.items()
            },
            "qualities": list(QUALITY_PRESETS.keys()),
        }
    )


@app.route("/api/output_dir")
def api_output_dir():
    return jsonify({"path": downloader.output_path})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Video Downloader Web Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--output", default=None, help="Custom output directory")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.output:
        downloader = VideoDownloader(output_dir=args.output)

    print(f"\n  Video Downloader running at  http://{args.host}:{args.port}")
    print(f"  Downloads saved to           {downloader.output_path}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)
