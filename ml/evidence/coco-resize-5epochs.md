# Five-epoch pretrained PCB baseline

Completed 2026-09-08. This is a research result; the website remains in demo mode.

Five epochs processed 165 training boards (825 optimizer steps) and evaluated 32 validation boards after every epoch. Training plus validation took 43.02 minutes on CPU with two Torch threads.

Epoch 4 was selected by validation AP50:95. The fifth epoch regressed; the final epoch did not replace the better checkpoint. Reloading the selected checkpoint reproduced every validation prediction and detection metric exactly. Local MLflow status was FINISHED.

## Validation results

All metrics below are percentages, not classification accuracy. AR100 averages recall across IoU thresholds 0.50-0.95 with at most 100 detections per original board. No held-out test evaluation was run.

| Epoch | Mean loss | AP50 | AP50:95 | AR100 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.3852 | 0.0072% | 0.0018% | 0.1733% |
| 2 | 0.3298 | 0.0354% | 0.0135% | 0.9759% |
| 3 | 0.3178 | 0.3451% | 0.1956% | 0.6687% |
| 4 (selected) | 0.3165 | 1.7526% | 0.7614% | 3.1077% |
| 5 | 0.3114 | 1.4744% | 0.4931% | 2.4976% |

### Selected checkpoint by class

| Class | Instances | AP50 | AP50:95 | AR100 |
| --- | ---: | ---: | ---: | ---: |
| missing_pad | 37 | 0.9275% | 0.1977% | 2.9730% |
| mouse_bite | 43 | 0.0000% | 0.0000% | 0.0000% |
| open_circuit | 38 | 0.0777% | 0.0217% | 1.8421% |
| short_circuit | 38 | 0.2038% | 0.0212% | 1.5789% |
| spur | 39 | 0.3284% | 0.1012% | 3.3333% |
| spurious_copper | 37 | 8.9783% | 4.2267% | 8.9189% |

## Interpretation and next experiment

The one-epoch scratch run had zero AP. This longer pretrained run produces some correct detections but still misses most labeled defects. It is not suitable for user-facing inspection. Initialization, normalization and training duration changed together, so this is not a controlled estimate of the effect of pretraining alone.

Next prioritize small-defect localization: compare higher input resolution or tiled views and a backbone with finer feature maps on the same frozen validation split. Keep each experiment separately named, record compute cost, and choose settings before evaluating the held-out test set. Longer training at the current resolution alone is not established as the best next step.

Independent annotation review, clean-board negative examples, external camera evaluation, calibrated thresholds and artifact distribution review remain open. Two validation groups do not support broad generalization claims.

## Reproduce and inspect

- [Training, evaluation and evidence commands](../BASELINE.md#explicit-pretrained-fine-tuning).
- [Weight provenance and loading contract](../PRETRAINED.md).
- [Machine-readable evidence](coco-resize-5epochs.json), including package/code/data/weight hashes and per-group metrics.
- Training revision: `e1cb54e3982524af32901b475414c19591f22c68`; clean at run start.
- Selected checkpoint SHA-256: `3f8dcca6f1937a5931c8f86b8a517a93cad8ba0bdfa1901d3132e391a5fa71b0`.
- Weights and full local logs remain ignored under `ml/runs/coco-resize-5epochs`; no model binary is pushed to GitHub.
