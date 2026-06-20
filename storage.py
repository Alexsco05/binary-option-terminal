# ================================================================
# STORAGE LAYER - swappable data access module
# v1: file-backed JSON with file locking to prevent corruption
# v1.1+: swap the internals of these functions for PostgreSQL/Supabase
#        without touching any code that calls them.
# ================================================================

import json
import os
import threading
import re

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()

def _get_lock(path: str) -> threading.Lock:
    """One lock per file path, created on first use."""
    with _LOCKS_GUARD:
        if path not in _LOCKS:
            _LOCKS[path] = threading.Lock()
        return _LOCKS[path]

def safe_device_id(device_id: str) -> str:
    """Sanitize device_id for safe filesystem use."""
    cleaned = re.sub(r"[^a-zA-Z0-9\-_]", "", str(device_id))[:64]
    return cleaned or "default"

def _path_for(kind: str, device_id: str) -> str:
    safe = safe_device_id(device_id)
    return f"{kind}_{safe}.json"

def read_json(kind: str, device_id: str, default):
    path = _path_for(kind, device_id)
    lock = _get_lock(path)
    with lock:
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return default

def write_json(kind: str, device_id: str, data) -> bool:
    path = _path_for(kind, device_id)
    lock = _get_lock(path)
    tmp_path = f"{path}.tmp"
    with lock:
        try:
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, path)  # atomic on POSIX, prevents corruption
            return True
        except Exception as e:
            print(f"[Storage] write_json failed for {path}: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return False

def delete_json(kind: str, device_id: str) -> bool:
    path = _path_for(kind, device_id)
    lock = _get_lock(path)
    with lock:
        try:
            if os.path.exists(path):
                os.remove(path)
            return True
        except Exception as e:
            print(f"[Storage] delete_json failed for {path}: {e}")
            return False

