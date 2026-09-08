import json

import pytest

from ml.data import file_hash
from ml.summarize import summarize


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def run(tmp_path):
    config = {
        "epochs": 3,
        "smoke": False,
        "manifest_sha256": "manifest",
        "classes": ["spur"],
        "training_source_images": ["train.jpg"],
        "validation_source_images": ["val.jpg"],
        "git_revision": "revision",
        "git_dirty": False,
    }
    write(tmp_path / "config.json", config)
    (tmp_path / "best-state.pt").write_bytes(b"opaque checkpoint; exporter never loads it")
    digest = file_hash(tmp_path / "best-state.pt")
    write(
        tmp_path / "checkpoint.json",
        {
            "config_sha256": file_hash(tmp_path / "config.json"),
            "state_sha256": digest,
            "manifest_sha256": "manifest",
            "classes": ["spur"],
            "selected_epoch": 2,
        },
    )
    write(
        tmp_path / "summary.json",
        {
            "status": "complete",
            "completed_epochs": 3,
            "checkpoint_sha256": digest,
            "mlflow_run_id": "run",
        },
    )
    metrics = {"ap50_95": 0.5, "ap50": 0.6, "ar100": 0.7, "per_class": {}, "by_group": {}}
    predictions = [{"image_id": 0, "score": 0.8}]
    result = {"source_images": ["val.jpg"], "predictions": predictions, "metrics": metrics}
    write(tmp_path / "best-validation.json", result)
    write(
        tmp_path / "validation-evaluation.json",
        {
            **result,
            "split": "validation",
            "checkpoint_sha256": digest,
            "manifest_sha256": "manifest",
        },
    )
    write(
        tmp_path / "history.json",
        [
            {
                "epoch": i,
                "train_steps": 1,
                "elapsed_seconds": 1,
                "validation": {**metrics, "ap50_95": ap},
                "train_view_indices": [0],
            }
            for i, ap in enumerate([0.1, 0.5, 0.5], 1)
        ],
    )
    return tmp_path


def test_export_preserves_best_epoch_and_reproducibility_evidence(run):
    result = summarize(run)
    assert result["selected_epoch"] == 2  # first epoch wins ties
    assert result["total_train_steps"] == 3
    assert result["reload_predictions_and_metrics_equal"]
    assert not result["promotion_eligible"]
    assert not result["test_evaluation_artifact_exists"]
    assert "train_view_indices" not in result["epochs"][0]
    assert "best-validation.json" in result["artifact_sha256"]


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("failure", "failed"),
        ("state", "Checkpoint checksum"),
        ("config", "Configuration checksum"),
        ("predictions", "predictions differ"),
        ("selection", "selection history"),
        ("ordering", "source ordering"),
    ],
)
def test_export_rejects_misleading_or_changed_evidence(run, mutation, match):
    if mutation == "failure":
        write(run / "failure.json", {"status": "failed"})
    elif mutation == "state":
        (run / "best-state.pt").write_bytes(b"changed")
    else:
        name = {
            "config": "config",
            "predictions": "validation-evaluation",
            "selection": "checkpoint",
            "ordering": "validation-evaluation",
        }[mutation]
        path = run / f"{name}.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "config":
            value["git_revision"] = "changed"
        elif mutation == "predictions":
            value["predictions"] = []
        elif mutation == "selection":
            value["selected_epoch"] = 3
        else:
            value["source_images"] = ["other.jpg"]
        write(path, value)
    with pytest.raises(ValueError, match=match):
        summarize(run)
