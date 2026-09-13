# Review-note import and annotation adjudication

This workflow restores exported notes, retains reviewer disagreements, and prepares
versioned annotation correction candidates. Notes are observations, not expert
certification. The frozen source release and test holdout remain unchanged.

## Restore notes in the viewer

Generate a fresh package with python -m ml.review, then use **Import exported notes**.
Schema 1.1 exports are supported, including the earlier false-positive viewer exports.
Imports check model/data/prediction/matcher hashes, original image/group, subject indices,
boxes and overlap context at the recorded diagnostic threshold. Identical notes are
idempotent; conflicting notes reject the whole import. Keep conflicting reviewer exports
separate for the adjudication ledger. Save a current draft before importing. Import is
limited to 2 MB / 5,000 notes / 4,000 characters per note.

Notes stay in page memory. Export before closing or reloading. Annotation and prediction
notes remain separate even when their numeric indices collide.

## Import observations into an immutable ledger

Use the real reviewer's name or identifier, not the tool operator's name by default:

```powershell
.venv/Scripts/python.exe -m ml.adjudication import --run ml/runs/coco-tiles1536-rpn0-epoch1 --notes path/to/reviewer-notes.json --reviewer "Reviewer identifier" --output ml/runs/adjudication-001
```

For another reviewer or updated observations, add --previous pointing to the prior
ledger.json and choose a new output directory. A repeated identical import makes no new
revision. Conflicting observations are retained, not replaced. Each revision records its
parent file hash and a checksum of its content; preserve all revision directories.

Case identity binds the review model/data/predictions plus image, subject kind and original
index. Reviewers are self-reported identifiers, not authenticated expert credentials.
The ledger is a local audit trail, not a signature or access-control system.

## Record a human decision

Every revision contains ledger.json (original observations and decision history) and
decisions-template.json. Fill in the actual adjudicator, timezone-qualified reviewed_at,
case actions and rationales. Blank templates deliberately fail validation. Decision actions:

| Subject | Actions |
| --- | --- |
| Existing annotation | keep_label, correct_label, remove_label, needs_reference |
| False-positive prediction | add_label, dismiss_prediction, needs_reference |

Adding or correcting a label requires an explicit annotation object:

```json
{
  "case_id": "copy the full case ID from the ledger",
  "action": "correct_label",
  "rationale": "Describe the actual expert/reference evidence",
  "annotation": {"class_id": 0, "xyxy": [10, 20, 30, 40]}
}
```

class_id uses the **zero-based dataset class map**. xyxy is original-image pixels,
not COCO xywh or resized coordinates. All other actions omit annotation. Predictions
are never automatically copied into labels. A needs_reference decision remains unresolved.

```powershell
.venv/Scripts/python.exe -m ml.adjudication adjudicate --run ml/runs/coco-tiles1536-rpn0-epoch1 --previous ml/runs/adjudication-001/ledger.json --decisions path/to/completed-decisions.json --output ml/runs/adjudication-002
```

Each decision binds every observation seen at that time. New observations reopen its case
until a human resolves the expanded evidence. Previous decisions stay in history.

## Prepare a separate candidate version

Only after all cases have current resolved human decisions:

```powershell
.venv/Scripts/python.exe -m ml.adjudication candidate --run ml/runs/coco-tiles1536-rpn0-epoch1 --previous ml/runs/adjudication-002/ledger.json --version 1.0.1-review-candidate --output ml/runs/dataset-candidate-001
```

The output contains candidate-manifest.json and corrections.json, binding the original
manifest, ledger, candidate bytes, case IDs, decisions and before/after labels.
This initial workflow only corrects the validation subjects exposed by the existing viewer.
It preserves all source images, group/split assignments, class maps and train/test labels.
Empty/reversed/out-of-bounds boxes, unknown classes, duplicate annotations, unresolved cases,
stale decisions, unchanged versions and overwriting output directories are rejected.

A candidate has ready_for_training=false and is not a new frozen release. It needs the
existing full integrity/leakage/license checks and independent release review. Historical
model metrics stay bound to the old manifest; corrected validation labels require a new
explicitly named evaluation protocol. Do not reuse old metrics as scores on the candidate.

No actual dataset correction is made merely by running the viewer or importing notes.
The generated local package review-adjudication-001 and adjudication-import-smoke-001 use
clearly labeled automated test notes; they contain no expert decisions.

## Remaining qualification work

Arrange expert annotation-completeness review, clean-board negatives, and an independent
camera-image holdout with rights and grouping provenance. Record camera/domain conditions
and source lineage before selecting splits. Do not reclassify existing boards as clean or
claim review coverage from a small set of prediction-driven cases. Operating thresholds,
final-test authorization, model promotion and production inference remain separate gates.
