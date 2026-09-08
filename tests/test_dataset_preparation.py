import hashlib
import importlib.util
import io
import json
import random
import zipfile
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from pcb_inspector.datasets import validate_dataset

SPEC = importlib.util.spec_from_file_location(
    "prepare_pcb_defect", Path(__file__).parents[1] / "scripts/prepare_pcb_defect.py"
)
assert SPEC and SPEC.loader
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def test_frozen_outputs_are_idempotent_and_refuse_changes(tmp_path):
    path = tmp_path / "frozen.json"
    prepare.frozen_write(path, b"original")
    prepare.frozen_write(path, b"original")
    with pytest.raises(ValueError, match="frozen artifact"):
        prepare.frozen_write(path, b"changed")
    assert path.read_bytes() == b"original"


def test_group_merges_are_transitive_and_preserve_source_families():
    records = [{"extra": {"name": f"{family}-1-1.png"}} for family in ["50", "51", "52", "53"]]
    decisions = [
        {"candidate": {"family_a": a, "family_b": b}, "decision": "merge_conservatively"}
        for a, b in [("50", "51"), ("51", "52")]
    ]
    groups = prepare.make_groups(records, decisions)
    assert groups["50"] == groups["51"] == groups["52"]
    assert groups["53"] != groups["50"]
    assert groups == prepare.make_groups(list(reversed(records)), list(reversed(decisions)))
    with pytest.raises(ValueError, match="provenance"):
        prepare.family({"extra": {"name": "untraceable.jpg"}})


def test_stratification_is_order_independent_and_honors_exclusions():
    stats = {
        f"g{i}": Counter({"images": i + 1, **{str(c): i + c + 1 for c in range(6)}})
        for i in range(7)
    }
    total = sum(stats.values(), Counter())
    selected = prepare.choose_holdout(stats, total, 2, {"g1"})
    assert "g1" not in selected
    assert selected == prepare.choose_holdout(dict(reversed(list(stats.items()))), total, 2, {"g1"})
    with pytest.raises(ValueError, match="class coverage"):
        prepare.choose_holdout({"one": Counter({"images": 1, "0": 1})}, total, 1, set())


def test_small_coco_release_preserves_pixels_boxes_and_frozen_splits(tmp_path, monkeypatch):
    archive_path = tmp_path / "fixture.zip"
    images, annotations = [], []
    with zipfile.ZipFile(archive_path, "w") as archive:
        for i in range(6):
            name = f"board-{i}.jpg"
            im = Image.frombytes("RGB", (64, 64), random.Random(i).randbytes(64 * 64 * 3))
            buffer = io.BytesIO()
            im.save(buffer, format="JPEG")
            archive.writestr(prepare.PREFIX + name, buffer.getvalue())
            images.append(
                {
                    "id": i,
                    "file_name": name,
                    "width": 64,
                    "height": 64,
                    "extra": {"name": f"{50 + i}-1-1.png"},
                }
            )
            for category in range(1, 7):
                annotations.append(
                    {
                        "id": i * 6 + category,
                        "image_id": i,
                        "category_id": category,
                        "bbox": [2, 3, 5, 7],
                    }
                )
        coco = {
            "images": images,
            "annotations": annotations,
            "licenses": [],
            "categories": [
                {"id": i + 1, "name": label.replace("short_circuit", "short")}
                for i, label in enumerate(prepare.LABELS)
            ],
        }
        archive.writestr("PCB_Defect/annotation/_annotations.coco.json", json.dumps(coco))
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    monkeypatch.setattr(prepare, "ARCHIVE_SHA256", checksum)
    review = tmp_path / "review.json"
    review.write_bytes(prepare.encoded({"archive_sha256": checksum, "decisions": []}))
    features = tmp_path / "features"
    features.mkdir()
    (features / "candidates.json").write_text("[]")
    root, manifest, release = tmp_path / "data", tmp_path / "manifest.json", tmp_path / "release"
    prepare.build(archive_path, review, features, root, manifest, release)
    original = manifest.read_bytes()
    prepare.build(archive_path, review, features, root, manifest, release)
    assert original == manifest.read_bytes()
    data = json.loads(original)
    assert data["classes"] == prepare.LABELS
    with zipfile.ZipFile(archive_path) as archive:
        for sample in data["samples"]:
            assert (root / sample["image"]).read_bytes() == archive.read(
                prepare.PREFIX + Path(sample["image"]).name
            )
            assert sample["annotations"][0] == {
                "class_id": 0,
                "bbox": {"x1": 2, "y1": 3, "x2": 7, "y2": 10},
            }
    report = validate_dataset(manifest, root)
    assert report.valid and report.ready_for_training
    assert report.sample_count == 6
    assert set(report.split_counts) == {"train", "validation", "test"}
    for counts in report.split_class_counts.values():
        assert all(value > 0 for value in counts.values())
