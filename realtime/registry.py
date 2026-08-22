# ================================================================
# GIDEON — realtime/registry.py
# ----------------------------------------------------------------
# Tracks which device_id currently has a live WebSocket connection,
# and the connection object itself, so backend code anywhere else
# (core/agent.py, integrations/, etc.) can push an event to a
# specific device without needing to know anything about sockets.
#
# One connection per device_id — a second connection from the same
# device_id replaces the first (matches "one Android app instance
# per device" reality; an old dangling connection from a killed app
# shouldn't keep receiving events meant for the new one).
# ================================================================

import threading

_CONNECTIONS = {}   # device_id -> websocket connection object
_GUARD = threading.Lock()


def register_connection(device_id: str, ws) -> None:
    with _GUARD:
        _CONNECTIONS[device_id] = ws


def unregister_connection(device_id: str, ws) -> None:
    """Only removes the entry if it's still THIS connection — avoids a
    race where an old connection's cleanup accidentally removes a
    newer connection that already replaced it for the same device_id."""
    with _GUARD:
        if _CONNECTIONS.get(device_id) is ws:
            del _CONNECTIONS[device_id]


def get_connection(device_id: str):
    with _GUARD:
        return _CONNECTIONS.get(device_id)


def is_connected(device_id: str) -> bool:
    with _GUARD:
        return device_id in _CONNECTIONS


def connected_device_count() -> int:
    with _GUARD:
        return len(_CONNECTIONS)
