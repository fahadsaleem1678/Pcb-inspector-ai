"""Validation-only operating-point audit; never selects or promotes a production policy."""

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from ml.data import file_hash, verify_release
from ml.error_analysis import match_image, rates
from ml.summarize import summarize

DIAGNOSTIC_THRESHOLDS = (0.05, 0.25, 0.5, 0.75, 0.9, 0.95)


def zero_escape_sample_size(max_rate, confidence=0.95):
    """Planning bound only: independent Bernoulli trials with zero observed escapes."""
    if (
        not math.isfinite(max_rate)
        or not 0 < max_rate < 1
        or not math.isfinite(confidence)
        or not 0 < confidence < 1
    ):
        raise ValueError("Rates and confidence must be finite and strictly between zero and one")
    return math.ceil(math.log1p(-confidence) / math.log1p(-max_rate))


def prepare(samples, classes, predictions):
    if not samples or not classes or len(set(classes)) != len(classes):
        raise ValueError("Nonempty samples and unique classes required")
    if len({sample.image for sample in samples}) != len(samples):
        raise ValueError("Duplicate source image")
    if any(sample.split != "validation" for sample in samples):
        raise ValueError("Operating-point audit is validation only")
    by_image = [[] for _ in samples]
    for row in predictions:
        index = row["image_id"]
        if type(index) is not int or not 0 <= index < len(samples):
            raise ValueError("Prediction outside validation split")
        category = row["category_id"]
        if type(category) is not int or not 1 <= category <= len(classes):
            raise ValueError("Invalid class ID")
        x, y, width, height = row["bbox"]
        sample = samples[index]
        if x < 0 or y < 0 or x + width > sample.width + 1e-6 or y + height > sample.height + 1e-6:
            raise ValueError("Prediction outside source image")
        by_image[index].append(row)
    boards = []
    for index, sample in enumerate(samples):
        truth = [
            {
                "category_id": a.class_id + 1,
                "bbox": [a.bbox.x1, a.bbox.y1, a.bbox.x2 - a.bbox.x1, a.bbox.y2 - a.bbox.y1],
            }
            for a in sample.annotations
        ]
        matched = match_image(truth, by_image[index], 0, len(classes))
        boards.append(
            {
                "image": sample.image,
                "sha256": sample.sha256,
                "group": sample.group_id,
                "truth": truth,
                "predictions": by_image[index],
                "matches": matched["prediction_matches"],
            }
        )
    return boards


def point(boards, classes, threshold):
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Invalid score threshold")
    counts = {i: {"tp": 0, "fp": 0, "fn": 0} for i in range(1, len(classes) + 1)}
    board_rows = []
    for board in boards:
        retained = [
            m
            for m in board["matches"]
            if board["predictions"][m["prediction_index"]]["score"] >= threshold
        ]
        matched = {m["matched_annotation_index"] for m in retained if m["outcome"] == "matched"}
        for m in retained:
            category = board["predictions"][m["prediction_index"]]["category_id"]
            counts[category]["tp" if m["outcome"] == "matched" else "fp"] += 1
        for index, target in enumerate(board["truth"]):
            if index not in matched:
                counts[target["category_id"]]["fn"] += 1
        board_rows.append(
            {
                "image": board["image"],
                "group": board["group"],
                "has_labeled_defect": bool(board["truth"]),
                "flagged": bool(retained),
                "retained_detections": len(retained),
                "missed_labels": len(board["truth"]) - len(matched),
            }
        )

    def board_rates(rows):
        positive = sum(r["has_labeled_defect"] for r in rows)
        negative = len(rows) - positive
        escaped = sum(r["has_labeled_defect"] and not r["flagged"] for r in rows)
        false_flags = sum(not r["has_labeled_defect"] and r["flagged"] for r in rows)
        flagged = sum(r["flagged"] for r in rows)
        return {
            "boards": len(rows),
            "labeled_positive_boards": positive,
            "annotation_empty_boards": negative,
            "flagged_boards": flagged,
            "flagged_fraction_in_this_sample": flagged / len(rows) if rows else None,
            "positive_boards_without_flag": escaped,
            "observed_positive_board_escape_rate": escaped / positive if positive else None,
            "annotation_empty_boards_flagged": false_flags,
            "annotation_empty_board_flag_rate": false_flags / negative if negative else None,
        }

    aggregate = {key: sum(c[key] for c in counts.values()) for key in ("tp", "fp", "fn")}
    return {
        "score_threshold": threshold,
        "micro": rates(aggregate),
        "per_class": {classes[i - 1]: rates(c) for i, c in counts.items()},
        "board_routing": board_rates(board_rows),
        "by_group": {
            group: board_rates([r for r in board_rows if r["group"] == group])
            for group in sorted({r["group"] for r in board_rows})
        },
        "boards": board_rows,
    }


