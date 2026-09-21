# Model and research tools

## Portfolio model

The app supports the completed nine-class DsPCBSD+ research checkpoint:
Faster R-CNN MobileNetV3 320 FPN, COCO initialization, 3,968 optimizer steps, batch two,
seed 20260915. All 7,936 training images were used once. The fixed 256-image validation
subset contains 504 annotations. Labels were not expert-reviewed; group independence and
clean-board performance are unverified.

| Metric | Result |
| --- | ---: |
| AP50 | 45.97% |
| AP50:95 | 19.91% |
| AR100 | 36.65% |

Classes: short, spur, spurious copper, open, mouse bite, hole breakout, conductor scratch,
conductor foreign object and base-material foreign object. These remain distinct from the
older six-class PCB-Defect dataset.

[Verified result](evidence/dspcbsd-nineclass-research-3968steps-001.md),
[run evidence](evidence/dspcbsd-nineclass-research-3968steps-001.json),
[error diagnostics](evidence/dspcbsd-nineclass-fullpass-errors-001.json), and
[frozen data evidence](evidence/dspcbsd-unreviewed-research-data-001.json) support the benchmark.
The app displays scores >=0.25 for demonstration; it makes no board pass/fail decision.
Training is stopped. The cancelled 640-pixel run produced no final checkpoint.

## Local inference

Install the optional ML runtime separately from the service environment:

```powershell
python -m venv .venv-ml
.venv-ml\Scripts\python.exe -m pip install torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cpu
.venv-ml\Scripts\python.exe -m pip install -c requirements.lock -c ml/requirements.lock -r ml/requirements.txt -e ".[dev]"
```

Supply the existing checkpoint at
`ml/runs/dspcbsd-nineclass-research-3968steps-001/final-research.pt`, then:

```powershell
$env:PCB_DETECTOR="research"
$env:PCB_RESEARCH_CHECKPOINT="ml/runs/dspcbsd-nineclass-research-3968steps-001/final-research.pt"
.venv-ml\Scripts\python.exe scripts/dev.py
```

The adapter checks SHA256
`1427332c3633582f34f1262ebbfaf3c832a411118412bcb2a359df8149c3c87e`
before loading. It never downloads weights. The checkpoint and source images are ignored;
a fresh Git clone alone cannot run trained inference. See [hosting](../docs/portfolio-deployment.md).

## Offline tooling

Research code remains available for reproducibility and testing; running the app does not
start training. Each CLI exposes its arguments through `python -m ml.MODULE --help`.

| Modules | Purpose |
| --- | --- |
| `research_dsp`, `research_errors` | Nine-class experimental preparation, training and saved-prediction analysis |
| `baseline`, `data`, `metrics`, `schedule`, `summarize`, `probe` | Six-class baseline, tiled views and reproducible evaluation |
| `candidate_audit`, `candidate_manifest`, `candidate_viewer` | Source-label audits and visual review packages |
| `candidate_decisions`, `candidate_derive`, `review`, `adjudication` | Human review import and versioned correction candidates |
| `error_analysis`, `qualification` | Error context and evidence-based qualification checks |
| `pretrained` | Explicit acquisition and verification of initialization weights |

The [initialization provenance record](PRETRAINED.md) is hashed by `pretrained.py` and must
remain intact. [Dataset records](../data/README.md) preserve source metadata and the frozen
six-class release. Review and qualification tools do not fabricate expert approvals.

```powershell
.venv-ml\Scripts\python.exe -m pytest tests/test_ml_views.py ml/tests tests/test_portfolio.py -q
```

Historical plans, handoffs and superseded experiment reports were removed from the working
repository; prior commits retain that history. Current benchmark evidence remains versioned.
