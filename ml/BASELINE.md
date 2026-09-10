# Offline six-class research baseline

The optional training tools are separate from the API environment and never change the
website's demo detector. The first adapter is Torchvision Faster R-CNN with a MobileNetV3
backbone. This provides a CPU-verifiable detection baseline; YOLO/RT-DETR comparisons remain
planned. There is no claim that this is the best architecture for tiny PCB defects.

## Install

Use Python 3.12 from the repository root. Keep the service's .venv separate.

```powershell
python -m venv .venv-ml
.\.venv-ml\Scripts\python.exe -m pip install torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv-ml\Scripts\python.exe -m pip install -c requirements.lock -c ml/requirements.lock -r ml/requirements.txt -e ".[dev]"
.\.venv-ml\Scripts\python.exe -m pip check
```

The [official version matrix](https://pytorch.org/get-started/previous-versions/) pairs
torch 2.13.0 with torchvision 0.28.0. For GPU work install the matching official CUDA
build for the target machine; a GPU run is not verified by the local CPU run.
ML packages and resolved dependencies are pinned in ml/requirements.lock; each experiment
records installed distributions. Torch local build suffixes are recorded in runs; the lock
uses public versions so matching CPU/CUDA builds can be installed explicitly.
The current workstation exposes Intel UHD 620 graphics, no CUDA device, and eight logical CPUs.

## Data preflight

Reproduce [PCB-Defect release 1.0.0](../data/releases/pcb-defect-v1/README.md) first.
Every run checks the manifest and recorded validation hashes, grouping review, license evidence,
frozen group assignments, current source-image hashes and dimensions. Altered data or unresolved
validation gates stop the run. All original images are retained, including those above the
service's 20 MP upload limit. Training consumes only train images; model selection uses validation.

Model labels are 1–6 internally (0 is Torchvision background), corresponding to manifest
labels 0–5. The nine-class product roadmap has a separate label ID space.

## Run a pipeline check

```powershell
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/cpu-smoke-001 --epochs 1 --smoke
.\.venv-ml\Scripts\python.exe -m ml.baseline evaluate --run ml/runs/cpu-smoke-001 --split validation
```

Smoke mode selects the first four train images, performs at most two optimizer steps per
epoch, and evaluates the first two validation images. These are plumbing checks only.
By default initialization is random; **weights=None and weights_backbone=None** prevent implicit
COCO/ImageNet weight downloads. A smoke checkpoint cannot evaluate the held-out test set.
All checkpoints currently have promotion_eligible=false, including full research runs.

A run directory must be new. Failures are surfaced; failed/incomplete runs cannot be evaluated.
Checkpoints contain only state dictionaries and load with weights_only=True after a SHA-256
check. Metadata binds weights to architecture, label names, manifest and configuration.

## Full experiments

For the first resized-image baseline:

```powershell
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/resize-001 --epochs 10 --input-size 320
```

For an independently named tiling experiment:

```powershell
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/tiles-001 --epochs 10 --input-size 640 --tile-size 1024 --overlap 256
```

These are starting configurations, not calibrated hyperparameters or completed training runs.
Full scratch training on 165 boards is unlikely to establish useful production quality by itself.
The explicit COCO initialization below supports local fine-tuning. No cloud resources are launched.

Whole-image mode preserves aspect ratio: Torchvision scales the short side toward input-size
and caps the long side at twice input-size. Tile mode uses the same transform for each crop.
All tiles inherit their source split; partially intersecting boxes are clipped, and empty
tiles are retained. No target fragments are silently dropped by a visibility threshold.
Tiny fragments and treating unannotated regions as negative inherit the source annotation
completeness limitation. No extra augmentation is implemented yet.

Tile inference maps boxes back by the crop offset after Torchvision restores resize coordinates,
then applies class-aware NMS at IoU 0.5 and keeps at most 100 detections per original board.
Evaluation always uses original full-image ground truth, not an artificially enlarged tile test set.

## Explicit pretrained fine-tuning

[Provenance review](PRETRAINED.md) records the official COCO_V1 artifact, full SHA-256,
normalization contract and unresolved public distribution rights. Acquire once explicitly:

```powershell
.\.venv-ml\Scripts\python.exe -m ml.pretrained --output ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/coco-resize-5epochs --epochs 5 --input-size 320 --learning-rate 0.005 --initial-weights ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth
.\.venv-ml\Scripts\python.exe -m ml.baseline evaluate --run ml/runs/coco-resize-5epochs --split validation
```

Training verifies the reviewed artifact bytes before deserialization, preserves pretrained
FrozenBatchNorm2d statistics, transfers RPN/FPN/box-head weights, and initializes a new seven-output
class/box predictor. All six backbone stages are trainable. Evaluation restores normalization
from the saved configuration and needs only the fine-tuned checkpoint, with no initial-weight
file or network access. Older scratch configurations keep BatchNorm2d.

This first five-epoch experiment fixes the existing seed, 320-pixel resize, learning rate,
optimizer and source split. It changes initialization, normalization and training duration;
comparison with the one-epoch scratch baseline is not a controlled estimate of pretraining's
individual effect. Best-epoch selection uses validation AP50:95 only. No test evaluation,
public model deployment or threshold calibration is part of this experiment.

## Metrics and experiment evidence

Each run writes:
- config.json: manifest hash, classes, seed, device, threads, transforms, actual source-image
  lists, package versions, Git revision/dirty state and training-code hashes;
- history.json: loss, step counts, time and per-epoch validation metrics;
- best-state.pt and checkpoint.json: checksum-bound best validation checkpoint, first epoch
  wins metric ties;
- best-validation.json: predictions, source image ordering, aggregate/per-class and per-group
  COCO metrics, and original-image latency;
- summary.json or failure.json;
- local mlflow.db and artifacts/ with parameters, metrics and provenance files.

COCO bbox evaluation uses IoU 0.50–0.95, 101 recall points and maxDets=100. AP50, AP50:95 and
AR100 are fractions; classes without ground truth report null, and no predictions yield zero
recall rather than an evaluator crash. Prediction retention floor is 0.001, not a product
decision threshold. Loss is not accuracy. Original-image latency includes decode, crop inference,
device transfer and NMS, with no warmup exclusion; hardware/device are recorded.

Per-group metrics are diagnostic; only two conservative groups in each full holdout are
insufficient for a strong population-level confidence interval. Clean-board false-positive
rates and external-camera robustness cannot be measured with this release.

Test evaluation is an explicit final step, after configuration and checkpoint selection:

```powershell
.\.venv-ml\Scripts\python.exe -m ml.baseline evaluate --run ml/runs/resize-001 --split test --final-test
```

It refuses smoke runs and refuses to overwrite an existing evaluation. Do not use test metrics
to choose another model. Test evaluation is not performed by training or by the smoke workflow.
Changing a run folder is not a replacement for a new versioned evaluation protocol.

## Export auditable results

After a full run and validation reload, export compact evidence without model weights or
full prediction lists:

```powershell
.\.venv-ml\Scripts\python.exe -m ml.summarize --run ml/runs/coco-resize-5epochs --output ml/evidence/coco-resize-5epochs.json
```

This refuses failed/incomplete/smoke runs, changed configuration or checkpoint bytes,
validation ordering/prediction/metric mismatches, missing epoch records, and a checkpoint
that disagrees with best-epoch selection. Existing evidence files are not overwritten.
The export records per-epoch/per-class/per-group metrics, package/code/data/weight hashes,
actual training steps, latency and whether a test-evaluation artifact exists locally.
It does not grant deployment approval or prove that no evaluation occurred elsewhere.

## Software and weight provenance

- [Torchvision 0.28 license](https://raw.githubusercontent.com/pytorch/vision/v0.28.0/LICENSE):
  BSD-3-Clause.
- [PyTorch 2.13 license](https://raw.githubusercontent.com/pytorch/pytorch/v2.13.0/LICENSE):
  BSD-style terms with bundled-component notices.
- [COCO API license](https://github.com/cocodataset/cocoapi/blob/master/license.txt):
  BSD-style evaluation software terms; these do not license COCO images.
- Torchvision explicitly notes that [pretrained models may have separate terms](https://github.com/pytorch/vision#pre-trained-model-license).
  No pretrained-model rights are inferred from the library license.
- PCB-Defect source license evidence is part of the research release; trained output is not
  automatically approved for a public product.

No upstream source code or model weights are vendored. Preserve applicable notices if
distributing dependencies or artifacts. Framework/weight review for the later YOLO/RT-DETR
comparison remains open.

## Checks

```powershell
.\.venv-ml\Scripts\python.exe -m pytest tests/test_ml_views.py ml/tests -q
```

The separate ML CI workflow installs CPU dependencies and checks geometry, label handling,
COCO edge cases, no-download model initialization and test-set protection.
The web/backend tests continue to run without any ML package installed.


## First full-data run: measured, not promoted

[Recorded evidence](evidence/cpu-resize-epoch1.json) captures the clean c461519 training revision,
package versions, configuration, source/checkpoint hashes and full validation metrics.
One scratch epoch used all 165 training images (165 optimizer steps) and 32 validation images.
It took 320.15 seconds including validation; mean training loss was 0.6585.
AP50, AP50:95 and AR100 were all zero across all six classes. Validation inference averaged
522.78 ms per board on this CPU with the timing scope described above. Checkpoint reload
reproduced predictions exactly; MLflow status was FINISHED. No test images were evaluated.
This is a failed-quality baseline and a successful workflow verification, not a usable model.

The training/validation metadata-only resize check found 56/1,230 training targets with a
short side below four pixels (three below two); validation had none below four. This motivates
resolution experiments but does not explain away the zero AP. Review initial weights and train
longer before selecting resolution/tiling or comparing architectures on validation.

## Five-epoch pretrained result

The [completed experiment report](evidence/coco-resize-5epochs.md) records 825 training steps
and all five validation passes. Epoch four was best: AP50 1.7526%, AP50:95 0.7614%,
AR100 3.1077%. Epoch five regressed. Selected-checkpoint reload reproduced predictions and
metrics exactly. The model remains research-only; no test evaluation was performed.
The next experiment should prioritize resolution, tiles or finer feature maps for small defects.

## Resolution and tiling experiments

The [resolution protocol](RESOLUTION.md) compares fixed-checkpoint inference transforms before
spending more CPU time on training. The [completed probe](evidence/resolution-probe-001.md)
reproduced the original predictions exactly; both changed transforms reduced AP50:95.
A separately defined one-epoch 640-pixel training pilot measures learning at the larger scale.

The [completed 640-pixel training pilot](evidence/coco-resize640-epoch1.md) reached AP50 8.2584%,
AP50:95 1.7542% and AR100 8.3799% after 165 training steps. Checkpoint reload was exact.
Higher-resolution training improved the equal-step comparison, but detection quality is still
inadequate. Next evaluate a separately named multi-epoch 640-pixel run; retain validation-only
selection and the unchanged test holdout.

## Validation error diagnostics

After a full run and verified validation reload, inspect errors at fixed score thresholds
0.05, 0.25 and 0.5. These thresholds are diagnostic examples, not product calibration.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.error_analysis --run ml/runs/coco-resize640-5epochs --output ml/evidence/coco-resize640-5epochs-errors.json
```

The report uses descending-score one-to-one matching with the same class and IoU >= 0.5.
Duplicate predictions count as false positives; wrong-class predictions also leave the target
missed. Per-class and per-board TP/FP/FN counts include missed annotation boxes for review.
Aggregate precision/recall are micro averages at this single IoU, not COCO AP or AR100.
An empty denominator returns null. False positives are relative to available labels, whose
completeness still requires review. Separate class-agnostic overlap coverage may reuse boxes
and must not be interpreted as matched recall. No test split or automatic threshold selection
is exposed; output files are never overwritten.

## Five-epoch 640-pixel result

The [completed longer run](evidence/coco-resize640-5epochs.md) selected epoch five: AP50 38.1599%,
AP50:95 13.5267%, AR100 23.8448%. All 825 optimizer steps completed, first-epoch pilot parity
was exact, and the selected checkpoint reload reproduced every prediction and detection metric.
At diagnostic score 0.25 / IoU 0.5, 131 of 232 validation labels remain missed, including 39 of
43 mouse bites. The next slice is local visual error review followed by a targeted spatial-feature
or tiling experiment; the model remains research-only and the test split remains unevaluated.


## Local visual review

Build a standalone review package after full-run evidence and selected-checkpoint validation
reload pass. The generator verifies the frozen release, prediction source order and copied
image hashes, includes only the 32 validation boards, and refuses an existing output directory.
It runs in the base service environment without Torch. Choose a fresh output name each time.

```powershell
.\.venv\Scripts\python.exe -m ml.review --run ml/runs/coco-resize640-5epochs --output ml/runs/review-640-002
.\.venv\Scripts\python.exe -m http.server 8766 --bind 127.0.0.1 --directory ml/runs/review-640-002
```

Open http://127.0.0.1:8766/. The server exposes only the generated review directory.
Boards are ordered by missed labels at score 0.25. Select a class and annotation to focus
its source-image region; pan, zoom and toggle labels/predictions to inspect underneath.
Prediction filtering follows the selected class. Switch to all classes to inspect confusion.
Missed labels use the same score-ordered, one-to-one IoU 0.5 matching as error diagnostics.
The fixed score options are 0.05, 0.25 and 0.5; they do not configure product thresholds.

Notes are held in browser memory and exported as JSON, with source annotation, zero-based
annotation index, threshold at the time of writing, checkpoint/manifest/prediction hashes.
Export before closing or reloading. Notes are not uploaded or applied to frozen labels.
Generated images, HTML and screenshots stay in ignored local directories; `provenance.json`
records template/generator/source/HTML hashes. Do not use a package containing `INCOMPLETE.txt`.

With frontend dependencies and its Playwright Chromium installed, run the manual acceptance
check from repository root against the generated five-epoch review:

```powershell
node ml/tests/review_browser.cjs http://127.0.0.1:8766/
```

This frozen-data check covers coordinates, focus/zoom, filters, layers, board navigation,
note export and original-threshold retention, desktop accessibility and mobile overflow.
It writes screenshots and results into `.runtime/`; it is separate from data-free ML CI.
The [completed visual review](evidence/coco-resize640-5epochs-visual-review.md) records six
selected mouse-bite failures and the next training hypothesis.
