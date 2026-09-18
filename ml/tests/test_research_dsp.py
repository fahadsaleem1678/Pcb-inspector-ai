import sys

import pytest

from ml.research_dsp import main, select_validation


def rows():
    return [
        {"file": f"{i:04}.jpg", "annotations": [{"category_id": i % 9 + 1}]} for i in range(360)
    ]


def test_validation_is_deterministic_and_covers_all_source_classes():
    data = rows()
    selected = select_validation(data, 256, 20260915)
    assert len(selected) == 256
    assert len({r["file"] for r in selected}) == 256
    assert selected == select_validation(list(reversed(data)), 256, 20260915)
    for category in range(1, 10):
        assert (
            sum(any(a["category_id"] == category for a in r["annotations"]) for r in selected) >= 16
        )


@pytest.mark.parametrize("count", [0, 143, 361])
def test_validation_rejects_bad_sample_counts(count):
    with pytest.raises(ValueError):
        select_validation(rows(), count, 1)


def test_validation_rejects_missing_source_class():
    data = [r for r in rows() if r["annotations"][0]["category_id"] != 9]
    with pytest.raises(ValueError, match="coverage"):
        select_validation(data, 256, 1)


def test_cli_requires_explicit_unreviewed_research_opt_in(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["research_dsp", "train", "--output", "unused"])
    with pytest.raises(SystemExit):
        main()


@pytest.mark.parametrize("size", [None, 320, 640])
def test_cli_passes_selected_resolution_to_training(monkeypatch, size):
    import ml.research_dsp as research

    received = []
    monkeypatch.setattr(research, "train", received.append)
    argv = [
        "research_dsp",
        "train",
        "--allow-unreviewed-research",
        "--data",
        "data",
        "--weights",
        "weights",
        "--manifest-sha256",
        "pinned",
        "--output",
        "unused",
    ]
    if size is not None:
        argv += ["--input-size", str(size)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert received[0].input_size == (320 if size is None else size)


@pytest.mark.parametrize("size", [320, 640])
def test_resolution_survives_checkpoint_reload(size):
    import torch

    from ml.baseline import make_model

    model = make_model(9, size, "frozen_batch")
    reloaded = make_model(9, size, "frozen_batch")
    reloaded.load_state_dict(model.state_dict())
    for candidate in (model, reloaded):
        candidate.eval()
        with torch.no_grad():
            images, _ = candidate.transform([torch.zeros(3, 100, 150)], None)
        assert images.image_sizes == [(size, size * 3 // 2)]
        assert candidate.roi_heads.box_predictor.cls_score.out_features == 10
