import json
from copy import deepcopy

import pytest

from ml import adjudication as a
from ml.review import build_boards
from pcb_inspector.datasets import DatasetManifest


@pytest.fixture
def source():
    sample = {
        "image": "validation.jpg",
        "sha256": "a" * 64,
        "width": 100,
        "height": 80,
        "group_id": "validation-family",
        "split": "validation",
        "annotations": [{"class_id": 0, "bbox": {"x1": 10, "y1": 20, "x2": 30, "y2": 40}}],
    }
    manifest = DatasetManifest.model_validate(
        {
            "name": "fixture",
            "version": "1.0",
            "source_url": "https://example.org/data",
            "source_revision": "fixture",
            "classes": ["spur", "mouse_bite"],
            "license": {
                "name": "fixture",
                "evidence": "license.txt",
                "allowed_uses": ["research"],
                "reviewed_by": "Fixture reviewer",
                "reviewed_on": "2026-01-01",
            },
            "samples": [
                sample,
                {**sample, "image": "train.jpg", "split": "train", "group_id": "train"},
                {**sample, "image": "test.jpg", "split": "test", "group_id": "test"},
            ],
        }
    )
    predictions = [{"image_id": 0, "category_id": 1, "bbox": [70, 60, 10, 10], "score": 0.8}]
    context = {
        "run": "fixture",
        "checkpoint_sha256": "b" * 64,
        "manifest_sha256": "c" * 64,
        "prediction_sha256": "d" * 64,
        "matching_code_sha256": "e" * 64,
        "classes": manifest.classes,
        "boards": build_boards([manifest.samples[0]], manifest.classes, predictions),
    }
    return manifest, context


def note_document(context, *, both=True):
    board = context["boards"][0]
    common = {
        "image": board["image"],
        "source_sha256": board["source_sha256"],
        "group": board["group"],
        "assessment": "needs_expert_review",
        "note": "Synthetic test observation.",
        "score_threshold": 0.25,
        "updated_at": "2026-09-13T00:00:00Z",
    }
    notes = [
        {
            **common,
            "subject_kind": "annotation",
            "annotation_index": 0,
            "annotation": board["annotations"][0],
        },
        {
            **common,
            "subject_kind": "prediction",
            "prediction_index": 0,
            "prediction": board["predictions"][0],
            "overlap_context": board["profiles"]["0.25"]["prediction_matches"][0],
        },
    ]
    return {
        "schema_version": "1.1",
        "purpose": "Review notes only; no dataset changes",
        **a.binding(context),
        "exported_at": "2026-09-13T00:00:00Z",
        "notes": deepcopy(notes if both else notes[:1]),
    }


def imported(context, *, both=True):
    return a.import_notes(
        a.Notes.model_validate(note_document(context, both=both)),
        "Fixture reviewer",
        "f" * 64,
        context,
    )


def decisions(ledger):
    return a.Decisions.model_validate(
        {
            "schema_version": "1.0",
            "adjudicator": "Fixture adjudicator",
            "reviewed_at": "2026-09-13T01:00:00Z",
            "decisions": [
                {
                    "case_id": case.case_id,
                    "action": "correct_label" if case.subject_kind == "annotation" else "add_label",
                    "rationale": "Synthetic correction for a regression test.",
                    "annotation": {
                        "class_id": 1,
                        "xyxy": [11, 21, 31, 41]
                        if case.subject_kind == "annotation"
                        else [70, 60, 80, 70],
                    },
                }
                for case in ledger.cases
            ],
        }
    )


