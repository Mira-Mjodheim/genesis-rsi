"""The second improver: ask the model for a better program, with evaluation feedback, keep it when it scores higher.

Everything an improver is lies in this file: it is handed to itself as the program to improve.
"""
import re


def extract(reply):
    """The longest fenced block of the answer that parses as Python, or None. A program may itself
    contain fences, so the span from the first opening fence to the last closing one is tried too.
    If no fenced block compiles, the whole reply is tried."""
    blocks = re.findall(r"```(?:python|py)?\n(.*?)```", reply, re.S)
    blocks += re.findall(r"```(?:python|py)?\n(.*)```", reply, re.S)
    blocks.append(reply)
    for block in sorted(blocks, key=len, reverse=True):
        try:
            compile(block, "candidate.py", "exec")
            return block
        except SyntaxError:
            continue
    return None


def improve(task, lm, budget):
    best = task.initial
    try:
        res = task.evaluate(best)
        best_score = float(res.score)
        best_details = str(res.details)
    except Exception as e:
        best_score = float("-inf")
        best_details = f"Evaluation of the starting program failed: {e!r}"
    feedback = ""

    while budget.lm_calls_left > 0 and budget.evaluations_left > 0 and budget.seconds_left > 0:
        prompt = (
            "You are improving a program.\n\n" + task.description
            + f"\n\nCurrent best program (score {best_score:.4f}, higher is better):\n```python\n{best}\n```\n\n"
            "Evaluation details of the current best program:\n"
            + best_details[:3000] + "\n\n"
            + (feedback + "\n\n" if feedback else "")
            + "Write a program that scores higher than the current best. "
            "Keep the same interface. Answer with the complete program in one ```python block."
        )
        reply = lm(prompt)
        candidate = extract(reply)
        if candidate is None:
            feedback = ("Your last answer contained no valid Python program. "
                        "Answer with the complete program in one ```python block.")
            continue
        if budget.evaluations_left <= 0:
            break
        try:
            res = task.evaluate(candidate)
            score = float(res.score)
            details = str(res.details)
        except Exception as e:
            feedback = f"Your last candidate failed to run with error: {e!r}. Fix this error."
            continue
        if score > best_score:
            best, best_score, best_details = candidate, score, details
            feedback = ""
        else:
            feedback = (f"Your last candidate scored {score:.4f}, which is not better than the current best. "
                        f"Its details:\n{details[:1500]}")
    return best
