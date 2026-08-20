# ================================================================
# GIDEON — core/formatting.py
# ----------------------------------------------------------------
# A general safety net against reply formats that would break the
# Android client's renderer (renderFormattedText() in
# MainActivityUI.kt, shared by both chat mode and voice mode).
#
# That renderer works line by line and only recognizes a structural
# element (heading, numbered item, bullet) if it's the FIRST thing on
# its own line. If the model strings several of the same kind of item
# together in one paragraph instead of one per line — which system
# prompt instructions alone don't reliably prevent — everything after
# the first item just shows as literal trailing text instead of
# becoming a real heading/list/bullet. Two markers behave differently:
# bold (**) and code fences (```) work in PAIRS, so an odd count means
# one stray marker flips formatting for everything after it in the
# message, not just the one spot the model meant to touch.
#
# Every function here degrades gracefully: it either inserts the line
# break the client actually needs, or removes a marker that can't be
# paired safely. The message stays fully readable either way — the
# alternative (broken rendering reaching the phone) is worse than a
# slightly imperfect but readable fallback.
#
# Applies to ALL routes, not just math — this is a client-rendering
# concern, unrelated to which specialist produced the reply.
# ================================================================

import re


_BLOCK_START_PATTERNS = (
    re.compile(r'^#'),
    re.compile(r'^[-•*]\s'),
    re.compile(r'^\d+\.\s'),
    re.compile(r'^```'),
)


def _is_block_element_line(line: str) -> bool:
    """True if this line is a real block-level markdown element the
    client specifically recognizes and needs on its own line — a
    heading, bullet, numbered item, or code fence marker. Lines like
    this are never merged into surrounding paragraph text."""
    stripped = line.strip()
    return any(p.match(stripped) for p in _BLOCK_START_PATTERNS)


def unwrap_paragraphs(text: str) -> str:
    """
    Joins consecutive non-blank lines within the same paragraph into
    one continuous line, unless a line is a real block element
    (heading, bullet, numbered item, code fence) or part of a
    multi-line $$ ... $$ / \\[ ... \\] math block.

    This is standard markdown "soft wrap" behavior — a single newline
    inside a paragraph is supposed to be just a wrap point, equivalent
    to a space, not a real line break. But the client's renderer works
    line by line: anything that's the ONLY thing on its own line gets
    its own UI element. When the model puts a short inline math mention
    on its own line — "If\n$F'$\nis an antiderivative of\n$f$\non\n
    $[a,b]$\n, then..." instead of one flowing sentence — the client
    (correctly, given its own logic) treats each fragment as a separate
    block, rendering three isolated boxes instead of one readable
    sentence with inline math embedded. This repairs that shape before
    it ever reaches the client, regardless of which route produced it.

    Multi-line $$ blocks and code fences are tracked with a small state
    machine and passed through completely untouched — their internal
    line structure is deliberate (a derivation's steps, a code file's
    real formatting) and must never be collapsed.
    """
    lines = text.split('\n')
    result, buffer = [], []
    in_math_block = False
    in_code_block = False

    def flush():
        if buffer:
            result.append(' '.join(buffer))
            buffer.clear()

    for line in lines:
        stripped = line.strip()

        if in_math_block:
            result.append(line)
            if stripped in ('$$', '\\]'):
                in_math_block = False
            continue

        if in_code_block:
            result.append(line)
            if stripped.startswith('```'):
                in_code_block = False
            continue

        if stripped in ('$$', '\\['):
            flush()
            result.append(line)
            in_math_block = True
            continue

        if stripped.startswith('```'):
            flush()
            result.append(line)
            in_code_block = True
            continue

        if not stripped:
            flush()
            result.append('')
            continue

        if _is_block_element_line(line):
            flush()
            result.append(line)
            continue

        buffer.append(stripped)

    flush()
    return '\n'.join(result)


_ISOLATED_SHORT_MATH = re.compile(r'^\$[^\$\n]{1,30}\$$')


