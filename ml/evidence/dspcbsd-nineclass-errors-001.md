# Nine-class research error diagnosis

Analyzed the existing 600-step predictions on 256 validation images / 504 source annotations.
No new training or model inference was performed. Source labels remain unreviewed.

## Fixed diagnostic thresholds

| Score cutoff | Correct detections | False positives | Missed labels | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.05 | 328 | 6774 | 176 | 4.62% | 65.08% |
| 0.25 | 145 | 518 | 359 | 21.87% | 28.77% |
| 0.5 | 112 | 203 | 392 | 35.56% | 22.22% |

These are label-level diagnostic counts at IoU >= 0.5, not board-acceptance rates.
No threshold was selected for production. There are no clean-board examples here.

## Mouse bite and spur

| Class | Score cutoff | TP / FP / FN | Precision | Recall |
| --- | --- | --- | ---: | ---: |
| MB | 0.05 | 28 / 835 / 36 | 3.24% | 43.75% |
| SP | 0.05 | 54 / 1539 / 53 | 3.39% | 50.47% |
| MB | 0.25 | 0 / 0 / 64 | undefined (no detections) | 0.00% |
| SP | 0.25 | 15 / 98 / 92 | 13.27% | 14.02% |
| MB | 0.5 | 0 / 0 / 64 | undefined (no detections) | 0.00% |
| SP | 0.5 | 0 / 0 / 107 | undefined (no detections) | 0.00% |

At cutoff 0.25, no mouse-bite prediction survives. Of 64 missed MB labels, 15 have a
high-overlap wrong-class prediction, 15 are assigned the score-suppressed category, five
have wrong-class partial overlap, and 29 have no useful retained detection under this
heuristic. The high-overlap confusions are 11 MB->SP, three MB->SC and one MB->CS.

At cutoff 0.25, spur has 15 correct detections and 92 misses: 35 score-suppressed, nine
high-overlap confusions (all SP->SC), four same-class localization errors, four wrong-class
partial overlaps, and 40 without a useful retained detection under the heuristic.

At cutoff 0.05, localization becomes more visible: 12 MB misses and 21 SP misses have
same-class boxes with IoU in [0.1, 0.5). Lowering the threshold yields only about 3% precision
for each class, so threshold adjustment alone is not an adequate remedy.

Many targets are narrow: 44/64 MB labels and 81/107 SP labels have a native short side below
16 pixels. This suggests a possible localization/resolution limitation, but does not isolate
its cause from limited training or source-label ambiguity. The first run exposed only
1,200 of 7,936 available training images.

## Visual spot check and method

Twelve deterministic examples were inspected with source boxes in red and selected saved
predictions in cyan. They show the reported wrong labels, low-score overlapping boxes and
partial box overlaps. This is a visual consistency check, not expert label certification.
[Local contact sheet](../runs/dspcbsd-nineclass-errors-001/weak-class-contact-sheet.jpg).

True/false counts reuse the tested score-ordered, one-to-one, same-class matcher. Miss causes
are assigned in this priority order: same-class matching competition; wrong-class IoU >=0.5;
same-class IoU >=0.5 below cutoff; retained same-class IoU >=0.1; retained wrong-class IoU
>=0.1; otherwise no useful saved detection. The three best-overlap contexts are retained
in case evidence. A prediction may explain more than one missed target; these explanation
counts are not a one-to-one confusion matrix or a causal diagnosis.

Saved outputs already have a score floor and 100-detection cap. Therefore a missing saved
box is not proof that the raw proposal network produced no candidate. Diagnostics never
infer unreviewed annotations to be correct. All counts conserve 504 targets across thresholds.

## Next controlled experiment

Prefer a fresh 3,968-step run at input size 320: batch size two covers the entire 7,936-image
training pool once. Keep initialization, seed, optimizer, quarantine and the same fixed
validation subset. This tests a larger training budget before changing image resolution.
The current checkpoint does not store optimizer state, so a true matched continuation
cannot be claimed; start from the same original COCO weights instead. The first 600 training
steps should reproduce the earlier experiment under the same runtime. Compare end metrics
and the same fixed-threshold diagnostics, without selecting a production threshold.

At the observed CPU rate, that full-pass experiment is estimated to take about three hours
plus evaluation; it has not been launched by this diagnostic step. A matched higher-resolution
experiment can follow if localization remains weak after the longer control.

## Reproduction and validation

```powershell
.venv\Scripts\python.exe -m ml.research_errors --run ml/runs/dspcbsd-nineclass-research-600steps-001 --manifest data/processed/dspcbsd-unreviewed-research-001/research-manifest.json --evidence ml/evidence/dspcbsd-nineclass-research-600steps-001.json --output ml/runs/dspcbsd-nineclass-errors-new
```

243 ML tests passed, including 12 diagnostic cases. Lint/format passed. Input manifest,
prediction hashes and validation ordering are checked against the committed training evidence.
[Bound diagnostics](dspcbsd-nineclass-errors-001.json) contain all classes and initialization/final
profiles; full case details stay in ignored local run artifacts. Original model/data files are
unchanged. The earlier result narrative incorrectly said 604 annotations; it is corrected to
504. Stored per-class metrics and training evidence always used the actual 504 annotations.
