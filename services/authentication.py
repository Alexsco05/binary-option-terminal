# ================================================================
# GIDEON — services/authentication.py
# ----------------------------------------------------------------
# Device token generation and verification. Moved from server.py
# with zero behavior change.
#
# Not full authentication. Raises the bar from "anyone who guesses
# a string" to "anyone who has the signed token", which the Android
# app generates once per device_id and reuses. True auth
# (Firebase/Supabase) is the v1.1 follow-up; this is the launch-week
# mitigation for the device_id spoofing gap.
# ================================================================

import hmac
import hashlib

from config.environment import DEVICE_SECRET


def make_device_token(device_id: str) -> str:
    sig = hmac.new(
        DEVICE_SECRET.encode(), device_id.encode(), hashlib.sha256
    ).hexdigest()[:24]
    return f"{device_id}.{sig}"


def verify_device_token(device_id: str, token: str) -> bool:
    if not token:
        return False
    expected = make_device_token(device_id)
    return hmac.compare_digest(expected, token)
