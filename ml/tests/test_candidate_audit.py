import io
import zipfile

import pytest
from PIL import Image

from ml.candidate_audit import (
    fingerprint,
    leakage,
    member_bytes,
    normalize_border_rounding,
    read_coco,
)


def image_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (20, 20), "green").save(stream, format="PNG")
    return stream.getvalue()


def test_fingerprint_deterministic():
    first = fingerprint(image_bytes())
    assert first == fingerprint(image_bytes())
    assert (first["width"], first["height"]) == (20, 20)


def test_leakage_distinguishes_exact_and_heuristic_matches():
    rows = [
        {"file": "a", "split": "train", "pixel_sha256": "same", "dhash": 0},
        {"file": "b", "split": "test", "pixel_sha256": "same", "dhash": 0},
        {"file": "c", "split": "validation", "pixel_sha256": "different", "dhash": 1},
    ]
    result = leakage(rows, limit=1)
    assert len(result["cross_split_duplicate_pixel_groups"]) == 1
    assert result["near_duplicate_cross_split_pairs"] == 2
    assert len(result["near_duplicate_candidates"]) == 1
    assert result["candidate_list_truncated"]
    assert not result["near_duplicate_is_proof_of_leakage"]


@pytest.mark.parametrize("name", ["../x", "/x", "a/../../x", "a\\x"])
def test_rejects_unsafe_archive_members(name):
    with pytest.raises(ValueError, match="Unsafe"):
        member_bytes(None, name)


def test_archive_size_limit():
    with zipfile.ZipFile(io.BytesIO(), "w") as archive:
        archive.writestr("x", b"123")
        with pytest.raises(ValueError, match="size limit"):
            member_bytes(archive, "x", limit=2)


def test_coco_reports_border_issue_without_mutating_and_rejects_unknown_image():
    box = [1, 1, 19.01, 10]
    document = {
        "categories": [{"id": 1, "name": "source"}],
        "images": [{"id": 1, "file_name": "x.png", "width": 20, "height": 20}],
        "annotations": [{"id": 1, "image_id": 1, "category_id": 1, "bbox": box}],
    }
    with zipfile.ZipFile(io.BytesIO(), "w") as archive:
        archive.writestr("images/x.png", image_bytes())
        rows, _, issues = read_coco(document, archive, "images/", "train")
        assert [issue["code"] for issue in issues] == ["invalid_box"]
        assert rows[0]["annotations"][0]["bbox"] == box
        document["annotations"][0]["image_id"] = 2
        with pytest.raises(ValueError, match="unknown"):
            read_coco(document, archive, "images/", "train")


def test_border_proposal_is_bounded_and_preserves_input():
    box = [1, 1, 19.0113, 10]
    assert normalize_border_rounding(box, 20, 20) == [1, 1, 19, 10]
    assert box == [1, 1, 19.0113, 10]
    assert normalize_border_rounding([1, 1, 5, 5], 20, 20) == [1, 1, 5, 5]
    assert normalize_border_rounding([-0.01, 1, 2, 2], 20, 20) == [0, 1, 1.99, 2]


@pytest.mark.parametrize(
    "box", [[1, 1, -1, 2], [1, 1, float("nan"), 2], [1, 1, 20, 2], [20, 1, 0.01, 1]]
)
def test_border_proposal_rejects_invalid_or_erased_boxes(box):
    with pytest.raises(ValueError):
        normalize_border_rounding(box, 20, 20)


def test_border_proposal_cannot_relax_tolerance():
    with pytest.raises(ValueError):
        normalize_border_rounding([1, 1, 5, 5], 20, 20, tolerance=1)
