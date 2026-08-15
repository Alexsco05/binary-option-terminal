# ================================================================
# GIDEON BACKEND - Version 11.0
# Creator: Alexsco (Adegolu Alex) @alexsco_official
# Pre-launch hardened build - July 1, 2026
# Modularization step 1: config extracted to config/environment.py
# and config/settings.py — everything else in this file is UNCHANGED.
# ================================================================

from flask import Flask, request, jsonify, Response, stream_with_context
import os, re, time, base64, json, datetime, threading
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

import requests

from storage import read_json, write_json, delete_json, safe_device_id
from ttl_cache import TTLCache

from config.environment import (
    BOT_NAME, GROQ_KEYS, OPENROUTER_KEYS, MISTRAL_KEYS,
    GEMINI_KEY, COHERE_KEY, CEREBRAS_KEY, WEATHER_KEY, NEWS_KEY,
    OPENAI_KEY, BRAVE_SEARCH_KEY, SERPER_KEY, FIRECRAWL_KEY,
    DEVICE_SECRET, PORT,
)
from config.settings import (
    MEMORY_LIMIT, CACHE_MAXSIZE, CACHE_TTL_SECONDS,
    EXECUTOR_MAX_WORKERS, PROVIDER_SOFT_CAPS, MODELS,
)

app = Flask(__name__)

# ── shared HTTP session — now lives in integrations/client.py, since
# every provider integration needs it and importing it from server.py
# would create a circular import ──────────────────────────────────
from integrations.client import SESSION

# ── background work pool — replaces unbounded thread spawning ─────
# EXECUTOR now lives in memory/conversation.py — imported below with
# the rest of short-term memory state.

# ================================================================
# DEVICE TOKEN + RATE LIMITING — moved to services/authentication.py
# and services/rate_limit.py. See those files for the actual logic.
# ================================================================
from services.authentication import make_device_token, verify_device_token
from services.rate_limit import is_rate_limited

# ================================================================
# PROVIDER LOAD TRACKING (Phase 9)
# ----------------------------------------------------------------
# Every route's primary has been Groq for a while now, on purpose —
# every attempt at routing specific task types to specialized models
# (dedicated math model, dedicated coding model) broke eventually,
# deprecated or moved to paid-only. That history is real and this
# doesn't undo it: routes still don't get reassigned by task type.
#
# What this DOES add: Groq hitting its daily token cap has already
# happened once for real ("Groq's TPD limit tonight" — see the fast
# route's own comment below). Right now every request goes to Groq
# first regardless of how much it's already been used, and only
# spreads to other providers once Groq is already failing. This
# tracks rolling usage per provider and, when the configured primary
# is nearing its soft cap, transparently promotes the first fallback
# to take its place BEFORE the request goes out — proactive load
# spreading, not reactive failover. The existing fallback chain on
# actual failure is completely untouched.
#
# PROVIDER_SOFT_CAPS and MODELS now live in config/settings.py —
# see there for the actual cap numbers and model registry.
# ================================================================
# ================================================================
# PROVIDER LOAD TRACKING + MODEL ROUTING — moved to core/router.py.
# ================================================================
from core.router import (
    record_provider_usage, _provider_usage_count, provider_near_cap,
    select_primary, route_model, get_mood_behavior, call_provider,
)

# ================================================================
# ================================================================
# ACTION WHITELIST — moved to core/permissions.py.
# ================================================================
from core.permissions import (
    ALLOWED_ACTION_PREFIXES, ALLOWED_TOOLS,
    is_action_allowed, sanitize_action,
)

# ================================================================
# MEMORY — short-term session state, long-term history/personality,
# and the knowledge graph all moved to memory/. See
# memory/conversation.py, memory/personality.py, memory/knowledge.py.
# ================================================================
from memory.conversation import (
    EXECUTOR, CACHE, USER_SHORT_TERM, PENDING_CONFIRMATIONS,
    get_short_term, trim_short_term,
)
from memory.personality import (
    load_history, save_history, update_long_term,
    load_personality, save_personality, extract_facts,
)
from memory.knowledge import (
    KNOWLEDGE_STORE, _get_knowledge, merge_nodes,
)

# ================================================================
# SANITIZER — clean_name() moved to core/text.py (shared with
# core/prompts.py; kept as a tiny zero-dependency module to avoid
# a circular import between server.py and core/).
# ================================================================
from core.text import clean_name

# ================================================================
# MATH DISPLAY + SPEECH CONVERSION — moved to skills/mathematics.py.
# ================================================================
from skills.mathematics import (
    LATEX_MAP, latex_to_unicode, strip_stray_inline_dollars,
    SPEECH_MATH_MAP, convert_math_for_speech,
)

# ================================================================
# HISTORY, PERSONALITY, FACT EXTRACTION — moved to memory/personality.py.
# _safe_json_loads is used directly in this file too (action parsing,
# research, planning), so it comes from core/text.py.
# ================================================================
from core.text import _safe_json_loads
# ================================================================
# ACTION/SEARCH/READ TAG PARSING — moved to core/tags.py.
# RESEARCH MODE (run_research) — moved to skills/research.py.
# ================================================================
from core.tags import extract_action_trigger, extract_search_trigger, extract_read_trigger
from integrations.web import (
    web_search, web_search_with_links, firecrawl_read,
    get_weather, extract_city_from_weather_query, get_news,
)
from skills.research import run_research

# ================================================================
# OFFLINE COMMAND DETECTION — moved to device/android.py.
# ================================================================
from device.android import (
    OFFLINE_COMMANDS, AMBIGUOUS_GUARD_WORDS,
    detect_offline_command, build_action_trigger,
)

# ================================================================
# ================================================================
# INTENT DETECTION + PENDING CONFIRMATIONS — moved to core/intent.py.
# ================================================================
from core.intent import (
    INTENT_PATTERNS, detect_user_intent,
    store_pending, check_user_confirmation,
)

# ================================================================
# INTENT RESPONSE BUILDER — moved to core/intent.py.
# ================================================================
from core.intent import build_intent_response

# ================================================================
# MODEL ROUTER — word-boundary matching to cut false positives
# (e.g. "explain Morse code" no longer routes to coding)
# ================================================================
# _word_match() and route_model() moved to core/router.py — imported
# near the top of this file.

# ================================================================
# SPECIALIST LIBRARY + SYSTEM PROMPT — moved to core/prompts.py.
# ================================================================
from core.prompts import build_system_prompt

# ================================================================
# AI PROVIDER CALLS — moved to integrations/providers.py (all six
# providers in one file). _stream_groq stays here (below) — it's
# tangled with search/read/action-tag resolution and memory writes,
# core-agent territory.
# ================================================================
from integrations.providers import (
    _call_groq_raw, _call_groq_raw_extended, _call_groq,
    _call_openrouter, _call_gemini, _call_cohere,
    _call_cerebras, _call_mistral,
)


