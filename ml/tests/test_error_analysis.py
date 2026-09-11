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


def test_prediction_identity_and_false_positive_context_priority():
    rows = [
        prediction(score=0.1),  # filtered, but original indices must remain stable
        prediction(score=0.95),
        prediction(score=0.9),
        prediction(category=2, score=0.8),
        prediction(score=0.7, box=[25, 20, 20, 20]),
        prediction(score=0.6, box=[100, 100, 20, 20]),
    ]
    result = match_image([target()], rows, 0.25, 2)
    matches = result["prediction_matches"]
    assert [m["prediction_index"] for m in matches] == [1, 2, 3, 4, 5]
    assert [m["outcome"] for m in matches] == [
        "matched",
        "duplicate",
        "class_confusion",
        "partial_overlap",
        "no_overlap",
    ]
    assert matches[0]["matched_annotation_index"] == 0
    assert matches[1]["matched_annotation_index"] is None
    assert matches[2]["best_any_class"] == {"annotation_index": 0, "iou": 1.0}
    assert matches[-1]["best_any_class"] == {"annotation_index": None, "iou": 0.0}
    assert sum(result["false_positive_context"].values()) == 4


def test_available_same_class_target_wins_before_duplicate_context():
    result = match_image([target(), target()], [prediction(), prediction()], 0.25, 1)
    assert [m["matched_annotation_index"] for m in result["prediction_matches"]] == [0, 1]
    assert all(m["outcome"] == "matched" for m in result["prediction_matches"])


def test_empty_truth_and_score_ties_keep_stable_prediction_identity():
    result = match_image([], [prediction(), prediction()], 0.25, 1)
    assert [m["prediction_index"] for m in result["prediction_matches"]] == [0, 1]
    assert result["false_positive_context"]["no_overlap"] == 2
    assert all(
        m["best_same_class"]["annotation_index"] is None for m in result["prediction_matches"]
    )


def test_overlap_just_below_half_is_not_rounded_into_a_match():
    truth = [target(box=[0, 0, 20, 20])]
    below = match_image(truth, [prediction(box=[0, 0, 20, 40.01])], 0.5, 1)
    exact = match_image(truth, [prediction(box=[0, 0, 20, 40])], 0.5, 1)
    detail = below["prediction_matches"][0]
    assert 0.499 < detail["best_same_class"]["iou"] < 0.5
    assert detail["outcome"] == "partial_overlap"
    assert exact["prediction_matches"][0]["outcome"] == "matched"
