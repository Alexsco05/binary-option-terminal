# ================================================================
# GIDEON BACKEND - Version 11.0
# Creator: Alexsco (Adegolu Alex) @alexsco_official
# ----------------------------------------------------------------
# Modularization complete. This file is now just the entry point:
# create the Flask app, register every route from api/routes.py,
# run it. Everything else — config, security services, AI provider
# integrations, memory, agent core, skills, device commands — lives
# in its own module:
#
#   config/        environment variables, model registry, settings
#   services/      device tokens, rate limiting
#   integrations/  every AI provider, TTS, web search, weather, news
#   memory/        short-term conversation, personality, history,
#                  fact extraction, knowledge graph
#   core/          routing, permissions, tag parsing, intent
#                  detection, system prompts, the agent loop itself
#   skills/        math notation, research mode
#   device/        Android offline command detection
#   api/           every Flask route
#   realtime/      WebSocket layer (event schema v1) — orb state,
#                  task lifecycle, workspaces, permissions, voice
#
# Started as one ~3,700-line file (July 2026). Each module above was
# extracted one working, tested slice at a time — see the header
# comment in each file for what moved and why.
# ================================================================

from flask import Flask

from config.environment import PORT, BOT_NAME
from api.routes import register_routes
from realtime.socket_server import register_socket_routes

app = Flask(__name__)
register_routes(app)
register_socket_routes(app)

if __name__ == "__main__":
    print(f"{BOT_NAME} v11.0 online")
    # threaded=True is required now — a WebSocket connection is
    # long-lived and would otherwise block Flask's single-threaded dev
    # server from handling any other request (HTTP or a second
    # WebSocket) for as long as it stays open.
    app.run(host="0.0.0.0", port=PORT, threaded=True)
