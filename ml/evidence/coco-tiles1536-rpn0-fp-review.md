# False-positive review of the corrected tile pilot

Visual inspection performed 2026-09-10; implementation and final checks completed 2026-09-11. This review changes neither model predictions nor the frozen labels.

## Context definitions

The existing descending-score, same-class, one-to-one IoU 0.5 matching is unchanged. Retained predictions now have stable original indices and explicit matching outcomes. For each unmatched prediction, assign exactly one context in this order:

1. **Duplicate:** same-class IoU >= 0.5 with a target already claimed by a higher-score prediction (stable input order resolves score ties).
2. **Class confusion:** no same-class match, but another-class label has IoU >= 0.5.
3. **Partial overlap:** overlap with any label is positive but below 0.5. This may be a localization problem or a coincidental overlap; the context does not establish a cause.
4. **No overlap:** zero overlap with all available labels. This does not establish a healthy region or complete annotation coverage.

## Fixed-score counts

| Score | Duplicate | Class confusion | Partial overlap | No overlap | Total FP |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.05 | 59 | 124 | 697 | 1139 | 2019 |
| 0.25 | 41 | 15 | 228 | 264 | 548 |
| 0.50 | 30 | 3 | 114 | 75 | 222 |

All prior per-board and per-class TP/FP/FN, precision/recall, missed boxes and class-agnostic coverage were reproduced exactly. These are diagnostic score thresholds, not product calibration.

At score 0.25, duplicates account for 41/548 false positives (7.5%). Partial/no-overlap cases account for 492/548 (89.8%). Duplicate suppression alone cannot resolve the majority. Duplicate context does not prove why a box survived tile merging; pairwise prediction overlap differs from overlap with a ground-truth label.

## Seven inspected regions

At score >= 0.5, select the highest-score false positive in each nonempty context within each validation family, resolving ties by image and original prediction index. Family 52 has no class-confusion case at that score, leaving seven cases. This selected sample is not a prevalence or completeness audit. Prediction numbers below are one-based; JSON indices are zero-based.

| Board / prediction | Predicted class | Score | Context | Visual observation |
| --- | --- | ---: | --- | --- |
| 017 / P4 | open_circuit | 0.917449 | duplicate | Multiple predicted boxes surround the same visible trace gap. The selected box overlaps a label already matched by a higher-score prediction; visual evidence is consistent with the duplicate context. |
| 013 / P3 | spur | 0.917944 | class_confusion | The selected spur box surrounds a broad bridge joining two vertical traces. Its best overlapping frozen label is short_circuit, so this is a class disagreement at the same visible feature. |
| 027 / P2 | open_circuit | 0.935737 | partial_overlap | A visible gap interrupts a horizontal trace. The selected open_circuit box is taller and narrower than the frozen label; it points at the gap but reaches only IoU 0.430455. |
| 023 / P5 | missing_pad | 0.873580 | no_overlap | The selected missing_pad box surrounds a solid rectangular terminal connected to a trace. No frozen label overlaps it. The intended pad shape and correctness need a board reference or expert review. |
| 039 / P3 | open_circuit | 0.920044 | duplicate | Multiple open_circuit boxes surround one visible gap in a horizontal trace. A higher-score box has already matched the label, leaving this selected box as a duplicate. |
| 032 / P2 | spur | 0.950478 | partial_overlap | The selected spur box surrounds a copper protrusion beneath a horizontal trace. Its frozen label is larger; IoU 0.499693 falls just below the unchanged 0.5 matching threshold. |
| 034 / P3 | missing_pad | 0.917218 | no_overlap | The selected missing_pad box surrounds a circular pad partly obscured by a dark irregular feature. The image alone does not establish missing-pad damage versus occlusion or an imaging artifact. No frozen label overlaps it. |

The 032 spur case has IoU 0.499693, which must remain below the unchanged matching threshold. The viewer now shows six decimals so it does not misleadingly display 0.500. No metric uses rounded values.

The two no-overlap missing-pad regions need expert/reference review: a solid trace terminal and a circular pad obscured by a dark feature do not independently establish missing-pad damage or healthy-board status. No annotations were added or corrected.

## Review workflow and next work

Select **False positives** in the review menu, then filter by score, class or context. Lists and board navigation rank by the highest qualifying score; **Highest-score false positive** jumps to the strongest remaining case. All annotation classes stay visible, including in class-filtered prediction review. Select a prediction to focus its original-coordinate box and inspect its best same-class and any-class overlaps.

Annotation and prediction notes have separate identities, even when their indices coincide. Schema 1.1 exports include the subject, source/checkpoint/prediction/matching hashes, and threshold/overlap context captured when the note was written. Notes remain in browser memory until exported.

Next add explicit optimizer-step budgeting and run the prespecified whole-board 640 control at 1,053 steps with training RPN threshold zero and final-budget checkpoint selection. This is not yet implemented or executed. Keep independent expert completeness review and external/clean-board data work separate. Do not change thresholds or labels based on these seven selected examples.

## Evidence

- [Context counts](coco-tiles1536-rpn0-fp-context.json), [source-bound visual observations](coco-tiles1536-rpn0-fp-review.json).
- Local package: `ml/runs/review-fp-003`, served at loopback port 8768 during this session. All source images and screenshots remain local.
- Regression checks cover stable identities, matching priority, empty truth, score ties and exact IoU boundaries. Browser checks cover note isolation, original threshold/context, filters, score navigation, coordinates, zoom, accessibility and mobile overflow.
