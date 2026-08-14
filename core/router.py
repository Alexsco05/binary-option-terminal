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

from config.settings import PROVIDER_SOFT_CAPS


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
    ml   = msg.lower()
    mood = personality.get("mood", "neutral")

    # guard: explicitly conversational/explanatory framing about a topic
    # should not be treated as an action/category trigger
    explain_framing = any(p in ml for p in [
        "explain", "what is", "what does", "tell me about",
        "history of", "meaning of", "define"
    ])

    rules = [
        (["code", "program", "debug", "kotlin", "python", "java",
          "function", "class", "compile", "gradle", "syntax",
          "algorithm", "api", "json", "xml", "crash", "exception"],
         "coding", False),
        (["calculate", "solve", "equation", "integral", "derivative",
          "algebra", "geometry", "trigonometry", "statistics",
          "probability", "matrix", "calculus", "formula"],
         "math", False),
        (["weather", "temperature", "rain", "forecast", "hot outside",
          "cold outside", "sunny", "cloudy"], "weather", False),
        (["latest news", "news today", "current events",
          "what happened today", "headlines"], "news", False),
        (["joke", "funny", "humor", "laugh", "roast", "prank", "silly",
          "entertain", "riddle"], "creative", False),
        (["sad", "depressed", "anxious", "lonely", "stressed", "worried",
          "scared", "angry", "upset", "hurt", "heartbreak", "crying",
          "i feel", "i am tired", "nobody cares", "give up", "hopeless"],
         "empathetic", False),
        (["shut up", "stupid", "idiot", "useless", "hate you", "terrible",
          "worst", "rubbish", "nonsense", "dumb", "you are trash",
          "garbage", "pathetic"], "firm", False),
        # ── these five were previously unreachable — SPECIALIST_BLOCKS
        # defines "writing", "planning", "teaching", "research", and
        # "business" specialists in full, but route_model() never had
        # a rule that could actually select any of them, so every
        # request that should have hit one fell into the generic
        # "complex" catch-all instead. Placed before "complex" so
        # first-match-wins routes these correctly now.
        (["write a", "write me", "write an", "blog post", "short story",
          "cover letter", "proofread", "rewrite this", "paraphrase",
          "draft an email", "draft a message", "improve my writing",
          "edit my writing", "summarize", "translate"], "writing", False),
        (["plan my", "make a plan", "roadmap for", "schedule my",
          "prioritize my", "project plan", "action plan",
          "next steps for", "organize my", "timeline for",
          "help me plan"], "planning", False),
        (["teach me", "eli5", "explain like i'm five", "tutor me",
          "quiz me", "walk me through", "help me learn",
          "help me understand"], "teaching", False),
        (["research about", "fact check", "is it true that",
          "find sources on", "investigate", "look into",
          "compare sources", "cite sources"], "research", False),
        (["business plan", "startup idea", "revenue model",
          "pricing strategy", "market analysis", "competitor analysis",
          "pitch deck", "monetize", "profit margin", "business idea",
          "go to market", "business strategy"], "business", False),
        (["how can i", "how do i", "how should i", "what should i do",
          "advice", "help me with", "i'm struggling", "i have a problem",
          "colleague", "coworker", "boss", "manager", "workplace",
          "relationship", "friend", "family", "disrespect", "conflict",
          "argument", "deal with", "handle", "improve", "become better",
          "learn how to", "what do you think", "your opinion", "recommend",
          "explain", "analyze", "compare", "why", "how does",
          "difference between", "pros and cons", "essay", "story",
          "philosophy", "meaning of", "history of"], "complex", False),
    ]

    # special case: "code" as a standalone word with explain framing
    # (e.g. "explain Morse code") should not hit coding route
    if "code" in ml.split() and explain_framing and "morse" in ml:
        rules = [r for r in rules if r[1] != "coding"]

    for keywords, route, _ in rules:
        if _word_match(ml, keywords):
            return route

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
