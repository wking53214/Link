"""GroundedMemory: notes declare what they stand on, and only a person is a root."""

from __future__ import annotations

import pytest
from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.errors import ConstitutionViolation

from link.grounding import FLOATING, GROUNDED, ORPHANED, GroundedMemory, Ungrounded

FACT = "latency doubled right after deploy 41"


def _setup():
    system = CCCSystem(allow_unguarded_writes=True, allow_unverified_humans=True)
    memory = GroundedMemory(system)
    return system, memory


def _human_fact(system, text=FACT):
    """A claim a person holds: a note adopted at EVIDENCE."""
    aid = GroundedMemory(system).note(text, model_id="scribe")
    system.classify(aid, EpistemicStatus.EVIDENCE, actor=Actor.human(), reason="a person checked the graph")
    return aid


def _erase(system, aid):
    system.erase(aid, actor=Actor.human(), reason="withdrawn", authorization_basis="test")


def test_a_note_with_nothing_under_it_floats():
    _, memory = _setup()
    aid = memory.note("the cache is the cause", model_id="planner")
    assert memory.grounding(aid).grounding == FLOATING


def test_a_note_standing_on_a_person_held_claim_is_grounded_with_its_root():
    system, memory = _setup()
    root = _human_fact(system)
    aid = memory.note("the cache is the cause", model_id="planner", supports=[root])
    claim = memory.grounding(aid)
    assert claim.grounding == GROUNDED and claim.roots == (root,)


def test_a_chain_stays_grounded_only_while_every_link_ends_in_a_person():
    system, memory = _setup()
    root = _human_fact(system)
    n1 = memory.note("deploy 41 changed the cache", model_id="a", supports=[root])
    n2 = memory.note("so roll back the cache change", model_id="b", supports=[n1])
    guess = memory.note("maybe the DNS is slow too", model_id="c")
    n3 = memory.note("do both", model_id="d", supports=[n2, guess])
    assert memory.grounding(n2).grounding == GROUNDED
    assert memory.grounding(n3).grounding == FLOATING  # one leg is a machine guess with no person behind it


def test_a_machine_cannot_make_its_own_root():
    system, memory = _setup()
    aid = memory.note("the cache is the cause", model_id="planner")
    with pytest.raises(ConstitutionViolation):
        system.classify(aid, EpistemicStatus.EVIDENCE, actor=Actor.model("planner"), reason="trust me")
    assert memory.grounding(aid).grounding == FLOATING


def test_erasing_a_root_orphans_everything_built_on_it_down_the_chain():
    system, memory = _setup()
    root = _human_fact(system)
    n1 = memory.note("n1", model_id="a", supports=[root])
    n2 = memory.note("n2", model_id="b", supports=[n1])
    n3 = memory.note("n3", model_id="c", supports=[n2])
    _erase(system, root)
    for n in (n1, n2, n3):
        claim = memory.grounding(n)
        assert claim.grounding == ORPHANED and claim.broken == (root,)


def test_a_superseded_root_orphans_its_dependents_too():
    system, memory = _setup()
    root = _human_fact(system)
    n1 = memory.note("n1", model_id="a", supports=[root])
    system.supersede(root, content="the real figure was a 30 percent rise", actor=Actor.human(),
                     reason="misread the graph", authorization_basis="test")
    assert memory.grounding(n1).grounding == ORPHANED


def test_demoting_a_root_leaves_dependents_floating_not_orphaned():
    system, memory = _setup()
    root = _human_fact(system)
    n1 = memory.note("n1", model_id="a", supports=[root])
    system.classify(root, EpistemicStatus.UNKNOWN, actor=Actor.human(), reason="not sure any more")
    assert memory.grounding(n1).grounding == FLOATING


def test_a_note_cannot_be_built_on_a_claim_that_is_already_gone():
    system, memory = _setup()
    root = _human_fact(system)
    _erase(system, root)
    before = len(system.store.artifacts)
    with pytest.raises(ValueError, match="gone or retracted"):
        memory.note("late note", model_id="a", supports=[root])
    assert len(system.store.artifacts) == before
    with pytest.raises(ValueError):
        memory.note("note on nothing", model_id="a", supports=["no-such-id"])


def test_impact_previews_the_blast_radius_and_writes_nothing():
    system, memory = _setup()
    root = _human_fact(system)
    other = _human_fact(system, "the rollback window is 10 minutes")
    n1 = memory.note("n1", model_id="a", supports=[root])
    n2 = memory.note("n2", model_id="b", supports=[n1])
    safe = memory.note("safe", model_id="c", supports=[other])
    mixed = memory.note("mixed", model_id="d", supports=[n2, other])
    before = (len(system.store.artifacts), len(system.lineage.for_object(root)))
    hit = {c.artifact_id: c.grounding for c in memory.impact(root)}
    assert hit == {n1: ORPHANED, n2: ORPHANED, mixed: ORPHANED} and safe not in hit
    assert (len(system.store.artifacts), len(system.lineage.for_object(root))) == before
    assert memory.grounding(n2).grounding == GROUNDED  # nothing actually changed


def test_impact_also_lists_a_floating_note_that_would_come_to_rest_on_something_retracted():
    system, memory = _setup()
    root = _human_fact(system)
    n1 = memory.note("n1", model_id="a", supports=[root])
    guess = memory.note("a guess", model_id="b")
    plan = memory.note("plan", model_id="c", supports=[n1, guess])  # FLOATING today
    unrelated = memory.note("unrelated guess", model_id="d")  # FLOATING, stays FLOATING
    hit = {c.artifact_id: c.grounding for c in memory.impact(root)}
    assert hit == {n1: ORPHANED, plan: ORPHANED} and unrelated not in hit


def test_recall_lists_orphans_so_nobody_builds_on_them_unaware_and_can_filter_to_grounded():
    system, memory = _setup()
    root = _human_fact(system)
    n1 = memory.note("n1", model_id="a", supports=[root], topics=("perf",))
    floating = memory.note("guess", model_id="b", topics=("perf",))
    _erase(system, root)
    states = {c.artifact_id: c.grounding for c in memory.recall(topics=["perf"])}
    assert states == {n1: ORPHANED, floating: FLOATING}
    assert memory.recall(topics=["perf"], grounded_only=True) == []


def test_require_grounded_refuses_anything_not_grounded_now_and_rechecks():
    system, memory = _setup()
    root = _human_fact(system)
    n1 = memory.note("n1", model_id="a", supports=[root])
    (claim,) = [c for c in memory.recall() if c.artifact_id == n1]
    assert memory.require_grounded([claim]) == [claim]
    _erase(system, root)
    with pytest.raises(Ungrounded) as info:
        memory.require_grounded([claim])  # the old copy says GROUNDED; the record no longer does
    assert info.value.claims[0].grounding == ORPHANED


def test_it_needs_a_real_ccc_system():
    with pytest.raises(TypeError):
        GroundedMemory(object())
