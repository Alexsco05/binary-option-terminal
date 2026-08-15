# ================================================================
# GIDEON — integrations/tts.py
# ----------------------------------------------------------------
# Full TTS pipeline: raw generators (Edge TTS primary, OpenAI
# fallback) plus the orchestration on top — generate_tts_base64()
# picks a generator and falls back, _clean_for_speech() strips
# markdown/action-tags and converts math notation into natural
# spoken phrasing before either generator ever sees the text.
#
# Moved from server.py with zero behavior change. Now fully self-
# contained — every dependency (convert_math_for_speech,
# extract_action_trigger) had already been modularized elsewhere.
# ================================================================

import os
import re
import base64
import asyncio
import uuid as _uuid

from config.environment import OPENAI_KEY
from integrations.client import SESSION
from core.tags import extract_action_trigger
from skills.mathematics import convert_math_for_speech

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


# ================================================================
# ORCHESTRATION — picks a generator, cleans text before either sees it
# ================================================================

def _clean_for_speech(text: str) -> str:
    """Strips markdown/action-tags and converts math notation into
    natural spoken phrasing, then truncates to a safe length.
    Reuses extract_action_trigger's balanced-brace tag stripping
    instead of a separate regex, so a JSON tool payload can't leave
    trailing debris that TTS would read out loud."""
    clean, _ = extract_action_trigger(text)
    clean = convert_math_for_speech(clean)
    clean = re.sub(r'#{1,3}\s*', '', clean)
    clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)
    clean = re.sub(r'^[-•]\s*', '', clean, flags=re.MULTILINE)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:900]


def generate_tts_base64(text: str, voice: str = "onyx") -> tuple:
    """
    Returns (audio_base64, error_message). One will be empty.
    Edge TTS is tried first since it has no billing/quota risk.
    OpenAI is only used as a fallback if Edge TTS fails for some
    reason and OPENAI_API_KEY happens to be configured and working —
    giving you a working voice pipeline today regardless of OpenAI
    account status, while still letting OpenAI act as a backup if
    you fix billing later.
    """
    clean = _clean_for_speech(text)
    if not clean:
        return "", "No speakable content after cleaning"

    audio, error = _generate_edge_tts(clean, voice)
    if audio:
        return audio, ""

    print(f"[TTS] Edge TTS failed ({error}), trying OpenAI fallback")
    audio, error2 = _generate_openai_tts(clean, voice)
    if audio:
        return audio, ""

    return "", f"Both TTS providers failed. Edge: {error} | OpenAI: {error2}"
