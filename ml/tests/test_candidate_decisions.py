import copy
import json

import pytest

from ml.candidate_audit import digest
from ml.candidate_decisions import (
    content_hash,
    import_batch,
    load_packet,
    read_json,
    template,
    validate_batch,
)

PACKET_HASH = "a" * 64
PARENT_HASH = "b" * 64
CATALOG = {"near-1": {"kind": "near", "subject": {}}, "box-1": {"kind": "box", "subject": {}}}


def batch(reviewer="Expert A", decision="related", time="2026-09-14T12:00:00+05:00"):
    return {
        "schema_version": "1.0",
        "packet_sha256": PACKET_HASH,
        "reviewer": reviewer,
        "reviewed_at": time,
        "decisions": [
            {
                "case_id": "near-1",
                "answers": {"relationship": decision},
                "rationale": "Compared source references.",
            }
        ],
    }


def test_import_preserves_conflicts_and_history_without_approval():
    first, changed = import_batch(batch(), CATALOG, PACKET_HASH)
    assert changed
    original = copy.deepcopy(first)
    second, changed = import_batch(
        batch("Expert B", "unrelated"), CATALOG, PACKET_HASH, first, PARENT_HASH
    )
    assert changed and second["revision"] == 2
    assert second["parent_sha256"] == PARENT_HASH
    assert first == original
    states = {s["case_id"]: s for s in second["states"]}
    assert states["near-1"]["status"] == "conflicting"
    assert len(states["near-1"]["current_reviews"]) == 2
    assert states["box-1"]["status"] == "unreviewed"
    assert not second["ready_for_training"] and not second["production_eligible"]


def test_identical_reimport_is_idempotent():
    first, _ = import_batch(batch(), CATALOG, PACKET_HASH)
    again, changed = import_batch(batch(), CATALOG, PACKET_HASH, first, PARENT_HASH)
    assert not changed and again == first


def test_reviewer_update_keeps_old_batch_and_requires_newer_timestamp():
    first, _ = import_batch(batch(), CATALOG, PACKET_HASH)
    with pytest.raises(ValueError, match="later timestamp"):
        import_batch(batch(decision="unrelated"), CATALOG, PACKET_HASH, first, PARENT_HASH)
    later = batch(decision="needs_reference", time="2026-09-14T13:00:00+05:00")
    second, _ = import_batch(later, CATALOG, PACKET_HASH, first, PARENT_HASH)
    assert second["batches"][0] == batch()
    assert (
        next(s for s in second["states"] if s["case_id"] == "near-1")["status"] == "needs_reference"
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(packet_sha256="c" * 64),
        lambda b: b.update(reviewer=" "),
        lambda b: b.update(reviewed_at="2026-09-14T12:00:00"),
        lambda b: b.update(ready_for_training=True),
        lambda b: b.update(decisions=[]),
        lambda b: b["decisions"].append(copy.deepcopy(b["decisions"][0])),
        lambda b: b["decisions"][0].update(case_id="unknown"),
        lambda b: b["decisions"][0].update(rationale=""),
        lambda b: b["decisions"][0].update(answers={"relationship": None}),
        lambda b: b["decisions"][0].update(answers={"correction": "accept"}),
        lambda b: b["decisions"][0].update(answers={"relationship": True}),
    ],
)
def test_rejects_malformed_or_unbound_decisions(mutate):
    value = batch()
    mutate(value)
    with pytest.raises(ValueError):
        validate_batch(value, CATALOG, PACKET_HASH)


def test_blank_template_is_not_an_expert_decision():
    value = template(CATALOG, PACKET_HASH)
    with pytest.raises(ValueError):
        validate_batch(value, CATALOG, PACKET_HASH)


