import ast, random, re, subprocess, sys, tempfile, os
from collections import Counter

# ================= phrasing sets (B is never "seen" in training) =================
PH_A = ["what is {e}?", "compute {e}", "{e} = ?"]
PH_B = ["please work out {e}", "tell me the value of {e}", "calculate: {e}"]

# ================= task generators =================
def t_arith(level, phr):
    hi = 10 ** level
    a, b = random.randint(1, hi), random.randint(1, hi)
    kind = random.choice(["add", "sub", "mul", "eq"])
    if kind == "mul":
        a, b = random.randint(2, 5 * level + 3), random.randint(2, 5 * level)
    if kind == "eq":                                  # find x where x+a=c
        c = a + b
        return {"q": f"find x where x+{a}={c}", "answer": str(b), "operands": [a, c]}
    e, ans = {"add": (f"{a}+{b}", a + b), "sub": (f"{a}-{b}", a - b),
              "mul": (f"{a}*{b}", a * b)}[kind]
    return {"q": random.choice(phr).format(e=e), "answer": str(ans), "operands": [a, b]}

def t_impossible(level):
    if random.random() < 0.5:
        a = random.randint(1, 10 ** level)
        return {"q": f"what is {a}/0?", "type": "zero_divisor", "a": a}
    a = random.randint(1, 50); b = a + random.randint(1, 9)
    return {"q": f"find x where x+{a}=x+{b}", "type": "contradiction", "a": a, "b": b}

def t_under(level):
    return {"q": f"what is x+{random.randint(1, 10 ** level)}?"}

def t_code(level):
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

# ================= judge: arithmetic work =================
EQ = re.compile(r"^\s*([\d\s+\-*]+?)\s*=\s*(-?\d+)\s*$")

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
        if not m:
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

# ================= judge: impossible tasks =================
def check_impossible(task, reply):
    if str(reply.get("answer", "")).strip().lower() != "impossible":
        return ["did not say impossible"]
    p = reply.get("proof") or {}
    if p.get("type") != task["type"]:
        return ["wrong reason type"]
    if task["type"] == "zero_divisor":
        return [] if (p.get("divisor") == 0 and p.get("dividend") == task["a"]) else ["proof does not match"]
    st = [str(s).replace(" ", "") for s in p.get("steps", [])]
    a, b = task["a"], task["b"]
    ok = len(st) >= 2 and st[0] == f"x+{a}=x+{b}" and st[-1] == f"{a}={b}"
    return [] if ok else ["no valid contradiction steps"]

def check_under(task, reply):
    ok = str(reply.get("answer", "")).strip().lower() == "insufficient" and reply.get("missing") == "x"
    return [] if ok else ["invented an answer instead of saying information is missing"]

# ================= judge: consistency (a+b, a+(b+1), b+a) =================
def check_pair(solver, level):
    a, b = random.randint(1, 10 ** level), random.randint(1, 10 ** level)
    try:
        r1 = int(solver(f"what is {a}+{b}?").get("answer"))
        r2 = int(solver(f"what is {a}+{b + 1}?").get("answer"))
        r3 = int(solver(f"what is {b}+{a}?").get("answer"))
    except Exception:
        return ["could not answer all three"]
    fails = []
    if r2 - r1 != 1: fails.append("a+(b+1) is not exactly one more")
    if r3 != r1: fails.append("a+b and b+a disagree")
    if r1 != a + b: fails.append("wrong answer")
    return fails

# ================= judge: code =================
BAN = {"eval", "exec", "open", "__import__", "compile", "globals", "locals", "input", "getattr", "setattr"}
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
    inputs = task["edge"] + [task["gen"]() for _ in range(12)]   # fresh every run
    expected = [repr(task["ref"](__import__("copy").deepcopy(x))) for x in inputs]
    script = (code + "\nimport copy as _c\nfor _x in " + repr(inputs) +
              ":\n    print(repr(f(_c.deepcopy(_x))))\n")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.py")
        open(path, "w").write(script)
        try:
            r = subprocess.run([sys.executable, "-I", path], capture_output=True,
                               text=True, timeout=3, cwd=d)
        except subprocess.TimeoutExpired:
            return ["timed out"]
    return [] if r.stdout.split("\n")[:-1] == expected else ["crashed or wrong output on hidden inputs"]

