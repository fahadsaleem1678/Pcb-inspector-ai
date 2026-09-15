import json

import pytest

from ml.candidate_decisions import case_catalog
from ml.candidate_manifest import build_packet
from ml.candidate_viewer import prepare_payload, script_json
from ml.tests.test_candidate_manifest import dsp, meiwei


def test_embedded_json_is_safe_and_roundtrips():
    value = {"text": "</script><script>alert(1)</script>\u2028\u2029"}
    text = script_json(value)
    assert "<" not in text
    assert json.loads(text) == value


def test_all_pair_and_similarity_images_are_available():
    report, inventory = meiwei()
    packet = build_packet(report, inventory)
    payload = prepare_payload(packet, case_catalog(packet), inventory, "a" * 64)
    assert len(payload["images"]) == 6
    assert len(payload["cases"]) == len(case_catalog(packet))
    for case in payload["cases"]:
        assert all(identity in payload["images"] for identity in case["image_ids"])
    assert all("annotations" in image for image in payload["images"].values())


def test_class_gallery_uses_matching_source_annotations():
    report, inventory = dsp()
    packet = build_packet(report, inventory)
    payload = prepare_payload(packet, case_catalog(packet), inventory, "a" * 64)
    case = next(c for c in payload["cases"] if c["kind"] == "class")
    assert len(case["image_ids"]) == 2
    assert all(
        any(
            a["category_id"] == case["subject"]["source_category_id"]
            for a in payload["images"][identity]["annotations"]
        )
        for identity in case["image_ids"]
    )


def test_mismatched_source_image_is_rejected():
    report, inventory = dsp()
    packet = build_packet(report, inventory)
    packet["members"][0]["sha256"] = "changed"
    with pytest.raises(ValueError, match="differs"):
        prepare_payload(packet, case_catalog(packet), inventory, "a" * 64)