def test_bound_import_isolated_subjects_and_idempotence(source):
    _, ctx = source
    ledger = imported(ctx)
    assert len(ledger.cases) == 2
    assert ledger.cases[0].case_id != ledger.cases[1].case_id
    assert all(a.status(c) == "pending" for c in ledger.cases)
    with pytest.raises(ValueError, match="No new"):
        a.import_notes(
            a.Notes.model_validate(note_document(ctx)),
            "Fixture reviewer",
            "f" * 64,
            ctx,
            ledger,
            "1" * 64,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "manifest",
        "checkpoint",
        "matcher",
        "predictions",
        "run",
        "source",
        "group",
        "image",
        "box",
        "index",
        "boolean_index",
        "boolean_box",
        "overlap",
        "threshold",
        "duplicate",
        "extra_fields",
        "nonfinite",
        "unknown_schema",
        "unknown_assessment",
        "timestamp",
    ],
)
def test_notes_reject_corrupt_or_unbound_imports(source, mutation):
    _, ctx = source
    doc = note_document(ctx)
    first, pred = doc["notes"]
    if mutation in ["manifest", "checkpoint", "matcher", "predictions", "run"]:
        key = {
            "manifest": "manifest_sha256",
            "checkpoint": "checkpoint_sha256",
            "matcher": "matching_code_sha256",
            "predictions": "prediction_sha256",
            "run": "run",
        }[mutation]
        doc[key] = "0" * 64
    elif mutation == "source":
        first["source_sha256"] = "0" * 64
    elif mutation == "group":
        first["group"] = "other"
    elif mutation == "image":
        first["image"] = "test.jpg"
    elif mutation == "box":
        first["annotation"]["bbox"][0] += 1
    elif mutation == "index":
        first["annotation_index"] = -1
    elif mutation == "boolean_index":
        first["annotation_index"] = False
    elif mutation == "boolean_box":
        pred["prediction"]["category_id"] = True
    elif mutation == "overlap":
        pred["overlap_context"]["outcome"] = "duplicate"
    elif mutation == "threshold":
        pred["score_threshold"] = 0.9
    elif mutation == "duplicate":
        doc["notes"].append(deepcopy(first))
    elif mutation == "extra_fields":
        first["prediction_index"] = 0
    elif mutation == "nonfinite":
        first["annotation"]["bbox"][0] = float("nan")
    elif mutation == "unknown_schema":
        doc["schema_version"] = "1.0"
    elif mutation == "unknown_assessment":
        first["assessment"] = "expert_certified"
    elif mutation == "timestamp":
        first["updated_at"] = "yesterday"
    with pytest.raises(ValueError):
        a.validate_notes(a.Notes.model_validate(doc), ctx)


def test_conflicting_observations_reopen_resolved_cases_without_erasing_decisions(source):
    _, ctx = source
    first = imported(ctx, both=False)
    resolved = a.adjudicate(first, "1" * 64, decisions(first), ctx)
    assert a.status(resolved.cases[0]) == "resolved"
    assert first.cases[0].decisions == []
    doc = note_document(ctx, both=False)
    doc["notes"][0]["note"] = "Conflicting synthetic observation."
    next_ledger = a.import_notes(
        a.Notes.model_validate(doc), "Another fixture reviewer", "2" * 64, ctx, resolved, "3" * 64
    )
    assert len(next_ledger.cases[0].observations) == 2
    assert len(next_ledger.cases[0].decisions) == 1
    assert a.status(next_ledger.cases[0]) == "pending"
    with pytest.raises(ValueError, match="current resolved"):
        a.candidate(next_ledger, ctx, source[0], "1.1")


def test_candidate_has_explicit_human_corrections_and_preserves_other_splits(source):
    manifest, ctx = source
    original = manifest.model_dump(mode="json")
    ledger = imported(ctx)
    resolved = a.adjudicate(ledger, "1" * 64, decisions(ledger), ctx)
    candidate, changes = a.candidate(resolved, ctx, manifest, "1.1-candidate")
    assert manifest.model_dump(mode="json") == original
    assert candidate["samples"][1:] == original["samples"][1:]
    assert candidate["classes"] == original["classes"]
    assert candidate["samples"][0]["annotations"] == [
        {"class_id": 1, "bbox": {"x1": 11, "y1": 21, "x2": 31, "y2": 41}},
        {"class_id": 1, "bbox": {"x1": 70, "y1": 60, "x2": 80, "y2": 70}},
    ]
    assert {c["action"] for c in changes} == {"correct_label", "add_label"}
    assert all(c["decision"]["adjudicator"] == "Fixture adjudicator" for c in changes)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_annotation",
        "bounds",
        "class",
        "nonfinite",
        "wrong_action",
        "blank_reviewer",
        "blank_reason",
        "duplicate_case",
        "unknown_case",
    ],
)
def test_adjudication_rejects_invalid_human_decisions(source, mutation):
    _, ctx = source
    ledger = imported(ctx)
    doc = decisions(ledger).model_dump(mode="json")
    item = doc["decisions"][0]
    if mutation == "missing_annotation":
        item["annotation"] = None
    elif mutation == "bounds":
        item["annotation"]["xyxy"] = [0, 0, 101, 80]
    elif mutation == "class":
        item["annotation"]["class_id"] = 2
    elif mutation == "nonfinite":
        item["annotation"]["xyxy"][0] = float("inf")
    elif mutation == "wrong_action":
        item["action"] = "add_label"
    elif mutation == "blank_reviewer":
        doc["adjudicator"] = " "
    elif mutation == "blank_reason":
        item["rationale"] = ""
    elif mutation == "duplicate_case":
        doc["decisions"].append(deepcopy(item))
    elif mutation == "unknown_case":
        item["case_id"] = "0" * 64
    with pytest.raises(ValueError):
        a.adjudicate(ledger, "1" * 64, a.Decisions.model_validate(doc), ctx)


