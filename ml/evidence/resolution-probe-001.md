# Resolution and tiling validation probe

Completed 2026-09-09 using the selected epoch-four checkpoint from the five-epoch COCO run. All three profiles use the same weights and 32 validation boards. The original control reproduced saved predictions and detection metrics exactly.

| Profile | Views | AP50 | AP50:95 | AR100 | Mean seconds/board |
| --- | ---: | ---: | ---: | ---: | ---: |
| control-320 | 32 | 1.7526% | 0.7614% | 3.1077% | 1.043 |
| resize-640 | 32 | 3.1264% | 0.3870% | 2.4943% | 1.420 |
| tiles-1536-at-640 | 160 | 1.5970% | 0.4333% | 1.7568% | 4.599 |

Higher-resolution inference increased AP50 but reduced AP50:95 and recall. Tiled inference reduced all three aggregate detection metrics and increased runtime. These results do not justify switching the deployed transform; there is still no approved real detector.

Latency includes image decode, crops, inference, transfers and merging, without warmup exclusion. Results describe this CPU run, not a hardware-independent speed estimate. Unit tests overlapped part of the tiled run, so its measured latency is not an isolated benchmark.

## Geometry and training workload

The [metadata diagnostic](resolution-workload.json) estimates visible defect size after each transform. It takes the best visible crop for each original target, rather than treating overlapping annotations as extra independent defects. Ideal floating-point resize sizes are approximate; they do not measure detector coverage.

At 320 pixels, 203/232 validation targets have a short side below 16 pixels; at 640 this falls to 58. With 1536-pixel tiles at 640, only 8 targets remain below 16 in their best visible crop. Despite these larger targets, the fixed checkpoint did not improve on AP50:95. Training at the changed scale therefore needs its own experiment.

Tiling increases training views from 165 to 1,053, including 111 empty crops and 2,774 annotation fragments. Validation uses 160 crops but still evaluates the 232 original targets across 32 original boards. Empty crops inherit the source annotation-completeness limitation; they are not independently verified clean boards.

## Scope and provenance

- [Prespecified protocol and training pilot](../RESOLUTION.md).
- [Machine-readable results](resolution-probe-001.json), including per-class/group metrics and hashes.
- This was an inference-only diagnostic; weights were never updated during the probe.
- No test images were evaluated. Validation selection is not external validation or model promotion.
- The [separate one-epoch training result](coco-resize640-epoch1.md) measures learning at 640 pixels; do not infer it from this probe.
