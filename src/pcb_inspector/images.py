import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from pcb_inspector.config import Settings


class InvalidImage(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    width: int
    height: int


def validate_image(content: bytes, settings: Settings) -> ValidatedImage:
    """Decode content, enforce bounds, orient, and re-encode without source metadata."""
    if not content or len(content) > settings.max_upload_bytes:
        raise InvalidImage("Image is empty or exceeds the upload size limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG"}:
                    raise InvalidImage("Only JPEG and PNG images are supported")
                width, height = source.size
                if (
                    min(width, height) < settings.min_image_dimension
                    or max(width, height) > settings.max_image_dimension
                    or width * height > settings.max_image_pixels
                ):
                    raise InvalidImage("Image dimensions are outside the configured limits")
                if getattr(source, "n_frames", 1) != 1:
                    raise InvalidImage("Animated images are not supported")
                source.verify()
            with Image.open(io.BytesIO(content)) as source:
                oriented = ImageOps.exif_transpose(source).convert("RGB")
                # A new image discards EXIF, text, profiles and other source metadata.
                clean = Image.new("RGB", oriented.size)
                clean.paste(oriented)
                output = io.BytesIO()
                clean.save(output, format="PNG")
                return ValidatedImage(output.getvalue(), *clean.size)
    except InvalidImage:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidImage("Image cannot be safely decoded") from exc
