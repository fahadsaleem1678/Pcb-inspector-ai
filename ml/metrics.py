"""COCO metrics on full original images, including empty prediction sets."""

import contextlib
import io

import numpy as np
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval


def coco_metrics(samples, labels, predictions):
    expected_ids = set(range(len(samples)))
    if any(row["image_id"] not in expected_ids for row in predictions):
        raise ValueError("Prediction references an image outside the evaluated split")
    dataset = {
        "info": {},
        "images": [
            {"id": i, "width": sample.width, "height": sample.height}
            for i, sample in enumerate(samples)
        ],
        "categories": [{"id": i + 1, "name": label} for i, label in enumerate(labels)],
        "annotations": [],
    }
    for image_id, sample in enumerate(samples):
        for annotation in sample.annotations:
            b = annotation.bbox
            width, height = b.x2 - b.x1, b.y2 - b.y1
            dataset["annotations"].append(
                {
                    "id": len(dataset["annotations"]) + 1,
                    "image_id": image_id,
                    "category_id": annotation.class_id + 1,
                    "bbox": [b.x1, b.y1, width, height],
                    "area": width * height,
                    "iscrowd": 0,
                }
            )
    with contextlib.redirect_stdout(io.StringIO()):
        truth = COCO()
        truth.dataset = dataset
        truth.createIndex()
        if predictions:
            detected = truth.loadRes(predictions)
        else:
            detected = COCO()
            detected.dataset = {**dataset, "annotations": []}
            detected.createIndex()
        evaluator = COCOeval(truth, detected, "bbox")
        evaluator.params.imgIds = list(range(len(samples)))
        evaluator.evaluate()
        evaluator.accumulate()
        evaluator.summarize()

    def average(values):
        valid = values[values >= 0]
        return float(np.mean(valid)) if valid.size else None

    per_class = {}
    for i, name in enumerate(labels):
        precision = evaluator.eval["precision"][:, :, i, 0, -1]
        recall = evaluator.eval["recall"][:, i, 0, -1]
        per_class[name] = {
            "ap50_95": average(precision),
            "ap50": average(precision[0]),
            "ar100": average(recall),
            "instances": sum(a.class_id == i for s in samples for a in s.annotations),
            "positive_images": sum(any(a.class_id == i for a in s.annotations) for s in samples),
        }
    return {
        "ap50_95": average(evaluator.eval["precision"][:, :, :, 0, -1]),
        "ap50": average(evaluator.eval["precision"][0, :, :, 0, -1]),
        "ar100": average(evaluator.eval["recall"][:, :, 0, -1]),
        "per_class": per_class,
        "images": len(samples),
        "groups": len({sample.group_id for sample in samples}),
        "max_detections_per_image": 100,
        "metric_protocol": "pycocotools bbox; IoU 0.50:0.05:0.95; 101 recall points",
    }


def grouped_metrics(samples, labels, predictions):
    result = {}
    for group in sorted({sample.group_id for sample in samples}):
        indices = [i for i, sample in enumerate(samples) if sample.group_id == group]
        remap = {old: new for new, old in enumerate(indices)}
        rows = [
            {**row, "image_id": remap[row["image_id"]]}
            for row in predictions
            if row["image_id"] in remap
        ]
        result[group] = coco_metrics([samples[i] for i in indices], labels, rows)
    return result
