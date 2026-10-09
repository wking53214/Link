# link

link is the small application that connects three libraries:

- **Triad-42** runs advisory review sessions and produces candidate findings.
- **CCC** (Cognitive Continuity Constitution) is the record. It decides what
  has been recorded, who originated it, and whether a human has erased it.
- **CNS** decides whether an item may be used. Its admission door refuses
  anything CCC does not hold, and asks for a retry while CCC is still
  recording it.

None of the three libraries imports the others. link is the one place that
does, so the rules for each library stay with that library.

## What it does

`admit_session` takes a Triad-42 session and a real CCC system. For each
candidate, in order:

1. If CCC does not hold the candidate yet, link hands the session to CCC to
   record it, then checks again.
2. If CCC holds it, the candidate is admitted.
3. If a human erased it in CCC, it is refused for good. Handing the session
   off again never brings it back.
4. If the retry cap is reached, it is refused for good.

The admitted candidates come back in session order.

## Setup and the packaging caveat

CNS keeps its admission door in a folder called `cns_composition`. That folder
is not part of the `cns` package, by design, so the CNS package stays
shapes-only. link therefore needs two things:

- the pinned packages listed in `pyproject.toml`, installed normally, and
- a checkout of the CNS repository at the same pinned commit, with its
  folder on the Python path.

If the second part is missing, importing link fails with a message that says
so. This arrangement is deliberate for now. It is fine on one machine and
would need a packaging change to run elsewhere.

## Pinned commits

- CCC: main, `96cfc9c`
- Triad-42: main, `e5791c8`
- CNS: main, `da9ab8c`, which includes the retry loop (CNS PR #12).

## Tests

The tests run against the real CCC and Triad-42 packages, not stand-ins.
