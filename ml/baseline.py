"""Reproducible CPU/CUDA research baseline, with validation-only model selection."""

import argparse
import importlib.metadata
import json
import math
import os
import platform
import random
import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_320_fpn
from torchvision.ops import batched_nms

from ml.data import BoardViews, file_hash, restore_boxes, verify_release
from ml.metrics import coco_metrics, grouped_metrics

MODEL = "torchvision-fasterrcnn-mobilenet-v3-large-320-fpn"
PACKAGES = ["torch", "torchvision", "numpy", "pycocotools", "mlflow-skinny", "pillow"]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def make_model(classes, input_size):
    # Both None values are required: the factory otherwise defaults to ImageNet backbone weights.
    return fasterrcnn_mobilenet_v3_large_320_fpn(
        weights=None,
        weights_backbone=None,
        num_classes=classes + 1,
        min_size=input_size,
        max_size=input_size * 2,
        box_score_thresh=0.001,
        box_detections_per_img=100,
    )


def configure(seed, threads, device):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    if device == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA requested but unavailable")
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    return torch.device(device)


def synchronize(device):
    if device.type == "cuda":
        torch.cuda.synchronize()


def infer(model, dataset, labels, device):
    model.eval()
    predictions, timings = [], []
    with torch.inference_mode():
        for source_index, sample in enumerate(dataset.samples):
            synchronize(device)
            start = time.perf_counter()
            boxes, scores, categories = [], [], []
            for view_index in dataset.by_image[source_index]:
                tensor, _ = dataset[view_index]
                output = model([tensor.to(device)])[0]
                window = dataset.views[view_index][1]
                boxes.append(restore_boxes(output["boxes"], window))
                scores.append(output["scores"])
                categories.append(output["labels"])
            boxes, scores, categories = torch.cat(boxes), torch.cat(scores), torch.cat(categories)
            if not all(torch.isfinite(value).all() for value in (boxes, scores)):
                raise ValueError("Nonfinite model predictions")
            boxes[:, [0, 2]] = boxes[:, [0, 2]].clamp(0, sample.width)
            boxes[:, [1, 3]] = boxes[:, [1, 3]].clamp(0, sample.height)
            valid = (
                (boxes[:, 2] > boxes[:, 0])
                & (boxes[:, 3] > boxes[:, 1])
                & (categories >= 1)
                & (categories <= len(labels))
            )
            boxes, scores, categories = boxes[valid], scores[valid], categories[valid]
            keep = batched_nms(boxes, scores, categories, 0.5)[:100]
            for box, score, category in zip(
                boxes[keep].cpu().tolist(),
                scores[keep].cpu().tolist(),
                categories[keep].cpu().tolist(),
                strict=True,
            ):
                x1, y1, x2, y2 = box
                predictions.append(
                    {
                        "image_id": source_index,
                        "category_id": category,
                        "bbox": [x1, y1, x2 - x1, y2 - y1],
                        "score": score,
                    }
                )
            synchronize(device)
            timings.append((time.perf_counter() - start) * 1000)
    metrics = coco_metrics(dataset.samples, labels, predictions)
    metrics["by_group"] = grouped_metrics(dataset.samples, labels, predictions)
    metrics["latency_ms"] = {
        "mean": float(np.mean(timings)),
        "p50": float(np.percentile(timings, 50)),
        "p95": float(np.percentile(timings, 95)),
        "scope": "decode, crops, inference, transfer and NMS",
        "warmup_excluded": False,
        "device": str(device),
    }
    return metrics, predictions


def metadata(args, manifest, digest):
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        revision, dirty = "unavailable", None
    return {
        "schema_version": "1.0",
        "architecture": MODEL,
        "initialization": "random_no_download",
        "classes": manifest.classes,
        "manifest_sha256": digest,
        "manifest": str(args.manifest.resolve()),
        "root": str(args.root.resolve()),
        "release": str(args.release.resolve()),
        "git_revision": revision,
        "git_dirty": dirty,
        "code_hashes": {
            str(path): file_hash(path)
            for path in [
                Path(__file__),
                Path(__file__).with_name("data.py"),
                Path(__file__).with_name("metrics.py"),
            ]
        },
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
        "installed_distributions": {
            d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
        },
        "seed": args.seed,
        "threads": args.threads,
        "device": args.device,
        "input_size": args.input_size,
        "tile_size": args.tile_size,
        "overlap": args.overlap,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "smoke": args.smoke,
        "promotion_eligible": False,
        "limitations": [
            "Random initialization; a short run verifies plumbing, not trained inspection quality.",
            "Frozen holdouts have two conservative groups each; no reliable population-level CI.",
            "No clean-board negatives or external camera holdout; no electrical certification.",
            "Software license review is separate from any future pretrained-weight rights review.",
        ],
    }


