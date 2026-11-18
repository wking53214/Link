"""The similar-wording default: a note that restates a stored claim is flagged, whatever the agent says."""

from __future__ import annotations

import builtins

import pytest
from ccc import Actor, CCCSystem, EpistemicStatus

from link.grounding import AT_RISK, FLOATING, GroundedMemory

FACT = "the checkout latency doubled right after the deploy 41 cache change"
RESTATED = "checkout latency doubled after the deploy 41 cache change"
UNRELATED = "the invoice footer uses an inconsistent font across the PDF templates"


def _setup(**kw):
    system = CCCSystem(allow_unguarded_writes=True, allow_unverified_humans=True)
    return system, GroundedMemory(system, **kw)


def _human_fact(system, memory, text=FACT):
    aid = memory.note(text, model_id="scribe", supports=())
    system.classify(aid, EpistemicStatus.EVIDENCE, actor=Actor.human(), reason="a person checked")
    return aid


def _erase(system, aid):
    system.erase(aid, actor=Actor.human(), reason="withdrawn", authorization_basis="test")


def test_a_restatement_the_agent_never_read_or_declared_is_flagged_and_goes_at_risk_on_withdrawal():
    system, memory = _setup()
    root = _human_fact(system, memory)
    restated = memory.note(RESTATED, model_id="stranger", supports=())  # never read it, declared nothing
    (target, why), = memory.possible_dependencies(restated)
    assert target == root and "similar wording" in why
    assert memory.grounding(restated).grounding == FLOATING  # fine while the claim stands
    _erase(system, root)
    assert memory.grounding(restated).grounding == AT_RISK


def test_an_unrelated_note_is_not_flagged():
    system, memory = _setup()
    _human_fact(system, memory)
    other = memory.note(UNRELATED, model_id="b", supports=())
    assert memory.possible_dependencies(other) == ()


def test_a_declared_support_is_not_also_listed_as_a_possible_one():
    system, memory = _setup()
    root = _human_fact(system, memory)
    note = memory.note(RESTATED, model_id="a", supports=[root])
    assert memory.possible_dependencies(note) == ()


def test_the_default_never_makes_a_note_grounded():
    system, memory = _setup()
    _human_fact(system, memory)
    restated = memory.note(RESTATED, model_id="a", supports=())
    assert memory.grounding(restated).grounding == FLOATING


def test_a_note_too_short_to_compare_is_ignored():
    system, memory = _setup()
    _human_fact(system, memory)
    short = memory.note("latency doubled", model_id="a", supports=())
    assert memory.possible_dependencies(short) == ()


def test_a_heavy_paraphrase_is_not_noticed_which_is_the_stated_limit():
    system, memory = _setup()
    _human_fact(system, memory, "failed payments are retried indefinitely; a single declined card keeps the retry queue busy")
    reworded = memory.note("there is no cap on charge retries, so a declined card can cycle endlessly", model_id="a", supports=())
    assert memory.possible_dependencies(reworded) == ()


def test_a_claim_already_withdrawn_cannot_be_compared_which_is_the_other_stated_limit():
    system, memory = _setup()
    root = _human_fact(system, memory)
    _erase(system, root)  # its text is gone
    late = memory.note(RESTATED, model_id="a", supports=())
    assert memory.possible_dependencies(late) == ()


def test_a_claim_both_read_and_similar_gets_one_possible_dependency_not_two():
    system, memory = _setup()
    root = _human_fact(system, memory)
    view = memory.agent("a")
    view.read(root)
    note = view.note(RESTATED, supports=())
    assert [t for t, _ in memory.possible_dependencies(note)] == [root]


def test_it_can_be_turned_off():
    system, memory = _setup(flag_similar=False)
    _human_fact(system, memory)
    restated = memory.note(RESTATED, model_id="a", supports=())
    assert memory.possible_dependencies(restated) == ()


def test_it_never_silently_does_nothing_when_the_matcher_is_missing(monkeypatch):
    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name.startswith("cccb"):
            raise ImportError("no matcher here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake)
    system = CCCSystem(allow_unguarded_writes=True, allow_unverified_humans=True)
    with pytest.raises(ImportError, match="flag_similar=False"):
        GroundedMemory(system)
    assert GroundedMemory(system, flag_similar=False) is not None
