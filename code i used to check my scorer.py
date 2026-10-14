# ============================================================================= IT CAN BE CHECKED BY SAVING IT AND OPENING IT AND THEN IT CONTAINS 22 QUESTIONS IN THE TERMINAL IT GIVES YOU THE QUESTIONS JUST COPY THEM AND PASTE THEM IN THE AI YOU WANT OR YOU MADE AND THEN AFTER THE 22
  QUESTIONS ARE YOU WILL GET A RESULT IN THE TERMINAL SAYING HOW MANY IT GOT CORRECT AND DID IT PASS OR NOT 
#  argus.py  -  Argus, in ONE file. Needs only Python 3.8+ (no pip, no PyTorch).
#
#  Argus tests an AI by asking it fresh questions, level by level, and checks HOW
#  it got each answer (true work, real proofs, hidden code tests), not just
#  whether the final answer matches. The result is PASS or FAIL, plus where and why.
#
#  HOW TO USE
#    1. Change the SETTINGS just below (or leave them as they are).
#    2. Run:   python argus.py
#       Or pick a mode without editing:   python argus.py demo
#                                         python argus.py selfcheck
#                                         python argus.py website | api | ollama
#
#  SAFETY: AI-written code is run in a throwaway folder with a 3 second timeout,
#  but that is NOT a real sandbox. Only use it with AIs you trust.
# =============================================================================
import ast, copy, json, os, random, re, subprocess, sys, tempfile
import urllib.error, urllib.request
from collections import Counter

# =============================== SETTINGS ====================================
MODE = "website"       # "website"   you paste by hand (an AI that only has a chat website)
                       # "api"       automatic, needs a provider's API key
                       # "ollama"    automatic, a model on your own Ollama
                       # "demo"      a pretend chat AI, to check the whole setup works
                       # "selfcheck" pretend honest AI + cheaters, to prove the judge works
AI_NAME   = "GLM 5.3 Flash"   # only used for the labels in the report
MAX_LEVEL = 1          # how many difficulty levels to try (1 = quick, 3 = thorough)
N         = 2          # questions per category at each level (bigger = fairer but slower)
LOG_FILE  = "argus_log.txt"   # every question and reply is saved here

# only for MODE = "api"  (copy these from your provider's page; examples from provider docs:
#   https://api.empiriolabs.ai/v1 + glm-5-3-flash   |   https://api.haimaker.ai/v1 + z-ai/glm-5.3-flash)
API_BASE_URL    = "https://api.empiriolabs.ai/v1"
API_MODEL       = "glm-5-3-flash"
API_KEY_ENV     = "ARGUS_API_KEY"   # the NAME of the environment variable that holds your key
API_TEMPERATURE = 0                 # if the provider rejects 'temperature', set this to None

# only for MODE = "ollama"
OLLAMA_MODEL   = "your-model-name"  # exact name from the command:  ollama list
OLLAMA_TIMEOUT = 300                # seconds allowed per answer (raise it for big models)


# =============================================================================
# PART 1: THE TASKS
# Makes brand-new random questions every time, so memorizing can't pass.
# =============================================================================

PH_A = ["what is {e}?", "compute {e}", "{e} = ?"]
PH_B = ["please work out {e}", "tell me the value of {e}", "calculate: {e}"]


def t_arith(level, phr):
    """add / subtract / multiply / find-x. Bigger level = bigger numbers."""
    hi = 10 ** level
    a, b = random.randint(1, hi), random.randint(1, hi)
    kind = random.choice(["add", "sub", "mul", "eq"])
    if kind == "mul":
        a, b = random.randint(2, 5 * level + 3), random.randint(2, 5 * level)
    if kind == "eq":                                   # find x where x+a=c
        c = a + b
        return {"q": f"find x where x+{a}={c}", "answer": str(b), "operands": [a, c]}
    e, ans = {"add": (f"{a}+{b}", a + b), "sub": (f"{a}-{b}", a - b),
              "mul": (f"{a}*{b}", a * b)}[kind]
    return {"q": random.choice(phr).format(e=e), "answer": str(ans), "operands": [a, b]}


