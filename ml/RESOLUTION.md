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
