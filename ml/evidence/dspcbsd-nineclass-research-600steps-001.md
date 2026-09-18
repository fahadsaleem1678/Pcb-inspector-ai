# DsPCBSD+ nine-class research: 600-step result

Completed the explicitly authorized unreviewed-data experiment; results verified 2026-09-18.
The model learned useful signals, but detection performance remains weak and uneven. This
is a separate nine-class research checkpoint, not a replacement for the website model or
a production qualification result. AP is a detection metric, not the percentage of boards
correctly inspected.

| Metric | Initialized head | After 600 steps |
| --- | ---: | ---: |
| AP50 | 0.87% | 23.23% |
| AP50:95 | 0.25% | 9.09% |
| AR100 | 9.34% | 29.79% |

## Per-class validation

| Source class | Validation boxes | AP50 | AP50:95 |
| --- | ---: | ---: | ---: |
| SH - Short | 27 | 22.33% | 6.10% |
| SP - Spur | 107 | 7.62% | 2.18% |
| SC - Spurious copper | 30 | 24.09% | 9.42% |
| OP - Open | 50 | 14.72% | 2.48% |
| MB - Mouse bite | 64 | 5.15% | 1.29% |
| HB - Hole breakout | 95 | 69.63% | 38.28% |
| CS - Conductor scratch | 45 | 29.37% | 10.81% |
| CFO - Conductor foreign object | 48 | 12.85% | 4.40% |
| BMFO - Base-material foreign object | 38 | 23.26% | 6.86% |

Hole breakout performs best. Mouse bite and spur are particularly weak; their AP50 scores
are only 5.15% and 7.62%. These weaknesses rule out treating the aggregate improvement as
evidence of dependable inspection. No confidence threshold or automatic board-acceptance
policy was selected.

## What ran

- Code revision: ee3071b. Fixed final-step selection, no checkpoint search.
- 600 SGD updates, two images per update, 1,200 distinct training images; all nine source
  classes appeared in training. This covers about 15.1% of the 7,936-image training pool,
  not a full epoch or proof of convergence.
- Frozen 256-image publisher-validation subset with 504 annotations, with class-aware
  selection and no verified independent physical-board count.
- 272 training images implicated in potential cross-split similarity were quarantined; actual
  training exposure contains no quarantined or validation image.
- 304 tiny boundary clips recorded in the research data as experimental preprocessing.
  Original source labels and all expert-review records remain unchanged.
- COCO initialization, new nine-class head, input size 320, frozen normalization, seed
  20260915, CPU / two threads, SGD lr 0.005, momentum 0.9 and weight decay 0.0005.
- Training took about 26.7 minutes. Training plus final evaluation/reload verification took 27.8
  minutes, excluding the initial evaluation and data-integrity startup checks.

## Verification and artifacts

231 ML tests passed before execution; lint and formatting passed. The saved checkpoint was
reloaded during the run and reproduced every final prediction and metric exactly. At result
export, both metric sets were independently recomputed from saved predictions. Manifest,
checkpoint and code hashes, 600 sequential history entries, all-nine-class exposure and
1,200 distinct source-separated training images were checked. No additional training or
model inference was needed to export the report.

Checkpoint SHA256: 14c40280b6e5e3989370ececf261c89738dc46dc57a2e0a984aedca4757ddf1b.

[Machine-readable evidence](dspcbsd-nineclass-research-600steps-001.json) binds the dataset,
configuration, checkpoint, history, predictions and results. Full artifacts remain local:
`ml/runs/dspcbsd-nineclass-research-600steps-001/`, including `final-research.pt`,
`final-validation.json`, `initial-validation.json` and `training-history.json`.
Preparation and commands are documented in [the research protocol](../UNREVIEWED_RESEARCH.md).

## Limits and next experiment

These source crops, classes and validation images differ from the existing six-class PCB
benchmark, so the scores cannot be compared directly to its tile-model scores. Validation
labels are unreviewed and the sample is class-aware; it does not establish population-level
accuracy. Exact/similarity quarantine does not establish physical-board independence.
No clean-board or target-camera qualification data is present. The acceptable defective-board
escape rate is still undecided. Production eligibility remains false.

The next useful step is error analysis of the saved predictions, especially mouse bite and
spur: distinguish missing detections, class confusion and poor box localization before
choosing a longer-budget or higher-resolution experiment. Additional unreviewed research
is allowed by the user; expert review is not being reintroduced as a prerequisite to that
research. It remains a separate limitation for production qualification.

The website model, existing six-class release and original project test holdout are unchanged.
No code or checkpoint was pushed to GitHub.

Follow-up: [saved-prediction error diagnosis](dspcbsd-nineclass-errors-001.md).
