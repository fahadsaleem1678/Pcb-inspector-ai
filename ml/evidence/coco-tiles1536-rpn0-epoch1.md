# Corrected tile-training pilot result

Completed and verified 2026-09-10. The website remains demo-only.

One epoch completed all 1,053 optimizer steps across 165 source training boards and 1,053 tile views. Validation used 32 source boards / 160 tile views, merged into original coordinates before scoring. Mean training loss was 0.259109; recorded training-loop time including validation was 42.92 minutes. The selected checkpoint reloaded with every prediction and detection metric exactly reproduced. Local MLflow status was FINISHED.

Training started from clean revision `6b80082294305f66a6a754859216de2d3aece2f6`. Checkpoint SHA-256: `d47d6ab12e6db81126b565f02b2c9447c1440664d162fdff121b411ca6a78ead`. No held-out test inference or model promotion occurred.

## Validation comparison

| Run | Steps | Training RPN filter | AP50 | AP50:95 | AR100 |
| --- | ---: | ---: | ---: | ---: | ---: |
| coco-resize640-epoch1 | 165 | 0.05 | 8.2584% | 1.7542% | 8.3799% |
| coco-resize640-5epochs | 825 | 0.05 | 38.1599% | 13.5267% | 23.8448% |
| coco-tiles1536-rpn0-epoch1 | 1,053 | 0.00 | 63.1950% | 24.7772% | 40.0831% |

The amended pilot improves all three aggregate validation metrics over both earlier runs. AP50:95 is the primary metric. AP/AR are detection metrics, not classification accuracy. This is a single seed with only two validation groups. More optimizer steps, repeated/clipped label appearances and changed training proposal filtering prevent attributing the gain solely to tiling. These runs are not an equal-compute benchmark.

## Class and group results

| Class | Labels | AP50 | AP50:95 | AR100 |
| --- | ---: | ---: | ---: | ---: |
| missing_pad | 37 | 70.7757% | 36.5561% | 49.7297% |
| mouse_bite | 43 | 30.0377% | 8.2423% | 23.7209% |
| open_circuit | 38 | 54.5577% | 15.4435% | 36.5789% |
| short_circuit | 38 | 77.4221% | 33.2964% | 42.8947% |
| spur | 39 | 78.6702% | 29.7308% | 44.8718% |
| spurious_copper | 37 | 67.7067% | 25.3942% | 42.7027% |

All six classes improved AP50 and AP50:95, but mouse bites remain weakest. Family 51 achieved AP50 57.0094% / AP50:95 21.5215%; family 52 achieved 74.5023% / 30.6316%. Both improved, while the family performance gap remains.

## Recall and false positives

Fixed diagnostic scores use same-class, descending-score, one-to-one matching at IoU 0.5. False positives are measured against available labels; annotation completeness is unverified. These scores are not calibrated product thresholds.

| Score | TP | FP | Missed labels | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.05 | 198 | 2019 | 34 | 8.93% | 85.34% |
| 0.25 | 186 | 548 | 46 | 25.34% | 80.17% |
| 0.50 | 172 | 222 | 60 | 43.65% | 74.14% |

At score 0.25, misses dropped from 131 to 46, including mouse-bite misses from 39 to 17. False positives increased from 162 to 548, and precision fell from 38.40% to 25.34%. Mouse-bite precision is only 14.94% at that score (26 TP / 148 FP). At score 0.5, there are still 222 false positives and 60 misses. The higher recall does not establish a usable operating point.

A [numerical recheck](coco-tiles1536-rpn0-reviewed-cases.json) of the six previously inspected mouse-bite regions found five now matched at score 0.25 / IoU 0.5: boards 014, 013, 016, 030 and 035. Board 044 remains missed (best same-class IoU 0.344). This is not a new visual or expert label assessment.

## Failure and correction

The [original tile attempt](coco-tiles1536-epoch1-failure.json) failed before completing an epoch, after last observed successful step 591. Its exact failed step was not recorded. A fresh-weight reproduction on candidate step 594 showed that the default RPN score filter could remove all proposals on an empty tile, leaving undefined ROI losses.

The corrected run explicitly sets the training RPN filter to zero, keeping background proposals. Inference retains the original filter 0.05. All empty tiles and labels remain included. The frozen view audit records 111 empty training tiles and 416 clipped annotation appearances. Configuration and MLflow record both filters; failures now include source/view/step/loss context. The original failed run remains intact.

A forced-empty-proposal regression verifies finite losses and gradients after the correction and restoration of the inference filter. All 43 ML tests passed. The previous best checkpoint still reproduced all 3,200 predictions and all detection metrics on 32 validation boards under the amended inference code. Both GitHub workflows passed for the training revision.

## Timing and next work

Initial validation inference averaged 2449.44 ms per source board on two CPU threads; independent reload averaged 2464.89 ms. Timing includes decoding, cropping, inference, transfers and NMS, with no warmup excluded. Different run wall times and machine load do not establish an isolated speed comparison.

1. Extend local review to select and annotate false-positive predictions, with overlap context that separates duplicates, class confusion, localization errors and unmatched regions. Review high-confidence false positives before changing thresholds; some unmatched regions may reflect incomplete labels.
2. Define a whole-board 640 control at the same 1,053-step budget and training RPN filter zero, with checkpoint selection at the final budget endpoint. This requires explicit step-budget support before execution; it has not been implemented or run here. Equal steps still do not equal equal compute or source exposure.
3. Retain expert completeness review, clean-board negatives, external-camera holdout, rights review and calibrated decision thresholds as separate qualification work. No production detector is enabled.

## Evidence and local review

- [Prespecified amendment](../RESOLUTION.md#empty-tile-failure-and-corrected-pilot).
- [Run evidence](coco-tiles1536-rpn0-epoch1.json), [fixed-score errors](coco-tiles1536-rpn0-epoch1-errors.json), [comparison and hashes](coco-tiles1536-rpn0-epoch1-comparison.json).
- [Corrected smoke checks](coco-tiles1536-rpn0-smoke-check.json), [tile composition](coco-tiles1536-view-audit.json), [legacy inference parity](legacy-control-after-tile-fix.json).
- Generated local review: `ml/runs/review-tiles1536-rpn0-001/index.html`, served on loopback port 8767 during this session. Notes must be exported before closing. Source images, predictions and weights stay local under ignored directories.
