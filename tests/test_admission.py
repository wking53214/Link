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


def test_held_candidates_do_not_trigger_a_second_handoff(monkeypatch):
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

    assert calls == []


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
