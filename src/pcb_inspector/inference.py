from typing import Protocol

from PIL import Image

from pcb_inspector.schemas import Detection, Finding


class Detector(Protocol):
    @property
    def version(self) -> str: ...
    @property
    def is_demo(self) -> bool: ...
    def predict(self, image: Image.Image) -> list[Detection]: ...


class DemoDetector:
    """Exercises transport and persistence; makes no claim about the image."""

    version = "demo-no-model-0.1.0"
    is_demo = True

    def predict(self, image: Image.Image) -> list[Detection]:
        return []


def decide(
    detections: list[Detection], width: int, height: int, *, experimental: bool = False
) -> tuple[list[Finding], int]:
    """Provisional policy only; calibrate class-specific thresholds with validation data."""
    findings = []
    ignored = 0
    for detection in detections:
        if detection.bbox.x2 > width or detection.bbox.y2 > height:
            raise ValueError("Model output contains an out-of-bounds box")
        if detection.confidence < (0.25 if experimental else 0.70):
            ignored += 1
            continue
        critical = detection.defect_type in {"solder_bridge", "missing_component"}
        findings.append(
            Finding(
                **detection.model_dump(),
                severity="medium" if experimental else "critical" if critical else "high",
                confidence_band=(
                    "high" if not experimental and detection.confidence >= 0.90 else "review"
                ),
            )
        )
    return findings, ignored
