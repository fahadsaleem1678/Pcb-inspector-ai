"""Explicitly unreviewed DsPCBSD+ research preparation and bounded training."""

import argparse
import hashlib
import importlib.metadata
import json
import random
import subprocess
import time
import zipfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from ml.candidate_audit import digest, member_bytes, normalize_border_rounding
from ml.candidate_decisions import load_packet, read_json

CLASSES = ["SH", "SP", "SC", "OP", "MB", "HB", "CS", "CFO", "BMFO"]
SEED = 20260915


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )


def select_validation(rows, count, seed):
    ordered = sorted(rows, key=lambda r: hashlib.sha256(f"{seed}:{r['file']}".encode()).hexdigest())
    if count < 16 * len(CLASSES) or count > len(rows):
        raise ValueError("Validation count must cover class sampling and fit source")
    selected = {}
    for category in range(1, len(CLASSES) + 1):
        matches = [
            r for r in ordered if any(a["category_id"] == category for a in r["annotations"])
        ]
        if len(matches) < 16:
            raise ValueError("Insufficient source validation class coverage")
        selected.update((r["file"], r) for r in matches[:16])
    for row in ordered:
        if len(selected) >= count:
            break
        selected[row["file"]] = row
    return sorted(selected.values(), key=lambda r: r["file"])


def prepare(args):
    if args.output.exists():
        raise ValueError("Research data output already exists")
    packet, _, packet_hash = load_packet(args.packet, args.summary)
    if packet["source"] != "DsPCBSD+":
        raise ValueError("This research experiment supports DsPCBSD+ only")
    if (
        digest(args.inventory) != packet["binding"]["inventory_sha256"]
        or digest(args.audit) != packet["binding"]["audit_sha256"]
    ):
        raise ValueError("Research source hash mismatch")
    audit, inventory = read_json(args.audit), read_json(args.inventory)
    if digest(args.raw) != audit["archive_sha256"]:
        raise ValueError("Source archive hash mismatch")
    if [audit["statistics"]["classes"][str(i)]["name"] for i in range(1, 10)] != CLASSES:
        raise ValueError("Unexpected source class mapping")
    members = {m["image_id"]: m for m in packet["members"]}
    quarantine = set()
    for case in packet["review"]["near_duplicate_cases"]:
        for key in ("first", "second"):
            member = members[case[key]]
            if member["source_split"] == "train":
                quarantine.add(member["file"])
    for group in packet["groups"]:
        if group["crosses_source_splits"]:
            quarantine.update(
                members[i]["file"]
                for i in group["image_ids"]
                if members[i]["source_split"] == "train"
            )
    rows = inventory["images"]
    train = [r for r in rows if r["split"] == "train" and r["file"] not in quarantine]
    validation = select_validation([r for r in rows if r["split"] == "validation"], 256, SEED)
    if {r["pixel_sha256"] for r in train} & {r["pixel_sha256"] for r in validation}:
        raise ValueError("Exact pixel duplicate remains across research partitions")
    corrections, samples = [], []
    with zipfile.ZipFile(args.raw) as archive:
        # Only a fresh, ignored research dataset is written. Reviewed release files are not used.
        args.output.mkdir(parents=True)
        (args.output / "images").mkdir()
        for row in train + validation:
            raw = member_bytes(archive, row["member"])
            if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("Image differs from audited inventory")
            annotations = []
            for index, annotation in enumerate(row["annotations"]):
                original = annotation["bbox"]
                box = normalize_border_rounding(original, row["width"], row["height"])
                if box != original:
                    corrections.append(
                        {
                            "file": row["file"],
                            "split": row["split"],
                            "annotation_index": index,
                            "before": original,
                            "after": box,
                        }
                    )
                annotations.append({"category_id": annotation["category_id"], "bbox": box})
            asset = "images/" + row["sha256"] + ".jpg"
            (args.output / asset).write_bytes(raw)
            samples.append(
                {
                    **{k: row[k] for k in ("file", "split", "sha256", "width", "height")},
                    "asset": asset,
                    "annotations": annotations,
                }
            )
    manifest = {
        "schema_version": "unreviewed-research-1",
        "source": "DsPCBSD+",
        "classes": CLASSES,
        "seed": SEED,
        "samples": samples,
        "quarantined_train_files": sorted(quarantine),
        "experimental_border_corrections": corrections,
        "packet_sha256": packet_hash,
        "inventory_sha256": digest(args.inventory),
        "archive_sha256": digest(args.raw),
        "source_declared_license": "CC BY 4.0",
        "expert_review_completed": False,
        "user_authorization": (
            "Proceed with experimental training while expert review remains pending"
        ),
        "production_eligible": False,
        "promotion_eligible": False,
        "group_independence_verified": False,
        "validation_policy": (
            "Fixed 256 public-val images, >=16 positive images per source class; "
            "seeded SHA256 ranking"
        ),
        "quarantine_policy": (
            "Exclude train endpoints of all audited cross-split dHash candidates and "
            "exact/pair-linked cross-split groups; heuristic precaution, not proof of independence"
        ),
        "summary": {
            "train_images": len(train),
            "validation_images": len(validation),
            "quarantined_train_images": len(quarantine),
            "corrections": len(corrections),
            "validation_annotations_per_class": dict(
                Counter(str(a["category_id"]) for r in validation for a in r["annotations"])
            ),
        },
    }
    write_json(args.output / "research-manifest.json", manifest)
    print(json.dumps(manifest["summary"]), flush=True)


