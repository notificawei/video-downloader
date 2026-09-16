import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edge_tts

SCRIPTS_DIR = Path(__file__).resolve().parent / "data"
SCRIPTS_FILE = SCRIPTS_DIR / "scripts.json"

VOICES = {
    "Ava (US)": "en-US-AvaNeural",
    "Jenny (US)": "en-US-JennyNeural",
    "Aria (US)": "en-US-AriaNeural",
    "Emma (US)": "en-US-EmmaNeural",
    "Sonia (UK)": "en-GB-SoniaNeural",
    "Libby (UK)": "en-GB-LibbyNeural",
}

DEFAULT_RATE = -5


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


async def _synthesize_async(text, voice, rate_pct, out_path):
    rate = f"{rate_pct:+d}%"
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_path))


def synthesize(text, voice, rate_pct, out_path):
    def _run():
        asyncio.run(_synthesize_async(text, voice, rate_pct, out_path))

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_run).result()
