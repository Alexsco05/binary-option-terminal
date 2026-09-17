# ================================================================
# GIDEON — skills/verification.py
# ----------------------------------------------------------------
# Real, independent verification for the math route — as opposed to
# the current system prompt instruction telling the model to "verify
# your own answer," which is the model grading its own homework.
#
# Scope, deliberately conservative for this first version: only
# handles genuine arithmetic expressions (numbers + operators the
# user actually typed, e.g. "what's 45 * 12 + 3"), not word problems,
# algebra, or symbolic math — those need a real CAS (sympy) to verify
# properly, which is a bigger dependency to add later. This version
# catches the most common and most embarrassing failure mode: the
# model just getting arithmetic wrong.
#
# SECURITY: never uses eval() or exec() on user input. Parses the
# expression into a restricted AST and only allows numeric literals
# plus a fixed set of safe operators/functions. Anything else in the
# expression (function calls, attribute access, names) is rejected
# before any computation happens.
# ================================================================

import ast
import operator
import re

# Only these node types and operators are ever evaluated. Anything
# else (Call, Name, Attribute, Subscript, comprehensions, etc.)
# raises before it can do anything.
_ALLOWED_BINOPS = {
    ast.Add:  operator.add,
    ast.Sub:  operator.sub,
    ast.Mult: operator.mul,
    ast.Div:  operator.truediv,
    ast.Mod:  operator.mod,
    ast.Pow:  operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class UnsafeExpressionError(Exception):
    pass


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise UnsafeExpressionError(f"non-numeric constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op_func = _ALLOWED_BINOPS.get(type(node.op))
        if op_func is None:
            raise UnsafeExpressionError(f"disallowed operator: {type(node.op).__name__}")
        left  = _eval_node(node.left)
        right = _eval_node(node.right)
        try:
            return op_func(left, right)
        except ZeroDivisionError:
            raise UnsafeExpressionError("division by zero")
    if isinstance(node, ast.UnaryOp):
        op_func = _ALLOWED_UNARYOPS.get(type(node.op))
        if op_func is None:
            raise UnsafeExpressionError(f"disallowed unary operator: {type(node.op).__name__}")
        return op_func(_eval_node(node.operand))
    raise UnsafeExpressionError(f"disallowed expression element: {type(node).__name__}")


def safe_eval(expr: str):
    """
    Evaluates a restricted arithmetic expression (+, -, *, /, //, %, **,
    parentheses, unary +/-) and returns a float, or None if the
    expression is empty, malformed, or contains anything outside that
    restricted set. Never uses eval()/exec() — parses to an AST and
    walks it manually, rejecting anything that isn't a plain number or
    an allowed operator.
    """
    if not expr or not expr.strip():
        return None
    try:
        tree = ast.parse(expr, mode="eval")
        result = _eval_node(tree)
        return float(result)
    except (UnsafeExpressionError, SyntaxError, ValueError, TypeError, OverflowError):
        return None


# Matches a contiguous run of digits, whitespace, and arithmetic
# operators/parentheses — deliberately narrow. Words like "what is"
# or "solve" around it are just not part of the match. This will
# miss anything phrased as a word problem, which is correct: this
# verifier should stay silent rather than guess on ambiguous input.
_EXPR_PATTERN = re.compile(r'[\d\s\.\+\-\*/%\(\)]{3,}')


def extract_math_expression(msg: str):
    """
    Pulls the longest plausible arithmetic expression out of a user
    message. Returns None if nothing that looks like real arithmetic
    is found, or if what's found doesn't actually contain an operator
    (a bare number isn't a question). Conservative on purpose — a
    missed verification opportunity is much cheaper than a false
    correction on a word problem this wasn't meant to touch.
    """
    candidates = _EXPR_PATTERN.findall(msg)
    if not candidates:
        return None
    best = max(candidates, key=len).strip()
    if not best or not re.search(r'[\+\-\*/%]', best):
        return None
    # trailing/leading operators mean the regex grabbed a partial
    # match (e.g. a phone number or list index) — bail rather than
    # guess what the user meant
    if best[0] in '+-*/%' or best[-1] in '+-*/%':
        return None
    return best


def _extract_final_number(text: str):
    """
    Pulls the last standalone number out of a model's reply — the
    de facto "final answer" position in almost every math explanation
    style the system prompt asks for. Deliberately picks the LAST
    number, not the first, since worked solutions mention plenty of
    intermediate numbers before the answer.
    """
    numbers = re.findall(r'-?\d+\.?\d*', text)
    if not numbers:
        return None
    try:
        return float(numbers[-1])
    except ValueError:
        return None


def verify_math_reply(user_msg: str, model_reply: str, tolerance: float = 0.01):
    """
    Attempts to independently verify a math reply against a
    computable expression pulled from the user's own message.

    Returns a dict:
      {"attempted": bool, "verified": bool|None, "expected": float|None,
       "found": float|None, "note": str|None}

    attempted=False means this message didn't contain anything this
    verifier could check (word problem, algebra, no clear expression)
    — the caller should treat that as "no opinion," not "wrong."
    """
    expr = extract_math_expression(user_msg)
    if expr is None:
        return {"attempted": False, "verified": None,
                "expected": None, "found": None, "note": None}

    expected = safe_eval(expr)
    if expected is None:
        return {"attempted": False, "verified": None,
                "expected": None, "found": None, "note": None}

    found = _extract_final_number(model_reply)
    if found is None:
        return {"attempted": True, "verified": None,
                "expected": expected, "found": None,
                "note": "Could not find a numeric answer in the reply to check."}

    verified = abs(expected - found) <= tolerance
    note = None
    if not verified:
        note = (f"Independent check computed {expected:g} for '{expr.strip()}', "
                f"but the reply's final number was {found:g}.")

    return {"attempted": True, "verified": verified,
            "expected": expected, "found": found, "note": note}


# ================================================================
# SYMBOLIC VERIFICATION (sympy) — derivatives
# ----------------------------------------------------------------
# The arithmetic checker above is deliberately scoped to plain numeric
# expressions — it says so in the module docstring: calculus needs a
# real CAS. This is that CAS, added now, kept separate from the
# arithmetic path above rather than merged into it — arithmetic stays
# fast and dependency-free for the common case, sympy only loads for
# what actually needs it.
#
# Scoped tightly to derivatives for this first pass, same conservative
# philosophy as everything above: silence (attempted=False) beats a
# wrong guess on a pattern this doesn't confidently recognize.
# Integrals, limits, and equation-solving are natural next additions
# using the same shape, not built yet.
#
# SECURITY — read this before touching anything below.
# sympy.parsing.sympy_parser.parse_expr DOES use eval() internally —
# confirmed directly against sympy's own docstring ("this function
# uses eval, and thus shouldn't be used on unsanitized input") and by
# testing it: a plain empty global_dict is NOT enough. Passing
# global_dict={} still let a real os.system() call execute, because
# Python's eval() silently re-injects real builtins into any
# namespace dict that doesn't already contain the key "__builtins__".
# And even with "__builtins__": {} added to block that, a classic
# Python sandbox-escape gadget chain — ().__class__.__bases__[0] — was
# confirmed working directly against this parser, since restricting
# globals alone doesn't stop pure attribute-access syntax that needs
# no builtin at all.
#
# So this uses TWO independent layers, not one:
#  1. _is_safe_math_string() — a strict character/pattern whitelist
#     BEFORE the string ever reaches parse_expr. Rejects "__" (blocks
#     every dunder-based gadget chain), "[" / "]" (blocks subscript/
#     indexing, never needed for a calculus expression), and any "."
#     that isn't a decimal point between two digits (blocks attribute
#     access while still allowing "3.5"). What survives is restricted
#     to letters/digits/+-*/^().,space only.
#  2. A restricted global_dict (still no bare Python builtins) as a
#     second layer, in case something to do with sympy's OWN token
#     transformations ever introduces a path the whitelist didn't
#     anticipate — defense in depth, not "the whitelist alone is
#     trusted to be perfect forever."
# ================================================================

import sympy
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations, implicit_multiplication_application,
)

_SYMPY_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)
_X = sympy.Symbol("x")

