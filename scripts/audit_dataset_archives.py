"""Inspect the two pinned Mendeley archives without extracting or modifying source data.

This is an acquisition audit, not a training manifest or a license approval tool.
"""

import argparse
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from statistics import mean

from PIL import Image, ImageDraw, ImageStat

SOURCES = {
    "defect": "a5fb17e7009f96ffdb833cd9309b36da775545c8cc36a6dca3a8e9b4fbcb5f2a",
    "mixed": "e8a92347fccc3eed28c6a3d9df8455499a96619d6a1cbfea141af834e04c2ae7",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def audit(path, name, output):
    import zipfile

    archive_hash = digest(path)
    if archive_hash != SOURCES[name]:
        raise ValueError(f"{name}: archive differs from audited source revision")
    issues = []
    records = []
    annotations = defaultdict(list)
    image_metadata = {}
    categories = {}
    licenses = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP member names")
        if sum(i.file_size for i in archive.infolist()) > 1_000_000_000:
            raise ValueError("Expanded archive exceeds audit limit")
        for member in archive.infolist():
            parts = PurePosixPath(member.filename).parts
            if member.file_size > 80_000_000 or ".." in parts:
                raise ValueError("Unsafe or oversized archive member")
        image_names = sorted(n for n in names if n.lower().endswith((".jpg", ".jpeg", ".png")))
        if name == "defect":
            coco = json.loads(archive.read("PCB_Defect/annotation/_annotations.coco.json"))
            categories = {str(c["id"]): c["name"] for c in coco["categories"]}
            licenses = coco["licenses"]
            ids = {im["id"]: im for im in coco["images"]}
            if len(ids) != len(coco["images"]):
                raise ValueError("Duplicate COCO image IDs")
            if len({a["id"] for a in coco["annotations"]}) != len(coco["annotations"]):
                raise ValueError("Duplicate COCO annotation IDs")
            for im in ids.values():
                key = "PCB_Defect/images/" + im["file_name"]
                if key in image_metadata:
                    raise ValueError("Duplicate COCO filename")
                image_metadata[key] = im
            for ann in coco["annotations"]:
                if ann["image_id"] not in ids or str(ann["category_id"]) not in categories:
                    raise ValueError("Unresolved COCO annotation reference")
                key = "PCB_Defect/images/" + ids[ann["image_id"]]["file_name"]
                x, y, w, h = ann["bbox"]
                annotations[key].append((str(ann["category_id"]), [x, y, x + w, y + h]))
            if set(image_metadata) != set(image_names):
                raise ValueError("COCO images do not match archive images")
        else:
            # This archive has numeric YOLO labels but no class-name map.
            issues.append(
                {"code": "missing_class_map", "detail": "Do not infer class IDs from filenames."}
            )
        byte_groups = defaultdict(list)
        pixel_groups = defaultdict(list)
        family_groups = defaultdict(list)
        class_counts = Counter()
        split_class_counts = defaultdict(Counter)
        box_fractions = []
        sheets = []
        for index, member in enumerate(image_names):
            raw = archive.read(member)
            byte_hash = hashlib.sha256(raw).hexdigest()
            with Image.open(io.BytesIO(raw)) as source:
                if source.width * source.height > 40_000_000:
                    raise ValueError("Image exceeds offline audit pixel limit")
                source.load()
                im = source.convert("RGB")
                orientation = source.getexif().get(274, 1)
            width, height = im.size
            split = PurePosixPath(member).parts[-3] if name == "mixed" else "unassigned"
            if name == "mixed":
                label = (
                    member.rsplit("/images/", 1)[0]
                    + "/labels/"
                    + PurePosixPath(member).stem
                    + ".txt"
                )
                if label not in names:
                    issues.append({"code": "missing_label", "image": member})
                else:
                    for line_no, line in enumerate(
                        archive.read(label).decode("utf-8").splitlines(), 1
                    ):
                        values = line.split()
                        if len(values) != 5:
                            issues.append(
                                {"code": "invalid_yolo_line", "image": member, "line": line_no}
                            )
                            continue
                        category, cx, cy, w, h = map(float, values)
                        if (
                            not all(math.isfinite(v) for v in (category, cx, cy, w, h))
                            or category < 0
                            or not category.is_integer()
                        ):
                            issues.append(
                                {"code": "invalid_yolo_values", "image": member, "line": line_no}
                            )
                            continue
                        box = [
                            (cx - w / 2) * width,
                            (cy - h / 2) * height,
                            (cx + w / 2) * width,
                            (cy + h / 2) * height,
                        ]
                        annotations[member].append((str(int(category)), box))
            elif (width, height) != (
                image_metadata[member]["width"],
                image_metadata[member]["height"],
            ):
                issues.append({"code": "dimension_mismatch", "image": member})
            if orientation != 1:
                issues.append({"code": "exif_orientation", "image": member, "value": orientation})
            for category, box in annotations[member]:
                x1, y1, x2, y2 = box
                if not all(math.isfinite(v) for v in box) or not (
                    0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height
                ):
                    issues.append({"code": "out_of_bounds_box", "image": member, "bbox": box})
                else:
                    box_fractions.append((x2 - x1) * (y2 - y1) / (width * height))
                class_counts[category] += 1
                split_class_counts[split][category] += 1
            pixel_hash = hashlib.sha256(f"{width}x{height}:".encode() + im.tobytes()).hexdigest()
            byte_groups[byte_hash].append(member)
            pixel_groups[pixel_hash].append(member)
            family = PurePosixPath(member).name.split(".rf.")[0]
            family_groups[family].append(member)
            tiny = im.resize((32, 32)).convert("L")
            record = {
                "image": member,
                "width": width,
                "height": height,
                "split": split,
                "sha256": byte_hash,
                "pixel_sha256": pixel_hash,
                "annotation_count": len(annotations[member]),
                "mean_luminance": round(ImageStat.Stat(tiny).mean[0], 2),
                "source_name_hint": image_metadata.get(member, {}).get("extra", {}).get("name"),
                "exceeds_upload_20mp": width * height > 20_000_000,
            }
            records.append(record)
            # Evenly spaced files for visual review; not a representative statistical sample.
            step = max(1, len(image_names) // 12)
            if index % step == 0 and len(sheets) < 12:
                scale = min(300 / width, 250 / height)
                thumb = im.resize((round(width * scale), round(height * scale)))
                cell = Image.new("RGB", (320, 300), "white")
                cell.paste(thumb, (10, 25))
                draw = ImageDraw.Draw(cell)
                draw.text((10, 5), f"{name} #{index} {width}x{height}", fill="black")
                for category, (x1, y1, x2, y2) in annotations[member]:
                    draw.rectangle(
                        (10 + x1 * scale, 25 + y1 * scale, 10 + x2 * scale, 25 + y2 * scale),
                        outline="#ff2020",
                        width=2,
                    )
                    draw.text((10 + x1 * scale, 25 + y1 * scale), category, fill="#0044ff")
                draw.text(
                    (10, 278),
                    f"{split} / {len(annotations[member])} labels (source IDs)",
                    fill="black",
                )
                sheets.append(cell)
        duplicates = {
            "bytes": [g for g in byte_groups.values() if len(g) > 1],
            "pixels": [g for g in pixel_groups.values() if len(g) > 1],
        }
        split_by_name = {r["image"]: r["split"] for r in records}
        duplicate_cross_split = [
            g for g in duplicates["pixels"] if len({split_by_name[n] for n in g}) > 1
        ]
        family_cross_split = [
            g for g in family_groups.values() if len({split_by_name[n] for n in g}) > 1
        ]
        report = {
            "audit_version": 1,
            "source": name,
            "archive_sha256": archive_hash,
            "image_count": len(records),
            "annotation_count": sum(class_counts.values()),
            "categories": categories,
            "embedded_licenses": licenses,
            "class_counts_by_source_id": dict(class_counts),
            "split_counts": dict(Counter(r["split"] for r in records)),
            "split_class_counts_by_source_id": {k: dict(v) for k, v in split_class_counts.items()},
            "dimension_counts": dict(Counter(f"{r['width']}x{r['height']}" for r in records)),
            "megapixels": {
                "min": min(r["width"] * r["height"] / 1e6 for r in records),
                "max": max(r["width"] * r["height"] / 1e6 for r in records),
                "mean": mean(r["width"] * r["height"] / 1e6 for r in records),
            },
            "mean_image_luminance": mean(r["mean_luminance"] for r in records),
            "mean_box_area_fraction": mean(box_fractions) if box_fractions else None,
            "negative_images": sum(r["annotation_count"] == 0 for r in records),
            "over_upload_pixel_limit": sum(r["exceeds_upload_20mp"] for r in records),
            "duplicates": duplicates,
            "cross_split_pixel_duplicates": duplicate_cross_split,
            "cross_split_filename_family_candidates": family_cross_split,
            "issues": issues,
            "images": records,
            "ready_for_training": False,
            "limitations": [
                "Filename families are review candidates, not verified physical board IDs.",
                "No transformed near-duplicate, provenance, or annotation-completeness audit.",
                "Luminance and box size are descriptive statistics, not calibrated quality scores.",
                "No training splits or license approval created.",
            ],
        }
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{name}-audit.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        sheet = Image.new("RGB", (1280, 900), "#eeeeee")
        for i, cell in enumerate(sheets):
            sheet.paste(cell, ((i % 4) * 320, (i // 4) * 300))
        sheet.save(output / f"{name}-contact-sheet.png")
        summary = {
            k: report[k]
            for k in [
                "source",
                "image_count",
                "annotation_count",
                "categories",
                "class_counts_by_source_id",
                "split_counts",
                "megapixels",
                "negative_images",
                "over_upload_pixel_limit",
            ]
        }
        summary.update(
            issues=len(issues),
            byte_duplicate_groups=len(duplicates["bytes"]),
            pixel_duplicate_groups=len(duplicates["pixels"]),
            cross_split_pixel_duplicates=len(duplicate_cross_split),
            cross_split_family_candidates=len(family_cross_split),
        )
        print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/source-audit"))
    parser.add_argument("--output", type=Path, default=Path("data/interim/source-audit"))
    args = parser.parse_args()
    for name in SOURCES:
        audit(args.root / f"{name}.zip", name, args.output)


if __name__ == "__main__":
    main()
