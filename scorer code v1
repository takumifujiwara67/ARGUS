import random
import re

def make_tasks():
    tasks = []
    for _ in range(5):                                   # new numbers every run
        a, b = random.randint(1, 99), random.randint(1, 99)
        tasks.append({"q": f"What is {a} + {b}?", "kind": "solvable", "answer": str(a + b)})
    tasks.append({"q": "What is 5 / 0?", "kind": "impossible", "reason": "zero"})
    tasks.append({"q": "Find an integer x where x + 1 = x.", "kind": "impossible", "reason": "no integer"})
    return tasks

def check(task, reply):
    if task["kind"] == "solvable":
        return reply["answer"] == task["answer"]
    # impossible: must say so AND give the right reason
    said_impossible = reply["answer"] == "impossible"
    gave_reason = task["reason"] in reply["explanation"].lower()
    return said_impossible and gave_reason

def score(solver):
    tasks = make_tasks()
    passed = 0
    for t in tasks:
        ok = check(t, solver(t["q"]))
        passed += ok
        print("PASS" if ok else "FAIL", "-", t["q"])
    print(f"Score: {passed}/{len(tasks)}\n")

# two test "AIs" so you can see the scorer working
def lazy_solver(q):
    return {"answer": "0", "explanation": ""}

def good_solver(q):
    m = re.match(r"What is (\d+) \+ (\d+)\?", q)
    if m:
        return {"answer": str(int(m[1]) + int(m[2])), "explanation": ""}
    if "/ 0" in q:
        return {"answer": "impossible", "explanation": "Dividing by zero is undefined."}
    if "x + 1 = x" in q:
        return {"answer": "impossible", "explanation": "No integer equals itself plus one, so there is no solution."}
    return {"answer": "unknown", "explanation": ""}

print("Lazy solver:")
score(lazy_solver)
print("Good solver:")
score(good_solver)
