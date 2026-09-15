import copy

import pytest

from ml.candidate_audit import normalize_border_rounding
from ml.candidate_decisions import case_catalog, import_batch
from ml.candidate_derive import derive
from ml.candidate_manifest import build_packet
from ml.tests.test_candidate_manifest import dsp, meiwei

PACKET_HASH = "a" * 64


def fixture():
    report, inventory = dsp()
    box = [1, 1, 19.01, 2]
    inventory["images"][0]["annotations"][0]["bbox"] = box
    report["border_normalization"] = {
        "proposals": [
            {
                "file": "a.jpg",
                "split": "train",
                "annotation_index": 0,
                "category_id": 1,
                "before_xywh": box,
                "after_xywh": normalize_border_rounding(box, 20, 20),
            }
        ]
    }
    return build_packet(report, inventory), inventory


def ledger(packet, kinds, reviewer="Reviewer A", previous=None):
    catalog = case_catalog(packet)
    batch = {
        "schema_version": "1.0",
        "packet_sha256": PACKET_HASH,
        "reviewer": reviewer,
        "reviewed_at": "2026-09-15T10:00:00+05:00",
        "decisions": [
            {
                "case_id": identity,
                "answers": kinds[case["kind"]],
                "rationale": "Synthetic test reference.",
            }
            for identity, case in catalog.items()
            if case["kind"] in kinds
        ],
    }
    return import_batch(batch, catalog, PACKET_HASH, previous, "b" * 64 if previous else None)[0]


def test_no_reviews_preserve_annotations_groups_and_block_release():
    packet, inventory = fixture()
    original = copy.deepcopy((packet, inventory))
    result = derive(packet, inventory, PACKET_HASH)
    assert result["summary"]["applied_corrections"] == 0
    assert result["summary"]["reviewed_group_links"] == 0
    assert result["summary"]["remaining_invalid_boxes"] == 1
    assert result["summary"]["case_blockers"] == len(case_catalog(packet))
    assert not result["ready_for_training"] and not result["production_eligible"]
    assert all(g["proposed_split"] is None for g in result["groups"])
    assert (packet, inventory) == original


def test_uncontested_reviews_apply_only_derived_boxes_and_related_links():
    packet, inventory = fixture()
    original = copy.deepcopy(inventory)
    review = ledger(packet, {"box": {"correction": "accept"}, "near": {"relationship": "related"}})
    result = derive(packet, inventory, PACKET_HASH, review)
    assert result["summary"]["applied_corrections"] == 1
    assert result["summary"]["groups"] == 1
    assert result["summary"]["cross_source_split_groups"] == 1
    assert result["summary"]["remaining_invalid_boxes"] == 0
    assert result["applied_corrections"][0]["before_xywh"] == [1, 1, 19.01, 2]
    assert result["applied_corrections"][0]["after_xywh"] == [1, 1, 19, 2]
    assert inventory == original
    assert result["summary"]["annotations"] == 2
    assert not result["ready_for_training"]


def test_conflicting_reviews_apply_nothing():
    packet, inventory = fixture()
    first = ledger(packet, {"box": {"correction": "accept"}, "near": {"relationship": "related"}})
    second = ledger(
        packet,
        {"box": {"correction": "reject"}, "near": {"relationship": "unrelated"}},
        reviewer="Reviewer B",
        previous=first,
    )
    result = derive(packet, inventory, PACKET_HASH, second)
    assert not result["applied_corrections"] and not result["reviewed_group_links"]
    assert result["summary"]["blocker_reasons"]["conflicting"] == 2


def test_rejected_correction_remains_blocking():
    packet, inventory = fixture()
    result = derive(
        packet, inventory, PACKET_HASH, ledger(packet, {"box": {"correction": "reject"}})
    )
    assert result["summary"]["blocker_reasons"]["border_correction_rejected"] == 1
    assert result["summary"]["remaining_invalid_boxes"] == 1


def test_unrelated_decisions_cannot_split_existing_exact_pair_groups():
    report, inventory = meiwei()
    packet = build_packet(report, inventory)
    result = derive(
        packet, inventory, PACKET_HASH, ledger(packet, {"near": {"relationship": "unrelated"}})
    )
    assert result["summary"]["groups"] == 1
    assert result["summary"]["blocker_reasons"]["unrelated_conflicts_with_group_links"] > 0


def test_rejected_pair_does_not_create_clean_negatives():
    report, inventory = meiwei()
    packet = build_packet(report, inventory)
    result = derive(
        packet,
        inventory,
        PACKET_HASH,
        ledger(
            packet,
            {
                "pair": {
                    "alignment": "confirmed",
                    "normal_clean": "rejected",
                    "annotation_completeness": "confirmed",
                }
            },
        ),
    )
    assert result["summary"]["blocker_reasons"]["pair_review_rejected"] == 3
    assert len(result["images"]) == 6
    assert not result["ready_for_training"]


@pytest.mark.parametrize("target", ["box", "member", "ledger"])
def test_rejects_changed_bound_inputs(target):
    packet, inventory = fixture()
    review = ledger(packet, {"box": {"correction": "accept"}})
    if target == "box":
        packet["review"]["border_corrections"][0]["after_xywh"] = [0, 0, 1, 1]
    elif target == "member":
        packet["members"][0]["sha256"] = "changed"
    else:
        review["states"][0]["status"] = "changed"
    with pytest.raises(ValueError):
        derive(packet, inventory, PACKET_HASH, review)


def test_recorded_source_reviews_still_do_not_approve_training():
    packet, inventory = fixture()
    review = ledger(
        packet,
        {
            "box": {"correction": "accept"},
            "near": {"relationship": "unrelated"},
            "class": {"definition": "retain_source"},
            "source": {"assessment": "reviewed"},
        },
    )
    result = derive(packet, inventory, PACKET_HASH, review)
    assert result["summary"]["case_blockers"] == 0
    assert result["release_requirements"]
    assert not result["ready_for_training"] and not result["production_eligible"]
    assert result["source_categories"] == packet["review"]["class_definitions"]


def test_unresolved_references_do_not_apply_changes():
    packet, inventory = fixture()
    review = ledger(packet, {"box": {"correction": "needs_reference"}})
    result = derive(packet, inventory, PACKET_HASH, review)
    assert result["summary"]["blocker_reasons"]["needs_reference"] == 1
    assert not result["applied_corrections"]


def test_invalid_group_partition_is_rejected():
    packet, inventory = fixture()
    packet["groups"].pop()
    with pytest.raises(ValueError, match="omit"):
        derive(packet, inventory, PACKET_HASH)
