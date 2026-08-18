# ================================================================
# GIDEON — skills/mathematics.py
# ----------------------------------------------------------------
# Math notation handling, two separate jobs:
#
# 1. DISPLAY: latex_to_unicode() and strip_stray_inline_dollars()
#    convert LaTeX for the WebView/MathJax renderer and chat bubbles.
#
# 2. SPEECH: convert_math_for_speech() and its helpers convert the
#    same notation into natural spoken phrasing for TTS — a formula
#    like $$x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}$$ should SHOW as
#    symbols but be SPOKEN as "x equals negative b, plus or minus
#    the square root of b squared minus 4ac, all over 2a," the way
#    a teacher actually says it out loud.
#
# Moved from server.py with zero behavior change. Fully self-
# contained — no dependency on anything else in the project.
# ================================================================

import re

# ================================================================
# LATEX TO UNICODE (display)
# ================================================================
LATEX_MAP = [
    (r'\frac{d}{dx}', 'd/dx'), (r'\frac{1}{2}', '½'), (r'\frac{1}{x}', '1/x'),
    (r'\int', '∫'), (r'\sum', '∑'), (r'\lim_{', 'lim('), (r'\lim', 'lim'),
    (r'\sqrt', '√'), (r'\infty', '∞'), (r'\theta', 'θ'), (r'\alpha', 'α'),
    (r'\beta', 'β'), (r'\gamma', 'γ'), (r'\pi', 'π'), (r'\Delta', 'Δ'),
    (r'\delta', 'δ'), (r'\epsilon', 'ε'), (r'\lambda', 'λ'), (r'\mu', 'μ'),
    (r'\sigma', 'σ'), (r'\omega', 'ω'), (r'\times', '×'), (r'\div', '÷'),
    (r'\neq', '≠'), (r'\leq', '≤'), (r'\geq', '≥'), (r'\approx', '≈'),
    (r'\rightarrow', '→'), (r'\leftarrow', '←'), (r'\Rightarrow', '⇒'),
    (r'\pm', '±'), (r'^{2}', '²'), (r'^{3}', '³'), (r'^{n}', 'ⁿ'),
    (r'^2', '²'), (r'^3', '³'), (r'_{0}', '₀'), (r'_{1}', '₁'),
    (r'_{2}', '₂'), (r'_{n}', 'ₙ'), (r'\left(', '('), (r'\right)', ')'),
    (r'\cdot', '·'), (r'\ldots', '...'), (r'\to', '→'),
    (r'\nabla', '∇'), (r'\partial', '∂'),
]


def latex_to_unicode(text: str) -> str:
    for latex, uni in LATEX_MAP:
        text = text.replace(latex, uni)
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    return text