# Layer 2: everything a derivative answer legitimately needs, and
# NOTHING else — no builtins, no import machinery.
_SAFE_SYMPY_GLOBALS = {
    "Symbol": sympy.Symbol, "Integer": sympy.Integer, "Float": sympy.Float,
    "Rational": sympy.Rational, "pi": sympy.pi, "E": sympy.E, "I": sympy.I,
    "oo": sympy.oo, "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan,
    "exp": sympy.exp, "log": sympy.log, "sqrt": sympy.sqrt,
    "Abs": sympy.Abs, "factorial": sympy.factorial,
    "__builtins__": {},
}

# Layer 1: the actual gate. Confirmed to block every gadget-chain
# variant tested (dunder attribute access, subscript indexing) while
# passing every legitimate calculus expression tested (polynomials,
# trig, decimals, parentheses).
_UNSAFE_CHAR_PATTERN = re.compile(r'[a-zA-Z0-9+\-*/^().,\s]*')


def _is_safe_math_string(s: str) -> bool:
    if not s or '__' in s or '[' in s or ']' in s:
        return False
    if re.search(r'\.(?!\d)|(?<!\d)\.', s):
        return False
    return bool(_UNSAFE_CHAR_PATTERN.fullmatch(s))


def _latex_to_sympy_syntax(text: str) -> str:
    """
    Narrow LaTeX -> sympy-parseable string converter, scoped only to
    what a calculus ANSWER typically looks like (polynomials, trig,
    exp, simple fractions) — not a general LaTeX parser. sympy's own
    parse_latex() needs the antlr4 runtime pinned to a specific old
    version (confirmed: current antlr4-python3-runtime on PyPI is
    already incompatible with it) — exactly the kind of fragile
    dependency chain not worth adding just for this.
    """
    t = text
    t = t.replace('\\left(', '(').replace('\\right)', ')')
    t = t.replace('\\cdot', '*').replace('\\times', '*')
    t = re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}', r'(\1)/(\2)', t)
    for fn in ['sin', 'cos', 'tan', 'exp', 'log', 'ln', 'sqrt']:
        t = t.replace(f'\\{fn}', fn)
    t = t.replace('\\pi', 'pi')
    t = t.replace('^', '**')
    t = re.sub(r'\s+', '', t)
    return t