def train(args):
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    import mlflow

    if args.output.exists():
        raise ValueError("Run output already exists; choose a new run directory")
    device = configure(args.seed, args.threads, args.device)
    manifest, digest = verify_release(args.manifest, args.root, args.release)
    train_data = BoardViews(
        manifest, args.root, "train", args.tile_size, args.overlap, 4 if args.smoke else None
    )
    validation_data = BoardViews(
        manifest, args.root, "validation", args.tile_size, args.overlap, 2 if args.smoke else None
    )
    config = metadata(args, manifest, digest)
    config["training_source_images"] = [s.image for s in train_data.samples]
    config["validation_source_images"] = [s.image for s in validation_data.samples]
    config["training_views"] = len(train_data)
    config["validation_views"] = len(validation_data)
    args.output.mkdir(parents=True)
    write_json(args.output / "config.json", config)
    mlflow.set_tracking_uri("sqlite:///" + (args.output / "mlflow.db").resolve().as_posix())
    experiment_id = mlflow.create_experiment(
        "pcb-defect-surface-baseline",
        artifact_location=(args.output / "artifacts").resolve().as_uri(),
    )
    mlflow.set_experiment(experiment_id=experiment_id)
    model = make_model(len(manifest.classes), args.input_size).to(device)
    optimizer = torch.optim.SGD(
        model.parameters(), lr=args.learning_rate, momentum=0.9, weight_decay=0.0005
    )
    completed_epochs, best_ap = 0, -1.0
    checkpoint = args.output / "best-state.pt"
    try:
        with mlflow.start_run(run_name=args.output.name) as run:
            mlflow.log_params(
                {
                    key: config[key]
                    for key in [
                        "architecture",
                        "initialization",
                        "manifest_sha256",
                        "seed",
                        "threads",
                        "device",
                        "input_size",
                        "tile_size",
                        "overlap",
                        "epochs",
                        "learning_rate",
                        "smoke",
                    ]
                }
            )
            mlflow.set_tags({"promotion_eligible": "false", "git_revision": config["git_revision"]})
            history = []
            for epoch in range(args.epochs):
                model.train()
                indices = list(range(len(train_data)))
                random.Random(args.seed + epoch).shuffle(indices)
                if args.smoke:
                    indices = indices[:2]
                losses, start = [], time.perf_counter()
                for step, index in enumerate(indices):
                    tensor, target = train_data[index]
                    target = {key: value.to(device) for key, value in target.items()}
                    loss_dict = model([tensor.to(device)], [target])
                    loss = sum(loss_dict.values())
                    if not torch.isfinite(loss):
                        raise ValueError("Nonfinite training loss")
                    optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(
                        model.parameters(), 10.0, error_if_nonfinite=True
                    )
                    optimizer.step()
                    losses.append(float(loss.detach()))
                    if step % 10 == 0 or step + 1 == len(indices):
                        print(
                            json.dumps(
                                {
                                    "epoch": epoch + 1,
                                    "step": step + 1,
                                    "steps": len(indices),
                                    "loss": losses[-1],
                                }
                            ),
                            flush=True,
                        )
                metrics, predictions = infer(model, validation_data, manifest.classes, device)
                completed_epochs += 1
                record = {
                    "epoch": completed_epochs,
                    "train_loss": sum(losses) / len(losses),
                    "train_steps": len(indices),
                    "train_view_indices": indices,
                    "elapsed_seconds": time.perf_counter() - start,
                    "validation": metrics,
                }
                history.append(record)
                write_json(args.output / "history.json", history)
                mlflow.log_metrics(
                    {
                        "train_loss": record["train_loss"],
                        "val_ap50_95": metrics["ap50_95"],
                        "val_ap50": metrics["ap50"],
                        "val_ar100": metrics["ar100"],
                    },
                    step=completed_epochs,
                )
                if metrics["ap50_95"] > best_ap:
                    best_ap = metrics["ap50_95"]
                    torch.save(model.state_dict(), checkpoint)
                    write_json(
                        args.output / "best-validation.json",
                        {
                            "metrics": metrics,
                            "predictions": predictions,
                            "source_images": [s.image for s in validation_data.samples],
                        },
                    )
                    write_json(
                        args.output / "checkpoint.json",
                        {
                            "architecture": MODEL,
                            "classes": manifest.classes,
                            "manifest_sha256": digest,
                            "config_sha256": file_hash(args.output / "config.json"),
                            "state_sha256": file_hash(checkpoint),
                            "selected_epoch": completed_epochs,
                            "selection_metric": "validation_ap50_95",
                            "selection_value": best_ap,
                            "smoke": args.smoke,
                            "promotion_eligible": False,
                        },
                    )
                print(
                    json.dumps(
                        {
                            "epoch_complete": completed_epochs,
                            "validation_ap50_95": metrics["ap50_95"],
                            "smoke": args.smoke,
                        }
                    ),
                    flush=True,
                )
            summary = {
                "status": "complete",
                "completed_epochs": completed_epochs,
                "mlflow_run_id": run.info.run_id,
                "smoke": args.smoke,
                "checkpoint_sha256": file_hash(checkpoint),
                "best_validation_ap50_95": best_ap,
                "test_evaluated": False,
                "promotion_eligible": False,
            }
            write_json(args.output / "summary.json", summary)
            for filename in ["config.json", "history.json", "checkpoint.json", "summary.json"]:
                mlflow.log_artifact(str(args.output / filename))
    except BaseException as exc:
        write_json(
            args.output / "failure.json",
            {
                "status": "failed",
                "completed_epochs": completed_epochs,
                "error_type": type(exc).__name__,
                "message": str(exc),
                "promotion_eligible": False,
            },
        )
        raise
    return summary


