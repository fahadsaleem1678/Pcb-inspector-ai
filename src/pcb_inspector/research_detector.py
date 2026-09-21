"""Pinned research checkpoint adapter for portfolio demonstrations, never board acceptance."""

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image

from pcb_inspector.schemas import BoundingBox, DefectType, Detection

CHECKPOINT_SHA256 = "1427332c3633582f34f1262ebbfaf3c832a411118412bcb2a359df8149c3c87e"
SOURCE_CLASSES = ["SH", "SP", "SC", "OP", "MB", "HB", "CS", "CFO", "BMFO"]
CLASSES = [
    DefectType.SHORT,
    DefectType.SPUR,
    DefectType.SPURIOUS_COPPER,
    DefectType.OPEN,
    DefectType.MOUSE_BITE,
    DefectType.HOLE_BREAKOUT,
    DefectType.CONDUCTOR_SCRATCH,
    DefectType.CONDUCTOR_FOREIGN_OBJECT,
    DefectType.BASE_MATERIAL_FOREIGN_OBJECT,
]


class ResearchDetector:
    version = "dspcbsd-nineclass-320-3968-1427332c3633"
    is_demo = True
    is_experimental = True

    def __init__(self, checkpoint: Path) -> None:
        # Verify the approved artifact before torch deserialization; never download weights.
        with checkpoint.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != CHECKPOINT_SHA256:
                raise ValueError("Research checkpoint checksum mismatch")
        import torch
        from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_320_fpn
        from torchvision.ops import FrozenBatchNorm2d

        torch.set_num_threads(2)
        saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
        if (
            saved["classes"] != SOURCE_CLASSES
            or saved["config"]["input_size"] != 320
            or saved["config"]["steps"] != 3968
            or saved["promotion_eligible"] is not False
        ):
            raise ValueError("Unexpected research checkpoint configuration")
        self.model = fasterrcnn_mobilenet_v3_large_320_fpn(
            weights=None,
            weights_backbone=None,
            num_classes=10,
            min_size=320,
            max_size=640,
            rpn_score_thresh=0.05,
            box_score_thresh=0.001,
            box_detections_per_img=100,
        )

        def freeze(module: Any) -> None:
            for name, child in module.named_children():
                if isinstance(child, torch.nn.BatchNorm2d):
                    setattr(module, name, FrozenBatchNorm2d(child.num_features, eps=child.eps))
                else:
                    freeze(child)

        freeze(self.model.backbone)
        self.model.load_state_dict(saved["model"], strict=True)
        self.model.eval()

    def predict(self, image: Image.Image) -> list[Detection]:
        import torch
        from torchvision.transforms.functional import pil_to_tensor

        with torch.inference_mode():
            result = self.model([pil_to_tensor(image.convert("RGB")).float() / 255])[0]
        return [
            Detection(
                defect_type=CLASSES[int(label) - 1],
                confidence=float(score),
                bbox=BoundingBox(
                    x1=float(box[0]), y1=float(box[1]), x2=float(box[2]), y2=float(box[3])
                ),
            )
            for box, score, label in zip(
                result["boxes"], result["scores"], result["labels"], strict=True
            )
        ]
