# Dataset records

Raw images and processed datasets are local, ignored artifacts. This directory keeps the
schemas, provenance and frozen release records used by the research tools.

- [Source metadata and checksums](source-lock.json)
- [Manifest schema](manifest.schema.json) and [template](manifest.template.json)
- [Six-class PCB-Defect release](releases/pcb-defect-v1/README.md) used by the older baseline
- [Nine-class model and data evidence](../ml/README.md) used by the portfolio adapter

The source datasets have different label spaces; do not merge them by numeric category ID.
Recorded permissions and grouping reviews apply to their specific source artifacts. They
do not establish industrial inspection quality or blanket rights to redistribute imagery.

Validate an actual manifest and local image root with:

```sh
python -m pcb_inspector.datasets PATH_TO_MANIFEST --root PATH_TO_IMAGES --purpose research --output .runtime/dataset-validation.json
```

The template intentionally needs real source, review and sample records before it can pass.
Training and deployment do not download datasets automatically.
