"""The front door for non-Triad sources."""

from __future__ import annotations

import pytest
from ccc import Actor, CCCSystem, EpistemicStatus

from link.door import SourceItem, UnrecordedOutput, admit_items, record_items

KEY = b"k" * 32
A = SourceItem("a1", "the config exposes a secret")
B = SourceItem("a2", "the loop is unbounded")
W = SourceItem("a3", "naming is inconsistent", surfaced=False, reason="below the severity bar")


def test_surfaced_items_are_admitted_in_order_and_withheld_ones_are_recorded_but_not_offered():
    system = CCCSystem()
    assert admit_items("scanner", [A, W, B], system) == [A, B]
    assert len(system.store.artifacts) == 3
    withheld = [a for a in system.store.artifacts.values() if a.metadata["candidate_id"] == "a3"][0]
    assert withheld.metadata["surfacing_reason"] == "below the severity bar"


def test_records_are_machine_originated_under_the_sources_own_identity():
    system = CCCSystem()
    admit_items("scanner", [A], system)
    (artifact,) = system.store.artifacts.values()
    assert artifact.origin == Actor.model("scanner")
    assert artifact.epistemic_status is EpistemicStatus.UNKNOWN


def test_running_again_records_nothing_twice():
    system = CCCSystem()
    admit_items("scanner", [A, B], system)
    admit_items("scanner", [A, B], system)
    assert len(system.store.artifacts) == 2


def test_an_erased_item_is_refused_and_stays_refused():
    system = CCCSystem()
    admit_items("scanner", [A], system)
    (artifact,) = system.store.artifacts.values()
    system.erase(artifact.artifact_id, actor=Actor.human(), reason="withdrawn", authorization_basis="test")
    for _ in range(2):
        with pytest.raises(UnrecordedOutput) as info:
            admit_items("scanner", [A], system)
        assert info.value.status == "erased"
    assert len(system.store.artifacts) == 1


def test_the_same_erased_text_under_a_new_id_is_refused_too():
    system = CCCSystem()
    admit_items("scanner", [A], system)
    (artifact,) = system.store.artifacts.values()
    system.erase(artifact.artifact_id, actor=Actor.human(), reason="withdrawn", authorization_basis="test")
    with pytest.raises(UnrecordedOutput):
        admit_items("scanner", [SourceItem("new-id", A.text)], system)


def test_one_source_cannot_use_anothers_records():
    system = CCCSystem()
    admit_items("scanner", [A], system)
    other = admit_items("linter", [A], system)
    assert other == [A]
    assert len(system.store.artifacts) == 2
    assert {a.origin.actor_id for a in system.store.artifacts.values()} == {"scanner", "linter"}


def test_triad_identity_cannot_be_borrowed():
    with pytest.raises(ValueError, match="Triad"):
        admit_items("triad42", [A], CCCSystem())
    with pytest.raises(ValueError):
        record_items("triad42", [A], CCCSystem())


def test_a_record_written_by_someone_else_in_the_sources_name_is_not_admitted_with_a_key():
    system = CCCSystem()
    system.ingest(A.text, actor=Actor.model("scanner"), epistemic_status=EpistemicStatus.UNKNOWN,
                  topics=("scanner",), reason="forged",
                  metadata={"source": "scanner", "candidate_id": "a1"})
    with pytest.raises(UnrecordedOutput) as info:
        admit_items("scanner", [A], system, attestation_key=KEY)
    assert info.value.status == "unattested"


def test_with_a_key_the_door_stamps_and_admits():
    system = CCCSystem()
    assert admit_items("scanner", [A, B], system, attestation_key=KEY) == [A, B]


def test_bad_input_is_refused():
    with pytest.raises(TypeError):
        admit_items("scanner", [A], object())
    with pytest.raises(ValueError):
        admit_items("", [A], CCCSystem())
    with pytest.raises(ValueError):
        SourceItem("x", "withheld without a reason", surfaced=False)
