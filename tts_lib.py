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


def wav_duration(path):
    import wave

    try:
        with wave.open(str(path)) as handle:
            return handle.getnframes() / float(handle.getframerate())
    except Exception:
        return None


def slugify(text, fallback="scratch"):
    words = re.findall(r"[A-Za-z0-9]+", text)
    slug = "-".join(words[:8]).lower() if words else fallback
    return slug[:60] or fallback


def rate_to_wpm(rate_pct):
    wpm = int(round(DEFAULT_WPM * (1 + rate_pct / 100.0)))
    return max(80, min(300, wpm))


# Neural voices that run entirely on this machine once the model file is downloaded.
PIPER_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en"

PIPER_VOICES = {
    "Lessac (US, female) — clearest": "en_US/lessac/high/en_US-lessac-high",
    "Amy (US, female) — warm": "en_US/amy/medium/en_US-amy-medium",
    "Kristin (US, female) — bright": "en_US/kristin/medium/en_US-kristin-medium",
    "HFC Female (US) — neutral": "en_US/hfc_female/medium/en_US-hfc_female-medium",
    "Ryan (US, male) — news read": "en_US/ryan/high/en_US-ryan-high",
    "HFC Male (US) — neutral": "en_US/hfc_male/medium/en_US-hfc_male-medium",
    "Cori (UK, female) — polished": "en_GB/cori/high/en_GB-cori-high",
    "Jenny (UK, female) — soft": "en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium",
    "Alba (UK, female) — Scottish": "en_GB/alba/medium/en_GB-alba-medium",
    "Northern English (UK, male)": "en_GB/northern_english_male/medium/en_GB-northern_english_male-medium",
}

DEFAULT_PIPER_VOICE = "Lessac (US, female) — clearest"


def voices_dir():
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "ScratchVO"
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        ) / "scratch-vo"
    return base / "voices"


def _piper_model_path(voice_label):
    rel = PIPER_VOICES[voice_label]
    return voices_dir() / f"{Path(rel).name}.onnx"


