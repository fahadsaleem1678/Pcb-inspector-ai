# Fixed-checkpoint resolution probe

Protocol fixed before execution on 2026-09-09. The previous five-epoch run selected epoch four
with AP50 1.7526%, AP50:95 0.7614%, AR100 3.1077%. Test images remain held out.

## Question and scope

Does higher-resolution or tiled inference improve localization of small defects using the
same selected checkpoint? This is a validation diagnostic. It does not measure training at
higher resolution and does not grant model promotion. An inference-only improvement can guide
a later separately named training experiment; it cannot establish a production operating point.

## Prespecified profiles

| Profile | Short-side target | Long-side cap | Native tile | Overlap | Validation views |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control | 320 | 640 | Full image | N/A | 32 |
| Higher resolution | 640 | 1280 | Full image | N/A | 32 |
| Tiles | 640 | 1280 | 1536 | 256 | 160 |

The 1536-pixel tiled training alternative would expand 165 training images to 1,053 views;
1024-pixel tiles would expand them to 2,563. Running this diagnostic first bounds CPU cost.
Every tile inherits its source split. Predictions are offset to the original board coordinates,
merged by class-aware IoU 0.5 NMS and capped at 100 per original image, using the existing evaluator.
Metrics use full original-image annotations, including partially visible defects.

## Integrity and comparison

- Source must be a complete non-smoke run with checksum-bound config/checkpoint, full history,
  successful validation reload and correct best-epoch selection.
- Frozen release and actual source bytes are reverified before execution.
- Run the original 320-pixel profile first and require exact source ordering, predictions and
  detection metrics. Timing can vary. Abort before other profiles if the control differs.
- Compare AP50:95, AP50, AR100, all six classes, two validation groups, and latency including
  decode, crop, model inference, transfers and merge. The weights never change.
- Fixed seed and two CPU threads by default. No test-split switch exists. Every profile records
  source/code/checkpoint hashes; existing outputs are never overwritten. Partial failures cannot
  produce a completed summary.
- All profiles are validation choices. Additional tuning increases validation overfitting risk;
  external/clean-negative evaluation and artifact rights review remain outstanding.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.probe --run ml/runs/coco-resize-5epochs --output ml/runs/resolution-probe-001
```

Full predictions remain under ignored ml/runs. Commit the compact summary and interpretation
after all three profiles complete. No checkpoint binary or source image is redistributed.

## Follow-up: one-epoch higher-resolution training pilot

The fixed-checkpoint comparison changes only inference. To measure training at the larger
resolution, run one full epoch initialized from the same original COCO_V1 artifact at 640
pixels (long-side cap 1280), without tiles. Keep seed 20260908, SGD learning rate 0.005,
momentum 0.9, weight decay 0.0005, fixed normalization and all backbone stages trainable.
Use all 165 training boards and the same 32 validation boards, with two CPU threads.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/coco-resize640-epoch1 --epochs 1 --input-size 640 --learning-rate 0.005 --initial-weights ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth
.\.venv-ml\Scripts\python.exe -m ml.baseline evaluate --run ml/runs/coco-resize640-epoch1 --split validation
.\.venv-ml\Scripts\python.exe -m ml.summarize --run ml/runs/coco-resize640-epoch1 --output ml/evidence/coco-resize640-epoch1.json
```

Compare primarily with epoch one of the earlier 320-pixel COCO training run: equal source
images and optimizer steps, different resolution and runtime. Architecture, initialization,
seed, optimizer and data split stay fixed; varying resolution can still change stochastic
proposal sampling. This is a single-seed pilot, not evidence of convergence. The five-epoch
selected checkpoint is contextual only, since it received more training. Retain every measured
result and do not evaluate test images or automatically launch a longer run based on this pilot.

## Authorized five-epoch 640-pixel experiment

