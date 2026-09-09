import pytest

from ml.error_analysis import match_image, rates


def target(category=1, box=None):
    return {"category_id": category, "bbox": box or [10, 20, 20, 20]}


def prediction(category=1, score=0.9, box=None):
    return {**target(category, box), "score": score}


def test_duplicate_predictions_cannot_inflate_recall():
    result = match_image([target()], [prediction(), prediction(score=0.8)], 0.05, 1)
    assert result["counts"][1] == {"tp": 1, "fp": 1, "fn": 0}
    assert result["missed_indices"] == []
    assert rates(result["counts"][1])["precision"] == 0.5


def test_wrong_class_is_false_positive_and_missed_defect():
    result = match_image([target()], [prediction(2)], 0.05, 2)
    assert result["counts"][1] == {"tp": 0, "fp": 0, "fn": 1}
    assert result["counts"][2] == {"tp": 0, "fp": 1, "fn": 0}
    assert result["class_agnostic_target_coverage"] == 1


def test_one_prediction_cannot_match_two_targets():
    result = match_image([target(), target()], [prediction()], 0.05, 1)
    assert result["counts"][1] == {"tp": 1, "fp": 0, "fn": 1}
    assert len(result["missed_indices"]) == 1
    assert result["class_agnostic_target_coverage"] == 2


def test_threshold_boundary_and_empty_cases():
    result = match_image([target()], [prediction(score=0.25)], 0.25, 1)
    assert result["counts"][1]["tp"] == 1
    result = match_image([target()], [prediction(score=0.249)], 0.25, 1)
    assert result["counts"][1]["fn"] == 1
    assert rates(result["counts"][1]) == {"tp": 0, "fp": 0, "fn": 1, "precision": None, "recall": 0}
    result = match_image([], [], 0.5, 1)
    assert rates(result["counts"][1])["recall"] is None


def test_nonoverlap_does_not_count_as_detection():
    result = match_image([target()], [prediction(box=[100, 100, 10, 10])], 0.05, 1)
    assert result["counts"][1] == {"tp": 0, "fp": 1, "fn": 1}
    assert result["class_agnostic_target_coverage"] == 0


@pytest.mark.parametrize(
    "row", [prediction(score=float("nan")), prediction(category=3), prediction(box=[0, 0, -1, 2])]
)
def test_invalid_predictions_fail_closed(row):
    with pytest.raises(ValueError):
        match_image([target()], [row], 0.05, 2)
