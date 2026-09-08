"""Export compact, checksum-bound evidence after full validation checkpoint reload."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from ml.data import file_hash


def summarize(run):
    run = Path(run)
    names = [
        "config",
        "checkpoint",
        "summary",
        "history",
        "best-validation",
        "validation-evaluation",
    ]
    artifacts = {name: run / f"{name}.json" for name in names}
    data = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in artifacts.items()}
    config, checkpoint, summary = (data[name] for name in names[:3])
    best, evaluation = data["best-validation"], data["validation-evaluation"]
    if (run / "failure.json").exists() or summary["status"] != "complete":
        raise ValueError("Cannot summarize a failed or incomplete run")
    if summary["completed_epochs"] != config["epochs"]:
        raise ValueError("Configured epochs did not complete")
    if config["smoke"] or evaluation["split"] != "validation":
        raise ValueError("Evidence requires a full run and validation reload")
    if checkpoint["config_sha256"] != file_hash(artifacts["config"]):
        raise ValueError("Configuration checksum mismatch")
    digest = file_hash(run / "best-state.pt")
    if any(
        digest != expected
        for expected in [
            checkpoint["state_sha256"],
            summary["checkpoint_sha256"],
            evaluation["checkpoint_sha256"],
        ]
    ):
        raise ValueError("Checkpoint checksum mismatch")
    if (
        any(
            config["manifest_sha256"] != value
            for value in [checkpoint["manifest_sha256"], evaluation["manifest_sha256"]]
        )
        or config["classes"] != checkpoint["classes"]
    ):
        raise ValueError("Dataset or class contract differs")
    if (
        best["source_images"] != evaluation["source_images"]
        or best["source_images"] != config["validation_source_images"]
    ):
        raise ValueError("Validation source ordering differs")
    if best["predictions"] != evaluation["predictions"]:
        raise ValueError("Checkpoint reload predictions differ")
    for key in ["ap50_95", "ap50", "ar100", "per_class", "by_group"]:
        if best["metrics"][key] != evaluation["metrics"][key]:
            raise ValueError(f"Checkpoint reload metrics differ: {key}")
    history = data["history"]
    if [row["epoch"] for row in history] != list(range(1, config["epochs"] + 1)):
        raise ValueError("Epoch history is incomplete")
    selected = max(history, key=lambda row: row["validation"]["ap50_95"])
    if (
        selected["epoch"] != checkpoint["selected_epoch"]
        or selected["validation"]["ap50_95"] != best["metrics"]["ap50_95"]
    ):
        raise ValueError("Best checkpoint differs from validation selection history")
    return {
        "schema_version": "1.0",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "experiment": run.name,
        "training_git_revision": config["git_revision"],
        "training_git_dirty": config["git_dirty"],
        "manifest_sha256": config["manifest_sha256"],
        "checkpoint_sha256": digest,
        "configuration": {
            key: value
            for key, value in config.items()
            if key
            not in [
                "training_source_images",
                "validation_source_images",
                "root",
                "manifest",
                "release",
            ]
        },
        "train_images": len(config["training_source_images"]),
        "validation_images": len(config["validation_source_images"]),
        "total_train_steps": sum(row["train_steps"] for row in history),
        "elapsed_seconds": sum(row["elapsed_seconds"] for row in history),
        "epochs": [
            {key: value for key, value in row.items() if key != "train_view_indices"}
            for row in history
        ],
        "selected_epoch": checkpoint["selected_epoch"],
        "validation": best["metrics"],
        "validation_prediction_count": len(best["predictions"]),
        "reload_predictions_and_metrics_equal": True,
        "mlflow_run_id": summary["mlflow_run_id"],
        "test_evaluation_artifact_exists": (run / "test-evaluation.json").exists(),
        "promotion_eligible": False,
        "artifact_sha256": {path.name: file_hash(path) for path in artifacts.values()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = summarize(args.run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    print(f"Verified evidence saved: {args.output}")


if __name__ == "__main__":
    main()
