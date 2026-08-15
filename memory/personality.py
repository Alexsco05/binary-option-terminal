# ================================================================
# GIDEON — memory/personality.py
# ----------------------------------------------------------------
# Long-term memory: conversation history (with periodic AI
# summarization), the personality profile (facts, preferences,
# people, locations, mood), and background fact extraction from
# each message. Moved from server.py with zero behavior change.
# ================================================================

import re
import datetime

from storage import read_json, write_json
from core.text import clean_name, _safe_json_loads
from integrations.providers import _call_groq_raw
from memory.conversation import EXECUTOR


# ================================================================
# HISTORY (via storage module — locked + atomic writes)
# ================================================================
def load_history(device_id: str):
    return read_json("history", device_id, [])


def save_history(history: list, device_id: str):
    write_json("history", device_id, history)


def update_long_term(user_msg: str, bot_reply: str, device_id: str):
    history = load_history(device_id)
    history.append({
        "timestamp": datetime.datetime.now().isoformat(),
        "user": user_msg, "gideon": bot_reply,
    })
    if len(history) > 100:
        history = _summarise(history, device_id)
    save_history(history, device_id)


def _summarise(history: list, device_id: str):
    """
    Summarizes into categories instead of a flat blob, so important
    details (goals, projects, relationships) survive compression
    instead of being flattened into one vague paragraph.
    """
    try:
        recent = history[-40:]
        old    = history[:-40]
        text   = "\n".join(f"U:{h['user']}\nG:{h['gideon']}" for h in old)
        prompt = (
            "Summarize this conversation history into JSON with these "
            "exact keys: goals, projects, relationships, preferences. "
            "Each is a short list of strings. Return ONLY the JSON.\n\n"
            f"{text}"
        )
        raw = _call_groq_raw(prompt)
        if raw:
            clean = raw.strip().replace("```json", "").replace("```", "").strip()
            s, e = clean.find("{"), clean.rfind("}") + 1
            if s >= 0 and e > 0:
                parsed = _safe_json_loads(clean[s:e])
                if parsed:
                    summary_line = (
                        f"Goals: {', '.join(parsed.get('goals', []))}. "
                        f"Projects: {', '.join(parsed.get('projects', []))}. "
                        f"Relationships: {', '.join(parsed.get('relationships', []))}. "
                        f"Preferences: {', '.join(parsed.get('preferences', []))}."
                    )
                    return [{
                        "timestamp": datetime.datetime.now().isoformat(),
                        "user": "[Summary]", "gideon": summary_line,
                    }] + recent
    except Exception as e:
        print(f"[Memory] summarise: {e}")
    return history[-40:]


# ================================================================
# PERSONALITY
# ================================================================
def load_personality(device_id: str):
    data = read_json("personality", device_id, None)
    if data is None:
        return {
            "name": "User", "nickname": "User",
            "facts": [], "preferences": [], "people": [],
            "locations": [], "mood": "neutral",
            "mood_history": [], "last_seen": "",
        }
    data["name"]     = clean_name(data.get("name", "User")) or "User"
    data["nickname"] = clean_name(data.get("nickname", "")) or data["name"]
    return data


def save_personality(data: dict, device_id: str):
    data["name"]     = clean_name(data.get("name", "User")) or "User"
    data["nickname"] = clean_name(data.get("nickname", "")) or data["name"]
    write_json("personality", device_id, data)


# ================================================================
# FACT EXTRACTION — validated, contradiction-aware, repair-parsed
# ================================================================
def extract_facts(user_msg: str, device_id: str):
    EXECUTOR.submit(_extract_facts_bg, user_msg, device_id)


def _category_key(item: str) -> str:
    """Very light heuristic to detect 'same topic, different value' facts
    so a later statement replaces rather than duplicates the earlier one.
    e.g. 'favorite color is red' and 'favorite color is blue' share a key."""
    words = re.sub(r'\b(is|are|was|were|the|a|an)\b', '', item.lower())
    words = re.sub(r'[^a-z\s]', '', words).split()
    # use the first 2-3 meaningful words as the topic key
    return " ".join(words[:3])


def _extract_facts_bg(user_msg: str, device_id: str):
    try:
        p    = load_personality(device_id)
        name = p.get("nickname") or p.get("name", "User")
        raw = _call_groq_raw(
            f"Extract personal facts about {name} from this message ONLY "
            f"if explicitly and clearly stated. Do not infer or guess. "
            f"Return ONLY valid JSON with keys: facts, preferences, people, "
            f"locations, mood (one word). "
            f"If nothing is stated: "
            f'{{"facts":[],"preferences":[],"people":[],"locations":[],"mood":"neutral"}} '
            f"Message: {user_msg}"
        )
        if not raw:
            return
        clean = raw.strip().replace("```json", "").replace("```", "").strip()
        s, e = clean.find("{"), clean.rfind("}") + 1
        if s < 0 or e <= 0:
            return
        ex = _safe_json_loads(clean[s:e])
        if not ex:
            return

        for key in ["facts", "preferences", "people", "locations"]:
            for item in ex.get(key, []):
                # basic validation — reject absurdly long or empty items
                if not item or not isinstance(item, str) or len(item) > 150:
                    continue
                item = item.strip()
                if not item:
                    continue

                existing_list = p.setdefault(key, [])
                new_topic = _category_key(item)

                # contradiction handling: same topic, different value
                # → replace instead of accumulate
                replaced = False
                for i, existing_item in enumerate(existing_list):
                    if _category_key(existing_item) == new_topic and new_topic:
                        existing_list[i] = item
                        replaced = True
                        break

                if not replaced and item not in existing_list:
                    existing_list.append(item)

                # cap list growth regardless
                p[key] = existing_list[-30:]

        mood = ex.get("mood", "")
        if mood and isinstance(mood, str) and mood != "neutral":
            p["mood"] = mood[:30]
            p.setdefault("mood_history", []).append({
                "timestamp": datetime.datetime.now().isoformat(), "mood": mood[:30]
            })
            p["mood_history"] = p["mood_history"][-20:]

        p["last_seen"] = datetime.datetime.now().isoformat()
        save_personality(p, device_id)
    except Exception as e:
        print(f"[Facts] {e}")
