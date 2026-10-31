# link

link is a small Python package (one module, `link/admission.py`, 76 lines) that
carries the output of a Triad-42 review session into CNS's admission door, with
CCC holding the record in between. It exposes one function, `admit_session`.

It is an integration seam between three libraries. It is not one of the five
hops of the CNS evidence spine (see "Role in STACK" below).

- **Triad-42** runs advisory review sessions and produces candidate findings.
- **CCC** (Cognitive Continuity Constitution) is the record. It decides what
  has been recorded, who originated it, and whether a human has erased it.
- **CNS** supplies the shape of the admission decision (PASS, RETRY,
  TERMINAL_BREACH) and, in its sibling package `cns_composition`, the gate that
  applies it to CCC's record. Items CCC does not hold are refused; while CCC is
  still recording one, the gate asks for a retry.

None of the three libraries imports the others. link is the one place that
does, so the rules for each library stay with that library.

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
contain. It was written to be the single importer of Triad-42, CCC and
`cns_composition`, so none of those depends on another.

**Inputs and outputs.**

| | |
|---|---|
| In | a `triad42.Session`, a `ccc.CCCSystem`, optionally a `ResubmissionGuard` and an `attestation_key` |
| Out | a list of `TriadOutput` (candidate id and text) in session order, or an exception |
| Side effect | the CCC handoff, which records the session's candidates (surfaced and withheld) in the supplied `CCCSystem` |

**Owns.** The choice of which Triad candidates are offered to the door (only
exactly SURFACED), the ordering (hand off first, admit in session order), and the
wiring of the three libraries.

**Does not own.** Whether a candidate is true or any good (Triad-42's review is
advisory and link does not judge it). What CCC holds, who originated it, and
erasure (CCC). The gate, its outcomes and the retry cap (`cns_composition`, on
the shapes in `cns`). Any permission: admission here means "CCC holds this
record, so this process may use it", not that anything downstream must accept
it. Receivers apply their own policy.

**Relationship to the evidence spine.** The CNS evidence spine runs one document
through HERALD, TIE, Conservation_Kernel, Governance_Gateway and CCC. Link is
not a hop in that chain. It imports none of HERALD, TIE, Conservation_Kernel or
Governance_Gateway, and it does not call CCCb. Its only contact with the spine
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

## CNS interaction and status

Status: **partial**, meaning implemented against `cns` and `cns_composition`
only, and absent for the rest of CNS.

- Implemented: link imports and calls the composition admission door.
  `link/admission.py:21-23` imports `TriadOutput`, `ResubmissionGuard` and
  `admit_candidates` from `cns_composition`; `link/admission.py:71-76` calls
  `admit_candidates`, which builds the CNS gate and returns on PASS, hands off
  again on RETRY and raises on anything else. `tests/test_admission.py:11-13`
  imports `cns.gate.GateOutcome` and the composition gate name and exception,
  and the tests run the real door.
- Absent: no import of `cns_interop` anywhere in link. link does not send or
  receive UAI-1 signed messages, uses no envelope, identity, grant or ledger
  from `cns_interop`, and does not use the CNS evidence-spine chain
  (`chains/evidence_spine.py`).
- link does not forward `attestation_key` to the gate itself
  (`link/admission.py:71-76`); the key reaches the check through the
  `MachineRecords` lookup (`link/admission.py:74`). The key tests
  (`tests/test_admission.py:207-264`) pass against that wiring.

CNS is pinned to the tag `v2.3.0` (`pyproject.toml`), whose wheel ships
`cns_composition` beside `cns`.

## Setup

Installing link installs its three pinned dependencies; no CNS checkout on the
Python path is needed.

```
pip install -e ".[dev]"
```

## Pinned commits

- CCC: main, `9862cfb` (the pin is held by `tests/test_pins.py`)
- Triad-42: main, `58a2c7f`
- CNS: tag `v2.3.0`, commit `41592fb`

## Tests and maturity

The tests run against the real CCC and Triad-42 packages and the real CNS
admission door, not stand-ins.

```
python -m pytest -q
```

Measured 2026-10-31 in a fresh venv installed from the pins: 21 passed, 0
failed, 0 skipped (20 in `tests/test_admission.py`, 1 in `tests/test_pins.py`).

Limitations:

- Version 0.1.0, one function, no CLI and no service. It runs inside the
  caller's process against an in-memory or caller-supplied `CCCSystem`.
- Admission is only as strong as CCC's record. Without `attestation_key` a
  record forged in the Triad's name is admitted
  (`test_without_a_key_the_same_forgery_is_admitted`).
- The caller supplies and protects the key; link does not generate, store or
  rotate one.
- The retry cap and refusal rules belong to `cns_composition`, and a change
  there moves link's behaviour when the CNS pin moves.
- No test asserts anything about this README.
