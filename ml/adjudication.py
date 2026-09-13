"""Import bound review notes, record human decisions, and emit unapproved dataset candidates."""

import argparse
import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from ml.data import file_hash
from ml.review import build_payload
from pcb_inspector.datasets import DatasetManifest

BINDINGS = (
    "run",
    "checkpoint_sha256",
    "manifest_sha256",
    "prediction_sha256",
    "matching_code_sha256",
)
MAX_BYTES = 2_000_000
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Text = Annotated[str, Field(min_length=1, max_length=200, pattern=r".*\S.*")]
Kind = Literal["annotation", "prediction"]
Action = Literal[
    "keep_label",
    "correct_label",
    "remove_label",
    "add_label",
    "dismiss_prediction",
    "needs_reference",
]


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Review timestamps must include a timezone")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Note(Strict):
    image: Text
    source_sha256: Hash
    group: Text
    subject_kind: Kind
    annotation_index: StrictInt | None = None
    annotation: dict | None = None
    prediction_index: StrictInt | None = None
    prediction: dict | None = None
    overlap_context: dict | None = None
    assessment: Literal["unreviewed", "looks_consistent", "needs_expert_review", "unclear"]
    note: str = Field(max_length=4000)
    score_threshold: Literal[0.05, 0.25, 0.5]
    updated_at: str

    _time = field_validator("updated_at")(timestamp)


class Notes(Strict):
    schema_version: Literal["1.1"]
    purpose: Literal["Review notes only; no dataset changes"]
    run: Text
    checkpoint_sha256: Hash
    manifest_sha256: Hash
    prediction_sha256: Hash
    matching_code_sha256: Hash
    exported_at: str
    notes: list[Note] = Field(max_length=5000)

    _time = field_validator("exported_at")(timestamp)


class Replacement(Strict):
    class_id: StrictInt = Field(ge=0)
    xyxy: list[float] = Field(min_length=4, max_length=4)


class Resolution(Strict):
    case_id: Hash
    action: Action
    rationale: str = Field(min_length=1, max_length=4000, pattern=r".*\S.*")
    annotation: Replacement | None = None


class Decisions(Strict):
    schema_version: Literal["1.0"]
    adjudicator: Text
    reviewed_at: str
    decisions: list[Resolution] = Field(min_length=1, max_length=5000)

    _time = field_validator("reviewed_at")(timestamp)


class Observation(Strict):
    reviewer: Text
    source_notes_sha256: Hash
    note: Note


class Decision(Resolution):
    adjudicator: Text
    reviewed_at: str
    observation_count: StrictInt = Field(gt=0)
    observations_sha256: Hash

    _time = field_validator("reviewed_at")(timestamp)


class Case(Strict):
    case_id: Hash
    image: Text
    subject_kind: Kind
    subject_index: StrictInt = Field(ge=0)
    observations: list[Observation] = Field(min_length=1)
    decisions: list[Decision] = Field(default_factory=list)


class Ledger(Strict):
    schema_version: Literal["1.0"] = "1.0"
    version: StrictInt = Field(gt=0)
    parent_sha256: Hash | None = None
    binding: dict[str, str]
    cases: list[Case]
    purpose: Literal["Human review record; not expert certification or dataset approval"] = (
        "Human review record; not expert certification or dataset approval"
    )


