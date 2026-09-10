# Visual review of missed mouse bites

Reviewed 2026-09-10 using the local review package for selected epoch five of
`coco-resize640-5epochs`. [Machine-readable observations and overlaps](coco-resize640-5epochs-visual-review.json)
bind the source images, checkpoint, manifest, predictions and generated page by SHA-256.
This is a six-case visual inspection by Codex, not independent expert label approval.

## Selection and observations

At diagnostic score 0.25 / IoU 0.5, inspect the first missed mouse-bite annotation on each
of the three worst validation boards, then the first three family-52 boards with mouse-bite
misses in the same descending total-miss ordering. All six labels surround visible inward
trace recesses or nicks. Their morphology appears consistent with the label, but completeness,
precise extent and electrical significance were not established. Boards 013 and 014 show
similar layout features and cannot be counted as independent examples.

Annotation numbers below are one-based as shown in the viewer; JSON indices are zero-based.
IoUs use original coordinates and the saved, postprocessed predictions, not internal proposals.

| Board / annotation | Family | Visible feature | Prediction evidence |
| --- | --- | --- | --- |
| 014 / 8 | 51 | Inward notch at a trace bend | No overlapping prediction of any class at score >= 0.05. |
| 013 / 3 | 51 | Similar inward notch at a trace bend | A **spur** box has IoU 0.609 at score 0.065; no overlapping mouse-bite box at >= 0.05. |
| 016 / 5 | 51 | Recess at diagonal-to-horizontal bend | Mouse-bite box has IoU 0.350 at score 0.063: low confidence and partial localization. |
| 030 / 2 | 52 | Pronounced notch in a diagonal trace | Mouse-bite IoU 0.578, score 0.149: matched at 0.05, missed at 0.25. |
| 035 / 2 | 52 | Long recess down a vertical trace | Mouse-bite score 0.388, but IoU 0.387; predicted height 83.3 px versus annotated 190.6 px. |
| 044 / 5 | 52 | Nick in a vertical trace with softer image edges | No overlapping prediction of any class at score >= 0.05. |

The family-51 annotations shrink to approximately 18-23 pixels on their shorter box side
at the 640-pixel training transform. Board 035's box becomes approximately 13 x 47 pixels.
These are nominal resize estimates; the actual notch occupies less area than its box.
Visual differences between these selected groups do not isolate a cause of the measured
family performance gap.

## Decision for the next experiment

Lowering the threshold helps board 030, but cannot repair missing spatial candidates,
wrong labels or short boxes in the other cases. Across all validation classes, changing
score 0.25 to 0.05 raises recall from 43.53% to 56.03% while precision falls from 38.40%
to 14.38%. These fixed diagnostic thresholds are not a calibrated operating point.

Next test **training with 1536-pixel tiles at input size 640**, keeping the detector,
initial weights, optimizer and split unchanged. This is a hypothesis that presenting
larger defect detail during learning may improve recognition/localization. The earlier
inference-only tile probe became worse; it does not establish the result of tile training.
The [prespecified pilot](../RESOLUTION.md#follow-up-trained-tiling-pilot) records view counts,
comparisons, runtime measurement and stopping conditions. No training was launched as part
of this review. Finer backbone features or anchor changes remain separate later experiments.

Keep the frozen labels unchanged. This selected review cannot establish dataset completeness,
performance on clean boards or external cameras, calibrated thresholds, or public deployment
readiness. Source images and screenshots remain local under ignored directories.
