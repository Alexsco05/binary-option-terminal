# ================================================================
# GIDEON — memory/conversation.py
# ----------------------------------------------------------------
# Short-term (per-request-session) memory: the response cache, each
# device's in-flight conversation history, and pending confirmations
# ("should I open WhatsApp?"). Moved from server.py with zero
# behavior change.
#
# EXECUTOR also lives here — it's the shared background thread pool
# used for fire-and-forget memory writes (update_long_term,
# extract_facts) so a slow write never blocks the reply. Both
# server.py and memory/personality.py need it; defining it here
# (rather than in server.py) avoids a circular import, same reasoning
# as integrations/client.py's SESSION.
# ================================================================

from concurrent.futures import ThreadPoolExecutor

from config.settings import MEMORY_LIMIT, CACHE_MAXSIZE, CACHE_TTL_SECONDS, EXECUTOR_MAX_WORKERS
from ttl_cache import TTLCache

EXECUTOR = ThreadPoolExecutor(max_workers=EXECUTOR_MAX_WORKERS)

CACHE                 = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)
USER_SHORT_TERM       = {}
PENDING_CONFIRMATIONS = {}


def get_short_term(device_id: str):
    if device_id not in USER_SHORT_TERM:
        USER_SHORT_TERM[device_id] = [{"role": "system", "content": ""}]
    return USER_SHORT_TERM[device_id]


def trim_short_term(st: list):
    """
    Trims by COMPLETE exchanges (user+assistant pairs), not single
    messages, so the conversation never ends up misaligned.
    Index 0 is always the system message.
    """
    while len(st) > MEMORY_LIMIT:
        del st[1:3]
