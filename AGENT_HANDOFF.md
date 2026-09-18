# PCB Inspector AI â€” Agent handoff

Updated: 2026-09-19 (Asia/Karachi). Workspace: E:\PCB, Windows/PowerShell.

## Current task and stopping point

The 3,968-step size-320 full pass is COMPLETE and independently verified. All 7,936
train images were used once; first 600 steps and initialized validation match the
600-step control exactly. AP50 45.97%, AP50:95 19.91%, AR100 36.65%.
See ml/evidence/dspcbsd-nineclass-research-3968steps-001.{json,md} and
ml/evidence/dspcbsd-nineclass-fullpass-errors-001.json. At score .25 there are
298 TP / 578 FP / 206 FN; mouse bite 19 TP / 77 FP / 45 FN, spur 45 TP / 204 FP / 62 FN.
The old .runtime/export_dsp_research.py remains specific to the 600-step run.

User authorized the matched 640-pixel experiment with "go ahead". Runner now accepts
--input-size 320 or 640, default 320; training and independent reload use the chosen
size. Budget remains 3,968 steps, same data, seed, initialization and optimizer.
Planned run: ml/runs/dspcbsd-nineclass-research640-3968steps-001.
Check .runtime/dspcbsd-resolution640-001.* and run artifacts before launching to
avoid a duplicate. Launch confirmation will be recorded below after tests pass.
Higher resolution requires substantially more CPU time. No production promotion.


Saved-prediction error analysis completed on 2026-09-18. See
ml/evidence/dspcbsd-nineclass-errors-001.{json,md} and ml/research_errors.py.
At score .25: overall 145 TP / 518 FP / 359 FN; MB 0 TP / 0 FP / 64 FN;
SP 15 TP / 98 FP / 92 FN. At .05 MB/SP recall improves but precision is about 3%.
Mixed confidence, classification and localization errors; 12 examples visually inspected,
without expert certification. Corrected the prior narrative's 604-label typo to 504;
metrics/data were already based on the actual 504 labels. 243 ML tests passed.
Next chosen experiment: fresh 3,968-step / batch-two / size-320 control from the same COCO
initialization and seed, covering all 7,936 training images once; estimated ~3 hours CPU.
This was subsequently launched as recorded above. The old checkpoint lacks optimizer state, so do not
claim exact resume. Preserve fixed validation/quarantine; no production threshold selected.


User changed the model-work scope on 2026-09-15: no expert reviewer is available; after the
assistant proposed clearly unreviewed experimental training, the user explicitly said
"ok do it". This permits the separate research run, not expert certification or promotion.
Read ml/UNREVIEWED_RESEARCH.md; do not reimpose expert review as a prerequisite for this
already-authorized experiment. Reviewed-release and production gates remain unchanged.
Run: ml/runs/dspcbsd-nineclass-research-600steps-001. Code commit ee3071b; exactly 600
optimizer steps, batch two, COCO initialization, nine preserved DsPCBSD+ source classes.
The run is COMPLETE: 600 steps / 1,200 distinct training images. Do not rerun it.
AP50 23.2258%, AP50:95 9.0906%, AR100 29.7874% on 256 unreviewed validation images.
Initialization AP50 was 0.8656%; checkpoint reload reproduced final predictions exactly.
Final evidence and report: ml/evidence/dspcbsd-nineclass-research-600steps-001.{json,md}.
Saved-prediction metrics were independently recomputed on 2026-09-18; all hashes, source
separation and all-nine-class exposure checks passed. Weakest AP50: MB 5.15%, SP 7.62%.
Data: 7,936 train / fixed 256 source-validation images; 272 train similarity candidates
quarantined; 304 bounded source-box corrections recorded as experimental preprocessing.
No expert ledger was fabricated. 231 ML tests passed before execution. Post-run evidence
verification helper: .runtime/export_dsp_research.py (run only after result.json exists).
Saved-prediction analysis is complete as described above. Website/production gates remain unchanged.


Visual candidate review is complete: ml.candidate_viewer builds verified offline packages;
ml/candidate_viewer.html and .js provide paired images, overlays, zoom, filtering, strict
saved-decision export/restore and missing-image safeguards. Read ml/CANDIDATE_VISUAL_REVIEW.md.
Packages: ml/runs/meiwei-visual-review-002 (1,015 cases / 1,938 images) and
ml/runs/dspcbsd-visual-review-002 (835 cases / 771 selected images). Open index.html in a
browser with the package folders intact. Saved decisions stay in memory until exported.
Validation: 225 ML tests; desktop/mobile browser checks and axe checks passed for both;
synthetic browser exports validated in memory with the Python importer, never recorded as
actual expert observations. Evidence: ml/evidence/candidate-visual-review-001.json.
Browser plugin startup failed twice; the project's standalone Playwright harness was used.
Next practical step is actual expert/source review using these viewers, then importing the
exports and deriving candidates. Training and production remain unapproved; no reviews or
model metrics were invented, and source labels/splits remain unchanged.


