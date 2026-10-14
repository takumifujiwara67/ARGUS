# PART 2: THE JUDGE
# Plain code (not an AI) that decides PASS or FAIL. It checks the WORK, not
# just the final answer. Each check returns a list of problems; empty = PASS.
# Run this file alone:  python p2_judge.py   (it tests the judge itself)
import ast, copy, os, random, re, subprocess, sys, tempfile

EQ = re.compile(r"^\s*([\d\s+\-*]+?)\s*=\s*(-?\d+)\s*$")


# ---------- helpers: call an AI safely ----------
def ask(solver, q):
    """a crash or a non-dict reply just counts as an empty answer"""
    try:
        r = solver(q)
        return r if isinstance(r, dict) else {}
    except Exception:
        return {}


def guarded(fn):
    try:
        return fn()
    except Exception as e:
        return [f"crashed: {type(e).__name__}"]


# ---------- arithmetic: the work must be true and tied to THIS question ----------
def check_solve(task, reply):
    fails = []
    if str(reply.get("answer", "")).strip() != task["answer"]:
        fails.append("wrong answer")
    steps = reply.get("steps")
    if not isinstance(steps, list) or not steps:
        return fails + ["no work shown"]
    last = None
    for s in steps:
        m = EQ.match(str(s))
        if not m or "**" in m[1]:                      # '**' could hang the computer
            return fails + [f"unreadable step: {s}"]
        try:
            if eval(m[1], {"__builtins__": {}}, {}) != int(m[2]):
                return fails + [f"false step: {s}"]
        except Exception:
            return fails + [f"unreadable step: {s}"]
        last = m[2]
    if last != task["answer"]:
        fails.append("steps do not end at the answer")
    used = set(re.findall(r"\d+", " ".join(map(str, steps))))
    if not all(str(o) in used for o in task["operands"]):
        fails.append("work not tied to this question")
    return fails


# ---------- impossible: needs a real proof, keywords are not enough ----------
def check_impossible(task, reply):
    if str(reply.get("answer", "")).strip().lower() != "impossible":
        return ["did not say impossible"]
    p = reply.get("proof") or {}
    if not isinstance(p, dict) or p.get("type") != task["type"]:
        return ["wrong reason type"]
    if task["type"] == "zero_divisor":
        ok = p.get("divisor") == 0 and p.get("dividend") == task["a"]
        return [] if ok else ["proof does not match"]
    st = [str(s).replace(" ", "") for s in p.get("steps", [])]
    a, b = task["a"], task["b"]
    ok = len(st) >= 2 and st[0] == f"x+{a}=x+{b}" and st[-1] == f"{a}={b}"
    return [] if ok else ["no valid contradiction steps"]


# ---------- missing information must not be invented ----------
def check_under(task, reply):
    ok = str(reply.get("answer", "")).strip().lower() == "insufficient" and reply.get("missing") == "x"
    return [] if ok else ["invented an answer instead of saying information is missing"]


# ---------- consistency: a+b, a+(b+1) and b+a must agree ----------
def check_pair(solver, level):
    a, b = random.randint(1, 10 ** level), random.randint(1, 10 ** level)
    try:
        r1 = int(ask(solver, f"what is {a}+{b}?").get("answer"))
        r2 = int(ask(solver, f"what is {a}+{b + 1}?").get("answer"))
        r3 = int(ask(solver, f"what is {b}+{a}?").get("answer"))
    except Exception:
        return ["could not answer all three"]
    fails = []
    if r2 - r1 != 1:
        fails.append("a+(b+1) is not exactly one more")
    if r3 != r1:
        fails.append("a+b and b+a disagree")
    if r1 != a + b:
        fails.append("wrong answer")
    return fails


# ---------- code: scanned for tricks, then run on fresh hidden inputs ----------
BAN = {"eval", "exec", "open", "__import__", "compile", "globals", "locals", "input",
       "getattr", "setattr", "__builtins__", "breakpoint", "vars"}
OK_IMPORTS = {"math", "re", "collections", "itertools"}


def static_check(code):
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"syntax error line {e.lineno}"
    const_returns = 0
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
            for m in mods:
                if m.split(".")[0] not in OK_IMPORTS:
                    return f"banned import {m}"
        if isinstance(n, ast.Name) and n.id in BAN:
            return f"banned name {n.id}"
        if isinstance(n, ast.Attribute) and n.attr.startswith("__"):
            return "dunder access"
        if isinstance(n, (ast.List, ast.Tuple, ast.Set)) and len(n.elts) >= 8 \
                and all(isinstance(e, ast.Constant) for e in n.elts):
            return "big literal table (looks hardcoded)"
        if isinstance(n, ast.Dict) and len(n.keys) >= 5:
            return "big literal table (looks hardcoded)"
        if isinstance(n, ast.If) and isinstance(n.test, ast.Compare) \
                and any(isinstance(c, ast.Constant) for c in n.test.comparators) \
                and n.body and isinstance(n.body[0], ast.Return) \
                and isinstance(n.body[0].value, ast.Constant):
            const_returns += 1
    if const_returns >= 3:
        return "chain of 'if x == constant: return constant' (looks hardcoded)"
    return None


