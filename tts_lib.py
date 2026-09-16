import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent / "data"
SCRIPTS_FILE = SCRIPTS_DIR / "scripts.json"

DEFAULT_RATE = -5
DEFAULT_WPM = 165


def load_scripts():
    if not SCRIPTS_FILE.exists():
        return []
    try:
        return json.loads(SCRIPTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_scripts(scripts):
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    SCRIPTS_FILE.write_text(
        json.dumps(scripts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def slugify(text, fallback="scratch"):
    words = re.findall(r"[A-Za-z0-9]+", text)
    slug = "-".join(words[:8]).lower() if words else fallback
    return slug[:60] or fallback


def rate_to_wpm(rate_pct):
    wpm = int(round(DEFAULT_WPM * (1 + rate_pct / 100.0)))
    return max(80, min(300, wpm))


def engine_name():
    if sys.platform == "darwin" and shutil.which("say"):
        return "macos_say"
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        return "espeak"
    return "none"


def engine_label():
    name = engine_name()
    if name == "macos_say":
        return "macOS Speech (offline, on this Mac only)"
    if name == "espeak":
        return "eSpeak NG (offline)"
    return "No offline TTS engine found"


def _parse_say_voices(raw):
    voices = []
    seen = set()
    for line in raw.splitlines():
        match = re.match(r"^(\S.*?)\s+([a-z]{2}_[A-Z]{2}|en_US|en_GB|en_AU|en_IN)\s+", line)
        if not match:
            continue
        voice, locale = match.group(1).strip(), match.group(2)
        if not locale.lower().startswith("en"):
            continue
        if voice in seen:
            continue
        seen.add(voice)
        voices.append(voice)
    return voices


def list_voices():
    name = engine_name()
    if name == "macos_say":
        try:
            raw = subprocess.check_output(["say", "-v", "?"], text=True, stderr=subprocess.STDOUT)
        except (OSError, subprocess.CalledProcessError):
            return ["Samantha", "Alex"]
        voices = _parse_say_voices(raw)
        preferred = [
            "Samantha",
            "Ava",
            "Zoe",
            "Allison",
            "Susan",
            "Victoria",
            "Fiona",
            "Moira",
            "Kate",
            "Daniel",
            "Alex",
        ]
        ordered = [v for v in preferred if v in voices]
        ordered.extend(v for v in voices if v not in ordered)
        return ordered or ["Samantha"]
    if name == "espeak":
        return {
            "English US": "en-us",
            "English UK": "en-gb",
            "English": "en",
        }
    return {}


def _espeak_bin():
    return shutil.which("espeak-ng") or shutil.which("espeak")


def _run(cmd, **kwargs):
    subprocess.run(cmd, check=True, **kwargs)


def synthesize(text, voice, rate_pct, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wpm = rate_to_wpm(rate_pct)
    name = engine_name()

    if name == "macos_say":
        _synthesize_macos(text, voice, wpm, out_path)
        return
    if name == "espeak":
        _synthesize_espeak(text, voice, wpm, out_path)
        return
    raise RuntimeError(
        "No offline TTS engine found. On a Mac this app uses the built-in say command. "
        "Do not use Edge TTS — that would send the script to Microsoft."
    )


def _synthesize_macos(text, voice, wpm, out_path):
    wav_path = out_path.with_suffix(".wav")
    cmd = [
        "say",
        "-v",
        voice,
        "-r",
        str(wpm),
        "-o",
        str(wav_path),
        "--data-format=LEI16@22050",
    ]
    try:
        _run(cmd, input=text, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        aiff_path = out_path.with_suffix(".aiff")
        _run(
            ["say", "-v", voice, "-r", str(wpm), "-o", str(aiff_path)],
            input=text,
            capture_output=True,
            text=True,
        )
        wav_path = _to_wav(aiff_path)
    final = _to_wav(wav_path) if wav_path.suffix.lower() != ".wav" else wav_path
    if final != out_path:
        if out_path.exists():
            out_path.unlink()
        os.replace(final, out_path)


def _synthesize_espeak(text, voice, wpm, out_path):
    wav_path = out_path.with_suffix(".wav")
    bin_name = _espeak_bin()
    _run(
        [bin_name, "-v", voice, "-s", str(wpm), "-w", str(wav_path), "--", text],
        capture_output=True,
        text=True,
    )
    if wav_path != out_path:
        if out_path.exists():
            out_path.unlink()
        os.replace(wav_path, out_path)


def _to_wav(src):
    src = Path(src)
    if src.suffix.lower() == ".wav":
        return src
    wav = src.with_suffix(".wav")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        _run(
            [ffmpeg, "-y", "-i", str(src), "-acodec", "pcm_s16le", str(wav)],
            capture_output=True,
            text=True,
        )
        src.unlink(missing_ok=True)
        return wav
    raise RuntimeError(f"Could not convert {src.suffix} to WAV (ffmpeg not found).")
