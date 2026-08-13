# ================================================================
# GIDEON — integrations/tts.py
# ----------------------------------------------------------------
# Raw text-to-speech generation: Edge TTS (free, primary) and OpenAI
# TTS (paid, fallback). Moved from server.py with zero behavior
# change.
#
# generate_tts_base64() and _clean_for_speech() are NOT here — they
# depend on convert_math_for_speech() and extract_action_trigger(),
# which are core/skill logic that hasn't been modularized yet. Moving
# them now would either duplicate that logic or create a circular
# import. They stay in server.py and call the two generators below.
# ================================================================

import os
import base64
import asyncio
import uuid as _uuid

from config.environment import OPENAI_KEY
from integrations.client import SESSION

VALID_OPENAI_VOICES = {
    "alloy", "ash", "ballad", "coral", "echo",
    "fable", "onyx", "nova", "sage", "shimmer",
}

# Edge TTS voice names — pick whichever sounds best for Gideon.
# Full list: run `edge-tts --list-voices` once locally if you want options.
EDGE_VOICE_MAP = {
    "onyx":    "en-US-GuyNeural",      # closest match: calm male voice
    "echo":    "en-US-ChristopherNeural",
    "alloy":   "en-US-EricNeural",
    "fable":   "en-GB-RyanNeural",
    "nova":    "en-US-AriaNeural",     # female option
    "shimmer": "en-US-JennyNeural",    # female option
    "default": "en-US-GuyNeural",
}


def _generate_edge_tts(text: str, voice_key: str) -> tuple:
    """Returns (audio_base64, error_message). Free, no API key, no quota.
    Each call uses a unique temp file so concurrent requests from
    different users never collide or overwrite each other."""
    try:
        import edge_tts
    except ImportError:
        return "", "edge-tts package not installed on server"

    edge_voice = EDGE_VOICE_MAP.get(voice_key, EDGE_VOICE_MAP["default"])
    temp_path  = f"/tmp/gideon_tts_{_uuid.uuid4().hex}.mp3"

    try:
        async def _run():
            communicate = edge_tts.Communicate(text, edge_voice)
            await communicate.save(temp_path)

        # safe to call from a plain Flask request handler — creates
        # its own event loop rather than assuming one already exists
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_run())
        finally:
            loop.close()

        with open(temp_path, "rb") as f:
            audio_bytes = f.read()

        if not audio_bytes:
            return "", "Edge TTS produced an empty file"

        return base64.b64encode(audio_bytes).decode("utf-8"), ""
    except Exception as e:
        print(f"[TTS][Edge] exception: {e}")
        return "", f"Edge TTS error: {e}"
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def _generate_openai_tts(text: str, voice: str) -> tuple:
    """Returns (audio_base64, error_message). Used only as an optional
    fallback if OPENAI_API_KEY is set and billing is active."""
    if not OPENAI_KEY:
        return "", "OPENAI_API_KEY not configured"

    if voice not in VALID_OPENAI_VOICES:
        voice = "onyx"

    try:
        r = SESSION.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={
                "model": "tts-1", "voice": voice, "input": text,
                "response_format": "mp3", "speed": 1.0,
            },
            timeout=20,
        )
        print(f"[TTS][OpenAI] response status: {r.status_code}")
        if r.status_code == 200:
            return base64.b64encode(r.content).decode("utf-8"), ""
        else:
            body_preview = r.text[:300]
            print(f"[TTS][OpenAI] error body: {body_preview}")
            return "", f"OpenAI TTS returned {r.status_code}: {body_preview}"
    except Exception as e:
        print(f"[TTS][OpenAI] exception: {e}")
        return "", str(e)
