# ================================================================
# GIDEON — core/tags.py
# ----------------------------------------------------------------
# Parses the three tags the model can emit inside a reply:
#   [ACTION:command]  — a device operation to perform
#   [SEARCH:query]    — a request to run a web search before answering
#   [READ:url]        — a request to fetch a full webpage before answering
#
# Each extractor returns (reply_with_tag_removed, tag_content_or_None).
# These are pure text-parsing functions — the actual search/read/
# action-execution logic lives elsewhere (integrations/web.py,
# core/permissions.py, device/android.py).
#
# Moved from server.py with zero behavior change.
# ================================================================

import re

from core.permissions import sanitize_action


def extract_action_trigger(reply: str):
    """
    Finds the first [ACTION:...] tag and extracts its content.

    JSON payloads get a balanced-brace scan rather than a regex, so:
      - a ] inside a JSON array param doesn't get mistaken for the
        tag's closing bracket
      - a second [ACTION:...] tag later in the same reply doesn't get
        swallowed into the first one (the old greedy .+ regex did
        exactly this — grabbed everything up to the LAST ] in the
        whole message, mangling both tags into one malformed blob)
    Only the first tag in a reply is honored; the model is instructed
    to send at most one per message.
    """
    idx = reply.find('[ACTION:')
    if idx == -1:
        return reply, None

    start   = idx + len('[ACTION:')
    content = reply[start:]

    if content.lstrip().startswith('{'):
        depth, end = 0, None
        for i, ch in enumerate(content):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            return reply, None  # unterminated JSON, nothing safe to extract
        action   = content[:end].strip()
        tag_end  = start + end
        if tag_end < len(reply) and reply[tag_end] == ']':
            tag_end += 1
        clean = (reply[:idx] + reply[tag_end:]).strip()
        return clean, sanitize_action(action)

    # legacy plain-text command — stop at the first ], same as before
    m = re.match(r'([^\]]+)\]', content)
    if m:
        action  = m.group(1).strip()
        tag_end = start + m.end()
        clean   = (reply[:idx] + reply[tag_end:]).strip()
        return clean, sanitize_action(action)

    return reply, None


# ================================================================
# WEB SEARCH TAG — model-triggered, same pattern as [ACTION:...]
# ----------------------------------------------------------------
# The model can emit [SEARCH:query] when it judges a question needs
# current information it wouldn't reliably know (news, prices, recent
# events, "is X still true today" type questions). The server detects
# this tag the same way it detects [ACTION:...], runs ONE search, and
# feeds the results back to the model for a final answer. This keeps
# search opt-in per-message rather than running on every request.
# ================================================================

def extract_search_trigger(reply: str):
    m = re.search(r'\[SEARCH:([^\]]+)\]', reply)
    if m:
        query = m.group(1).strip()
        clean = re.sub(r'\[SEARCH:[^\]]+\]', '', reply).strip()
        return clean, query[:200]  # cap query length defensively
    return reply, None


# ================================================================
# FIRECRAWL READ TAG
# ----------------------------------------------------------------
# Model emits [READ:url] to fetch full webpage content.
# ================================================================

def extract_read_trigger(reply: str):
    m = re.search(r'\[READ:([^\]]+)\]', reply)
    if m:
        url   = m.group(1).strip()[:500]
        clean = re.sub(r'\[READ:[^\]]+\]', '', reply).strip()
        return clean, url
    return reply, None
