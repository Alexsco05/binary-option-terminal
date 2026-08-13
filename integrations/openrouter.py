# ================================================================
# GIDEON — integrations/openrouter.py
# ----------------------------------------------------------------
# Moved from server.py with zero behavior change.
# ================================================================

from config.environment import OPENROUTER_KEYS
from integrations.client import SESSION


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