def t_impossible(level):
    """questions that CANNOT be solved. The AI must prove why."""
    if random.random() < 0.5:
        a = random.randint(1, 10 ** level)
        return {"q": f"what is {a}/0?", "type": "zero_divisor", "a": a}
    a = random.randint(1, 50)
    b = a + random.randint(1, 9)
    return {"q": f"find x where x+{a}=x+{b}", "type": "contradiction", "a": a, "b": b}


def t_under(level):
    """not enough information. The AI must NOT invent an answer."""
    return {"q": f"what is x+{random.randint(1, 10 ** level)}?"}


def t_compose(level, phr):
    """multi-step questions where the ORDER of operations matters.
    The AI cannot just restate the answer: it has to break the question into steps."""
    hi = 5 * level + 4
    shapes = ["a+b*c", "a*b-c", "(a+b)*c", "a-b*c", "a*b+c"]
    if level >= 3:
        shapes += ["a*b+c*d", "(a+b)*(c+d)", "a*b-c*d"]
    shape = random.choice(shapes)
    vals = {k: random.randint(2, hi) for k in "abcd"}
    expr = "".join(str(vals[ch]) if ch in vals else ch for ch in shape)
    operands = [vals[ch] for ch in dict.fromkeys(ch for ch in shape if ch in vals)]
    answer = eval(expr, {"__builtins__": {}}, {})          # our own safe expression
    return {"q": random.choice(phr).format(e=expr), "answer": str(answer), "operands": operands}


def t_trap(level, phr):
    """look-alike traps. They LOOK like impossible questions but are not.
    An AI that matches on how a question looks (a '/', or 'x+..=x+..') gets them wrong."""
    kind = random.choice(["zero_numerator", "exact_division", "identity"])
    a = random.randint(1, 10 ** level)
    if kind == "zero_numerator":                           # 0/a is just 0
        return {"q": f"what is 0/{a}?", "answer": "0", "operands": [0, a]}
    if kind == "exact_division":                           # a division that is fine
        b = random.randint(2, 5 * level + 3)
        return {"q": f"what is {a * b}/{b}?", "answer": str(a), "operands": [a * b, b]}
    return {"q": f"find x where x+{a}=x+{a}", "type": "identity", "a": a}   # true for EVERY x


def t_code(level):
    """coding tasks. The test inputs are hidden and fresh every run."""
    k = random.randint(0, 9)
    return random.choice([
        {"q": "write a python function f(n) that returns the sum of the digits of n",
         "gen": lambda: random.randint(0, 10 ** (level + 3)),
         "ref": lambda n: sum(map(int, str(n))), "edge": [0, 9, 10, 99999]},
        {"q": "write a python function f(xs) that returns the largest number in the list xs",
         "gen": lambda: [random.randint(-99, 99) for _ in range(random.randint(1, 4 + level))],
         "ref": lambda xs: max(xs), "edge": [[5], [-3, -9], [0, 0]]},
        {"q": "write a python function f(s) that returns how many vowels (a,e,i,o,u) are in the string s",
         "gen": lambda: "".join(random.choice("abcdeiouxyz") for _ in range(random.randint(0, 5 + 3 * level))),
         "ref": lambda s: sum(c in "aeiou" for c in s), "edge": ["", "xyz", "aeiou"]},
        {"q": f"write a python function f(xs) that returns how many numbers in xs are greater than {k}",
         "gen": lambda: [random.randint(-5, 15) for _ in range(random.randint(0, 4 + level))],
         "ref": lambda xs, k=k: sum(x > k for x in xs), "edge": [[], [k], [k + 1]]},
    ])


# =============================================================================
# PART 2: THE JUDGE
# Plain code (not an AI) that decides PASS or FAIL. It checks the WORK, not just the answer.
# =============================================================================

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


