"""Revocation for admitted Triad output (link).

`admit_session` returns plain items, so a finding a human erases in CCC after it
was admitted keeps being used by whoever holds the list. This module returns a
receipt per item and re-asks CCC at the moment of use, so an erasure (or
redaction, rejection or supersession) takes effect for every holder at once.
The recheck is CNS's (`cns_composition.triad_admission`); link only wires it to
a real CCC system. The receipt records what was admitted; it is not a permission.
"""

from __future__ import annotations

from ccc import CCCSystem
from ccc.record_status import MachineRecords
from cns.gate import GateOutcome
from cns_composition.resubmission import ResubmissionGuard
from cns_composition.triad_admission import AdmissionReceipt, admit_with_receipts, recheck, use
from triad42.ccc_handoff import hand_off

from link.admission import surfaced_candidates

__all__ = ["admit_session_with_receipts", "revoked", "use_admitted"]


def _system(ccc_system):
    if not isinstance(ccc_system, CCCSystem):
        raise TypeError(f"needs a ccc.CCCSystem; got {type(ccc_system).__name__}")
    return ccc_system


def admit_session_with_receipts(session, ccc_system, guard=None, *, attestation_key=None):
    """Like `admit_session`, but returns an `AdmissionReceipt` per admitted item, in session order."""
    _system(ccc_system)

    def handoff():
        if attestation_key is None:
            hand_off(session, ccc_system)
        else:
            hand_off(session, ccc_system, attestation_key=attestation_key)

    handoff()
    return admit_with_receipts(
        surfaced_candidates(session),
        hand_off=handoff,
        lookup=MachineRecords(ccc_system, attestation_key=attestation_key),
        guard=guard if guard is not None else ResubmissionGuard(),
        attestation_key=attestation_key,
    )


def use_admitted(receipt, ccc_system, *, attestation_key=None):
    """The admitted item, only if CCC still holds it now. Raises UnrecordedTriadOutput otherwise."""
    lookup = MachineRecords(_system(ccc_system), attestation_key=attestation_key)
    return use(receipt, lookup, attestation_key=attestation_key)


def revoked(receipts, ccc_system, *, attestation_key=None):
    """The receipts whose item CCC no longer holds, each with the reason CCC gives. Does not raise."""
    lookup = MachineRecords(_system(ccc_system), attestation_key=attestation_key)
    out = []
    for receipt in receipts:
        if not isinstance(receipt, AdmissionReceipt):
            raise TypeError(f"revoked takes AdmissionReceipts; got {type(receipt).__name__}")
        result = recheck(receipt, lookup, attestation_key=attestation_key)
        if result.outcome is not GateOutcome.PASS:
            out.append((receipt, result.reason))
    return out
