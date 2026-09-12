import random
from copy import deepcopy

import pytest

from ml.schedule import STEP_SELECTION, training_schedule, validate_training


@pytest.mark.parametrize("budget", [1, 164, 165, 166, 330, 1053])
def test_exact_budget_preserves_seeded_permutations_and_final_prefix(budget):
    passes = list(training_schedule(165, 20260908, max_steps=budget))
    assert sum(map(len, passes)) == budget
    for epoch, indices in enumerate(passes):
        expected = list(range(165))
        random.Random(20260908 + epoch).shuffle(expected)
        assert indices == expected[: len(indices)]
    if budget == 1053:
        assert list(map(len, passes)) == [165] * 6 + [63]


@pytest.mark.parametrize("budget", [0, -1, 1.5, True, "2"])
def test_invalid_budget_is_rejected(budget):
    with pytest.raises(ValueError, match="positive integer"):
        list(training_schedule(165, 1, max_steps=budget))


def test_modes_are_exclusive_and_legacy_smoke_is_unchanged():
    for kwargs in [{}, {"epochs": 2, "max_steps": 3}]:
        with pytest.raises(ValueError, match="exactly one"):
            list(training_schedule(4, 17, **kwargs))
    legacy = list(training_schedule(4, 17, epochs=3, smoke=True))
    full = list(training_schedule(4, 17, epochs=3))
    assert legacy == [indices[:2] for indices in full]
    assert list(map(len, training_schedule(4, 17, max_steps=5, smoke=True))) == [4, 1]


def budget_contract():
    config = {
        "epochs": None,
        "max_steps": 5,
        "training_views": 4,
        "seed": 17,
        "selection_policy": STEP_SELECTION,
    }
    summary = {
        "completed_steps": 5,
        "completed_epochs": 1,
        "partial_pass_steps": 1,
        "best_validation_ap50_95": 0.5,
    }
    checkpoint = {
        "selected_epoch": None,
        "selected_step": 5,
        "selection_policy": STEP_SELECTION,
        "selection_metric": "optimizer_steps",
        "selection_value": 5,
    }
    history = [
        {
            "pass": number,
            "step_start": start,
            "step_end": end,
            "train_steps": len(indices),
            "train_view_indices": indices,
            "pass_complete": len(indices) == 4,
        }
        for number, start, end, indices in zip(
            [1, 2], [1, 5], [4, 5], training_schedule(4, 17, max_steps=5), strict=True
        )
    ]
    history[-1]["validation"] = {"ap50_95": 0.5}
    return config, summary, checkpoint, history


def test_budget_contract_accepts_final_partial_pass():
    args = budget_contract()
    assert validate_training(*args) is args[-1][-1]


@pytest.mark.parametrize(
    "mutation",
    [
        "under",
        "over",
        "missing_pass",
        "extra_pass",
        "order",
        "duplicate",
        "wrong_seed",
        "wrong_pass",
        "step_gap",
        "wrong_count",
        "partial_as_epoch",
        "partial_as_complete",
        "extra_validation",
        "no_validation",
        "early_checkpoint",
        "wrong_policy",
        "epoch_mode",
        "metric_selection",
        "wrong_value",
        "summary_passes",
        "summary_partial",
        "nonfinite_metric",
        "summary_score",
        "boolean_index",
        "boolean_steps",
    ],
)
def test_budget_contract_rejects_misleading_history_and_selection(mutation):
    config, summary, checkpoint, history = budget_contract()
    if mutation == "under":
        summary["completed_steps"] = 4
    elif mutation == "over":
        summary["completed_steps"] = 6
    elif mutation == "missing_pass":
        history.pop()
    elif mutation == "extra_pass":
        history.append(deepcopy(history[-1]))
    elif mutation == "order":
        history[0]["train_view_indices"].reverse()
    elif mutation == "duplicate":
        history[0]["train_view_indices"][1] = history[0]["train_view_indices"][0]
    elif mutation == "wrong_seed":
        config["seed"] += 1
    elif mutation == "wrong_pass":
        history[-1]["pass"] = 3
    elif mutation == "step_gap":
        history[-1]["step_start"] = 6
    elif mutation == "wrong_count":
        history[-1]["train_steps"] = 2
    elif mutation == "partial_as_epoch":
        history[-1]["epoch"] = 2
    elif mutation == "partial_as_complete":
        history[-1]["pass_complete"] = True
    elif mutation == "extra_validation":
        history[0]["validation"] = {"ap50_95": 0.9}
    elif mutation == "no_validation":
        del history[-1]["validation"]
    elif mutation == "early_checkpoint":
        checkpoint["selected_step"] = 4
    elif mutation == "wrong_policy":
        checkpoint["selection_policy"] = "best"
    elif mutation == "epoch_mode":
        config["epochs"] = 2
    elif mutation == "metric_selection":
        checkpoint["selection_metric"] = "validation_ap50_95"
    elif mutation == "wrong_value":
        checkpoint["selection_value"] = 4
    elif mutation == "summary_passes":
        summary["completed_epochs"] = 2
    elif mutation == "summary_partial":
        summary["partial_pass_steps"] = 0
    elif mutation == "nonfinite_metric":
        history[-1]["validation"]["ap50_95"] = float("nan")
    elif mutation == "summary_score":
        summary["best_validation_ap50_95"] = 0.9
    elif mutation == "boolean_index":
        history[-1]["train_view_indices"][0] = True
    elif mutation == "boolean_steps":
        history[-1]["train_steps"] = True
    with pytest.raises(ValueError):
        validate_training(config, summary, checkpoint, history)
