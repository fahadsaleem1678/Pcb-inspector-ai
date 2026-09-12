# Implementation verification

Verified locally on 2026-09-07 with Windows, Python 3.12.14, and the dependency versions
recorded in `requirements.lock`.

| Check | Result |
| --- | --- |
| `python -m pytest -q` | 56 passed |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | 36 files formatted |
| `python -m mypy` | Passed; 13 source files checked in strict mode |
| `python -m alembic upgrade head` | Passed |
| `python -m alembic check` | No schema differences |
| `python -m pip check` | No broken requirements |
| `python scripts/smoke.py` | Passed: real HTTP API and separate worker, persisted report after API restart |
| `docker compose config --quiet` | Passed |
| Container build/runtime and PostgreSQL execution | Not run locally: Docker Desktop Linux engine is stopped |
| GitHub Actions | Workflow authored; not remotely executed |

Tests cover image byte/pixel/dimension limits, malformed/animated content, metadata removal,
orientation, filesystem containment, upload/status/results/history/download, owner filtering,
migration-backed storage, failure cleanup, events, concurrent claims, lease expiry/fencing,
retry delays, exhausted/crashed jobs and provisional decision thresholds.

The separate-process smoke test used an isolated SQLite database and filesystem, then cleaned
its processes and temporary files. Its last output is saved in the gitignored
`.runtime/last-smoke-result.json`. No trained model or real inference quality was tested.

Two dependency deprecation warnings were emitted by Starlette's test client: legacy HTTPX
integration and an AnyIO BlockingPortal alias. They do not fail these checks; revisit the
test-client dependency upgrade before a future dependency refresh.

The workflow includes a PostgreSQL service smoke test and a container build to run once the
repository is hosted on GitHub. Public deployment, Cognito, S3/SQS, actual model evaluation,
browser acceptance and production load/security tests remain later milestone gates.

## Local product and dataset preparation

Frontend production build and ESLint passed. Three component/hook tests passed. All eight browser scenarios passed in a complete desktop/mobile run after the authentication changes. Axe reported no violations in tested empty/completed
desktop and mobile states. The in-app browser connection failed; local Playwright Chromium
was used instead. Browser tests cover real upload/worker/report flow, download, reload, history,
errors, keyboard access and bounding-box geometry during zoom.

Dataset regression tests cover usage/evidence gates, checksums, annotations, dimensions,
duplicate bytes/pixels, likely visual leakage, class coverage and grouped split determinism.
No external dataset or trained model is included. Test detector outputs are synthetic fixtures.

Node 24.19.0 and the frontend lockfile were used. Frontend container/Compose and CI integration
are authored; Docker runtime and hosted CI verification remain pending.

## Authentication verification

The suite includes 21 additional Cognito checks using ephemeral RSA keys and mocked HTTPS JWKS.
Valid access tokens, key caching/rotation, malformed signatures/headers/claims, expiry, missing
scopes, resource audience, identity-service outage and cross-user isolation are covered.
Local development remains the default. No real Cognito pool or browser login has been exercised.

Windows launcher cleanup now stops owned process trees; the smoke test also verifies the old API no longer accepts connections before restart.


## Dataset acquisition and scope revision — 2026-09-08

- Acquired the original PCB-Defect V1 and MIXED V4 archives; both SHA-256 values match
  Mendeley metadata. URLs, versions and hashes are recorded in data/source-lock.json.
- Re-ran scripts/audit_dataset_archives.py against all 1,971 images and 5,640 annotation rows.
  Reproduced counts, geometry statistics, issues and filename-family leakage candidates.
- PCB-Defect: 230 images / 1,704 boxes; no structural issues or exact duplicates; ten images
  exceed the API's 20 MP limit. Group independence and annotation completeness are not proven.
- MIXED: 1,741 images / 3,936 rows; class-name mapping absent; four filename families span
  splits. No exact duplicates found. Training eligibility remains false for both sources.
- Visually reviewed 12 annotated images from each archive and PCB-IND's manuscript class table.
  These are exploratory reviews, not expert relabeling or statistically representative sampling.
- Checksum mismatch probe rejected an unexpected archive before ZIP processing.
- Python lint and formatting passed across the repository. Specification links, JSON parsing
  and six-class source-to-canonical mapping checks passed; git diff --check passed.
- No runtime/API/frontend behavior changed; service tests were not rerun for this data/docs slice.
- PCB-IND's Zenodo page/API returned HTTP 403. Its repository and manuscript disagree on label
  IDs/names; no PCB-IND archive, weights, training-ready manifest or trained model was produced.
