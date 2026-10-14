# PART 1: THE TASKS
# Makes brand-new random questions every time, so memorizing can't pass.
# Run this file alone:  python p1_tasks.py   (it just prints example tasks)
import random, copy

# Two sets of wordings. Set B is "unseen": if an AI does much worse on B than
# on A, it memorized formats instead of learning the skill.
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


if __name__ == "__main__":
    print("PART 1 check: here is one task of each kind (run again for new ones)\n")
    print("arith (seen wording):  ", t_arith(1, PH_A)["q"])
    print("arith (unseen wording):", t_arith(1, PH_B)["q"])
    print("impossible:            ", t_impossible(1)["q"])
    print("under-specified:       ", t_under(1)["q"])
    print("code:                  ", t_code(1)["q"])
    print("\nRun it twice. If the numbers change each time, it works.")
