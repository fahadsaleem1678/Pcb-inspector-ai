import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")

from ml import baseline  # noqa: E402
from ml.schedule import validate_training  # noqa: E402


@pytest.mark.parametrize(
    "options",
    [
        ["--max-steps", "0"],
        ["--max-steps", "-1"],
        ["--max-steps", "1.5"],
        ["--max-steps", "5", "--epochs", "2"],
    ],
)
def test_cli_rejects_invalid_or_ambiguous_budget(options):
    with pytest.raises(SystemExit):
        baseline.parse_args(["train", "--output", "unused", *options])


def test_cli_preserves_default_epochs_and_explicit_budget():
    assert baseline.parse_args(["train", "--output", "unused"]).epochs == 10
    args = baseline.parse_args(["train", "--output", "unused", "--max-steps", "1053"])
    assert args.epochs is None
    assert args.max_steps == 1053


@pytest.fixture
def tiny_training(monkeypatch, tmp_path):
    calls = {"updates": 0, "validation": [], "logged": []}

    class TinyModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor(1.0))
            self.rpn = SimpleNamespace(score_thresh=0.05)

        def forward(self, images, targets):
            return {"loss": self.weight.square()}

    model = TinyModel()
    real_sgd = torch.optim.SGD

    class CountingSGD(real_sgd):
        def step(self, *args, **kwargs):
            result = super().step(*args, **kwargs)
            calls["updates"] += 1
            return result

    class Views:
        def __init__(self, manifest, root, split, *args):
            count = 4 if split == "train" else 2
            self.samples = [SimpleNamespace(image=f"{split}-{i}.jpg") for i in range(count)]
            self.views = [(i, (0, 0, 128, 128)) for i in range(count)]

        def __len__(self):
            return len(self.views)

        def __getitem__(self, index):
            return torch.zeros(1), {"boxes": torch.empty(0, 4)}

    def infer(*args):
        calls["validation"].append(calls["updates"])
        # Legacy first-best selection must still choose epoch 2 on a 2/3 tie.
        score = 0.1 if len(calls["validation"]) == 1 else 0.5
        return {"ap50_95": score, "ap50": score, "ar100": score}, []

    tracking = SimpleNamespace(
        set_tracking_uri=lambda *a: None,
        create_experiment=lambda *a, **kw: "experiment",
        set_experiment=lambda **kw: None,
        start_run=lambda **kw: nullcontext(SimpleNamespace(info=SimpleNamespace(run_id="run"))),
        log_params=lambda *a: None,
        set_tags=lambda *a: None,
        log_metrics=lambda metrics, step: calls["logged"].append((step, metrics)),
        log_artifact=lambda *a: None,
    )
    monkeypatch.setitem(sys.modules, "mlflow", tracking)
    monkeypatch.setattr(baseline, "BoardViews", Views)
    monkeypatch.setattr(
        baseline, "verify_release", lambda *a: (SimpleNamespace(classes=["spur"]), "m")
    )
    monkeypatch.setattr(baseline, "make_model", lambda *a: model)
    monkeypatch.setattr(baseline, "infer", infer)
    monkeypatch.setattr(torch.optim, "SGD", CountingSGD)

    def metadata(args, manifest, digest):
        result = {k: v for k, v in vars(args).items() if not hasattr(v, "resolve")}
        result.update(
            {
                "normalization": "batch",
                "architecture": baseline.MODEL,
                "classes": ["spur"],
                "initialization": "random_no_download",
                "manifest_sha256": digest,
                "git_revision": "fixture",
                "inference_rpn_score_threshold": 0.05,
                "selection_policy": (
                    baseline.STEP_SELECTION
                    if args.max_steps is not None
                    else baseline.EPOCH_SELECTION
                ),
            }
        )
        return result

    monkeypatch.setattr(baseline, "metadata", metadata)
    return tmp_path / "run", calls, model


@pytest.mark.parametrize("budget", [1, 4, 5, 8, 1053])
def test_trainer_performs_exact_updates_and_only_endpoint_validation(tiny_training, budget):
    output, calls, model = tiny_training
    args = baseline.parse_args(["train", "--output", str(output), "--max-steps", str(budget)])
    summary = baseline.train(args)

    def load(name):
        return json.loads((output / f"{name}.json").read_text())

    assert calls["updates"] == budget
    assert calls["validation"] == [budget]
    assert [step for step, values in calls["logged"] if "val_ap50" in values] == [budget]
    assert summary["completed_epochs"] == budget // 4
    assert summary["partial_pass_steps"] == budget % 4
    validate_training(load("config"), summary, load("checkpoint"), load("history"))
    state = torch.load(output / "best-state.pt", weights_only=True)
    assert torch.equal(state["weight"], model.weight.detach())


def test_trainer_preserves_legacy_first_best_epoch_selection(tiny_training):
    output, calls, _ = tiny_training
    args = baseline.parse_args(["train", "--output", str(output), "--epochs", "3", "--smoke"])
    baseline.train(args)
    assert calls["updates"] == 6
    assert calls["validation"] == [2, 4, 6]
    checkpoint = json.loads((output / "checkpoint.json").read_text())
    assert checkpoint["selected_epoch"] == 2
    assert checkpoint["selected_step"] == 4


def test_failed_update_never_creates_endpoint_checkpoint(tiny_training, monkeypatch):
    output, calls, model = tiny_training

    def fail(*args):
        return {"loss": model.weight * float("nan")}

    monkeypatch.setattr(model, "forward", fail)
    args = baseline.parse_args(["train", "--output", str(output), "--max-steps", "5"])
    with pytest.raises(ValueError, match="Nonfinite"):
        baseline.train(args)
    assert calls["updates"] == 0
    assert calls["validation"] == []
    failure = json.loads((output / "failure.json").read_text())
    assert failure["completed_steps"] == 0
    assert failure["training_context"]["optimizer_step"] == 1
    assert not (output / "checkpoint.json").exists()
    assert not (output / "summary.json").exists()
