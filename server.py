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
#
# Started as one ~3,700-line file (July 2026). Each module above was
# extracted one working, tested slice at a time — see the header
# comment in each file for what moved and why.
# ================================================================

from flask import Flask

from config.environment import PORT, BOT_NAME
from api.routes import register_routes

app = Flask(__name__)
register_routes(app)

if __name__ == "__main__":
    print(f"{BOT_NAME} v11.0 online")
    app.run(host="0.0.0.0", port=PORT)
