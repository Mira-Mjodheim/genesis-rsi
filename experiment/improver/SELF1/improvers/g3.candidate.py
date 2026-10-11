"""The second improver: ask the model for a better program, with evaluation feedback, keep it when it scores higher.

Everything an improver is lies in this file: it is handed to itself as the program to improve.
"""
import re


def extract(reply):
    """The longest fenced block of the answer that parses as Python, or None. A program may itself
    contain fences, so the span from the first opening fence to the last closing one is tried too."""
    blocks = re.findall(r"```(?:python|py)?\n(.*?)```", reply, re.S)
    blocks += re.findall(r"```(?:python|py)?\n(.*)```", reply, re.S)
    for block in sorted(blocks, key=len, reverse=True):
        try:
            compile(block, "candidate.py", "exec")
            return block
        except SyntaxError:
            continue
    return None


def _clip(text, limit=3000):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "\n...(truncated)"


def improve(task, lm, budget):
    best = task.initial
    res = task.evaluate(best)
    best_score = res.score
    best_details = res.details
    feedback = ""

    while budget.lm_calls_left > 0 and budget.evaluations_left > 0 and budget.seconds_left > 0:
        prompt = (
            "You are improving a program.\n\n" + task.description
            + f"\n\nCurrent best program (score {best_score:.4f}):\n```python\n{best}\n```\n\n"
            + "Evaluation details of the current best program:\n" + _clip(best_details, 2000) + "\n\n"
            + (("Feedback on your previous attempt:\n" + feedback + "\n\n") if feedback else "")
            + "Write a program that scores higher. Keep the same interface and any required function names. "
              "Answer with the complete program in one ```python block."
        )
        try:
            reply = lm(prompt)
        except Exception:
            break

        candidate = extract(reply)
        if candidate is None:
            feedback = "Your last answer contained no valid Python block. Answer with one ```python block."
            continue

        if budget.evaluations_left <= 0:
            break
        try:
            r = task.evaluate(candidate)
        except Exception as e:
            feedback = "Evaluating your program raised an exception: " + repr(e)
            continue

        try:
            better = r.score > best_score
        except Exception:
            better = False

        if better:
            best, best_score, best_details = candidate, r.score, r.details
            feedback = ""
        else:
            feedback = (f"Your last program scored {r.score:.4f}, not better than {best_score:.4f}. "
                        "Its evaluation details:\n" + _clip(r.details, 2000))
    return best
