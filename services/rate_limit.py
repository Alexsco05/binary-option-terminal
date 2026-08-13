# ================================================================
# GIDEON — services/rate_limit.py
# ----------------------------------------------------------------
# Per-device rate limiting with expiry-based pruning (fixes the
# unbounded-memory-growth bug the original in-line version had).
# Moved from server.py with zero behavior change.
# ================================================================

import time
from collections import defaultdict

from config.settings import RATE_LIMIT_PER_MINUTE, RATE_LIMIT_PER_HOUR

REQUEST_COUNTS = defaultdict(list)
_last_global_prune = time.time()


def is_rate_limited(device_id: str) -> bool:
    global _last_global_prune
    now = time.time()

    # lazy global prune every ~5 minutes so the dict never grows forever
    if now - _last_global_prune > 300:
        stale = [
            k for k, v in REQUEST_COUNTS.items()
            if not v or now - v[-1] > 3600
        ]
        for k in stale:
            del REQUEST_COUNTS[k]
        _last_global_prune = now

    counts = [t for t in REQUEST_COUNTS[device_id] if t > now - 3600]
    REQUEST_COUNTS[device_id] = counts
    if sum(1 for t in counts if t > now - 60) >= RATE_LIMIT_PER_MINUTE:
        return True
    if len(counts) >= RATE_LIMIT_PER_HOUR:
        return True
    REQUEST_COUNTS[device_id].append(now)
    return False
