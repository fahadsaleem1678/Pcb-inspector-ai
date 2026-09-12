# Matched-step whole-board control result

Completed and verified 2026-09-12. The website remains demo-only.

The prespecified whole-board control completed exactly **1,053 optimizer updates**: six full
165-board passes plus the first 63 indices of the seventh seeded permutation. Only the final
endpoint was validated and selected. The selected checkpoint independently reproduced all
**3,182 predictions** and all aggregate/per-class/per-group detection metrics exactly.
MLflow status is FINISHED, with its sole training validation event at step 1,053.

Training revision: `c76479702c1a642878c3af78b2ae3ce0abbe7b99` (clean local commit).
Checkpoint SHA-256: `4dc04ed4a31e7630e929adc69139ba8e2130edc314fb7b1161b4dcf95c057824`.
MLflow run: `b4276b9d3ca84d16930b96cb1887d5d8`.

## Validation comparison

| Run | Updates | Training RPN | Selection opportunities | AP50 | AP50:95 | AR100 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Earlier whole-board 640 | 825 | 0.05 | 5 | 38.1599% | 13.5267% | 23.8448% |
| Tiles 1536 / input 640 | 1,053 | 0.00 | 1 | 63.1950% | 24.7772% | 40.0831% |
| Matched-step whole-board 640 | 1,053 | 0.00 | 1 | 45.8523% | 15.5973% | 26.6494% |

The matched-step control improves AP50:95 over the earlier whole-board run by **2.0706
percentage points**, while the tile pilot retains a **9.1799-point** lead over the new control.
Matching optimizer updates, training proposal filtering and a single endpoint selection
opportunity therefore does not remove the tile pilot's aggregate advantage in this experiment.
It does not establish that tiling alone caused the difference. The earlier whole-board
comparison also changes duration, proposal filtering and checkpoint-selection opportunities.

## Class and group results

| Class | Labels | Control AP50 | Control AP50:95 | Tile AP50:95 | Control AR100 |
| --- | ---: | ---: | ---: | ---: | ---: |
| missing_pad | 37 | 49.0175% | 22.0316% | 36.5561% | 32.4324% |
| mouse_bite | 43 | 20.9831% | 3.8322% | 8.2423% | 12.7907% |
| open_circuit | 38 | 40.7024% | 9.4142% | 15.4435% | 23.9474% |
| short_circuit | 38 | 53.6985% | 23.4301% | 33.2964% | 32.3684% |
| spur | 39 | 42.9687% | 14.3026% | 29.7308% | 25.3846% |
| spurious_copper | 37 | 67.7439% | 20.5731% | 25.3942% | 32.9730% |

The tile run has higher AP50:95 for all six classes. Mouse bites remain the weakest
class in both runs. AP50 for spurious copper is essentially tied (control 67.7439%,
tile 67.7067%); the aggregate comparison should not imply that every metric improved
for every class.

| Validation family | Control AP50 | Control AP50:95 | Tile AP50:95 |
| --- | ---: | ---: | ---: |
| pcb-defect-family-51 | 41.1827% | 12.6657% | 21.5215% |
| pcb-defect-family-52 | 56.9295% | 21.9012% | 30.6316% |

Both validation families favor tiles on AP50:95. There are only two conservative groups
and one training seed; these results do not establish population-level accuracy.

## Recall and false positives

Fixed diagnostic scores use descending-score, same-class, one-to-one matching at IoU 0.5.
These are not calibrated product operating thresholds.

| Score | Control TP | Control FP | Control FN | Control precision | Control recall | Tile TP / FP / FN |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0.05 | 152 | 804 | 80 | 15.90% | 65.52% | 198 / 2019 / 34 |
| 0.25 | 137 | 268 | 95 | 33.83% | 59.05% | 186 / 548 / 46 |
| 0.50 | 122 | 122 | 110 | 50.00% | 52.59% | 172 / 222 / 60 |

At score 0.25, tiles detect 49 more labeled defects (186 versus 137) with 280 more false
positives (548 versus 268). At score 0.5, tiles detect 50 more labels with 100 more false
positives. Better recall still carries a substantial false-positive cost.

Control FP contexts at score 0.25 are 21 duplicate, 7 class confusion, 150 partial overlap
and 90 no overlap. Thus 240/268 (89.6%) have partial or no overlap; duplicates alone
do not explain most errors. Contexts describe geometry against available labels, not
proven error causes. Annotation completeness remains unverified.

## What was matched and what still differs

The comparison verifies identical architecture, initialization bytes, frozen normalization,
six trainable backbone stages, class/manifest contracts, source ordering, seed 20260908,
640 input size, CPU/two threads, learning rate and package versions. Both use SGD momentum
0.9, weight decay 0.0005, gradient clipping 10, training RPN zero and inference RPN 0.05.
Both have one endpoint validation-selection opportunity at 1,053 updates. The control's
seeded schedule and the tile pilot's full seeded order were verified.

Equal optimizer steps do not make the data exposure equivalent:

| Exposure over 1,053 updates | Whole-board control | Tile pilot |
| --- | ---: | ---: |
| Distinct source boards | 165 | 165 |
| Source-view appearances per board | 6 or 7 | 2 to 20 |
| Labeled-box appearances | 7,849 | 2,774 |
| Clipped label appearances | 0 | 416 |
| Empty updates | 0 | 111 |

The control revisits complete boards; tile updates expose local crops at different effective
defect scale. Label appearances, clipping, background balance and per-board exposure differ.
The exposure audit is metadata-only and matches the frozen tile composition audit.

## Runtime, verification and stopping point

The control training loop, including final validation, took **64.61 minutes**
(3876.73 seconds), versus 42.92 minutes for the tile pilot.
Initial validation averaged 879.77 ms per original board;
independent reload averaged 1080.16 ms.
Timing includes decoding, crops, inference, transfers and NMS with no warmup excluded.
Machine load varied; these measured wall times are not an isolated compute benchmark.

Implementation verification: 105 ML tests passed, Ruff lint/format checks passed, and a
real five-update CPU smoke verified the partial-pass boundary and exact reload. Full-run
evidence checks confirm requested/actual/selected steps = 1,053, pass lengths
[165, 165, 165, 165, 165, 165, 63], one endpoint validation, and a checksum-bound history.
Legacy epoch evidence remains readable. See the [step-budget protocol](../BASELINE.md#exact-optimizer-step-budgets).

The implementation was committed cleanly before training. The planned pre-training push
was blocked by automatic approval review pending direct permission to update main; the
run therefore records a clean local revision. Export commands later encountered an approval
service usage limit and succeeded when the user asked to continue. Neither interruption
restarted or altered the completed training run.

This completes the single prescribed control and comparison. No further training, held-out
test inference, label/threshold changes or model promotion was performed. Expert annotation
review, clean-board negatives, an external-camera holdout and calibrated thresholds remain
qualification requirements.

## Evidence

- [Run evidence](coco-resize640-rpn0-steps1053.json).
- [Fixed-score errors and FP contexts](coco-resize640-rpn0-steps1053-errors.json).
- [Comparison, exposure audit and source hashes](coco-resize640-rpn0-steps1053-comparison.json).
- [Exact-budget smoke and legacy compatibility](step-budget-smoke-check.json).
- Local artifacts: `ml/runs/coco-resize640-rpn0-steps1053`; model weights and full predictions remain ignored.
