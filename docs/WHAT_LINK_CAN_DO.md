# What Link can do, in plain language

Link started as a small piece of glue that carries the output of one AI reviewer
(Triad-42) into a gatekeeper (CNS), with a record keeper (CCC) in the middle. This
note says what else Link can now do, which parts are new, and what is still unproven.
Written 2026-11-17 against 59 passing tests.

## The idea in one sentence

AI output is treated as advice, not fact: it is written down, a person can take it
back, and nothing downstream may use it unless the record still stands.

## What it can do now

1. **Admit a review's findings** (`admit_session`). Only findings the reviewer
   actually showed are offered. Ones it held back are recorded, not offered.
2. **Count the same problem across separate reviews** (`record_recurrence`). One
   mention is a note. Three differently worded mentions in three independent reviews
   become a pattern that flags a person. Only a person can call it a mandate.
3. **Take it back everywhere** (`admit_session_with_receipts`, `use_admitted`,
   `revoked`). If a person erases a finding, everyone who held it is refused the next
   time they try to use it.
4. **Grade the reviewer** (`reviewer_calibration`). It compares what the reviewer
   showed with what it held back, and how often each later came back, was adopted by
   a person, or was erased.
5. **Admit output from any source, not just one reviewer** (`admit_items`). A
   scanner or another model gets the same rules, under its own name.
6. **Keep an agent's memory honest** (`MemoryGate`). A model's note comes back
   labelled "advisory, not a fact" until a person adopts it.

## What is new and what is not

| Idea | Honest status |
|---|---|
| Keep machine notes as "not a fact" until a person adopts them | **Common.** Several recent papers and posts describe this. Not new. |
| Count repeats across reviews, with one-step escalation and a person-only mandate | **Nothing matching found**, but the search was small. |
| Hand out receipts and re-check them at the moment of use | **Nothing matching found.** Erasure reaching copies is a known gap in the privacy literature. |
| All three together | **The only part I would call possibly new.** Unproven. |

Closest work found, by a quick search and not a survey: write-path auditing for
agent memory ([arXiv 2607.02579](https://arxiv.org/pdf/2607.02579)), provenance-grounded
memory ([Eywa](https://arxiv.org/pdf/2605.30771)), memory loops where one model's guess
becomes another's fact ([glukhov.org](https://www.glukhov.org/ai-systems/memory/self-reinforcing-memory-loops/)),
review state across rounds ([MCR-Bench write-up](https://codex.danielvaughan.com/2026/09/01/mcr-bench-dynamic-code-review-multi-round-state-tracking-codex-cli/)),
and erasure reaching downstream copies ([Gravitee](https://www.gravitee.io/corpus/gen-1993/data-protection-directive/right-to-erasure.html),
[Tech Policy Press](https://techpolicy.press/the-right-to-be-forgotten-is-dead-data-lives-forever-in-ai)).

## What is still unproven or limited

- **Mostly tiny tests.** Almost everything ran on small hand-made cases. The one
  real-data check is described below. Receipts, revocation, grounded memory and the
  read log have never seen real data or a real agent loop.
- **"Same problem" means "shares at least half its significant words".** This is
  the biggest limit, and a made-up billing-service run measured it. Three natural
  rewordings of one problem ("retried indefinitely", "no upper limit", "no cap on
  retries") scored 0.12 to 0.19 against the 0.5 bar, so they were **not** linked: three
  groups of one, no pattern. The matcher also treats "retries", "retried" and "retry"
  as different words. When the reviews kept most of the same words they scored 0.54 to
  0.58 and linked into one flagged pattern. A reviewer that rephrases a lot will never
  trigger it. The matcher's own notes say this is deliberate (a false link is worse
  than a missed one). Fixing it needs a meaning-aware step in CCC or CCCb, not in Link.
- **Echoes and independence.** Identical text counts as an echo, not a new sighting.
  Two reviews fed the same input by the same reviewer could still look independent.
- **Taking it back stops use, it does not delete copies.** A consumer that already
  copied the text keeps the copy. Some privacy rules call that not erasure.
- **The reviewer scorecard is slow on big stores** and only sees repeats that read
  as similar text.
- **No key means no proof of who wrote a record.** With a key, forged records are
  refused. Without one, they are not.
- **The memory gate cannot stop a model that ignores its label.** It labels and
  refuses; it does not judge truth. "A person adopted it" does not mean "it is correct".
- **One small stretch:** a review finding is handed to CCC marked "verified" only to
  mean "real, non-empty output that passed admission", not "true".

## Real-data check (2026-11-18)

Real duplicate bug reports (GitBugs) stand in for repeated findings. They are not AI
reviews, and the sample is small (28 clusters from Spark and Cassandra).

- The shipped matcher links only 11.8% of real duplicate pairs (typical word overlap
  0.07 against the 0.5 bar).
- Through the real `record_recurrence`, 3 of 28 clusters linked 2 or more reports into a
  pattern, and none reached the human-review flag.
- A character n-gram matcher ranks duplicates better (AUC 0.91 against 0.72). At a
  strict setting it changes little end to end (4 of 28 linked). At a loose setting it
  links 10 of 28 and flags 2, but unrelated reports start joining groups.
- Adding the report body made the shipped matcher worse (1 of 28).
- GloVe word vectors did not help. No sentence-embedding model was tested.
- The prior-art search stayed small, and arXiv papers were read only through search
  summaries.

So the repeat-counting works when findings share most of their words and rarely
otherwise. Treat the recurrence ladder as unproven on real wording.

## Questions worth answering before calling it novel

1. Does a careful search outside these few sources turn up the same combination?
2. Run on a real series of reviews, do three independent sightings actually look
   independent, or does the same reviewer echo itself?
3. Does a person retracting a finding reach the places that really use it, or only
   the ones wired through Link?
4. How much do real reviews reuse each other's key words? If it is rarely half, the
   repeat counting needs a meaning-aware matcher before it is worth relying on.
