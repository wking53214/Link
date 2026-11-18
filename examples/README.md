# Examples

Runnable walkthroughs. Each prints what Link does step by step. They are not part of
the test suite.

Run from the repo root with Link and its dependencies installed:

    python examples/walkthrough.py       # recurrence, revocation, other sources, memory gate
    python examples/grounded_memory.py   # grounded, floating, orphaned and at-risk notes
    python examples/read_log.py          # read log and similar-wording default

The walkthrough counts repeats by shared wording, so its three sample findings are
worded closely on purpose. See docs/WHAT_LINK_CAN_DO.md for how this behaves on real text.
