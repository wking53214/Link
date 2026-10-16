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

## Setup

CNS keeps its admission door in a package called `cns_composition`. It ships in
the same wheel as `cns`, beside it, so installing the pinned packages in
`pyproject.toml` normally is all link needs. Earlier versions of this README
required a CNS checkout on the Python path; that is no longer so.

## Pinned commits

- CCC: main, `96cfc9c`
- Triad-42: main, `e5791c8`
- CNS: `e638e08`, the commit that ships `cns_composition` in the wheel. It sits on a branch, not on CNS main yet; re-pin to a CNS tag once one carries it.

## Tests

The tests run against the real CCC and Triad-42 packages, not stand-ins.