def merge_isolated_math_paragraphs(text: str) -> str:
    """
    unwrap_paragraphs only merges fragments within the SAME paragraph
    (no blank line between them). But the model sometimes puts a short
    single-$ math mention — '$[a,b]$', '$C$' — in its OWN paragraph,
    correctly surrounded by blank lines the way the system prompt asks
    full $$ equations to be formatted, but never intended for
    something this short. There's nothing else in that paragraph to
    merge it with, so unwrap_paragraphs can't touch it — it stays
    isolated, and the client still gives it its own standalone box for
    the same reason described there.

    This looks at the paragraph level instead: a "paragraph" that is
    NOTHING BUT a short $...$ span gets merged into whichever
    neighboring paragraph actually continues the sentence it belongs
    to. The signal used: if the paragraph right after the isolated
    math starts with a lowercase letter, that's a strong sign it's
    the back half of a sentence the isolated math started ("$C$" then
    "is an arbitrary constant...") — merging backward instead would
    bolt it onto whatever unrelated heading or bullet came before,
    while leaving the real continuation as an orphaned fragment with
    no subject. Otherwise this merges backward into the previous
    paragraph — the more common case (some intro text, then a short
    aside like "$[a,b]$" that belongs at the end of that sentence).

    Only single-$ spans are ever touched — a real $$ block is SUPPOSED
    to stand alone with blank lines around it, and this must never
    merge one of those into surrounding prose.
    """
    paragraphs = text.split('\n\n')
    n = len(paragraphs)
    keep = [True] * n

    for i, para in enumerate(paragraphs):
        stripped = para.strip()
        if not _ISOLATED_SHORT_MATH.match(stripped):
            continue

        next_para = paragraphs[i + 1].lstrip() if i + 1 < n else ""
        next_continues = bool(next_para) and next_para[0].islower()

        if next_continues:
            paragraphs[i + 1] = stripped + " " + paragraphs[i + 1].lstrip()
            keep[i] = False
        elif i > 0 and keep[i - 1]:
            # find the nearest preceding paragraph that's still standing
            j = i - 1
            while j > 0 and not keep[j]:
                j -= 1
            paragraphs[j] = paragraphs[j].rstrip() + " " + stripped
            keep[i] = False
        elif i + 1 < n:
            # no usable previous paragraph -- merge forward regardless
            paragraphs[i + 1] = stripped + " " + paragraphs[i + 1].lstrip()
            keep[i] = False

    return '\n\n'.join(p for p, k in zip(paragraphs, keep) if k)


def _fix_broken_inline_bullets(text: str) -> str:
    """
    The model strings bullet items together inline using ' - ' as a
    plain-text separator instead of putting each item on its own line
    — e.g. "I can help with - **Calendar** - **Reminders** -
    **Files**" as one run-on sentence. The client only recognizes a
    bullet if the line starts with '- ' or '- ', so everything after
    the first dash just shows as literal text.

    Deliberately narrow trigger: only fires when the shape ' - **'
    (space, dash, space, then a bold marker — the start of a bolded
    list item) appears 2 or more times in the same reply. That
    specific, repeated shape is a strong signal of a broken pseudo-
    list. A single dash in ordinary prose ("well-known", "state-of-
    the-art") never matches — there's no surrounding whitespace-dash-
    whitespace-then-bold pattern in normal writing.
    """
    matches = list(re.finditer(r'\s-\s(?=\*\*)', text))
    if len(matches) < 2:
        return text

    result, last_end, first = [], 0, True
    for m in matches:
        result.append(text[last_end:m.start()])
        result.append("\n\n- " if first else "\n- ")
        first = False
        last_end = m.end()
    result.append(text[last_end:])
    return "".join(result)


_NUM_ITEM = re.compile(r'(?<!\d)(\d+)\.\s')