def tensor_sample(row, root):
    import torch
    from PIL import Image
    from torchvision.transforms.functional import pil_to_tensor

    with Image.open(root / row["asset"]) as image:
        tensor = pil_to_tensor(image.convert("RGB")).float() / 255
    boxes = [[x, y, x + w, y + h] for x, y, w, h in (a["bbox"] for a in row["annotations"])]
    return tensor, {
        "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
        "labels": torch.tensor([a["category_id"] for a in row["annotations"]], dtype=torch.int64),
    }


def evaluate(model, rows, root):
    import torch
    from torchvision.ops import batched_nms

    from ml.metrics import coco_metrics

    model.eval()
    model.rpn.score_thresh = 0.05
    samples, predictions = [], []
    with torch.inference_mode():
        for i, row in enumerate(rows):
            annotations = []
            for a in row["annotations"]:
                x, y, w, h = a["bbox"]
                annotations.append(
                    SimpleNamespace(
                        class_id=a["category_id"] - 1,
                        bbox=SimpleNamespace(x1=x, y1=y, x2=x + w, y2=y + h),
                    )
                )
            samples.append(
                SimpleNamespace(
                    width=row["width"],
                    height=row["height"],
                    group_id="public-validation-independence-unverified",
                    annotations=annotations,
                )
            )
            tensor, _ = tensor_sample(row, root)
            output = model([tensor])[0]
            keep = batched_nms(output["boxes"], output["scores"], output["labels"], 0.5)[:100]
            for index in keep.tolist():
                x, y, right, bottom = output["boxes"][index].tolist()
                predictions.append(
                    {
                        "image_id": i,
                        "category_id": int(output["labels"][index]),
                        "bbox": [x, y, right - x, bottom - y],
                        "score": float(output["scores"][index]),
                    }
                )
    metrics = coco_metrics(samples, CLASSES, predictions)
    metrics.pop("groups")
    metrics["independent_group_count"] = None
    return {
        "metrics": metrics,
        "predictions": predictions,
        "source_images": [r["file"] for r in rows],
    }


