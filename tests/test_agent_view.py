"""AgentView: an independent witness for what an agent declares it stands on."""

from __future__ import annotations

import pytest
from ccc import Actor, CCCSystem, EpistemicStatus

from link.grounding import (
    AT_RISK,
    FLOATING,
    GROUNDED,
    ORPHANED,
    GroundedMemory,
    Ungrounded,
    UnreadSupport,
)


def _setup():
    system = CCCSystem(allow_unguarded_writes=True, allow_unverified_humans=True)
    return system, GroundedMemory(system)


def _human_fact(system, memory, text="latency doubled right after deploy 41", topics=("perf",)):
    aid = memory.note(text, model_id="scribe", supports=(), topics=topics)
    system.classify(aid, EpistemicStatus.EVIDENCE, actor=Actor.human(), reason="a person checked the graph")
    return aid


def _erase(system, aid):
    system.erase(aid, actor=Actor.human(), reason="withdrawn", authorization_basis="test")


def test_supports_must_always_be_given_and_empty_is_the_honest_answer():
    _, memory = _setup()
    view = memory.agent("planner")
    with pytest.raises(TypeError):
        view.note("a note")  # forgetting to say what it stands on is an error, not a silent default
    aid = view.note("a note standing on nothing", supports=())
    assert memory.grounding(aid).grounding == FLOATING


def test_an_agent_cannot_claim_support_from_something_it_never_read():
    system, memory = _setup()
    root = _human_fact(system, memory)
    view = memory.agent("planner")
    before = len(system.store.artifacts)
    with pytest.raises(UnreadSupport):
        view.note("the cache is the cause", supports=[root])  # claims a root it never saw
    assert len(system.store.artifacts) == before  # nothing written


def test_an_agent_that_read_and_declared_gets_the_normal_grounded_result():
    system, memory = _setup()
    root = _human_fact(system, memory)
    view = memory.agent("planner")
    view.recall(topics=["perf"])
    aid = view.note("the cache is the cause", supports=[root])
    claim = memory.grounding(aid)
    assert claim.grounding == GROUNDED and claim.roots == (root,)


def test_reading_without_declaring_leaves_a_note_at_risk_once_the_read_claim_is_withdrawn():
    system, memory = _setup()
    root = _human_fact(system, memory)
    view = memory.agent("planner")
    view.recall(topics=["perf"])
    sneaky = view.note("so roll back the cache", supports=())  # built on it, forgot to say so
    assert memory.grounding(sneaky).grounding == FLOATING  # fine while the claim stands
    _erase(system, root)
    claim = memory.grounding(sneaky)
    assert claim.grounding == AT_RISK and claim.broken == (root,)
    with pytest.raises(Ungrounded):
        memory.require_grounded([claim])


def test_the_retraction_preview_includes_notes_that_only_read_the_claim():
    system, memory = _setup()
    root = _human_fact(system, memory)
    honest = memory.agent("a")
    honest.recall(topics=["perf"])
    declared = honest.note("declared", supports=[root])
    forgetful = memory.agent("b")
    forgetful.recall(topics=["perf"])
    undeclared = forgetful.note("forgot to say", supports=())
    stranger = memory.agent("c")
    unrelated = stranger.note("never read it", supports=())
    hit = {c.artifact_id: c.grounding for c in memory.impact(root)}
    assert hit == {declared: ORPHANED, undeclared: AT_RISK} and unrelated not in hit


def test_risk_passes_down_a_chain_as_risk_not_as_proof():
    system, memory = _setup()
    root = _human_fact(system, memory)
    first = memory.agent("a")
    first.recall(topics=["perf"])
    maybe = first.note("maybe", supports=())
    second = memory.agent("b")
    second.read(maybe)
    downstream = second.note("builds on maybe", supports=[maybe])
    _erase(system, root)
    assert memory.grounding(maybe).grounding == AT_RISK
    assert memory.grounding(downstream).grounding == AT_RISK  # not ORPHANED: nothing proved it depended on the root


def test_a_possible_dependency_never_makes_a_note_grounded():
    system, memory = _setup()
    _human_fact(system, memory)
    view = memory.agent("a")
    view.recall(topics=["perf"])
    aid = view.note("read a root, declared nothing", supports=())
    assert memory.grounding(aid).grounding == FLOATING  # reading a root is not standing on it


def test_an_agents_own_earlier_notes_count_as_read_but_a_fresh_view_starts_empty():
    system, memory = _setup()
    root = _human_fact(system, memory)
    view = memory.agent("a")
    view.recall(topics=["perf"])
    first = view.note("first", supports=[root])
    second = view.note("second", supports=[first])  # its own note: allowed without re-reading
    assert memory.grounding(second).grounding == GROUNDED
    restarted = memory.agent("a")
    with pytest.raises(UnreadSupport):
        restarted.note("after restart", supports=[second])  # must read again first


def test_an_undeclared_read_of_a_claim_that_was_already_withdrawn_is_flagged_at_once():
    system, memory = _setup()
    root = _human_fact(system, memory)
    view = memory.agent("a")
    view.recall(topics=["perf"])
    _erase(system, root)
    late = view.note("written after the withdrawal", supports=())
    assert memory.grounding(late).grounding == AT_RISK


def test_a_view_needs_a_memory_and_a_name():
    _, memory = _setup()
    with pytest.raises(TypeError):
        memory.agent("x").__class__(object(), "x")
    with pytest.raises(ValueError):
        memory.agent("")
