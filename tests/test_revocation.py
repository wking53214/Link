"""Revocation: an erasure after admission reaches every holder of a receipt."""

from __future__ import annotations

import pytest
from ccc import Actor, CCCSystem
from cns_composition.ccc_admission import UnrecordedTriadOutput
from triad42 import Label, LabeledItem, Session, Severity

from link.revocation import admit_session_with_receipts, revoked, use_admitted

KEY = b"k" * 32


def _session(*texts):
    session = Session()
    rp = session.start_pass(LabeledItem("The plan as written.", Label.ASSUMPTION))
    ids = {rp.add_finding(t, Severity.HIGH, scope="plan").finding_id for t in texts}
    session.harvest(rp, surfaced_ids=ids)
    return session


def _erase_first(session, system):
    artifact_id = next(iter(session.handed_off.values()))
    system.erase(artifact_id, actor=Actor.human(), reason="withdrawn", authorization_basis="test")


def test_receipts_are_returned_in_session_order_and_usable():
    session, system = _session("first", "second"), CCCSystem()
    receipts = admit_session_with_receipts(session, system)
    assert [r.output.text for r in receipts] == ["first", "second"]
    assert [use_admitted(r, system).text for r in receipts] == ["first", "second"]
    assert revoked(receipts, system) == []


def test_an_erasure_after_admission_stops_use_and_is_listed():
    session, system = _session("keep", "withdraw"), CCCSystem()
    receipts = admit_session_with_receipts(session, system)
    erased = next(a for a in system.store.artifacts.values() if a.content == "withdraw")
    system.erase(erased.artifact_id, actor=Actor.human(), reason="withdrawn", authorization_basis="test")

    gone = revoked(receipts, system)
    assert [r.output.text for r, _ in gone] == ["withdraw"]
    assert "erased" in gone[0][1]
    with pytest.raises(UnrecordedTriadOutput):
        use_admitted(receipts[1], system)
    assert use_admitted(receipts[0], system).text == "keep"


def test_it_works_with_an_attestation_key():
    session, system = _session("stamped"), CCCSystem()
    receipts = admit_session_with_receipts(session, system, attestation_key=KEY)
    assert use_admitted(receipts[0], system, attestation_key=KEY).text == "stamped"
    _erase_first(session, system)
    assert len(revoked(receipts, system, attestation_key=KEY)) == 1


def test_a_forged_receipt_is_not_accepted():
    with pytest.raises(TypeError):
        revoked(["not a receipt"], CCCSystem())
    with pytest.raises(TypeError):
        use_admitted(object(), CCCSystem())
