# ================================================================
# GIDEON — integrations/client.py
# ----------------------------------------------------------------
# Shared HTTP session, reused across every provider integration to
# cut connection-setup latency. Moved from server.py with zero
# behavior change — same object, same headers, just relocated so
# integrations/*.py can import it without importing server.py
# (which would create a circular import: server imports
# integrations, integrations imports server).
# ================================================================

import requests

SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})
