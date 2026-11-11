"""Reviewer calibration ledger (link).

Triad records the findings it withheld, with the reason, and CCC keeps them. This
reads that record back and asks, of each group of Triad findings, how often they
were later vindicated by something a human or a later review did:

- recurred: a later session surfaced a finding CCC's matcher reads as the same
  problem (text only; see `record_recurrence`);
- promoted: a human moved the record to a status only a human may hold;
- erased: a human removed it.

Compare the withheld group with the surfaced group. A withheld group that recurs
or is promoted as often as the surfaced group suggests the reviewer's
withholding is losing signal. This is a measurement of the record, not a verdict
on the reviewer, and small counts mean little. Read-only: nothing is written to
CCC and the system's own matcher is not touched.
"""

from __future__ import annotations

from dataclasses import dataclass

from ccc import ArtifactState, EpistemicStatus
from cccb import TextMatcher
from triad42.ccc_handoff import SOURCE_TAG
from triad42.retrieval import CandidateKind, SurfacingStatus

__all__ = ["CalibrationRow", "reviewer_calibration"]

_HUMAN_HELD = frozenset({EpistemicStatus.HISTORICAL_RECORD, EpistemicStatus.EVIDENCE})


@dataclass(frozen=True)
class CalibrationRow:
    status: SurfacingStatus
    total: int
    recurred: int
    promoted: int
    erased: int

    def rate(self, count: int) -> float | None:
        return count / self.total if self.total else None


def reviewer_calibration(ccc_system) -> dict[SurfacingStatus, CalibrationRow]:
    """Per surfacing status, how many Triad FINDING records recurred, were promoted or erased."""
    discoveries = [
        (d.created_at, d.source_material, d.conclusion)
        for d in ccc_system.store.discoveries.values()
        if any(s.startswith(f"{SOURCE_TAG}/") for s in d.source_material)
    ]
    counts = {s: [0, 0, 0, 0] for s in SurfacingStatus}
    for art in ccc_system.store.artifacts.values():
        meta = art.metadata or {}
        if meta.get("source") != SOURCE_TAG or meta.get("candidate_kind") != CandidateKind.FINDING.value:
            continue
        row = counts[SurfacingStatus(meta["surfacing_status"])]
        row[0] += 1
        if art.state is ArtifactState.ERASED:
            row[3] += 1
            continue
        if art.epistemic_status in _HUMAN_HELD:
            row[2] += 1
        # Only later sightings from other sessions count as recurrence.
        prefix = f"{SOURCE_TAG}/{meta.get('session_id')}/"
        matcher = TextMatcher()
        for i, (created, sources, text) in enumerate(discoveries):
            if created > art.created_at and not any(s.startswith(prefix) for s in sources):
                matcher.add(str(i), text)
        if art.content and matcher.recurrence_of(art.content) is not None:
            row[1] += 1
    return {s: CalibrationRow(s, c[0], c[1], c[2], c[3]) for s, c in counts.items()}
