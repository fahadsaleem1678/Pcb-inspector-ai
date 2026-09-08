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
The initialization is random; **weights=None and weights_backbone=None** prevent implicit
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
Select reviewed pretrained weights and an appropriate compute budget in a later experiment.
The current local run does not download weights or launch cloud resources.

Whole-image mode preserves aspect ratio: Torchvision scales the short side toward input-size
and caps the long side at twice input-size. Tile mode uses the same transform for each crop.
All tiles inherit their source split; partially intersecting boxes are clipped, and empty
tiles are retained. No target fragments are silently dropped by a visibility threshold.
Tiny fragments and treating unannotated regions as negative inherit the source annotation
completeness limitation. No extra augmentation is implemented yet.

Tile inference maps boxes back by the crop offset after Torchvision restores resize coordinates,
then applies class-aware NMS at IoU 0.5 and keeps at most 100 detections per original board.
Evaluation always uses original full-image ground truth, not an artificially enlarged tile test set.

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