def piper_available():
    try:
        subprocess.run(
            [sys.executable, "-m", "piper", "--help"],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def installed_piper_voices():
    installed = []
    for label in PIPER_VOICES:
        model = _piper_model_path(label)
        if model.exists() and model.with_suffix(".onnx.json").exists():
            installed.append(label)
    return installed


def download_piper_voice(voice_label):
    """Fetch one neural voice model. Downloads the model only — no script text is sent."""
    import urllib.request

    rel = PIPER_VOICES[voice_label]
    target_dir = voices_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(rel).name

    for suffix in (".onnx", ".onnx.json"):
        url = f"{PIPER_BASE_URL}/{rel}{suffix}"
        dest = target_dir / f"{stem}{suffix}"
        if dest.exists() and dest.stat().st_size > 0:
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=120) as response, open(tmp, "wb") as out:
                shutil.copyfileobj(response, out)
            os.replace(tmp, dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    return _piper_model_path(voice_label)


def engine_name():
    if installed_piper_voices() and piper_available():
        return "piper"
    if sys.platform == "darwin" and shutil.which("say"):
        return "macos_say"
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        return "espeak"
    return "none"


def engine_label():
    name = engine_name()
    if name == "piper":
        return "Piper neural voices (offline, on this computer)"
    if name == "macos_say":
        return "macOS Speech (offline, on this Mac only)"
    if name == "espeak":
        return "eSpeak NG (offline)"
    return "No offline TTS engine found"


# macOS ships joke voices alongside the real ones; they are useless for a VO track.
NOVELTY_VOICES = {
    "albert", "bad news", "bahh", "bells", "boing", "bubbles", "cellos",
    "deranged", "eddy", "flo", "good news", "grandma", "grandpa", "jester",
    "junior", "kathy", "organ", "princess", "ralph", "reed", "rocko", "sandy",
    "shelley", "superstar", "trinoids", "whisper", "wobble", "zarvox",
}

# Natural-sounding narration voices, best first.
PREFERRED_VOICES = [
    "ava", "allison", "samantha", "susan", "zoe", "evan", "nathan", "joelle",
    "tom", "alex", "serena", "stephanie", "daniel", "oliver", "kate", "fiona",
    "moira", "karen", "matilda", "victoria", "tessa", "rishi", "veena",
]


def _parse_say_voices(raw):
    voices = []
    seen = set()
    for line in raw.splitlines():
        match = re.match(r"^(\S.*?)\s+([A-Za-z]{2}[_-][A-Za-z]+)(?:\s|$)", line)
        if not match:
            continue
        voice, locale = match.group(1).strip(), match.group(2)
        if not locale.lower().startswith("en"):
            continue
        if voice.lower() in seen:
            continue
        seen.add(voice.lower())
        voices.append(voice)
    return voices


def _voice_quality(voice):
    lowered = voice.lower()
    if "premium" in lowered:
        return 0
    if "enhanced" in lowered:
        return 1
    return 2


def _base_voice_name(voice):
    """Strip trailing parentheticals like '(Premium)' or '(English (US))'."""
    name = voice.strip()
    while name.endswith(")"):
        depth = 0
        for i in range(len(name) - 1, -1, -1):
            if name[i] == ")":
                depth += 1
            elif name[i] == "(":
                depth -= 1
                if depth == 0:
                    name = name[:i].strip()
                    break
        else:
            break
    return name


def _rank_say_voices(voices):
    usable = [v for v in voices if _base_voice_name(v).lower() not in NOVELTY_VOICES]
    if not usable:
        usable = voices

    def sort_key(voice):
        base = _base_voice_name(voice).lower()
        try:
            preference = PREFERRED_VOICES.index(base)
        except ValueError:
            preference = len(PREFERRED_VOICES)
        return (_voice_quality(voice), preference, base)

    return sorted(usable, key=sort_key)


def _say_voice_label(voice):
    quality = _voice_quality(voice)
    base = _base_voice_name(voice)
    if quality == 0:
        return f"{base} — best quality"
    if quality == 1:
        return f"{base} — better quality"
    return f"{base} — basic"


def list_voices():
    name = engine_name()
    if name == "piper":
        return {label: label for label in installed_piper_voices()}
    if name == "macos_say":
        try:
            raw = subprocess.check_output(["say", "-v", "?"], text=True, stderr=subprocess.STDOUT)
        except (OSError, subprocess.CalledProcessError):
            return {"Samantha — basic": "Samantha"}
        ranked = _rank_say_voices(_parse_say_voices(raw))
        if not ranked:
            return {"Samantha — basic": "Samantha"}
        labels = {}
        for voice in ranked:
            label = _say_voice_label(voice)
            if label in labels:
                label = f"{label} ({voice})"
            labels[label] = voice
        return labels
    if name == "espeak":
        return {
            "English US": "en-us",
            "English UK": "en-gb",
            "English": "en",
        }
    return {}


def has_high_quality_voice():
    voices = list_voices()
    if engine_name() != "macos_say":
        return False
    return any(_voice_quality(v) < 2 for v in voices.values())


def _espeak_bin():
    return shutil.which("espeak-ng") or shutil.which("espeak")


def _run(cmd, **kwargs):
    subprocess.run(cmd, check=True, **kwargs)


def synthesize(text, voice, rate_pct, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wpm = rate_to_wpm(rate_pct)
    name = engine_name()

    if name == "piper":
        _synthesize_piper(text, voice, rate_pct, out_path)
        return
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


def _synthesize_piper(text, voice_label, rate_pct, out_path):
    model = _piper_model_path(voice_label)
    # Piper stretches audio by length: >1 is slower, so invert the percentage.
    length_scale = round(1.0 / (1.0 + rate_pct / 100.0), 4)
    wav_path = out_path.with_suffix(".wav")
    _run(
        [
            sys.executable,
            "-m",
            "piper",
            "-m",
            str(model),
            "-c",
            str(model.with_suffix(".onnx.json")),
            "-f",
            str(wav_path),
            "--length-scale",
            str(length_scale),
            # Sampled phoneme durations make the same script vary by tens of
            # milliseconds per run, which breaks matching a fixed picture edit.
            "--noise-w-scale",
            "0",
        ],
        input=text,
        capture_output=True,
        text=True,
    )
    if wav_path != out_path:
        if out_path.exists():
            out_path.unlink()
        os.replace(wav_path, out_path)


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
