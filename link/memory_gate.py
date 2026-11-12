"""An anti-laundering gate for agent memory (link).

The failure this closes: one model's guess is stored, a second model reads it
back as if it were established, and a third cites the second. Each hop adds
confidence and no evidence. Here an agent's memory is a CCC system, and nothing
read back from it is a premise unless a human holds it at a status only a human
may give (EVIDENCE or HISTORICAL_RECORD in CCC). Everything else comes back
labelled advisory, with its origin, and `require_premises` refuses it at the
point an agent would build on it.

What comes back is also only what CCC still holds: erased, redacted, rejected
and superseded records are not recalled, so a human's retraction reaches every
agent that reads this memory.

Limits: the gate labels and refuses; it cannot stop a model that ignores the
label when it writes its own text, and it does not judge whether a premise is
true. A human-held status says a human adopted the claim, not that it is correct.
"""

from __future__ import annotations

from dataclasses import dataclass

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.models import ProvenanceStatus, RelationshipType

__all__ = ["LaunderingRefused", "MemoryGate", "RecalledClaim"]

_PREMISE_STATUSES = frozenset({EpistemicStatus.EVIDENCE, EpistemicStatus.HISTORICAL_RECORD})


class LaunderingRefused(RuntimeError):
    """Advisory claims were offered as premises."""

    def __init__(self, claims) -> None:
        super().__init__(
            "not premises (no human holds them at EVIDENCE or HISTORICAL_RECORD): "
            + ", ".join(f"{c.artifact_id} [{c.origin}]" for c in claims)
        )
        self.claims = tuple(claims)


@dataclass(frozen=True)
class RecalledClaim:
    artifact_id: str
    text: str
    origin: str  # for example "model:planner" or "human:human"
    status: str  # CCC epistemic status
    premise: bool  # True only when a human holds it at a premise status


class MemoryGate:
    """Agent memory backed by a real CCC system."""

    def __init__(self, ccc_system) -> None:
        if not isinstance(ccc_system, CCCSystem):
            raise TypeError(f"MemoryGate needs a ccc.CCCSystem; got {type(ccc_system).__name__}")
        self._ccc = ccc_system

    def remember(self, text, *, model_id, topics=()):
        """Store a model's output. It is machine-originated and UNKNOWN, so it can never come back as a premise
        until a human promotes it in CCC. Returns the artifact id."""
        artifact = self._ccc.ingest(
            text, actor=Actor.model(model_id), epistemic_status=EpistemicStatus.UNKNOWN,
            topics=tuple(topics), reason="agent memory: machine output, advisory until a human holds it",
        )
        return artifact.artifact_id

    def _superseded(self, artifact_id):
        return any(e.target_id == artifact_id and e.source_id != artifact_id
                   for e in self._ccc.lineage.related(artifact_id, RelationshipType.SUPERSEDES))

    def recall(self, *, topics=None, premises_only=False):
        """What CCC still holds, each claim labelled. `topics` keeps claims carrying any of those topics."""
        wanted = set(topics) if topics is not None else None
        out = []
        for a in self._ccc.store.artifacts.values():
            if not a.available or a.provenance_status is ProvenanceStatus.REJECTED or self._superseded(a.artifact_id):
                continue
            if wanted is not None and not wanted.intersection(a.topics):
                continue
            premise = a.epistemic_status in _PREMISE_STATUSES
            if premises_only and not premise:
                continue
            out.append(RecalledClaim(a.artifact_id, a.content, f"{a.origin.kind.value.lower()}:{a.origin.actor_id}",
                                     a.epistemic_status.value, premise))
        return out

    def require_premises(self, claims):
        """The claims, if every one is a premise now. Raises LaunderingRefused naming the ones that are not.
        Asks CCC again, so a claim retracted or demoted since it was recalled is refused."""
        claims = list(claims)
        current = {c.artifact_id: c for c in self.recall()}
        bad = [c for c in claims if not (c.artifact_id in current and current[c.artifact_id].premise)]
        if bad:
            raise LaunderingRefused(bad)
        return claims

    @staticmethod
    def render(claims):
        """Text for an agent's context, each claim tagged so the label travels with it."""
        lines = []
        for c in claims:
            tag = "PREMISE (human-held)" if c.premise else f"ADVISORY, {c.origin}, unverified: not a fact"
            lines.append(f"[{tag}] {c.text}")
        return "\n".join(lines)