- Compact measured reports are in data/audits/2026-09-08; raw data and visual artifacts remain
  ignored by Git. Dataset V1 specification records the accepted surface scope and remaining gates.


## Frozen PCB-Defect research manifest — 2026-09-08

- Reviewed first/middle/last images from all 22 original-name families and all 30 cross-family
  aHash/pHash candidates. Recorded five different-layout decisions and 25 conservative merges,
  yielding 13 transitive provenance/layout groups. Physical board IDs remain author-unverified.
- Built the immutable six-class release from unchanged source image bytes: 165/32/33 images,
  1,230/232/242 annotations and 9/2/2 groups across train/validation/test.
- All six classes are present in every split. Full 230-image manifest validation at the explicit
  40 MP offline limit passes with no errors/review findings. API/default limits remain 20 MP.
- Rebuilt the release with identical bytes. Manifest SHA-256:
  31bc9c3df24a42dae1b577ea7082a4c0906fd26a5fb4ecf095af2853d43b26b4.
- All 61 Python tests passed, including five new preparation/boundary regressions; Python lint,
  formatting and strict source typing passed. Frontend behavior did not change.
- Release provenance, review decisions and validation are committed under data/releases/pcb-defect-v1.
  Native images, license evidence copy and review thumbnails remain ignored by Git.
- This is research-baseline readiness, not production suitability: holdouts contain only two
  conservative groups each; no clean-board negatives, external camera set, expert annotation
  completeness certification or trained model is included.


## Offline ML baseline workflow — 2026-09-08

- Installed matched torch 2.13.0+cpu / torchvision 0.28.0+cpu in separate .venv-ml, with
  pycocotools 2.0.11, numpy 2.5.3 and mlflow-skinny 3.16.0. Resolved ML pins are recorded.
- CPU resize and 1024-pixel/256-overlap tile smoke training completed with finite losses,
  checkpoint artifacts and local SQLite MLflow tracking. Each used two optimizer steps and
  two validation boards; AP was zero, not evidence of useful inspection accuracy.
- Resize checkpoint reload reproduced predictions and per-class metrics exactly; MLflow
  run status was FINISHED. No held-out test evaluation or pretrained weight download occurred.
- 65 service/data tests passed without ML dependencies. Eleven optional ML contract tests
  passed for geometry, split isolation, source/evidence integrity, COCO edge cases, model
  initialization and smoke/test-set protection. Dependency consistency checks passed.
- Lint, formatting and strict source typing passed before final documentation updates.
- Optional CPU CI is authored; hosted execution has not been verified in this slice.
- Website inference remains explicitly demo-only. All research checkpoints remain ineligible
  for deployment; no clean-board negative or external camera evaluation is claimed.


### Full-data CPU baseline and final failure guard

- One clean-revision c461519 scratch epoch completed: 165 train images/steps, 32 validation
  images, 320.15 seconds including validation. Mean training loss 0.6585; every class had
  zero AP50/AP50:95/AR100. The checkpoint is not a usable detector and remains unpromoted.
- Full checkpoint reload reproduced all validation predictions and per-class metrics exactly;
  the local MLflow run is FINISHED. Held-out test data were not evaluated.
- Compact reproducible evidence is committed in ml/evidence/cpu-resize-epoch1.json. Model
  weights and full local logs remain ignored under ml/runs/cpu-resize-epoch1.
- Added a regression rejecting evaluation when artifact logging fails after a completion
  summary is written; all four model-contract tests passed after that fix (12 ML checks overall,
  including the four lightweight view/preflight checks also in the 65-test service suite).
- Final lint/format checks passed. Hosted CI and GPU execution remain unverified.

### Pretrained initialization support

- Reviewed the official COCO_V1 artifact provenance and separate weight/data terms for local
  research; public distribution approval remains unresolved (ml/PRETRAINED.md).
- Initial download matched publisher prefix; full SHA-256 is pinned for every subsequent
  acquisition and training load. Training/evaluation do not implicitly download weights.
- All 280 transferred tensors matched an official pretrained factory model with six trainable
  backbone stages. The predictor was replaced with six classes plus background.
- Fourteen ML checks passed, including corrupt-weight rejection before deserialization and
  offline frozen-normalization checkpoint reload; repository lint and formatting passed.
- Real-data COCO smoke fine-tuning completed with finite loss. Checkpoint reload reproduced
  all validation predictions and per-class metrics exactly; smoke AP remained zero.
- Five-epoch full-data experiment is documented separately when complete. The web detector
  remains demo-only; no hosted CI, CUDA execution or public-model qualification is claimed.

