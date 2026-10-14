"""Tamper tests for G10 successor proposals (no network, no model)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import g10_evaluator  # noqa: E402
import g10_task_bank  # noqa: E402
from genesis.evolution import recursive_chain  # noqa: E402
from genesis.evolution.recursive_chain import RecursiveChainError  # noqa: E402
from genesis.trust_root import digest_of  # noqa: E402

G9 = json.loads((ROOT / "experiment/g9_qualification/SUCCESSOR.json").read_text())
SPECIALIST = json.loads((ROOT / "experiment/g8_qualification/SPECIALIST.json").read_text())["specialist"]


def _copy(obj):
    return json.loads(json.dumps(obj))


def redigest(p):
    p.pop("proposal_digest", None)
    p["proposal_digest"] = digest_of(p)
    return p


def _holders(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            yield obj
        for v in obj.values():
            yield from _holders(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from _holders(v, key)


def _set_everywhere(obj, key, value):
    holders = list(_holders(obj, key))
    assert holders, f"key {key!r} not found in proposal"
    for h in holders:
        h[key] = value


def _bump(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value + 1
    return f"{value}-tampered"


def _tamper_path(p, path):
    node = p
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = _bump(node[path[-1]])


_GAP_REASON = (
    "known gap: validate_proposal only checks the global proposal_digest "
    "and does not re-derive material_change / discovery_digest"
)


@pytest.fixture(scope="module")
def proposal():
    seed = recursive_chain.build_seed_profile(G9)
    bank = g10_task_bank.build_bank(
        SPECIALIST, stage=1, purpose="discovery", seed=11001
    )
    measure = g10_evaluator.evaluate_profile(
        ROOT, seed, bank, max_candidates_per_case=6
    )
    evidence = g10_evaluator.build_discovery_evidence(measure)
    return recursive_chain.induce_successor(seed, evidence)


def test_intact_proposal_validates(proposal):
    recursive_chain.validate_proposal(_copy(proposal))


@pytest.mark.parametrize(
    "path", [("discovery_digest",), ("material_change", "to_level")]
)
def test_tamper_without_redigest_rejected(proposal, path):
    p = _copy(proposal)
    _tamper_path(p, path)
    with pytest.raises(RecursiveChainError):
        recursive_chain.validate_proposal(p)


@pytest.mark.parametrize(
    "key,value",
    [
        ("lineage_produced", False),
        ("prospective_holdout_visible", True),
        ("mutable_lineage_owns_verdict", True),
    ],
)
def test_semantic_tamper_with_redigest_rejected(proposal, key, value):
    p = _copy(proposal)
    _set_everywhere(p, key, value)
    redigest(p)
    with pytest.raises(RecursiveChainError):
        recursive_chain.validate_proposal(p)


def test_forged_parent_rejected(proposal):
    p = _copy(proposal)
    sp = p["successor_profile"]
    sp["parent_profile_digest"] = "0" * 64
    sp.pop("profile_digest", None)
    sp["profile_digest"] = digest_of(sp)
    redigest(p)
    with pytest.raises(RecursiveChainError, match="does not name supplied parent"):
        recursive_chain.validate_proposal(p)


@pytest.mark.xfail(strict=True, raises=pytest.fail.Exception, reason=_GAP_REASON)
def test_known_gap_material_change_to_level(proposal):
    p = _copy(proposal)
    _tamper_path(p, ("material_change", "to_level"))
    redigest(p)
    with pytest.raises(RecursiveChainError):
        recursive_chain.validate_proposal(p)


@pytest.mark.xfail(strict=True, raises=pytest.fail.Exception, reason=_GAP_REASON)
def test_known_gap_discovery_digest(proposal):
    p = _copy(proposal)
    _tamper_path(p, ("discovery_digest",))
    redigest(p)
    with pytest.raises(RecursiveChainError):
        recursive_chain.validate_proposal(p)
