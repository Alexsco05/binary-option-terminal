# ================================================================
# GIDEON — integrations/providers.py
# ----------------------------------------------------------------
# All plain (non-streaming) AI provider calls in one file: Groq,
# OpenRouter, Gemini, Cohere, Cerebras, Mistral. Moved from
# server.py with zero behavior change.
#
# Kept as one file rather than split per-provider — these are small,
# always edited together when tuning fallback chains in
# config/settings.py, and one file is simpler to manage from a phone
# workflow (Termux/GitHub app) than six.
#
# _stream_groq is NOT here — it's tangled with search/read/action-tag
# resolution and memory writes, core-agent territory, so it stays in
# server.py until the core/ modularization step.
# ================================================================

import time
import requests

from config.environment import (
    GROQ_KEYS, OPENROUTER_KEYS, GEMINI_KEY,
    COHERE_KEY, CEREBRAS_KEY, MISTRAL_KEYS,
)
from integrations.client import SESSION


# ── GROQ ──────────────────────────────────────────────────────────

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


# ── OPENROUTER ────────────────────────────────────────────────────

def _call_openrouter(msg: str, model: str, system_prompt: str, short_term: list):
    if not any(OPENROUTER_KEYS):
        print("[OpenRouter] No OPENROUTER_KEY_1/2 set, skipping")
        return None
    for key in OPENROUTER_KEYS:
        if not key:
            continue
        try:
            messages = list(short_term)
            messages[0] = {"role": "system", "content": system_prompt}
            messages.append({"role": "user", "content": msg})
            # OpenRouter's free-model catalog rotates fast enough that
            # a single hardcoded model ID is a real liability — entire
            # free tiers (Meta Llama, Qwen, DeepSeek) have been pulled
            # or moved to paid-only within weeks. Sending a "models"
            # array instead of one "model" string lets OpenRouter try
            # each candidate in order itself, so the configured model
            # going stale doesn't take the whole request down with it.
            # Second and third entries are meant as broad safety nets,
            # not tied to route quality, they'll also drift over time,
            # this reduces how often that matters rather than solving
            # it permanently.
            candidates = [model]
            for extra in ("nvidia/nemotron-3-ultra-550b-a55b:free",
                         "openai/gpt-oss-120b:free"):
                if extra not in candidates:
                    candidates.append(extra)
            r = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}",
                         "HTTP-Referer": "https://gideon-app.com",
                         "X-Title": "Gideon AI"},
                json={"models": candidates, "messages": messages, "max_tokens": 1500},
                timeout=18,
            )
            d = r.json()
            if "choices" in d:
                used = d.get("model", model)
                if used != model:
                    print(f"[OpenRouter] {model} unavailable, used {used} instead")
                return d["choices"][0]["message"]["content"]
            print(f"[OpenRouter {model}] No choices in response: {d}")
        except Exception as e:
            print(f"[OpenRouter {model}] {e}")
    return None


# ── GEMINI ────────────────────────────────────────────────────────

def _call_gemini(msg: str, model: str, system_prompt: str, short_term: list):
    if not GEMINI_KEY:
        return None
    try:
        # fold short_term into the context Gemini receives, since it has
        # no native multi-turn role array the same way OpenAI-style APIs do
        history_text = ""
        for m in short_term[1:]:
            role = "User" if m["role"] == "user" else "Gideon"
            history_text += f"{role}: {m['content']}\n"

        full_prompt = f"{system_prompt}\n\n{history_text}User: {msg}"
        r = SESSION.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={GEMINI_KEY}",
            json={"contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
                  "generationConfig": {"maxOutputTokens": 1500}},
            timeout=18,
        )
        cands = r.json().get("candidates", [])
        if cands:
            return cands[0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[Gemini] {e}")
    return None


# ── COHERE ────────────────────────────────────────────────────────
# Replaced by Cerebras throughout the fallback chains in
# config/settings.py, but kept here in case it's ever wired back in.

def _call_cohere(msg: str, system_prompt: str, short_term: list):
    if not COHERE_KEY:
        return None
    try:
        chat_history = []
        for m in short_term[1:]:
            chat_history.append({
                "role": "USER" if m["role"] == "user" else "CHATBOT",
                "message": m["content"],
            })
        r = SESSION.post(
            "https://api.cohere.ai/v1/chat",
            headers={"Authorization": f"Bearer {COHERE_KEY}"},
            json={"message": msg, "preamble": system_prompt,
                  "chat_history": chat_history, "max_tokens": 1500},
            timeout=18,
        )
        return r.json().get("text", None)
    except Exception as e:
        print(f"[Cohere] {e}")
    return None


# ── CEREBRAS ──────────────────────────────────────────────────────

def _call_cerebras(msg: str, model: str, system_prompt: str, short_term: list):
    """Cerebras replaces Cohere in the fallback chains below — same
    OpenAI-compatible chat completions shape as Mistral/OpenRouter,
    just a different base URL, and known for very fast inference on
    Llama models, which matters for a fallback path (the whole point
    is not adding a second round of noticeable latency on top of the
    primary call that already failed)."""
    if not CEREBRAS_KEY:
        print("[Cerebras] CEREBRAS_KEY not set, skipping")
        return None
    try:
        messages = list(short_term)
        messages[0] = {"role": "system", "content": system_prompt}
        messages.append({"role": "user", "content": msg})
        r = SESSION.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {CEREBRAS_KEY}"},
            json={"model": model, "messages": messages,
                  "max_tokens": 1500, "temperature": 0.7},
            timeout=18,
        )
        d = r.json()
        if "choices" in d:
            return d["choices"][0]["message"]["content"]
        print(f"[Cerebras {model}] No choices in response: {d}")
    except Exception as e:
        print(f"[Cerebras] {e}")
    return None


# ── MISTRAL ───────────────────────────────────────────────────────

def _call_mistral(msg: str, system_prompt: str, short_term: list):
    for key in MISTRAL_KEYS:
        if not key:
            continue
        try:
            messages = list(short_term)
            messages[0] = {"role": "system", "content": system_prompt}
            messages.append({"role": "user", "content": msg})
            r = SESSION.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "mistral-small-latest", "messages": messages,
                      "max_tokens": 1500, "temperature": 0.7},
                timeout=18,
            )
            d = r.json()
            if "choices" in d:
                return d["choices"][0]["message"]["content"]
            print(f"[Mistral] No choices in response: {d}")
        except Exception as e:
            print(f"[Mistral] {e}")
    return None