# ================================================================
# PHASE 1 — STREAMING GROQ
# ----------------------------------------------------------------
# Calls Groq with stream=True and yields sentence chunks as they
# arrive. Android starts TTS on the first sentence while the rest
# is still being generated — this is what makes replies feel instant.
# ================================================================
def _stream_groq(model_input: str, msg: str, model: str, system_prompt: str,
                 short_term: list, device_id: str, route: str = "fast",
                 fallback_chain: list = None):
    """
    Generator yielding SSE-formatted sentence chunks.
    Format  : data: <sentence>\n\n
    Done    : data: [DONE]\n\n
    Action  : data: [ACTION:<cmd>]\n\n
    Error   : data: [ERROR]<message>\n\n

    model_input is what actually gets sent to Groq (may have weather/
    news context folded in). msg is the original user text, used for
    search/read follow-up prompts and for what gets persisted to
    short_term — same split process() already uses for weather/news,
    kept consistent here.
    """
    is_complex = len(model_input.split()) > 8
    messages   = list(short_term)
    messages[0] = {"role": "system", "content": system_prompt}
    messages.append({"role": "user", "content": model_input})

    for key in GROQ_KEYS:
        if not key:
            continue
        try:
            record_provider_usage("groq")
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model":      model,
                    "messages":   messages,
                    "max_tokens": 1500 if is_complex else 800,
                    "stream":     True,
                },
                stream=True,
                timeout=30,
            )
            if r.status_code != 200:
                print(f"[Stream] Groq {model} HTTP {r.status_code}")
                continue

            buffer     = ""
            full_text  = ""
            SENT_CHARS = {".", "!", "?"}

            # The memory-save logic below the loop only runs if the loop
            # finishes normally. If the Android client disconnects
            # mid-stream — which is exactly what happens on a barge-in,
            # since StreamingLLMClient.cancel() just closes the
            # connection — the next yield raises GeneratorExit right
            # here, the generator dies at that point, and everything
            # after the loop (including saving to memory) never runs.
            # That meant an interrupted exchange was silently never
            # remembered, on top of whatever partial reply the user did
            # hear. Catching GeneratorExit here saves what was generated
            # so far before letting the disconnect propagate.
            try:
                for raw_line in r.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="ignore")
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        token = chunk["choices"][0].get("delta", {}).get("content", "")
                        if not token:
                            continue
                        buffer    += token
                        full_text += token

                        # yield at sentence boundary or when buffer is large enough
                        if any(c in buffer for c in SENT_CHARS) or len(buffer) > 180:
                            split_at = max(
                                buffer.rfind(". "),
                                buffer.rfind("! "),
                                buffer.rfind("? "),
                                buffer.rfind(".\n"),
                            )
                            if split_at > 0:
                                sentence = buffer[:split_at + 1].strip()
                                buffer   = buffer[split_at + 1:].strip()
                            elif len(buffer) > 250:
                                sentence = buffer.strip()
                                buffer   = ""
                            else:
                                continue
                            if sentence:
                                yield f"data: {_clean_for_route(sentence, route)}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
            except GeneratorExit:
                if full_text.strip():
                    try:
                        partial = _clean_for_route(full_text.strip(), route)
                        short_term.append({"role": "user", "content": msg})
                        short_term.append({"role": "assistant", "content": partial})
                        trim_short_term(short_term)
                        EXECUTOR.submit(update_long_term, msg, partial, device_id)
                        print(f"[Stream] Barge-in — saved partial reply ({len(partial)} chars)")
                    except Exception as e:
                        print(f"[Stream] partial-save on interrupt failed: {e}")
                raise

            # ── TAG RESOLUTION ──────────────────────────────────────
            # Everything above was already sent to the client in real
            # time as soon as a sentence boundary was hit. Only the
            # leftover trailing buffer — whatever had no punctuation to
            # trigger an earlier yield — is still being held back, and
            # that's exactly where a [SEARCH:...], [READ:...] or
            # [ACTION:...] tag ends up, since the model is instructed
            # to end its reply with the tag and nothing else. This used
            # to just dump that buffer straight to the client raw,
            # which is why "[SEARCH:latest news]" showed up as a chat
            # bubble instead of triggering an actual search.
            spoken_tail = buffer.strip()
            tag_consumed = False
            resolved = full_text

            pre_search_clean, search_query = extract_search_trigger(resolved)
            if search_query:
                tag_consumed = True
                print(f"[Stream][Search] Model requested search: '{search_query}'")
                results = web_search(search_query)
                if results:
                    followup_prompt = (
                        f"User asked: {msg}\n\n"
                        f"You searched for: {search_query}\n"
                        f"Search results:\n{results}\n\n"
                        f"Now answer the user's question naturally using "
                        f"these results. Do not mention that you searched "
                        f"or show raw results — just answer as yourself."
                    )
                    followup = call_provider(followup_prompt, "groq", model,
                                             system_prompt, short_term, device_id)
                    resolved = followup or pre_search_clean or (
                        "I searched but could not put together an answer. "
                        "Please try again."
                    )
                else:
                    resolved = pre_search_clean.strip() or (
                        "I don't have live search access right now. "
                        "Let me answer from what I know."
                    )

            pre_read_clean, read_url = extract_read_trigger(resolved)
            if read_url:
                tag_consumed = True
                print(f"[Stream][Firecrawl] Model requested read: '{read_url}'")
                page_content = firecrawl_read(read_url)
                if page_content:
                    followup = call_provider(
                        f"User asked: {msg}\n\nYou read: {read_url}\n"
                        f"Content:\n{page_content}\n\nAnswer naturally.",
                        "groq", model, system_prompt, short_term, device_id
                    )
                    resolved = followup or pre_read_clean or "I could not read that page."
                else:
                    resolved = pre_read_clean.strip() or "I could not access that page right now."

            clean_final, action_trigger = extract_action_trigger(resolved)
            clean_final = _clean_for_route(clean_final, route)

            if tag_consumed:
                for chunk in _split_into_sentence_chunks(clean_final):
                    yield f"data: {chunk}\n\n"
            elif spoken_tail:
                tail_clean, _ = extract_action_trigger(spoken_tail)
                if tail_clean.strip():
                    yield f"data: {_clean_for_route(tail_clean, route)}\n\n"

            if action_trigger and action_trigger not in ("None", "null"):
                yield f"data: [ACTION:{action_trigger}]\n\n"

            # update memory with what the user actually heard, never
            # the raw tag text
            short_term.append({"role": "user",     "content": msg})
            short_term.append({"role": "assistant", "content": clean_final})
            trim_short_term(short_term)
            EXECUTOR.submit(update_long_term, msg, clean_final, device_id)
            extract_facts(msg, device_id)

            yield "data: [DONE]\n\n"
            return

        except requests.Timeout:
            print(f"[Stream] Groq timeout on {model}")
        except Exception as e:
            print(f"[Stream] Groq {model} error: {e}")

    # Every GROQ_KEYS attempt failed or rate-limited (this is the gap
    # that was here before — model_cfg["fallback"] was configured and
    # correct, but nothing in this function ever called it, so a Groq
    # outage or hitting the daily token cap meant every request failed
    # with the hardcoded error below regardless of what fallback was
    # set up. Now it actually falls through to it, and tries every
    # provider in the chain, not just one, before finally giving up.
    for fb in (fallback_chain or []):
        print(f"[Stream] Trying fallback {fb['provider']}/{fb['model']}")
        answer = call_provider(model_input, fb["provider"],
                               fb["model"], system_prompt,
                               short_term, device_id)
        if answer:
            final, action_trigger = extract_action_trigger(answer)
            final = _clean_for_route(final, route)

            short_term.append({"role": "user",     "content": msg})
            short_term.append({"role": "assistant", "content": final})
            trim_short_term(short_term)
            EXECUTOR.submit(update_long_term, msg, final, device_id)
            extract_facts(msg, device_id)

            chunks = list(_split_into_sentence_chunks(final))
            for chunk in (chunks or [final]):
                yield f"data: {chunk}\n\n"
            if action_trigger and action_trigger not in ("None", "null"):
                yield f"data: [ACTION:{action_trigger}]\n\n"
            yield "data: [DONE]\n\n"
            return
        print(f"[Stream] Fallback {fb['provider']} also failed, trying next in chain")

    yield "data: [ERROR]I could not get a response. Please try again.\n\n"
    yield "data: [DONE]\n\n"


# call_provider() moved to core/router.py — imported above.

# ================================================================
# TTS — Edge TTS primary (free, no quota/billing), OpenAI optional
# fallback. Same /tts contract as before (base64 in JSON), so the
# ================================================================
# TTS — full pipeline (raw generators + orchestration) moved to
# integrations/tts.py.
# ================================================================
from integrations.tts import generate_tts_base64

