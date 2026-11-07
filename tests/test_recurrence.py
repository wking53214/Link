"""record_recurrence: independent sessions climb CCC's ladder; echoes and erased text do not."""

from __future__ import annotations

import pytest
from ccc import Actor, AnalysisStage, CCCSystem
from cccb import TextMatcher
from cns_composition.ccc_admission import UnrecordedTriadOutput
from triad42 import Label, LabeledItem, Session, Severity

from link.recurrence import record_recurrence

GOV_1 = "governance terminology escalated into grandiose theological jargon"
GOV_2 = "grandiose theological jargon: the governance terminology escalated once again"
GOV_3 = "escalated governance terminology, grandiose theological jargon yet another time"


def _session(*texts, surfaced=True):
    session = Session()
    rp = session.start_pass(LabeledItem("The plan as written.", Label.ASSUMPTION))
    ids = {rp.add_finding(t, Severity.HIGH, scope="plan").finding_id for t in texts}
    session.harvest(rp, surfaced_ids=ids if surfaced else set())
    return session


def _system():
    return CCCSystem(text_matcher=TextMatcher(), private_source_markers=())


def test_three_independent_sessions_become_a_pattern_for_human_review():
    system = _system()
    for text in (GOV_1, GOV_2, GOV_3):
        assert len(record_recurrence(_session(text), system)) == 1
    (group,) = system.recurring_groups()
    assert group.stage is AnalysisStage.PATTERN
    assert group.occurrence_count == 3
    assert group.needs_human_review
    assert all(d.stage is not AnalysisStage.MANDATE for d in system.store.discoveries.values())


def test_the_same_text_again_is_an_echo_not_an_occurrence():
    system = _system()
    record_recurrence(_session(GOV_1), system)
    record_recurrence(_session(GOV_1), system)
    (group,) = system.recurring_groups()
    assert group.occurrence_count == 1
    assert len(group.duplicates) == 1


def test_running_the_same_session_twice_records_nothing_new():
    system = _system()
    session = _session(GOV_1)
    assert len(record_recurrence(session, system)) == 1
    assert record_recurrence(session, system) == []
    assert len(system.store.discoveries) == 1


def test_withheld_findings_never_reach_the_ladder():
    system = _system()
    assert record_recurrence(_session(GOV_1, surfaced=False), system) == []
    assert system.store.discoveries == {}


def test_an_erased_finding_is_refused_before_the_ladder():
    system = _system()
    first = _session(GOV_1)
    record_recurrence(first, system)
    artifact_id = next(iter(first.handed_off.values()))
    system.erase(artifact_id, actor=Actor.human(), reason="withdrawn", authorization_basis="test")
    with pytest.raises(UnrecordedTriadOutput):
        record_recurrence(first, system)
    assert len(system.store.discoveries) == 1


def test_findings_are_recorded_as_machine_inference_not_fact():
    system = _system()
    record_recurrence(_session(GOV_1), system)
    (record,) = system.store.discoveries.values()
    assert record.machine_origin
    assert record.epistemic_status.name == "INFERENCE"
