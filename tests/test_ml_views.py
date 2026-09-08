from types import SimpleNamespace

import pytest

from ml.data import BoardViews, crop_annotations, starts, windows
from pcb_inspector.datasets import Annotation


def test_tile_windows_cover_borders_without_repeated_edge_tiles():
    assert starts(640, 1024, 256) == [0]
    assert starts(2048, 1024, 256) == [0, 768, 1024]
    tiles = windows(2050, 1300, 1024, 256)
    assert len(tiles) == len(set(tiles)) == 6
    assert max(t[2] for t in tiles) == 2050
    assert max(t[3] for t in tiles) == 1300
    assert windows(2050, 1300, 0, 0) == [(0, 0, 2050, 1300)]
    for invalid in [(0, 0), (256, 256), (256, -1)]:
        with pytest.raises(ValueError):
            starts(640, *invalid)


def test_tile_labels_clip_crossing_targets_and_retain_background_convention():
    annotations = [
        Annotation(class_id=0, bbox={"x1": 80, "y1": 80, "x2": 140, "y2": 150}),
        Annotation(class_id=5, bbox={"x1": 110, "y1": 110, "x2": 130, "y2": 135}),
        Annotation(class_id=2, bbox={"x1": 5, "y1": 5, "x2": 20, "y2": 20}),
    ]
    boxes, labels = crop_annotations(annotations, (100, 100, 200, 200))
    assert boxes == [[0, 0, 40, 50], [10, 10, 30, 35]]
    assert labels == [1, 6]
    assert crop_annotations(annotations, (150, 150, 200, 200)) == ([], [])


def test_views_never_move_images_between_frozen_splits(tmp_path):
    samples = [
        SimpleNamespace(split=split, width=200, height=200, image=f"{split}.png")
        for split in ["train", "validation", "test"]
    ]
    views = BoardViews(SimpleNamespace(samples=samples), tmp_path, "train", 128, 32)
    assert len(views) == 4
    assert all(views.samples[index].split == "train" for index, _ in views.views)
    assert views.by_image == {0: [0, 1, 2, 3]}
    with pytest.raises(ValueError):
        BoardViews(SimpleNamespace(samples=samples), tmp_path, "unknown")


def test_training_preflight_rejects_changed_images_and_frozen_evidence(tmp_path):
    import hashlib
    import json

    from PIL import Image

    from ml.data import verify_release

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    image = tmp_path / "board.png"
    Image.new("RGB", (64, 64), "green").save(image)
    evidence = tmp_path / "license.json"
    evidence.write_text("recorded source rights")
    review = tmp_path / "group-review.json"
    review.write_text("recorded grouping decisions")
    manifest = {
        "name": "fixture",
        "version": "1",
        "source_url": "https://example.com/source",
        "source_revision": "fixture",
        "classes": ["open"],
        "license": {
            "name": "owned",
            "evidence": evidence.name,
            "allowed_uses": ["research"],
            "reviewed_by": "fixture",
            "reviewed_on": "2026-01-01",
        },
        "samples": [
            {
                "image": image.name,
                "sha256": digest(image),
                "width": 64,
                "height": 64,
                "group_id": "g1",
                "split": "train",
                "annotations": [],
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    release = {
        "manifest_sha256": digest(path),
        "grouping_review_sha256": digest(review),
        "license_evidence_sha256": digest(evidence),
        "group_assignment": {"g1": "train"},
    }
    (tmp_path / "release.json").write_text(json.dumps(release))
    validation = {"manifest_sha256": digest(path), "ready_for_training": True, "issues": []}
    report = tmp_path / "validation.json"
    report.write_text(json.dumps(validation))
    loaded, checksum = verify_release(path, tmp_path, tmp_path)
    assert loaded.classes == ["open"] and checksum == digest(path)
    validation["ready_for_training"] = False
    report.write_text(json.dumps(validation))
    with pytest.raises(ValueError, match="unresolved gates"):
        verify_release(path, tmp_path, tmp_path)
    validation["ready_for_training"] = True
    report.write_text(json.dumps(validation))
    Image.new("RGB", (64, 64), "red").save(image)
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_release(path, tmp_path, tmp_path)
