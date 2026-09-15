# ================================================================
# GIDEON — integrations/client.py
# ----------------------------------------------------------------
# Shared HTTP session, reused across every provider integration to
# cut connection-setup latency. Moved from server.py with zero
# behavior change — same object, same headers, just relocated so
# integrations/*.py can import it without importing server.py
# (which would create a circular import: server imports
# integrations, integrations imports server).
#
# post_with_retry() (roadmap §29, Error Recovery) — added on top of
# the original SESSION object, not a replacement for it. Before this,
# three different files (integrations/providers.py, core/
# tool_router.py, integrations/tts.py) each hand-rolled their own
# "if this key fails, try the next one" loop with no retry of a
# single key on a transient failure — one network blip and a
# perfectly good key got skipped outright. tenacity replaces that
# hand-rolled bit with one well-tested implementation: retry the SAME
# request up to 2 extra times with exponential backoff + jitter, but
# ONLY for failures actually worth retrying (timeouts, connection
# errors, 5xx) — never for 4xx, which won't be fixed by trying again,
# and never in a way that changes the multi-key fallback structure
# those three files still own themselves.
# ================================================================

import requests
from tenacity import (
    retry, stop_after_attempt, wait_exponential_jitter,
    retry_if_exception_type,
)

SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})


class RetryableHTTPError(Exception):
    """Raised only for failures worth retrying — timeouts, connection
    errors, and 5xx server errors. A 4xx is returned to the caller
    as-is, not retried, since a bad request or bad auth doesn't
    become correct by trying again."""
    pass


@retry(
    stop=stop_after_attempt(3),  # 1 initial attempt + 2 retries
    wait=wait_exponential_jitter(initial=0.5, max=3),
    retry=retry_if_exception_type(RetryableHTTPError),
    reraise=True,
)
def post_with_retry(url: str, headers: dict = None, **kwargs):
    """
    Drop-in replacement for SESSION.post(...) at any Groq call site.
    Returns the response object for BOTH success and 4xx (the caller
    still checks status_code and handles a 4xx exactly as before) —
    only a timeout, connection error, or 5xx triggers a retry here,
    and only reaches the caller as a raised RetryableHTTPError after
    every retry is exhausted (the caller's existing try/except around
    each key's attempt already handles that the same way it handles
    any other exception today — this doesn't require call sites to
    change their own error handling shape).

    A multipart file upload (files=...) needs Content-Type explicitly
    unset here, not inherited from SESSION's JSON default — requests
    only auto-computes the correct multipart boundary header when
    Content-Type isn't already present, and SESSION always has one
    set. Every call site using this function for a multipart request
    must pass files=... and this handles the rest.
    """
    req_headers = dict(headers or {})
    if "files" in kwargs:
        req_headers.setdefault("Content-Type", None)
    try:
        r = SESSION.post(url, headers=req_headers, **kwargs)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        raise RetryableHTTPError(str(e)) from e
    if r.status_code >= 500:
        raise RetryableHTTPError(f"{r.status_code}: {r.text[:200]}")
    return r
