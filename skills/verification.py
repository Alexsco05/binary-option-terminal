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