# One step = ONE operation on TWO numbers:  "20+35 = 55"
STEP = re.compile(r"^\s*(-?\d+)\s*([+\-*/])\s*(-?\d+)\s*=\s*(-?\d+)\s*$")


def apply_op(a, op, b):
    """exact whole-number arithmetic. Returns None when the step is not valid."""
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return a // b if b != 0 and a % b == 0 else None      # no divide-by-zero, no rounding
    return None


# ---------- arithmetic: the work must be a real chain from the question to the answer ----------
def check_solve(task, reply):
    fails = []
    if str(reply.get("answer", "")).strip() != task["answer"]:
        fails.append("wrong answer")
    steps = reply.get("steps")
    if not isinstance(steps, list) or not steps:
        return fails + ["no work shown"]
    available = set(task["operands"])        # the only numbers the AI may start from
    result = None
    for s in steps:
        m = STEP.match(str(s))
        if not m:
            return fails + [f"not one clear operation: {s}"]
        try:
            a, op, b, r = int(m[1]), m[2], int(m[3]), int(m[4])
        except ValueError:
            return fails + [f"unreadable step: {s}"]
        if a not in available or b not in available:
            return fails + [f"uses a number from nowhere: {s}"]
        if apply_op(a, op, b) != r:
            return fails + [f"false step: {s}"]
        available.add(r)                     # this result may be used by later steps
        result = r
    if str(result) != task["answer"]:
        fails.append("steps do not end at the answer")
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


# ---------- look-alike trap: true for EVERY x, so it is NOT impossible ----------
def check_identity(task, reply):
    if str(reply.get("answer", "")).strip().lower() != "any":
        return ["did not say the equation is true for every x"]
    p = reply.get("proof") or {}
    if not isinstance(p, dict) or p.get("type") != "identity":
        return ["wrong reason type"]
    st = [str(s).replace(" ", "") for s in p.get("steps", [])]
    a = task["a"]
    ok = len(st) >= 2 and st[0] == f"x+{a}=x+{a}" and st[-1] == f"{a}={a}"
    return [] if ok else ["no valid identity steps"]


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


# =============================================================================
# PART 3: THE RUNNER
# The pressure test: asks fresh questions level by level until the AI breaks.
# =============================================================================

ALL_CATS = ["arith", "compose", "trap", "impossible", "under", "code", "consistency"]


def run_suite(solver, level, phr, n=10, only=None):
    """n fresh questions per category. Returns (problems per category, cheat flags)."""
    cats = only or ALL_CATS
    res = {c: [] for c in cats}
    answers = []
    for _ in range(n):
        if "arith" in cats:
            t = t_arith(level, phr)
            r = ask(solver, t["q"])
            res["arith"].append(guarded(lambda: check_solve(t, r)))
            answers.append(str(r.get("answer")))
        if "compose" in cats:
            t = t_compose(level, phr)
            r = ask(solver, t["q"])
            res["compose"].append(guarded(lambda: check_solve(t, r)))
        if "trap" in cats:
            t = t_trap(level, phr)
            r = ask(solver, t["q"])
            chk = check_identity if t.get("type") == "identity" else check_solve
            res["trap"].append(guarded(lambda: chk(t, r)))
        if "impossible" in cats:
            t = t_impossible(level)
            res["impossible"].append(guarded(lambda: check_impossible(t, ask(solver, t["q"]))))
        if "under" in cats:
            t = t_under(level)
            res["under"].append(guarded(lambda: check_under(t, ask(solver, t["q"]))))
        if "code" in cats:
            t = t_code(level)
            res["code"].append(guarded(lambda: check_code(t, ask(solver, t["q"]))))
        if "consistency" in cats:
            res["consistency"].append(guarded(lambda: check_pair(solver, level)))
    flags = []
    # same answer to most questions (needs at least 4 repeats, so luck with a
    # small sample can't make an honest AI look like a cheater)
    top = Counter(answers).most_common(1)[0][1] if answers else 0
    if top >= 4 and top > 0.5 * len(answers):
        flags.append("CONSTANT-ANSWER: same answer to most different questions")
    return res, flags