### Five-epoch pretrained experiment and evidence export

- Full clean-revision e1cb54e run completed five epochs / 825 optimizer steps on 165 training
  images, with 32 validation images each epoch, in 43.02 minutes including validation.
- Best epoch four: AP50 1.7526%, AP50:95 0.7614%, AR100 3.1077%; the fifth epoch regressed.
  Poor detection quality remains explicit. No test evaluation or public model promotion.
- Reload reproduced every selected validation prediction and aggregate/per-class/per-group
  metric exactly. Local SQLite MLflow status was FINISHED.
- New evidence exporter checks completion, config/state hashes, validation source order,
  predictions/metrics and best-epoch history before writing an immutable compact export.
- All 21 ML checks passed (including four lightweight checks shared with the service suite),
  plus repository lint/formatting. The seven export checks also ran in the base environment.
- Report and provenance are in ml/evidence/coco-resize-5epochs.md and .json; binary artifacts
  remain ignored. Previous dc142ea hosted application and ML workflows were verified successful.

### Resolution comparison and 640-pixel training pilot (2026-09-09)

- Added a prespecified, validation-only fixed-checkpoint probe. Original 320-pixel predictions
  and detection metrics reproduced exactly before running 640-pixel and 1536-pixel tile profiles.
- Neither changed inference transform improved AP50:95. Full-image 640 AP50 was 3.1264%, but
  AP50:95 fell to 0.3870%; tiles had AP50 1.5970%, AP50:95 0.4333%. All three profiles completed.
- Separate clean-revision 074c1d2 one-epoch 640-pixel training completed 165 steps / 32 validation
  boards in 16.85 minutes including validation. AP50 8.2584%, AP50:95 1.7542%, AR100 8.3799%.
- Initial weights, code, package versions, architecture, seed, optimizer settings, source list
  and actual first-epoch training order matched the earlier 320 run. One seed is not a convergence
  or significance study. Different-run timing is not an isolated benchmark.
- Checkpoint reload reproduced every pilot validation prediction and detection metric. MLflow
  status FINISHED; no held-out test evaluation or model promotion occurred.
- All 25 ML checks passed, including control mismatch and existing-output preservation tests;
  repository lint and formatting passed. No service code or dependency changes in this slice.
- Protocol, compact metrics, hashes and interpretations are recorded in ml/RESOLUTION.md and
  ml/evidence/resolution-probe-001.*, coco-resize640-epoch1.*, resolution-training-comparison.json.

### Five-epoch 640-pixel run and error diagnostics (verified 2026-09-10)

- Training completed five epochs / 825 optimizer steps from clean revision 28d7971. Recorded
  loop wall time totaled 97.35 minutes including validation; unusually long epochs three/five
  make this unsuitable as an isolated compute-speed benchmark. No causal timing claim is made.
- First epoch exactly reproduced the pilot's source order, mean loss, every prediction and
  detection metric. Best epoch five achieved AP50 38.1599%, AP50:95 13.5267%, AR100 23.8448%.
- Selected checkpoint reload reproduced all validation predictions and detection metrics;
  checksum-bound evidence export succeeded, and local SQLite MLflow status was FINISHED.
- Added score-ordered, one-to-one IoU .5 diagnostic matching at fixed scores .05/.25/.5,
  with TP/FP/FN, per-class/per-board details, missed annotation boxes and overlap coverage.
- At score .25: 101 TP, 162 FP, 131 missed labels; 39 of 43 mouse-bite labels missed.
  Precision/recall here are micro rates at one IoU, not COCO AP/AR or product calibration.
- All 33 ML checks passed, including duplicate/wrong-class/nonoverlap matching, score boundaries,
  empty denominators and malformed prediction rejection. Repository lint and formatting passed.
- Reports and compact evidence are in ml/evidence/coco-resize640-5epochs*. No test evaluation,
  model promotion, product inference change, or dependency change was made.


### Local validation review (verified 2026-09-10)

- Added a validation-only static review generator with full-run/release/source-order checks,
  byte-verified local image copies, original-coordinate SVG overlays, three fixed diagnostic
  thresholds, class/miss filters, focus/zoom/pan, board navigation and JSON note export.
- Notes remain in page memory until export; changing the score filter preserves the threshold
  under which a draft was written. Notes never change the frozen manifest or labels.
- Generated and served the final 32-board package at loopback port 8766, under ignored
  ml/runs/review-640-002. Source images and screenshots were not added to Git.