def _fix_broken_inline_numbered_lists(text: str) -> str:
    """
    Same failure class as bullets, for numbered lists: '1. First step
    2. Second step 3. Third step' crammed onto one line instead of
    each item starting its own line. The client only recognizes a
    numbered item if the trimmed line STARTS with '<digits>.', so
    everything after item 1 in a crammed run just shows as literal
    trailing text on that line.

    Trigger is deliberately conservative but not overly strict: acts
    when the numbers found are STRICTLY INCREASING (each one greater
    than the last), not necessarily consecutive. A real reply answering
    a subset of a larger problem set often skips numbers — "6. ... 9.
    ... 10. ... 15." is a completely normal numbered list, not a
    sequence starting at 1. Requiring exact consecutiveness missed this
    real case entirely. Strictly increasing (rather than any order) is
    still what makes this safe against false positives — ordinary prose
    essentially never contains 2+ 'N. ' patterns in increasing order by
    coincidence, and even if it rarely did, the cost of a wrongly
    inserted line break is far lower than a squished, unreadable list.
    """
    matches = list(_NUM_ITEM.finditer(text))
    if len(matches) < 2:
        return text

    nums = [int(m.group(1)) for m in matches]
    if not all(nums[i + 1] > nums[i] for i in range(len(nums) - 1)):
        return text

    result, last_end = [], 0
    for idx, m in enumerate(matches):
        result.append(text[last_end:m.start()])
        already_at_line_start = text[:m.start()].rstrip(' ').endswith('\n') or m.start() == 0
        if idx > 0 and not already_at_line_start:
            result.append("\n\n" if idx == 1 else "\n")
        last_end = m.start()
    result.append(text[last_end:])
    return "".join(result)


_HEADING = re.compile(r'(?<!\A)(?<!\n)(#{2,3}\s)')


def _fix_inline_headings(text: str) -> str:
    """
    '## Heading' or '### Subheading' only renders as a real heading if
    it starts its own line — the client checks trimmed.startsWith("##
    ") on each line independently. If the model writes a heading mid-
    paragraph ('...as follows: ## Next Steps'), it shows as the
    literal text '## Next Steps' instead of becoming a styled heading.
    This inserts the missing line break before any ## or ### that
    isn't already at the start of a line.

    Doesn't touch a heading-shaped line that's already on its own
    line (including one inside a fenced code block, like a Python
    comment '## TODO') — the negative lookbehind only matches when
    the marker is NOT already preceded by a newline or the start of
    the string, so genuine existing structure is left alone.
    """
    return _HEADING.sub(r'\n\n\1', text)


def _fix_unpaired_bold(text: str) -> str:
    """
    ** markers work in pairs to toggle bold on/off. An odd count means
    one stray ** flips bold state for everything after it in the
    message — not just the one word the model meant to emphasize.
    Strips the LAST unpaired occurrence, since that's the one most
    likely to be the accidental extra (a genuinely intended bold
    phrase almost always has its closing ** nearby; an odd one left
    dangling at the end of a long reply is the common failure shape).
    """
    if text.count('**') % 2 != 0:
        idx = text.rfind('**')
        if idx != -1:
            text = text[:idx] + text[idx + 2:]
    return text


def _fix_unpaired_code_fence(text: str) -> str:
    """
    ``` fences also work in pairs. An odd count means the model opened
    a code block and never closed it — the client's fence collector
    runs to the end of the message treating everything after the
    opening fence as code, swallowing any real prose that was meant
    to follow. Appends a closing fence so nothing gets silently eaten.
    """
    if text.count('```') % 2 != 0:
        text = text + '\n```'
    return text


def sanitize_formatting(text: str) -> str:
    """
    Runs every rendering safety net above, in order. Call this once,
    early, on any reply before it goes to the client — applies to
    every route, not just math, since this is purely about what the
    Android renderer needs, unrelated to which specialist produced
    the text.
    """
    text = unwrap_paragraphs(text)
    text = merge_isolated_math_paragraphs(text)
    text = _fix_broken_inline_bullets(text)
    text = _fix_broken_inline_numbered_lists(text)
    text = _fix_inline_headings(text)
    text = _fix_unpaired_bold(text)
    text = _fix_unpaired_code_fence(text)
    return text
