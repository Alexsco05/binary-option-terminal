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
    """
    placeholders = []

    def _is_real_pair(content: str) -> bool:
        if re.search(r'\n\s*\d+\.\s', content):
            return False
        if content.count('\n\n') > 0:
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

    # single-$ inline math ($a$, $x$) is left as-is now — the client
    # renders it. Only genuinely leftover, unpaired $$ markers (never
    # matched to a confirmed real pair above) get removed, since those
    # can't render as anything on either side.
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
