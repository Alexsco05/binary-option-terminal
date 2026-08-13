# ================================================================
# GIDEON — config/settings.py
# ----------------------------------------------------------------
# Static and derived configuration: nothing here reads an env var
# directly (that's environment.py's job) — this is data that was
# hardcoded as module-level constants in server.py v11.0, moved
# verbatim. MODELS, PROVIDER_SOFT_CAPS, rate limits, cache sizing,
# memory window size.
#
# Import from config.environment where a value is genuinely a secret
# or per-deployment setting; everything below is the same regardless
# of which Railway account this runs on.
# ================================================================

# ── Rate limiting ────────────────────────────────────────────────
RATE_LIMIT_PER_MINUTE = 20
RATE_LIMIT_PER_HOUR   = 200

# ── Short-term memory window ─────────────────────────────────────
# Number of messages (not exchanges) kept in USER_SHORT_TERM before
# trim_short_term() starts dropping the oldest complete exchange.
MEMORY_LIMIT = 20

# ── Response cache ───────────────────────────────────────────────
CACHE_MAXSIZE = 2000
CACHE_TTL_SECONDS = 1800  # 30 minutes

# ── Background executor ──────────────────────────────────────────
EXECUTOR_MAX_WORKERS = 8

# ================================================================
# PROVIDER SOFT CAPS (Phase 9 load spreading)
# ----------------------------------------------------------------
# Deliberately conservative, meant to be tuned against real free-tier
# limits per provider. A SOFT cap: once a provider crosses it within
# the rolling window it's deprioritized (tried later), not blocked
# outright — a traffic burst shouldn't lock a healthy provider out
# entirely. See core/router.py for the logic that reads these.
# ================================================================
PROVIDER_SOFT_CAPS = {
    "groq":       {"window_seconds": 86400, "max_requests": 800},
    "cerebras":   {"window_seconds": 86400, "max_requests": 400},
    "openrouter": {"window_seconds": 86400, "max_requests": 300},
    "mistral":    {"window_seconds": 86400, "max_requests": 300},
    "gemini":     {"window_seconds": 86400, "max_requests": 300},
}

# ================================================================
# MODEL REGISTRY
# ----------------------------------------------------------------
# llama-3.3-70b-versatile is the primary workhorse across every route —
# higher free-tier TPM limit than openai/gpt-oss-20b (which caps at
# 8k TPM and also interprets [SEARCH:...] tags as native tool calls,
# breaking the tag-based search system). 70b handles all route types
# well enough that per-route dedicated models have repeatedly gone
# stale or moved to paid-only (see coding/math notes below) — Groq
# primary everywhere, with a diversified multi-provider fallback list,
# has proven more durable than routing by task type.
#
# "fallbacks" is a LIST, tried in order, not a single dict. Diversified
# across PROVIDERS, not just models — a single provider hitting its own
# cap (Groq's TPD limit has happened for real) shouldn't take an entire
# chain down with it.
# ================================================================
MODELS = {
    "fast": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallbacks": [
            {"provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct:free"},
            {"provider": "cerebras",   "model": "gpt-oss-120b"},
            {"provider": "mistral",    "model": "mistral-small-latest"},
        ],
    },
    "complex": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        # gemini-1.5-flash was fully shut down by Google — was silently
        # 404ing on every fallback. gemini-3.5-flash is current GA with
        # no shutdown date announced as of this writing, but Google's
        # retirement cadence is fast; check
        # https://ai.google.dev/gemini-api/docs/deprecations periodically.
        "fallbacks": [
            {"provider": "gemini",     "model": "gemini-3.5-flash"},
            {"provider": "cerebras",   "model": "gpt-oss-120b"},
            {"provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct:free"},
        ],
    },
    "creative": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallbacks": [
            {"provider": "mistral",    "model": "mistral-small-latest"},
            {"provider": "openrouter", "model": "mistralai/mistral-7b-instruct:free"},
            {"provider": "gemini",     "model": "gemini-3.5-flash"},
        ],
    },
    "empathetic": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallbacks": [
            {"provider": "cerebras",   "model": "gpt-oss-120b"},
            {"provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct:free"},
            {"provider": "gemini",     "model": "gemini-3.5-flash"},
        ],
    },
    "firm": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallbacks": [
            {"provider": "openrouter", "model": "mistralai/mistral-7b-instruct:free"},
            {"provider": "mistral",    "model": "mistral-small-latest"},
            {"provider": "gemini",     "model": "gemini-3.5-flash"},
        ],
    },
    "math": {
        # was openrouter primary with a dedicated free math model —
        # unverifiable given how fast that catalog rotates, and math
        # was failing outright whenever it went stale. Groq's general
        # model handles math well enough to be the safer primary.
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallbacks": [
            {"provider": "openrouter", "model": "qwen/qwen3-coder:free"},
            {"provider": "cerebras",   "model": "gpt-oss-120b"},
            {"provider": "mistral",    "model": "mistral-small-latest"},
        ],
    },
    "coding": {
        # was openrouter primary with deepseek/deepseek-coder:free —
        # confirmed permanently moved to paid-only, not a temporary
        # outage. Same reasoning as math: Groq primary, OpenRouter (now
        # with its own internal multi-model fallback) demoted to a
        # fallback slot instead of gating the whole route.
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallbacks": [
            {"provider": "openrouter", "model": "qwen/qwen3-coder:free"},
            {"provider": "cerebras",   "model": "gpt-oss-120b"},
            {"provider": "mistral",    "model": "mistral-small-latest"},
        ],
    },
    "weather": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallbacks": [
            {"provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct:free"},
            {"provider": "mistral",    "model": "mistral-small-latest"},
            {"provider": "gemini",     "model": "gemini-3.5-flash"},
        ],
    },
    "news": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallbacks": [
            {"provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct:free"},
            {"provider": "mistral",    "model": "mistral-small-latest"},
            {"provider": "gemini",     "model": "gemini-3.5-flash"},
        ],
    },
}
