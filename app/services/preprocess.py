"""
Image preprocessing for scanned answer sheets.

Deliberately thin: since grading reads the image directly (no separate OCR
stage), preprocessing's only job is to make sure the vision model sees a
correctly-oriented, legible, reasonably-sized image — not to do handwriting-
specific work like binarization, which a modern vision LLM doesn't need and
can actively hurt (it can destroy pen-stroke detail OCR engines rely on).
"""

from __future__ import annotations

import io
import logging

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.exceptions import InvalidImageError

logger = logging.getLogger(__name__)

_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def preprocess_image(raw_bytes: bytes, max_dimension: int) -> bytes:
    """
    Validate and prepare an uploaded image for grading.

    Steps:
    1. Decode and validate it's actually a readable image.
    2. Apply EXIF orientation (phone photos are frequently rotated in the
       file's metadata rather than the pixel data — skip this and the image
       silently uploads sideways).
    3. Downscale if larger than max_dimension on the long edge.
    4. Apply mild contrast/sharpness correction for faint pencil or low-light
       scans.
    5. Re-encode as JPEG for consistent, compact upload size.

    Raises InvalidImageError on anything that isn't a decodable image.
    """
    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()
    except UnidentifiedImageError as exc:
        raise InvalidImageError("File is not a readable image.") from exc
    except OSError as exc:
        raise InvalidImageError(f"Could not decode image: {exc}") from exc

    if image.format not in _ALLOWED_FORMATS:
        raise InvalidImageError(
            f"Unsupported image format '{image.format}'. "
            f"Allowed: {', '.join(sorted(_ALLOWED_FORMATS))}."
        )

    image = ImageOps.exif_transpose(image)
    if image is None:
        raise InvalidImageError("Image has no readable pixel data.")

    image = image.convert("RGB")
    image = _downscale(image, max_dimension)
    image = _enhance_contrast(image)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90, optimize=True)
    logger.debug(
        "Preprocessed image: %dx%d, %d bytes", image.width, image.height, buffer.tell()
    )
    return buffer.getvalue()


def _downscale(image: Image.Image, max_dimension: int) -> Image.Image:
    longest_edge = max(image.width, image.height)
    if longest_edge <= max_dimension:
        return image
    scale = max_dimension / longest_edge
    new_size = (round(image.width * scale), round(image.height * scale))
    return image.resize(new_size, Image.LANCZOS)


def _enhance_contrast(image: Image.Image) -> Image.Image:
    """CLAHE (adaptive histogram equalization) on the luminance channel only,
    so faint pencil writing or uneven scan lighting becomes more legible
    without blowing out color or introducing halo artifacts a global
    contrast stretch would cause."""
    array = np.array(image)
    lab = cv2.cvtColor(array, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)

    merged = cv2.merge((l_channel, a_channel, b_channel))
    result = cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)
    return Image.fromarray(result)
