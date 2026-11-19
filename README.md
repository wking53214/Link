# link

link is a small Python package (`link/admission.py` plus two optional modules,
`link/recurrence.py` and `link/calibration.py`) that
carries the output of a Triad-42 review session into CNS's admission door, with
CCC holding the record in between. Its core function is `admit_session`; `record_recurrence` and
`reviewer_calibration` build on it (below).

It is an integration seam between three libraries. It is not one of the five
hops of the CNS evidence spine (see "Role in STACK" below).

- **Triad-42** runs advisory review sessions and produces candidate findings.
- **CCC** (Cognitive Continuity Constitution) is the record. It decides what
  has been recorded, who originated it, and whether a human has erased it.
- **CNS** supplies the shape of the admission decision (PASS, RETRY,
  TERMINAL_BREACH) and, in its sibling package `cns_composition`, the gate that
  applies it to CCC's record. Items CCC does not hold are refused; while CCC is
  still recording one, the gate asks for a retry.

None of the three libraries needs another to install or run, and link is the
one place that uses all three together. They are not import-free of each other:
Triad-42's handoff module (`triad42/ccc_handoff.py`, its optional `ccc` extra)
imports CCC, and link calls that module; Triad-42 and CCC each also carry an
optional CNS connector that loads `cns.gate` on demand (INSPECTED 2026-11-17 at
the pins below). CNS's packages import neither of the other two.

## What it does

`admit_session` takes a Triad-42 session and a real CCC system (a
`ccc.CCCSystem`; anything else raises `TypeError`). It considers only the
candidates the review surfaced. Triad also records the candidates it did not
show, with the reason, so that withholding one is never silent; every one of
those is still recorded in CCC as an audit trail, but none is offered to CNS,
because the review never presented it. A status that is not exactly SURFACED is
treated the same way. link hands the session to CCC first, on every run, so a
session with a pass that was never harvested is refused even when every
candidate is already held. Then, for each surfaced candidate, in order:

1. If CCC does not hold the candidate yet, link hands the session to CCC to
   record it, then checks again.
2. If CCC holds it, the candidate is admitted.
3. If a human erased it in CCC, it is refused for good. Handing the session
   off again never brings it back.
4. If the retry cap is reached, it is refused for good.

The admitted candidates come back in session order. A refusal raises
`UnrecordedTriadOutput` (from `cns_composition`).

Optionally, `attestation_key` (bytes, at least 16, supplied by the caller)
makes the handoff stamp each record and makes CCC's lookup count only stamped
records, so a record someone else wrote in the Triad's name is not admitted.
Without a key the answer is as unauthenticated as the underlying records. link
never holds or defaults a key.

## Role in STACK

**What link is.** The glue that the other libraries deliberately do not
contain. It is the only package that imports Triad-42, CCC and
`cns_composition` together, so none of those has to depend on another to be
installed (the optional imports between them are listed at the top).

**Inputs and outputs.**

| | |
|---|---|
| In | a `triad42.Session`, a `ccc.CCCSystem`, optionally a `ResubmissionGuard` and an `attestation_key` |
| Out | a list of `TriadOutput` (candidate id and text) in session order, or an exception |
| Side effect | the CCC handoff, which records the session's candidates (surfaced and withheld) in the supplied `CCCSystem` |

**Owns.** The choice of which Triad candidates are offered to the door (only
exactly SURFACED), the ordering (hand off first, admit in session order), and the
wiring of the three libraries.

