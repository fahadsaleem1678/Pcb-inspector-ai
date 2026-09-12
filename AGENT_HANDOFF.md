# PCB Inspector AI — Agent handoff

Updated: 2026-09-12 (Asia/Karachi). Workspace: E:\PCB, Windows/PowerShell.

## Current task and stopping point

The user asked to resume explicit step-budget support, then the matched-step training control.
Step-budget implementation is complete, with 105 passing ML tests and a real five-update
partial-pass smoke run/reload. The full control has not started yet at this checkpoint.
Next commit/push the implementation cleanly, execute the single approved control below,
reload validation, export evidence/errors, compare with the tile pilot, and commit/push results.
Earlier user authorization covers local commits and pushes to main. Do not run further
expensive experiments automatically after that comparison.

## Scope and frozen data

Read PCB_Inspector_AI_Production_Architecture.md, docs/implementation-plan.md,
docs/dataset-v1-spec.md and ml/BASELINE.md. Accepted V1 scope is surface defects;
assembly inspection is deferred to V2. The website remains demo-only / NOT_EVALUATED.
No real model is approved for product use.

Frozen manifest: data/manifests/pcb-defect-v1.0.json.
SHA256: 31bc9c3df24a42dae1b577ea7082a4c0906fd26a5fb4ecf095af2853d43b26b4.
Release: data/releases/pcb-defect-v1; images: data/processed/pcb-defect-v1.
230 boards: 165 train / 32 validation / 33 test, 13 conservative groups.
Validation families 51 and 52 have 16 boards each and 232 labels total.
Classes: missing_pad, mouse_bite, open_circuit, short_circuit, spur, spurious_copper.
Torch labels 1–6, background 0. Keep the release intact.

No test inference is authorized. Expert annotation-completeness review, clean-board
negatives and an external-camera holdout are missing. Local research permission is not
public redistribution approval. Weights/data/runs/environments stay ignored.

## Exact-budget implementation

- ml/schedule.py yields seeded permutations and a final prefix, and shares strict
  completion/selection checks between evaluation and evidence export.
- --epochs and --max-steps are mutually exclusive. Neither supplied means ten epochs.
  Legacy epoch mode retains per-epoch validation and first-best AP50:95 tie selection.
- Step mode validates only after exactly max_steps updates. History uses pass,
  pass_complete, step_start/end and train_view_indices; only its final row has validation.
  Summary records completed_steps, completed_epochs (full passes) and partial_pass_steps.
- Step checkpoint: selected_epoch=null, selected_step=max_steps,
  selection_policy=final_budget_endpoint, selection_metric=optimizer_steps.
  It binds the final history hash. Legacy best-state.pt filename remains.
- Schema 1.1 evidence uses passes, requested/selected/actual steps; legacy export remains
  schema 1.0. The scheduling helper is included in training code hashes.
- Budget smoke uses four source boards and two validation boards, honoring exact steps.
  Legacy epoch smoke still consumes only the first two shuffled views per epoch.
- Tests include exact update/validation counts, 165-view 1053-step schedule, malformed
  order/history/endpoint rejection, legacy ties and nonfinite failures.

Real smoke: ml/runs/steps-smoke-001, five steps = 4 + 1, input 128, original COCO weights,
training RPN zero. Reload predictions/metrics match exactly. MLflow FINISHED with its
single validation event at step 5. Development run is dirty, with code/artifact hashes
in ml/evidence/step-budget-smoke-check.json. Old whole-board/tile evidence revalidated.

## Approved whole-board control

Output: ml/runs/coco-resize640-rpn0-steps1053 (verify absent before launching).

Exactly 1,053 updates: six full 165-board passes (990) plus 63 indices of seventh seeded
permutation. Whole boards, input 640 / max 1280, original COCO initialization, frozen
batch normalization, all six backbone stages trainable. Seed 20260908, SGD lr 0.005,
momentum 0.9, weight decay 0.0005, clip norm 10, CPU/two Torch threads/deterministic
algorithms. Training RPN zero, inference RPN 0.05. Final endpoint selection and one
validation opportunity. Exact commands are in ml/BASELINE.md.

Weights: ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth.
SHA256: 907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5.
No implicit downloads. Keep the frozen source ordering and untouched test holdout.

## Existing comparison evidence

Whole-board ml/runs/coco-resize640-5epochs: 825 updates, selected epoch 5,
AP50 38.1599%, AP50:95 13.5267%, AR100 23.8448%. Training RPN was 0.05.
Checkpoint: 13bb737a93252cf0535520bc774c3d6b434dc656a971ed7473ab458c880772f4.

Tile ml/runs/coco-tiles1536-rpn0-epoch1: 1053 updates, one epoch, tile1536/overlap256,
input640. AP50 63.1950%, AP50:95 24.7772%, AR100 40.0831%.
Checkpoint: d47d6ab12e6db81126b565f02b2c9447c1440664d162fdff121b411ca6a78ead.
Training revision: 6b80082294305f66a6a754859216de2d3aece2f6 (clean).
MLflow: d096d8fb069a41f6a3611ad1e6f67d71, FINISHED.
Training loop with validation: 2575.18 seconds. Exact reload verified.
At score .25 TP/FP/FN = 186/548/46; at .5 = 172/222/60.

Read ml/evidence/coco-tiles1536-rpn0-epoch1.md and matching JSON/errors/comparison.
Equal optimizer steps do not equal compute, board exposure or label appearances.

The original tile attempt failed with nonfinite loss: score-filtering all RPN proposals
on empty tiles can yield undefined ROI loss. Training threshold zero fixes the reproduced
failure, retaining empty tiles and optimizer settings. Inference stays .05. Exact original
failed step is unknown. Preserve the failure evidence and stop for diagnosis on new failure.

## False-positive review already completed

ml/error_analysis.py retains original prediction indices and exclusive contexts: duplicate,
class confusion, partial overlap, no overlap. At .25 tile FP contexts = 41/15/228/264.
ml/review.py + review.html offer annotation/FP modes, stable selection, filtering, overlays,
zoom and separate prediction notes. Exported notes bind to data/model/prediction/code hashes.
Notes remain only in browser memory until exported. Seven selected regions were inspected;
no labels or thresholds changed. See ml/evidence/coco-tiles1536-rpn0-fp-review.md.
Local review package: ml/runs/review-fp-003; verify any old server before relying on it.

## Execution and repository

Remote: https://github.com/fahadsaleem1678/Pcb-inspector-ai.git, main.
Pre-task HEAD: 94738416888b466040c6bb7807a98e7e6abf1c0e.
No AGENTS.md found. No subagents unless explicitly authorized.

Use .venv-ml/Scripts/python.exe for ML; .venv/Scripts/python.exe for service/lint.
ML tests: python -m pytest tests/test_ml_views.py ml/tests -q.
Lint/format: python -m ruff check .; python -m ruff format --check .

Normal sandbox shell/file helper fails to initialize. Escalated exec commands work with
task-specific justification. Respect current approval rules. PowerShell single-quoted
here-strings piped to Python support edits reliably. Do not start duplicate training after
interruption: inspect process command lines, run files and failure/summary before resuming.
Retain long-command session IDs and keep progress updates under a minute apart.

Git tracks LF. Hash new checked-in comparison evidence using LF bytes; never rewrite local
run artifacts after recording their actual-byte hashes. Keep full training source clean
before launch. No browser work is required for this task.

Service work (managed Cognito browser PKCE, S3/SQS/outbox, production deployment) remains
separate. Product qualification still requires expert labels, negatives, external data,
calibration and an approved surface-model artifact/API contract.