# ================================================================
# WEATHER & NEWS — moved to integrations/web.py, imported near the
# top of this file alongside web_search/firecrawl_read.
# ================================================================

# ================================================================
# MAIN PROCESS
# ================================================================
def resolve_immediate_reply(msg: str, device_id: str):
    """
    Shared short-circuit path used by BOTH /run and /stream, in this
    order: pending confirmation, cache, intent detection, offline
    command. Returns (reply, action_trigger) if one of these produced
    a complete answer, or None if the caller should continue on to
    full AI routing.

    This used to exist twice — once correctly inside process() for
    typed chat, and once as a broken partial copy inside /stream that
    only handled offline commands, and did so by unpacking a plain
    string into two variables (crashes on every offline command said
    during a voice session). Having one shared version means /run and
    /stream can no longer drift apart on this logic.
    """
    # 1. pending confirmation
    conf = check_user_confirmation(msg, device_id)
    if conf is not None:
        reply, action = conf
        st = get_short_term(device_id)
        st.append({"role": "user", "content": msg})
        st.append({"role": "assistant", "content": reply})
        trim_short_term(st)
        return reply, action

    # 2. cache — informational replies only.
    #    CRITICAL FIX: action-bearing replies are never cached, because a
    #    cached "Opening WhatsApp" would silently lose the action_trigger
    #    on every repeat and the app would never actually open.
    cache_key = f"{device_id}:{msg.lower()}"
    cached_entry = CACHE.get(cache_key)
    if cached_entry is not None:
        reply, action = cached_entry
        st = get_short_term(device_id)
        st.append({"role": "user", "content": msg})
        st.append({"role": "assistant", "content": reply})
        trim_short_term(st)
        return reply, action

    personality = load_personality(device_id)

    # 3. intent detection
    intent = detect_user_intent(msg)
    if intent:
        reply, action = build_intent_response(intent, msg, personality, device_id)
        if reply:
            st = get_short_term(device_id)
            st.append({"role": "user", "content": msg})
            st.append({"role": "assistant", "content": reply})
            trim_short_term(st)
            return reply, action

    # 4. offline command
    offline_type = detect_offline_command(msg)
    if offline_type:
        action_trigger = sanitize_action(build_action_trigger(offline_type, msg))
        short_term    = get_short_term(device_id)
        system_prompt = build_system_prompt(personality, "fast")
        answer = _call_groq(msg, "llama-3.3-70b-versatile", system_prompt, short_term)
        if answer:
            clean, extra = extract_action_trigger(answer)
            clean = latex_to_unicode(clean)
            final_action = action_trigger or extra
            short_term.append({"role": "user", "content": msg})
            short_term.append({"role": "assistant", "content": clean})
            trim_short_term(short_term)
            return clean, final_action
        return "On it.", action_trigger

    return None


# ================================================================
# STREAMING HELPERS — shared between /stream's Groq path and its
# non-Groq fallback path, so both apply the same math/route cleanup
# and the same sentence-pacing for non-streamed follow-up answers.
# ================================================================
def _split_into_sentence_chunks(text: str):
    """Splits a full block of text (e.g. a non-streamed follow-up
    answer) into sentence-sized SSE chunks so it still arrives as
    several pieces instead of one big pause-then-dump."""
    text = (text or "").strip()
    if not text:
        return
    pieces = re.split(r'(?<=[.!?])\s+', text)
    buf = ""
    for p in pieces:
        buf = f"{buf} {p}".strip() if buf else p
        if len(buf) > 40:
            yield buf
            buf = ""
    if buf:
        yield buf


def _clean_for_route(text: str, route: str) -> str:
    """Same formatting rule process() already applies: math route keeps
    real $$ blocks for the WebView renderer and only strips stray inline
    $ wrapping, everything else gets full LaTeX-to-unicode conversion.
    /stream never applied either of these before, so voice replies with
    formulas came through as raw LaTeX.

    BUG FIXED: latex_to_unicode()'s cleanup regex strips ANY backslash
    followed by letters, meant to catch leftover LaTeX commands like
    \\alpha, but that's the exact same shape as \\n, \\t, \\d, \\w, \\s
    in real code (newlines, tabs, regex patterns) and Windows paths
    like C:\\Users\\name. Every code sample the model generated on any
    non-math route was getting its escape sequences silently deleted.
    The coding route now skips this entirely, and every other route
    protects fenced code blocks before running the LaTeX cleanup, so a
    code snippet inside a normal conversational answer doesn't get
    mangled either — that happens often, not just on the coding route.
    """
    if route == "coding":
        return text

    # pull out fenced code blocks before any LaTeX/math cleanup touches
    # the text, then put them back afterward completely untouched
    code_blocks = []
    def _stash(m):
        code_blocks.append(m.group(0))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"
    protected = re.sub(r'```.*?```', _stash, text, flags=re.DOTALL)

    if route == "math":
        cleaned = strip_stray_inline_dollars(protected)
    else:
        cleaned = latex_to_unicode(protected)

    for i, block in enumerate(code_blocks):
        cleaned = cleaned.replace(f"\x00CODEBLOCK{i}\x00", block)
    return cleaned


def _looks_multi_part(msg: str) -> bool:
    """
    Cheap heuristic deciding whether a request is worth actually
    planning and executing step by step, versus the normal single-shot
    path everything already uses. Deliberately conservative: a false
    negative just means the existing, already-working path handles it
    exactly as it did before this phase existed. A false positive costs
    one extra small planning call. Short or simple messages never reach
    this check's cost at all — plan_steps only runs if this returns True.
    """
    if len(msg.split()) < 12:
        return False
    ml = msg.lower()
    markers = (" and then ", " then ", " after that ", " also ",
               " first ", " next ", " and also ")
    return msg.count("?") > 1 or any(m in ml for m in markers)

def plan_steps(msg: str, device_id: str) -> list:
    """
    Asks the model to break a request into an ordered list of
    self-contained steps, ONLY called after _looks_multi_part already
    said yes. Always returns a usable list: on any failure (call
    fails, bad JSON, empty result) it returns [msg] unchanged, which
    the caller treats as "not actually multi-part" and falls through
    to the normal single-shot path. Capped at 5 steps as a sanity
    limit against a runaway plan.
    """
    prompt = (
        "Break this request into an ordered list of separate, "
        "self-contained steps, only if it genuinely has multiple "
        "distinct parts. Each step should be answerable on its own, "
        "with enough context to stand alone. Return ONLY valid JSON: "
        '{"steps": ["step one", "step two"]}. '
        'If this is really just one request, return {"steps": ["<the original request>"]}.\n\n'
        f"Request: {msg}"
    )
    raw = _call_groq_raw_extended(prompt, max_tokens=400)
    if not raw:
        return [msg]
    clean = raw.strip().replace("```json", "").replace("```", "").strip()
    s, e = clean.find("{"), clean.rfind("}") + 1
    if s < 0 or e <= 0:
        return [msg]
    parsed = _safe_json_loads(clean[s:e])
    steps = parsed.get("steps") if parsed else None
    if not steps or not isinstance(steps, list):
        return [msg]
    steps = [str(s).strip() for s in steps if str(s).strip()]
    return steps[:5] if steps else [msg]