**Authority matrix.** Mostly wiring, with a few rules of its own. The admission decision and the record belong to `cns_composition` and CCC. link's own rules are the ones under "Owns" above, plus two more: the door refuses the source name `triad42`, and `MemoryGate.require_premises` accepts a claim as a premise only when a human holds it at EVIDENCE or HISTORICAL_RECORD. It enforces at its own exits only, by raising (`UnrecordedTriadOutput`, `UnrecordedOutput`, `LaunderingRefused`, `TypeError`, `ValueError`); nothing stops a caller that ignores the exception. `reviewer_calibration` evaluates the record by counting, read-only. link authenticates no one: an `attestation_key` is the caller's, and link passes it to Triad-42's handoff, CCC's lookup and CNS's door. It issues no permission and writes no evidence of its own beyond the records it asks CCC to hold; receipts are CNS's. **Fail behavior.** Closed: an item CCC does not hold is refused, and the retry cap belongs to the gate. Without `attestation_key` a record forged in the Triad's name is admitted (stated under Limitations).

**Does not own.** Whether a candidate is true or any good (Triad-42's review is
advisory and link does not judge it). What CCC holds, who originated it, and
erasure (CCC). The gate, its outcomes and the retry cap (`cns_composition`, on
the shapes in `cns`). Any permission: admission here means "CCC holds this
record, so this process may use it", not that anything downstream must accept
it. Receivers apply their own policy.

**Relationship to the evidence spine.** The CNS evidence spine runs one document
through HERALD, TIE, Conservation_Kernel, Governance_Gateway and CCC. Link is
not a hop in that chain. It imports none of HERALD, TIE, Conservation_Kernel or
Governance_Gateway. `admit_session` does not use CCCb; the optional `match`
extra does (`link/calibration.py` builds CCCb's `TextMatcher`, and
`record_recurrence` needs a CCC system that has one). Its only contact with the spine
is CCC, which it shares as the record: link writes Triad-42 candidates into a
CCC system and reads them back, which is a separate flow from the spine's
ingest. CNS's own link ledger lists Link as a repository with a two-way
connector (`link/admission.py` toward CNS, `cns_composition/consumers.py` back),
not as a spine stage.

```
  Triad-42 session
        |  candidates (SURFACED / withheld)
        v
  link.admit_session ---- hand_off(session, ccc) ----> CCC  (record)
        |                                               ^
        |  only SURFACED candidates                     | held? erased?
        v                                               |
  cns_composition.admit_candidates --- MachineRecords --+
        |   gate: PASS / RETRY (hand off again) / TERMINAL_BREACH
        v
  admitted TriadOutput list   or   UnrecordedTriadOutput

  (HERALD -> TIE -> Conservation_Kernel -> Governance_Gateway -> CCC
   is the evidence spine; link is not on it.)
```

## Cross-session recurrence

`link.recurrence.record_recurrence(session, ccc_system)` runs `admit_session`,
then records each admitted FINDING in CCC's recurrence ladder
(`record_external_finding`). Triad's 1/2/3 rule only counts inside one session;
this lets independent sessions add up. Three differently worded sightings of the
same problem become a PATTERN that CCC flags for human review
(`ccc_system.recurring_groups()`). MANDATE stays human-only.

- Erased and withheld findings never reach the ladder. Running a session twice
  records nothing new.
- The same text found again is kept as a duplicate and not counted. Sightings
  must be worded differently to count as independent, which is CCC's rule.
- `verified=True` is passed to CCC only to mean "real, admitted review output".
  Records stay machine-originated inferences, not verified fact.
- The CCC system needs a text matcher (`cccb`, installed with `pip install ".[match]"`) and
  `private_source_markers` stated.

## Reviewer calibration

`link.calibration.reviewer_calibration(ccc_system)` is a read-only ledger. For
Triad FINDING records it reports, separately for surfaced and withheld
candidates: how many there are, how many a later session surfaced again
(`recurred`), how many a human promoted, and how many a human erased. A withheld
group that recurs or is promoted as often as the surfaced group suggests the
reviewer's withholding is losing signal. It measures the record, not the
reviewer, and small counts mean little. Recurrence uses CCC's text matcher, so
it only sees repeats worded similarly, and same-session repeats do not count.

## Revocation, other sources, and agent memory

