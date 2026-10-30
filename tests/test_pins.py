"""The CCC pin in pyproject.toml tracks the reviewed commit link is built against.

The tests run against the real CCC, so the commit the install fetches must be
the one they were run with. The constant here moves with the pin, and moving
either is a reviewed change.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The CCC commit the runtime dependency installs. Moving it is a reviewed change.
EXPECTED_CCC_PIN = "9862cfb684ee6e6a3a62a40cbe4f7a9ef9e72c83"


def test_ccc_is_pinned_to_the_reviewed_commit():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    ccc = [d for d in data["project"]["dependencies"] if d.startswith("cognitive-continuity-constitution @ ")]
    assert len(ccc) == 1, data["project"]["dependencies"]
    found = re.fullmatch(
        r"cognitive-continuity-constitution @ git\+https://github\.com/wking53214/CCC(?:\.git)?@([0-9a-f]{40})",
        ccc[0],
    )
    assert found is not None, ccc[0]
    assert found.group(1) == EXPECTED_CCC_PIN
