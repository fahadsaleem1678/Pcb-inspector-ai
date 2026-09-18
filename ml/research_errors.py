"""Hash-bound diagnostics for saved unreviewed research validation predictions."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from ml.candidate_audit import digest
from ml.candidate_decisions import read_json
from ml.error_analysis import THRESHOLDS, match_image, overlap, rates
from ml.research_dsp import CLASSES, write_json


def explain_miss(truth, predictions, threshold):
    scored = [(i, p, overlap(truth["bbox"], p["bbox"])) for i, p in enumerate(predictions)]
    retained = [v for v in scored if v[1]["score"] >= threshold]
    same = [v for v in retained if v[1]["category_id"] == truth["category_id"]]
    wrong = [v for v in retained if v[1]["category_id"] != truth["category_id"]]
    low = [
        v
        for v in scored
        if v[1]["score"] < threshold and v[1]["category_id"] == truth["category_id"]
    ]

    def best(values):
        value = max(values, key=lambda v: (v[2], v[1]["score"], -v[0]), default=None)
        return (
            {"prediction_index": value[0], "iou": value[2], "prediction": value[1]}
            if value
            else {"prediction_index": None, "iou": 0, "prediction": None}
        )

    good, other, suppressed = best(same), best(wrong), best(low)
    if good["iou"] >= 0.5:
        reason = "matching_competition"
    elif other["iou"] >= 0.5:
        reason = "class_confusion"
    elif suppressed["iou"] >= 0.5:
        reason = "score_suppressed"
    elif good["iou"] >= 0.1:
        reason = "same_class_localization"
    elif other["iou"] >= 0.1:
        reason = "wrong_class_partial_overlap"
    else:
        reason = "no_useful_saved_detection"
    return {
        "reason": reason,
        "best_retained_same": good,
        "best_retained_other": other,
        "best_suppressed_same": suppressed,
    }


def size_bin(box):
    side = min(box[2:])
    return "<4px" if side < 4 else "4-8px" if side < 8 else "8-16px" if side < 16 else ">=16px"


def analyze(rows, predictions, threshold):
    by_image = defaultdict(list)
    for prediction in predictions:
        image_id = prediction["image_id"]
        if type(image_id) is not int or not 0 <= image_id < len(rows):
            raise ValueError("Prediction outside bound validation subset")
        by_image[image_id].append(prediction)
    totals = {name: Counter(tp=0, fp=0, fn=0) for name in CLASSES}
    missed_reasons = {name: Counter() for name in CLASSES}
    fp_reasons = {name: Counter() for name in CLASSES}
    sizes = {name: defaultdict(lambda: Counter(targets=0, matched=0)) for name in CLASSES}
    confusions = Counter()
    cases = []
    for index, row in enumerate(rows):
        truth, guessed = row["annotations"], by_image[index]
        matched = match_image(truth, guessed, threshold, len(CLASSES))
        for category, counts in matched["counts"].items():
            totals[CLASSES[category - 1]].update(counts)
        missed = set(matched["missed_indices"])
        for ai, annotation in enumerate(truth):
            name = CLASSES[annotation["category_id"] - 1]
            bucket = sizes[name][size_bin(annotation["bbox"])]
            bucket["targets"] += 1
            bucket["matched"] += ai not in missed
            if ai in missed:
                detail = explain_miss(annotation, guessed, threshold)
                missed_reasons[name][detail["reason"]] += 1
                if detail["reason"] == "class_confusion":
                    predicted = detail["best_retained_other"]["prediction"]["category_id"]
                    confusions[f"{name}->{CLASSES[predicted - 1]}"] += 1
                if name in {"MB", "SP"}:
                    cases.append(
                        {
                            "image": row["file"],
                            "asset": row["asset"],
                            "image_sha256": row["sha256"],
                            "annotation_index": ai,
                            "class": name,
                            "annotation": annotation,
                            **detail,
                        }
                    )
        for item in matched["prediction_matches"]:
            if item["outcome"] != "matched":
                name = CLASSES[guessed[item["prediction_index"]]["category_id"] - 1]
                fp_reasons[name][item["outcome"]] += 1
    per_class = {
        name: {
            **rates(totals[name]),
            "miss_reasons": dict(missed_reasons[name]),
            "false_positive_reasons": dict(fp_reasons[name]),
            "short_side_bins": dict(sizes[name]),
        }
        for name in CLASSES
    }
    aggregate = {key: sum(t[key] for t in totals.values()) for key in ("tp", "fp", "fn")}
    return {
        "score_threshold": threshold,
        "micro": rates(aggregate),
        "per_class": per_class,
        "missed_target_confusions": dict(confusions),
    }, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Diagnostic output already exists")
    evidence = read_json(args.evidence)
    manifest = read_json(args.manifest)
    if digest(args.manifest) != evidence["result"]["manifest_sha256"]:
        raise ValueError("Research manifest hash mismatch")
    if manifest["classes"] != CLASSES or manifest["schema_version"] != "unreviewed-research-1":
        raise ValueError("Unexpected research class/schema contract")
    rows = [r for r in manifest["samples"] if r["split"] == "validation"]
    phases, cases = {}, {}
    bindings = {
        "manifest_sha256": digest(args.manifest),
        "run_evidence_sha256": digest(args.evidence),
        "diagnostic_code_sha256": digest(__file__),
        "matcher_code_sha256": digest(Path(__file__).with_name("error_analysis.py")),
    }
    for phase in ("initial", "final"):
        path = args.run / f"{phase}-validation.json"
        if digest(path) != evidence[f"{phase}_validation_sha256"]:
            raise ValueError("Saved prediction hash mismatch")
        saved = read_json(path)
        if saved["source_images"] != [r["file"] for r in rows]:
            raise ValueError("Saved validation order mismatch")
        bindings[f"{phase}_predictions_sha256"] = digest(path)
        phases[phase], cases[phase] = [], {}
        for threshold in THRESHOLDS:
            summary, details = analyze(rows, saved["predictions"], threshold)
            phases[phase].append(summary)
            cases[phase][str(threshold)] = details
    output = {
        "schema_version": "1.0",
        "binding": bindings,
        "phases": phases,
        "matching": "Score-ordered one-to-one same-class IoU>=0.5; fixed diagnostic thresholds",
        "miss_reason_priority": [
            "matching_competition",
            "class_confusion",
            "score_suppressed",
            "same_class_localization",
            "wrong_class_partial_overlap",
            "no_useful_saved_detection",
        ],
        "limitations": [
            "Unreviewed source labels",
            "Heuristics are not causal diagnoses",
            "Saved detections are score-filtered and capped at 100 per image",
            "Miss explanations reuse predictions and are not a one-to-one confusion matrix",
            "No clean boards or independent camera qualification",
        ],
        "production_threshold_selected": False,
        "model_inference_performed": False,
        "training_performed": False,
        "production_eligible": False,
    }
    args.output.mkdir(parents=True)
    write_json(args.output / "cases.json", cases)
    output["cases_sha256"] = digest(args.output / "cases.json")
    write_json(args.output / "diagnostics.json", output)
    print(__import__("json").dumps({"output": str(args.output), "final": phases["final"]}))


if __name__ == "__main__":
    main()