def evaluate(args):
    run_dir = args.run
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    if summary["status"] != "complete":
        raise ValueError("Training run is incomplete")
    if args.split == "test" and (config["smoke"] or not args.final_test):
        raise ValueError("Test evaluation requires a full run and explicit --final-test")
    if checkpoint["config_sha256"] != file_hash(run_dir / "config.json"):
        raise ValueError("Configuration has changed since checkpoint creation")
    state_path = run_dir / "best-state.pt"
    if checkpoint["state_sha256"] != file_hash(state_path):
        raise ValueError("Checkpoint checksum mismatch")
    manifest, digest = verify_release(args.manifest, args.root, args.release)
    if digest != checkpoint["manifest_sha256"] or manifest.classes != checkpoint["classes"]:
        raise ValueError("Checkpoint and dataset label/release contracts differ")
    output = run_dir / f"{args.split}-evaluation.json"
    if output.exists():
        raise ValueError("Evaluation already exists; refusing to overwrite recorded results")
    device = configure(config["seed"], args.threads, args.device)
    model = make_model(len(manifest.classes), config["input_size"])
    model.load_state_dict(
        torch.load(state_path, map_location="cpu", weights_only=True), strict=True
    )
    model.to(device)
    data = BoardViews(
        manifest,
        args.root,
        args.split,
        config["tile_size"],
        config["overlap"],
        2 if config["smoke"] else None,
    )
    metrics, predictions = infer(model, data, manifest.classes, device)
    result = {
        "split": args.split,
        "evaluation_packages": {name: importlib.metadata.version(name) for name in PACKAGES},
        "evaluation_code_sha256": file_hash(__file__),
        "metrics": metrics,
        "predictions": predictions,
        "source_images": [s.image for s in data.samples],
        "checkpoint_sha256": checkpoint["state_sha256"],
        "manifest_sha256": digest,
        "smoke": config["smoke"],
        "promotion_eligible": False,
    }
    write_json(output, result)
    print(
        json.dumps(
            {"split": args.split, "ap50_95": metrics["ap50_95"], "images": len(data.samples)}
        )
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["train", "evaluate"])
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/pcb-defect-v1.0.json")
    )
    parser.add_argument("--root", type=Path, default=Path("data/processed/pcb-defect-v1"))
    parser.add_argument("--release", type=Path, default=Path("data/releases/pcb-defect-v1"))
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--input-size", type=int, default=320)
    parser.add_argument("--tile-size", type=int, default=0)
    parser.add_argument("--overlap", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=0.005)
    parser.add_argument("--seed", type=int, default=20260908)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--split", choices=["validation", "test"], default="validation")
    parser.add_argument("--final-test", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.threads <= 32 or not 1 <= args.epochs <= 1000:
        parser.error("Threads must be 1–32 and epochs 1–1000")
    if (
        not 128 <= args.input_size <= 2048
        or not math.isfinite(args.learning_rate)
        or args.learning_rate <= 0
    ):
        parser.error("Input size must be 128–2048 and learning rate finite and positive")
    if args.tile_size and not 0 <= args.overlap < args.tile_size:
        parser.error("Tile overlap must be nonnegative and smaller than tile size")
    if args.action == "train":
        if not args.output:
            parser.error("Training requires --output")
        train(args)
    else:
        if not args.run:
            parser.error("Evaluation requires --run")
        evaluate(args)


if __name__ == "__main__":
    main()
