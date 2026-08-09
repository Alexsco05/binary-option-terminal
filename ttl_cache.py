# ================================================================
# MINIMAL TTL + SIZE-LIMITED CACHE
#
# Zero external dependencies.
# Thread-safe.
# O(1) average lookup and insertion.
# Automatically expires entries after the configured TTL.
# ================================================================

import time
import threading
from collections import OrderedDict


class TTLCache:
    def __init__(self, maxsize: int = 2000, ttl: int = 3600):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data = OrderedDict()  # key -> (value, expires_at)
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            entry = self._data.get(key)

            if entry is None:
                return default

            value, expires_at = entry

            if time.time() > expires_at:
                del self._data[key]
                return default

            # Mark as recently used
            self._data.move_to_end(key)

            return value

    def set(self, key, value):
        with self._lock:
            if key in self._data:
                del self._data[key]

            self._data[key] = (
                value,
                time.time() + self.ttl
            )

            self._data.move_to_end(key)

            # Remove oldest entries when cache exceeds max size
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def contains(self, key):
        return self.get(key, "MISSING") != "MISSING"

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str):
        with self._lock:
            keys = [
                k for k in self._data
                if str(k).startswith(prefix)
            ]

            for k in keys:
                del self._data[k]

    def cleanup_expired(self):
        with self._lock:
            now = time.time()

            expired = [
                k
                for k, (_, expires_at) in self._data.items()
                if now > expires_at
            ]

            for k in expired:
                del self._data[k]

    def len(self):
        with self._lock:
            return len(self._data)


# ================================================================
# CACHE INSTANCE
# ================================================================

CACHE = TTLCache(
    maxsize=2000,
    ttl=1800
)