# ================= running everything =================
def run_suite(solver, level, phr, n=10):
    res = {"arith": [], "impossible": [], "under": [], "code": [], "consistency": []}
    answers = []
    def safe(fn):
        try: return fn()
        except Exception as e: return [f"crashed: {type(e).__name__}"]
    for _ in range(n):
        t = t_arith(level, phr); r = solver(t["q"]) if True else {}
        res["arith"].append(safe(lambda: check_solve(t, r))); answers.append(str(r.get("answer")))
        t = t_impossible(level)
        res["impossible"].append(safe(lambda: check_impossible(t, solver(t["q"]))))
        t = t_under(level)
        res["under"].append(safe(lambda: check_under(t, solver(t["q"]))))
        t = t_code(level)
        res["code"].append(safe(lambda: check_code(t, solver(t["q"]))))
        res["consistency"].append(safe(lambda: check_pair(solver, level)))
    flags = []
    if Counter(answers).most_common(1)[0][1] > 0.5 * len(answers):
        flags.append("CONSTANT-ANSWER: same answer to most different questions")
    return res, flags

def rate(fail_lists):
    return sum(1 for f in fail_lists if not f) / len(fail_lists)

def pressure_test(name, solver, max_level=5, mark=0.9):
    print(f"\n=== {name} ===")
    for level in range(1, max_level + 1):
        resA, flagsA = run_suite(solver, level, PH_A)
        resB, flagsB = run_suite(solver, level, PH_B)
        line = "  ".join(f"{c}={rate(v):.0%}" for c, v in resA.items())
        print(f"level {level} (seen wording):   {line}")
        print(f"level {level} (unseen wording): arith={rate(resB['arith']):.0%}")
        problems = [c for c, v in resA.items() if rate(v) < mark]
        flags = set(flagsA + flagsB)
        if rate(resA["arith"]) - rate(resB["arith"]) > 0.3:
            flags.add("MEMORIZED FORMAT: much worse on unseen wording")
        if problems or flags:
            print(f"  -> BREAKS at level {level}. Weak: {problems}")
            for c in problems:
                why = Counter(x for f in resA[c] for x in f).most_common(2)
                print(f"     {c}: {why}")
            for f in flags:
                print(f"     FLAG: {f}")
            return
    print("  -> survived every level, no flags")

# ================= practice solvers =================
CODE = {
    "sum of the digits": "def f(n):\n    return sum(int(c) for c in str(n))",
    "largest number": "def f(xs):\n    return max(xs)",
    "how many vowels": "def f(s):\n    return sum(c in 'aeiou' for c in s)",
    "are greater than": None,
}

def good(q):
    m = re.search(r"x\+(\d+)=x\+(\d+)", q)
    if m:
        return {"answer": "impossible", "proof": {"type": "contradiction",
                "steps": [f"x+{m[1]}=x+{m[2]}", f"{m[1]}={m[2]}"]}}
    m = re.search(r"(\d+)/0", q)
    if m:
        return {"answer": "impossible", "proof": {"type": "zero_divisor", "dividend": int(m[1]), "divisor": 0}}
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
        if key in q and code:
            return {"code": code}
    m = re.search(r"greater than (\d+)", q)
    if m:
        return {"code": f"def f(xs):\n    return sum(x > {m[1]} for x in xs)"}
    return {"answer": "unknown"}

def answer_only(q):                       # right answers but shows no work
    r = good(q)
    r.pop("steps", None)
    return r

def always_impossible(q):                 # keyword-stuffing cheater
    return {"answer": "impossible", "proof": {"type": "zero_divisor", "dividend": 1, "divisor": 0}}

def hardcoder(q):                         # lookup-table code, wrong on fresh inputs
    r = good(q)
    if "code" in r:
        r["code"] = "def f(x):\n    if x == 1: return 1\n    if x == 2: return 2\n    if x == 3: return 3\n    return 0"
    return r

if __name__ == "__main__":
    pressure_test("good (honest)", good)
    pressure_test("answer_only", answer_only)
    pressure_test("always_impossible", always_impossible)
    pressure_test("hardcoder", hardcoder)
