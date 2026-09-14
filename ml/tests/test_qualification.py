from types import SimpleNamespace

import pytest

from ml.error_analysis import match_image, rates
from ml.qualification import frontier, point, prepare, zero_escape_sample_size


def board(truth, predictions, group="a", image="a"):
    return {
        "image": image,
        "group": group,
        "truth": truth,
        "predictions": predictions,
        "matches": match_image(truth, predictions, 0, 2)["prediction_matches"],
    }


def target(category=1):
    return {"category_id": category, "bbox": [10, 10, 10, 10]}


def prediction(score, category=1):
    return {**target(category), "score": score}


def test_board_routing_does_not_confuse_localization_with_detection():
    boards = [board([target()], [prediction(0.9, 2)])]
    result = point(boards, ["a", "b"], 0.5)
    assert result["micro"] == {"tp": 0, "fp": 1, "fn": 1, "precision": 0, "recall": 0}
    assert result["board_routing"]["positive_boards_without_flag"] == 0
    assert result["board_routing"]["annotation_empty_board_flag_rate"] is None


def test_all_negative_or_empty_predictions_report_undefined_rates():
    result = point([board([], [])], ["a", "b"], 0.5)
    assert result["micro"]["precision"] is None and result["micro"]["recall"] is None
    assert result["board_routing"]["observed_positive_board_escape_rate"] is None
    assert result["board_routing"]["annotation_empty_board_flag_rate"] == 0


def test_board_escape_and_false_flag_are_separate():
    boards = [
        board([target()], [], image="defect"),
        board([], [prediction(0.7)], group="b", image="empty"),
    ]
    result = point(boards, ["a", "b"], 0.5)
    assert result["board_routing"]["positive_boards_without_flag"] == 1
    assert result["board_routing"]["annotation_empty_board_flag_rate"] == 1
    assert result["by_group"]["a"]["flagged_boards"] == 0
    assert result["by_group"]["b"]["flagged_boards"] == 1


def test_frontier_matches_direct_greedy_evaluation_and_keeps_ties_together():
    boards = [
        board([target(), target(2)], [prediction(0.8), prediction(0.8), prediction(0.1, 2)]),
        board([], [prediction(0.8, 2), prediction(0.4)], image="b"),
    ]
    sweep = frontier(boards)
    assert [p["score_threshold"] for p in sweep] == [1, 0.8, 0.4, 0.1, 0]
    for candidate in sweep:
        threshold = candidate["score_threshold"]
        actual = point(boards, ["a", "b"], threshold)
        for key in ("tp", "fp", "fn", "precision", "recall"):
            assert candidate[key] == actual["micro"][key]
        direct = [match_image(b["truth"], b["predictions"], threshold, 2) for b in boards]
        counts = {
            key: sum(c[key] for r in direct for c in r["counts"].values())
            for key in ("tp", "fp", "fn")
        }
        assert actual["micro"] == rates(counts)
    assert sweep[1]["tp"] == 1 and sweep[1]["fp"] == 2


@pytest.mark.parametrize("split", ["train", "test"])
def test_nonvalidation_sources_rejected(split):
    sample = SimpleNamespace(image="x", split=split)
    with pytest.raises(ValueError, match="validation only"):
        prepare([sample], ["a"], [])


@pytest.mark.parametrize(
    "row",
    [
        {"image_id": True, "category_id": 1, "bbox": [0, 0, 1, 1], "score": 0.5},
        {"image_id": 1, "category_id": 1, "bbox": [0, 0, 1, 1], "score": 0.5},
        {"image_id": 0, "category_id": True, "bbox": [0, 0, 1, 1], "score": 0.5},
        {"image_id": 0, "category_id": 1, "bbox": [-1, 0, 1, 1], "score": 0.5},
        {"image_id": 0, "category_id": 1, "bbox": [0, 0, 1000, 1], "score": 0.5},
        {"image_id": 0, "category_id": 1, "bbox": [0, 0, 1, 1], "score": float("nan")},
    ],
)
def test_invalid_predictions_cannot_enter_frontier(row):
    sample = SimpleNamespace(image="x", split="validation", width=100, height=100, annotations=[])
    with pytest.raises(ValueError):
        prepare([sample], ["a"], [row])


def test_planning_sample_size_is_not_validation_acceptance():
    assert zero_escape_sample_size(0.01) == 299
    assert zero_escape_sample_size(0.001) == 2995
    for value in (0, 1, float("nan"), -1):
        with pytest.raises(ValueError):
            zero_escape_sample_size(value)


def test_randomized_frontier_agrees_with_direct_matching():
    import random

    rng = random.Random(20260914)
    boards = []
    for index in range(12):
        truth = [target(rng.choice([1, 2])) for _ in range(rng.randrange(4))]
        predictions = [
            prediction(rng.choice([0, 0.1, 0.5, 1]), rng.choice([1, 2]))
            for _ in range(rng.randrange(8))
        ]
        boards.append(board(truth, predictions, image=str(index)))
    for candidate in frontier(boards):
        direct = [
            match_image(b["truth"], b["predictions"], candidate["score_threshold"], 2)
            for b in boards
        ]
        counts = {
            key: sum(c[key] for result in direct for c in result["counts"].values())
            for key in ("tp", "fp", "fn")
        }
        assert {key: candidate[key] for key in rates(counts)} == rates(counts)


@pytest.fixture
def audit_fixture(tmp_path, monkeypatch):
    import json

    from ml import qualification

    sample = SimpleNamespace(
        image="board.png",
        split="validation",
        width=100,
        height=100,
        sha256="a" * 64,
        group_id="group",
        annotations=[],
    )
    manifest = SimpleNamespace(classes=["a"], samples=[sample])
    evidence = {
        "manifest_sha256": "b" * 64,
        "configuration": {"classes": ["a"]},
        "checkpoint_sha256": "c" * 64,
        "artifact_sha256": {},
        "test_evaluation_artifact_exists": False,
    }
    saved = {"source_images": ["board.png"], "predictions": []}
    (tmp_path / "best-validation.json").write_text(json.dumps(saved), encoding="utf-8")
    monkeypatch.setattr(qualification, "summarize", lambda run: evidence)
    monkeypatch.setattr(qualification, "verify_release", lambda *args: (manifest, "b" * 64))
    return qualification, tmp_path, evidence, manifest


def test_audit_never_promotes_even_with_zero_errors(audit_fixture):
    qualification, run, _, _ = audit_fixture
    result = qualification.audit_run(run, None, None, None)
    assert result["readiness"] == "BLOCKED" and result["production_threshold"] is None
    assert not result["promotion_eligible"] and not result["test_evaluated"]
    assert (
        result["global_threshold_frontier"][
            "highest_threshold_with_zero_observed_positive_board_escapes"
        ]
        is None
    )
    assert result["code_sha256"]["qualification.py"]


@pytest.mark.parametrize("field", ["manifest", "classes", "order"])
def test_audit_rejects_mismatched_evidence(audit_fixture, field):
    qualification, run, evidence, manifest = audit_fixture
    if field == "manifest":
        evidence["manifest_sha256"] = "d" * 64
    elif field == "classes":
        evidence["configuration"]["classes"] = ["wrong"]
    else:
        manifest.samples[0].image = "wrong.png"
    with pytest.raises(ValueError):
        qualification.audit_run(run, None, None, None)