def test_remove_labels_uses_original_indices_and_needs_reference_blocks_release(source):
    manifest, ctx = source
    ledger = imported(ctx, both=False)
    doc = decisions(ledger).model_dump(mode="json")
    doc["decisions"][0].update(action="needs_reference", annotation=None)
    unresolved = a.adjudicate(ledger, "1" * 64, a.Decisions.model_validate(doc), ctx)
    with pytest.raises(ValueError, match="resolved"):
        a.candidate(unresolved, ctx, manifest, "1.1")
    doc["decisions"][0]["action"] = "remove_label"
    resolved = a.adjudicate(unresolved, "2" * 64, a.Decisions.model_validate(doc), ctx)
    value, _ = a.candidate(resolved, ctx, manifest, "1.1")
    assert value["samples"][0]["annotations"] == []
    assert len(resolved.cases[0].decisions) == 2


def test_ledger_hash_and_observation_binding_reject_tampering(source, tmp_path):
    _, ctx = source
    ledger = imported(ctx)
    resolved = a.adjudicate(ledger, "1" * 64, decisions(ledger), ctx)
    content = resolved.model_dump(mode="json", exclude_none=True)
    path = tmp_path / "ledger.json"
    a.write_json(path, {"content": content, "sha256": a.digest(content)})
    assert a.load_ledger(path, ctx).version == 2
    wrapped = a.read_json(path)
    wrapped["content"]["cases"][0]["observations"][0]["note"]["note"] = "Tampered"
    path.write_text(json.dumps(wrapped), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        a.load_ledger(path, ctx)
    wrapped["sha256"] = a.digest(wrapped["content"])
    path.write_text(json.dumps(wrapped), encoding="utf-8")
    with pytest.raises(ValueError, match="observed notes"):
        a.load_ledger(path, ctx)


def test_cli_import_adjudicate_candidate_and_refuse_overwrite(source, monkeypatch, tmp_path):
    manifest, ctx = source
    manifest_path = tmp_path / "manifest.json"
    a.write_json(manifest_path, manifest.model_dump(mode="json"))
    ctx["manifest_sha256"] = a.file_hash(manifest_path)
    monkeypatch.setattr(a, "build_payload", lambda args: ctx)
    notes = tmp_path / "notes.json"
    a.write_json(notes, note_document(ctx))
    common = ["--run", str(tmp_path / "run"), "--manifest", str(manifest_path)]
    first = tmp_path / "v1"
    a.main(
        [
            "import",
            *common,
            "--notes",
            str(notes),
            "--reviewer",
            "Fixture reviewer",
            "--output",
            str(first),
        ]
    )
    before = (first / "ledger.json").read_bytes()
    ledger = a.load_ledger(first / "ledger.json", ctx)
    decision_path = tmp_path / "decisions.json"
    a.write_json(decision_path, decisions(ledger).model_dump(mode="json"))
    second = tmp_path / "v2"
    a.main(
        [
            "adjudicate",
            *common,
            "--previous",
            str(first / "ledger.json"),
            "--decisions",
            str(decision_path),
            "--output",
            str(second),
        ]
    )
    output = tmp_path / "candidate"
    a.main(
        [
            "candidate",
            *common,
            "--previous",
            str(second / "ledger.json"),
            "--version",
            "1.1-review",
            "--output",
            str(output),
        ]
    )
    provenance = a.read_json(output / "corrections.json")
    assert provenance["ready_for_training"] is False
    assert provenance["test_split_changed"] is False
    assert provenance["parent_manifest_sha256"] == a.file_hash(manifest_path)
    assert (first / "ledger.json").read_bytes() == before
    with pytest.raises(ValueError, match="Output exists"):
        a.main(["import", *common, "--output", str(first)])


def test_bounded_json_rejects_duplicate_keys_and_nonfinite_values(tmp_path):
    path = tmp_path / "bad.json"
    for raw in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}']:
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(ValueError):
            a.read_json(path)
    with pytest.raises(ValueError, match="size"):
        a.read_json(path, 1)


@pytest.mark.parametrize("mutation", ["split", "annotation", "class"])
def test_candidate_rejects_changed_source_contract(source, mutation):
    manifest, context = source
    ledger = imported(context)
    resolved = a.adjudicate(ledger, "1" * 64, decisions(ledger), context)
    changed = manifest.model_copy(deep=True)
    if mutation == "split":
        changed.samples[0].split = "test"
    elif mutation == "annotation":
        ann = changed.samples[0].annotations[0]
        ann.bbox = ann.bbox.model_copy(update={"x1": 12})
    else:
        changed.classes.reverse()
    with pytest.raises(ValueError, match="differs|differ"):
        a.candidate(resolved, context, changed, "1.1")