- All 38 ML checks passed; repository Ruff lint/formatting passed. Five new data-free review
  tests cover original-coordinate matching, stable asset mapping when sorting, validation
  isolation, embedded-script escaping and refusal to overwrite an existing output.
- Headless Chromium acceptance checks passed for overlays, focus/zoom, filters, layer switches,
  next/previous navigation, note export and original note-threshold retention. Desktop axe
  WCAG 2 A/AA and 2.1 AA reported zero violations; 390px mobile had no horizontal overflow,
  and no page script errors occurred. The reusable manual harness is ml/tests/review_browser.cjs.
- In-app browser setup and the native image helper were unavailable; used a separate headless
  Chromium session and viewed its local JPEG screenshots. Six selected mouse-bite regions were
  visually inspected across families 51 and 52, then compared with saved detection overlaps.
- Findings include absent retained boxes, low-score class confusion, a threshold-suppressed
  correct detection and partial localization. Observations are not expert label approval.
  Hash-bound evidence and the prespecified next tile-training pilot are recorded in ml/.
- No additional training, held-out test inference, model promotion, service/dependency change
  or dataset correction was performed in this slice. Hosted CI is verified after pushing.


### Empty-tile failure diagnosis and training correction (2026-09-10)

- Original tile smoke passed exact reload; the full tile pilot later aborted with nonfinite
  loss after last reported successful step 591, zero completed epochs and no checkpoint.
  MLflow marked it FAILED. Exact failed step was not recorded by the previous trainer.
- Fresh-COCO reproduction on candidate step 594's empty tile yielded zero RPN proposals at
  filter 0.05 and NaN ROI classifier/box losses. Training filter 0 retained proposals and
  produced finite losses. This establishes a failure path, not the original failing state.
- Added explicit --training-rpn-score-threshold (historical default 0.05; corrected pilot
  opts into 0). Inference always restores 0.05. Config/MLflow record both thresholds, and
  failure.json now includes step/source/window/target count and individual loss strings.
- All 43 ML tests passed, including forced-empty-proposal forward/backward regression,
  inference filter restoration and invalid-threshold rejection. Ruff lint/formatting passed.
- Corrected two-step tile smoke completed with finite mean loss 1.67621, then exact validation
  prediction/metric reload and MLflow FINISHED. It used the working fix before commit;
  dirty revision and source hashes are retained in its smoke evidence.
- Existing five-epoch 640 checkpoint rerun with the changed inference code reproduced all
  3,200 predictions and detection metrics on 32 validation boards exactly.
- Failed attempt, both smoke checks, tile-view audit and legacy-control parity are committed
  as compact metadata. No images/weights, held-out test inference or model promotion.
- The amended full pilot is a fresh single epoch, with explicit comparison limitations:
  training proposal filtering differs in addition to tiling, step count and label appearances.


### Completed corrected tile pilot (2026-09-10)

- Clean revision 6b80082 completed one epoch / all 1,053 seeded tile steps, from 165 source
  training boards. Mean loss 0.259109; loop time including validation 42.92 minutes.
- Validation used 160 tile views from 32 boards, merged into source coordinates. AP50 63.1950%,
  AP50:95 24.7772%, AR100 40.0831%; all six classes and both validation groups improved AP50/AP50:95.
- Independent checkpoint reload reproduced every prediction and aggregate/per-class/per-group
  detection metric exactly. MLflow status FINISHED. Export verified code/config/checkpoint
  hashes, complete history and the exact seeded permutation of all 1,053 view indices.
- At score 0.25 / IoU 0.5: 186 TP, 548 FP, 46 misses; mouse bites 26 TP / 148 FP / 17 misses.
  Higher recall comes with more false positives and does not qualify a production threshold.
- Five of six previously inspected mouse-bite labels now match numerically at that score/IoU.
  Board 044 remains missed. No new expert label review is claimed.
- New review package generated with verified copies of all 32 validation images, under ignored
  ml/runs/review-tiles1536-rpn0-001. Model weights and source images were not committed.
- Full 43-test ML suite, lint/format and both hosted workflows passed for the training fix;
  final result work changes evidence/docs only. No new test inference, dataset correction,
  longer training, automatic threshold selection or model promotion occurred.


### False-positive selection and visual review (2026-09-11)

- Extended the existing matcher with stable prediction indices, matched annotation indices,
  best same/any-class overlaps and mutually exclusive FP contexts. All prior per-board/class
  counts, missed boxes and class-agnostic coverage for the corrected tile run remain exact.
