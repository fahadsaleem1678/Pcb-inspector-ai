"""Build hash-bound grouping and review packets; never assign new training splits."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from ml.candidate_audit import digest, leakage


def stable_id(kind, value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return kind + "-" + hashlib.sha256(payload.encode()).hexdigest()


def load_audit(audit_path, inventory_path):
    report = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    if report.get("schema_version") != "1.0":
        raise ValueError("Unsupported audit schema")
    if report.get("inventory_sha256") != digest(inventory_path):
        raise ValueError("Inventory hash mismatch")
    inventory = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    return report, inventory


def build_packet(report, inventory):
    source = report["source"]
    if source == "MeiweiPCB":
        collections = {"defect": inventory["defects"], "normal": inventory["normals"]}
        primary = collections["defect"]
    elif source == "DsPCBSD+":
        collections = {"defect": inventory["images"]}
        primary = collections["defect"]
    else:
        raise ValueError("Unsupported candidate source")
    if len(primary) != report["statistics"]["images"]:
        raise ValueError("Image count differs from audited source")
    if sum(len(r["annotations"]) for r in primary) != report["statistics"]["annotations"]:
        raise ValueError("Annotation count differs from audited source")
    members, lookup, parent = {}, {}, {}
    for condition, rows in collections.items():
        for row in rows:
            key = (condition, row["split"], row["file"])
            if key in lookup:
                raise ValueError("Duplicate inventory identity")
            identity = stable_id("image", [source, *key])
            lookup[key] = identity
            parent[identity] = identity
            members[identity] = {
                "image_id": identity,
                "condition": condition,
                **{
                    k: row[k]
                    for k in ("file", "member", "sha256", "pixel_sha256", "width", "height")
                },
                "source_split": row["split"],
            }

    def find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def join(first, second):
        a, b = sorted((find(first), find(second)))
        parent[b] = a

    links = []
    pair_reviews = []
    paired = set()
    if source == "MeiweiPCB":
        if len(collections["normal"]) != report["normal_images"]:
            raise ValueError("Normal count differs from audit")
        for pair in inventory["pairs"]:
            first = lookup[("defect", pair["source_split"], pair["defect"])]
            second = lookup[("normal", pair["source_split"], pair["normal"])]
            if first in paired or second in paired:
                raise ValueError("Pairing is not one-to-one")
            paired.update((first, second))
            join(first, second)
            links.append({"first": first, "second": second, "reason": "source_filename_pair"})
            pair_reviews.append(
                {
                    "case_id": stable_id("pair", [first, second]),
                    "defect_image_id": first,
                    "normal_image_id": second,
                    "pair_alignment_verified": None,
                    "normal_patch_verified_clean": None,
                    "defect_annotations_complete": None,
                    "source_group_evidence": None,
                }
            )
        if paired != set(members):
            raise ValueError("Pairing does not cover every image")
    pixels = defaultdict(list)
    for identity, member in members.items():
        pixels[member["pixel_sha256"]].append(identity)
    for identities in pixels.values():
        identities.sort()
        for second in identities[1:]:
            join(identities[0], second)
            links.append(
                {"first": identities[0], "second": second, "reason": "identical_decoded_pixels"}
            )
    grouped = defaultdict(list)
    for identity in sorted(members):
        grouped[find(identity)].append(identity)
    groups = []
    for identities in grouped.values():
        splits = sorted({members[i]["source_split"] for i in identities})
        groups.append(
            {
                "group_id": stable_id("group", identities),
                "image_ids": identities,
                "source_splits": splits,
                "crosses_source_splits": len(splits) > 1,
                "proposed_split": None,
                "verified_physical_board_id": None,
            }
        )
    near_reviews = []
    for condition, rows in collections.items():
        # Audits intentionally truncate display lists; reconstruct every candidate for review.
        scan = leakage(rows, limit=len(rows) * (len(rows) - 1) // 2)
        expected = report["leakage"] if source == "DsPCBSD+" else report[condition + "_leakage"]
        if scan["near_duplicate_cross_split_pairs"] != expected["near_duplicate_cross_split_pairs"]:
            raise ValueError("Near-duplicate count differs from audit")
        for candidate in scan["near_duplicate_candidates"]:
            first = lookup[(condition, candidate["first_split"], candidate["first"])]
            second = lookup[(condition, candidate["second_split"], candidate["second"])]
            first, second = sorted((first, second))
            near_reviews.append(
                {
                    "case_id": stable_id("near", [first, second]),
                    "first": first,
                    "second": second,
                    "dhash_distance": candidate["dhash_distance"],
                    "already_linked_by_exact_or_pair_evidence": find(first) == find(second),
                    "related_capture_decision": None,
                    "reference_evidence": None,
                }
            )
    classes = [
        {
            "source_category_id": int(key),
            "source_name": value["name"],
            "retain_source_category": True,
            "approved_project_class": None,
            "definition_review": None,
        }
        for key, value in sorted(report["statistics"]["classes"].items())
    ]
    corrections = []
    for proposal in report.get("border_normalization", {}).get("proposals", []):
        identity = lookup[("defect", proposal["split"], proposal["file"])]
        row = next(
            r for r in primary if r["file"] == proposal["file"] and r["split"] == proposal["split"]
        )
        original = row["annotations"][proposal["annotation_index"]]
        if (
            original["bbox"] != proposal["before_xywh"]
            or original["category_id"] != proposal["category_id"]
        ):
            raise ValueError("Correction proposal differs from inventory annotation")
        corrections.append(
            {
                "case_id": stable_id("box", [identity, proposal["annotation_index"]]),
                "image_id": identity,
                **proposal,
                "accept_correction": None,
                "rationale": None,
            }
        )
    return {
        "schema_version": "1.0",
        "source": source,
        "status": "unreviewed_candidate",
        "ready_for_training": False,
        "production_eligible": False,
        "test_inference_performed": False,
        "groups_are_verified_physical_boards": False,
        "members": sorted(members.values(), key=lambda m: m["image_id"]),
        "groups": sorted(groups, key=lambda g: g["group_id"]),
        "grouping_links": sorted(links, key=lambda x: (x["first"], x["second"], x["reason"])),
        "review": {
            "reviewer": None,
            "reviewed_at": None,
            "rights_and_provenance": None,
            "source_grouping_and_split_review": None,
            "pair_cases": sorted(pair_reviews, key=lambda x: x["case_id"]),
            "near_duplicate_cases": sorted(near_reviews, key=lambda x: x["case_id"]),
            "class_definitions": classes,
            "border_corrections": sorted(corrections, key=lambda x: x["case_id"]),
        },
        "summary": {
            "images": len(members),
            "groups": len(groups),
            "cross_source_split_groups": sum(g["crosses_source_splits"] for g in groups),
            "link_reasons": dict(Counter(link["reason"] for link in links)),
            "pair_review_cases": len(pair_reviews),
            "near_duplicate_review_cases": len(near_reviews),
            "border_correction_review_cases": len(corrections),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output already exists; choose a new packet directory")
    report, inventory = load_audit(args.audit, args.inventory)
    packet = build_packet(report, inventory)
    packet["binding"] = {
        "audit_sha256": digest(args.audit),
        "inventory_sha256": digest(args.inventory),
        "generator_sha256": digest(__file__),
    }
    args.output.mkdir(parents=True)
    target = args.output / "candidate-review.json"
    target.write_text(
        json.dumps(packet, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    summary = {
        k: packet[k]
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
    summary["packet_sha256"] = digest(target)
    summary["local_packet_path"] = target.as_posix()
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
