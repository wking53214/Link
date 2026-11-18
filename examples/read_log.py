from ccc import Actor, CCCSystem, EpistemicStatus

from link.grounding import GroundedMemory, UnreadSupport

ccc = CCCSystem(allow_unguarded_writes=True, allow_unverified_humans=True)
mem = GroundedMemory(ccc)
person, names = Actor.human(), {}

fact = mem.note("deploy 41 doubled checkout latency", model_id="scribe", supports=(), topics=("checkout",))
ccc.classify(fact, EpistemicStatus.EVIDENCE, actor=person, reason="checked the graph myself")
names[fact] = "person-held fact"

planner = mem.agent("planner"); planner.recall(topics=["checkout"])
honest = planner.note("the new cache is the cause", supports=[fact]); names[honest] = "planner (declared its basis)"

coder = mem.agent("coder"); coder.recall(topics=["checkout"])
forgetful = coder.note("roll back the cache change", supports=()); names[forgetful] = "coder (read it, forgot to declare)"

liar = mem.agent("critic")
try:
    liar.note("DNS is the real cause", supports=[fact])
except UnreadSupport as e:
    print("Critic claims to stand on the fact without ever reading it -> refused")
    print("   ", str(e)[:75])

print("\nPerson previews withdrawing the fact:")
for c in mem.impact(fact):
    print(f"   {c.grounding:9} {names[c.artifact_id]}")

ccc.erase(fact, actor=person, reason="misread: wrong dashboard", authorization_basis="demo")
print("\nAfter the person withdraws it:")
for c in mem.recall():
    print(f"   {c.grounding:9} {names[c.artifact_id]}")
