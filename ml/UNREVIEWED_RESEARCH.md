# Explicitly unreviewed DsPCBSD+ research

On 2026-09-15 the user said they have no expert reviewer and explicitly agreed to proceed
with experimental training. This authorizes a separate research path; it does not invent
expert decisions or change the reviewed-release validator, existing model, or production gates.

The experiment retains all nine DsPCBSD+ source categories. It does not mix these into the
six-class PCB-Defect model, rename hole breakout to missing pad, or fabricate clean negatives.
The source declares CC BY 4.0; source/initial-weight distribution rights remain as previously
recorded. Checkpoints and data remain local ignored artifacts.

## Frozen experiment

- 7,936 publisher-training images after quarantining 272 train endpoints of audited
  cross-split similarity cases. No publisher-validation image enters training.
- A fixed 256-image subset of publisher validation, selected by seeded SHA256 ranking
  with at least 16 positive images for every class. Remaining publisher-validation images
  are not evaluated in this run. There is no independent DsPCBSD+ test partition here.
- 304 box corrections in the selected train/validation data are deterministic border clips
  of at most 0.02 pixels. Before/after coordinates are preserved. These are explicitly
  experimental preprocessing, not expert-approved corrections. Source archives stay intact.
- COCO-initialized Faster R-CNN MobileNetV3 320 FPN, new nine-class head, frozen batch
  normalization, CPU with two threads, seed 20260915, batch size two, 600 optimizer steps,
  SGD learning rate 0.005 / momentum 0.9 / weight decay 0.0005; training RPN cutoff zero.
- Evaluate initialization and the fixed final step on the same subset. No validation-based
  checkpoint search or threshold tuning. Reload the saved model and reproduce final predictions.

The 600 steps expose 1,200 training images: an initial learning experiment, not a completed
pass over the whole dataset or evidence of convergence. The class-aware validation sample
is not an unbiased production prevalence sample. Similarity quarantine is a conservative
heuristic, not proof of independent physical boards. No target-camera/clean-board evidence
or accepted defective-board escape-rate target is supplied by this experiment.

Data evidence: [frozen research data](evidence/dspcbsd-unreviewed-research-data-001.json).
The separate manifest schema is unreviewed-research-1 and cannot masquerade as a reviewed
DatasetManifest release. Train requires explicit opt-in and the exact pinned manifest hash.

```powershell
.venv-ml\Scripts\python.exe -m ml.research_dsp train --allow-unreviewed-research --data data/processed/dspcbsd-unreviewed-research-001 --manifest-sha256 1bee207587d9793402d9292c47e004b8d0de7c926ce52775298884dbf610b90f --weights ml/weights/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth --steps 600 --output ml/runs/dspcbsd-nineclass-research-600steps-001
```

Use a fresh output directory only for an intentionally authorized new run; do not rerun
completed experiments just to recreate reports. The existing project test holdout is not
loaded or inferred. The website remains unchanged and all artifacts remain promotion-ineligible.

## Completed result

The 600-step run completed and was verified on 2026-09-18. AP50 improved from 0.87% to
23.23%; AP50:95 reached 9.09%. See the [full result and per-class limits](evidence/dspcbsd-nineclass-research-600steps-001.md).
Do not rerun the command above to reproduce this report; preserve the completed run.
