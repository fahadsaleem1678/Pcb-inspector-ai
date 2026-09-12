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


@pytest.fixture
def step_run(run):
    from ml.schedule import STEP_SELECTION, training_schedule

    def read(name):
        return json.loads((run / f"{name}.json").read_text())

    config = read("config")
    config.update(
        {
            "epochs": None,
            "max_steps": 5,
            "training_views": 4,
            "seed": 17,
            "selection_policy": STEP_SELECTION,
        }
    )
    write(run / "config.json", config)
    metrics = read("best-validation")["metrics"]
    history = [
        {
            "pass": i + 1,
            "train_steps": len(indices),
            "train_view_indices": indices,
            "step_start": i * 4 + 1,
            "step_end": min((i + 1) * 4, 5),
            "pass_complete": len(indices) == 4,
            "elapsed_seconds": 1,
        }
        for i, indices in enumerate(training_schedule(4, 17, max_steps=5))
    ]
    history[-1]["validation"] = metrics
    write(run / "history.json", history)
    checkpoint = read("checkpoint")
    checkpoint.update(
        {
            "config_sha256": file_hash(run / "config.json"),
            "history_sha256": file_hash(run / "history.json"),
            "selected_epoch": None,
            "selected_step": 5,
            "selection_policy": STEP_SELECTION,
            "selection_metric": "optimizer_steps",
            "selection_value": 5,
        }
    )
    write(run / "checkpoint.json", checkpoint)
    summary = read("summary")
    summary.update(
        {
            "completed_steps": 5,
            "completed_epochs": 1,
            "partial_pass_steps": 1,
            "best_validation_ap50_95": metrics["ap50_95"],
        }
    )
    write(run / "summary.json", summary)
    return run


def test_step_evidence_reports_passes_without_inventing_complete_epoch(step_run):
    result = summarize(step_run)
    assert result["schema_version"] == "1.1"
    assert result["selected_epoch"] is None
    assert result["selected_step"] == result["total_train_steps"] == result["requested_steps"] == 5
    assert result["completed_epochs"] == 1
    assert result["partial_pass_steps"] == 1
    assert "epochs" not in result
    assert "validation" not in result["passes"][0]
    assert result["passes"][-1]["validation"]["ap50_95"] == 0.5


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("under", "completion"),
        ("over", "completion"),
        ("selection", "endpoint"),
        ("order", "ordering"),
        ("history_hash", "history checksum"),
        ("early_validation", "only at the endpoint"),
        ("endpoint_metrics", "Endpoint metrics"),
    ],
)
def test_step_evidence_and_evaluation_reject_invalid_contracts(
    step_run, monkeypatch, mutation, match
):
    from types import SimpleNamespace

    from ml import baseline

    name = {
        "under": "summary",
        "over": "summary",
        "selection": "checkpoint",
        "order": "history",
        "history_hash": "history",
        "early_validation": "history",
        "endpoint_metrics": "history",
    }[mutation]
    path = step_run / f"{name}.json"
    value = json.loads(path.read_text())
    if mutation in ("under", "over"):
        value["completed_steps"] = 4 if mutation == "under" else 6
    elif mutation == "selection":
        value["selected_step"] = 4
    elif mutation == "order":
        value[0]["train_view_indices"].reverse()
    elif mutation == "early_validation":
        value[0]["validation"] = {"ap50_95": 0.9}
    elif mutation == "endpoint_metrics":
        value[-1]["validation"]["ap50"] = 0.9
    else:
        value[0]["elapsed_seconds"] += 1
    write(path, value)
    if mutation == "endpoint_metrics":
        path = step_run / "checkpoint.json"
        checkpoint = json.loads(path.read_text())
        checkpoint["history_sha256"] = file_hash(step_run / "history.json")
        write(path, checkpoint)
    with pytest.raises(ValueError, match=match):
        summarize(step_run)

    if mutation != "endpoint_metrics":

        def forbidden(*args, **kwargs):
            raise AssertionError("Invalid training run reached model loading")

        monkeypatch.setattr(baseline, "make_model", forbidden)
        monkeypatch.setattr(baseline.torch, "load", forbidden)
        with pytest.raises(ValueError, match=match):
            baseline.evaluate(SimpleNamespace(run=step_run, split="validation", final_test=False))
