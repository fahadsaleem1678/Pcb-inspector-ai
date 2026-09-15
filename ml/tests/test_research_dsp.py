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
