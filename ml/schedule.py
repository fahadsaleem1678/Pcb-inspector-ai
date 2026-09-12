"""Seeded training passes and shared completion/selection contracts."""

import math
import random

EPOCH_SELECTION = "best_validation_ap50_95_first"
STEP_SELECTION = "final_budget_endpoint"


def positive_integer(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def training_schedule(views, seed, *, epochs=None, max_steps=None, smoke=False):
    """Yield one seeded permutation (or final prefix) at a time, never skip views."""
    positive_integer(views, "Training views")
    if (epochs is None) == (max_steps is None):
        raise ValueError("Specify exactly one of epochs or max_steps")
    if max_steps is not None:
        positive_integer(max_steps, "max_steps")
        passes = (max_steps + views - 1) // views
    else:
        positive_integer(epochs, "epochs")
        passes = epochs
    consumed = 0
    for epoch in range(passes):
        indices = list(range(views))
        random.Random(seed + epoch).shuffle(indices)
        if max_steps is not None:
            indices = indices[: max_steps - consumed]
        elif smoke:
            indices = indices[:2]  # Preserve historical epoch smoke behavior.
        consumed += len(indices)
        yield indices


def validate_training(config, summary, checkpoint, history):
    """Reject incomplete schedules or extra selection opportunities before loading weights.

    Legacy runs lack step/policy metadata; their first-best epoch contract remains valid.
    New exact-budget runs require complete schedule, endpoint and selection metadata.
    """
    budget = config.get("max_steps")
    if budget is None:
        epochs = positive_integer(config["epochs"], "epochs")
        if summary["completed_epochs"] != epochs:
            raise ValueError("Configured epochs did not complete")
        if [row["epoch"] for row in history] != list(range(1, epochs + 1)):
            raise ValueError("Epoch history is incomplete")
        if config.get("selection_policy", EPOCH_SELECTION) != EPOCH_SELECTION:
            raise ValueError("Invalid epoch selection policy")
        selected = max(history, key=lambda row: row["validation"]["ap50_95"])
        if selected["epoch"] != checkpoint["selected_epoch"]:
            raise ValueError("Best checkpoint differs from validation selection history")
        return selected

    positive_integer(budget, "max_steps")
    views = positive_integer(config["training_views"], "Training views")
    if config.get("epochs") is not None or config.get("selection_policy") != STEP_SELECTION:
        raise ValueError("Invalid step-budget mode or selection policy")
    complete, partial = divmod(budget, views)
    expected_count = complete + bool(partial)
    if len(history) != expected_count:
        raise ValueError("Step-budget history is incomplete or over budget")
    for key, expected in {
        "completed_steps": budget,
        "completed_epochs": complete,
        "partial_pass_steps": partial,
    }.items():
        if type(summary.get(key)) is not int or summary[key] != expected:
            raise ValueError(f"Step-budget completion differs: {key}")
    consumed = 0
    schedule = training_schedule(views, config["seed"], max_steps=budget)
    for number, (row, indices) in enumerate(zip(history, schedule, strict=True), 1):
        for key, expected in {
            "pass": number,
            "step_start": consumed + 1,
            "step_end": consumed + len(indices),
            "train_steps": len(indices),
        }.items():
            if type(row.get(key)) is not int or row[key] != expected:
                raise ValueError(f"Step-budget history differs: {key}")
        recorded = row.get("train_view_indices")
        if (
            not isinstance(recorded, list)
            or any(type(index) is not int for index in recorded)
            or recorded != indices
        ):
            raise ValueError("Step-budget seeded view ordering differs")
        if "epoch" in row or row.get("pass_complete") is not (len(indices) == views):
            raise ValueError("Step-budget partial pass misreported as an epoch")
        endpoint = number == expected_count
        if ("validation" in row) != endpoint:
            raise ValueError("Step-budget validation must occur only at the endpoint")
        consumed += len(indices)
    if (
        type(checkpoint.get("selected_step")) is not int
        or checkpoint["selected_step"] != budget
        or checkpoint.get("selected_epoch") is not None
        or checkpoint.get("selection_policy") != STEP_SELECTION
        or checkpoint.get("selection_metric") != "optimizer_steps"
        or type(checkpoint.get("selection_value")) is not int
        or checkpoint["selection_value"] != budget
    ):
        raise ValueError("Checkpoint differs from final budget endpoint selection")
    score = history[-1]["validation"]["ap50_95"]
    if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Invalid endpoint validation score")
    if summary.get("best_validation_ap50_95") != score:
        raise ValueError("Endpoint validation differs from summary")
    return history[-1]
