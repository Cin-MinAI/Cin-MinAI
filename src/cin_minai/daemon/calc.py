# SPDX-License-Identifier: GPL-3.0-or-later
"""The calculator the guide calls (PLAN D68: knowledge from real tools, not the model's memory): arithmetic,
percentages, powers and roots, and equations solved for their unknown, exactly, with SymPy.

The expression is the model's text, so it is never evaluated as Python: it's parsed (Python's own parser, nothing run)
and only numbers, the letters a-z as unknowns, the operators and a short list of functions are turned into SymPy
objects; anything else is refused. Sizes are bounded (the text, powers, factorials), so a request can't hang the
assistant.

    calculate("15% of 240")        -> {"expression": "15% of 240", "result": "36"}
    calculate("3*x + 7 = 25")      -> {"expression": ..., "solve_for": "x", "solutions": ["6"]}
"""

from __future__ import annotations

import ast
import re

MAX_CHARS = 200
MAX_POWER = 1000
MAX_FACTORIAL = 500
DIGITS = 12

FUNCTIONS = ("sqrt", "cbrt", "root", "sin", "cos", "tan", "asin", "acos", "atan", "log", "ln", "exp", "abs", "floor",
             "ceiling", "factorial", "round")


class CalcError(ValueError):
    pass


def _prepare(text: str) -> str:
    """The way people write maths, in Python's syntax: 15% of 240, 3x, 2^8, ×, ÷, a dot or comma for the decimals."""
    s = text.strip().replace("×", "*").replace("÷", "/").replace("−", "-").replace("^", "**").replace("√", "sqrt")
    s = re.sub(r"(?<=\d),(?=\d{1,2}\b)", ".", s)            # 3,5 -> 3.5 (a decimal comma)
    s = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", s)            # 1,000,000 / 1 000 000 -> 1000000
    # "100 - 20%" is 80, as on every pocket calculator: a percentage added or taken off what comes before it
    s = re.sub(r"^(.+?)\s*([+-])\s*(\d+(?:\.\d+)?)\s*%\s*$", r"(\1)*(1\2\3/100)", s)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*(?:of|de|von|の)\s*", r"(\1/100)*", s, flags=re.I)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%(?!\s*[\d(a-z])", r"(\1/100)", s)
    s = re.sub(r"(?<=\d)\s*(?=[a-z(])", "*", s)              # 3x, 2(x+1) -> 3*x, 2*(x+1)
    s = re.sub(r"(?<=\))\s*(?=[\d(a-z])", "*", s)            # (x+1)(x-1) -> (x+1)*(x-1)
    return s


def _build(node, sp, names: set):
    """A SymPy object from a parsed node, or CalcError for anything outside the calculator's alphabet."""
    if isinstance(node, ast.Expression):
        return _build(node.body, sp, names)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return sp.Rational(str(node.value)) if isinstance(node.value, float) else sp.Integer(node.value)
    if isinstance(node, ast.Name):
        if node.id == "pi":
            return sp.pi
        if node.id == "e":
            return sp.E
        if re.fullmatch(r"[a-z]", node.id):
            names.add(node.id)
            return sp.Symbol(node.id)
        raise CalcError(f"unknown name {node.id!r}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _build(node.operand, sp, names)
        return v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp):
        a, b = _build(node.left, sp, names), _build(node.right, sp, names)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            if b == 0:
                raise CalcError("division by zero")
            return a / b
        if isinstance(node.op, ast.Pow):
            if b.is_number and abs(b) > MAX_POWER:
                raise CalcError("the power is too large")
            return a ** b
        if isinstance(node.op, ast.Mod):
            return sp.Mod(a, b)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
        args = [_build(a, sp, names) for a in node.args]
        f = node.func.id
        if f == "factorial" and (len(args) != 1 or not args[0].is_number or abs(args[0]) > MAX_FACTORIAL):
            raise CalcError("factorial of a number up to 500")
        if f == "round" and 1 <= len(args) <= 2 and all(a.is_number for a in args):
            return sp.Float(round(float(args[0]), int(args[1]) if len(args) == 2 else 0), DIGITS)
        fn = {"ln": sp.log, "abs": sp.Abs, "cbrt": sp.cbrt, "root": sp.root}.get(f) or getattr(sp, f)
        return fn(*args)
    raise CalcError("only numbers, x-style unknowns, + - * / ^ % and functions like sqrt, sin, log")


def _show(value, sp) -> str:
    """A result as people read it: an exact whole number or fraction as it is, otherwise a decimal to 12 digits."""
    value = sp.nsimplify(value) if value.is_Float and value == int(value) else value
    if value.is_Integer:
        return str(value)
    if value.is_Rational and value.q <= 1000:
        decimal = _decimal(value, sp)
        return decimal if len(decimal.split(".")[-1]) <= 6 else f"{value} ≈ {decimal}"
    if value.is_number and value.is_real:
        return _decimal(value, sp)
    if value.is_number:  # a complex number: 2 + 3i, as a maths book writes it
        return str(sp.nsimplify(value)).replace("*I", "i").replace("I", "i")
    return str(value)


def _decimal(value, sp) -> str:
    text = f"{float(sp.N(value, DIGITS + 3)):.{DIGITS}g}" if abs(value) >= 1e-6 else str(sp.N(value, DIGITS))
    return text.rstrip("0").rstrip(".") if "." in text and "e" not in text else text


def calculate(expression: str) -> dict:
    """The answer, or {"error"} saying what the calculator can't read; never raises for the person's input."""
    import sympy as sp
    shown = " ".join(str(expression).split())
    if not shown:
        return {"expression": "", "error": "there's nothing to calculate"}
    if len(shown) > MAX_CHARS:  # never cut: a shortened sum is a different sum
        return {"expression": shown[:MAX_CHARS] + "…", "error": f"too long for the calculator ({MAX_CHARS} characters)"}
    text = _prepare(shown)
    sides = text.split("=")
    if len(sides) > 2 or text.count("==") or len(text) > MAX_CHARS * 2:
        return {"expression": shown, "error": "one expression, or one equation with a single ="}
    names: set = set()
    try:
        parts = [_build(ast.parse(side.strip(), mode="eval"), sp, names) for side in sides]
    except (SyntaxError, CalcError, TypeError, ValueError, ZeroDivisionError) as e:
        return {"expression": shown, "error": str(e) if isinstance(e, CalcError) else "the calculator can't read it"}
    try:
        if len(parts) == 2:
            if not names:
                return {"expression": shown, "true": bool(sp.simplify(parts[0] - parts[1]) == 0)}
            unknown = sp.Symbol("x") if "x" in names else sp.Symbol(sorted(names)[0])
            solutions = sp.solve(sp.Eq(parts[0], parts[1]), unknown)
            return {"expression": shown, "solve_for": str(unknown),
                    "solutions": [_show(s, sp) for s in solutions[:6]] or [], **({} if solutions else
                                                                                 {"note": "no solution"})}
        value = sp.simplify(parts[0])
        if names:
            return {"expression": shown, "simplified": str(value)}
        if value is sp.zoo or value is sp.nan:
            return {"expression": shown, "error": "it has no value (a division by zero)"}
        return {"expression": shown, "result": _show(value, sp)}
    except (TypeError, ValueError, ZeroDivisionError, NotImplementedError, RecursionError, OverflowError):
        return {"expression": shown, "error": "the calculator couldn't work it out"}
