from ccc import Actor, CCCSystem, EpistemicStatus
from triad42 import Label, LabeledItem, Session, Severity

from link.admission import admit_session
from link.grounding import GroundedMemory, Ungrounded

ccc = CCCSystem(allow_unguarded_writes=True, allow_unverified_humans=True)
mem = GroundedMemory(ccc)
person = Actor.human()
names = {}

def show(title):
    print(f"\n--- {title}")
    for c in mem.recall():
        why = f"stands on {len(c.roots)} person-held claim(s)" if c.grounding == "GROUNDED" else (
              f"retracted underneath: {len(c.broken)}" if c.grounding == "ORPHANED" else "no person behind it")
        print(f"  {c.grounding:9} {names.get(c.artifact_id, c.artifact_id[:6]):28} {why}")

# 1. A reviewer's finding is admitted the normal Link way.
s = Session()
rp = s.start_pass(LabeledItem("The checkout design.", Label.ASSUMPTION))
f = rp.add_finding("deploy 41 doubled checkout latency", Severity.HIGH, scope="checkout")
s.harvest(rp, surfaced_ids={f.finding_id})
admit_session(s, ccc)
finding = next(iter(s.handed_off.values()))
names[finding] = "reviewer finding"

# 2. A person reads it and adopts it. That is the only way to make a root.
ccc.classify(finding, EpistemicStatus.EVIDENCE, actor=person, reason="checked the graph myself")

# 3. Agents build on it, each declaring what it stands on.
cache = mem.note("the new cache is the cause", model_id="planner", supports=[finding]); names[cache] = "planner: cache is the cause"
fix = mem.note("roll back the cache change", model_id="coder", supports=[cache]); names[fix] = "coder: roll back the cache"
guess = mem.note("DNS may also be slow", model_id="critic"); names[guess] = "critic: DNS guess (no basis)"
plan = mem.note("roll back and then check DNS", model_id="lead", supports=[fix, guess]); names[plan] = "lead: combined plan"
side = mem.note("page the on-call team", model_id="ops", supports=[finding]); names[side] = "ops: page on-call"
show("Before: what each note stands on")

# 4. Before retracting, the person previews the damage.
print("\n--- A person is about to withdraw the reviewer finding. Preview:")
for c in mem.impact(finding):
    print(f"  would lose its footing: {names[c.artifact_id]}")
print(f"  (nothing changed yet: planner note is still {mem.grounding(cache).grounding})")

# 5. They retract it.
ccc.erase(finding, actor=person, reason="I misread the graph; it was a different dashboard", authorization_basis="demo")
show("After the person withdraws the finding")

# 6. Someone tries to keep building on the dead branch.
try:
    mem.note("also add a cache warm-up", model_id="coder", supports=[finding])
except ValueError as e:
    print("\n--- New note on the withdrawn finding is refused:", str(e)[:60])
try:
    mem.require_grounded([c for c in mem.recall() if c.artifact_id == plan])
except Ungrounded as e:
    print("--- Using the lead's plan as established is refused:", type(e).__name__)
