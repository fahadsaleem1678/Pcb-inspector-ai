from copy import deepcopy
from types import SimpleNamespace

import pytest

pytest.importorskip("torch")
pytest.importorskip("torchvision")

from ml.probe import probe, verify_control  # noqa: E402


@pytest.mark.parametrize("change", ["source_images", "predictions", "ap50"])
def test_probe_rejects_nonreproducing_control(change):
    reference = {
        "source_images": ["a"],
        "predictions": [{"score": 0.5}],
        "metrics": {"ap50_95": 0.1, "ap50": 0.2, "ar100": 0.3, "per_class": {}, "by_group": {}},
    }
    result = deepcopy(reference)
    result["metrics"]["latency_ms"] = {"mean": 999}  # latency need not match
    verify_control(reference, result)
    if change == "ap50":
        result["metrics"][change] = 0.9
    else:
        result[change] = []
    with pytest.raises(ValueError, match="Control"):
        verify_control(reference, result)


def test_probe_preserves_existing_results(tmp_path):
    sentinel = tmp_path / "summary.json"
    sentinel.write_text("existing")
    with pytest.raises(ValueError, match="already exists"):
        probe(SimpleNamespace(output=tmp_path))
    assert sentinel.read_text() == "existing"