def train(args):
    import torch

    from ml.baseline import configure, make_model, training_mode
    from ml.pretrained import verify_weights

    if args.output.exists():
        raise ValueError("Training output already exists")
    if digest(args.data / "research-manifest.json") != args.manifest_sha256:
        raise ValueError("Research manifest differs from pinned hash")
    manifest = read_json(args.data / "research-manifest.json")
    if manifest["schema_version"] != "unreviewed-research-1" or manifest["classes"] != CLASSES:
        raise ValueError("Wrong research data schema/classes")
    for row in manifest["samples"]:
        if digest(args.data / row["asset"]) != row["sha256"]:
            raise ValueError("Research image hash mismatch")
    if args.steps < 1 or args.steps > 5000:
        raise ValueError("Use an explicit bounded 1..5000-step research budget")
    configure(SEED, 2, "cpu")
    train_rows = [r for r in manifest["samples"] if r["split"] == "train"]
    val_rows = [r for r in manifest["samples"] if r["split"] == "validation"]
    if not train_rows or len(val_rows) != 256:
        raise ValueError("Missing training pool or fixed validation subset")
    config = {
        "schema_version": "unreviewed-research-run-1",
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("torch", "torchvision", "numpy", "pycocotools", "pillow")
        },
        "classes": CLASSES,
        "manifest_sha256": digest(args.data / "research-manifest.json"),
        "initial_weights": verify_weights(args.weights),
        "steps": args.steps,
        "batch_size": 2,
        "input_size": args.input_size,
        "learning_rate": 0.005,
        "seed": SEED,
        "threads": 2,
        "device": "cpu",
        "selection": "fixed_final_step_no_checkpoint_search",
        "promotion_eligible": False,
        "expert_review_completed": False,
        "code_hashes": {
            name: digest(Path(__file__).with_name(name))
            for name in ["research_dsp.py", "baseline.py", "metrics.py", "pretrained.py"]
        },
    }
    args.output.mkdir(parents=True)
    write_json(args.output / "config.json", config)
    model = make_model(9, args.input_size, "frozen_batch", args.weights)
    print("Evaluating initialized nine-class head on fixed public-validation subset", flush=True)
    initial = evaluate(model, val_rows, args.data)
    write_json(args.output / "initial-validation.json", initial)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.005, momentum=0.9, weight_decay=0.0005)
    rng, order, history, exposures = random.Random(SEED), [], [], Counter()
    start = time.perf_counter()
    for step in range(1, args.steps + 1):
        if len(order) < 2:
            order.extend(rng.sample(range(len(train_rows)), len(train_rows)))
        selected = [order.pop(), order.pop()]
        items = [tensor_sample(train_rows[i], args.data) for i in selected]
        training_mode(model, 0.0)
        loss_dict = model([item[0] for item in items], [item[1] for item in items])
        loss = sum(loss_dict.values())
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite research training loss")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0, error_if_nonfinite=True)
        optimizer.step()
        exposures.update(
            str(a["category_id"]) for i in selected for a in train_rows[i]["annotations"]
        )
        history.append(
            {
                "step": step,
                "loss": float(loss.detach()),
                "images": [train_rows[i]["file"] for i in selected],
            }
        )
        if step % 25 == 0 or step == 1 or step == args.steps:
            progress = {
                "step": step,
                "budget": args.steps,
                "loss": history[-1]["loss"],
                "elapsed_seconds": time.perf_counter() - start,
            }
            write_json(args.output / "progress.json", progress)
            print(json.dumps(progress), flush=True)
    torch.save(
        {
            "model": model.state_dict(),
            "classes": CLASSES,
            "config": config,
            "promotion_eligible": False,
        },
        args.output / "final-research.pt",
    )
    write_json(args.output / "training-history.json", history)
    print("Evaluating final research checkpoint", flush=True)
    final = evaluate(model, val_rows, args.data)
    write_json(args.output / "final-validation.json", final)
    # Independent reload verifies that the saved artifact reproduces the reported predictions.
    reloaded = make_model(9, args.input_size, "frozen_batch")
    reloaded.load_state_dict(
        torch.load(args.output / "final-research.pt", weights_only=True)["model"]
    )
    reproduced = evaluate(reloaded, val_rows, args.data)
    if reproduced != final:
        raise ValueError("Reloaded research checkpoint does not reproduce evaluation")
    result = {
        "initial_metrics": initial["metrics"],
        "final_metrics": final["metrics"],
        "completed_steps": args.steps,
        "training_class_exposures": dict(exposures),
        "checkpoint_sha256": digest(args.output / "final-research.pt"),
        "manifest_sha256": config["manifest_sha256"],
        "reload_predictions_identical": True,
        "elapsed_seconds": time.perf_counter() - start,
        "production_eligible": False,
        "expert_review_completed": False,
        "project_test_holdout_inferred": False,
        "website_model_changed": False,
    }
    write_json(args.output / "result.json", result)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "train"))
    parser.add_argument("--allow-unreviewed-research", action="store_true", required=True)
    for name in ("packet", "summary", "inventory", "audit", "raw", "data", "weights"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--input-size", type=int, choices=(320, 640), default=320)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        if any(
            getattr(args, k) is None for k in ("packet", "summary", "inventory", "audit", "raw")
        ):
            parser.error(
                "Preparation requires bound packet, summary, inventory, audit and raw archive"
            )
        prepare(args)
    else:
        if args.data is None or args.weights is None or not args.manifest_sha256:
            parser.error("Training requires data, pinned manifest hash and local weights")
        train(args)


if __name__ == "__main__":
    main()
