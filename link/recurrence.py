"""Cross-session recurrence for Triad-42 findings (link).

Triad's 1/2/3 rule counts findings inside one session. CCC already tracks
recurrence over time, but only for findings recorded through
`record_external_finding`. This module is the bridge: it takes the findings
`admit_session` admitted and records each one in CCC's recurrence ladder, so a
problem seen in three independent sessions becomes a PATTERN that CCC flags for
a human. CCC alone decides what counts as a repeat; MANDATE stays human-only.

What `verified` means here: CCC refuses an "unverified" finding, meaning a
non-answer. A Triad finding is never verified true. It is passed as verified
only because it is real, non-empty review output that already passed admission.
The record stays machine-originated, an inference, and advisory.
"""

from __future__ import annotations

from dataclasses import dataclass

from ccc import Actor, EpistemicStatus
from triad42.ccc_handoff import SOURCE_TAG
from triad42.retrieval import CandidateKind

from link.admission import admit_session

__all__ = ["record_recurrence"]


@dataclass(frozen=True)
class _Finding:
    conclusion: str
    method: str
    source_material: tuple[str, ...]
    confidence: None
    verified: bool
    evidence: tuple[tuple[str, str], ...]
    event_start_date: str
    event_end_date: str


def record_recurrence(session, ccc_system, guard=None, *, attestation_key=None):
    """Admit a session, then feed its admitted findings to CCC's recurrence ladder.

    Returns the discovery ids recorded by this call (empty on a repeat call).
    Only FINDING candidates that `admit_session` admitted are recorded, so an
    erased or withheld finding never reaches the ladder. Running twice records
    nothing new. The CCC system needs a text matcher and stated private
    sources; CCC refuses otherwise. Read the result with
    `ccc_system.recurring_groups()`.
    """
    admitted = {item.candidate_id for item in admit_session(
        session, ccc_system, guard, attestation_key=attestation_key)}
    done = {part for d in ccc_system.store.discoveries.values() for part in d.source_material}
    actor = Actor.model(SOURCE_TAG)
    recorded = []
    for cand in session.candidates.all():
        if cand.candidate_id not in admitted or cand.kind is not CandidateKind.FINDING:
            continue
        source = f"{SOURCE_TAG}/{session.session_id}/{cand.candidate_id}"
        if source in done:
            continue
        date = cand.recorded_at
        finding = _Finding(
            conclusion=cand.text, method="triad42.review", source_material=(source,),
            confidence=None, verified=True, evidence=((source, cand.text),),
            event_start_date=date, event_end_date=date)
        recorded.append(ccc_system.record_external_finding(
            finding, actor=actor, epistemic_status=EpistemicStatus.INFERENCE))
    return recorded
