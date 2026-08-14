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


def clean_name(raw: str) -> str:
    if not raw:
        return ""
    cleaned = raw.split("[")[0].split("]")[0].strip()
    cleaned = re.sub(r"[^a-zA-Z0-9\s\-']", "", cleaned).strip()
    return cleaned[:50]
  