def process_multi_step(msg: str, device_id: str):
    """
    Genuine step-by-step execution for requests that actually have
    more than one distinct part. Each step runs through the same
    routing and model-calling machinery any single message already
    uses, and results are combined into one reply, so a request like
    "check the weather, then remind me to bring an umbrella" gets both
    parts handled instead of hoping one model call covers both.

    Returns None whenever the request doesn't genuinely have multiple
    parts (the common case), meaning process() falls straight through
    to the existing single-shot path completely unchanged. Nothing
    about how single-part requests are handled is touched by this.

    Scoped to /run (typed chat) only for now — see the note in
    process() for why voice sessions aren't wired to this yet.
    """
    if not _looks_multi_part(msg):
        return None

    steps = plan_steps(msg, device_id)
    if len(steps) <= 1:
        return None

    print(f"[Planner] '{msg[:60]}' -> {len(steps)} step(s): {steps}")

    personality    = load_personality(device_id)
    short_term     = get_short_term(device_id)
    answers        = []
    action_trigger = None

    for step in steps:
        route         = route_model(step, personality)
        system_prompt = build_system_prompt(personality, route)
        model_cfg     = MODELS.get(route, MODELS["fast"])
        primary       = select_primary(model_cfg)

        answer = call_provider(step, primary["provider"],
                               primary["model"], system_prompt,
                               short_term, device_id)
        if not answer:
            for fb in model_cfg.get("fallbacks", []):
                answer = call_provider(step, fb["provider"], fb["model"],
                                       system_prompt, short_term, device_id)
                if answer:
                    break

        clean, action = extract_action_trigger(answer or "I couldn't complete that part.")
        clean = _clean_for_route(clean, route)
        answers.append(clean)
        if action and not action_trigger:
            action_trigger = action  # only the first step's action reaches the phone

    combined = " ".join(a.strip() for a in answers if a and a.strip())

    short_term.append({"role": "user",      "content": msg})
    short_term.append({"role": "assistant", "content": combined})
    trim_short_term(short_term)
    EXECUTOR.submit(update_long_term, msg, combined, device_id)
    extract_facts(msg, device_id)

    return combined, action_trigger


def process(msg: str, device_id: str):
    msg = msg.strip()
    if not msg:
        return "No input received.", None
    if len(msg) > 2000:
        return "Message too long. Please keep it shorter.", None

    shortcut = resolve_immediate_reply(msg, device_id)
    if shortcut is not None:
        return shortcut

    # Phase 4 — only engages for requests that genuinely look multi-part;
    # returns None immediately otherwise, so this adds no latency or
    # behavior change to the normal single-shot case below. Voice
    # sessions (/stream) intentionally don't call this yet — see
    # process_multi_step's docstring.
    multi = process_multi_step(msg, device_id)
    if multi is not None:
        return multi

    personality   = load_personality(device_id)
    cache_key     = f"{device_id}:{msg.lower()}"

    # 5. AI routing
    route         = route_model(msg, personality)
    system_prompt = build_system_prompt(personality, route)
    short_term    = get_short_term(device_id)

    if route == "weather":
        city = extract_city_from_weather_query(msg)
        weather = get_weather(city)
        if weather:
            ans = _call_groq(f"User: {msg}\nWeather: {weather}\nRespond naturally.",
                             "llama-3.3-70b-versatile", system_prompt, short_term)
            if ans:
                clean, trigger = extract_action_trigger(ans)
                clean = latex_to_unicode(clean)
                short_term.append({"role": "user", "content": msg})
                short_term.append({"role": "assistant", "content": clean})
                trim_short_term(short_term)
                return clean, trigger

    if route == "news":
        news = get_news()
        if news:
            ans = _call_groq(f"User: {msg}\nNews: {news}\nSummarise naturally.",
                             "llama-3.3-70b-versatile", system_prompt, short_term)
            if ans:
                clean, trigger = extract_action_trigger(ans)
                clean = latex_to_unicode(clean)
                short_term.append({"role": "user", "content": msg})
                short_term.append({"role": "assistant", "content": clean})
                trim_short_term(short_term)
                return clean, trigger

    model_cfg = MODELS.get(route, MODELS["fast"])
    primary   = select_primary(model_cfg)
    answer = call_provider(msg, primary["provider"],
                           primary["model"],
                           system_prompt, short_term, device_id)
    if not answer:
        for fb in model_cfg.get("fallbacks", []):
            print(f"[Process] Primary failed, trying fallback {fb['provider']}")
            answer = call_provider(msg, fb["provider"], fb["model"],
                                   system_prompt, short_term, device_id)
            if answer:
                break
    if not answer:
        for m in ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "mixtral-8x7b-32768"]:
            answer = _call_groq(msg, m, system_prompt, short_term)
            if answer:
                break

    if not answer:
        return "I could not process that right now. Please try again.", None

    # ── WEB SEARCH (model-triggered) ────────────────────────────────
    # If the model asked to search, run ONE search and ask it again
    # with results included, the same two-step pattern already used
    # for weather/news above. Capped at one round trip — if the model
    # asks to search again after seeing results, we just use what we
    # have rather than looping.
    pre_search_clean, search_query = extract_search_trigger(answer)
    if search_query:
        print(f"[Search] Model requested search: '{search_query}'")
        results = web_search(search_query)
        if results:
            followup_prompt = (
                f"User asked: {msg}\n\n"
                f"You searched for: {search_query}\n"
                f"Search results:\n{results}\n\n"
                f"Now answer the user's question naturally using these "
                f"results. Do not mention that you searched or show raw "
                f"results — just answer as yourself."
            )
            followup = call_provider(
                followup_prompt, primary["provider"],
                primary["model"], system_prompt, short_term, device_id
            )
            if followup:
                answer = followup
            else:
                # search worked but the follow-up call failed —
                # fall back to the pre-search reply with the tag stripped
                answer = pre_search_clean or "I searched but could not put together an answer. Please try again."
        else:
            print("[Search] No results or search unavailable, using original reply")
            # FIXED: always use pre_search_clean so the [SEARCH:...] tag
            # never reaches the user's chat bubble. When the model returns
            # ONLY the tag with no preceding text, pre_search_clean is empty
            # — use a fallback message instead of showing the raw tag.
            if pre_search_clean.strip():
                answer = pre_search_clean
            else:
                answer = "I don't have live search access right now. Let me answer from what I know."

    # ── FIRECRAWL READ (model-triggered) ─────────────────────────
    pre_read_clean, read_url = extract_read_trigger(answer)
    if read_url:
        print(f"[Firecrawl] Model requested read: '{read_url}'")
        page_content = firecrawl_read(read_url)
        if page_content:
            followup = call_provider(
                f"User asked: {msg}\n\nYou read: {read_url}\nContent:\n{page_content}\n\nAnswer naturally.",
                primary["provider"], primary["model"],
                system_prompt, short_term, device_id
            )
            answer = followup or pre_read_clean or "I could not read that page."
        else:
            answer = pre_read_clean.strip() or "I could not access that page right now."

    clean, action_trigger = extract_action_trigger(answer)
    if route != "math":
        clean = latex_to_unicode(clean)
    else:
        # math route keeps real $$ blocks for the WebView/MathJax renderer,
        # but stray inline $a$ $b$ style wrapping (which isn't real LaTeX
        # the renderer needs, just the model echoing notation in prose)
        # gets unwrapped to plain text so it reads naturally in chat.
        clean = strip_stray_inline_dollars(clean)

    # only cache informational replies — never cache anything carrying
    # an action_trigger (see Bug #1 fix note above)
    if not action_trigger:
        CACHE.set(cache_key, (clean, None))

    short_term.append({"role": "user", "content": msg})
    short_term.append({"role": "assistant", "content": clean})
    trim_short_term(short_term)

    EXECUTOR.submit(update_long_term, msg, clean, device_id)
    extract_facts(msg, device_id)

    return clean, action_trigger