def rate(problem_lists):
    """share of tasks with no problems at all"""
    return sum(1 for p in problem_lists if not p) / len(problem_lists)


# ---------- the result: PASS or FAIL ----------
def _banner(name, result):
    n = result["max_level"]
    lines = [f"ARGUS: {name}"]
    if result["result"] == "PASS":
        lines.append(f"result: PASS  (survived all {n} level{'s' if n != 1 else ''})")
    else:
        lines.append(f"result: FAIL  (broke at level {result['broke_at']} of {n})")
        if result["weak"]:
            lines.append("failed on: " + ", ".join(result["weak"]))
        for f in result["flags"]:
            lines.append("flag: " + f)
    w = max(len(l) for l in lines)
    bar = "+" + "-" * (w + 4) + "+"
    print("\n" + bar)
    for l in lines:
        print("|  " + l.ljust(w) + "  |")
    print(bar)


def pressure_test(name, solver, max_level=5, mark=0.9, n=10, quiet=False):
    """raise the difficulty level by level until the AI breaks.
    Returns a dict with the result (PASS or FAIL), so other code can use it."""
    say = (lambda *a: None) if quiet else print
    say(f"\n=== {name} ===")
    result = {"name": name, "max_level": max_level, "survived": 0,
              "broke_at": None, "weak": [], "flags": []}
    for level in range(1, max_level + 1):
        resA, flagsA = run_suite(solver, level, PH_A, n)
        resB, flagsB = run_suite(solver, level, PH_B, n, only=["arith", "compose"])
        line = "  ".join(f"{c}={rate(v):.0%}" for c, v in resA.items())
        say(f"level {level} (seen wording):   {line}")
        mathA = rate(resA["arith"] + resA["compose"])
        mathB = rate(resB["arith"] + resB["compose"])
        say(f"level {level} (unseen wording): math={mathB:.0%}")
        problems = [c for c, v in resA.items() if rate(v) < mark]
        flags = set(flagsA + flagsB)
        if mathA - mathB > 0.3:
            flags.add("MEMORIZED FORMAT: much worse on unseen wording")
        if problems or flags:
            say(f"  -> BREAKS at level {level}. Weak: {problems}")
            for c in problems:
                why = Counter(x for f in resA[c] for x in f).most_common(2)
                say(f"     {c}: {why}")
            for f in sorted(flags):
                say(f"     FLAG: {f}")
            result.update(broke_at=level, weak=problems, flags=sorted(flags))
            break
        result["survived"] = level
    else:
        say("  -> survived every level, no flags")
    result["result"] = "PASS" if result["broke_at"] is None else "FAIL"
    if not quiet:
        _banner(name, result)
    return result


# =============================================================================
# PART 4: PRACTICE AIs
# Hand-written pretend AIs (one honest, cheaters) that prove the judge works.
# =============================================================================

CODE = {
    "sum of the digits": "def f(n):\n    return sum(int(c) for c in str(n))",
    "largest number": "def f(xs):\n    return max(xs)",
    "how many vowels": "def f(s):\n    return sum(c in 'aeiou' for c in s)",
}


def _derive(node, steps):
    """break an expression into ONE-operation steps, in the right order"""
    if isinstance(node, ast.Constant):
        return node.value
    a = _derive(node.left, steps)
    b = _derive(node.right, steps)
    if isinstance(node.op, ast.Add):
        op, v = "+", a + b
    elif isinstance(node.op, ast.Sub):
        op, v = "-", a - b
    elif isinstance(node.op, ast.Mult):
        op, v = "*", a * b
    else:
        op, v = "/", a // b
    steps.append(f"{a}{op}{b} = {v}")
    return v


