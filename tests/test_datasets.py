import hashlib
import json
import random

import pytest
from PIL import Image
from pydantic import ValidationError

from pcb_inspector.datasets import DatasetManifest, grouped_split, validate_dataset


@pytest.fixture
def dataset(tmp_path):
    (tmp_path / "LICENSE.txt").write_text("Owned synthetic fixtures for software testing.")
    samples = []
    for index, split in enumerate(["train", "validation", "test"]):
        image = Image.frombytes("RGB", (64, 64), random.Random(index).randbytes(64 * 64 * 3))
        path = tmp_path / f"{index}.png"
        image.save(path)
        samples.append(
            {
                "image": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "width": 64,
                "height": 64,
                "group_id": f"board-{index}",
                "split": split,
                "annotations": [{"class_id": 0, "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10}}],
            }
        )
    manifest = {
        "name": "owned-test-fixture",
        "version": "1",
        "source_url": "https://example.com/owned-fixture",
        "source_revision": "fixture-v1",
        "license": {
            "name": "owned fixture",
            "evidence": "LICENSE.txt",
            "allowed_uses": ["research"],
            "reviewed_by": "fixture author",
            "reviewed_on": "2026-01-01",
        },
        "classes": ["test_defect"],
        "samples": samples,
    }
    path = tmp_path / "manifest.json"

    def write():
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    return tmp_path, manifest, write


def test_clean_manifest_has_reproducible_counts(dataset):
    root, manifest, write = dataset
    report = validate_dataset(write(), root)
    assert report.valid and report.ready_for_training
    assert report.sample_count == 3
    assert report.split_counts == {"train": 1, "validation": 1, "test": 1}
    assert report.class_counts == {"test_defect": 3}
    assert len(report.manifest_sha256) == 64


def test_use_restriction_and_evidence_gate(dataset):
    root, manifest, write = dataset
    report = validate_dataset(write(), root, "commercial")
    assert not report.ready_for_training
    assert "usage_not_permitted" in {issue.code for issue in report.issues}
    manifest["license"]["evidence"] = "../outside.txt"
    report = validate_dataset(write(), root)
    assert "unsafe_license_path" in {issue.code for issue in report.issues}
    manifest["license"]["evidence"] = "missing.txt"
    assert "missing_license_evidence" in {
        issue.code for issue in validate_dataset(write(), root).issues
    }


def test_annotations_checksums_dimensions_and_group_leakage(dataset):
    root, manifest, write = dataset
    manifest["samples"][0]["sha256"] = "0" * 64
    manifest["samples"][1]["group_id"] = "board-0"
    manifest["samples"][2]["width"] = 60
    manifest["samples"][2]["annotations"][0]["bbox"]["x2"] = 80
    manifest["samples"][1]["annotations"][0]["class_id"] = 5
    report = validate_dataset(write(), root)
    assert not report.valid
    assert {
        "checksum_mismatch",
        "group_leakage",
        "dimension_mismatch",
        "out_of_bounds",
        "unknown_class",
    } <= {issue.code for issue in report.issues}


def test_exact_and_reencoded_duplicates(dataset):
    root, manifest, write = dataset
    first = manifest["samples"][0]
    duplicate = root / "copy.png"
    duplicate.write_bytes((root / first["image"]).read_bytes())
    manifest["samples"][1].update({"image": "copy.png", "sha256": first["sha256"]})
    with Image.open(root / first["image"]) as image:
        image.save(root / "reencoded.png", compress_level=0)
    manifest["samples"][2].update(
        {
            "image": "reencoded.png",
            "sha256": hashlib.sha256((root / "reencoded.png").read_bytes()).hexdigest(),
        }
    )
    report = validate_dataset(write(), root)
    codes = {issue.code for issue in report.issues}
    assert {"duplicate_bytes", "duplicate_pixels", "possible_visual_leakage"} <= codes


def test_missing_class_coverage_blocks_training(dataset):
    root, manifest, write = dataset
    manifest["classes"].append("missing_component")
    report = validate_dataset(write(), root)
    assert report.valid and not report.ready_for_training
    assert len([issue for issue in report.issues if issue.code == "missing_class_coverage"]) == 3


def test_paths_and_invalid_manifest_are_rejected(dataset):
    root, manifest, write = dataset
    manifest["samples"][0]["image"] = "../escape.png"
    report = validate_dataset(write(), root)
    assert "image_unreadable" in {issue.code for issue in report.issues}
    manifest["classes"] = ["duplicate", "duplicate"]
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(manifest)


def test_group_splitting_is_deterministic_order_independent_and_complete():
    groups = [f"board-{index}" for index in range(20)]
    assignment = grouped_split(groups)
    assert assignment == grouped_split(list(reversed(groups)) + groups[:2])
    assert set(assignment) == set(groups)
    assert set(assignment.values()) == {"train", "validation", "test"}
    assert assignment != grouped_split(groups, seed="different")
    assert len(set(grouped_split(["a", "b", "c"]).values())) == 3
    with pytest.raises(ValueError):
        grouped_split(["only-one"])


def test_cli_reports_gate_failure_with_nonzero_exit(dataset):
    import subprocess
    import sys

    root, manifest, write = dataset
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pcb_inspector.datasets",
            str(write()),
            "--root",
            str(root),
            "--purpose",
            "public_demo",
            "--output",
            str(root / "validation.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["ready_for_training"] is False
    assert json.loads((root / "validation.json").read_text())["purpose"] == "public_demo"


def test_offline_pixel_limit_is_explicit_bounded_and_recorded(dataset):
    root, manifest, write = dataset
    report = validate_dataset(write(), root, max_image_pixels=4095)
    assert not report.valid
    assert all(issue.code == "image_unreadable" for issue in report.issues)
    assert report.max_image_pixels == 4095
    report = validate_dataset(write(), root, max_image_pixels=4096)
    assert report.valid and report.max_image_pixels == 4096
    assert validate_dataset(write(), root).max_image_pixels == 20_000_000
    for invalid in [0, -1, 40_000_001]:
        with pytest.raises(ValueError, match="Offline image limit"):
            validate_dataset(write(), root, max_image_pixels=invalid)