# ================================================================
# FLASK ROUTES
# ================================================================
@app.route("/run", methods=["POST"])
def run():
    data       = request.get_json(silent=True) or {}
    action     = data.get("action", "process")
    msg        = str(data.get("data", "") or data.get("message", ""))[:2000].strip()
    user_name  = clean_name(str(data.get("user_name", "User"))[:100]) or "User"
    nickname   = clean_name(str(data.get("nickname", user_name))[:100]) or user_name
    device_id  = safe_device_id(str(data.get("device_id", "default"))[:100].strip() or "default")
    device_tok = str(data.get("device_token", ""))

    # device token check — soft enforcement for launch week.
    # If no token is sent (older app builds), we allow the request through
    # but log it, so this can be made strict in v1.1 once all clients
    # have updated to send a token.
    if device_tok and not verify_device_token(device_id, device_tok):
        print(f"[Security] Invalid device token for {device_id}")
        return jsonify({"reply": "Authentication failed."}), 401

    if is_rate_limited(device_id):
        return jsonify({"reply": "Too many requests. Please wait a moment."}), 429

    try:
        if action == "process":
            if nickname and nickname != "User":
                p = load_personality(device_id)
                if p.get("nickname", "User") != nickname:
                    p["nickname"] = nickname
                    p["name"]     = nickname
                    save_personality(p, device_id)

            reply, action_trigger = process(msg, device_id)
            resp = {"reply": reply or "Done"}
            if action_trigger and action_trigger not in ("None", "null"):
                resp["action_trigger"] = action_trigger
            return jsonify(resp)

        elif action == "update_name":
            clean = clean_name(msg) or "User"
            p = load_personality(device_id)
            p["name"] = p["nickname"] = clean
            save_personality(p, device_id)
            return jsonify({"reply": f"Name updated to {clean}"})

        elif action == "memory":
            p = load_personality(device_id)
            safe = {
                "name": p.get("name", "User"),
                "facts": p.get("facts", [])[:10],
                "preferences": p.get("preferences", [])[:5],
                "mood": p.get("mood", "neutral"),
                "last_seen": p.get("last_seen", ""),
            }
            return jsonify({"reply": json.dumps(safe, indent=2)})

        elif action == "clear_memory":
            save_history([], device_id)
            save_personality({
                "name": user_name, "nickname": user_name, "facts": [],
                "preferences": [], "people": [], "locations": [],
                "mood": "neutral", "mood_history": [], "last_seen": "",
            }, device_id)
            USER_SHORT_TERM.pop(device_id, None)
            PENDING_CONFIRMATIONS.pop(device_id, None)
            CACHE.delete_prefix(device_id)
            return jsonify({"reply": "Memory cleared"})

        elif action == "get_device_token":
            # called once by the Android app to obtain its signed token
            return jsonify({"device_token": make_device_token(device_id)})

        else:
            reply, action_trigger = process(msg, device_id)
            resp = {"reply": reply or "Done"}
            if action_trigger and action_trigger not in ("None", "null"):
                resp["action_trigger"] = action_trigger
            return jsonify(resp)

    except Exception as e:
        import traceback
        print(f"[Server] error: {e}")
        traceback.print_exc()
        return jsonify({"reply": "Something went wrong. Please try again."})




# ================================================================
# PHASE 1 — /stream SSE ENDPOINT
# ----------------------------------------------------------------
# Android connects here instead of /run for voice sessions.
# Sentences arrive progressively — TTS starts on sentence 1 while
# sentences 2, 3... are still being generated. Perceived latency
# drops from "wait for full reply" to "first sentence time" only.
# ================================================================
@app.route("/stream", methods=["POST"])
def stream_response():
    data      = request.get_json(silent=True) or {}
    msg       = str(data.get("data", "") or data.get("message", ""))[:2000].strip()
    user_name = clean_name(str(data.get("user_name", "User"))[:100]) or "User"
    nickname  = clean_name(str(data.get("nickname",  user_name))[:100]) or user_name
    device_id = safe_device_id(str(data.get("device_id", "default"))[:100].strip() or "default")
    device_tok = str(data.get("device_token", ""))

    if not msg:
        def empty():
            yield "data: [ERROR]Empty message.\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(empty()),
                        mimetype="text/event-stream")

    # device token check — same soft enforcement as /run. Previously
    # /stream skipped this entirely, so voice sessions were an open
    # door even after /run's auth got tightened.
    if device_tok and not verify_device_token(device_id, device_tok):
        print(f"[Security] Invalid device token for {device_id}")
        def unauthorized():
            yield "data: [ERROR]Authentication failed.\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(unauthorized()),
                        mimetype="text/event-stream")

    if is_rate_limited(device_id):
        def limited():
            yield "data: [ERROR]Too many requests. Please wait.\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(limited()),
                        mimetype="text/event-stream")

    # update name if provided
    if nickname and nickname != "User":
        p = load_personality(device_id)
        if p.get("nickname", "User") != nickname:
            p["nickname"] = nickname
            p["name"]     = nickname
            save_personality(p, device_id)

    # ── SAME SHORT-CIRCUIT PATH AS /run ─────────────────────────────
    # Pending confirmations, cache, intent detection ("should I open
    # WhatsApp?"), and offline commands now go through the exact same
    # logic typed chat uses. This used to be a separate, incomplete
    # copy here that only handled offline commands, and did so by
    # unpacking a plain string into two variables — which raised an
    # unhandled ValueError on every offline command said during a
    # voice session (e.g. "what time is it", "battery level", "lock
    # my phone") and killed the stream.
    shortcut = resolve_immediate_reply(msg, device_id)
    if shortcut is not None:
        reply, action_trigger = shortcut
        def shortcut_gen():
            chunks = list(_split_into_sentence_chunks(reply))
            for chunk in (chunks or [reply]):
                yield f"data: {chunk}\n\n"
            if action_trigger and action_trigger not in ("None", "null"):
                yield f"data: [ACTION:{action_trigger}]\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(shortcut_gen()),
                        mimetype="text/event-stream")

    personality  = load_personality(device_id)
    short_term   = USER_SHORT_TERM.setdefault(
        device_id, [{"role": "system", "content": ""}]
    )

    # route and build system prompt
    route        = route_model(msg, personality)
    system_prompt = build_system_prompt(personality, route)
    model_cfg    = MODELS.get(route, MODELS["fast"])
    primary      = select_primary(model_cfg)
    model        = primary["model"]
    provider     = primary["provider"]

    # weather/news get the same direct-API treatment /run already uses,
    # instead of relying on the model to request a search for them.
    # Previously /stream had no version of this at all, so a spoken
    # "how's the weather" would route to the model with no real data
    # and typically fall through to the (broken) search-tag path.
    model_input = msg
    if route == "weather":
        city = extract_city_from_weather_query(msg)
        weather = get_weather(city)
        if weather:
            model_input = f"User: {msg}\nWeather: {weather}\nRespond naturally."
    elif route == "news":
        news = get_news()
        if news:
            model_input = f"User: {msg}\nNews: {news}\nSummarise naturally."

    # only Groq supports streaming in current stack
    if provider == "groq":
        gen = _stream_groq(model_input, msg, model, system_prompt,
                           short_term, device_id, route,
                           fallback_chain=model_cfg.get("fallbacks"))
    else:
        # non-Groq provider — no native token streaming, but still needs
        # the same search/read/action handling as everything else, or
        # those requests silently break for whichever provider ends up
        # here. Previously this branch also never called
        # update_long_term/extract_facts, so long-term memory and
        # personality facts were never captured for these turns.
        answer = call_provider(model_input, provider, model, system_prompt,
                               short_term, device_id)
        if not answer:
            for fb in model_cfg.get("fallbacks", []):
                answer = call_provider(model_input, fb["provider"], fb["model"],
                                       system_prompt, short_term, device_id)
                if answer:
                    break
        answer = answer or "I could not get a response right now."

        pre_search_clean, search_query = extract_search_trigger(answer)
        if search_query:
            print(f"[Stream][Search] Model requested search: '{search_query}'")
            results = web_search(search_query)
            if results:
                followup_prompt = (
                    f"User asked: {msg}\n\n"
                    f"You searched for: {search_query}\n"
                    f"Search results:\n{results}\n\n"
                    f"Now answer the user's question naturally using "
                    f"these results. Do not mention that you searched "
                    f"or show raw results — just answer as yourself."
                )
                followup = call_provider(followup_prompt, provider, model,
                                         system_prompt, short_term, device_id)
                answer = followup or pre_search_clean or (
                    "I searched but could not put together an answer. "
                    "Please try again."
                )
            else:
                answer = pre_search_clean.strip() or (
                    "I don't have live search access right now. "
                    "Let me answer from what I know."
                )

        pre_read_clean, read_url = extract_read_trigger(answer)
        if read_url:
            print(f"[Stream][Firecrawl] Model requested read: '{read_url}'")
            page_content = firecrawl_read(read_url)
            if page_content:
                followup = call_provider(
                    f"User asked: {msg}\n\nYou read: {read_url}\n"
                    f"Content:\n{page_content}\n\nAnswer naturally.",
                    provider, model, system_prompt, short_term, device_id
                )
                answer = followup or pre_read_clean or "I could not read that page."
            else:
                answer = pre_read_clean.strip() or "I could not access that page right now."

        final, action_trigger = extract_action_trigger(answer)
        final = _clean_for_route(final, route)

        short_term.append({"role": "user",     "content": msg})
        short_term.append({"role": "assistant", "content": final})
        trim_short_term(short_term)
        EXECUTOR.submit(update_long_term, msg, final, device_id)
        extract_facts(msg, device_id)

        def wrapped():
            chunks = list(_split_into_sentence_chunks(final))
            for chunk in (chunks or [final]):
                yield f"data: {chunk}\n\n"
            if action_trigger and action_trigger not in ("None", "null"):
                yield f"data: [ACTION:{action_trigger}]\n\n"
            yield "data: [DONE]\n\n"
        gen = wrapped()

    return Response(
        stream_with_context(gen),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",   # disable nginx buffering
            "Access-Control-Allow-Origin": "*",
        },
    )