def good(q):                                  # honest: really works everything out
    if "python function" in q:
        for key, code in CODE.items():
            if key in q:
                return {"code": code}
        m = re.search(r"greater than (\d+)", q)
        if m:
            return {"code": f"def f(xs):\n    return sum(x > {m[1]} for x in xs)"}
        return {"answer": "unknown"}
    m = re.search(r"x\+(\d+)=x\+(\d+)", q)
    if m:
        a, b = m[1], m[2]
        if a == b:                            # true for every x, so NOT impossible
            return {"answer": "any", "proof": {"type": "identity",
                    "steps": [f"x+{a}=x+{a}", f"{a}={a}"]}}
        return {"answer": "impossible", "proof": {"type": "contradiction",
                "steps": [f"x+{a}=x+{b}", f"{a}={b}"]}}
    m = re.search(r"(\d+)/0(?!\d)", q)
    if m:
        return {"answer": "impossible",
                "proof": {"type": "zero_divisor", "dividend": int(m[1]), "divisor": 0}}
    if re.search(r"x\+\d+\?", q):
        return {"answer": "insufficient", "missing": "x"}
    m = re.search(r"x\+(\d+)=(\d+)", q)
    if m:
        a, c = int(m[1]), int(m[2])
        return {"answer": str(c - a), "steps": [f"{c}-{a} = {c - a}"]}
    m = re.search(r"[\d(][\d+\-*/() ]*", q)
    if m:
        try:
            steps = []
            value = _derive(ast.parse(m[0].strip(), mode="eval").body, steps)
            if steps:
                return {"answer": str(value), "steps": steps}
        except Exception:
            pass
    return {"answer": "unknown"}


def small_numbers_only(q):                    # breaks under pressure: fine under 100, wrong with bigger numbers
    if any(int(x) > 99 for x in re.findall(r"\d+", q)):
        return {"answer": "0", "steps": ["0+0 = 0"]}
    return good(q)


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


def restater(q):                              # cheater: states the whole calculation as ONE step
    r = good(q)
    m = re.search(r"[\d(][\d+\-*/() ]*", q)
    if len(r.get("steps", [])) > 1 and m:
        r["steps"] = [f"{m[0].strip()} = {r['answer']}"]
    return r


def cue_matcher(q):                           # cheater: reacts to how a question LOOKS, not what it says
    m = re.search(r"x\+(\d+)=x\+(\d+)", q)
    if m:                                     # sees x+..=x+.. -> always "contradiction"
        return {"answer": "impossible", "proof": {"type": "contradiction",
                "steps": [f"x+{m[1]}=x+{m[2]}", f"{m[1]}={m[2]}"]}}
    m = re.search(r"(\d+)/(\d+)", q)
    if m:                                     # sees a division -> always "impossible"
        return {"answer": "impossible", "proof": {"type": "zero_divisor",
                "dividend": int(m[1]), "divisor": 0}}
    return good(q)


# =============================================================================
# PART 5: THE BRIDGE
# Connects ANY AI to the scorer: your Ollama, an API, a program, or a chat website.
# =============================================================================

PROMPT = """You are being tested by a strict automatic judge.
Reply with ONE JSON object and nothing else. Pick the format that fits the question.

1) A math question (a calculation, or "find x"):
   {"answer": "<final number>", "steps": ["<number> <op> <number> = <result>", ...]}
   Each step is ONE operation on TWO numbers, using + - * or / (exact division only).
   A step may only use numbers from the question or results of earlier steps.
   The last result must equal the answer.
   Example for 3+4*5 (multiply first): ["4*5 = 20", "3+20 = 23"]
   For "find x where x+5=12", write the arithmetic that gives x: ["12-5 = 7"]

2) Questions with no solution, or where every x is a solution:
   - dividing by zero:
     {"answer": "impossible", "proof": {"type": "zero_divisor", "dividend": <number>, "divisor": 0}}
   - an equation with no solution, like x+3=x+5:
     {"answer": "impossible", "proof": {"type": "contradiction", "steps": ["x+3=x+5", "3=5"]}}
   - an equation true for EVERY x, like x+3=x+3:
     {"answer": "any", "proof": {"type": "identity", "steps": ["x+3=x+3", "3=3"]}}

3) A question with not enough information (it contains an unknown like x):
   {"answer": "insufficient", "missing": "x"}

4) A request to write a Python function:
   {"code": "def f(...):\n    ..."}
   Use only the standard modules math, re, collections, itertools. No file access.

Question: {q}"""


