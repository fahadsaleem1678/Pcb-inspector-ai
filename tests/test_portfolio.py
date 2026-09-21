import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from pcb_inspector.api import create_app
from pcb_inspector.config import Settings
from pcb_inspector.research_detector import CLASSES, ResearchDetector
from pcb_inspector.schemas import BoundingBox, Detection
from pcb_inspector.worker import Worker


def test_public_portfolio_cannot_share_local_identity():
    with pytest.raises(ValidationError, match="user isolation"):
        Settings(_env_file=None, environment="portfolio", auth_mode="local")


@pytest.mark.parametrize(
    "origin", ["*", "http://example.com", "https://example.com/", "https://u:p@example.com"]
)
def test_cors_rejects_unsafe_origins(origin):
    with pytest.raises(ValidationError, match="CORS origins"):
        Settings(_env_file=None, cors_origins=(origin,))


def test_cors_preflight_allows_only_configured_site(settings):
    from fastapi.testclient import TestClient

    settings.cors_origins = ("https://portfolio.example",)
    with TestClient(create_app(settings)) as client:
        for origin, expected in [
            ("https://portfolio.example", 200),
            ("https://other.example", 400),
        ]:
            response = client.options(
                "/api/v1/inspections/upload",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
            assert response.status_code == expected
            assert response.headers.get("access-control-allow-origin") == (
                origin if expected == 200 else None
            )


def test_invalid_checkpoint_fails_before_loading(tmp_path):
    checkpoint = tmp_path / "bad.pt"
    checkpoint.write_bytes(b"not a model")
    with pytest.raises(ValueError, match="checksum"):
        ResearchDetector(checkpoint)


@pytest.mark.parametrize("score, count", [(0.24, 0), (0.25, 1), (0.95, 1)])
def test_experimental_reports_never_accept_boards(client, app, settings, png, score, count):
    class Experimental:
        is_demo = True
        is_experimental = True
        version = "test-research"

        def predict(self, image):
            return [
                Detection(
                    defect_type="mouse_bite",
                    confidence=score,
                    bbox=BoundingBox(x1=1, y1=2, x2=20, y2=30),
                )
            ]

    job = client.post("/api/v1/inspections/upload", files={"file": ("board.png", png)}).json()[
        "inspection_id"
    ]
    Worker(app.state.repository, app.state.storage, settings, Experimental()).run_once()
    result = client.get(f"/api/v1/inspections/{job}/results").json()
    assert result["overall_result"] == "NOT_EVALUATED"
    assert result["is_experimental"] and result["is_demo"]
    assert len(result["detections"]) == count
    if count:
        assert result["detections"][0]["confidence_band"] == "review"
    downloaded = client.get(f"/api/v1/inspections/{job}/report")
    assert downloaded.status_code == 200
    assert downloaded.json() == result


def test_real_checkpoint_matches_saved_predictions_and_upload_pipeline(client, app, settings):
    checkpoint = Path("ml/runs/dspcbsd-nineclass-research-3968steps-001/final-research.pt")
    if not checkpoint.exists() or importlib.util.find_spec("torch") is None:
        pytest.skip("Requires the local research artifact and ML runtime")
    saved = json.loads((checkpoint.parent / "final-validation.json").read_text())
    data = Path("data/processed/dspcbsd-unreviewed-research-001")
    manifest = json.loads((data / "research-manifest.json").read_text())
    assets = {row["file"]: row["asset"] for row in manifest["samples"]}
    detector = ResearchDetector(checkpoint)
    for index in range(3):
        source = data / assets[saved["source_images"][index]]
        with Image.open(source) as image:
            predictions = detector.predict(image)
        expected = [p for p in saved["predictions"] if p["image_id"] == index]
        assert len(predictions) == len(expected)
        for prediction, reference in zip(predictions, expected, strict=True):
            assert CLASSES.index(prediction.defect_type) + 1 == reference["category_id"]
            assert prediction.confidence == reference["score"]
            box = prediction.bbox
            assert [box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1] == reference["bbox"]

    job = client.post(
        "/api/v1/inspections/upload", files={"file": (source.name, source.read_bytes())}
    ).json()["inspection_id"]
    Worker(app.state.repository, app.state.storage, settings, detector).run_once()
    result = client.get(f"/api/v1/inspections/{job}/results").json()
    assert result["model_version"] == detector.version
    assert result["is_experimental"] and result["overall_result"] == "NOT_EVALUATED"
    assert result["detections"]
    assert client.get(f"/api/v1/inspections/{job}/report").status_code == 200