- **Revocation.** `link.revocation.admit_session_with_receipts` returns a receipt
  per admitted Triad finding; `use_admitted(receipt, ccc)` re-asks CCC at the
  moment of use and refuses an item a human has since erased, redacted, rejected
  or superseded; `revoked(receipts, ccc)` lists what has been withdrawn. The
  recheck is CNS's; link wires it to a real CCC system.
- **Other sources.** `link.door.admit_items(source, items, ccc)` gives any
  advisory source (a scanner, another model) the same discipline: everything it
  produced is recorded in CCC under its own machine identity, only surfaced items
  are offered, and an item is admitted only while CCC holds exactly that text.
  The decision is CNS's: the door calls CNS's admission door with the source
  name (a parameter since CNS 4.1.0). The name `triad42` is refused here so no
  source can borrow Triad's identity. A refusal is `UnrecordedOutput`, whose
  `status` is CCC's answer and whose `__cause__` is CNS's verdict.
- **Agent memory.** `link.memory_gate.MemoryGate` stores a model's output as
  machine-originated and UNKNOWN. `recall` returns only what CCC still holds,
  each claim labelled with its origin; a claim is a premise only when a human
  holds it at EVIDENCE or HISTORICAL_RECORD, and `require_premises` refuses
  anything else. It labels and refuses; it cannot stop a model that ignores the
  label, and a human-held status means adopted, not correct.

## Grounded memory

`link.grounding.GroundedMemory` goes one step past `MemoryGate`. A model's note says what it
was built on when it is written (`note(text, model_id=..., supports=[...])`), and a note can
only be built on something that still stands. Each note is GROUNDED (every note under it ends in a
claim a person still holds), FLOATING (something under it is a machine note no person is behind),
or ORPHANED (something under it was erased, redacted, rejected or superseded). Only a person can
make a root, so a machine cannot ground its own notes. `impact(claim_id)` shows a person every note
whose state would change if they retracted that claim, before they do it, and writes nothing.
`require_grounded` re-checks the record and refuses anything not GROUNDED now.

The dependency idea is classic truth maintenance, and recent papers apply it to agent memory (for
example PACMI, arXiv 2610.05732). What is specific here is the human-only roots, dependencies checked
when the note is written, and the retraction preview. It does not judge whether a root is true.

A note's list of what it stands on is written by the agent, so it can be left out or false. `memory.agent(name)`
returns an `AgentView` that adds an independent witness: it logs what the agent actually read, requires
`supports` to be given (an empty tuple is the honest "I stand on nothing"), refuses support from anything the agent
never read, and records what it read but did not declare as a possible dependency. A possible dependency never
makes a note grounded, but once the claim is withdrawn the note is AT_RISK (not trusted as grounded, shown in the
retraction preview) instead of silently unaffected. This is information-flow tracking. It sees only reads that go
through here, not the agent's prompt, training or other tools, and it over-warns on purpose.

A second witness does not depend on the agent at all: when a note's wording closely matches a stored claim it did
not declare, that claim is also recorded as a possible dependency (`possible_dependencies(note_id)` lists them and
why), using the same word-overlap measure CCC uses for recurrence. It catches a restatement even if the claim was
never read through Link. It needs the `match` extra (it raises `ImportError` rather than silently doing nothing;
pass `flag_similar=False` to go without), and it has that measure's limits: heavy rewording is not noticed, and a
claim already withdrawn cannot be compared because its text is gone.

## CNS interaction and status

Status: **partial**, meaning implemented against `cns` and `cns_composition`
only, and absent for the rest of CNS.

- Implemented: link imports and calls the composition admission door.
  `link/admission.py:21-23` imports `TriadOutput`, `ResubmissionGuard` and
  `admit_candidates` from `cns_composition`; `link/admission.py:78-84` calls
  `admit_candidates`, which builds the CNS gate and returns on PASS, hands off
  again on RETRY and raises on anything else. `tests/test_admission.py:11-13`
  imports `cns.gate.GateOutcome` and the composition gate name and exception,
  and the tests run the real door.
