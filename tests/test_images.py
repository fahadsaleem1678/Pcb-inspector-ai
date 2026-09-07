import io

import pytest
from PIL import Image, PngImagePlugin
from pydantic import ValidationError

from pcb_inspector.config import Settings
from pcb_inspector.images import InvalidImage, validate_image
from pcb_inspector.storage import LocalObjectStore


def image_bytes(size=(128, 96), fmt="PNG", **kwargs):
    output = io.BytesIO()
    Image.new("RGB", size).save(output, fmt, **kwargs)
    return output.getvalue()


@pytest.mark.parametrize(
    "content", [b"", b"bad image", image_bytes(fmt="GIF"), image_bytes((8, 8))]
)
def test_rejects_unsupported_and_invalid_images(settings, content):
    with pytest.raises(InvalidImage):
        validate_image(content, settings)


def test_limits_pixels_dimensions_and_truncated_images(settings, png):
    with pytest.raises(InvalidImage):
        validate_image(png, settings.model_copy(update={"max_image_pixels": 10000}))
    with pytest.raises(InvalidImage):
        validate_image(png, settings.model_copy(update={"max_image_dimension": 100}))
    with pytest.raises(InvalidImage):
        validate_image(png[:40], settings)


def test_orientation_and_metadata_removal(settings):
    exif = Image.Exif()
    exif[274] = 6
    result = validate_image(image_bytes(fmt="JPEG", exif=exif), settings)
    assert (result.width, result.height) == (96, 128)
    assert not Image.open(io.BytesIO(result.content)).getexif()
    info = PngImagePlugin.PngInfo()
    info.add_text("private", "remove me")
    result = validate_image(image_bytes(pnginfo=info), settings)
    assert "private" not in Image.open(io.BytesIO(result.content)).info


def test_rejects_animation(settings):
    output = io.BytesIO()
    Image.new("RGB", (128, 96)).save(
        output,
        "PNG",
        save_all=True,
        append_images=[Image.new("RGB", (128, 96), "red")],
    )
    with pytest.raises(InvalidImage, match="Animated"):
        validate_image(output.getvalue(), settings)


def test_object_store_containment_and_replace(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    for key in ["../escape.png", str(tmp_path / "outside.png"), "."]:
        with pytest.raises(ValueError):
            store.put(key, b"bad")
    store.put("a/image.png", b"first")
    store.put("a/image.png", b"second")
    assert store.get("a/image.png") == b"second"
    assert not list(store.root.rglob("*.tmp"))


def test_nonlocal_and_real_detector_configuration_fail_closed():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, detector="yolo")
