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
  AT_RISK   it never declared a dependency on something that was taken back, but its writer
            had read it (see `AgentView`); not proven, so never trusted as grounded

`impact` shows a person what retracting a claim would do before they do it.

A note's list of what it stands on is written by the agent, so it can be incomplete or false.
`AgentView` adds an independent witness: the memory layer logs what each agent actually read. A note
may declare support only from what its writer read (no claiming a root it never saw), and anything
read but not declared is recorded as a possible dependency, which shows up as AT_RISK once it is
taken back and in the retraction preview. This is information-flow tracking: it sees only reads that
go through here (not the agent's prompt, training or other tools), and it over-warns on purpose.

A second witness does not depend on the agent at all: when a note's wording closely matches a stored
claim it did not declare, that claim is recorded as a possible dependency too (the same word-overlap
measure CCC uses for recurrence). It catches a restatement even if the claim was never read through
here. It shares that measure's limit: heavy rewording is not noticed, and a claim already withdrawn
cannot be compared (its text is gone).

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

__all__ = ["AT_RISK", "FLOATING", "GROUNDED", "ORPHANED", "AgentView", "GroundedClaim", "GroundedMemory", "Ungrounded", "UnreadSupport"]

GROUNDED, FLOATING, ORPHANED, AT_RISK = "GROUNDED", "FLOATING", "ORPHANED", "AT_RISK"
_POSSIBLE = "possible dependency (read, not declared)"
_PREMISE_STATUSES = frozenset({EpistemicStatus.EVIDENCE, EpistemicStatus.HISTORICAL_RECORD})


class UnreadSupport(ValueError):
    """A note declared support from something its writer never read."""


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

    def __init__(self, ccc_system, *, flag_similar=True) -> None:
        """`flag_similar` turns on the word-overlap default (needs the `match` extra, CCC's text matcher). It never
        silently does nothing: if it is on and the matcher is missing, this raises ImportError."""
        if not isinstance(ccc_system, CCCSystem):
            raise TypeError(f"GroundedMemory needs a ccc.CCCSystem; got {type(ccc_system).__name__}")
        self._ccc = ccc_system
        self._concepts = None
        if flag_similar:
            try:
                from cccb.recurrence import (
                    MINIMUM_SIGNATURE_SIZE,
                    RECURRENCE_THRESHOLD,
                    concept_set,
                )
            except ImportError as exc:
                raise ImportError(
                    "flag_similar needs CCC's text matcher (pip install \"link[match]\"); pass flag_similar=False "
                    "to go without the similar-wording default"
                ) from exc
            self._concepts, self._bar, self._min_size = concept_set, RECURRENCE_THRESHOLD, MINIMUM_SIGNATURE_SIZE

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

    def _soft_supports(self, artifact_id):
        return tuple(e.target_id for e in self._ccc.lineage.related(artifact_id, RelationshipType.RELATED_TO)
                     if e.source_id == artifact_id and e.reason.startswith(_POSSIBLE))

    def _record_possible(self, artifact_id, target_id, model_id, why="had read"):
        if target_id in self._soft_supports(artifact_id):
            return  # one possible dependency per claim, whichever witness saw it first
        self._ccc.relate(artifact_id, target_id, RelationshipType.RELATED_TO, actor=Actor.model(model_id),
                         reason=f"{_POSSIBLE}: {model_id} {why} {target_id}")

    def possible_dependencies(self, artifact_id):
        """(claim id, why) for everything this note may have depended on without declaring it."""
        return tuple((e.target_id, e.reason.split(": ", 1)[-1]) for e in
                     self._ccc.lineage.related(artifact_id, RelationshipType.RELATED_TO)
                     if e.source_id == artifact_id and e.reason.startswith(_POSSIBLE))

    def _flag_similar(self, artifact_id, text, model_id, declared):
        mine = self._concepts(text)
        if len(mine) < self._min_size:
            return
        for other in self._ccc.store.artifacts.values():
            if (other.artifact_id == artifact_id or other.artifact_id in declared or not other.available
                    or self._retracted(other.artifact_id)):
                continue
            theirs = self._concepts(other.content)
            if len(theirs) < self._min_size:
                continue
            score = len(mine & theirs) / len(mine | theirs)
            if score >= self._bar:
                self._record_possible(artifact_id, other.artifact_id, model_id, why=f"wrote similar wording ({score:.2f}) to")

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
        if self._concepts is not None:
            self._flag_similar(artifact.artifact_id, text, model_id, set(supports))
        return artifact.artifact_id

    def agent(self, model_id):
        """A view for one agent that logs its reads and checks what it declares (see `AgentView`)."""
        return AgentView(self, model_id)

    # -- grounding ---------------------------------------------------------------------
    def _resolve(self, artifact_id, assume_retracted, memo):
        """(state, roots, broken, risk): `broken` are retracted claims under it; `risk` are retracted claims it
        only possibly depended on (read, never declared)."""
        if artifact_id in memo:
            return memo[artifact_id]
        none = frozenset()
        memo[artifact_id] = (FLOATING, none, none, none)  # cycle guard; edges only point at older notes
        if artifact_id in assume_retracted or self._retracted(artifact_id):
            result = (ORPHANED, none, frozenset({artifact_id}), none)
        elif self._is_root(artifact_id):
            result = (GROUNDED, frozenset({artifact_id}), none, none)
        else:
            declared = [self._resolve(s, assume_retracted, memo) for s in self._supports(artifact_id)]
            soft = [self._resolve(s, assume_retracted, memo) for s in self._soft_supports(artifact_id)]
            broken = none.union(*(d[2] for d in declared)) if declared else none
            risk = none.union(*(d[3] for d in declared), *(d[2] | d[3] for d in soft)) if (declared or soft) else none
            if broken:
                result = (ORPHANED, none, broken, none)
            elif risk:
                result = (AT_RISK, none, none, risk)
            elif declared and all(d[0] == GROUNDED for d in declared):
                result = (GROUNDED, none.union(*(d[1] for d in declared)), none, none)
            else:
                result = (FLOATING, none, none, none)
        memo[artifact_id] = result
        return result

    def _claim(self, artifact_id, assume_retracted=frozenset(), memo=None):
        a = self._artifact(artifact_id)
        grounding, roots, broken, risk = self._resolve(artifact_id, assume_retracted, {} if memo is None else memo)
        broken = broken or risk  # an AT_RISK note shows the retracted claims it may have depended on
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


class AgentView:
    """One agent's window onto the memory. It logs what the agent reads and checks what it declares.

    `recall` and `read` record what this agent has seen. `note` then requires `supports` to be given (an
    empty tuple is the honest answer "I stand on nothing", and leaving it out is an error), refuses any
    support the agent never read, and records everything it read but did not declare as a possible
    dependency. Its own earlier notes count as read. The log lives in this object: a new view starts
    empty, so an agent that restarts must read again before it can declare support.
    """

    def __init__(self, memory, model_id) -> None:
        if not isinstance(memory, GroundedMemory):
            raise TypeError(f"AgentView needs a GroundedMemory; got {type(memory).__name__}")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("an agent view needs the agent's name")
        self._memory, self.model_id, self._seen = memory, model_id, set()

    @property
    def read_ids(self):
        return frozenset(self._seen)

    def recall(self, *, topics=None, grounded_only=False):
        claims = self._memory.recall(topics=topics, grounded_only=grounded_only)
        self._seen.update(c.artifact_id for c in claims)
        return claims

    def read(self, artifact_id):
        claim = self._memory.grounding(artifact_id)
        self._seen.add(artifact_id)
        return claim

    def note(self, text, *, supports, topics=()):
        supports = tuple(dict.fromkeys(supports))
        unread = [s for s in supports if s not in self._seen]
        if unread:
            raise UnreadSupport(f"{self.model_id} declared support from claims it never read: {', '.join(unread)}")
        artifact_id = self._memory.note(text, model_id=self.model_id, supports=supports, topics=topics)
        for read_id in sorted(self._seen - set(supports)):
            self._memory._record_possible(artifact_id, read_id, self.model_id)
        self._seen.add(artifact_id)
        return artifact_id
