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
