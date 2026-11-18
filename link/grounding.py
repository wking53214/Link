"""Grounded memory: every machine note says what it stands on, and only a person is a root (link).

`MemoryGate` labels a model's note as advisory until a person adopts it. That stops one
hop of laundering. It does not stop a chain: model B builds on A's guess, model C builds on
B, and each hop looks more settled than the last. This module records what each note was
built on, at write time, and tracks the chain back to its roots.

The rule of the roots is the point. Only a person can make a root (CCC lets only a human
hold a claim at EVIDENCE or HISTORICAL_RECORD), so a machine cannot ground its own notes.
Each note is then in one of three states:

  GROUNDED  every note under it, all the way down, ends in a claim a person still holds
  FLOATING  something under it is a machine note with no person behind it (never grounded)
  ORPHANED  something under it was taken back: erased, redacted, rejected or superseded

`impact` shows a person what retracting a claim would do before they do it.

This is the dependency idea of classic truth maintenance systems, and recent work applies
it to agent memory (for example PACMI, arXiv 2610.05732). What is specific here is that
the roots are human-only by construction, the dependencies are declared when the note is
written and checked then (a note cannot stand on something already retracted), and the
person deciding to retract gets the blast radius first. It labels and refuses; it does not
judge whether a root is true.
"""

from __future__ import annotations

from dataclasses import dataclass

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.models import ProvenanceStatus, RelationshipType

__all__ = ["FLOATING", "GROUNDED", "ORPHANED", "GroundedClaim", "GroundedMemory", "Ungrounded"]

GROUNDED, FLOATING, ORPHANED = "GROUNDED", "FLOATING", "ORPHANED"
_PREMISE_STATUSES = frozenset({EpistemicStatus.EVIDENCE, EpistemicStatus.HISTORICAL_RECORD})


class Ungrounded(RuntimeError):
    """Notes that are not grounded were offered where grounded ones are required."""

    def __init__(self, claims) -> None:
        super().__init__("not grounded: " + ", ".join(f"{c.artifact_id} [{c.grounding}]" for c in claims))
        self.claims = tuple(claims)


@dataclass(frozen=True)
class GroundedClaim:
    artifact_id: str
    text: str
    origin: str
    grounding: str
    roots: tuple[str, ...]  # the person-held claims it stands on (GROUNDED only)
    broken: tuple[str, ...]  # the retracted claims under it (ORPHANED only)


