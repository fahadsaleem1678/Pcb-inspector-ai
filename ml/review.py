"""Build an offline, validation-only annotation/prediction review package."""

import argparse
import json
import shutil
from pathlib import Path

from ml.data import file_hash, verify_release
from ml.error_analysis import THRESHOLDS, match_image
from ml.summarize import summarize
from pcb_inspector.datasets import contained


def script_json(value):
    # JSON in an inert script still needs HTML end-tag escaping.
    return (
        json.dumps(value, allow_nan=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_boards(samples, classes, predictions):
    if any(s.split != "validation" for s in samples):
        raise ValueError("Review includes an image outside validation")
    by_image = {i: [] for i in range(len(samples))}
    for p in predictions:
        if p["image_id"] not in by_image:
            raise ValueError("Review prediction lies outside validation")
        by_image[p["image_id"]].append(p)
    boards = []
    for i, sample in enumerate(samples):
        truth = [
            {
                "category_id": a.class_id + 1,
                "bbox": [a.bbox.x1, a.bbox.y1, a.bbox.x2 - a.bbox.x1, a.bbox.y2 - a.bbox.y1],
            }
            for a in sample.annotations
        ]
        profiles = {str(t): match_image(truth, by_image[i], t, len(classes)) for t in THRESHOLDS}
        boards.append(
            {
                "image": sample.image,
                "group": sample.group_id,
                "width": sample.width,
                "height": sample.height,
                "asset": f"images/board-{i:03d}.jpg",
                "source_sha256": sample.sha256,
                "annotations": truth,
                "predictions": by_image[i],
                "profiles": profiles,
            }
        )
    return sorted(boards, key=lambda b: (-len(b["profiles"]["0.25"]["missed_indices"]), b["image"]))


def build(args):
    if args.output.exists():
        raise ValueError("Review output already exists")
    evidence = summarize(args.run)
    manifest, digest = verify_release(args.manifest, args.root, args.release)
    if (
        digest != evidence["manifest_sha256"]
        or manifest.classes != evidence["configuration"]["classes"]
    ):
        raise ValueError("Review release differs from model evidence")
    samples = [s for s in manifest.samples if s.split == "validation"]
    saved = json.loads((args.run / "best-validation.json").read_text(encoding="utf-8"))
    if [s.image for s in samples] != saved["source_images"]:
        raise ValueError("Review source image order differs")
    boards = build_boards(samples, manifest.classes, saved["predictions"])
    payload = {
        "schema_version": "1.0",
        "run": args.run.name,
        "classes": manifest.classes,
        "checkpoint_sha256": evidence["checkpoint_sha256"],
        "manifest_sha256": digest,
        "prediction_sha256": file_hash(args.run / "best-validation.json"),
        "generator_sha256": file_hash(__file__),
        "split": "validation",
        "boards": boards,
    }
    template = Path(__file__).with_name("review.html")
    payload["template_sha256"] = file_hash(template)
    args.output.mkdir(parents=True)
    try:
        (args.output / "images").mkdir()
        for board in boards:
            destination = args.output / board["asset"]
            shutil.copyfile(contained(args.root, board["image"]), destination)
            if file_hash(destination) != board["source_sha256"]:
                raise ValueError("Copied image checksum mismatch")
        html = template.read_text(encoding="utf-8").replace("__REVIEW_DATA__", script_json(payload))
        (args.output / "index.html").write_text(html, encoding="utf-8")
        (args.output / "provenance.json").write_text(
            json.dumps(
                {
                    **{k: v for k, v in payload.items() if k != "boards"},
                    "images": [
                        {k: b[k] for k in ["image", "asset", "source_sha256"]} for b in boards
                    ],
                    "html_sha256": file_hash(args.output / "index.html"),
                    "purpose": "Local research review; notes do not alter the frozen release",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except BaseException:
        (args.output / "INCOMPLETE.txt").write_text(
            "Generation failed. Do not use this review.", encoding="utf-8"
        )
        raise
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/pcb-defect-v1.0.json")
    )
    parser.add_argument("--root", type=Path, default=Path("data/processed/pcb-defect-v1"))
    parser.add_argument("--release", type=Path, default=Path("data/releases/pcb-defect-v1"))
    result = build(parser.parse_args())
    print(f"Review generated for {len(result['boards'])} validation boards")


if __name__ == "__main__":
    main()
