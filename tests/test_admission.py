"""admit_session: CCC decides what is held, CNS decides what is admitted.

These tests run against the real CCC and Triad-42 packages, with the real
CNS admission door. Nothing is stubbed except where a test counts calls.
"""

from __future__ import annotations

import pytest
from ccc import Actor, CCCSystem
from cns.gate import GateOutcome
from cns_composition.ccc_admission import GATE_NAME as CCC_GATE
from cns_composition.ccc_admission import UnrecordedTriadOutput
from triad42 import Label, LabeledItem, Session, Severity
from triad42.retrieval import SurfacingStatus

from link import admission
from link.admission import admit_session


def _session(*texts: str) -> Session:
    """A session whose one harvested pass surfaces each text as a finding."""
    session = Session()
    rp = session.start_pass(LabeledItem("The plan as written.", Label.ASSUMPTION))
    ids = {rp.add_finding(text, Severity.HIGH, scope="plan").finding_id for text in texts}
    session.harvest(rp, surfaced_ids=ids)
    return session


def test_candidates_are_recorded_and_admitted_in_session_order():
    session = _session("first finding", "second finding")
    system = CCCSystem()

    admitted = admit_session(session, system)

    expected = [c.candidate_id for c in session.candidates.all()]
    assert [a.candidate_id for a in admitted] == expected
    assert [a.text for a in admitted] == ["first finding", "second finding"]
    assert len(system.store.artifacts) == 2


def test_running_again_admits_without_recording_twice():
    session = _session("only finding")
    system = CCCSystem()
    admit_session(session, system)

    admitted = admit_session(session, system)

    assert len(admitted) == 1
    assert len(system.store.artifacts) == 1


def test_held_candidates_are_not_recorded_again(monkeypatch):
    session = _session("finding")
    system = CCCSystem()
    admit_session(session, system)
    calls = []
    real_hand_off = admission.hand_off

    def counting_hand_off(sess, target):
        calls.append(sess)
        return real_hand_off(sess, target)

    monkeypatch.setattr(admission, "hand_off", counting_hand_off)

    admit_session(session, system)

    assert len(calls) == 1
    assert len(system.store.artifacts) == 1


def test_an_unharvested_pass_is_refused_even_when_every_candidate_is_held():
    session = _session("finding")
    system = CCCSystem()
    admit_session(session, system)
    session.start_pass(LabeledItem("Started, never harvested.", Label.ASSUMPTION))

    with pytest.raises(ValueError, match="never harvested"):
        admit_session(session, system)

    assert len(system.store.artifacts) == 1


def test_an_erased_candidate_is_refused_and_not_brought_back():
    session = _session("withdrawn finding")
    system = CCCSystem()
    admitted = admit_session(session, system)
    artifact_id = session.handed_off[admitted[0].candidate_id]
    system.erase(
        artifact_id,
        actor=Actor.human(),
        reason="withdrawn by the reviewer",
        authorization_basis="test",
    )

    with pytest.raises(UnrecordedTriadOutput) as info:
        admit_session(session, system)

    assert info.value.result.gate == CCC_GATE
    assert info.value.result.outcome is GateOutcome.TERMINAL_BREACH
    assert len(system.store.artifacts) == 1


def test_an_unharvested_pass_blocks_the_handoff_for_new_candidates():
    session = _session("finding")
    session.start_pass(LabeledItem("Started, never harvested.", Label.ASSUMPTION))
    system = CCCSystem()

    with pytest.raises(ValueError, match="never harvested"):
        admit_session(session, system)

    assert len(system.store.artifacts) == 0


def test_a_target_that_is_not_a_real_ccc_system_is_refused():
    session = _session("finding")

    with pytest.raises(TypeError, match="ccc.CCCSystem"):
        admit_session(session, object())


def _session_with_hidden(shown: str, hidden: str) -> Session:
    """A harvested pass in which `shown` surfaces and `hidden` is detected but not shown to the reviewer."""
    session = Session()
    rp = session.start_pass(LabeledItem("The plan as written.", Label.ASSUMPTION))
    shown_id = rp.add_finding(shown, Severity.HIGH, scope="plan").finding_id
    rp.add_finding(hidden, Severity.HIGH, scope="plan")
    session.harvest(rp, surfaced_ids={shown_id})
    return session


def test_the_fixture_really_contains_a_hidden_candidate():
    session = _session_with_hidden("shown finding", "hidden finding")
    status = {c.text: c.status for c in session.candidates.all()}
    assert status == {"shown finding": SurfacingStatus.SURFACED, "hidden finding": SurfacingStatus.NOT_SURFACED}


def test_a_candidate_the_reviewer_was_not_shown_is_not_admitted():
    """Triad records a hidden candidate, with its reason, so that not showing it is never silent. That record
    is an audit trail of what was withheld, not output to use. Admitting it would put into CNS something the
    review never presented."""
    session = _session_with_hidden("shown finding", "hidden finding")

    admitted = admit_session(session, CCCSystem())

    assert [a.text for a in admitted] == ["shown finding"]


def test_a_hidden_candidate_is_still_recorded_in_ccc_for_the_audit_trail():
    session = _session_with_hidden("shown finding", "hidden finding")
    system = CCCSystem()

    admit_session(session, system)

    assert len(system.store.artifacts) == 2


def test_a_session_with_nothing_surfaced_admits_nothing_and_does_not_fail():
    session = Session()
    rp = session.start_pass(LabeledItem("The plan as written.", Label.ASSUMPTION))
    rp.add_finding("hidden one", Severity.HIGH, scope="plan")
    rp.add_finding("hidden two", Severity.HIGH, scope="plan")
    session.harvest(rp, surfaced_ids=set())

    assert admit_session(session, CCCSystem()) == []


def test_admitted_candidates_keep_session_order_around_a_hidden_one():
    session = Session()
    rp = session.start_pass(LabeledItem("The plan as written.", Label.ASSUMPTION))
    first = rp.add_finding("first", Severity.HIGH, scope="plan").finding_id
    rp.add_finding("hidden between", Severity.HIGH, scope="plan")
    third = rp.add_finding("third", Severity.HIGH, scope="plan").finding_id
    session.harvest(rp, surfaced_ids={first, third})

    assert [a.text for a in admit_session(session, CCCSystem())] == ["first", "third"]


def test_a_status_that_is_not_exactly_surfaced_is_never_admitted():
    """Only SURFACED is permission. A status Triad adds later, which this code has not seen, is not."""
    from enum import Enum

    class FutureStatus(Enum):
        SOMETHING_NEW = "SOMETHING_NEW"

    session = _session("finding")
    for candidate in session.candidates.all():
        candidate.status = FutureStatus.SOMETHING_NEW

    assert admit_session(session, CCCSystem()) == []
