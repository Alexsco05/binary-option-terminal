# ================================================================
# GIDEON — core/agent.py
# ----------------------------------------------------------------
# The agent core: everything that decides HOW a message gets
# answered, as opposed to WHAT answers it (that's integrations/ and
# skills/). Four pieces, in the order a message actually flows
# through them:
#
# 1. resolve_immediate_reply() — the fast-path shortcuts (pending
#    confirmation, cache, intent, offline command) that skip full AI
#    routing entirely when possible.
# 2. process_multi_step() / plan_steps() / _looks_multi_part() — the
#    planner for requests that genuinely have more than one part.
# 3. process() — the main single-shot path: route, call a provider,
#    resolve any [SEARCH:]/[READ:] tags, clean, save, return.
# 4. _stream_groq() — the SSE streaming version of the same logic,
#    used by /stream for voice sessions.
#
# Plus two small shared helpers used by both the streaming and
# non-streaming paths: _split_into_sentence_chunks() and
# _clean_for_route().
#
# Moved from server.py with zero behavior change.
# ================================================================

import re
import json
import requests

from config.environment import GROQ_KEYS
from config.settings import MODELS

from core.router import (
    record_provider_usage, select_primary, route_model, call_provider,
)
from core.permissions import sanitize_action
from core.text import _safe_json_loads
from core.tags import extract_action_trigger, extract_search_trigger, extract_read_trigger
from core.intent import detect_user_intent, check_user_confirmation, build_intent_response
from core.prompts import build_system_prompt

from memory.conversation import CACHE, EXECUTOR, get_short_term, trim_short_term
from memory.personality import load_personality, update_long_term, extract_facts

from device.android import detect_offline_command, build_action_trigger

from skills.mathematics import latex_to_unicode, strip_stray_inline_dollars
from core.skills import get_skill

from integrations.web import (
    web_search, firecrawl_read, get_weather, get_news, extract_city_from_weather_query,
)
from integrations.providers import _call_groq, _call_groq_raw_extended


# ================================================================
# MAIN PROCESS — SHORTCUT PATH
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
        answer = _call_groq(msg, "openai/gpt-oss-120b", system_prompt, short_term)
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


# ================================================================
# MULTI-STEP PLANNER
# ================================================================

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


# ================================================================
# MAIN PROCESS — single-shot path (typed chat, /run)
# ================================================================

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
                             "openai/gpt-oss-120b", system_prompt, short_term)
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
                             "openai/gpt-oss-120b", system_prompt, short_term)
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
        # llama-3.1-70b-versatile and mixtral-8x7b-32768 were already
        # deprecated by Groq before this list was last touched — this
        # was quietly failing on every one of these three except the
        # first even before the Aug 16 2026 llama-3.3 decommission.
        # Replaced with the two currently-live GPT-OSS sizes.
        for m in ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
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

    # Real, independent verification — not the model grading its own
    # work. Pulled from whatever skill is registered for THIS route
    # (see core/skills.py), not hardcoded to math — any skill that
    # registers a verify function gets checked here automatically, no
    # edit needed in this file. Right now only "math" has declared one,
    # but this line doesn't know or care which skill that is.
    # Only speaks up on a genuine, confident mismatch. Silent when the
    # skill has no verifier, or the verifier has no opinion on this
    # particular message (word problems, algebra, etc.) — a missed
    # check is much cheaper than a false correction.
    skill = get_skill(route)
    if skill and skill.verify:
        check = skill.verify(msg, clean)
        if check.get("attempted") and check.get("verified") is False:
            print(f"[Verification] Mismatch on '{msg[:60]}': {check['note']}")
            clean += (
                f"\n\n*(Double-checking that arithmetic independently, "
                f"I get {check['expected']:g} — worth a second look.)*"
            )

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
# PHASE 1 — STREAMING GROQ (SSE, used by /stream for voice sessions)
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
