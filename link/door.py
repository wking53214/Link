"""A front door for advisory output from any source, not only Triad-42 (link).

CNS's admission gate names one source, "triad42", so it cannot admit output from
anything else. This door gives other advisory sources (a scanner, another model,
a human-run reviewer) the same discipline: record everything the source produced
in CCC under the source's own machine identity, offer only what it surfaced, and
admit an item only while CCC still holds exactly that text. An erased, redacted,
rejected, superseded or altered item is refused, and refusals do not reverse.

This is link's own door, not CNS's. It applies CCC's record lookup directly and
has no retry cap, because it records first and so never needs a second try. When
CNS takes the source as a parameter, this module should become a thin call to it.

The source name is the machine identity the records carry. "triad42" is refused
here: Triad output goes through `admit_session`, and no other source may borrow
its identity.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.record_status import MachineRecords, attest
from triad42.ccc_handoff import SOURCE_TAG as TRIAD_SOURCE

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


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def admit_items(source, items, ccc_system, *, attestation_key=None):
    """Record the items, then admit each surfaced one CCC still holds. Returns them in input order.

    Withheld items are recorded as an audit trail but never offered. Raises UnrecordedOutput on the first
    surfaced item CCC does not hold exactly as presented.
    """
    items = list(items)
    record_items(source, items, ccc_system, attestation_key=attestation_key)
    records = MachineRecords(ccc_system, attestation_key=attestation_key)
    admitted = []
    for item in items:
        if not item.surfaced:
            continue
        status = records.status(source, item.candidate_id, _digest(item.text))
        if status != "held":
            raise UnrecordedOutput(item, status)
        admitted.append(item)
    return admitted