class StopTest(BaseException):
    """raised to stop the whole test (call budget used up, or the AI is unreachable)"""


# ---------- reading the AI's reply ----------
def extract_json(text):
    """find the first JSON object in the reply, even inside ```json fences or chatter"""
    dec = json.JSONDecoder(strict=False)       # strict=False: allow raw line breaks inside strings
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        i = text.find("{", i + 1)
    return None


def _num(x):
    """tolerate '55', 55.0 and 55 - this is about typing, not about being right"""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, str) and re.fullmatch(r"-?\d+", x.strip()):
        return int(x.strip())
    return x


def _steps(v):
    if isinstance(v, list):
        return [str(s) for s in v]
    if isinstance(v, str):
        return [s.strip() for s in re.split(r"[;\n]", v) if s.strip()]
    return []


def normalize(d):
    out = {}
    if "answer" in d:
        out["answer"] = str(_num(d["answer"])).strip()
    if "steps" in d:
        out["steps"] = _steps(d["steps"])
    if "missing" in d:
        out["missing"] = str(d["missing"]).strip()
    if "code" in d:
        out["code"] = str(d["code"])
    if isinstance(d.get("proof"), dict):
        p = dict(d["proof"])
        for k in ("dividend", "divisor"):
            if k in p:
                p[k] = _num(p[k])
        if "steps" in p:
            p["steps"] = _steps(p["steps"])
        out["proof"] = p
    return out


# ---------- the bridge itself ----------
class Bridge:
    def __init__(self, raw_ask, max_calls=500):
        self.raw_ask = raw_ask          # any function: prompt text -> reply text
        self.max_calls = max_calls      # safety limit (protects you from big API bills)
        self.calls = self.bad_format = self.errors = self.in_a_row = 0
        self.last_error = ""
        self.bad_samples = []

    def __call__(self, q):              # this is what the scorer calls
        if self.calls >= self.max_calls:
            raise StopTest(f"call budget of {self.max_calls} reached")
        self.calls += 1
        try:
            text = self.raw_ask(PROMPT.replace("{q}", q))
            self.in_a_row = 0
        except Exception as e:
            self.errors += 1
            self.in_a_row += 1
            self.last_error = repr(e)
            if self.in_a_row >= 3:
                raise StopTest(f"the AI failed 3 times in a row: {self.last_error}")
            return {}
        obj = extract_json(text or "")
        if obj is None:
            self.bad_format += 1
            if len(self.bad_samples) < 2:
                self.bad_samples.append((text or "")[:200])
            return {}
        return normalize(obj)

    def report(self):
        print(f"\nBridge report: {self.calls} questions sent, "
              f"{self.bad_format} replies had no JSON, {self.errors} errors.")
        if self.bad_format:
            print("  Replies that were not JSON count as FAILS (format counts).")
            for s in self.bad_samples:
                print("  example:", repr(s))
        if self.errors:
            print("  last error:", self.last_error)


# ---------- adapters: ways to reach an AI ----------
def from_function(fn):
    """an AI that is a Python function: prompt (str) -> reply (str)"""
    return fn


def _post_json(url, payload, headers=None, timeout=120):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, json.dumps(payload).encode("utf-8"), h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:200]!r}")


def from_ollama(model, url="http://localhost:11434", timeout=300):
    """a model running in Ollama (ollama.com). Big models can be slow on a small
    computer, so each answer gets up to `timeout` seconds (raise it if needed)."""
    def raw_ask(prompt):
        r = _post_json(f"{url}/api/generate",
                       {"model": model, "prompt": prompt, "stream": False,
                        "options": {"temperature": 0}}, timeout=timeout)
        return r["response"]
    return raw_ask


