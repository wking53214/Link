"""The anti-laundering gate for agent memory."""

from __future__ import annotations

import pytest
from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.errors import ConstitutionViolation

from link.memory_gate import LaunderingRefused, MemoryGate

GUESS = "the cache is why latency doubled"


def _human_hold(system, artifact_id, status=EpistemicStatus.EVIDENCE):
    system.classify(artifact_id, status, actor=Actor.human(), reason="a human adopted it")


def test_a_models_output_comes_back_advisory_with_its_origin():
    gate = MemoryGate(CCCSystem())
    gate.remember(GUESS, model_id="planner")
    (claim,) = gate.recall()
    assert claim.premise is False
    assert claim.origin == "model:planner"
    assert claim.status == "UNKNOWN"


def test_advisory_claims_are_refused_as_premises_and_a_second_model_cannot_launder_them():
    gate = MemoryGate(CCCSystem())
    first = gate.remember(GUESS, model_id="planner")
    gate.remember(f"building on: {GUESS}", model_id="critic")
    claims = gate.recall()
    with pytest.raises(LaunderingRefused) as info:
        gate.require_premises(claims)
    assert {c.artifact_id for c in info.value.claims} >= {first}
    assert gate.recall(premises_only=True) == []


def test_a_human_promotion_makes_it_a_premise():
    system = CCCSystem()
    gate = MemoryGate(system)
    aid = gate.remember(GUESS, model_id="planner")
    _human_hold(system, aid)
    (claim,) = gate.recall(premises_only=True)
    assert claim.premise and claim.origin == "model:planner"
    assert gate.require_premises([claim]) == [claim]


def test_a_machine_cannot_promote_a_claim_itself():
    system = CCCSystem()
    gate = MemoryGate(system)
    aid = gate.remember(GUESS, model_id="planner")
    with pytest.raises(ConstitutionViolation):
        system.classify(aid, EpistemicStatus.EVIDENCE, actor=Actor.model("planner"), reason="trust me")
    assert gate.recall(premises_only=True) == []


def test_an_erased_claim_is_no_longer_recalled_and_a_held_premise_is_refused_after_retraction():
    system = CCCSystem()
    gate = MemoryGate(system)
    aid = gate.remember(GUESS, model_id="planner")
    _human_hold(system, aid)
    (claim,) = gate.recall(premises_only=True)
    system.erase(aid, actor=Actor.human(), reason="withdrawn", authorization_basis="test")
    assert gate.recall() == []
    with pytest.raises(LaunderingRefused):
        gate.require_premises([claim])


def test_a_demoted_premise_is_refused():
    system = CCCSystem()
    gate = MemoryGate(system)
    aid = gate.remember(GUESS, model_id="planner")
    _human_hold(system, aid)
    (claim,) = gate.recall(premises_only=True)
    _human_hold(system, aid, EpistemicStatus.UNKNOWN)
    with pytest.raises(LaunderingRefused):
        gate.require_premises([claim])


def test_topics_filter_and_rendering_carries_the_label():
    system = CCCSystem()
    gate = MemoryGate(system)
    a = gate.remember(GUESS, model_id="planner", topics=("perf",))
    gate.remember("unrelated", model_id="planner", topics=("docs",))
    _human_hold(system, a)
    claims = gate.recall(topics=["perf"])
    assert [c.text for c in claims] == [GUESS]
    assert gate.render(claims).startswith("[PREMISE (human-held)]")
    advisory = gate.render(gate.recall(topics=["docs"]))
    assert "ADVISORY" in advisory and "not a fact" in advisory


def test_it_needs_a_real_ccc_system():
    with pytest.raises(TypeError):
        MemoryGate(object())
