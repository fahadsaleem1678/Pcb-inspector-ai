# Higher-resolution training pilot

Completed 2026-09-09. One full epoch at a 640-pixel short-side target (1280-pixel long-side cap) trained on 165 boards and validated on the frozen 32-board split. Original COCO weights, architecture, fixed normalization, optimizer, seed, package versions, training code and actual training image order matched the earlier 320-pixel experiment.

## Results

| Training configuration | AP50 | AP50:95 | AR100 |
| --- | ---: | ---: | ---: |
| 320 pixels, epoch one | 0.0072% | 0.0018% | 0.1733% |
| 320 pixels, best of five (context) | 1.7526% | 0.7614% | 3.1077% |
| 640 pixels, epoch one | 8.2584% | 1.7542% | 8.3799% |

The pilot took 16.85 minutes including validation, versus 12.21 minutes for the earlier first epoch. These are workstation wall times on different runs, not an isolated hardware benchmark. Mean pilot validation latency was 1.607 seconds per board including decoding/inference/merging, without warmup exclusion.

### Pilot by defect class

| Class | Instances | AP50 | AP50:95 | AR100 |
| --- | ---: | ---: | ---: | ---: |
| missing_pad | 37 | 1.1651% | 0.4569% | 5.4054% |
| mouse_bite | 43 | 3.6464% | 0.4331% | 6.2791% |
| open_circuit | 38 | 20.6174% | 3.2164% | 11.3158% |
| short_circuit | 38 | 2.8062% | 0.8906% | 5.7895% |
| spur | 39 | 0.6670% | 0.3021% | 7.4359% |
| spurious_copper | 37 | 20.6480% | 5.2258% | 14.0541% |

## Interpretation

Learning at the higher resolution improved all three aggregate metrics after equal training steps. In contrast, the [fixed-checkpoint inference probe](resolution-probe-001.md) did not improve AP50:95 by enlarging or tiling inference alone. This supports testing a longer 640-pixel training run before investing in the much larger tiled training workload.

The absolute result remains poor: average recall is only 8.38%, and all six classes need improvement. This is one seed, one epoch and two validation groups. Resolution changes can affect stochastic proposal sampling; no convergence, statistical significance, calibrated operating threshold or production readiness is claimed. Comparison with the best of five is contextual because training duration differs.

Next run a separately named multi-epoch 640-pixel experiment with validation-only checkpoint selection. Preserve this pilot, inspect false positives/missed annotations, and compare a finer-feature backbone if localization stalls. Clean-board negatives, expert annotation review, external camera data and distribution review remain required for a public model.

## Verification and artifacts

- Reloading the saved checkpoint reproduced every validation prediction and all detection metrics exactly.
- Local SQLite MLflow run status was FINISHED; all 165 optimizer steps completed.
- No held-out test evaluation occurred, and the website stays in demo mode.
- [Protocol](../RESOLUTION.md#follow-up-one-epoch-higher-resolution-training-pilot), [run evidence](coco-resize640-epoch1.json), [comparison evidence](resolution-training-comparison.json).
- Training revision `074c1d205e10241a87ef090a3f2f379fc2e26c04`, clean at run start.
- Checkpoint SHA-256 `a22923cd7f6f4e1c7cc225a6f58edf640cabbbaf1a8d4b480d89cb5e8209f0e3`.
- Weights and full prediction files remain ignored in `ml/runs/coco-resize640-epoch1`.
