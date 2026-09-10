# Five-epoch higher-resolution training result

Training completed 2026-09-09; checkpoint reload and error analysis verified 2026-09-10. This research run keeps the website in demo mode.

All five epochs used 165 training boards (825 optimizer steps total) and 32 validation boards, with the original COCO initialization, 640-pixel short-side target / 1280-pixel cap, whole-image inputs, two CPU threads and the pilot optimizer settings. Test images were not evaluated.

## Validation progression

| Epoch | Mean loss | AP50 | AP50:95 | AR100 | Wall minutes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.4886 | 8.2584% | 1.7542% | 8.3799% | 7.40 |
| 2 | 0.4530 | 20.0212% | 6.1266% | 18.7948% | 7.13 |
| 3 | 0.4306 | 27.1399% | 8.1594% | 19.7773% | 51.93 |
| 4 | 0.4155 | 36.5514% | 12.5974% | 21.2901% | 6.98 |
| 5 (selected) | 0.4393 | 38.1599% | 13.5267% | 23.8448% | 23.92 |

Training-loop wall time, including per-epoch validation, totaled 97.35 minutes. Epochs three and five have much longer wall times than the others; the cause is not established, so this run is not an isolated compute-speed benchmark. First-epoch training order, mean loss, all validation predictions and detection metrics reproduced the one-epoch pilot exactly.

Best-epoch selection used AP50:95 and selected epoch five. Its checkpoint reload reproduced all validation predictions and detection metrics exactly. Local MLflow run status was FINISHED. AP/AR values are percentages here, not classification accuracy.

## Context

| Experiment | AP50 | AP50:95 | AR100 |
| --- | ---: | ---: | ---: |
| 320 best of five | 1.7526% | 0.7614% | 3.1077% |
| 640 one-epoch pilot | 8.2584% | 1.7542% | 8.3799% |
| 640 best of five | 38.1599% | 13.5267% | 23.8448% |

Five epochs at 640 outperform both the 640 pilot and the earlier five-epoch 320 run on this validation split. This is one seed and only two validation groups; no statistical significance, convergence or external generalization claim follows.

## Selected checkpoint by class

| Class | Instances | AP50 | AP50:95 | AR100 |
| --- | ---: | ---: | ---: | ---: |
| missing_pad | 37 | 54.0643% | 23.8714% | 35.6757% |
| mouse_bite | 43 | 7.5457% | 1.3109% | 8.8372% |
| open_circuit | 38 | 32.3347% | 7.8892% | 18.6842% |
| short_circuit | 38 | 45.0888% | 15.9134% | 25.2632% |
| spur | 39 | 31.6086% | 10.4531% | 19.7436% |
| spurious_copper | 37 | 58.3172% | 21.7223% | 34.8649% |

## Fixed-threshold error review

These prespecified diagnostic thresholds use score-ordered, same-class, one-to-one matching at IoU >= 0.5. Micro precision and recall below differ from COCO AP and AR100 above. Scores are not calibrated product decisions, and false positives are relative to source annotations whose completeness is unverified.

| Score threshold | TP | FP | Missed targets | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.05 | 130 | 774 | 102 | 14.38% | 56.03% |
| 0.25 | 101 | 162 | 131 | 38.40% | 43.53% |
| 0.50 | 73 | 48 | 159 | 60.33% | 31.47% |

At score 0.25, mouse bites are the weakest class: 4 true positives and 39 misses from 43 labels. Raising the threshold to 0.5 reduces total false positives to 48 but leaves 159/232 targets missed. None of these thresholds is an acceptable product operating point established by this experiment.

Validation family 51 has AP50 28.05% versus 52.57% for family 52. At score 0.25, boards pcb_defect_014, 013 and 016 have 11, 10 and 10 missed annotations respectively. Their class-agnostic IoU coverage is also low (1, 2 and 2 targets), suggesting localization needs attention alongside classification. This numerical diagnostic does not establish annotation correctness or a causal model diagnosis.

## Next implementation slice

1. Build a local visual review of missed mouse bites and the worst family-51 boards, showing source annotations and predictions at the existing diagnostic thresholds. Flag uncertain labels for expert review rather than silently changing the frozen release.
2. Use that review to define a separate experiment with finer spatial features, smaller anchors or trained tiles. The current model still has a large AP50-to-AP50:95 gap and low recall; another unbounded training extension is not a qualified fix.
3. Keep threshold calibration, clean-board negatives, external camera holdout, rights review and approved model/API integration as separate outstanding gates. No real detector is enabled by this experiment.

## Reproduce and inspect

- [Prespecified protocol](../RESOLUTION.md#authorized-five-epoch-640-pixel-experiment).
- [Run evidence](coco-resize640-5epochs.json), [fixed-threshold error details](coco-resize640-5epochs-errors.json), [comparison and hashes](coco-resize640-5epochs-comparison.json).
- Training revision `28d7971e6619e969f081a4f18377926a0b328865`, clean at run start.
- Checkpoint SHA-256 `13bb737a93252cf0535520bc774c3d6b434dc656a971ed7473ab458c880772f4`.
- Model weights and full prediction logs remain ignored under `ml/runs/coco-resize640-5epochs`.
