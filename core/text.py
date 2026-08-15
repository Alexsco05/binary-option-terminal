# ================================================================
# GIDEON — core/text.py
# ----------------------------------------------------------------
# Tiny, dependency-free text utilities shared across modules.
# clean_name() moved here (not left in server.py) specifically so
# core/prompts.py can use it without creating a circular import —
# server.py imports build_system_prompt from core.prompts, so
# core.prompts can't import anything back from server.py.
# ================================================================

import re
import json


def clean_name(raw: str) -> str:
    if not raw:
        return ""
    cleaned = raw.split("[")[0].split("]")[0].strip()
    cleaned = re.sub(r"[^a-zA-Z0-9\s\-']", "", cleaned).strip()
    return cleaned[:50]


def _safe_json_loads(text: str):
    """Parses JSON, repairing common trailing-comma issues from LLM output."""
    try:
        return json.loads(text)
    except Exception:
        try:
            repaired = re.sub(r',\s*([\]}])', r'\1', text)
            return json.loads(repaired)
        except Exception as e:
            print(f"[JSON] repair failed: {e}")
            return None
