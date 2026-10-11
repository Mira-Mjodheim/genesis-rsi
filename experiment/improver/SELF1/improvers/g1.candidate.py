"""The third improver: each model request asks for up to two alternative programs; every valid
candidate is evaluated while evaluations remain, and a candidate is kept only when it scores higher.
The source and details of the last rejected candidate are shown to the model as well.

Everything an improver is lies in this file: it is handed to itself as the program to improve.
"""
import re


def extract_all(reply):
    """All distinct fenced blocks of the answer that parse as Python, longest first. If none is found
    separately, the span from the first opening fence to the last closing one is tried."""
    if not isinstance(reply, str):
        return []
    blocks = re.findall(r"```(?:python|py)?\n(.*?)```", reply, re.S)
    blocks += re.findall(r"```(?:python|py)?\n(.*)```", reply, re.S)
    out = []
    for block in sorted(blocks, key=len, reverse=True):
        if block in out:
            continue
        try:
            compile(block, "candidate.py", "exec")
            out.append(block)
        except SyntaxError:
            continue
    return out


def _num(x):
    try:
        v = float(x)
        return v if v == v else float("-inf")
    except Exception:
        return float("-inf")


def _clip(text, n=2500):
    text = str(text)
    return text if len(text) <= n else text[:n] + "\n...(truncated)"


def improve(task, lm, budget):
    best = task.initial
    try:
        first = task.evaluate(best)
        best_score = _num(first.score)
        feedback = _clip(first.details)
    except Exception as e:
        best_score = float("-inf")
        feedback = f"The starting program failed to evaluate: {e!r}"

    history = []
    last_rejected = None  # (score, source)
    while budget.lm_calls_left > 0 and budget.evaluations_left > 0:
        try:
            if budget.seconds_left is not None and budget.seconds_left < 5:
                break
        except Exception:
            pass
        prompt = (
            "You are improving a program.\n\n" + task.description
            + f"\n\nCurrent best program (score {best_score:.4f}):\n```python\n{best}\n```\n\n"
            + "Evaluation details of the current best program:\n" + feedback + "\n\n"
        )
        if last_rejected is not None:
            prompt += ("The last rejected candidate (score %.4f):\n```python\n%s\n```\n\n"
                       % (last_rejected[0], _clip(last_rejected[1], 3000)))
        if history:
            prompt += "Scores of previous rejected candidates: " + ", ".join(
                f"{s:.4f}" for s in history[-8:]) + "\n\n"
        prompt += (
            "Identify what limits the score in the details (weak instances, errors, slow or "
            "suboptimal choices), then write two different complete programs that score higher, "
            "the most promising first. Keep the required interface unchanged. Keep the programs "
            "compact. Answer with each complete program in its own ```python block."
        )
        try:
            reply = lm(prompt)
        except Exception:
            break

        cands = extract_all(reply)
        if not cands:
            feedback = ("Your last answer contained no valid Python block. Reply with ```python "
                        "blocks holding complete programs.")
            continue
        for cand in cands:
            if budget.evaluations_left <= 0:
                break
            if cand == best:
                continue
            try:
                result = task.evaluate(cand)
            except Exception as e:
                feedback = f"Your last candidate raised an error during evaluation: {e!r}"
                continue
            score = _num(result.score)
            if score > best_score:
                best, best_score = cand, score
                feedback = _clip(result.details)
                last_rejected = None
            else:
                history.append(score)
                last_rejected = (score, cand)
                feedback = ("The last candidate scored %.4f, not better than the best. Its details:\n%s"
                            % (score, _clip(result.details, 1500)))
    return best