# _normalize_label(), _get_knowledge(), merge_nodes() moved to
# memory/knowledge.py — imported near the top of this file.

@app.route("/research", methods=["POST"])
def research_endpoint():
    """
    Phase 6. POST {device_id, topic} -> searches, reads the top pages,
    summarizes, and stores extracted nodes into that device's running
    knowledge graph (same store /extract-knowledge and /search-knowledge
    already use). Read-and-write, unlike /extract-knowledge which is
    read-only against existing conversation — this one goes out and
    gathers new information.
    """
    data      = request.get_json(silent=True) or {}
    device_id = safe_device_id(str(data.get("device_id", "default"))[:100].strip() or "default")
    topic     = str(data.get("topic", "")).strip()[:300]

    if not topic:
        return jsonify({"topic": "", "summary": "", "sources": [], "nodes": [],
                        "note": "No topic provided."})

    result = run_research(topic, device_id)
    return jsonify(result)

@app.route("/extract-knowledge", methods=["POST"])
def extract_knowledge():
    """
    Phase 2 prototype. Pulls structured concept nodes out of a device's
    recent LIVE conversation (whatever is currently in short_term).

    This is a read-only test — nothing gets persisted here, intentionally.
    The point is to judge extraction quality by eye before any graph
    storage or canvas UI gets built on top of it. If this doesn't
    produce meaningful nodes on real conversations, nothing downstream
    is worth building yet.
    """
    data      = request.get_json(silent=True) or {}
    device_id = safe_device_id(str(data.get("device_id", "default"))[:100].strip() or "default")
    turns     = int(data.get("turns", 10))
    turns     = max(1, min(turns, 40))  # keep the prompt a sane size

    short_term = get_short_term(device_id)
    convo = short_term[1:]            # index 0 is always the system message
    convo = convo[-(turns * 2):]      # last N user+assistant exchanges

    if not convo:
        return jsonify({
            "nodes": [],
            "note": "No recent conversation found for this device_id."
        })

    transcript = "\n".join(
        f"{'User' if m.get('role') == 'user' else 'Gideon'}: {m.get('content', '')}"
        for m in convo if m.get("content")
    )

    prompt = (
        "Extract concept nodes from this conversation. A node is a "
        "meaningful topic, project, person, tool, or idea that was "
        "actually discussed, not every noun that appears. Merge obvious "
        "duplicates into one node. Return ONLY valid JSON, this exact shape:\n"
        '{"nodes": [{"id": "n1", "label": "short label", '
        '"category": "one word", "related_to": ["n2"]}]}\n'
        "Categories should be simple words like: project, person, tool, "
        "idea, task, place. related_to lists the ids of OTHER nodes in "
        "this same response that this node connects to — leave it empty "
        "if there's no clear connection. If nothing meaningful is present, "
        'return {"nodes": []}. No text outside the JSON.\n\n'
        f"Conversation:\n{transcript}"
    )

    raw = _call_groq_raw_extended(prompt)
    if not raw:
        return jsonify({"nodes": [], "note": "Extraction call failed."}), 200

    clean = raw.strip().replace("```json", "").replace("```", "").strip()
    s, e = clean.find("{"), clean.rfind("}") + 1
    if s < 0 or e <= 0:
        return jsonify({
            "nodes": [], "note": "Model did not return JSON.", "raw": raw[:300]
        })

    parsed = _safe_json_loads(clean[s:e])
    if not parsed or "nodes" not in parsed:
        return jsonify({
            "nodes": [], "note": "Could not parse extraction result.", "raw": raw[:300]
        })

    store = merge_nodes(device_id, parsed.get("nodes", []))

    return jsonify({
        "nodes": parsed.get("nodes", []),
        "total_nodes_stored": len(store),
    })

@app.route("/search-knowledge", methods=["POST"])
def search_knowledge():
    """
    Keyword search over this device's in-memory knowledge graph.
    Matches against label and category, returns each hit plus its
    directly linked nodes so a search result shows immediate context,
    not just an isolated fact.
    """
    data      = request.get_json(silent=True) or {}
    device_id = safe_device_id(str(data.get("device_id", "default"))[:100].strip() or "default")
    query     = str(data.get("query", "")).strip().lower()

    if not query:
        return jsonify({"results": [], "note": "Empty query."})

    store = _get_knowledge(device_id)
    matches = [
        nid for nid, n in store.items()
        if query in n["label"].lower() or query in n["category"].lower()
    ]

    results = []
    for nid in matches:
        n = store[nid]
        related = [
            {"id": rid, "label": store[rid]["label"], "category": store[rid]["category"]}
            for rid in n["related_to"] if rid in store
        ]
        results.append({
            "id": nid, "label": n["label"], "category": n["category"],
            "related": related,
        })

    return jsonify({"results": results, "total_nodes_stored": len(store)})

@app.route("/knowledge/<device_id>", methods=["GET"])
def view_knowledge(device_id):
    """Dumps the full in-memory graph for one device — for eyeballing
    whether extraction and linking actually make sense, not a client-
    facing endpoint."""
    device_id = safe_device_id(device_id)
    store = _get_knowledge(device_id)
    nodes = [
        {
            "id": nid, "label": n["label"], "category": n["category"],
            "related_to": sorted(n["related_to"]),
        }
        for nid, n in list(store.items())
    ]
    return jsonify({"nodes": nodes, "total": len(nodes)})

