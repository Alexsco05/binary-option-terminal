# ================================================================
# GIDEON — realtime/socket_server.py
# ----------------------------------------------------------------
# The actual WebSocket endpoint. One route: /ws?device_id=...
#
# Handles the full connection lifecycle (register on connect,
# unregister on disconnect/error) and dispatches every client→server
# message type defined in the schema doc §9: permission.response,
# voice.interrupt, task.cancel, workspace.action.
#
# Uses flask-sock — plain WebSocket, no Socket.IO protocol, works
# with the existing Flask dev server (app.run()) already in use, no
# gevent/eventlet or deployment changes required. See requirements.txt.
#
# Registered onto the app the same way api/routes.py is — a single
# register_socket_routes(app) call from server.py.
# ================================================================

import json

from flask import request
from flask_sock import Sock

from realtime.registry import register_connection, unregister_connection
from realtime.events import emit_state, DORMANT
from services.rate_limit import is_rate_limited
from storage import safe_device_id

# Handlers for each client -> server message type. Registered here so
# new message types can be added by adding a function + one line in
# _DISPATCH, without touching the connection-handling loop itself.
_DISPATCH = {}


def on_client_event(event_name):
    """Decorator: registers a handler for a client->server event type.
    Usage: @on_client_event('voice.interrupt') above a function
    taking (device_id, task_id, payload)."""
    def wrapper(fn):
        _DISPATCH[event_name] = fn
        return fn
    return wrapper


@on_client_event("permission.response")
def _handle_permission_response(device_id, task_id, payload):
    # Stubbed until the permission system (schema §6) is implemented —
    # logged so you can see it arriving correctly during testing, not
    # yet wired to anything that acts on the decision.
    print(f"[Realtime] permission.response from {device_id}: {payload}")


@on_client_event("voice.interrupt")
def _handle_voice_interrupt(device_id, task_id, payload):
    # Stubbed — barge-in already has its own mechanism via /stream
    # disconnecting mid-generation (see core/agent.py's _stream_groq
    # GeneratorExit handling). Wiring this into that same path is a
    # later phase, once voice moves onto this socket.
    print(f"[Realtime] voice.interrupt from {device_id}")


@on_client_event("task.cancel")
def _handle_task_cancel(device_id, task_id, payload):
    # Stubbed until task lifecycle tracking (schema §3) exists — there
    # is no running task object yet for this to cancel.
    print(f"[Realtime] task.cancel from {device_id} for task {task_id}")


@on_client_event("workspace.action")
def _handle_workspace_action(device_id, task_id, payload):
    # Stubbed until workspaces (schema §5/§7/§7a) are implemented.
    print(f"[Realtime] workspace.action from {device_id}: {payload}")


def register_socket_routes(app):
    sock = Sock(app)

    @sock.route("/ws")
    def ws_endpoint(ws):
        device_id = safe_device_id(
            request.args.get("device_id", "default")[:100].strip() or "default"
        )

        if is_rate_limited(device_id):
            # Same rate limiting every HTTP route already uses — a
            # WebSocket connection is still a resource, and this is
            # the same protection against a runaway/misbehaving client
            # hammering reconnects.
            ws.close(reason="rate limited")
            return

        register_connection(device_id, ws)
        print(f"[Realtime] {device_id} connected")

        # Tell the client its starting orb state immediately on
        # connect, rather than leaving it showing whatever it last
        # had (e.g. stale 'offline' from before this connection
        # existed).
        emit_state(device_id, DORMANT)

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break  # client closed the connection

                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    print(f"[Realtime] {device_id} sent invalid JSON, ignoring")
                    continue

                event_name = msg.get("event")
                task_id = msg.get("task_id")
                payload = msg.get("payload") or {}

                handler = _DISPATCH.get(event_name)
                if handler is None:
                    print(f"[Realtime] {device_id} sent unknown event '{event_name}', ignoring")
                    continue

                try:
                    handler(device_id, task_id, payload)
                except Exception as e:
                    print(f"[Realtime] handler for '{event_name}' failed: {e}")

        except Exception as e:
            print(f"[Realtime] {device_id} connection error: {e}")
        finally:
            unregister_connection(device_id, ws)
            print(f"[Realtime] {device_id} disconnected")
