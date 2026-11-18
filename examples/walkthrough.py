"""A realistic walk through Link: one made-up billing service, several AI review sessions."""
import time

from ccc import Actor, CCCSystem, EpistemicStatus
from cccb import TextMatcher
from cns_composition.ccc_admission import UnrecordedTriadOutput
from triad42 import Label, LabeledItem, Session, Severity
from triad42.retrieval import SurfacingStatus

from link.calibration import reviewer_calibration
from link.door import SourceItem, admit_items
from link.memory_gate import LaunderingRefused, MemoryGate
from link.recurrence import record_recurrence
from link.revocation import admit_session_with_receipts, revoked, use_admitted

ccc = CCCSystem(text_matcher=TextMatcher(), private_source_markers=(),
                allow_unguarded_writes=True, allow_unverified_humans=True)
human = Actor.human()


def review(shown, withheld=()):
    s = Session()
    rp = s.start_pass(LabeledItem("The billing service design.", Label.ASSUMPTION))
    keep = {rp.add_finding(t, Severity.HIGH, scope="billing").finding_id for t in shown}
    for t in withheld:
        rp.add_finding(t, Severity.LOW, scope="billing")
    s.harvest(rp, surfaced_ids=keep)
    return s


def say(title):
    print(f"\n=== {title}")


# --- Three separate reviews describe the same problem in different words.
A = "billing retries failed charges without a limit, so a declined card loops forever"
B = "the billing service keeps retrying failed charges with no limit, so a declined card loops"
C = "failed charges are retried with no limit in billing: a declined card can loop forever"
FONT_WITHHELD = "the invoice footer uses an inconsistent font across the PDF templates"

say("1. Three independent reviews, three different wordings")
sessions = []
for name, text, held in (("Mon", A, [FONT_WITHHELD]), ("Wed", B, []), ("Fri", C, [])):
    s = review([text], held)
    new = record_recurrence(s, ccc)
    sessions.append(s)
    groups = ccc.recurring_groups()
    top = groups[0] if groups else None
    print(f"{name}: recorded {len(new)} finding(s). Groups now: {len(groups)}"
          + (f", biggest has {top.occurrence_count} sighting(s), stage {top.stage.name}, needs a human: {top.needs_human_review}" if top else ""))
mandates = [d for d in ccc.store.discoveries.values() if d.stage.name == "MANDATE"]
print(f"Anything declared a MANDATE by the machine? {len(mandates)} (only a human may do that)")

say("2. The same reviewer repeating itself word for word")
echo = review([A])
record_recurrence(echo, ccc)
g = next(x for x in ccc.recurring_groups() if any(A in ccc.store.discoveries[d].conclusion for d in x.occurrences + x.duplicates))
print(f"After an exact repeat: {g.occurrence_count} real sightings, {len(g.duplicates)} echo(es) kept but not counted")

say("3. A finding the reviewer held back shows up later in someone else's review")
time.sleep(0.05)
later = review(["the invoice footer font is inconsistent across the PDF templates"])
record_recurrence(later, ccc)
cal = reviewer_calibration(ccc)
w, sh = cal[SurfacingStatus.NOT_SURFACED], cal[SurfacingStatus.SURFACED]
print(f"Held back: {w.total}, later came back: {w.recurred}.  Shown: {sh.total}, later came back: {sh.recurred}")

say("4. A person takes a finding back, and everyone who held it finds out")
fresh = CCCSystem(allow_unguarded_writes=True, allow_unverified_humans=True)
s = review([B, "the retry timer is not reset after a restart"])
receipts = admit_session_with_receipts(s, fresh)
print(f"Admitted {len(receipts)} findings with receipts; any withdrawn? {len(revoked(receipts, fresh))}")
art = next(a for a in fresh.store.artifacts.values() if a.content == B)
fresh.erase(art.artifact_id, actor=human, reason="reviewer was wrong about this service", authorization_basis="demo")
for r, why in revoked(receipts, fresh):
    print(f"Now withdrawn: {r.output.text[:50]}...  ({why})")
try:
    use_admitted(receipts[0], fresh)
except UnrecordedTriadOutput:
    print("Using the withdrawn finding is refused. The other finding still works:",
          use_admitted(receipts[1], fresh).text[:40] + "...")

say("5. Another tool (a code scanner) gets the same rules, under its own name")
items = [SourceItem("s1", "hard-coded API key in billing/config.py"),
         SourceItem("s2", "unused import in billing/util.py", surfaced=False, reason="below the severity bar")]
print("Admitted:", [i.candidate_id for i in admit_items("scanner", items, fresh)], "(the held-back one is recorded but not offered)")
try:
    admit_items("triad42", items, fresh)
except ValueError as e:
    print("Pretending to be the reviewer is refused:", str(e)[:70])

say("6. An AI agent's memory")
gate = MemoryGate(CCCSystem(allow_unguarded_writes=True, allow_unverified_humans=True))
note = gate.remember("the retry cap is the root cause of last week's outage", model_id="planner", topics=("billing",))
print(gate.render(gate.recall(topics=["billing"])))
try:
    gate.require_premises(gate.recall(topics=["billing"]))
except LaunderingRefused:
    print("Using it as a fact is refused (a model said it, no person adopted it)")
gate._ccc.classify(note, EpistemicStatus.EVIDENCE, actor=human, reason="checked the logs")
print(gate.render(gate.recall(topics=["billing"])))
print("Now it can be used as a fact:", len(gate.require_premises(gate.recall(topics=["billing"]))) == 1)