- Absent: no import of `cns_interop` anywhere in link. link does not send or
  receive UAI-1 signed messages, uses no envelope, identity, grant or ledger
  from `cns_interop`, and does not use the CNS evidence-spine chain
  (`chains/evidence_spine.py`).
- Since 2026-11-15 link passes `attestation_key` to CNS's door as well as to
  the `MachineRecords` lookup (`link/admission.py:78-84`), and the door checks
  the stamp itself, so a lookup that only answers "held" is refused
  (`test_with_a_key_cnss_door_checks_the_stamp_itself_and_a_lookup_that_only_says_held_is_refused`).
  An earlier version of this bullet said the key was not forwarded; that was
  true before commit `520d20d`. The key tests are the `test_with_a_key_*` and
  `test_without_a_key_*` cases in `tests/test_admission.py`.

CNS is pinned to the tag `v4.1.0` (`pyproject.toml`), whose wheel ships
`cns_composition` beside `cns`.

## Setup

Installing link installs its three pinned dependencies (`record_recurrence` and
`reviewer_calibration` also need the `match` extra, which adds CCC's text matcher); no CNS checkout on the
Python path is needed.

```
pip install -e ".[dev]"
```

## Pinned commits

- CCC: main, `d133b81` (the pin is held by `tests/test_pins.py`)
- Triad-42: main, `e908e32`
- CNS: tag `v4.1.0`, commit `c84ef8c`
- CCCb (the `match` extra only): `8e3c779`

## Tests and maturity

The tests run against the real CCC and Triad-42 packages and the real CNS
admission door, not stand-ins.

```
python -m pytest -q
```

Measured 2026-11-16 in a fresh venv installed from the pins: 59 passed, 0
failed, 0 skipped (23 admission, 1 pins, 6 recurrence, 5 calibration, 4 revocation,
12 door, 8 memory gate).

EXECUTED 2026-11-17 at `be4aa33`, Python 3.13, in fresh environments installed from the pins: 59 passed, 0 failed, 0 skipped, both with `pip install ".[dev]"` (the way CI installs) and with the editable line under "Setup". The per-file figures above match. The same 59 pass with CCC and CCCb moved to their mains (`2379de8`, `5d27a12`), so the CCC guard change no longer breaks this suite. At the earlier commit `18ded80` the suite gives 57 (EXECUTED the same day): three admission tests were added on 2026-11-15, after the 54 measured on 2026-11-12, and two door tests on 2026-11-16. Not run: GitHub CI, Python 3.11 and 3.12 (CI's versions). `ruff check .` reports 7 findings with ruff 0.17.5; lint is not part of CI here.

EXECUTED 2026-11-19 at `062dbd2`, Python 3.13, a fresh environment installed from the pins with `pip install ".[dev]"`: 92 passed, 0 failed, 0 skipped. The 33 tests added since `be4aa33` are 13 grounding, 10 agent view and 10 similar wording; the other files are as above. The pins listed above did not change. Not run: CI.

Limitations:

- Version 0.1.0, six entry points, no CLI and no service. It runs inside the
  caller's process against an in-memory or caller-supplied `CCCSystem`.
- Admission is only as strong as CCC's record. Without `attestation_key` a
  record forged in the Triad's name is admitted
  (`test_without_a_key_the_same_forgery_is_admitted`).
- The caller supplies and protects the key; link does not generate, store or
  rotate one.
- The retry cap and refusal rules belong to `cns_composition`, and a change
  there moves link's behaviour when the CNS pin moves.
- Recurrence counts differently worded sightings. Two sessions given the same
  input by the same reviewer can echo each other in new words and still count as
  independent; link has no notion of independent input.
- `reviewer_calibration` rebuilds a matcher per finding, so it suits small
  stores, and it sees only repeats that read as similar text.
- No test asserts anything about this README.