- At score 0.25: 41 duplicates, 15 class confusions, 228 partial overlaps and 264 no-overlap
  predictions sum to the existing 548 false positives. Context is geometry, not a proven cause.
- Added false-positive mode, class/context filters, score-ordered lists/board navigation,
  highest-score selection, original-coordinate focus and all-class annotation context.
- Schema 1.1 notes isolate annotation and prediction identities and retain original score/
  overlap context across filter changes. Source, checkpoint, prediction and matching hashes
  are exported. Notes remain in memory until export; no dataset edits or automatic relabeling.
- Seven deliberately selected high-score regions were visually inspected on 2026-09-10.
  Observations include repeated boxes on trace gaps, a spur/bridge class disagreement,
  box-extent mismatches and unlabelled regions needing reference/expert review.
- The 0.499693 IoU case exposed misleading three-decimal display; six decimals now distinguish
  it from a valid 0.5 match. Exact-threshold and just-below-threshold regressions passed.
- All 47 ML tests passed; Ruff lint/formatting and patch whitespace checks passed. Headless
  Chromium verified coordinate alignment, note identity isolation and original threshold/
  context, score navigation, filters/empty state, zoom, all-class label visibility and precise
  IoU display. Desktop axe reported zero WCAG A/AA violations; mobile had no horizontal overflow
  and no page script errors. In-app browser setup failed, so a separate Chromium session was used.
- Final generated package ml/runs/review-fp-003 serves on loopback 8768 during the session.
  HTML, 32 copied image hashes and matching/evidence hashes agree. Source images/screenshots
  remain ignored. The reusable browser acceptance harness is ml/tests/fp_review_browser.cjs.
- No training, threshold/annotation changes, held-out test inference or model promotion.
  Next work is explicit step-budget support and the matched-step whole-board control.


## Exact optimizer-step budgeting — 2026-09-12

Added mutually exclusive --epochs / --max-steps modes with the ten-epoch legacy default
and first-best tie behavior preserved. Step mode consumes seeded full passes plus a final
prefix, validates only at the exact endpoint, and records full/partial passes separately.
Evaluation/export verify schedule order, step ranges, completion and endpoint selection;
the checkpoint binds the final history hash. New evidence uses schema 1.1 passes while
old epoch evidence remains readable.

105 ML tests passed, covering 165-view/1,053-step schedule boundaries, invalid budgets,
actual optimizer updates and endpoint validation in the trainer, legacy first-best ties,
nonfinite failure, and rejection of altered completion/order/selection/history. Ruff lint
and formatting passed. Existing dependency deprecation warnings do not fail the checks.

Real pinned-COCO CPU smoke completed five updates on four source views (4 + 1), with one
validation opportunity on two boards. Independent reload reproduced all predictions and
detection metrics exactly; MLflow FINISHED and its validation metric occurs only at step 5.
Both historical comparison runs revalidated through the updated exporter. This is a
dirty-development smoke, not a full quality experiment; recorded code/artifact hashes are
in [smoke evidence](../ml/evidence/step-budget-smoke-check.json).


## Matched-step control completed — 2026-09-12

- Trained once from clean local c76479702c1a642878c3af78b2ae3ce0abbe7b99.
- Exactly 1,053 optimizer updates: six 165-view passes plus a 63-view final prefix.
  Seeded order, inclusive step ranges, six complete passes and partial-pass metadata verified.
- Only one training validation/selection opportunity, at step 1,053. MLflow FINISHED;
  run b4276b9d3ca84d16930b96cb1887d5d8.
- Checkpoint 4dc04ed4a31e7630e929adc69139ba8e2130edc314fb7b1161b4dcf95c057824
  independently reproduced all 3,182 predictions and detection metrics exactly.
- Validation AP50 45.8523%, AP50:95 15.5973%, AR100 26.6494%; training loop 3,876.73 seconds.
- Exported evidence, fixed-score error/overlap diagnostics and checksum-bound comparison.
  At score 0.25: 137 TP / 268 FP / 95 FN. Tiles retain 9.1799 points higher AP50:95,
  with 49 more TP and 280 more FP at that score.
- Matched initialization/source/configuration fields and single endpoint selection verified.
  Exposure remains unequal: 7,849 control versus 2,774 tile label appearances.
- No held-out test inference, label changes, threshold calibration or promotion.
- Automatic review blocked the main-branch push pending direct permission. The experiment
  used a clean local commit. A later approval-service usage-limit interruption delayed only
  evidence export, which succeeded after the user asked to continue.

See [full report and evidence](../ml/evidence/coco-resize640-rpn0-steps1053.md).
