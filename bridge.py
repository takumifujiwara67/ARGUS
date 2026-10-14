# PART 5: THE BRIDGE
# Connects ANY AI that somebody else made to the scorer.
#
# The scorer needs a function:   solver(question) -> dict
# Other people's AIs are different: they take a prompt and return text.
# So the bridge does three jobs:
#   1. wraps each question in instructions that explain the answer format
#   2. sends it to the AI through an "adapter" (function, Ollama, API, or program)
#   3. pulls the JSON out of the AI's reply and hands the dict to the judge
#
# Run this file alone:  python p5_bridge.py   (tests the bridge with pretend AIs)
import json, os, re, subprocess, sys, urllib.error, urllib.request

PROMPT = """You are being tested by a strict automatic judge.
Reply with ONE JSON object and nothing else. Pick the format that fits the question.

1) A normal math question (add, subtract, multiply, or find x):
   {"answer": "<final number>", "steps": ["<numbers and + - * only> = <result>", ...]}
   Every step must be a TRUE equation, e.g. "20+35 = 55". The last result must equal the answer.
   For a "find x" question, write the arithmetic that gives x, e.g. "12-5 = 7".

2) A question that is impossible:
   - dividing by zero:
     {"answer": "impossible", "proof": {"type": "zero_divisor", "dividend": <number>, "divisor": 0}}
   - an equation with no solution, like x+3=x+5:
     {"answer": "impossible", "proof": {"type": "contradiction", "steps": ["x+3=x+5", "3=5"]}}

3) A question with not enough information (it contains an unknown like x):
   {"answer": "insufficient", "missing": "x"}

4) A request to write a Python function:
   {"code": "def f(...):\\n    ..."}
   Use only the standard modules math, re, collections, itertools. No file access.

Question: {q}"""


class StopTest(BaseException):
    """raised to stop the whole test (call budget used up, or the AI is unreachable)"""


# ---------- reading the AI's reply ----------
def extract_json(text):
    """find the first JSON object in the reply, even inside ```json fences or chatter"""
    dec = json.JSONDecoder()
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
    def __init__(self, raw_ask, max_calls=300):
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


def from_ollama(model, url="http://localhost:11434"):
    """a model running locally in Ollama (ollama.com)"""
    def raw_ask(prompt):
        r = _post_json(f"{url}/api/generate",
                       {"model": model, "prompt": prompt, "stream": False,
                        "options": {"temperature": 0}})
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


# ---------- pretend AIs so you can test the bridge without installing anything ----------
def demo_chat_ai(prompt):
    """behaves like a chatty, decent AI: right answers, wrapped in ```json fences + small talk"""
    from p4_practice import good
    q = prompt.split("Question:")[-1].strip()
    return "Sure! Here is my answer:\n```json\n" + json.dumps(good(q)) + "\n```\nHope that helps."


def sloppy_chat_ai(prompt):
    """a chatty AI that ignores the format and answers in plain sentences"""
    return "I think the answer is probably around 42, but I am not totally sure."


if __name__ == "__main__":
    from p3_runner import pressure_test
    print("PART 5 check: the bridge with two pretend AIs.")
    print("Expected: the chatty-but-correct AI survives, the sloppy one breaks.")
    b1 = Bridge(from_function(demo_chat_ai))
    pressure_test("pretend AI that follows the format", b1, max_level=2, n=5)
    b1.report()
    b2 = Bridge(from_function(sloppy_chat_ai))
    pressure_test("pretend AI that ignores the format", b2, max_level=1, n=5)
    b2.report()
