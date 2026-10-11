"""The fourth improver: each model request asks for several differing targeted variants, every
parseable variant is evaluated while evaluations remain, and failed attempts are fed back.

Everything an improver is lies in this file: it is handed to itself as the program to improve.
"""
import re


def _compiles(src):
    try:
        compile(src, "candidate.py", "exec")
        return True
    except Exception:
        return False


def extract_blocks(reply):
    """All fenced blocks of the answer that parse as Python, in order, without duplicates.
    If none parse, the span from the first opening fence to the last closing one is tried,
    then the whole reply as a bare program."""
    reply = reply or ""
    out = []
    for b in re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", reply, re.S):
        if _compiles(b) and b not in out:
            out.append(b)
    if not out:
        for b in re.findall(r"```(?:python|py)?[ \t]*\n(.*)```", reply, re.S):
            if _compiles(b) and b not in out:
                out.append(b)
    if not out and _compiles(reply):
        out.append(reply)
    return out


def _clip(text, n=1500):
    text = str(text)
    return text if len(text) <= n else text[:n] + "\n...[truncated]"


def _score(res):
    try:
        return float(res.score)
    except Exception:
        return float("-inf")


def _left(budget, name):
    try:
        return getattr(budget, name)
    except Exception:
        return 10 ** 9


def improve(task, lm, budget):
    best = task.initial
    best_score = float("-inf")
    best_details = ""
    try:
        res = task.evaluate(best)
        best_score = _score(res)
        best_details = res.details
    except Exception as e:
        best_details = f"Evaluation of the starting program failed: {e}"

    history = []  # failed attempts: (label, details, source)

    while _left(budget, "lm_calls_left") > 0 and _left(budget, "evaluations_left") > 0:
        if _left(budget, "seconds_left") < 5:
            break

        recent = ""
        for label, info, src in history[-3:]:
            recent += (
                f"- Attempt {label}. Its details:\n{_clip(info, 700)}\n"
                f"  Its code (clipped):\n```python\n{_clip(src, 1000)}\n```\n"
            )
        if not recent:
            recent = "(none yet)\n"

        prompt = (
            "You are improving a program.\n\n" + task.description
            + f"\n\nCurrent best program (score {best_score:.4f}):\n```python\n{best}\n```\n\n"
            + f"Its per-instance results:\n{_clip(best_details)}\n\n"
            + f"Recent failed attempts:\n{recent}\n"
            + "Write up to three alternative complete programs that score higher than the current best. "
              "Each must be a targeted change aimed at the weakest part shown in the per-instance results, "
              "and the three should differ from each other in the change they make; do not rewrite what "
              "already works. Keep the same interface, make sure each runs without errors, and keep the "
              "running time modest. Put each complete program in its own ```python block, with at most "
              "one short sentence before it describing the change."
        )

        try:
            reply = lm(prompt)
        except Exception:
            break

        cands = extract_blocks(reply)
        if not cands:
            history.append(("with no valid Python code", "The answer contained no parseable Python program.", ""))
            continue

        for cand in cands[:3]:
            if _left(budget, "evaluations_left") <= 0:
                break
            try:
                res = task.evaluate(cand)
            except Exception as e:
                history.append(("that raised an exception", f"Exception: {e}", cand))
                continue

            score = _score(res)
            if score > best_score:
                best, best_score, best_details = cand, score, res.details
            else:
                history.append((f"with score {score:.4f}", res.details, cand))

    return best
