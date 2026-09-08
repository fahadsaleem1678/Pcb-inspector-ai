from types import SimpleNamespace

import pytest

pytest.importorskip("pycocotools")
pytest.importorskip("numpy")

from ml.metrics import coco_metrics, grouped_metrics  # noqa: E402
from pcb_inspector.datasets import Annotation  # noqa: E402


def sample(group="board-1", class_id=0):
    return SimpleNamespace(
        width=100,
        height=100,
        group_id=group,
        annotations=[Annotation(class_id=class_id, bbox={"x1": 10, "y1": 20, "x2": 30, "y2": 40})],
    )


def test_perfect_predictions_have_perfect_coco_metrics():
    result = coco_metrics(
        [sample()],
        ["open", "short"],
        [{"image_id": 0, "category_id": 1, "bbox": [10, 20, 20, 20], "score": 0.9}],
    )
    assert result["ap50_95"] == pytest.approx(1.0)
    assert result["ar100"] == pytest.approx(1.0)
    assert result["per_class"]["short"]["ap50"] is None


def test_empty_predictions_are_valid_zero_recall_not_a_crash():
    result = coco_metrics([sample()], ["open"], [])
    assert result["ap50_95"] == 0.0
    assert result["ar100"] == 0.0


def test_wrong_class_predictions_do_not_match_and_group_ids_are_remapped():
    samples = [sample("b1"), sample("b2", 1)]
    rows = [{"image_id": 1, "category_id": 2, "bbox": [10, 20, 20, 20], "score": 0.9}]
    result = grouped_metrics(samples, ["open", "short"], rows)
    assert result["b1"]["ap50"] == 0.0
    assert result["b2"]["ap50"] == pytest.approx(1.0)
    wrong = coco_metrics(
        [sample()],
        ["open", "short"],
        [
            {"image_id": 0, "category_id": 2, "bbox": [10, 20, 20, 20], "score": 1.0},
        ],
    )
    assert wrong["ap50"] == 0.0


def test_predictions_cannot_reference_another_split():
    with pytest.raises(ValueError):
        coco_metrics(
            [sample()],
            ["open"],
            [
                {"image_id": 1, "category_id": 1, "bbox": [10, 20, 20, 20], "score": 1.0},
            ],
        )
