"""Validation-only error counts at fixed diagnostic score thresholds."""

import argparse
import json
import math
from pathlib import Path

from ml.data import file_hash, verify_release
from ml.summarize import summarize

THRESHOLDS = (0.05, 0.25, 0.5)


def overlap(a, b):
    # COCO pixel xywh coordinates.
    intersection = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(
        0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    )
    union = a[2] * a[3] + b[2] * b[3] - intersection
    return intersection / union if union > 0 else 0.0


def best_overlap(indices, overlaps):
    index = max(indices, key=overlaps.__getitem__, default=None)
    iou = overlaps[index] if index is not None else 0.0
    return {"annotation_index": index if iou > 0 else None, "iou": iou}


def match_image(truth, predictions, threshold, classes):
    """Score-ordered, one-to-one, same-class IoU >= .5 diagnostic matching."""
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Threshold must be finite and between zero and one")
    for row in [*truth, *predictions]:
        box = row["bbox"]
        if len(box) != 4 or not all(math.isfinite(x) for x in box) or min(box[2:]) <= 0:
            raise ValueError("Invalid diagnostic bounding box")
        if row["category_id"] not in range(1, classes + 1):
            raise ValueError("Unknown diagnostic category")
    for row in predictions:
        if not math.isfinite(row["score"]) or not 0 <= row["score"] <= 1:
            raise ValueError("Invalid diagnostic score")
    retained = sorted(
        ((i, p) for i, p in enumerate(predictions) if p["score"] >= threshold),
        key=lambda item: -item[1]["score"],
    )
    matched = set()
    counts = {i: {"tp": 0, "fp": 0, "fn": 0} for i in range(1, classes + 1)}
    prediction_matches = []
    contexts = {k: 0 for k in ["duplicate", "class_confusion", "partial_overlap", "no_overlap"]}
    for prediction_index, prediction in retained:
        overlaps = [overlap(prediction["bbox"], t["bbox"]) for t in truth]
        same = [i for i, t in enumerate(truth) if t["category_id"] == prediction["category_id"]]

        best_same = best_overlap(same, overlaps)
        best_any = best_overlap(range(len(truth)), overlaps)
        best_available = best_overlap((i for i in same if i not in matched), overlaps)
        category = prediction["category_id"]
        matched_index = None
        if best_available["iou"] >= 0.5:
            matched_index = best_available["annotation_index"]
            matched.add(matched_index)
            counts[category]["tp"] += 1
            outcome = "matched"
        else:
            counts[category]["fp"] += 1
            if best_same["iou"] >= 0.5:
                outcome = "duplicate"
            elif best_any["iou"] >= 0.5:
                outcome = "class_confusion"
            elif best_any["iou"] > 0:
                outcome = "partial_overlap"
            else:
                outcome = "no_overlap"
            contexts[outcome] += 1
        prediction_matches.append(
            {
                "prediction_index": prediction_index,
                "matched_annotation_index": matched_index,
                "outcome": outcome,
                "best_same_class": best_same,
                "best_any_class": best_any,
            }
        )
    missed = [i for i in range(len(truth)) if i not in matched]
    for i in missed:
        counts[truth[i]["category_id"]]["fn"] += 1
    # Non-exclusive coverage diagnostic: a prediction may overlap multiple targets.
    localized = sum(any(overlap(t["bbox"], p["bbox"]) >= 0.5 for _, p in retained) for t in truth)
    return {
        "counts": counts,
        "missed_indices": missed,
        "class_agnostic_target_coverage": localized,
        "retained_predictions": len(retained),
        "prediction_matches": prediction_matches,
        "false_positive_context": contexts,
    }


