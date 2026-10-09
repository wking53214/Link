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

try:
    from cns_composition.ccc_admission import TriadOutput
    from cns_composition.resubmission import ResubmissionGuard
    from cns_composition.triad_admission import admit_candidates
except ImportError as exc:
    raise ImportError(
        "link needs the cns_composition folder from a CNS checkout at the pinned "
        "commit on the Python path. It is not part of the cns package by design. "
        "See the README."
    ) from exc

__all__ = ["admit_session"]


def admit_session(session, ccc_system, guard=None):
    """Admit every candidate in a Triad-42 session for use inside CNS.

    Each candidate is recorded in CCC if it is not there yet, then checked
    against CCC's record. Returns the admitted items in session order.

    Raises UnrecordedTriadOutput when an item is refused for good, for example
    because a human erased it in CCC or the retry cap was reached. Raises
    ValueError when the session has passes that were never harvested, because
    their output would be missing from CCC.
    """
    if not isinstance(ccc_system, CCCSystem):
        raise TypeError(
            "admit_session needs a ccc.CCCSystem to record and check against; "
            f"got {type(ccc_system).__name__}"
        )
    candidates = [
        TriadOutput(candidate_id=candidate.candidate_id, text=candidate.text)
        for candidate in session.candidates.all()
    ]
    return admit_candidates(
        candidates,
        hand_off=lambda: hand_off(session, ccc_system),
        lookup=MachineRecords(ccc_system),
        guard=guard if guard is not None else ResubmissionGuard(),
    )
