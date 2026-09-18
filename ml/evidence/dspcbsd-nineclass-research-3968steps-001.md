# Full-pass nine-class research result

Verified 2026-09-19. This is unreviewed research, not a production release.

| Metric | 600 steps, 320 pixels | 3,968 steps, 320 pixels |
| --- | ---: | ---: |
| AP50 | 23.23% | 45.97% |
| AP50:95 | 9.09% | 19.91% |
| AR100 | 29.79% | 36.65% |

The full pass used all 7,936 training images exactly once. Its first 600 steps match
control image order and losses exactly; initialized validation predictions also match.
All nine classes were exposed. Manifest, prediction and checkpoint hashes were verified;
metrics were independently recomputed from saved predictions. The runner independently
reloaded the checkpoint and reproduced final predictions exactly. Reported elapsed time
was 13,071 seconds, excluding initialization and initial evaluation.

At score 0.25 and IoU 0.5, overall counts improved from 145 TP / 518 FP / 359 FN
to 298 TP / 578 FP / 206 FN. Mouse bite still misses 45 of 64 annotations
(19 TP, 77 FP); spur misses 62 of 107 (45 TP, 204 FP). These are annotation-level
counts, not defective-board escape rates. At score 0.05 mouse-bite recall is 50%
and spur recall 54.21%, with precision near 6% for each. Lowering the threshold
alone does not establish acceptable performance.

Mouse-bite AP50 is 16.32%; spur AP50 is 17.17%. Confidence, classification and
localization problems remain. Diagnostic reason categories describe saved predictions,
not causal proof; predictions are already capped and filtered by the detector.

Next authorized experiment: input short side 640 (maximum long side 1,280), same
3,968 steps, batch two, seed 20260915, initialization, optimizer and frozen data split.
Default input remains 320. Final-step progress logging is also corrected, without
changing optimization. Evaluate the fixed final checkpoint and compare metrics and
fixed-threshold errors; do not choose production thresholds on this subset.

The fixed 256-image validation subset has 504 annotations and unreviewed labels.
Group independence is unverified and clean-board coverage is absent. Expert review and
the acceptable board-escape target remain unresolved. Website and production gates are unchanged.

Evidence: [run verification](dspcbsd-nineclass-research-3968steps-001.json) and
[bound error diagnostics](dspcbsd-nineclass-fullpass-errors-001.json).
