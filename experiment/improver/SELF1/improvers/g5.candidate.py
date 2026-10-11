"""Improver v3: parallel rounds with model feedback. Each round asks the model for two candidates
concurrently, evaluates every parseable candidate, and keeps the best one. The details of the
round's best attempt (or the current best, if none was evaluated) are shown in the next request.
Only strictly better candidates replace the current best."""
import re
from concurrent.futures import ThreadPoolExecutor


def extract(reply):
    """The longest fenced block of the answer that compiles as Python, or None. The span from the
    first opening fence to the last closing one is tried too, since a program may contain fences."""
    blocks = re.findall(r"```(?:python|py)?\n(.*?)```", reply, re.S)
    blocks += re.findall(r"```(?:python|py)?\n(.*)```", reply, re.S)
    for block in sorted(blocks, key=len, reverse=True):
        try:
            compile(block, "candidate.py", "exec")
            return block
        except SyntaxError:
            continue
    return None


def _clip(text, n=3000):
    text = str(text)
    return text if len(text) <= n else text[:n] + "\n...[truncated]"


def improve(task, lm, budget):
    best = task.initial
    try:
        first = task.evaluate(best)
        best_score = first.score
        feedback = "Result of the current best program:\n" + _clip(first.details)
    except Exception as e:
        best_score = float("-inf")
        feedback = f"The current program could not be evaluated: {e}"

    while budget.lm_calls_left > 0 and budget.evaluations_left > 0:
        if budget.seconds_left is not None and budget.seconds_left <= 0:
            break
        k = min(2, budget.lm_calls_left, budget.evaluations_left)
        if k <= 0:
            break
        score_txt = "-inf" if best_score == float("-inf") else f"{best_score:.4f}"
        prompt = (
            "You are improving a program.\n\n" + task.description
            + f"\n\nCurrent best program (score {score_txt}):\n```python\n{best}\n```\n\n"
            + "Feedback from the last evaluation:\n" + _clip(feedback) + "\n\n"
            "Write a program that scores higher than the current best. Keep the required interface, "
            "use only the standard library, make sure it runs without errors on all instances, and "
            "keep it within time limits. Fix any errors shown in the feedback. "
            "Answer with the complete program in one ```python block."
        )

        def ask(_):
            try:
                return lm(prompt)
            except Exception:
                return None

        try:
            with ThreadPoolExecutor(max_workers=k) as pool:
                replies = list(pool.map(ask, range(k)))
        except Exception:
            break

        round_best = None  # (score, details)
        notes = []
        for reply in replies:
            if reply is None:
                notes.append("A request failed.")
                continue
            candidate = extract(reply)
            if candidate is None:
                notes.append("A reply contained no parseable ```python block.")
                continue
            if budget.evaluations_left <= 0:
                break
            try:
                result = task.evaluate(candidate)
            except Exception as e:
                notes.append(f"A candidate raised an error during evaluation: {e}")
                continue
            if result.score > best_score:
                best, best_score = candidate, result.score
                feedback = "New best. Result:\n" + _clip(result.details)
                round_best = None
                continue
            if round_best is None or result.score > round_best[0]:
                round_best = (result.score, result.details)

        if round_best is not None:
            feedback = (
                f"The last candidate scored {round_best[0]:.4f}, not better than {best_score:.4f}. "
                "Its result:\n" + _clip(round_best[1])
            )
        elif notes and not feedback.startswith("New best"):
            feedback = " ".join(notes) + "\n" + feedback
        elif notes:
            feedback = " ".join(notes) + "\n" + feedback

    return best
