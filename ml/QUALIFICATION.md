# Model qualification: review flagged boards only

Started 2026-09-14. The user selected **only flagged boards get reviewed**, and answered
**not decided yet** for the acceptable defective-board escape rate. Those decisions are
recorded in qualification-policy-draft.json. No numeric production target is approved.

## Findings from the current checkpoints

The new validation-only audit verifies frozen source/model/reload evidence before using
saved predictions. It explores every distinct saved score plus 0 and 1, keeping equal scores
together. It records fixed diagnostic thresholds, per-class counts, board routing and group
coverage. It never changes a model, chooses a production threshold or evaluates test data.

| Tile operating point | Correct detections | False positives | Missed labels | Defective boards with no flag |
| --- | ---: | ---: | ---: | ---: |
| Score 0.25 | 186 | 548 | 46 | 0/32 |
| Score 0.50 | 172 | 222 | 60 | 0/32 |
| Score 0.90 | 77 | 16 | 155 | 0/32 |
| Score 0.95 | 22 | 2 | 210 | 12/32 |

Searching all global score thresholds on stored predictions, the tile model's maximum
label recall while attaining at least 90% detection precision is **16.38%**: 38 correct,
3 false detections, 194 missed labels, and **4/32 defective boards unflagged**. This occurs
at the exact stored score 0.9351373910903931. It is diagnostic development evidence, not a
recommended operating threshold. At least 80% precision permits at most 38.36% label recall.
The whole-board control reaches only 11.64% recall at the 90% precision floor and leaves
14/32 defective boards unflagged. Threshold adjustment alone does not meet a joint 90/90
precision/recall probe for either saved model. Those probes are not approved product targets.

Both models flag all 32 boards at scores 0.25 and 0.50. This does not establish safe
production routing: all boards in this validation set have labels, only two groups are
represented, and no verified clean-board false-flag rate can be measured. A wrong-class or
misplaced prediction can still flag a board. Therefore a flagged board must receive a full
inspection; checking only highlighted rectangles leaves unlocalized defects unreviewed.

Evidence:
- [Tile qualification audit](evidence/coco-tiles1536-rpn0-qualification-001.json)
- [Whole-board qualification audit](evidence/coco-resize640-rpn0-qualification-001.json)

## Qualification gates

| Gate | Required evidence | Current state |
| --- | --- | --- |
| Decision policy | Owner-approved board escape, clean-board false-flag, review-load and latency limits | Workflow chosen; limits undecided |
| Label quality | Independent whole-image completeness review, disagreements resolved, versioned corrections | Tooling exists; actual expert decisions missing |
| Real operating domain | Representative camera images, board/layout/batch lineage, quality conditions and rights | Missing |
| Clean negatives | Independently reviewed clean boards from the intended domain | Missing; empty tiles are not certified clean boards |
| Model/threshold selection | Validation tradeoffs, per-class/group checks, fixed artifact and transform hashes | Research evidence exists; no approved operating point |
| Final acceptance | Authorized untouched test evaluation under a prespecified protocol and target-domain holdout | Not performed |
| Runtime | Surface taxonomy adapter, quality/domain abstention, latency/load, monitoring and rollback | Not qualified; application remains demo-only |

Do not let a failed decode, low-quality image, unsupported board/domain or inference error
become an unflagged clearance. Quality/domain abstention must route to review or reject the
submission with an explicit reason. This is a proposed release requirement; no new real-model
routing has been enabled by this audit.

## Data work before the next training experiment

1. Review complete original train/validation images, including apparently normal areas, using
   the frozen manifest as the baseline. Prediction-driven notes alone do not prove completeness.
   The existing viewer/adjudication pipeline supports validation corrections; broader train
   label review must receive its own versioned release process. Keep test inspection/inference
   separate and do not use test cases to choose training examples or thresholds.
2. Collect original camera photographs of clean and defective boards from the intended line.
   Record physical board ID, layout, batch/session, camera and lighting, original SHA256,
   source/license/allowed use, reference evidence, reviewer and acquisition date. Include normal
   pads/traces/background patterns resembling current false positives. Do not relabel uncertain
   regions as clean merely because a model fires there or the source annotation is empty.
3. Have an independent reviewer establish clean/defective status and supported-class coverage.
   Group all captures/crops/augmentations of the same board and related acquisition lineage
   before splitting. Reserve external evaluation data before selecting hard negatives.
4. Freeze a new reviewed development release. Keep the current release and reported metrics
   immutable. If validation labels change, give the new benchmark a distinct name and reevaluate
   comparisons under it; do not mix old and corrected scores.

The next proposed training experiment is a **verified hard-negative inclusion comparison**:
retain the tile configuration/initial weights/seed/optimizer and 1,053-update endpoint budget;
compare the same reviewed development release with versus without eligible train-only clean
examples. Specify the inclusion/sampling schedule and class/group counts before starting.
Keep validation identical between arms, retain all real empty tiles, and report changed
positive/negative exposure. Evaluate both localization and board routing. No improvement is
assumed, and equal updates do not equal equal data exposure or compute. This experiment is
not executable yet because the required verified negative examples are absent.

More training on the same incomplete labels would not resolve the missing production evidence.
No extra full training run, automatic label correction or synthetic clean-board certification
was performed during this qualification slice.

## Acceptance sample planning

A planning helper calculates n = ceil(log(0.05) / log(1-p)) for a **one-sided 95% bound** with
zero observed escapes in independent defective-board trials. For illustration, an upper
escape bound of 1% needs 299 zero-escape trials; 0.1% needs 2,995. These are not user-approved
sample targets. The calculation follows the zero-failure case of exact binomial inference;
see [NIST's exact binomial bounds](https://itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbino.htm).

Independence, representative acquisition and a prespecified fixed policy matter. Repeated
crops or correlated layouts are not independent evidence. The current 32-board/two-group
validation set has been used for development; do not apply this bound to it as a release claim.
A clustered/multidomain acceptance design must be agreed once the target and deployment
population are known. Clean-board false flags require a separate verified negative sample.

## Reproduce the audit

Choose new output paths; existing reports cannot be overwritten:

```powershell
.venv/Scripts/python.exe -m ml.qualification --run ml/runs/coco-tiles1536-rpn0-epoch1 --output ml/runs/tile-qualification-new.json
.venv/Scripts/python.exe -m ml.qualification --run ml/runs/coco-resize640-rpn0-steps1053 --output ml/runs/whole-board-qualification-new.json
.venv-ml/Scripts/python.exe -m pytest tests/test_ml_views.py ml/tests -q
```

The sweep uses stable same-class one-to-one IoU >= 0.5 matches. Higher-score prefixes cannot
be changed by lower-score predictions; tests compare the optimized sweep against direct
matching, including tied scores and empty sets. Results are restricted to the saved model's
proposal filtering, NMS and maximum detection count. Scores are not calibrated probabilities.
The audit checks all release bytes for integrity but consumes validation predictions only.
