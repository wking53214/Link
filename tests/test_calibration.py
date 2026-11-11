"""reviewer_calibration: how often withheld and surfaced findings were later vindicated."""

from __future__ import annotations

import time

from ccc import Actor, CCCSystem, EpistemicStatus
from cccb import TextMatcher
from triad42 import Label, LabeledItem, Session, Severity
from triad42.retrieval import SurfacingStatus

from link.calibration import reviewer_calibration
from link.recurrence import record_recurrence

GOV_1 = "governance terminology escalated into grandiose theological jargon"
GOV_2 = "grandiose theological jargon: the governance terminology escalated once again"
QUEUE = "queue wait times exceeded the friction threshold on the billing line"


def _session(shown, withheld=()):
    session = Session()
    rp = session.start_pass(LabeledItem("The plan as written.", Label.ASSUMPTION))
    keep = {rp.add_finding(t, Severity.HIGH, scope="plan").finding_id for t in shown}
    for t in withheld:
        rp.add_finding(t, Severity.HIGH, scope="plan")
    session.harvest(rp, surfaced_ids=keep)
    return session


def _system():
    return CCCSystem(text_matcher=TextMatcher(), private_source_markers=())


def test_a_withheld_finding_that_a_later_session_surfaces_counts_as_recurred():
    system = _system()
    record_recurrence(_session([QUEUE], withheld=[GOV_1]), system)
    time.sleep(0.01)
    record_recurrence(_session([GOV_2]), system)

    rows = reviewer_calibration(system)
    withheld, surfaced = rows[SurfacingStatus.NOT_SURFACED], rows[SurfacingStatus.SURFACED]
    assert (withheld.total, withheld.recurred) == (1, 1)
    assert withheld.rate(withheld.recurred) == 1.0
    assert (surfaced.total, surfaced.recurred) == (2, 0)


def test_the_same_session_does_not_count_as_recurrence():
    system = _system()
    record_recurrence(_session([GOV_2], withheld=[GOV_1]), system)
    assert reviewer_calibration(system)[SurfacingStatus.NOT_SURFACED].recurred == 0


def test_a_human_promotion_and_an_erasure_are_counted():
    system = _system()
    session = _session([QUEUE], withheld=[GOV_1])
    record_recurrence(session, system)
    by_status = {a.metadata["surfacing_status"]: a.artifact_id for a in system.store.artifacts.values()}
    system.classify(by_status["NOT_SURFACED"], EpistemicStatus.EVIDENCE, actor=Actor.human(),
                    reason="a human adopted it")
    system.erase(by_status["SURFACED"], actor=Actor.human(), reason="withdrawn", authorization_basis="test")

    rows = reviewer_calibration(system)
    assert rows[SurfacingStatus.NOT_SURFACED].promoted == 1
    assert rows[SurfacingStatus.SURFACED].erased == 1


def test_an_empty_system_gives_zero_totals_and_no_rates():
    row = reviewer_calibration(_system())[SurfacingStatus.NOT_SURFACED]
    assert row.total == 0 and row.rate(row.recurred) is None


def test_the_ledger_writes_nothing():
    system = _system()
    record_recurrence(_session([QUEUE], withheld=[GOV_1]), system)
    before = (len(system.store.artifacts), len(system.store.discoveries))
    reviewer_calibration(system)
    assert (len(system.store.artifacts), len(system.store.discoveries)) == before
