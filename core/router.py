# ================================================================
# GIDEON — core/router.py
# ----------------------------------------------------------------
# Two related jobs, kept in one file since they're both "which
# route/provider handles this request":
#   1. Provider load tracking — rolling usage counts per provider,
#      used to proactively spread load before a provider hits its
#      soft cap (Phase 9).
#   2. Message routing — keyword-based classification of a user
#      message into one of MODELS' route keys (fast/coding/math/...),
#      plus mood-based tone behavior.
#
# Moved from server.py with zero behavior change.
# ================================================================

import re
import time
import threading
from collections import defaultdict

from integrations.providers import (
    _call_groq, _call_openrouter, _call_gemini,
    _call_cohere, _call_cerebras, _call_mistral,
)

from config.settings import PROVIDER_SOFT_CAPS
from core.skills import SKILL_REGISTRY


# ================================================================
# PROVIDER LOAD TRACKING (Phase 9)
# ----------------------------------------------------------------
# Every route's primary has been Groq for a while now, on purpose —
# every attempt at routing specific task types to specialized models
# (dedicated math model, dedicated coding model) broke eventually,
# deprecated or moved to paid-only. That history is real and this
# doesn't undo it: routes still don't get reassigned by task type.
#
# What this DOES add: Groq hitting its daily token cap has already
# happened once for real ("Groq's TPD limit tonight" — see the fast
# route's own comment in config/settings.py). Right now every request
# goes to Groq first regardless of how much it's already been used,
# and only spreads to other providers once Groq is already failing.
# This tracks rolling usage per provider and, when the configured
# primary is nearing its soft cap, transparently promotes the first
# fallback to take its place BEFORE the request goes out — proactive
# load spreading, not reactive failover. The existing fallback chain
# on actual failure is completely untouched.
# ================================================================
PROVIDER_USAGE        = defaultdict(list)   # provider -> [timestamps]
_PROVIDER_USAGE_GUARD = threading.Lock()


def record_provider_usage(provider: str):
    with _PROVIDER_USAGE_GUARD:
        PROVIDER_USAGE[provider].append(time.time())


def _provider_usage_count(provider: str, window_seconds: int) -> int:
    now = time.time()
    with _PROVIDER_USAGE_GUARD:
        recent = [t for t in PROVIDER_USAGE[provider] if now - t < window_seconds]
        PROVIDER_USAGE[provider] = recent  # prune while we're here
        return len(recent)


def provider_near_cap(provider: str) -> bool:
    cap = PROVIDER_SOFT_CAPS.get(provider)
    if not cap:
        return False
    return _provider_usage_count(provider, cap["window_seconds"]) >= cap["max_requests"]


def select_primary(model_cfg: dict) -> dict:
    """
    Returns the provider/model to actually use as primary for this
    call. Normally that's just model_cfg["primary"] — but if that
    provider is near its soft cap, the first fallback is promoted in
    its place instead, so load spreads across providers proactively
    instead of hammering one until it fails. Falls back to the
    original primary if every fallback is also near cap, since trying
    the real primary anyway beats refusing the request outright.
    """
    primary = model_cfg["primary"]
    if provider_near_cap(primary["provider"]):
        for fb in (model_cfg.get("fallbacks") or []):
            if not provider_near_cap(fb["provider"]):
                print(f"[Load] {primary['provider']} near soft cap, using {fb['provider']} instead")
                return fb
    return primary


# ================================================================
# MODEL ROUTER — word-boundary matching to cut false positives
# (e.g. "explain Morse code" no longer routes to coding)
# ================================================================
def _word_match(ml: str, keywords: list) -> bool:
    for k in keywords:
        if " " in k:
            if k in ml:
                return True
        else:
            if re.search(rf'\b{re.escape(k)}\b', ml):
                return True
    return False


def route_model(msg: str, personality: dict) -> str:
    """
    Classifies a message into a skill name by checking each registered
    skill's keywords, in registry order, first match wins. Used to
    read from a hardcoded rules list duplicated across this function;
    now reads from core/skills.py's SKILL_REGISTRY, so adding a new
    skill's keywords means registering it there — this function
    doesn't change.
    """
    ml   = msg.lower()
    mood = personality.get("mood", "neutral")

    # guard: explicitly conversational/explanatory framing about a topic
    # should not be treated as an action/category trigger
    explain_framing = any(p in ml for p in [
        "explain", "what is", "what does", "tell me about",
        "history of", "meaning of", "define"
    ])

    # special case: "code" as a standalone word with explain framing
    # (e.g. "explain Morse code") should not hit the coding skill
    skip_coding = "code" in ml.split() and explain_framing and "morse" in ml

    for skill in SKILL_REGISTRY.values():
        if skill.name == "coding" and skip_coding:
            continue
        if not skill.keywords:
            continue  # "fast" has no keywords — it's the final fallback below
        if _word_match(ml, skill.keywords):
            return skill.name

    if mood in ["sad", "depressed", "lonely", "anxious"]:
        return "empathetic"
    if mood in ["happy", "excited", "playful"]:
        return "creative"
    return "fast"


# ================================================================
# MOOD BEHAVIOR + DEPTH (v11 prompt system)
# ================================================================
MOOD_BEHAVIOR = {
    "neutral":    "Standard tone. Clear and direct.",
    "happy":      "Match the positive energy. Be warm.",
    "excited":    "Match the energy. Keep it engaging.",
    "playful":    "Light tone is fine. Still be useful.",
    "sad":        "Shorter responses. Gentle, supportive tone. No forced positivity.",
    "depressed":  "Shorter responses. Gentle, supportive tone. No forced positivity.",
    "anxious":    "Calm, steady tone. Avoid overwhelming detail. Reassure without dismissing.",
    "lonely":     "Warm and present. Avoid being clinical.",
    "stressed":   "Direct and concise. Reduce cognitive load. Prioritize the one next step.",
    "frustrated": "Shorter, more direct responses. Skip pleasantries. Solve the problem.",
    "angry":      "Calm, measured tone. Do not escalate. Stay factual.",
    "curious":    "More explanation welcome. Can go deeper.",
    "tired":      "Keep it brief. Don't ask follow-up questions unless necessary.",
}


def get_mood_behavior(mood: str) -> str:
    return MOOD_BEHAVIOR.get(mood, MOOD_BEHAVIOR["neutral"])


# ================================================================
# PROVIDER DISPATCHER
# ----------------------------------------------------------------
# Single entry point every caller uses to actually reach a provider.
# All providers receive short_term memory — fixes the inconsistency
# where only Groq had context.
# ================================================================

def call_provider(msg, provider, model, system_prompt, short_term, device_id):
    record_provider_usage(provider)
    if provider == "groq":
        return _call_groq(msg, model, system_prompt, short_term)
    if provider == "openrouter":
        return _call_openrouter(msg, model, system_prompt, short_term)
    if provider == "gemini":
        return _call_gemini(msg, model, system_prompt, short_term)
    if provider == "cohere":
        return _call_cohere(msg, system_prompt, short_term)
    if provider == "cerebras":
        return _call_cerebras(msg, model, system_prompt, short_term)
    if provider == "mistral":
        return _call_mistral(msg, system_prompt, short_term)
    return None
