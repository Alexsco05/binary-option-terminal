# ================================================================
# GIDEON — config/environment.py
# ----------------------------------------------------------------
# Raw environment-variable loading only. No logic, no defaults beyond
# what server.py already used, nothing derived. If it isn't read from
# os.getenv() somewhere in the original server.py's CONFIG block, it
# does not belong in this file — anything computed FROM these values
# (the MODELS registry, PROVIDER_SOFT_CAPS, rate limit numbers) lives
# in config/settings.py instead.
#
# Moved from server.py v11.0 with zero behavior change. Same variable
# names, same env var names, same fallback strings.
# ================================================================

import os

# ── Identity ────────────────────────────────────────────────────
BOT_NAME = "Gideon"

# ── AI provider keys ────────────────────────────────────────────
GROQ_KEYS = [
    os.getenv("GROQ_KEY_1", ""),
    os.getenv("GROQ_KEY_2", ""),
]
OPENROUTER_KEYS = [
    os.getenv("OPENROUTER_KEY_1", ""),
    os.getenv("OPENROUTER_KEY_2", ""),
]
MISTRAL_KEYS = [
    os.getenv("MISTRAL_KEY_1", ""),
    os.getenv("MISTRAL_KEY_2", ""),
]
GEMINI_KEY   = os.getenv("GEMINI_KEY", "")
COHERE_KEY   = os.getenv("COHERE_KEY", "")
CEREBRAS_KEY = os.getenv("CEREBRAS_KEY", "")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "")

# ── External service keys ───────────────────────────────────────
WEATHER_KEY       = os.getenv("WEATHER_KEY", "")
NEWS_KEY          = os.getenv("NEWS_KEY", "")
BRAVE_SEARCH_KEY  = os.getenv("BRAVE_SEARCH_KEY", "")  # kept for backwards compat
SERPER_KEY        = os.getenv("SERPER_KEY", "")
FIRECRAWL_KEY     = os.getenv("FIRECRAWL_KEY", "")

# ── Security ─────────────────────────────────────────────────────
DEVICE_SECRET = os.getenv("DEVICE_SECRET", "gideon-dev-secret-change-in-railway")

# ── Deployment ───────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 5000))