def check_code(task, reply):
    code = str(reply.get("code", ""))
    bad = static_check(code)
    if bad:
        return [bad]
    inputs = task["edge"] + [task["gen"]() for _ in range(12)]     # fresh every run
    expected = [repr(task["ref"](copy.deepcopy(x))) for x in inputs]
    script = (code + "\nimport copy as _c\nfor _x in " + repr(inputs) +
              ":\n    print(repr(f(_c.deepcopy(_x))))\n")
    with tempfile.TemporaryDirectory() as d:                       # throwaway folder
        path = os.path.join(d, "t.py")
        with open(path, "w") as fh:
            fh.write(script)
        try:
            r = subprocess.run([sys.executable, "-I", path], capture_output=True,
                               text=True, timeout=3, cwd=d)
        except subprocess.TimeoutExpired:
            return ["timed out"]
    ok = r.stdout.split("\n")[:-1] == expected
    return [] if ok else ["crashed or wrong output on hidden inputs"]


# ---------- self-test: feed the judge replies where we KNOW the right verdict ----------
if __name__ == "__main__":
    print("PART 2 check: the judge must give the verdict we expect.")
    print("(the infinite-loop test takes about 3 seconds)\n")
    wrong = 0

    def show(name, fails, expected):
        global wrong
        got = "FAIL" if fails else "PASS"
        ok = "ok " if got == expected else "BAD"
        wrong += got != expected
        print(f"[{ok}] {name:38} -> {got}  {fails if fails else ''}")

    t = {"q": "what is 20+35?", "answer": "55", "operands": [20, 35]}
    show("right answer + true work", check_solve(t, {"answer": "55", "steps": ["20+35 = 55"]}), "PASS")
    show("right answer, NO work", check_solve(t, {"answer": "55"}), "FAIL")
    show("wrong answer", check_solve(t, {"answer": "56", "steps": ["20+35 = 56"]}), "FAIL")
    show("false step", check_solve(t, {"answer": "55", "steps": ["20+35 = 56", "56-1 = 55"]}), "FAIL")
    show("work about other numbers", check_solve(t, {"answer": "55", "steps": ["1+1 = 2", "2+53 = 55"]}), "FAIL")
    show("slow-computer trick 9**9**9", check_solve(t, {"answer": "55", "steps": ["9**9**9 = 55"]}), "FAIL")

    z = {"q": "what is 7/0?", "type": "zero_divisor", "a": 7}
    show("zero: correct proof", check_impossible(z, {"answer": "impossible", "proof": {"type": "zero_divisor", "dividend": 7, "divisor": 0}}), "PASS")
    show("zero: keywords only, no proof", check_impossible(z, {"answer": "impossible", "explanation": "divide by zero"}), "FAIL")
    show("zero: wrong proof type", check_impossible(z, {"answer": "impossible", "proof": {"type": "contradiction", "steps": []}}), "FAIL")
    show("zero: answered 0 instead", check_impossible(z, {"answer": "0"}), "FAIL")

    c = {"q": "find x where x+3=x+5", "type": "contradiction", "a": 3, "b": 5}
    show("contradiction: valid proof", check_impossible(c, {"answer": "impossible", "proof": {"type": "contradiction", "steps": ["x+3=x+5", "3=5"]}}), "PASS")
    show("contradiction: no steps", check_impossible(c, {"answer": "impossible", "proof": {"type": "contradiction", "steps": []}}), "FAIL")

    u = {"q": "what is x+4?"}
    show("under: says insufficient", check_under(u, {"answer": "insufficient", "missing": "x"}), "PASS")
    show("under: invents a number", check_under(u, {"answer": "9"}), "FAIL")

    ct = {"gen": lambda: random.randint(0, 99), "ref": lambda n: n * 2, "edge": [0, 1], "q": ""}
    show("code: correct", check_code(ct, {"code": "def f(n):\n    return n*2"}), "PASS")
    show("code: hardcoded lookups", check_code(ct, {"code": "def f(n):\n    if n == 0: return 0\n    if n == 1: return 2\n    if n == 2: return 4\n    return 0"}), "FAIL")
    show("code: tries to import os", check_code(ct, {"code": "import os\ndef f(n):\n    return n*2"}), "FAIL")
    show("code: tries to open a file", check_code(ct, {"code": "def f(n):\n    return open('x').read()"}), "FAIL")
    show("code: infinite loop", check_code(ct, {"code": "def f(n):\n    while True: pass"}), "FAIL")

    print("\nAll verdicts as expected." if not wrong else f"\n{wrong} verdict(s) were NOT as expected - tell me which.")