def test_ledger_tampering_and_resigned_state_mismatch_are_rejected():
    ledger, _ = import_batch(batch(), CATALOG, PACKET_HASH)
    ledger["states"][0]["status"] = "recorded"
    with pytest.raises(ValueError, match="content hash"):
        import_batch(batch("Expert B"), CATALOG, PACKET_HASH, ledger, PARENT_HASH)
    ledger["content_sha256"] = content_hash(
        {k: v for k, v in ledger.items() if k != "content_sha256"}
    )
    with pytest.raises(ValueError, match="reproduce history"):
        import_batch(batch("Expert B"), CATALOG, PACKET_HASH, ledger, PARENT_HASH)


def test_previous_ledger_requires_parent_file_hash():
    first, _ = import_batch(batch(), CATALOG, PACKET_HASH)
    with pytest.raises(ValueError, match="file hash"):
        import_batch(batch("Expert B"), CATALOG, PACKET_HASH, first)


def test_rejects_json_duplicate_keys_nonfinite_and_oversize(tmp_path):
    path = tmp_path / "x.json"
    for text in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}']:
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            read_json(path)
    path.write_text('"long"', encoding="utf-8")
    with pytest.raises(ValueError, match="size limit"):
        read_json(path, limit=2)


def test_packet_must_match_committed_summary(tmp_path):
    packet = {
        "schema_version": "1.0",
        "source": "DsPCBSD+",
        "status": "unreviewed_candidate",
        "ready_for_training": False,
        "production_eligible": False,
        "binding": {"inventory_sha256": "c" * 64},
        "review": {
            "pair_cases": [],
            "near_duplicate_cases": [],
            "border_corrections": [],
            "class_definitions": [],
        },
    }
    path = tmp_path / "packet.json"
    summary_path = tmp_path / "summary.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    summary_path.write_text(
        json.dumps(
            {
                "packet_sha256": digest(path),
                "source": packet["source"],
                "binding": packet["binding"],
            }
        ),
        encoding="utf-8",
    )
    assert len(load_packet(path, summary_path)[1]) == 2
    packet["ready_for_training"] = True
    path.write_text(json.dumps(packet), encoding="utf-8")
    with pytest.raises(ValueError, match="Packet hash"):
        load_packet(path, summary_path)


def test_source_class_review_cannot_silently_remap_labels():
    catalog = {"class-1": {"kind": "class", "subject": {}}}
    value = batch()
    value["decisions"][0].update(case_id="class-1", answers={"definition": "missing_pad"})
    with pytest.raises(ValueError, match="Invalid"):
        validate_batch(value, catalog, PACKET_HASH)


def test_cli_invalid_import_creates_no_output(monkeypatch, tmp_path):
    from ml import candidate_decisions as module

    monkeypatch.setattr(module, "load_packet", lambda *args: ({}, CATALOG, PACKET_HASH))
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps(template(CATALOG, PACKET_HASH)), encoding="utf-8")
    output = tmp_path / "rejected"
    monkeypatch.setattr(
        "sys.argv",
        [
            "candidate_decisions",
            "import",
            "--packet",
            "unused",
            "--summary",
            "unused",
            "--decisions",
            str(decisions),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(ValueError):
        module.main()
    assert not output.exists()


def test_cli_reimport_creates_no_revision_and_never_overwrites(monkeypatch, tmp_path):
    from ml import candidate_decisions as module

    monkeypatch.setattr(module, "load_packet", lambda *args: ({}, CATALOG, PACKET_HASH))
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps(batch()), encoding="utf-8")
    first = tmp_path / "revision-1"
    args = [
        "candidate_decisions",
        "import",
        "--packet",
        "unused",
        "--summary",
        "unused",
        "--decisions",
        str(decisions),
        "--output",
        str(first),
    ]
    monkeypatch.setattr("sys.argv", args)
    module.main()
    original = (first / "ledger.json").read_bytes()
    with pytest.raises(ValueError, match="Output exists"):
        module.main()
    second = tmp_path / "revision-2"
    monkeypatch.setattr(
        "sys.argv", args[:-1] + [str(second), "--previous", str(first / "ledger.json")]
    )
    module.main()
    assert not second.exists()
    assert (first / "ledger.json").read_bytes() == original
