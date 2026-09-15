"""Derive unapproved candidate data from bound, uncontested reviewer observations."""

import argparse
import json
import math
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

from ml.candidate_audit import digest, normalize_border_rounding
from ml.candidate_decisions import (
    case_catalog,
    content_hash,
    load_packet,
    read_json,
    review_state,
    validate_ledger,
)
from ml.candidate_manifest import stable_id


def derive(packet, inventory, packet_hash, ledger=None):
    catalog = case_catalog(packet)
    states = (
        validate_ledger(ledger, catalog, packet_hash)
        if ledger is not None
        else review_state([], catalog, packet_hash)
    )
    state_by_id = {s["case_id"]: s for s in states}
    collections = (
        {"defect": inventory["defects"], "normal": inventory["normals"]}
        if packet["source"] == "MeiweiPCB"
        else {"defect": inventory["images"]}
    )
    source_rows = {}
    for condition, rows in collections.items():
        for row in rows:
            identity = stable_id("image", [packet["source"], condition, row["split"], row["file"]])
            if identity in source_rows:
                raise ValueError("Duplicate source image identity")
            source_rows[identity] = row
    members = {m["image_id"]: m for m in packet["members"]}
    if len(members) != len(packet["members"]) or set(members) != set(source_rows):
        raise ValueError("Packet and inventory membership differ")
    images = {}
    for identity, member in members.items():
        row = source_rows[identity]
        for key in ("sha256", "pixel_sha256", "width", "height", "member", "file"):
            if member[key] != row[key]:
                raise ValueError("Packet image differs from inventory")
        images[identity] = {
            **deepcopy(member),
            "annotations": deepcopy(row["annotations"]),
            "source_annotations_sha256": content_hash(row["annotations"]),
        }
    parent = {identity: identity for identity in members}

    def find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def join(first, second):
        if first not in parent or second not in parent:
            raise ValueError("Group link references unknown image")
        a, b = sorted((find(first), find(second)))
        parent[b] = a

    covered = set()
    for group in packet["groups"]:
        ids = group["image_ids"]
        if (
            not ids
            or any(i not in members or i in covered for i in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("Invalid original group membership")
        covered.update(ids)
        for identity in ids[1:]:
            join(ids[0], identity)
    if covered != set(members):
        raise ValueError("Original groups omit images")
    blockers = []
    changes, new_links = [], []
    unrelated = []
    corrected = set()
    for identity, case in sorted(catalog.items()):
        state = state_by_id[identity]
        subject = case["subject"]
        answers = state["current_reviews"][0]["answers"] if state["status"] == "recorded" else None
        if answers is None:
            blockers.append({"case_id": identity, "reason": state["status"]})
        if case["kind"] == "near" and answers:
            if answers["relationship"] == "related":
                join(subject["first"], subject["second"])
                new_links.append(
                    {
                        "case_id": identity,
                        "first": subject["first"],
                        "second": subject["second"],
                        "reason": "reviewed_related_capture",
                    }
                )
            elif answers["relationship"] == "unrelated":
                unrelated.append((identity, subject))
        elif case["kind"] == "pair" and answers:
            if any(value != "confirmed" for value in answers.values()):
                blockers.append({"case_id": identity, "reason": "pair_review_rejected"})
        elif case["kind"] == "box":
            image = images[subject["image_id"]]
            index = subject["annotation_index"]
            key = (subject["image_id"], index)
            if (
                type(index) is not int
                or index < 0
                or index >= len(image["annotations"])
                or key in corrected
            ):
                raise ValueError("Invalid or duplicate correction target")
            corrected.add(key)
            original = source_rows[subject["image_id"]]["annotations"][index]
            if (
                original["bbox"] != subject["before_xywh"]
                or original["category_id"] != subject["category_id"]
            ):
                raise ValueError("Correction source annotation mismatch")
            expected = normalize_border_rounding(original["bbox"], image["width"], image["height"])
            if expected != subject["after_xywh"]:
                raise ValueError("Correction differs from bounded normalization")
            if answers and answers["correction"] == "accept":
                image["annotations"][index]["bbox"] = deepcopy(expected)
                changes.append(
                    {
                        "case_id": identity,
                        "image_id": subject["image_id"],
                        "annotation_index": index,
                        "category_id": original["category_id"],
                        "before_xywh": deepcopy(original["bbox"]),
                        "after_xywh": expected,
                    }
                )
            elif answers:
                blockers.append({"case_id": identity, "reason": "border_correction_rejected"})
    for identity, subject in unrelated:
        if find(subject["first"]) == find(subject["second"]):
            blockers.append({"case_id": identity, "reason": "unrelated_conflicts_with_group_links"})
    grouped = defaultdict(list)
    for identity in sorted(images):
        grouped[find(identity)].append(identity)
    groups = []
    for ids in grouped.values():
        splits = sorted({members[i]["source_split"] for i in ids})
        groups.append(
            {
                "group_id": stable_id("group", ids),
                "image_ids": ids,
                "source_splits": splits,
                "crosses_source_splits": len(splits) > 1,
                "proposed_split": None,
                "verified_physical_board_id": None,
            }
        )
    invalid = []
    for identity, image in images.items():
        for index, annotation in enumerate(image["annotations"]):
            box = annotation["bbox"]
            if (
                len(box) != 4
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
                or min(box[:2]) < 0
                or min(box[2:]) <= 0
                or box[0] + box[2] > image["width"] + 1e-6
                or box[1] + box[3] > image["height"] + 1e-6
            ):
                invalid.append({"image_id": identity, "annotation_index": index})
    return {
        "schema_version": "1.0",
        "source": packet["source"],
        "status": "derived_unapproved_candidate",
        "ready_for_training": False,
        "production_eligible": False,
        "test_inference_performed": False,
        "source_files_modified": False,
        "groups_are_verified_physical_boards": False,
        "source_categories": deepcopy(packet["review"]["class_definitions"]),
        "images": sorted(images.values(), key=lambda x: x["image_id"]),
        "groups": sorted(groups, key=lambda x: x["group_id"]),
        "applied_corrections": changes,
        "reviewed_group_links": new_links,
        "case_blockers": blockers,
        "remaining_invalid_boxes": invalid,
        "release_requirements": [
            "independent_split_approval",
            "source_group_independence",
            "expert_completeness_review",
            "explicit_training_release",
        ],
        "summary": {
            "images": len(images),
            "annotations": sum(len(i["annotations"]) for i in images.values()),
            "groups": len(groups),
            "cross_source_split_groups": sum(g["crosses_source_splits"] for g in groups),
            "applied_corrections": len(changes),
            "reviewed_group_links": len(new_links),
            "case_blockers": len(blockers),
            "blocker_reasons": dict(Counter(b["reason"] for b in blockers)),
            "remaining_invalid_boxes": len(invalid),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output already exists; choose a new candidate directory")
    packet, _, packet_hash = load_packet(args.packet, args.summary)
    if digest(args.inventory) != packet["binding"]["inventory_sha256"]:
        raise ValueError("Inventory hash mismatch")
    result = derive(
        packet,
        read_json(args.inventory),
        packet_hash,
        read_json(args.ledger) if args.ledger else None,
    )
    result["binding"] = {
        "packet_sha256": packet_hash,
        "inventory_sha256": digest(args.inventory),
        "ledger_sha256": digest(args.ledger) if args.ledger else None,
        "derivation_code_sha256": digest(__file__),
        "decision_code_sha256": digest(Path(__file__).with_name("candidate_decisions.py")),
    }
    args.output.mkdir(parents=True)
    target = args.output / "derived-candidate.json"
    target.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    summary = {
        k: result[k]
        for k in (
            "schema_version",
            "source",
            "status",
            "ready_for_training",
            "production_eligible",
            "binding",
            "summary",
        )
    }
    summary.update(candidate_sha256=digest(target), local_candidate_path=target.as_posix())
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