def normalize_math_delimiters(text: str) -> str:
    """
    Converts LaTeX's native inline/display delimiters — \\( ... \\) and
    \\[ ... \\] — into the $ ... $ / $$ ... $$ style the rest of this
    pipeline (strip_stray_inline_dollars) and the Android client's
    containsLatex() both already validate and render.

    Why this exists: the system prompt asks for $/$$ delimiters, and
    the model that used to run this route mostly complied. The current
    model (gpt-oss-120b) instead defaults to standard LaTeX \\( \\) and
    \\[ \\] notation regardless of what the prompt asks for. Without
    this normalization step, that content passes straight through
    every downstream check untouched — not rejected, just never
    recognized as math at all — and the client shows the raw LaTeX
    commands as literal text instead of rendering anything.

    Runs BEFORE strip_stray_inline_dollars, so its content-quality
    checks (balanced braces, no prose leakage, etc.) apply uniformly
    regardless of which delimiter style the model happened to use.

    The backslash immediately before the bracket/paren is the safe,
    unambiguous signal — ordinary prose never contains a literal
    backslash right before '(' or '[', so this never fires on a
    normal citation '[1]' or parenthetical '(see above)'.
    """
    text = re.sub(r'\\\[(.*?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    text = re.sub(r'\\\((.*?)\\\)', r'$\1$', text, flags=re.DOTALL)
    return text


def strip_stray_inline_dollars(text: str) -> str:
    """
    Leaves real $$ ... $$ display blocks and single-$ inline variables
    ($a$, $x$) both untouched — the Android client now renders both
    correctly (display blocks via the MathJax WebView, inline $x$ as
    italicized text). This function used to also unwrap single-$ pairs
    back to bare text, from back when the client only handled display
    blocks; that stripping is gone now that inline math has somewhere
    to go, but see below.

    What's still handled here: ORPHANED dollar markers — cases where
    the model wrote a closing $$ for one formula and the next
    formula's closing $$ ends up looking like its pair (e.g. a
    numbered list of formulas where each one is missing its own
    opening $$). A naive $$...$$ regex would incorrectly treat two
    unrelated orphaned markers as one valid block, so a real pair is
    only accepted if its content doesn't cross a numbered-list
    boundary or a paragraph break — those are the signals that two
    markers belong to different, unrelated formulas. Genuinely
    unpaired $$ markers left over after that check are removed, since
    a lone $$ with nothing to pair with can't render as anything
    sensible on either side.

    ALSO REJECTED: content that would actually break the client's
    MathJax WebView renderer rather than just looking odd. A raw '#'
    inside math mode is a reserved LaTeX macro-parameter character —
    MathJax throws 'You can't use macro parameter character #' and
    the whole block fails to render, visibly, as an error box in the
    chat. A markdown bullet marker ('- ') at the start of a line
    inside the block means the model wrote a list item INSIDE what
    was supposed to be pure math, which produces the same kind of
    broken render (English words with no spaces, since math mode
    ignores whitespace — 'from x=0 to x=4' renders as
    'fromx=0tox=4', not as readable text). Content that fails this
    check gets its $$ delimiters stripped and falls back to plain
    text instead of a broken WebView — a flat, readable fallback is
    strictly better than a visible rendering crash.
    ONE MORE CASE: prose crammed inside $$ with no markdown symbols at
    all, e.g. '$$y=\\sqrt{x} from x=0 to x=4 about the x-axis$$'. This
    doesn't trip the '#' or bullet checks above, but math mode still
    ignores whitespace, so it renders as 'fromx=0tox=4aboutthex-axis'
    — squished together, unreadable, no visible error but still
    broken. Caught by counting common English connector words ('from',
    'to', 'about', 'the', 'use', 'using', 'and', 'with', 'for', 'is',
    'are') that essentially never appear as legitimate short variable
    names in real math notation. Two or more is treated as prose that
    leaked into the block rather than actual mathematics.

    TWO MORE, added after a real report where the above still wasn't
    enough:

    1. An ENTIRE ordinary sentence with no math content at all —
       e.g. 'Here are a variety of calculus practice questions' — can
       still slip through if it only contains ONE prose-list word
       ('are', in that example). Rather than keep growing a word
       blacklist forever, this adds a positive requirement instead: a
       real math block MUST contain at least one actual math signal —
       a digit, a backslash command, or a math operator (= + - * / ^
       _). No signal at all means it's plainly not math, full stop,
       regardless of which words happen to appear in it. This is what
       actually caught the "entire sentence accidentally became a
       math block" case — mismatched $$ counts elsewhere in the reply
       paired an opening $$ with the wrong closing $$, sweeping up an
       unrelated sentence in between. The word-list checks above are
       still useful for content that DOES contain some real math
       mixed with prose (like the sqrt example) and so wouldn't be
       caught by "no math signal at all" alone.

    2. Unbalanced braces — '\\frac{a}{b' missing its closing brace,
       or similar. MathJax reports this as "Extra close brace or
       missing open brace" and fails the same visible way. A quick
       count of '{' vs '}' catches the common case (not a full parser,
       but genuine LaTeX from a model rarely nests unbalanced braces
       any other way in practice).
    """
    placeholders = []
    _PROSE_WORDS = re.compile(
        r'\b(from|to|about|the|use|using|and|with|for|is|are|then|when)\b',
        re.IGNORECASE,
    )
    _MATH_SIGNAL = re.compile(r'[\d\\=+\-*/^_]')

    def _is_real_pair(content: str) -> bool:
        if re.search(r'\n\s*\d+\.\s', content):
            return False
        if content.count('\n\n') > 0:
            return False
        if '#' in content:
            return False
        if re.search(r'(^|\n)\s*[-*]\s', content):
            return False
        if len(_PROSE_WORDS.findall(content)) >= 2:
            return False
        if not _MATH_SIGNAL.search(content):
            return False
        if content.count('{') != content.count('}'):
            return False
        return True

    def _protect_checked(match):
        content = match.group(1)
        if _is_real_pair(content):
            placeholders.append(match.group(0))
            return f"\x00BLOCK{len(placeholders) - 1}\x00"
        return match.group(0)

    def _protect(match):
        placeholders.append(match.group(0))
        return f"\x00BLOCK{len(placeholders) - 1}\x00"

    # protect only CONFIRMED real $$ ... $$ blocks
    protected = re.sub(r'\$\$(.*?)\$\$', _protect_checked, text, flags=re.DOTALL)
    protected = re.sub(r'\\\[.*?\\\]', _protect, protected, flags=re.DOTALL)

    # Single-$ inline math ($a$, $x$) mostly renders fine untouched, and
    # the full _is_real_pair checks above are too strict for it — a
    # legitimate short variable like $a$ has no digit/operator/backslash
    # and would incorrectly fail the "must contain a math signal" check
    # meant for full equations. But now that normalize_math_delimiters()
    # can produce single-$ spans from \( \), a genuinely malformed one
    # (bullet marker or heading leaking in, unbalanced braces) can slip
    # through unvalidated. This applies only the checks that are
    # unambiguous regardless of span length — a short real variable name
    # never starts with '#' or '- ', and never has unbalanced braces.
    def _is_safe_inline(content: str) -> bool:
        if '#' in content:
            return False
        if re.search(r'(^|\n)\s*[-*]\s', content):
            return False
        if content.count('{') != content.count('}'):
            return False
        return True

    def _validate_inline(match):
        content = match.group(1)
        if _is_safe_inline(content):
            return match.group(0)
        return content  # strip the $ delimiters, keep the text readable

    protected = re.sub(r'(?<!\$)\$([^\$\n]+)\$(?!\$)', _validate_inline, protected)

    # Only genuinely leftover, unpaired $$ markers (never matched to a
    # confirmed real pair above) get removed, since those can't render
    # as anything on either side.
    protected = re.sub(r'\${2,}', '', protected)

    # restore protected display blocks
    for i, block in enumerate(placeholders):
        protected = protected.replace(f"\x00BLOCK{i}\x00", block)

    return protected


# ================================================================
# MATH-TO-SPEECH CONVERSION
# ----------------------------------------------------------------
# Display text and spoken text are different jobs. A formula like
# $$x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}$$ should SHOW as symbols in
# the WebView, but should be SPOKEN as a full sentence — "x equals
# negative b, plus or minus the square root of b squared minus 4ac,
# all over 2a" — the way a teacher actually says it out loud. This
# converts LaTeX/math notation into natural spoken phrasing rather
# than reading punctuation marks literally.
# ================================================================
SPEECH_MATH_MAP = [
    # \frac{}{} and \sqrt{} are handled separately by _expand_nested_commands
    # (brace-aware, handles nesting) — not listed here since simple regex
    # patterns can't correctly match nested braces like \frac{-b}{\sqrt{x}}.
    (r'\\int', ' the integral of '),
    (r'\\sum', ' the sum of '),
    (r'\\lim', ' the limit of '),
    (r'\\infty', ' infinity '),
    (r'\\theta', ' theta '), (r'\\alpha', ' alpha '), (r'\\beta', ' beta '),
    (r'\\gamma', ' gamma '), (r'\\pi', ' pi '), (r'\\Delta', ' delta '),
    (r'\\delta', ' delta '), (r'\\epsilon', ' epsilon '),
    (r'\\lambda', ' lambda '), (r'\\mu', ' mu '), (r'\\sigma', ' sigma '),
    (r'\\omega', ' omega '),
    (r'\\times', ' times '), (r'\\div', ' divided by '),
    (r'\\cdot', ' times '),
    (r'\\neq', ' is not equal to '), (r'\\leq', ' is less than or equal to '),
    (r'\\geq', ' is greater than or equal to '),
    (r'\\approx', ' is approximately '),
    (r'\\rightarrow', ' leads to '), (r'\\to', ' leads to '),
    (r'\\Rightarrow', ' implies '),
    (r'\\pm', ' plus or minus '),
    (r'\\nabla', ' the gradient of '), (r'\\partial', ' the partial derivative of '),
    (r'\^\{2\}', ' squared'), (r'\^2', ' squared'),
    (r'\^\{3\}', ' cubed'), (r'\^3', ' cubed'),
    (r'\^\{n\}', ' to the power of n'),
    (r'_\{0\}', ' sub zero'), (r'_\{1\}', ' sub one'), (r'_\{2\}', ' sub two'),
    (r'_\{n\}', ' sub n'),
    (r'\\left\(', '('), (r'\\right\)', ')'),
    (r'\\ldots', ' and so on '),
    (r'(?<=[\d\)])\s*-\s*(?=[\d\(])', ' minus '),   # X-Y between numbers/parens, e.g. "4-4ac", "5 - 4(1)(6)"
    (r'(?<=[a-zA-Z])\s*-\s*(?=\d)', ' minus '),     # e.g. "squared-4ac" after ^2 already converted
    (r'(?<!\w)-(?=[a-zA-Z])', ' negative '),        # negative sign before a variable, e.g. "-b"
    (r'(?<!\w)-(?=\d)', ' negative '),              # negative sign before a digit, e.g. "-5"
    (r'=', ' equals '),
    (r'\+', ' plus '),
]


def _find_matching_brace(s: str, start: int) -> int:
    """Given s[start] == '{', returns the index of its matching '}'."""
    depth = 0
    for i in range(start, len(s)):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _expand_nested_commands(text: str) -> str:
    """
    Handles \\frac{a}{b} and \\sqrt{x} with proper brace matching so
    nested commands like \\frac{-b}{\\sqrt{x}} convert correctly instead
    of the naive regex failing on the inner braces.
    Runs repeatedly until no more matches are found (handles nesting).
    """
    changed = True
    while changed:
        changed = False

        # \frac{...}{...}
        idx = text.find('\\frac{')
        if idx != -1:
            brace1_start = idx + len('\\frac')
            brace1_end = _find_matching_brace(text, brace1_start)
            if brace1_end != -1 and brace1_end + 1 < len(text) and text[brace1_end + 1] == '{':
                brace2_start = brace1_end + 1
                brace2_end = _find_matching_brace(text, brace2_start)
                if brace2_end != -1:
                    numerator = text[brace1_start + 1:brace1_end]
                    denominator = text[brace2_start + 1:brace2_end]
                    replacement = f" {numerator.strip()} over {denominator.strip()} "
                    text = text[:idx] + replacement + text[brace2_end + 1:]
                    changed = True
                    continue

        # \sqrt{...}
        idx = text.find('\\sqrt{')
        if idx != -1:
            brace_start = idx + len('\\sqrt')
            brace_end = _find_matching_brace(text, brace_start)
            if brace_end != -1:
                inner = text[brace_start + 1:brace_end]
                replacement = f" the square root of {inner.strip()} "
                text = text[:idx] + replacement + text[brace_end + 1:]
                changed = True
                continue

    return text


def _convert_math_block_to_speech(math_text: str) -> str:
    """Converts the inner content of a $$ ... $$ block into a spoken
    sentence fragment."""
    t = _expand_nested_commands(math_text)
    for pattern, replacement in SPEECH_MATH_MAP:
        t = re.sub(pattern, replacement, t)
    # clean leftover backslash commands and braces that weren't matched
    t = re.sub(r'\\[a-zA-Z]+', '', t)
    t = t.replace('{', '').replace('}', '')
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def convert_math_for_speech(text: str) -> str:
    """
    Full pipeline: finds $$ ... $$ display blocks and \\[ ... \\] blocks
    and replaces them with spoken phrasing. Then unwraps any remaining
    inline $...$ wrapping. Then runs the existing symbol-level cleanup
    for anything left over (e.g. stray \\pm outside a block).
    """
    def _replace_display_block(match):
        inner = match.group(1)
        return " " + _convert_math_block_to_speech(inner) + " "

    converted = re.sub(r'\$\$(.*?)\$\$', _replace_display_block, text, flags=re.DOTALL)
    converted = re.sub(r'\\\[(.*?)\\\]', _replace_display_block, converted, flags=re.DOTALL)

    # unwrap any remaining inline $...$ (single variables/symbols in prose)
    converted = re.sub(r'\$([^\$\n]{1,80}?)\$', r'\1', converted)

    # run symbol-level cleanup for anything outside a block (stray \pm,
    # \frac, \sqrt etc that weren't inside $$ ... $$)
    converted = _expand_nested_commands(converted)
    for pattern, replacement in SPEECH_MATH_MAP:
        converted = re.sub(pattern, replacement, converted)
    converted = re.sub(r'\\[a-zA-Z]+', '', converted)

    converted = re.sub(r'\s+', ' ', converted).strip()
    return converted