@app.route("/debug/keys", methods=["GET"])
def debug_keys():
    """
    Checks every provider API key from inside the running process,
    since sealing a Railway variable makes it write-only — the
    dashboard won't show it back to you, and neither will `railway
    variables`, but the app itself still has the real value in memory
    and can use it. This is the only place that's still true, so
    checking has to happen here rather than by pulling values out.

    Never returns the actual key values, only per-key status, same
    intent as check_keys.sh but runnable against sealed keys.

    Uses lightweight models-list endpoints where the provider has one,
    so checking doesn't itself burn into whatever quota you're trying
    to check. Note: this confirms a key AUTHENTICATES and isn't
    currently rate-limited, not remaining daily quota — a key can
    check out fine here and still hit a token-per-day cap on a real
    completion call, the same gap noted in check_keys.sh.
    """
    def check(label, key, url, params=None):
        if not key:
            return {"key": label, "status": "not set"}
        try:
            headers = {} if params else {"Authorization": f"Bearer {key}"}
            r = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code == 200:
                return {"key": label, "status": "active"}
            if r.status_code in (401, 403):
                return {"key": label, "status": "invalid or revoked", "http": r.status_code}
            if r.status_code == 429:
                return {"key": label, "status": "rate-limited right now", "http": 429}
            return {"key": label, "status": "unexpected response", "http": r.status_code}
        except requests.RequestException as e:
            return {"key": label, "status": "no response / network error", "error": str(e)[:120]}

    results = []
    for i, key in enumerate(GROQ_KEYS, start=1):
        results.append(check(f"Groq Key {i}", key,
                             "https://api.groq.com/openai/v1/models"))
    for i, key in enumerate(OPENROUTER_KEYS, start=1):
        results.append(check(f"OpenRouter Key {i}", key,
                             "https://openrouter.ai/api/v1/models"))
    for i, key in enumerate(MISTRAL_KEYS, start=1):
        results.append(check(f"Mistral Key {i}", key,
                             "https://api.mistral.ai/v1/models"))
    results.append(check("Cohere Key", COHERE_KEY,
                         "https://api.cohere.com/v1/models"))
    results.append(check("Cerebras Key", CEREBRAS_KEY,
                         "https://api.cerebras.ai/v1/models"))
    results.append(check("OpenAI Key", OPENAI_KEY,
                         "https://api.openai.com/v1/models"))
    results.append(check("Gemini Key", GEMINI_KEY,
                         "https://generativelanguage.googleapis.com/v1beta/models",
                         params={"key": GEMINI_KEY} if GEMINI_KEY else None))

    return jsonify({
        "results": results,
        "note": ("Checks auth + current rate-limit status only, not "
                 "remaining daily quota. OpenAI's /models can return "
                 "200 even with billing exhausted, since listing "
                 "models doesn't charge against quota the way "
                 "completions do.")
    })

@app.route("/debug/provider-usage", methods=["GET"])
def debug_provider_usage():
    """Shows current rolling usage per provider against its soft cap —
    the easiest way to confirm Phase 9's load spreading is actually
    doing anything, and to tune PROVIDER_SOFT_CAPS against your real
    limits once you've seen real traffic patterns."""
    result = {}
    for provider, cap in PROVIDER_SOFT_CAPS.items():
        count = _provider_usage_count(provider, cap["window_seconds"])
        result[provider] = {
            "used":        count,
            "cap":         cap["max_requests"],
            "near_cap":    count >= cap["max_requests"],
            "window_hours": cap["window_seconds"] // 3600,
        }
    return jsonify(result)

@app.route("/debug/devices", methods=["GET"])
def debug_devices():
    """
    Lists every device_id currently active in short-term memory, with a
    preview of their last exchange, so you can find your own device_id
    without digging through Android code or Railway logs. In-memory
    only, so this only shows devices that have talked to Gideon since
    the last restart.
    """
    devices = []
    # snapshot with list(...) before iterating — USER_SHORT_TERM gets
    # written to by every concurrent /run and /stream request, and
    # iterating a live dict while another thread inserts a new device
    # key raises "dictionary changed size during iteration" and 500s
    # this whole endpoint, which is exactly what was leaving the debug
    # page's device dropdown stuck on "Loading devices..." forever.
    for device_id, st in list(USER_SHORT_TERM.items()):
        convo = [m for m in list(st) if m.get("role") in ("user", "assistant")]
        if not convo:
            continue  # skip empty/phantom entries — nothing to extract from anyway
        last = convo[-1]["content"][:80]
        devices.append({
            "device_id": device_id,
            "exchanges": len(convo) // 2,
            "last_message": last,
        })
    return jsonify({"devices": devices})

