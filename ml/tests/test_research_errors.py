import pytest

from ml.research_errors import analyze, explain_miss, size_bin


def target(category=5, box=None):
    return {"category_id": category, "bbox": box or [0, 0, 10, 10]}


def pred(category=5, score=0.9, box=None):
    return {**target(category, box), "score": score, "image_id": 0}


@pytest.mark.parametrize(
    "predictions,reason",
    [
        ([pred()], "matching_competition"),
        ([pred(category=2)], "class_confusion"),
        ([pred(score=0.1)], "score_suppressed"),
        ([pred(box=[5, 0, 10, 10])], "same_class_localization"),
        ([pred(category=2, box=[5, 0, 10, 10])], "wrong_class_partial_overlap"),
        ([pred(box=[30, 30, 10, 10])], "no_useful_saved_detection"),
        ([], "no_useful_saved_detection"),
    ],
)
def test_miss_categories(predictions, reason):
    assert explain_miss(target(), predictions, 0.25)["reason"] == reason


def test_one_prediction_cannot_match_two_targets():
    rows = [{"file": "x", "asset": "x", "sha256": "hash", "annotations": [target(), target()]}]
    summary, cases = analyze(rows, [pred()], 0.25)
    assert summary["micro"]["tp"] == 1
    assert summary["micro"]["fn"] == 1
    assert cases[0]["reason"] == "matching_competition"
    assert summary["per_class"]["MB"]["short_side_bins"]["8-16px"] == {"targets": 2, "matched": 1}


def test_class_confusion_counts_both_false_negative_and_false_positive():
    rows = [{"file": "x", "asset": "x", "sha256": "hash", "annotations": [target()]}]
    summary, _ = analyze(rows, [pred(category=2)], 0.25)
    assert summary["per_class"]["MB"]["fn"] == 1
    assert summary["per_class"]["SP"]["fp"] == 1
    assert summary["missed_target_confusions"] == {"MB->SP": 1}


def test_score_suppression_is_not_reported_as_missing_saved_box():
    rows = [{"file": "x", "asset": "x", "sha256": "hash", "annotations": [target()]}]
    low, _ = analyze(rows, [pred(score=0.1)], 0.05)
    high, cases = analyze(rows, [pred(score=0.1)], 0.25)
    assert low["micro"]["tp"] == 1
    assert high["micro"]["tp"] == 0
    assert cases[0]["reason"] == "score_suppressed"


def test_rejects_predictions_outside_validation():
    with pytest.raises(ValueError, match="outside"):
        analyze([], [pred()], 0.25)


def test_short_side_bin_boundaries():
    assert [size_bin([0, 0, x, 100]) for x in [3, 4, 8, 16]] == [
        "<4px",
        "4-8px",
        "8-16px",
        ">=16px",
    ]
