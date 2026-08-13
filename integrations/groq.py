# ================================================================
# GIDEON — integrations/groq.py
# ----------------------------------------------------------------
# Plain (non-streaming) Groq calls. Moved from server.py with zero
# behavior change. Streaming (_stream_groq) is NOT here — it's
# tangled with search/read/action-tag resolution and memory writes,
# core-agent territory, so it stays in server.py until the core/
# modularization step.
# ================================================================

import time
import requests

from config.environment import GROQ_KEYS
from integrations.client import SESSION


def _call_groq_raw(prompt: str):
    for key in GROQ_KEYS:
        if not key:
            continue
        try:
            r = SESSION.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "llama-3.3-70b-versatile",
                      "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 500},
                timeout=8,
            )
            d = r.json()
            if "choices" in d:
                return d["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[GroqRaw] {e}")
    return None


def _call_groq_raw_extended(prompt: str, max_tokens: int = 1200):
    """Same as _call_groq_raw, but with a higher token ceiling for
    extraction-style calls that need to return a structured list rather
    than one short reply. Kept separate so the existing fact-extraction
    call (which works fine at 500 tokens) isn't touched."""
    for key in GROQ_KEYS:
        if not key:
            continue
        try:
            r = SESSION.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "llama-3.3-70b-versatile",
                      "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": max_tokens},
                timeout=12,
            )
            d = r.json()
            if "choices" in d:
                return d["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[GroqRawExtended] {e}")
    return None


def _call_groq(msg: str, model: str, system_prompt: str, short_term: list, retries: int = 2):
    is_complex = len(msg.split()) > 8
    for key in GROQ_KEYS:
        if not key:
            continue
        for attempt in range(retries):
            try:
                messages = list(short_term)
                messages[0] = {"role": "system", "content": system_prompt}
                messages.append({"role": "user", "content": msg})
                r = SESSION.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "messages": messages,
                          "max_tokens": 1500 if is_complex else 800},
                    timeout=18,
                )
                d = r.json()
                if "choices" in d:
                    return d["choices"][0]["message"]["content"]
                err = d.get("error", {})
                print(f"[Groq {model}] failed: {err}")
                if "rate_limit" in str(err).lower():
                    break
            except requests.Timeout:
                print(f"[Groq {model}] timeout attempt {attempt}")
                if attempt < retries - 1:
                    time.sleep(0.5)
            except Exception as e:
                print(f"[Groq {model}] attempt {attempt}: {e}")
                if attempt < retries - 1:
                    time.sleep(0.5)
    return None