def canonical(value):
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def same(a, b):
    """JSON equality with numeric parity (1 == 1.0), but never True == 1."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    return a == b


def binding(context):
    return {key: context[key] for key in BINDINGS}


def note_key(note):
    index = note.annotation_index if note.subject_kind == "annotation" else note.prediction_index
    return note.image, note.subject_kind, index


def case_id(context, key):
    return digest({"binding": binding(context), "subject": key})


def validate_note(note, context):
    boards = {b["image"]: b for b in context["boards"]}
    board = boards.get(note.image)
    if not board or note.source_sha256 != board["source_sha256"] or note.group != board["group"]:
        raise ValueError("Note source image/hash/group differs from validation review")
    kind = note.subject_kind
    index = note_key(note)[2]
    rows = board["annotations" if kind == "annotation" else "predictions"]
    if type(index) is not int or not 0 <= index < len(rows):
        raise ValueError("Note subject index is outside the original source")
    if kind == "annotation":
        if any(
            v is not None for v in [note.prediction_index, note.prediction, note.overlap_context]
        ):
            raise ValueError("Annotation note contains prediction fields")
        expected = rows[index]
        if not same(note.annotation, expected):
            raise ValueError("Note annotation differs from original source")
    else:
        if note.annotation_index is not None or note.annotation is not None:
            raise ValueError("Prediction note contains annotation fields")
        if not same(note.prediction, rows[index]):
            raise ValueError("Note prediction differs from original source")
        matches = board["profiles"][str(note.score_threshold)]["prediction_matches"]
        match = next((m for m in matches if m["prediction_index"] == index), None)
        if match is None or match["outcome"] == "matched" or not same(note.overlap_context, match):
            raise ValueError("Note overlap context/threshold differs from false-positive review")
    return board


def validate_notes(notes, context):
    if any(getattr(notes, key) != context[key] for key in BINDINGS):
        raise ValueError(
            "Notes belong to another run, checkpoint, manifest, predictions or matcher"
        )
    keys = set()
    for note in notes.notes:
        validate_note(note, context)
        key = note_key(note)
        if key in keys:
            raise ValueError("Duplicate subject in notes export")
        keys.add(key)


def validate_resolution(resolution, case, context):
    allowed = (
        {"keep_label", "correct_label", "remove_label", "needs_reference"}
        if case.subject_kind == "annotation"
        else {"add_label", "dismiss_prediction", "needs_reference"}
    )
    if resolution.action not in allowed:
        raise ValueError("Decision action does not apply to this subject kind")
    correction = resolution.annotation
    if (resolution.action in {"correct_label", "add_label"}) != (correction is not None):
        raise ValueError(
            "Add/correct decisions require an explicit annotation, other actions forbid it"
        )
    if correction:
        b = next(b for b in context["boards"] if b["image"] == case.image)
        x1, y1, x2, y2 = correction.xyxy
        if not (
            correction.class_id < len(context["classes"])
            and all(math.isfinite(x) for x in correction.xyxy)
            and 0 <= x1 < x2 <= b["width"]
            and 0 <= y1 < y2 <= b["height"]
        ):
            raise ValueError("Corrected annotation class or bounds are invalid")


def validate_ledger(ledger, context):
    if ledger.binding != binding(context):
        raise ValueError("Ledger belongs to another review")
    if (ledger.version == 1) != (ledger.parent_sha256 is None):
        raise ValueError("Ledger version/parent contract is invalid")
    seen = set()
    for case in ledger.cases:
        key = (case.image, case.subject_kind, case.subject_index)
        if case.case_id != case_id(context, key) or case.case_id in seen:
            raise ValueError("Invalid or duplicate case identity")
        seen.add(case.case_id)
        for obs in case.observations:
            validate_note(obs.note, context)
            if note_key(obs.note) != key:
                raise ValueError("Observation differs from case subject")
        for decision in case.decisions:
            count = decision.observation_count
            if (
                decision.case_id != case.case_id
                or count > len(case.observations)
                or decision.observations_sha256
                != digest(
                    [
                        o.model_dump(mode="json", exclude_none=True)
                        for o in case.observations[:count]
                    ]
                )
            ):
                raise ValueError("Decision does not bind its observed notes")
            validate_resolution(decision, case, context)


def import_notes(notes, reviewer, source_hash, context, previous=None, parent_hash=None):
    validate_notes(notes, context)
    if not reviewer.strip():
        raise ValueError("Reviewer identity is required")
    if previous:
        validate_ledger(previous, context)
    ledger = Ledger(
        version=previous.version + 1 if previous else 1,
        parent_sha256=parent_hash,
        binding=binding(context),
        cases=deepcopy(previous.cases) if previous else [],
    )
    cases = {case.case_id: case for case in ledger.cases}
    added = 0
    for note in notes.notes:
        identity = case_id(context, note_key(note))
        obs = Observation(reviewer=reviewer, source_notes_sha256=source_hash, note=note)
        case = cases.get(identity)
        if case is None:
            image, kind, index = note_key(note)
            case = Case(
                case_id=identity,
                image=image,
                subject_kind=kind,
                subject_index=index,
                observations=[obs],
            )
            ledger.cases.append(case)
            cases[identity] = case
            added += 1
        elif not any(
            o.reviewer == reviewer and same(o.note.model_dump(), note.model_dump())
            for o in case.observations
        ):
            case.observations.append(obs)
            added += 1
    if not added:
        raise ValueError("No new observations; repeated imports are idempotent")
    validate_ledger(ledger, context)
    return ledger


def adjudicate(previous, parent_hash, decisions, context):
    validate_ledger(previous, context)
    ledger = previous.model_copy(
        deep=True,
        update={
            "version": previous.version + 1,
            "parent_sha256": parent_hash,
        },
    )
    cases = {case.case_id: case for case in ledger.cases}
    seen = set()
    for resolution in decisions.decisions:
        if resolution.case_id not in cases or resolution.case_id in seen:
            raise ValueError("Unknown or duplicate decision case")
        seen.add(resolution.case_id)
        case = cases[resolution.case_id]
        validate_resolution(resolution, case, context)
        observations = [o.model_dump(mode="json", exclude_none=True) for o in case.observations]
        case.decisions.append(
            Decision(
                **resolution.model_dump(),
                adjudicator=decisions.adjudicator,
                reviewed_at=decisions.reviewed_at,
                observation_count=len(observations),
                observations_sha256=digest(observations),
            )
        )
    validate_ledger(ledger, context)
    return ledger


def status(case):
    if not case.decisions or case.decisions[-1].observation_count != len(case.observations):
        return "pending"
    return "needs_reference" if case.decisions[-1].action == "needs_reference" else "resolved"


def candidate(ledger, context, manifest, version):
    validate_ledger(ledger, context)
    if not ledger.cases or any(status(case) != "resolved" for case in ledger.cases):
        raise ValueError("All cases must have current resolved human decisions")
    if not version.strip() or version == manifest.version:
        raise ValueError("Candidate requires a distinct nonblank dataset version")
    if manifest.classes != context["classes"]:
        raise ValueError("Candidate class map differs from review")
    originals = {sample.image: sample for sample in manifest.samples}
    for board in context["boards"]:
        sample = originals.get(board["image"])
        if sample is None or (
            sample.split != "validation"
            or sample.sha256 != board["source_sha256"]
            or sample.group_id != board["group"]
            or sample.width != board["width"]
            or sample.height != board["height"]
        ):
            raise ValueError("Candidate source differs from reviewed validation image")
        truth = [
            {
                "category_id": ann.class_id + 1,
                "bbox": [
                    ann.bbox.x1,
                    ann.bbox.y1,
                    ann.bbox.x2 - ann.bbox.x1,
                    ann.bbox.y2 - ann.bbox.y1,
                ],
            }
            for ann in sample.annotations
        ]
        if not same(truth, board["annotations"]):
            raise ValueError("Candidate annotations differ from reviewed source")
    result = manifest.model_dump(mode="json")
    result["version"] = version
    samples = {s["image"]: s for s in result["samples"]}
    edits, additions, changes = {}, {}, []
    for case in ledger.cases:
        decision = case.decisions[-1]
        if decision.action in {"keep_label", "dismiss_prediction"}:
            continue
        sample = samples[case.image]
        if sample["split"] != "validation":
            raise ValueError("Correction lies outside the reviewed validation split")
        replacement = None
        if decision.annotation:
            x1, y1, x2, y2 = decision.annotation.xyxy
            replacement = {
                "class_id": decision.annotation.class_id,
                "bbox": dict(x1=x1, y1=y1, x2=x2, y2=y2),
            }
        before = None
        if decision.action == "add_label":
            additions.setdefault(case.image, []).append(replacement)
        else:
            before = deepcopy(sample["annotations"][case.subject_index])
            if same(before, replacement):
                raise ValueError("Correction does not change the annotation")
            edits[(case.image, case.subject_index)] = replacement
        changes.append(
            {
                "case_id": case.case_id,
                "image": case.image,
                "action": decision.action,
                "before": before,
                "after": replacement,
                "decision": decision.model_dump(mode="json", exclude_none=True),
            }
        )
    if not changes:
        raise ValueError("No annotation corrections to version")
    for sample in result["samples"]:
        updated = [
            edits.get((sample["image"], i), a) for i, a in enumerate(sample["annotations"])
        ] + additions.get(sample["image"], [])
        sample["annotations"] = [a for a in updated if a is not None]
        encoded = [canonical(a) for a in sample["annotations"]]
        if len(set(encoded)) != len(encoded):
            raise ValueError("Candidate contains duplicate annotations")
    DatasetManifest.model_validate(result)
    return result, changes


def read_json(path, limit=MAX_BYTES):
    if Path(path).stat().st_size > limit:
        raise ValueError("Input exceeds size limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=unique,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
    )


def load_ledger(path, context):
    wrapped = read_json(path, 20_000_000)
    if set(wrapped) != {"content", "sha256"} or digest(wrapped["content"]) != wrapped["sha256"]:
        raise ValueError("Ledger checksum mismatch")
    ledger = Ledger.model_validate(wrapped["content"])
    validate_ledger(ledger, context)
    return ledger


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["import", "adjudicate", "candidate"])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/pcb-defect-v1.0.json")
    )
    parser.add_argument("--root", type=Path, default=Path("data/processed/pcb-defect-v1"))
    parser.add_argument("--release", type=Path, default=Path("data/releases/pcb-defect-v1"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--reviewer")
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("Output exists; choose a new immutable revision directory")
    context = build_payload(args)
    previous = load_ledger(args.previous, context) if args.previous else None
    parent_hash = file_hash(args.previous) if args.previous else None
    if args.action == "import":
        if not args.notes or not args.reviewer:
            parser.error("Import requires --notes and --reviewer")
        ledger = import_notes(
            Notes.model_validate(read_json(args.notes)),
            args.reviewer,
            file_hash(args.notes),
            context,
            previous,
            parent_hash,
        )
    elif args.action == "adjudicate":
        if previous is None or not args.decisions:
            parser.error("Adjudication requires --previous and --decisions")
        ledger = adjudicate(
            previous, parent_hash, Decisions.model_validate(read_json(args.decisions)), context
        )
    else:
        if previous is None or not args.version:
            parser.error("Candidate requires --previous and --version")
        if file_hash(args.manifest) != context["manifest_sha256"]:
            raise ValueError("Manifest changed after review verification")
        manifest = DatasetManifest.model_validate_json(args.manifest.read_bytes())
        result, changes = candidate(previous, context, manifest, args.version)
        args.output.mkdir(parents=True)
        write_json(args.output / "candidate-manifest.json", result)
        write_json(
            args.output / "corrections.json",
            {
                "schema_version": "1.0",
                "parent_manifest_sha256": context["manifest_sha256"],
                "candidate_manifest_sha256": file_hash(args.output / "candidate-manifest.json"),
                "ledger_sha256": parent_hash,
                "changes": changes,
                "ready_for_training": False,
                "promotion_eligible": False,
                "status": "candidate_requires_independent_validation_and_release_review",
                "test_split_changed": False,
            },
        )
        print(f"Unapproved candidate written: {args.output}")
        return
    args.output.mkdir(parents=True)
    content = ledger.model_dump(mode="json", exclude_none=True)
    write_json(args.output / "ledger.json", {"content": content, "sha256": digest(content)})
    write_json(
        args.output / "decisions-template.json",
        {
            "schema_version": "1.0",
            "adjudicator": "",
            "reviewed_at": "",
            "decisions": [
                {"case_id": c.case_id, "action": "needs_reference", "rationale": ""}
                for c in ledger.cases
                if status(c) != "resolved"
            ],
        },
    )
    print(
        json.dumps(
            {
                "version": ledger.version,
                "cases": {
                    s: sum(status(c) == s for c in ledger.cases)
                    for s in ["pending", "needs_reference", "resolved"]
                },
            }
        )
    )


if __name__ == "__main__":
    main()
