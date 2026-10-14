# PART 4: PRACTICE AIs (hand-written, so you can SEE the scorer catching cheaters)
# One honest solver and three cheaters. They are not real AIs.
# Run this file alone:  python p4_practice.py
import re
from p3_runner import pressure_test

CODE = {
    "sum of the digits": "def f(n):\n    return sum(int(c) for c in str(n))",
    "largest number": "def f(xs):\n    return max(xs)",
    "how many vowels": "def f(s):\n    return sum(c in 'aeiou' for c in s)",
}


def good(q):                                  # honest: really computes everything
    m = re.search(r"x\+(\d+)=x\+(\d+)", q)
    if m:
        return {"answer": "impossible", "proof": {"type": "contradiction",
                "steps": [f"x+{m[1]}=x+{m[2]}", f"{m[1]}={m[2]}"]}}
    m = re.search(r"(\d+)/0", q)
    if m:
        return {"answer": "impossible",
                "proof": {"type": "zero_divisor", "dividend": int(m[1]), "divisor": 0}}
    if re.search(r"x\+\d+\?", q):
        return {"answer": "insufficient", "missing": "x"}
    m = re.search(r"x\+(\d+)=(\d+)", q)
    if m:
        a, c = int(m[1]), int(m[2])
        return {"answer": str(c - a), "steps": [f"{c}-{a} = {c - a}"]}
    m = re.search(r"(\d+)\s*([+\-*])\s*(\d+)", q)
    if m:
        a, op, b = int(m[1]), m[2], int(m[3])
        v = {"+": a + b, "-": a - b, "*": a * b}[op]
        return {"answer": str(v), "steps": [f"{a}{op}{b} = {v}"]}
    for key, code in CODE.items():
        if key in q:
            return {"code": code}
    m = re.search(r"greater than (\d+)", q)
    if m:
        return {"code": f"def f(xs):\n    return sum(x > {m[1]} for x in xs)"}
    return {"answer": "unknown"}


def answer_only(q):                           # cheater: right answers, shows no work
    r = good(q)
    r.pop("steps", None)
    return r


def always_impossible(q):                     # cheater: says "impossible" to everything
    return {"answer": "impossible",
            "proof": {"type": "zero_divisor", "dividend": 1, "divisor": 0}}


def hardcoder(q):                             # cheater: lookup-table code
    r = good(q)
    if "code" in r:
        r["code"] = "def f(x):\n    if x == 1: return 1\n    if x == 2: return 2\n    if x == 3: return 3\n    return 0"
    return r


if __name__ == "__main__":
    print("PART 4 check. Expected: honest survives, all three cheaters break.")
    pressure_test("honest solver", good, max_level=3, n=5)
    pressure_test("cheater: right answers, no work", answer_only, max_level=2, n=5)
    pressure_test("cheater: says impossible to everything", always_impossible, max_level=2, n=5)
    pressure_test("cheater: hardcoded code", hardcoder, max_level=2, n=5)