class GroundedMemory:
    """Agent notes with declared dependencies, on a real CCC system."""

    def __init__(self, ccc_system) -> None:
        if not isinstance(ccc_system, CCCSystem):
            raise TypeError(f"GroundedMemory needs a ccc.CCCSystem; got {type(ccc_system).__name__}")
        self._ccc = ccc_system

    # -- reading the record ------------------------------------------------------------
    def _artifact(self, artifact_id):
        return self._ccc.store.artifacts.get(artifact_id)

    def _superseded(self, artifact_id):
        return any(e.target_id == artifact_id and e.source_id != artifact_id
                   for e in self._ccc.lineage.related(artifact_id, RelationshipType.SUPERSEDES))

    def _retracted(self, artifact_id):
        a = self._artifact(artifact_id)
        return (a is None or not a.available or a.provenance_status is ProvenanceStatus.REJECTED
                or self._superseded(artifact_id))

    def _supports(self, artifact_id):
        return tuple(e.target_id for e in self._ccc.lineage.related(artifact_id, RelationshipType.DERIVED_FROM)
                     if e.source_id == artifact_id)

    def _is_root(self, artifact_id):
        a = self._artifact(artifact_id)
        return a is not None and a.epistemic_status in _PREMISE_STATUSES

    # -- writing -----------------------------------------------------------------------
    def note(self, text, *, model_id, supports=(), topics=()):
        """Store a model's note and record what it stands on. Returns the artifact id.

        A note is machine-originated and UNKNOWN, so it is never a root by itself. Every id in
        `supports` must exist and still stand: a note cannot be built on something already taken
        back. Raises ValueError otherwise, and writes nothing.
        """
        supports = tuple(dict.fromkeys(supports))
        bad = [s for s in supports if self._retracted(s)]
        if bad:
            raise ValueError(f"cannot build on a claim that is gone or retracted: {', '.join(bad)}")
        actor = Actor.model(model_id)
        artifact = self._ccc.ingest(
            text, actor=actor, epistemic_status=EpistemicStatus.UNKNOWN, topics=tuple(topics),
            reason="agent note: machine output, grounded only through a person-held root",
        )
        for support in supports:
            self._ccc.relate(artifact.artifact_id, support, RelationshipType.DERIVED_FROM, actor=actor,
                             reason=f"{model_id} declares this note stands on {support}")
        return artifact.artifact_id

    # -- grounding ---------------------------------------------------------------------
    def _resolve(self, artifact_id, assume_retracted, memo):
        if artifact_id in memo:
            return memo[artifact_id]
        memo[artifact_id] = (FLOATING, frozenset(), frozenset())  # cycle guard; edges only point at older notes
        if artifact_id in assume_retracted or self._retracted(artifact_id):
            result = (ORPHANED, frozenset(), frozenset({artifact_id}))
        elif self._is_root(artifact_id):
            result = (GROUNDED, frozenset({artifact_id}), frozenset())
        else:
            states = [self._resolve(s, assume_retracted, memo) for s in self._supports(artifact_id)]
            broken = frozenset().union(*(b for _, _, b in states)) if states else frozenset()
            if broken:
                result = (ORPHANED, frozenset(), broken)
            elif states and all(g == GROUNDED for g, _, _ in states):
                result = (GROUNDED, frozenset().union(*(r for _, r, _ in states)), frozenset())
            else:
                result = (FLOATING, frozenset(), frozenset())
        memo[artifact_id] = result
        return result

    def _claim(self, artifact_id, assume_retracted=frozenset(), memo=None):
        a = self._artifact(artifact_id)
        grounding, roots, broken = self._resolve(artifact_id, assume_retracted, {} if memo is None else memo)
        return GroundedClaim(artifact_id, a.content if a else "", f"{a.origin.kind.value.lower()}:{a.origin.actor_id}" if a else "gone",
                             grounding, tuple(sorted(roots)), tuple(sorted(broken)))

    def grounding(self, artifact_id):
        """One note's state now, with the roots it stands on or the retracted claims under it."""
        if self._artifact(artifact_id) is None:
            raise KeyError(artifact_id)
        return self._claim(artifact_id)

    def recall(self, *, topics=None, grounded_only=False):
        """The notes CCC still holds, each with its state. ORPHANED notes are listed so nobody builds on them
        unaware; `grounded_only` keeps just the ones a person still stands behind."""
        wanted = set(topics) if topics is not None else None
        memo, out = {}, []
        for a in self._ccc.store.artifacts.values():
            if not a.available or self._retracted(a.artifact_id):
                continue
            if wanted is not None and not wanted.intersection(a.topics):
                continue
            claim = self._claim(a.artifact_id, memo=memo)
            if grounded_only and claim.grounding != GROUNDED:
                continue
            out.append(claim)
        return out

    def impact(self, artifact_id):
        """What retracting `artifact_id` would do, without doing it: every note that stands today and whose state
        would change (a GROUNDED note losing its footing, or a FLOATING one now resting on something retracted).
        A preview for the person deciding; nothing is written."""
        if self._artifact(artifact_id) is None:
            raise KeyError(artifact_id)
        now_memo, then_memo, hit = {}, {}, []
        for a in self._ccc.store.artifacts.values():
            if a.artifact_id == artifact_id or not a.available or self._retracted(a.artifact_id):
                continue
            before = self._claim(a.artifact_id, memo=now_memo)
            after = self._claim(a.artifact_id, assume_retracted=frozenset({artifact_id}), memo=then_memo)
            if before.grounding != after.grounding:
                hit.append(after)
        return hit

    def require_grounded(self, claims):
        """The claims, if every one is still GROUNDED now. Raises Ungrounded naming the rest."""
        claims = list(claims)
        bad = [c for c in claims if self.grounding(c.artifact_id).grounding != GROUNDED]
        if bad:
            raise Ungrounded([self.grounding(c.artifact_id) for c in bad])
        return claims
