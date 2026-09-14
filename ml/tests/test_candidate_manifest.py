import copy
import json

import pytest

from ml.candidate_audit import digest, leakage, statistics
from ml.candidate_manifest import build_packet, load_audit


def row(name, split, pixel, annotated=True):
    return {
        "file": name,
        "member": "images/" + name,
        "split": split,
        "sha256": "bytes-" + name,
        "pixel_sha256": pixel,
        "dhash": 0,
        "width": 20,
        "height": 20,
        "annotations": [{"category_id": 1, "bbox": [1, 1, 2, 2]}] if annotated else [],
    }


def meiwei():
    defects = [
        row("a_Cur.jpg", "train", "a"),
        row("b_Cur.jpg", "validation", "b"),
        row("c_Cur.jpg", "test", "b"),
    ]
    normals = [
        row("a_Ref.jpg", "train", "n", False),
        row("b_Ref.jpg", "validation", "n", False),
        row("c_Ref.jpg", "test", "m", False),
    ]
    report = {
        "source": "MeiweiPCB",
        "statistics": statistics(defects, {1: "1"}),
        "normal_images": 3,
        "defect_leakage": leakage(defects),
        "normal_leakage": leakage(normals),
    }
    inventory = {
        "defects": defects,
        "normals": normals,
        "pairs": [
            {"defect": d["file"], "normal": n["file"], "source_split": d["split"]}
            for d, n in zip(defects, normals, strict=True)
        ],
    }
    return report, inventory


def dsp():
    rows = [row("a.jpg", "train", "a"), row("b.jpg", "validation", "b")]
    return {
        "source": "DsPCBSD+",
        "statistics": statistics(rows, {1: "SH"}),
        "leakage": leakage(rows),
    }, {"images": rows}


def test_transitive_pair_and_pixel_groups_keep_every_related_member():
    packet = build_packet(*meiwei())
    assert len(packet["groups"]) == 1
    group = packet["groups"][0]
    assert len(group["image_ids"]) == 6
    assert group["source_splits"] == ["test", "train", "validation"]
    assert group["crosses_source_splits"]
    assert group["proposed_split"] is None
    assert group["verified_physical_board_id"] is None
    assert not packet["ready_for_training"]
    assert not packet["production_eligible"]
    assert packet["review"]["reviewer"] is None
    assert all(c["normal_patch_verified_clean"] is None for c in packet["review"]["pair_cases"])


def test_packet_is_independent_of_inventory_order_and_preserves_sources():
    report, inventory = meiwei()
    before = copy.deepcopy(inventory)
    packet = build_packet(report, inventory)
    assert inventory == before
    for value in inventory.values():
        value.reverse()
    assert build_packet(report, inventory) == packet


def test_near_matches_are_review_only_and_not_merged():
    packet = build_packet(*dsp())
    assert len(packet["groups"]) == 2
    cases = packet["review"]["near_duplicate_cases"]
    assert len(cases) == 1
    assert cases[0]["related_capture_decision"] is None
    assert not cases[0]["already_linked_by_exact_or_pair_evidence"]
    assert packet["review"]["class_definitions"][0]["approved_project_class"] is None


def test_truncated_audit_still_produces_complete_review_queue():
    report, inventory = dsp()
    report["leakage"]["near_duplicate_candidates"] = []
    report["leakage"]["candidate_list_truncated"] = True
    assert build_packet(report, inventory)["summary"]["near_duplicate_review_cases"] == 1


@pytest.mark.parametrize("kind", ["missing", "repeated"])
def test_rejects_incomplete_or_reused_pairs(kind):
    report, inventory = meiwei()
    if kind == "missing":
        inventory["pairs"].pop()
    else:
        inventory["pairs"].append(inventory["pairs"][0])
    with pytest.raises(ValueError, match="Pairing"):
        build_packet(report, inventory)


def test_rejects_duplicate_inventory_identity():
    report, inventory = dsp()
    inventory["images"][1] = copy.deepcopy(inventory["images"][0])
    with pytest.raises(ValueError, match="Duplicate inventory"):
        build_packet(report, inventory)


def test_rejects_changed_near_match_count():
    report, inventory = dsp()
    report["leakage"]["near_duplicate_cross_split_pairs"] = 0
    with pytest.raises(ValueError, match="Near-duplicate count"):
        build_packet(report, inventory)


def test_box_proposals_require_matching_original_and_remain_unaccepted():
    report, inventory = dsp()
    proposal = {
        "file": "a.jpg",
        "split": "train",
        "annotation_index": 0,
        "category_id": 1,
        "before_xywh": [1, 1, 2, 2],
        "after_xywh": [1, 1, 1.99, 2],
    }
    report["border_normalization"] = {"proposals": [proposal]}
    packet = build_packet(report, inventory)
    assert packet["review"]["border_corrections"][0]["accept_correction"] is None
    assert inventory["images"][0]["annotations"][0]["bbox"] == [1, 1, 2, 2]
    proposal["before_xywh"] = [0, 0, 1, 1]
    with pytest.raises(ValueError, match="Correction proposal"):
        build_packet(report, inventory)


def test_hash_bound_inventory_rejects_tampering(tmp_path):
    report, inventory = dsp()
    inventory_path = tmp_path / "inventory.json"
    audit_path = tmp_path / "audit.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    report.update(schema_version="1.0", inventory_sha256=digest(inventory_path))
    audit_path.write_text(json.dumps(report), encoding="utf-8")
    assert load_audit(audit_path, inventory_path) == (report, inventory)
    inventory_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Inventory hash mismatch"):
        load_audit(audit_path, inventory_path)


def test_preserves_all_nine_source_classes():
    report, inventory = dsp()
    names = ["SH", "SP", "SC", "OP", "MB", "HB", "CS", "CFO", "BMFO"]
    report["statistics"]["classes"] = {str(i): {"name": name} for i, name in enumerate(names, 1)}
    classes = build_packet(report, inventory)["review"]["class_definitions"]
    assert [c["source_name"] for c in classes] == names
    assert all(c["retain_source_category"] for c in classes)
    assert all(c["approved_project_class"] is None for c in classes)