Following the completed pilot and the user's instruction to proceed, train a new run for
five epochs at 640 pixels. Fix all other settings to the one-epoch pilot: original COCO_V1
initialization, all six backbone stages trainable, frozen normalization, seed 20260908,
two CPU threads, whole images, SGD learning rate 0.005 with momentum 0.9 and weight decay
0.0005, no scheduler or extra augmentation. Use all 165 training images every epoch and the
same 32 validation images for selection. No test evaluation or automatic model promotion.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/coco-resize640-5epochs --epochs 5 --input-size 640 --learning-rate 0.005 --initial-weights ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth
.\.venv-ml\Scripts\python.exe -m ml.baseline evaluate --run ml/runs/coco-resize640-5epochs --split validation
.\.venv-ml\Scripts\python.exe -m ml.summarize --run ml/runs/coco-resize640-5epochs --output ml/evidence/coco-resize640-5epochs.json
```

This restarts from the original COCO weights. It does not resume the pilot, whose saved
checkpoint lacks optimizer/RNG state. Confirm the first epoch reproduces pilot training
order and validation metrics, then compare all five epochs with the earlier 320-pixel run.
Select the greatest validation AP50:95, retaining the first epoch on ties. Checkpoint reload
must reproduce predictions and detection metrics before exporting the final evidence.

The pilot took about 17 minutes on this CPU, so five epochs may take around 85 minutes.
Keep measured per-epoch runtime; do not infer an isolated performance benchmark from it.
Even a better validation score does not satisfy annotation, negative-example, external-camera,
threshold-calibration or weight-distribution gates. Inspect missed detections after selection.


## Follow-up: trained tiling pilot

Original protocol, retained for provenance. After the observed empty-tile failure, use the
[corrected pilot below](#empty-tile-failure-and-corrected-pilot) for execution.

The [six-case visual review](evidence/coco-resize640-5epochs-visual-review.md) found a mixture
of absent retained boxes, low-confidence class confusion and partial localization. Test the
spatial-detail hypothesis with a separately named, one-epoch tiled run. This protocol is
specified before training; the visual-review work did not launch the experiment.

Use original COCO_V1 weights, input size 640 / cap 1280, native tiles 1536 with overlap 256,
seed 20260908, two CPU threads, all six backbone stages trainable, frozen normalization,
SGD learning rate 0.005 / momentum 0.9 / weight decay 0.0005, no scheduler or new augmentation.
Retain every tile, including empty tiles and clipped edge annotations, using the existing
source-preserving view implementation. The 165 training boards yield 1,053 optimizer steps
per epoch; 32 validation boards yield 160 views. The test split remains reserved.

First run the existing bounded tile smoke test in its own output directory to verify finite
loss, timing and validation reload. Then train one full epoch in a fresh directory. Do not
infer runtime by multiplying the earlier whole-board epoch, which used far fewer views.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/coco-tiles1536-smoke --smoke --epochs 1 --input-size 640 --tile-size 1536 --overlap 256 --learning-rate 0.005 --initial-weights ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth
.\.venv-ml\Scripts\python.exe -m ml.baseline evaluate --run ml/runs/coco-tiles1536-smoke --split validation
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/coco-tiles1536-epoch1 --epochs 1 --input-size 640 --tile-size 1536 --overlap 256 --learning-rate 0.005 --initial-weights ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth
.\.venv-ml\Scripts\python.exe -m ml.baseline evaluate --run ml/runs/coco-tiles1536-epoch1 --split validation
.\.venv-ml\Scripts\python.exe -m ml.summarize --run ml/runs/coco-tiles1536-epoch1 --output ml/evidence/coco-tiles1536-epoch1.json
```

Merge predictions in original coordinates using existing class-aware IoU 0.5 NMS and the
100-detection cap per board; evaluate against full-image labels. Record all six classes,
both validation groups, AP50:95 (primary), AP50, AR100, fixed-threshold errors and measured
training/inference times. Require exact selected-checkpoint prediction/metric reload.
Compare with both whole-image 640 runs: one epoch (165 steps) and five epochs (825 steps).
This pilot uses more steps (1,053), repeats source boards across tiles and clips boundary
labels, so neither comparison isolates resolution or establishes equal-compute superiority.
An equal-step experiment is needed before attributing a gain to tiling alone.

Stop after the one full epoch and retain the result even if quality falls. Do not silently
change anchors, overlap, thresholds or architecture, launch longer training, evaluate the
held-out test split, or promote the model as part of this pilot. Expert label/completeness,
clean-negative and external-camera review remain independent qualification work.


## Empty-tile failure and corrected pilot

The original `coco-tiles1536-epoch1` attempt stopped with nonfinite loss after the last
reported successful step 591, before completing an epoch or saving a selected checkpoint.
MLflow marked it FAILED. The old trainer did not record the exact failed step; it is unknown.
The [failure evidence](evidence/coco-tiles1536-epoch1-failure.json) preserves this limitation.

A bounded reproduction using original COCO weights on candidate step 594 (view 1043,
an empty tile from pcb_defect_228) showed zero proposals after the default RPN score filter
0.05. With no annotations to add as proposals, classifier loss and box loss were NaN.
Setting the **training-only** RPN threshold to 0 retained 2,000 proposals and gave finite
losses. This establishes a reproducible failure path, not the exact original failure state.
A data-free regression forces this condition and verifies finite backward gradients after
the fix. Inference always resets to the historical RPN filter 0.05, including old checkpoints.

The new CLI option defaults to 0.05 for historical reproducibility. The corrected tile pilot
explicitly uses `--training-rpn-score-threshold 0`. Both training and inference thresholds
are recorded in config/MLflow; future failures include epoch, step, source/view/window,
target count and individual loss values. Nonfinite values still abort; no tiles are skipped.

After corrected smoke and exact reload verification, run **one** fresh full epoch from the
original COCO weights in `coco-tiles1536-rpn0-epoch1`. Keep every other pilot setting fixed.
This is an explicit protocol amendment: more training proposals may affect every tile, so
comparisons now vary proposal filtering as well as tiling and optimizer-step count. Do not
attribute any gain solely to tile resolution. Retain the failed attempt and the retry result.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/coco-tiles1536-rpn0-smoke --smoke --epochs 1 --input-size 640 --tile-size 1536 --overlap 256 --learning-rate 0.005 --training-rpn-score-threshold 0 --initial-weights ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth
.\.venv-ml\Scripts\python.exe -m ml.baseline evaluate --run ml/runs/coco-tiles1536-rpn0-smoke --split validation
.\.venv-ml\Scripts\python.exe -m ml.baseline train --output ml/runs/coco-tiles1536-rpn0-epoch1 --epochs 1 --input-size 640 --tile-size 1536 --overlap 256 --learning-rate 0.005 --training-rpn-score-threshold 0 --initial-weights ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth
.\.venv-ml\Scripts\python.exe -m ml.baseline evaluate --run ml/runs/coco-tiles1536-rpn0-epoch1 --split validation
.\.venv-ml\Scripts\python.exe -m ml.summarize --run ml/runs/coco-tiles1536-rpn0-epoch1 --output ml/evidence/coco-tiles1536-rpn0-epoch1.json
```

A second numerical failure stops this retry for diagnosis; do not repeatedly restart or tune
learning rate/labels until loss appears acceptable. No test evaluation or automatic promotion.