def from_openai_compatible(base_url, model, api_key=None, temperature=0):
    """OpenAI and many others (LM Studio, llama.cpp server, vLLM, Ollama's /v1 ...).
    The key is read from the environment, never write it into a file you upload."""
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    def raw_ask(prompt):
        body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        if temperature is not None:
            body["temperature"] = temperature
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        r = _post_json(f"{base_url}/chat/completions", body, headers)
        return r["choices"][0]["message"]["content"]
    return raw_ask


def from_command(cmd, timeout=120):
    """any program (Python, C++, anything): the prompt goes in on stdin,
    the reply is read from stdout. Example: from_command(["./my_ai"])"""
    def raw_ask(prompt):
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"program exited with code {r.returncode}: {r.stderr[:200]}")
        return r.stdout
    return raw_ask


# ---------- website mode: YOU are the connection (for AIs that only have a chat website) ----------
def _clip_write(text):
    """put text on the clipboard so you only press Ctrl+V. Returns True if it worked."""
    try:
        if sys.platform.startswith("win"):
            cmd = ["clip"]
        elif sys.platform == "darwin":
            cmd = ["pbcopy"]
        else:
            cmd = ["xclip", "-selection", "clipboard"]
        subprocess.run(cmd, input=text.encode("utf-8"), timeout=10, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _clip_read():
    """read the clipboard. Returns "" if that is not possible."""
    try:
        if sys.platform.startswith("win"):
            cmd = ["powershell", "-NoProfile", "-Command",
                   "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"]
        elif sys.platform == "darwin":
            cmd = ["pbpaste"]
        else:
            cmd = ["xclip", "-selection", "clipboard", "-o"]
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        return r.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _read_until_end(lines):
    """read pasted lines until a line that says END"""
    while True:
        line = input()
        if line.strip() == "END":
            return "\n".join(lines)
        lines.append(line)


def from_paste(ai_name="the AI", use_clipboard=True):
    """For an AI that only has a chat website. Argus shows each question (and copies it
    to your clipboard), you paste it into the chat, then bring the reply back.
    The rules go in the first message only; after that each message is just a question."""
    state = {"n": 0, "clip": use_clipboard, "sent": ""}

    def raw_ask(prompt):
        state["n"] += 1
        q = prompt.rpartition("Question:")[2].strip()
        if state["n"] == 1:
            text = prompt
            print("\n" + "=" * 70)
            print(f"Open a NEW chat with {ai_name}. Your first message holds the rules")
            print("and question 1. Keep using the SAME chat for every question.")
            print("-" * 70)
            print(text)
            print("-" * 70)
        else:
            text = "(Same rules as before. Reply with ONE JSON object only.)\nQuestion: " + q
            print("\n" + "-" * 70)
            print(f"Question {state['n']}:  {q}")
        if state["clip"]:
            if _clip_write(text):
                state["sent"] = text.strip()
                print("(copied to your clipboard: paste it into the chat with Ctrl+V)")
            else:
                state["clip"] = False
                print("(no clipboard tool found: copy the text by hand)")
        print("When the AI has answered, click its COPY button here, then press Enter.")
        print("(Or paste the reply here and finish with a line that says END. SKIP skips, QUIT stops.)")
        while True:
            first = input("> ")
            word = first.strip().upper()
            if word == "QUIT":
                raise StopTest("you stopped the test")
            if word == "SKIP":
                return ""
            if word != "":
                return _read_until_end([first])
            reply = _clip_read() if state["clip"] else ""
            if reply and reply == state["sent"]:
                print("The clipboard still holds the question. Copy the AI's reply first, then press Enter.")
                continue
            if not reply:
                print("The clipboard is empty or unreadable. Paste the reply here, then a line that says END:")
                return _read_until_end([])
            return reply
    return raw_ask


# ---------- pretend AIs so you can test the bridge without installing anything ----------
def demo_chat_ai(prompt):
    """behaves like a chatty, decent AI: right answers, wrapped in ```json fences + small talk"""
    q = prompt.split("Question:")[-1].strip()
    return "Sure! Here is my answer:\n```json\n" + json.dumps(good(q)) + "\n```\nHope that helps."


def sloppy_chat_ai(prompt):
    """a chatty AI that ignores the format and answers in plain sentences"""
    return "I think the answer is probably around 42, but I am not totally sure."


# =============================================================================
# RUN IT
# =============================================================================
def _logged(raw_ask, path):
    """save every question and reply to a text file, so you can read what the AI really said"""
    def wrapper(prompt):
        reply = raw_ask(prompt)
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("QUESTION: " + prompt.rpartition("Question:")[2].strip()
                         + "\nREPLY:\n" + str(reply) + "\n" + "-" * 60 + "\n")
        except OSError:
            pass
        return reply
    return wrapper


def build_ai():
    """returns a Bridge connected to the AI chosen in MODE, or None if setup is incomplete"""
    if MODE == "demo":
        raw = from_function(demo_chat_ai)
    elif MODE == "website":
        raw = from_paste(AI_NAME)
    elif MODE == "ollama":
        raw = from_ollama(OLLAMA_MODEL, timeout=OLLAMA_TIMEOUT)
    elif MODE == "api":
        key = os.environ.get(API_KEY_ENV, "")
        if not key:
            print(f"No API key found. Set the environment variable {API_KEY_ENV} first:")
            print(f'  Windows (PowerShell):  $env:{API_KEY_ENV}="your-key"')
            print(f"  Windows (cmd):         set {API_KEY_ENV}=your-key")
            print(f'  Mac / Linux:           export {API_KEY_ENV}="your-key"')
            print("Never write the key into this file if you will upload it to GitHub.")
            return None
        raw = from_openai_compatible(API_BASE_URL, API_MODEL, api_key=key, temperature=API_TEMPERATURE)
    else:
        print(f'Unknown MODE "{MODE}". Use website, api, ollama, demo or selfcheck.')
        return None
    return Bridge(_logged(raw, LOG_FILE), max_calls=500)


def selfcheck():
    print("Judge self-check. Expected: the honest solver PASSES, every other one FAILS.")
    pressure_test("honest solver", good, max_level=3, n=5)
    pressure_test("breaks under pressure: only small numbers", small_numbers_only, max_level=3, n=5)
    pressure_test("cheater: right answers, no work", answer_only, max_level=2, n=5)
    pressure_test("cheater: restates the answer as one step", restater, max_level=2, n=5)
    pressure_test("cheater: judges questions by how they look", cue_matcher, max_level=2, n=5)
    pressure_test("cheater: says impossible to everything", always_impossible, max_level=2, n=5)
    pressure_test("cheater: hardcoded code", hardcoder, max_level=2, n=5)


def main():
    if MODE == "selfcheck":
        selfcheck()
        return
    ai = build_ai()
    if ai is None:
        return
    label = {"website": AI_NAME, "api": AI_NAME, "ollama": OLLAMA_MODEL,
             "demo": "pretend chat AI"}[MODE]
    try:
        open(LOG_FILE, "w", encoding="utf-8").close()          # start a fresh log
    except OSError:
        pass
    print(f"Argus is testing: {label}   (mode: {MODE}, up to {MAX_LEVEL} level(s), n={N})")
    try:
        pressure_test(label, ai, max_level=MAX_LEVEL, n=N)
    except StopTest as e:
        print("\nTest stopped early:", e)
    except KeyboardInterrupt:
        print("\nStopped by you (Ctrl+C). There is no final result because the test was not finished.")
    ai.report()
    print(f"\nEvery question and reply was saved in {LOG_FILE}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("website", "api", "ollama", "demo", "selfcheck"):
        MODE = sys.argv[1]
    main()
