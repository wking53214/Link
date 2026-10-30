"""Triad-42 output into CNS, with CCC holding the record (link).

Three libraries sit on either side of this module, and none of them imports
another:

- Triad-42 runs review sessions and hands their candidates to CCC.
- CCC records candidates and answers whether a given item is held.
- CNS decides whether an item may be used, through its guarded admission
  door and retry loop.

This package is the one place that imports all three.
"""

from __future__ import annotations

from ccc import CCCSystem
from ccc.record_status import MachineRecords
from triad42.ccc_handoff import hand_off
from triad42.retrieval import SurfacingStatus

from cns_composition.ccc_admission import TriadOutput
from cns_composition.resubmission import ResubmissionGuard
from cns_composition.triad_admission import admit_candidates

__all__ = ["admit_session"]


def admit_session(session, ccc_system, guard=None, *, attestation_key=None):
    """Admit every candidate in a Triad-42 session for use inside CNS.

    Each candidate is recorded in CCC if it is not there yet, then checked
    against CCC's record. Returns the admitted items in session order.

    Only candidates the review surfaced are admitted. Triad records a
    candidate it did not show, with the reason, so that not showing it is never
    silent; that record is an audit trail and stays in CCC, but it is not review
    output and it is not offered to CNS. Anything whose status is not exactly
    SURFACED is left out, including a status this code has not seen.

    Raises UnrecordedTriadOutput when an item is refused for good, for example
    because a human erased it in CCC or the retry cap was reached. Raises
    ValueError when the session has passes that were never harvested, because
    their output would be missing from CCC.

    With `attestation_key` (bytes, at least 16, supplied by the caller), the
    handoff stamps each record and CCC's lookup counts only stamped ones, so a
    record anyone else wrote in the Triad's name is never admitted. A session
    that already has an unstamped record in `ccc_system` is refused with
    ValueError. Without a key the answer is as unauthenticated as before.
    """
    if not isinstance(ccc_system, CCCSystem):
        raise TypeError(
            "admit_session needs a ccc.CCCSystem to record and check against; "
            f"got {type(ccc_system).__name__}"
        )
    candidates = [
        TriadOutput(candidate_id=candidate.candidate_id, text=candidate.text)
        for candidate in session.candidates.all()
        if candidate.status is SurfacingStatus.SURFACED
    ]

    def handoff():
        if attestation_key is None:
            hand_off(session, ccc_system)
        else:
            hand_off(session, ccc_system, attestation_key=attestation_key)

    # Hand off first, even when every candidate is already held, so an
    # unharvested pass is refused on every run. hand_off is idempotent.
    handoff()
    return admit_candidates(
        candidates,
        hand_off=handoff,
        lookup=MachineRecords(ccc_system, attestation_key=attestation_key),
        guard=guard if guard is not None else ResubmissionGuard(),
    )