@app.route("/debug/knowledge", methods=["GET"])
def debug_knowledge_page():
    """
    A self-contained debug page for the Phase 2/3 knowledge tools —
    no curl, no separate REST client app needed. Pick a device, run
    extraction, search, or view the full graph, all from a phone
    browser. Debug-only, not part of the actual product.
    """
    html = """
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gideon — Knowledge Debug</title>
  <style>
    body { font-family: sans-serif; background:#0d1117; color:#e6edf3; padding:16px; }
    h2 { color:#58a6ff; }
    select, input, button { width:100%; padding:10px; margin:6px 0; border-radius:6px;
      border:1px solid #30363d; background:#161b22; color:#e6edf3; box-sizing:border-box; }
    button { background:#238636; border:none; font-weight:bold; cursor:pointer; }
    button.secondary { background:#1f6feb; }
    pre { background:#161b22; padding:10px; border-radius:6px; overflow-x:auto;
      white-space:pre-wrap; word-break:break-word; font-size:13px; }
    .row { display:flex; gap:8px; }
    .row > * { flex:1; }
  </style>
</head>
<body>
  <h2>Gideon Knowledge Debug</h2>

  <label>Device</label>
  <select id="deviceSelect"><option>Loading devices...</option></select>
  <button class="secondary" onclick="loadDevices()">Refresh device list</button>

  <label>Turns to extract from</label>
  <input id="turns" type="number" value="10" min="1" max="40">
  <button onclick="extract()">Extract Knowledge</button>

  <label>Research topic (Phase 6 — searches + reads real pages, slower)</label>
  <input id="researchTopic" type="text" placeholder="e.g. lithium battery recycling in Nigeria">
  <button onclick="research()">Research This</button>

  <label>Search query</label>
  <input id="query" type="text" placeholder="e.g. voice">
  <div class="row">
    <button onclick="search()">Search</button>
    <button class="secondary" onclick="viewGraph()">View Full Graph</button>
  </div>

  <pre id="output">Results will appear here.</pre>
  <canvas id="graphCanvas" style="display:none; width:100%; height:400px; background:#161b22; border-radius:6px; margin-top:10px;"></canvas>

  <script>
    const out = document.getElementById('output');

    async function loadDevices() {
      out.textContent = "Loading...";
      const sel = document.getElementById('deviceSelect');
      try {
        const r = await fetch('/debug/devices');
        if (!r.ok) {
          throw new Error(`Server returned ${r.status}`);
        }
        const d = await r.json();
        sel.innerHTML = '';
        if (!d.devices.length) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = 'No active devices yet — talk to Gideon first';
          sel.appendChild(opt);
          out.textContent = "No devices have talked to Gideon since the last restart. Send it a message, then tap Refresh.";
          return;
        }
        d.devices.forEach(dev => {
          const opt = document.createElement('option');
          opt.value = dev.device_id;
          opt.textContent = `${dev.device_id}  (${dev.exchanges} exchanges — "${dev.last_message}")`;
          sel.appendChild(opt);
        });
        out.textContent = JSON.stringify(d, null, 2);
      } catch (err) {
        sel.innerHTML = '<option value="">Failed to load — tap Refresh to retry</option>';
        out.textContent = "Could not load devices: " + err.message + "\n\nCheck Railway logs for the actual error, or tap Refresh device list to try again.";
      }
    }

    function currentDevice() {
      const sel = document.getElementById('deviceSelect');
      return sel.value || null;
    }

    function requireDevice() {
      const id = currentDevice();
      if (!id) {
        out.textContent = "No real device selected. Talk to Gideon first, then tap Refresh device list, then pick your device from the dropdown.";
        return null;
      }
      return id;
    }

    async function extract() {
      const device_id = requireDevice();
      if (!device_id) return;
      document.getElementById('graphCanvas').style.display = 'none';
      out.textContent = "Extracting...";
      const turns = parseInt(document.getElementById('turns').value) || 10;
      try {
        const r = await fetch('/extract-knowledge', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({device_id, turns})
        });
        if (!r.ok) throw new Error(`Server returned ${r.status}`);
        out.textContent = JSON.stringify(await r.json(), null, 2);
      } catch (err) {
        out.textContent = "Extraction failed: " + err.message + "\n\nCheck Railway logs for details.";
      }
    }

    async function research() {
      const device_id = requireDevice();
      if (!device_id) return;
      const topic = document.getElementById('researchTopic').value.trim();
      if (!topic) {
        out.textContent = "Enter a research topic first.";
        return;
      }
      document.getElementById('graphCanvas').style.display = 'none';
      out.textContent = "Researching \"" + topic + "\" — searching, reading pages, summarizing. This can take 10-30 seconds...";
      try {
        const r = await fetch('/research', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({device_id, topic})
        });
        if (!r.ok) throw new Error(`Server returned ${r.status}`);
        out.textContent = JSON.stringify(await r.json(), null, 2);
      } catch (err) {
        out.textContent = "Research failed: " + err.message + "\n\nCheck Railway logs for details.";
      }
    }

    async function search() {
      const device_id = requireDevice();
      if (!device_id) return;
      document.getElementById('graphCanvas').style.display = 'none';
      out.textContent = "Searching...";
      const query = document.getElementById('query').value;
      try {
        const r = await fetch('/search-knowledge', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({device_id, query})
        });
        if (!r.ok) throw new Error(`Server returned ${r.status}`);
        out.textContent = JSON.stringify(await r.json(), null, 2);
      } catch (err) {
        out.textContent = "Search failed: " + err.message + "\n\nCheck Railway logs for details.";
      }
    }

    async function viewGraph() {
      const device_id = requireDevice();
      if (!device_id) return;
      out.textContent = "Loading graph...";
      try {
        const r = await fetch('/knowledge/' + encodeURIComponent(device_id));
        if (!r.ok) throw new Error(`Server returned ${r.status}`);
        const data = await r.json();
        out.textContent = JSON.stringify(data, null, 2);
        if (data.nodes && data.nodes.length) {
          drawGraph(data);
        } else {
          out.textContent += "\n\nNo nodes stored yet for this device. Run Extract Knowledge first.";
        }
      } catch (err) {
        out.textContent = "Could not load graph: " + err.message + "\n\nCheck Railway logs for details.";
      }
    }

    // Lightweight force-directed layout, drawn on canvas. No external
    // libraries — this is just a debug-page sanity check for whether
    // the extracted graph is worth ever building a real canvas UI for
    // (see roadmap Phase 10), not a component meant to ship in the app.
    function drawGraph(data) {
      const canvas = document.getElementById('graphCanvas');
      canvas.style.display = 'block';
      const ctx = canvas.getContext('2d');
      const W = canvas.width  = canvas.clientWidth;
      const H = canvas.height = 400;

      const nodes = data.nodes.map(n => ({
        id: n.id, label: n.label, category: n.category,
        x: Math.random() * W, y: Math.random() * H, vx: 0, vy: 0,
      }));
      const idIndex = {};
      nodes.forEach((n, i) => idIndex[n.id] = i);
      const edges = [];
      data.nodes.forEach(n => {
        (n.related_to || []).forEach(rid => {
          if (idIndex[rid] !== undefined) edges.push([idIndex[n.id], idIndex[rid]]);
        });
      });

      const palette = ['#58a6ff','#3fb950','#f0883e','#db61a2','#a371f7','#e3b341','#f85149'];
      const colors = {};
      let colorIdx = 0;
      function colorFor(cat) {
        if (!colors[cat]) { colors[cat] = palette[colorIdx % palette.length]; colorIdx++; }
        return colors[cat];
      }

      let frame = 0;
      function tick() {
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i], b = nodes[j];
            let dx = a.x - b.x, dy = a.y - b.y;
            let dist = Math.sqrt(dx*dx + dy*dy) || 1;
            const force = 1200 / (dist * dist);
            dx /= dist; dy /= dist;
            a.vx += dx * force; a.vy += dy * force;
            b.vx -= dx * force; b.vy -= dy * force;
          }
        }
        edges.forEach(([i, j]) => {
          const a = nodes[i], b = nodes[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let dist = Math.sqrt(dx*dx + dy*dy) || 1;
          const force = dist * 0.01;
          dx /= dist; dy /= dist;
          a.vx += dx * force; a.vy += dy * force;
          b.vx -= dx * force; b.vy -= dy * force;
        });
        nodes.forEach(n => {
          n.vx += (W / 2 - n.x) * 0.001;
          n.vy += (H / 2 - n.y) * 0.001;
          n.vx *= 0.85; n.vy *= 0.85;
          n.x += n.vx; n.y += n.vy;
          n.x = Math.max(20, Math.min(W - 20, n.x));
          n.y = Math.max(20, Math.min(H - 20, n.y));
        });

        ctx.clearRect(0, 0, W, H);
        ctx.strokeStyle = '#30363d';
        edges.forEach(([i, j]) => {
          ctx.beginPath();
          ctx.moveTo(nodes[i].x, nodes[i].y);
          ctx.lineTo(nodes[j].x, nodes[j].y);
          ctx.stroke();
        });
        nodes.forEach(n => {
          ctx.fillStyle = colorFor(n.category);
          ctx.beginPath();
          ctx.arc(n.x, n.y, 7, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = '#e6edf3';
          ctx.font = '11px sans-serif';
          ctx.fillText(n.label, n.x + 9, n.y + 4);
        });

        frame++;
        if (frame < 300) requestAnimationFrame(tick);
      }
      tick();
    }

    loadDevices();
  </script>
</body>
</html>
    """
    return Response(html, mimetype="text/html", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    })

@app.route("/tts", methods=["POST"])
def tts():
    data      = request.get_json(silent=True) or {}
    text      = data.get("text", "")
    voice     = data.get("voice", "onyx")
    device_id = safe_device_id(data.get("device_id", "default"))

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if is_rate_limited(device_id):
        return jsonify({"error": "Rate limited"}), 429

    audio, error = generate_tts_base64(text, voice)
    if not audio:
        return jsonify({"error": error or "TTS unavailable"}), 500
    return jsonify({"audio": audio, "format": "mp3"})


@app.route("/health", methods=["GET"])
def health():
    # Hardened: no longer leaks provider names or key counts.
    # Internal diagnostics moved to /health/internal which is not
    # meant to be public-facing — protect it at the Railway/proxy
    # level or remove before sharing the URL publicly.
    return jsonify({"status": "online", "bot": BOT_NAME, "version": "11.0"})


@app.route("/health/internal", methods=["GET"])
def health_internal():
    # Diagnostic endpoint — restrict access at the network level in
    # production (Railway private networking / IP allowlist), since
    # this does reveal configuration shape.
    auth = request.headers.get("X-Internal-Key", "")
    if auth != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({
        "status": "online", "bot": BOT_NAME, "version": "11.0",
        "groq_keys": sum(1 for k in GROQ_KEYS if k),
        "openrouter_keys": sum(1 for k in OPENROUTER_KEYS if k),
        "mistral_keys": sum(1 for k in MISTRAL_KEYS if k),
        "gemini": bool(GEMINI_KEY), "cohere": bool(COHERE_KEY),
        "cerebras": bool(CEREBRAS_KEY),
        "weather": bool(WEATHER_KEY), "news": bool(NEWS_KEY),
        "tts": bool(OPENAI_KEY),
        "brave_search": bool(BRAVE_SEARCH_KEY),  # legacy
        "web_search":   bool(SERPER_KEY),
        "firecrawl":    bool(FIRECRAWL_KEY),
        "cache_size": len(CACHE),
        "active_device_count": len(USER_SHORT_TERM),
    })


if __name__ == "__main__":
    print(f"{BOT_NAME} v11.0 online")
    app.run(host="0.0.0.0", port=PORT)
