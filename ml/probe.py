"""Validation-only transform probe of a fixed checkpoint; never trains or evaluates test."""

import argparse
import importlib.metadata
import json
import subprocess
from pathlib import Path

import torch

from ml.baseline import PACKAGES, configure, infer, make_model, write_json
from ml.data import BoardViews, file_hash, verify_release
from ml.summarize import summarize

PROFILES = [
    {"name": "control-320", "input_size": 320, "tile_size": 0, "overlap": 256},
    {"name": "resize-640", "input_size": 640, "tile_size": 0, "overlap": 256},
    {"name": "tiles-1536-at-640", "input_size": 640, "tile_size": 1536, "overlap": 256},
]


def verify_control(reference, result):
    if reference["source_images"] != result["source_images"]:
        raise ValueError("Control validation source order differs")
    if reference["predictions"] != result["predictions"]:
        raise ValueError("Control predictions differ from source run")
    for key in ["ap50_95", "ap50", "ar100", "per_class", "by_group"]:
        if reference["metrics"][key] != result["metrics"][key]:
            raise ValueError(f"Control metrics differ: {key}")


def probe(args):
    if args.output.exists():
        raise ValueError("Probe output already exists; choose a new directory")
    # Requires a complete full run, checksum-bound artifacts and successful validation reload.
    source = summarize(args.run)
    config = json.loads((args.run / "config.json").read_text(encoding="utf-8"))
    if (config["input_size"], config["tile_size"], config["overlap"]) != (320, 0, 256):
        raise ValueError("Probe requires the 320-pixel whole-image baseline")
    manifest, digest = verify_release(args.manifest, args.root, args.release)
    if digest != source["manifest_sha256"] or manifest.classes != config["classes"]:
        raise ValueError("Probe data does not match source checkpoint")
    device = configure(config["seed"], args.threads, "cpu")
    metadata = {
        "schema_version": "1.0",
        "purpose": "validation-only fixed-checkpoint transform probe",
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "git_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "code_hashes": {
            name: file_hash(Path(__file__).with_name(name))
            for name in ["probe.py", "baseline.py", "data.py", "metrics.py", "summarize.py"]
        },
        "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
        "source_run": str(args.run.resolve()),
        "source_config_sha256": file_hash(args.run / "config.json"),
        "checkpoint_sha256": source["checkpoint_sha256"],
        "manifest_sha256": digest,
        "classes": manifest.classes,
        "profiles": PROFILES,
        "device": "cpu",
        "threads": args.threads,
        "seed": config["seed"],
        "test_evaluated": False,
        "promotion_eligible": False,
        "limitations": [
            "Inference transform shift only; no higher-resolution training is measured.",
            "One checkpoint and two validation groups; selection can overfit validation.",
            "Not a calibrated model or a clean-negative/external-camera evaluation.",
        ],
    }
    args.output.mkdir(parents=True)
    write_json(args.output / "config.json", metadata)
    reference = json.loads((args.run / "best-validation.json").read_text(encoding="utf-8"))
    results = []
    try:
        for profile in PROFILES:
            print(json.dumps({"profile_started": profile["name"]}), flush=True)
            model = make_model(
                len(manifest.classes), profile["input_size"], config.get("normalization", "batch")
            )
            model.load_state_dict(
                torch.load(args.run / "best-state.pt", map_location="cpu", weights_only=True),
                strict=True,
            )
            model.to(device)
            data = BoardViews(
                manifest, args.root, "validation", profile["tile_size"], profile["overlap"]
            )
            metrics, predictions = infer(model, data, manifest.classes, device)
            result = {
                "profile": profile,
                "metrics": metrics,
                "predictions": predictions,
                "source_images": [s.image for s in data.samples],
                "views": len(data),
            }
            if profile["name"] == "control-320":
                verify_control(reference, result)
            path = args.output / f"{profile['name']}.json"
            write_json(path, result)
            results.append(
                {
                    "profile": profile,
                    "metrics": metrics,
                    "views": len(data),
                    "images": len(data.samples),
                    "prediction_count": len(predictions),
                    "result_sha256": file_hash(path),
                }
            )
            print(
                json.dumps(
                    {
                        "profile_complete": profile["name"],
                        "ap50": metrics["ap50"],
                        "ap50_95": metrics["ap50_95"],
                        "ar100": metrics["ar100"],
                    }
                ),
                flush=True,
            )
            del model
        summary = {
            **metadata,
            "status": "complete",
            "control_reproduced_exactly": True,
            "config_sha256": file_hash(args.output / "config.json"),
            "results": results,
        }
        write_json(args.output / "summary.json", summary)
        return summary
    except BaseException as exc:
        write_json(
            args.output / "failure.json",
            {
                "status": "failed",
                "completed_profiles": len(results),
                "error_type": type(exc).__name__,
                "message": str(exc),
                "promotion_eligible": False,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/pcb-defect-v1.0.json")
    )
    parser.add_argument("--root", type=Path, default=Path("data/processed/pcb-defect-v1"))
    parser.add_argument("--release", type=Path, default=Path("data/releases/pcb-defect-v1"))
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.threads <= 32:
        parser.error("Threads must be 1-32")
    probe(args)


if __name__ == "__main__":
    main()