def frontier(boards):
    """Every distinct retained set from a GLOBAL threshold, processing equal scores together."""
    rows = []
    labels = sum(len(b["truth"]) for b in boards)
    positives = {i for i, b in enumerate(boards) if b["truth"]}
    for index, board in enumerate(boards):
        for m in board["matches"]:
            prediction = board["predictions"][m["prediction_index"]]
            rows.append((prediction["score"], index, m["outcome"] == "matched"))
    rows.sort(key=lambda r: -r[0])
    points = []
    flagged = set()
    tp = fp = index = 0
    thresholds = sorted({0.0, 1.0, *(r[0] for r in rows)}, reverse=True)
    for threshold in thresholds:
        while index < len(rows) and rows[index][0] >= threshold:
            _, board, matched = rows[index]
            flagged.add(board)
            tp += matched
            fp += not matched
            index += 1
        points.append(
            {
                "score_threshold": threshold,
                **rates({"tp": tp, "fp": fp, "fn": labels - tp}),
                "flagged_boards": len(flagged),
                "positive_boards_without_flag": len(positives - flagged),
            }
        )
    return points


def audit_run(run, manifest_path, root, release):
    evidence = summarize(run)
    manifest, digest = verify_release(manifest_path, root, release)
    if (
        digest != evidence["manifest_sha256"]
        or manifest.classes != evidence["configuration"]["classes"]
    ):
        raise ValueError("Qualification manifest or classes differ from checkpoint")
    saved = json.loads((run / "best-validation.json").read_text(encoding="utf-8"))
    samples = [s for s in manifest.samples if s.split == "validation"]
    if [s.image for s in samples] != saved["source_images"]:
        raise ValueError("Validation order differs from checkpoint")
    boards = prepare(samples, manifest.classes, saved["predictions"])
    points = frontier(boards)
    candidates = {}
    # These floors are diagnostic probes, not business acceptance requirements.
    for floor in (0.5, 0.8, 0.9, 0.95):
        eligible = [p for p in points if p["precision"] is not None and p["precision"] >= floor]
        candidates[str(floor)] = max(
            eligible, key=lambda p: (p["recall"] or 0, -p["fp"], p["score_threshold"]), default=None
        )
    zero_escape = [p for p in points if p["positive_boards_without_flag"] == 0]
    if not any(b["truth"] for b in boards):
        zero_escape = []
    result = {
        "schema_version": "1.0",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "source_run": run.name,
        "split": "validation",
        "review_workflow": "flagged_boards_only",
        "checkpoint_sha256": evidence["checkpoint_sha256"],
        "manifest_sha256": digest,
        "source_predictions_sha256": file_hash(run / "best-validation.json"),
        "code_sha256": {
            name: file_hash(Path("ml") / name)
            for name in (
                "qualification.py",
                "error_analysis.py",
                "summarize.py",
                "schedule.py",
                "data.py",
            )
        },
        "training_artifact_sha256": evidence["artifact_sha256"],
        "source_images": [
            {"image": s.image, "sha256": s.sha256, "group": s.group_id} for s in samples
        ],
        "validation_groups": len({s.group_id for s in samples}),
        "diagnostic_points": [point(boards, manifest.classes, t) for t in DIAGNOSTIC_THRESHOLDS],
        "global_threshold_frontier": {
            "evaluated_thresholds": len(points),
            "maximum_recall_at_precision_floor": candidates,
            "highest_threshold_with_zero_observed_positive_board_escapes": max(
                zero_escape, key=lambda p: p["score_threshold"], default=None
            ),
        },
        "production_threshold": None,
        "promotion_eligible": False,
        "test_evaluated": False,
        "test_evaluation_artifact_exists": evidence["test_evaluation_artifact_exists"],
        "readiness": "BLOCKED",
        "blockers": [
            "Production escape-rate and clean-board false-flag limits need owner approval.",
            "Expert whole-image annotation-completeness review is not recorded.",
            "Independent clean-board and camera-domain evidence is missing.",
            "Validation threshold exploration is development evidence, not final acceptance.",
            "Final held-out evaluation and approved surface-detector integration remain pending.",
        ],
        "limitations": [
            "A board is flagged by any retained prediction, even a wrong-class or misplaced box.",
            "Zero board escapes can coexist with missed defects; review the entire flagged board.",
            "Annotation-empty boards are not certified clean without independent review.",
            "Flagged fraction on a defect-enriched sample is not production review workload.",
            "Stored predictions already include model filtering, NMS and the max100 limit.",
            "Precision floors are diagnostic probes, not approved targets or probabilities.",
            "This small correlated sample cannot establish a production escape-rate bound.",
        ],
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/pcb-defect-v1.0.json")
    )
    parser.add_argument("--root", type=Path, default=Path("data/processed/pcb-defect-v1"))
    parser.add_argument("--release", type=Path, default=Path("data/releases/pcb-defect-v1"))
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Qualification output already exists")
    result = audit_run(args.run, args.manifest, args.root, args.release)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "run": args.run.name,
                "readiness": result["readiness"],
                "frontier": result["global_threshold_frontier"],
            }
        )
    )


if __name__ == "__main__":
    main()