def _sympy_safe_parse(expr_str: str):
    """Parses into a sympy expression, gated by the two layers
    documented above. Returns None — same as any other rejection in
    this file — for anything that fails the whitelist, not an
    exception, so a hostile string degrades to "unverified" exactly
    like a genuinely unparseable one does."""
    if not expr_str or not _is_safe_math_string(expr_str):
        return None
    try:
        return parse_expr(expr_str, transformations=_SYMPY_TRANSFORMATIONS,
                          local_dict={"x": _X}, global_dict=_SAFE_SYMPY_GLOBALS)
    except Exception:
        return None


_DERIVATIVE_PATTERN = re.compile(
    r'(?:derivative of|differentiate|d/dx(?:\s*of)?)\s+([^,.\n?]+)',
    re.IGNORECASE,
)


def extract_derivative_problem(msg: str):
    """Pulls a differentiable expression out of a user message, only
    for clearly-phrased requests ('derivative of x^2', 'differentiate
    sin(x)', 'd/dx of 3x^2'). Returns None for anything else — a word
    problem or an ambiguous phrasing stays unverified rather than
    guessed at."""
    m = _DERIVATIVE_PATTERN.search(msg)
    if not m:
        return None
    raw = m.group(1).strip().rstrip('.').rstrip('?').strip()
    return raw or None


def _extract_final_expression(reply: str):
    """
    Pulls the model's claimed final answer out of its reply — the
    last $$ ... $$ display block if one exists (the math pipeline's
    own convention, see skills/mathematics.py), otherwise the last
    inline $...$ span. Mirrors _extract_final_number's "last one is
    the answer" philosophy for worked solutions that show intermediate
    steps first.
    """
    blocks = re.findall(r'\$\$(.*?)\$\$', reply, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    inline = re.findall(r'(?<!\$)\$([^\$\n]+)\$(?!\$)', reply)
    if inline:
        return inline[-1].strip()
    return None


def verify_derivative_reply(user_msg: str, model_reply: str):
    """
    Same return shape as verify_math_reply, for symbolic calculus:
    {attempted, verified, expected, found, note}. expected/found are
    stringified sympy expressions here, not floats. attempted=False
    for anything this can't confidently parse — this should never
    produce a false "wrong" on a problem it merely misunderstood.
    """
    problem = extract_derivative_problem(user_msg)
    if not problem:
        return {"attempted": False, "verified": None,
                "expected": None, "found": None, "note": None}

    expr = _sympy_safe_parse(_latex_to_sympy_syntax(problem))
    if expr is None:
        return {"attempted": False, "verified": None,
                "expected": None, "found": None, "note": None}

    try:
        expected = sympy.simplify(sympy.diff(expr, _X))
    except Exception:
        return {"attempted": False, "verified": None,
                "expected": None, "found": None, "note": None}

    found_raw = _extract_final_expression(model_reply)
    if found_raw is None:
        return {"attempted": True, "verified": None,
                "expected": str(expected), "found": None,
                "note": "Could not find a clear final expression in the reply to check."}

    found_expr = _sympy_safe_parse(_latex_to_sympy_syntax(found_raw))
    if found_expr is None:
        return {"attempted": True, "verified": None,
                "expected": str(expected), "found": found_raw,
                "note": "Could not parse the reply's claimed answer to verify it."}

    try:
        verified = sympy.simplify(expected - found_expr) == 0
    except Exception:
        verified = None

    note = None
    if verified is False:
        note = (f"Independent check computed d/dx = {expected}, "
                f"but the reply's final expression was {found_raw}.")

    return {"attempted": True, "verified": verified,
            "expected": str(expected), "found": found_raw, "note": note}


def verify_math_or_calculus_reply(user_msg: str, model_reply: str):
    """
    Combined entry point registered on the math Skill (core/skills.py)
    — tries the derivative checker first (more specific pattern, less
    likely to false-match), falls back to the arithmetic checker.
    Same {attempted, verified, expected, found, note} shape either
    way, so the caller (core/agent.py) doesn't need to know or care
    which one actually fired.
    """
    calc_result = verify_derivative_reply(user_msg, model_reply)
    if calc_result["attempted"]:
        return calc_result
    return verify_math_reply(user_msg, model_reply)