def rates(counts):
    tp, fp, fn = (counts[k] for k in ("tp", "fp", "fn"))
    return {
        **counts,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def analyze(args):
    if args.output.exists():
        raise ValueError("Diagnostic output already exists")
    evidence = summarize(args.run)
    manifest, digest = verify_release(args.manifest, args.root, args.release)
    if (
        digest != evidence["manifest_sha256"]
        or manifest.classes != evidence["configuration"]["classes"]
    ):
        raise ValueError("Diagnostic data differs from checkpoint")
    samples = [s for s in manifest.samples if s.split == "validation"]
    saved = json.loads((args.run / "best-validation.json").read_text(encoding="utf-8"))
    if [s.image for s in samples] != saved["source_images"]:
        raise ValueError("Diagnostic validation ordering differs")
    by_image = {i: [] for i in range(len(samples))}
    for prediction in saved["predictions"]:
        if prediction["image_id"] not in by_image:
            raise ValueError("Prediction lies outside validation split")
        by_image[prediction["image_id"]].append(prediction)
    profiles = []
    for threshold in THRESHOLDS:
        totals = {i: {"tp": 0, "fp": 0, "fn": 0} for i in range(1, len(manifest.classes) + 1)}
        boards = []
        for i, sample in enumerate(samples):
            truth = [
                {
                    "category_id": a.class_id + 1,
                    "bbox": [a.bbox.x1, a.bbox.y1, a.bbox.x2 - a.bbox.x1, a.bbox.y2 - a.bbox.y1],
                }
                for a in sample.annotations
            ]
            result = match_image(truth, by_image[i], threshold, len(manifest.classes))
            for category, counts in result["counts"].items():
                for key, value in counts.items():
                    totals[category][key] += value
            count = {
                k: sum(row[k] for row in result["counts"].values()) for k in ("tp", "fp", "fn")
            }
            boards.append(
                {
                    "image": sample.image,
                    "group": sample.group_id,
                    "false_positive_context": result["false_positive_context"],
                    **rates(count),
                    "missed_annotations": [truth[j] for j in result["missed_indices"]],
                    "class_agnostic_target_coverage": result["class_agnostic_target_coverage"],
                }
            )
        aggregate = {k: sum(row[k] for row in totals.values()) for k in ("tp", "fp", "fn")}
        profiles.append(
            {
                "score_threshold": threshold,
                "micro": rates(aggregate),
                "false_positive_context": {
                    k: sum(b["false_positive_context"][k] for b in boards)
                    for k in boards[0]["false_positive_context"]
                },
                "per_class": {manifest.classes[i - 1]: rates(row) for i, row in totals.items()},
                "boards": boards,
            }
        )
    output = {
        "schema_version": "1.0",
        "split": "validation",
        "iou_threshold": 0.5,
        "matching": "descending score, same class, one-to-one; ties use stable input order",
        "source_run": args.run.name,
        "checkpoint_sha256": evidence["checkpoint_sha256"],
        "manifest_sha256": digest,
        "source_predictions_sha256": file_hash(args.run / "best-validation.json"),
        "analysis_code_sha256": file_hash(__file__),
        "profiles": profiles,
        "promotion_eligible": False,
        "test_evaluated": False,
        "limitations": [
            "Fixed diagnostic thresholds, not calibrated product settings.",
            "FP context priority: duplicate, other-class IoU >= .5, partial overlap, no overlap.",
            "Overlap context describes geometry relative to labels, not proven error causes.",
            "False positives are relative to source annotations, whose completeness is unverified.",
            "Micro precision/recall at IoU .5 are not COCO AP or AR100.",
            "Class-agnostic coverage can reuse predictions; not precision or matched recall.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(output, indent=2, allow_nan=False) + "\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/pcb-defect-v1.0.json")
    )
    parser.add_argument("--root", type=Path, default=Path("data/processed/pcb-defect-v1"))
    parser.add_argument("--release", type=Path, default=Path("data/releases/pcb-defect-v1"))
    result = analyze(parser.parse_args())
    print(
        json.dumps([{"threshold": p["score_threshold"], **p["micro"]} for p in result["profiles"]])
    )


if __name__ == "__main__":
    main()
