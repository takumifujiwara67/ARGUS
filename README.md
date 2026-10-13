<img width="900" height="340" alt="architecture" src="https://github.com/user-attachments/assets/2adf60a9-53a0-4903-ba21-6fab8346cdc2" />

# Argus

A scorer that watches how an AI gets its answer, not just what it answers.

Most AI tests only ask one question: is the final answer right? An AI can pass that by guessing, memorizing the test, or special-casing it.

Argus, named after the hundred-eyed giant of Greek myth who never slept, checks how the AI got there. Is the work it shows actually true? Can it prove an impossible task is impossible instead of bluffing? Does it stay consistent when the question changes slightly? Then it turns the difficulty up, level by level, until the AI breaks. The result is simple: PASS or FAIL, plus exactly where and why.

No installs, no PyTorch, no pip. Python 3.8+ and nothing else.

## The result

| Result | What it means |
|--------|----------------|
| PASS   | Survived every level, no flags |
| FAIL   | Broke at some level. The report says which level and what failed |

## How it works

The judge is plain Python, not another AI, so it cannot be talked into a pass. Every question is generated fresh from random numbers, so memorized answers don't help.

## Tricks it catches

| The trick | What catches it |
|-----------|------------------|
| Memorizing answers | Fresh random numbers on every run |
| Right answer, no reasoning | The work must be shown, and every step is checked |
| Restating the answer as "work" | Each step must be ONE operation on two numbers, using only numbers from the question or earlier steps. Multi-step questions like 3+4*5 can't be answered in one step |
| Judging a question by how it looks | Look-alike traps: 0/7 and 12/4 look like division by zero but aren't, and x+3=x+3 looks like a contradiction but is true for every x |
| Saying "impossible" to everything | It needs a valid proof, and it still has to solve the solvable tasks |
| Stuffing keywords like "zero" or "cannot" | Proofs are checked by structure, so keywords count for nothing |
| Inventing a number when information is missing | "what is x+5?" must get "insufficient" |
| Only working on familiar phrasing | The same skill is retested with new wording; a big gap raises a flag |
| Hardcoding outputs in code | Code is scanned for lookup tables, then run on fresh hidden inputs |
| Falling apart on harder numbers | The pressure test raises the level until it breaks |
| Contradicting itself | a+b, a+(b+1) and b+a must agree |

## Quick start

Put all the p files in one folder, open a terminal there, and run:

```bash
python p2_judge.py        # the judge tests itself: "All verdicts as expected."
python p4_practice.py     # hand-written pretend AIs: the honest one passes, the cheaters fail
python p7_leaderboard.py  # ranks all the pretend AIs and saves leaderboard.md
```

On Windows, use `py` if `python` is not recognized.

## Test a real AI

Open `p6_try_it.py`, remove the `#` in front of one line, and fill in your AI:

```python
raw = from_ollama("qwen2.5-coder:1.5b")                                   # a local Ollama model
raw = from_openai_compatible("http://localhost:1234/v1", "model-name")    # LM Studio, llama.cpp, OpenAI...
raw = from_command(["./my_ai"])                                           # any program: prompt on stdin, reply on stdout
```

Then run `python p6_try_it.py`.

The bridge tells the AI the exact JSON answer format, sends each question, and pulls the JSON out of the reply, even through extra chatter and code fences. A reply that isn't valid JSON counts as a fail. A call budget stops the test early so a paid API can't run up a bill, and it stops with a clear message if the AI can't be reached. API keys are read from the environment (OPENAI_API_KEY), never written into files.

## Leaderboard

`p7_leaderboard.py` tests several AIs one after another and writes `leaderboard.md`, a table you can paste straight into your README. Add real models like this:

```python
contestants["qwen 1.5b"] = Bridge(from_ollama("qwen2.5-coder:1.5b"))
```

The AIs in the picture at the top are hand-written pretend AIs that ship with the repo, not real models.

## Files

| File | What it does |
|------|---------------|
| p1_tasks.py | Makes fresh random questions |
| p2_judge.py | Decides PASS or FAIL for each reply, and tests itself |
| p3_runner.py | The pressure test and the PASS or FAIL result |
| p4_practice.py | Pretend AIs (one honest, one that breaks under pressure, five cheaters) that prove the scorer works |
| p5_bridge.py | Connects any AI to the scorer |
| p6_try_it.py | The file you edit to test a real AI |
| p7_leaderboard.py | Ranks several AIs and saves the table |

## Known limitations

This is version 1. It makes common shortcuts hard, not impossible.

- Narrow coverage. It tests arithmetic, simple equations, impossible or under-specified questions, and small Python functions. It says nothing about other skills.
- It checks the work, not the mind. Steps must form a valid chain from the question to the answer, but nobody can see how an AI really got there. An AI that quietly uses a calculator and writes valid steps will pass.
- The code sandbox is not a real sandbox. It uses a throwaway folder, a 3 second timeout and banned names, nothing more. Only run code from AIs you trust, ideally inside Docker or a virtual machine.
- Format counts. Replies that aren't the requested JSON fail, so the score partly measures instruction following.
- Small samples are noisy. With n=5 results can vary between runs, and flags are hints, not proof. Use n=10 or more when comparing AIs.
- The adapters were tested against local fake servers, not against every real service.

## Break it

Found a way to pass without really solving the task? Open an issue. Every hole found becomes a new check.

## Roadmap

- More task types, including C++ tasks
- A training loop that feeds an AI's failures back into its training
- A real container for running generated code