Candidate derivation completed: ml.candidate_derive consumes a bound inventory/packet and
optional validated decision ledger. It applies only uncontested bounded corrections and
related-capture group links, preserves all source classes/images/labels, records conflicts
and rejected/unresolved cases, and keeps split/physical-board IDs null and eligibility false.
Shared ledger validation was extracted in ml.candidate_decisions without changing its format.
Validation: 221 ML tests passed (12 new derivation cases), plus Ruff lint/format checks.
See ml/CANDIDATE_DERIVATION.md. Complete-data no-review previews preserve 1,938 Meiwei
images / 1,275 boxes (1,015 unreviewed cases), and 10,259 DsPCBSD+ images / 20,276 boxes
(835 unreviewed cases; 277 invalid boxes still present). Zero corrections or reviewed links
were applied. Evidence: ml/evidence/*-derived-preview-001.json; full outputs remain ignored.
No expert reviews, training runs, new source splits or production approvals were fabricated.
Next practical work: visual candidate review interface and actual expert/source review,
then a separately reviewed independent split/release proposal. The derivation path is ready
for genuine review ledgers; lack of those decisions still blocks a new training release.


Candidate decision import is now implemented in ml.candidate_decisions. Read
ml/CANDIDATE_DECISIONS.md for strict batch fields and revision commands. Actual reviewer
observations bind to the committed packet hash; earlier batches and disagreements are
preserved, repeated batches are no-ops, and source data/splits remain unchanged.
Blank templates: ml/runs/meiwei-decisions-template-001 (1,015 cases) and
ml/runs/dspcbsd-decisions-template-001 (835 cases). No real reviews were imported.
Evidence: ml/evidence/candidate-decision-templates-001.json. Validation: 207-test ML suite
passed, then two added CLI regression checks passed (22 importer tests total); Ruff passed.
The derived-candidate slice is now implemented above; actual expert reviews remain pending.
Expert review and independent production qualification data are still outstanding.


Candidate grouping follow-up: ml.candidate_manifest now builds hash-bound review packets.
Meiwei has 966 provisional groups (two cross source splits), 969 pair reviews and 43
similarity cases. DsPCBSD+ has 10,259 provisional singleton groups, all 453 similarity
cases and 371 correction proposals. Exact/pair links are transitive; similarity does not
merge groups. New splits, physical-board identities and reviewer decisions remain null.
See ml/CANDIDATE_REVIEW.md and ml/evidence/*-candidate-review-001.json. Full packets are
under ignored ml/runs/*-candidate-review-001. No training or source correction was applied.
Validation: 187 ML tests passed, including 11 new manifest cases; Ruff lint/format passed.
Decision import is now complete as described above. Reviewed derived groups/annotations
and an independent split proposal remain. Do not infer approvals from filled flags.


Dataset follow-up completed on 2026-09-14: downloaded and checksum-verified DsPCBSD+;
audited its 10,259 images / 20,276 boxes and Meiwei's 969 normal/defect filename pairs.
See docs/dataset-candidate-audit.md and ml/evidence/*-source-audit-001.json.
Meiwei has two exact-normal-duplicate groups crossing inherited splits. DsPCBSD+ has
277 border overshoots above 1e-6 pixels; bounded proposals also cover 94 floating-point
boundary discrepancies. Original labels are intact. Near-image matches require review;
no verified board-group metadata or clean whole-board qualification set is available.
Neither candidate is released for training. No training or model test inference was
performed. 176 ML tests passed, including 14 new audit tests.
Next: review source grouping, normal-label completeness and source class definitions before
freezing a separate candidate release. Keep all paired/related views together. Preserve
all nine DsPCBSD+ classes in a separate research track; do not erase unmapped defects.

Latest model task: user asked to start production model qualification, chose **only flagged
boards get reviewed**, and answered **Not decided yet** for maximum defective-board escape
rate. The workflow is recorded in ml/qualification-policy-draft.json; targets remain null.

Completed ml.qualification and two bound validation reports, documented in ml/QUALIFICATION.md.
The tile model's maximum label recall at >=90% precision is 16.38% (38 TP, 3 FP, 194 FN),
leaving 4/32 defective boards without a flag. At .25 all 32 are flagged but 46 labels remain
missed. Flagged boards require full-board inspection, not just checking model boxes.
No clean-board/domain qualification can be inferred from this positive-only two-group set.

162 ML tests passed (18 new qualification cases). The audit rejects nonvalidation sources,
source/hash/order mismatches and invalid predictions; tied-score sweep matches direct greedy
matching. Reports never enable promotion or select a production threshold. Existing frozen
runs/labels/test holdout remain unchanged. No additional training was performed.

Next model work depends on real expert completeness review and verified clean/camera data.
The proposed next experiment compares train-only verified hard-negative inclusion with a
matched tile control after a reviewed release is frozen. Do not fabricate negative labels,
expert decisions, numeric acceptance targets or final-test authorization. See the qualification
guide for intake fields, split rules and independent-sample planning. The previously completed
cloud slice and its pending live acceptance remain as recorded below.


The latest "continue working" implemented the next local service slice: private S3 storage,
transactional submission outbox, standard SQS publication/consumption, database/SQS lease
renewal, native DLQ policy checks, explicit audited failed-job retry, and a read-only orphan
candidate audit. See docs/cloud-integrations.md for configuration and recovery commands.
The API and worker now use the same ObjectStore abstraction; ownership is checked before
S3 image delivery. Uncertain database commits no longer cause immediate image deletion.

Migration 0002 adds queue_backend (existing records default to database) and submission_outbox.
Run migrations before starting the updated API/worker. Do not flip an existing filesystem
installation to S3 without migrating its images or choosing a fresh integration database.
Downgrade refuses SQS inspection records. Local/test/demo configuration gates remain in place.
No AWS resources, live queue messages, real model inference or dataset changes were performed.

Verification: 116 service tests passed (including 51 cloud tests), Ruff lint/format, strict
mypy, pip check, separate-process API/worker/restart smoke, and all eight desktop/mobile local
browser checks passed. OpenAPI output is unchanged. The ML and frontend unit suites were not
rerun for this service-only slice; their last verified results remain 144 and 29 respectively.
A full-suite test exposed a heartbeat/completion race; durable completion is now acknowledged
even when a concurrent heartbeat observes the retired lease. Regression tests pass.

CI now runs cloud/worker tests against PostgreSQL in unique disposable schemas using
PCB_TEST_DATABASE_URL. The local Docker executable exists but its engine is stopped; the
PostgreSQL additions are not locally verified. SDK request-model stubs and in-memory S3/SQS
simulations do not establish live AWS behavior. Do not describe this as production-ready.

Next acceptance work: inspect remote CI, then authorized existing
S3/SQS/Cognito infrastructure and test accounts for IAM/KMS/queue-policy, two-user ownership,
crash/recovery, DLQ/retention and deployment checks. Monitoring/alerts, staging, restore/load
checks and safe URL ingestion remain pending. Upload idempotency keys are not implemented;
uncertain submissions can be located in history, and the browser does not replay uploads.
Expert annotation review, clean negatives and external-camera holdout remain independent
model qualification blockers. Do not automatically rerun the completed training experiments.

The earlier review-import/adjudication and Cognito PKCE work remains complete locally. No
actual expert decisions or dataset corrections have been recorded. See ml/ADJUDICATION.md
and docs/authentication.md. The user subsequently explicitly authorized pushing main;
push through 5f5c3fb succeeded. Dataset discovery/audit work after that is local only.

## Prior completed step-budget work

The user asked to resume explicit step-budget support, then the matched-step training control.
Both are complete. Implementation commit: c76479702c1a642878c3af78b2ae3ce0abbe7b99.
The single full control completed exactly 1,053 updates from that clean local revision,
then independently reproduced every prediction/metric. Evidence, error diagnostics and
the matched-step comparison are exported. Do not rerun the control or automatically start
another expensive experiment.

Full report: ml/evidence/coco-resize640-rpn0-steps1053.md.
AP50 45.8523%, AP50:95 15.5973%, AR100 26.6494%. Tile AP50:95 remains 9.1799 percentage
points higher. At score .25 the control has 137 TP / 268 FP / 95 FN; tiles have 186/548/46.
Training loop including validation took 3,876.73 seconds (64.61 minutes).
Checkpoint: 4dc04ed4a31e7630e929adc69139ba8e2130edc314fb7b1161b4dcf95c057824.
MLflow: b4276b9d3ca84d16930b96cb1887d5d8, FINISHED; one validation event at step 1053.
Reload reproduced all 3,182 predictions and all detection metrics exactly.
No test evaluation, label/threshold changes or model promotion occurred.

The implementation and results are local. Automatic approval review rejected the push to
main because historical authorization in the handoff was not accepted as direct permission.
An explicit push-approval question was sent; the later user message "continue" resumed
evidence export after an approval-service usage-limit failure and was not treated as
specific push authorization. Direct approval is still needed before updating the shared
main branch. Do not bypass that rejection. No fresh remote CI ran for these local commits.

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
Torch labels 1â€“6, background 0. Keep the release intact.

No test inference is authorized. Expert annotation-completeness review, clean-board
negatives and an external-camera holdout are missing. Local research permission is not
public redistribution approval. Weights/data/runs/environments stay ignored.

## New review and browser-auth implementation

ml/review.py exposes build_payload for authoritative validation context. The offline page
imports schema-1.1 notes with strict run/model/data/prediction/matcher and subject/threshold
checks, atomic conflict rejection and unsaved-draft preservation. Legacy export remains 1.1.
ml/adjudication.py provides import/adjudicate/candidate commands. Ledger revisions preserve
observations and decisions; later observations reopen cases. Human identities are self-reported,
not authenticated expertise. Corrections require explicit class/box decisions, resolved cases
and a separate version/output directory; candidate ready_for_training stays false. Train/test,
source images, groups and original frozen manifests remain unchanged. A candidate needs full
integrity/release review and a new evaluation protocol for changed validation labels.

Local generated package: ml/runs/review-adjudication-001 (32 validation boards).
Smoke ledger: ml/runs/adjudication-import-smoke-001, two pending synthetic cases, zero decisions.
The reviewer name explicitly says automated pipeline check, not human review. Never treat this
as expert coverage. Review import browser evidence: .runtime/review-import-browser-check.json.
Serve the package on a loopback port before running ml/tests/review_import_browser.cjs; do not
assume an old server is still alive. No real candidate has been generated.

Frontend adds pinned oidc-client-ts 3.5.0 with public VITE_* configuration. Default local mode
verifies /api/v1/auth/me; Cognito mode uses code/PKCE S256, state/nonce, API identity verification,
in-memory tokens and sessionStorage redirect state. Reload requires another hosted sign-in.
Refresh is single-flight, errors/401 close the workspace without replaying uploads, and late
responses cannot revive a logged-out session. Logout clears memory before bounded revocation
and hosted logout. Images/reports use bearer fetch and temporary object URLs, never token URLs.
See frontend/.env.example and docs/authentication.md for exact pool/client/callback settings.
Vite settings are build-time; Docker exposes public build arguments. No secrets belong there.

Verification: 144 ML tests, 65 service tests, 29 frontend tests; 10 mock Cognito desktop/mobile
checks and 8 local browser checks passed. Both old FP-review and new note-import browser
harnesses passed; accessibility has zero axe violations and no horizontal mobile overflow.
Ruff, mypy, frontend lint/format and production build passed. Auth browser tests use synthetic
provider tokens plus a mocked identity API; backend signed-token tests remain separate.
CI now includes auth browser acceptance and lightweight review/adjudication tests. No remote
CI or live Cognito verification has run for these local changes.

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

## Completed whole-board control

Output: ml/runs/coco-resize640-rpn0-steps1053 (complete; do not overwrite or rerun).

Exactly 1,053 updates: six full 165-board passes (990) plus 63 indices of seventh seeded
permutation. Whole boards, input 640 / max 1280, original COCO initialization, frozen
batch normalization, all six backbone stages trainable. Seed 20260908, SGD lr 0.005,
momentum 0.9, weight decay 0.0005, clip norm 10, CPU/two Torch threads/deterministic
algorithms. Training RPN zero, inference RPN 0.05. Final endpoint selection and one
validation opportunity. Exact commands are in ml/BASELINE.md.

Weights: ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth.
SHA256: 907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5.
No implicit downloads. Frozen source ordering and untouched test holdout were preserved.
Files: ml/evidence/coco-resize640-rpn0-steps1053.json, matching -errors.json,
-comparison.json and .md report. Comparison verifies equal updates/RPN settings/one
endpoint opportunity and matching source, initialization and configuration fields.
Exposure differs: control 7,849 label appearances versus tile 2,774; tiles retain 111
empty updates and 416 clipped appearances. Equal updates do not imply equal compute.

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
before launch. Frontend checks run with pnpm.cmd --dir frontend; test:auth and test:e2e
use separate output directories and ports 5175/5174. Local e2e also uses API port 8011.

Live Cognito and live S3/SQS acceptance plus production deployment remain pending. Product qualification still requires expert labels, negatives, external data,
calibration and an approved surface-model artifact/API contract.
