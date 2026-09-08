import json
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")
pytest.importorskip("mlflow")

from ml.baseline import evaluate, make_model  # noqa: E402
from ml.data import restore_boxes  # noqa: E402


def test_model_initialization_does_not_fetch_weights(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected pretrained weight download")

    monkeypatch.setattr(torch.hub, "download_url_to_file", forbidden)
    model = make_model(6, 320)
    assert model.roi_heads.box_predictor.cls_score.out_features == 7
    assert model.transform.min_size == (320,)
    assert model.transform.max_size == 640


def test_tile_outputs_restore_only_offset_without_double_resizing():
    boxes = torch.tensor([[0.0, 2.0, 20.0, 30.0]])
    result = restore_boxes(boxes, (100, 200, 300, 400))
    assert result.tolist() == [[100, 202, 120, 230]]
    assert boxes.tolist() == [[0, 2, 20, 30]]


def test_smoke_checkpoint_cannot_evaluate_test_set(tmp_path):
    for filename, value in [
        ("config.json", {"smoke": True}),
        ("checkpoint.json", {}),
        ("summary.json", {"status": "complete"}),
    ]:
        (tmp_path / filename).write_text(json.dumps(value))
    with pytest.raises(ValueError, match="full run"):
        evaluate(SimpleNamespace(run=tmp_path, split="test", final_test=True))


def test_tracking_failure_blocks_evaluation_even_after_training_finished(tmp_path):
    for filename, value in [
        ("config.json", {"smoke": False}),
        ("checkpoint.json", {}),
        ("summary.json", {"status": "complete"}),
        ("failure.json", {"status": "failed", "error_type": "TrackingError"}),
    ]:
        (tmp_path / filename).write_text(json.dumps(value))
    with pytest.raises(ValueError, match="incomplete or failed"):
        evaluate(SimpleNamespace(run=tmp_path, split="validation", final_test=False))


def test_frozen_checkpoint_reloads_without_download(monkeypatch):
    from torchvision.ops import FrozenBatchNorm2d

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected download")

    monkeypatch.setattr(torch.hub, "download_url_to_file", forbidden)
    source = make_model(6, 128, "frozen_batch")
    restored = make_model(6, 128, "frozen_batch")
    restored.load_state_dict(source.state_dict(), strict=True)
    assert any(isinstance(m, FrozenBatchNorm2d) for m in source.backbone.modules())
    assert not any(isinstance(m, torch.nn.BatchNorm2d) for m in source.backbone.modules())
    source.train()
    layer = next(m for m in source.backbone.modules() if isinstance(m, FrozenBatchNorm2d))
    before = layer.running_mean.clone()
    layer(torch.rand(1, layer.weight.numel(), 4, 4))
    assert torch.equal(before, layer.running_mean)


def test_unreviewed_initial_weights_rejected_before_deserialization(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unverified bytes deserialized")

    monkeypatch.setattr(torch, "load", forbidden)
    weights = tmp_path / "unreviewed.pth"
    weights.write_bytes(b"not the reviewed checkpoint")
    with pytest.raises(ValueError, match="checksum"):
        make_model(6, 320, "frozen_batch", weights)
