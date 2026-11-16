"""A front door for advisory output from any source, not only Triad-42 (link).

CNS's admission gate names one source, "triad42", so it cannot admit output from
anything else. This door gives other advisory sources (a scanner, another model,
a human-run reviewer) the same discipline: record everything the source produced
in CCC under the source's own machine identity, offer only what it surfaced, and
admit an item only while CCC still holds exactly that text. An erased, redacted,
rejected, superseded or altered item is refused, and refusals do not reverse.

The decision is CNS's: `admit_items` records the items, then asks CNS's admission
door (`cns_composition.triad_admission.admit_candidates`, which takes the source
since CNS 4.1.0) about each surfaced one. This module owns what to record and
which items are offered, and turns CNS's refusal into `UnrecordedOutput`, which
carries CCC's own answer as `status`.

The source name is the machine identity the records carry. "triad42" is refused
here: Triad output goes through `admit_session`, and no other source may borrow
its identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.record_status import MachineRecords, attest
from triad42.ccc_handoff import SOURCE_TAG as TRIAD_SOURCE

from cns_composition.ccc_admission import TriadOutput, UnrecordedTriadOutput
from cns_composition.ccc_admission import text_digest as _digest
from cns_composition.resubmission import ResubmissionGuard
from cns_composition.triad_admission import admit_candidates

__all__ = ["SourceItem", "UnrecordedOutput", "admit_items", "record_items"]


@dataclass(frozen=True)
class SourceItem:
    """One candidate from a source. `surfaced` is False for output the source withheld, with its reason."""

    candidate_id: str
    text: str
    surfaced: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("a candidate needs an id")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("a candidate needs text")
        if not self.surfaced and not self.reason.strip():
            raise ValueError("a withheld candidate needs a stated reason; silent withholding looks like suppression")


class UnrecordedOutput(RuntimeError):
    """An item was refused. `status` is CCC's answer (erased, altered, unattested and so on)."""

    def __init__(self, item: SourceItem, status: str) -> None:
        super().__init__(f"{item.candidate_id}: not admitted, CCC answers {status!r}")
        self.item = item
        self.status = status


def _checked(source: str, ccc_system) -> None:
    if not isinstance(source, str) or not source.strip():
        raise ValueError("a source needs a name")
    if source == TRIAD_SOURCE:
        raise ValueError(f"{TRIAD_SOURCE!r} is Triad-42's identity; use admit_session for Triad output")
    if not isinstance(ccc_system, CCCSystem):
        raise TypeError(f"needs a ccc.CCCSystem; got {type(ccc_system).__name__}")


def record_items(source, items, ccc_system, *, attestation_key=None):
    """Record every item (surfaced and withheld) in CCC under the source's machine identity.

    Idempotent: an item already held in any state, erased included, is not recorded again.
    Returns candidate id to artifact id for the items recorded by this call.
    """
    _checked(source, ccc_system)
    held = {
        (a.metadata or {}).get("candidate_id")
        for a in ccc_system.store.artifacts.values()
        if a.origin.actor_id == source and (a.metadata or {}).get("source") == source
    }
    actor = Actor.model(source)
    recorded = {}
    for item in items:
        if item.candidate_id in held:
            continue
        digest = _digest(item.text)
        metadata = {
            "source": source,
            "candidate_id": item.candidate_id,
            "surfacing_status": "SURFACED" if item.surfaced else "NOT_SURFACED",
            "surfacing_reason": item.reason,
            "text_digest": digest,
        }
        if attestation_key is not None:
            metadata["attestation"] = attest(
                attestation_key, source=source, candidate_id=item.candidate_id, text_digest=digest)
        artifact = ccc_system.ingest(
            item.text,
            actor=actor,
            epistemic_status=EpistemicStatus.UNKNOWN,
            topics=(source,),
            reason=f"{source} output: advisory, machine-originated, not ratified",
            metadata=metadata,
        )
        held.add(item.candidate_id)
        recorded[item.candidate_id] = artifact.artifact_id
    return recorded


def admit_items(source, items, ccc_system, *, attestation_key=None, guard=None):
    """Record the items, then admit each surfaced one CNS's door lets through. Returns them in input order.

    Withheld items are recorded as an audit trail but never offered. Raises UnrecordedOutput on the first
    surfaced item refused. `status` is CCC's answer for it (erased, altered, unattested and so on), or
    "resubmission" when CNS's resubmission guard refused an item CCC still holds; the CNS refusal is `__cause__`.
    """
    items = list(items)

    def hand_off():
        record_items(source, items, ccc_system, attestation_key=attestation_key)

    hand_off()
    records = MachineRecords(ccc_system, attestation_key=attestation_key)
    surfaced = [item for item in items if item.surfaced]
    try:
        admit_candidates(
            [TriadOutput(candidate_id=i.candidate_id, text=i.text) for i in surfaced],
            hand_off=hand_off,
            lookup=records,
            guard=guard if guard is not None else ResubmissionGuard(),
            attestation_key=attestation_key,
            source=source,
        )
    except UnrecordedTriadOutput as refusal:
        refused = next(i for i in surfaced if refusal.result.subject == f"{source}:{i.candidate_id}")
        answer = records.status(source, refused.candidate_id, _digest(refused.text))
        raise UnrecordedOutput(refused, "resubmission" if answer == "held" else answer) from refusal
    return surfaced
