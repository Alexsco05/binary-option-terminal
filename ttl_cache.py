# ================================================================
# MINIMAL TTL + SIZE-LIMITED CACHE
# Zero external dependencies - safe for launch, no install risk.
# Thread-safe, O(1) average operations.
# ================================================================

import time
import threading
from collections import OrderedDict

class TTLCache:
    def __init__(self, maxsize: int = 2000, ttl: int = 3600):
        self.maxsize = maxsize
        self.ttl     = ttl
        self._data   = OrderedDict()  # key -> (value, expires_at)
        self._lock   = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return default
            value, expires_at = entry
            if time.time() > expires_at:
                del self._data[key]
                return default
            self._data.move_to_end(key)  # mark as recently used
            return value

    def set(self, key, value):
        with self._lock:
            if key in self._data:
                del self._data[key]
            self._data[key] = (value, time.time() + self.ttl)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)  # evict oldest

    def __contains__(self, key):
        return self.get(key, "__MISSING__") != "__MISSING__"

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str):
        with self._lock:
            keys = [k for k in self._data if str(k).startswith(prefix)]
            for k in keys:
                del self._data[k]

    def cleanup_expired(self):
        with self._lock:
            now = time.time()
            expired = [k for k, (_, exp) in self._data.items() if now > exp]
            for k in expired:
                del self._data[k]

    def __len__(self):
        return len(self._data)

