import json
from types import SimpleNamespace

import pytest

from ml.review import build, build_boards, script_json
from pcb_inspector.datasets import Annotation


def sample(split="validation", name="board.jpg"):
    return SimpleNamespace(
        split=split,
        image=name,
        group_id="family",
        width=100,
        height=80,
        sha256="a" * 64,
        annotations=[Annotation(class_id=0, bbox={"x1": 10, "y1": 20, "x2": 30, "y2": 40})],
    )


def test_review_keeps_original_coordinates_and_threshold_matching():
    predictions = [{"image_id": 0, "category_id": 1, "bbox": [10, 20, 20, 20], "score": 0.2}]
    boards = build_boards([sample()], ["mouse_bite"], predictions)
    assert boards[0]["annotations"][0]["bbox"] == [10, 20, 20, 20]
    assert boards[0]["profiles"]["0.05"]["missed_indices"] == []
    assert boards[0]["profiles"]["0.25"]["missed_indices"] == [0]
    assert boards[0]["predictions"] == predictions


def test_review_sorts_most_missed_without_moving_asset_identity():
    predictions = [{"image_id": 0, "category_id": 1, "bbox": [10, 20, 20, 20], "score": 0.9}]
    boards = build_boards([sample(name="a.jpg"), sample(name="b.jpg")], ["mouse_bite"], predictions)
    assert [b["image"] for b in boards] == ["b.jpg", "a.jpg"]
    assert boards[0]["asset"] == "images/board-001.jpg"


def test_review_rejects_other_splits_and_unknown_prediction_images():
    with pytest.raises(ValueError, match="outside validation"):
        build_boards([sample("test")], ["mouse_bite"], [])
    with pytest.raises(ValueError, match="outside validation"):
        build_boards([sample()], ["mouse_bite"], [{"image_id": 2}])


def test_review_html_payload_cannot_close_script_element():
    value = {"image": "</script><script>alert(1)</script>", "note": "line\u2028break"}
    encoded = script_json(value)
    assert "</script>" not in encoded
    assert json.loads(encoded) == value


def test_review_refuses_existing_destination(tmp_path):
    marker = tmp_path / "index.html"
    marker.write_text("existing")
    with pytest.raises(ValueError, match="already exists"):
        build(SimpleNamespace(output=tmp_path))
    assert marker.read_text() == "existing"
