import io

import pytest
from PIL import Image

from app.core.exceptions import InvalidImageError
from app.services.preprocess import preprocess_image


def _jpeg_bytes(size=(400, 300), color="white"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _png_bytes(size=(400, 300)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


class TestPreprocessImage:
    def test_valid_jpeg_passes_through(self):
        result = preprocess_image(_jpeg_bytes(), max_dimension=2000)
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"

    def test_valid_png_is_accepted_and_converted(self):
        result = preprocess_image(_png_bytes(), max_dimension=2000)
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"  # always re-encoded to JPEG for consistency

    def test_garbage_bytes_rejected(self):
        with pytest.raises(InvalidImageError):
            preprocess_image(b"this is not an image", max_dimension=2000)

    def test_empty_bytes_rejected(self):
        with pytest.raises(InvalidImageError):
            preprocess_image(b"", max_dimension=2000)

    def test_truncated_image_rejected(self):
        valid = _jpeg_bytes()
        truncated = valid[: len(valid) // 2]
        with pytest.raises(InvalidImageError):
            preprocess_image(truncated, max_dimension=2000)

    def test_downscales_oversized_image(self):
        result = preprocess_image(_jpeg_bytes(size=(4000, 3000)), max_dimension=1000)
        img = Image.open(io.BytesIO(result))
        assert max(img.width, img.height) <= 1000

    def test_does_not_upscale_small_image(self):
        result = preprocess_image(_jpeg_bytes(size=(200, 150)), max_dimension=2000)
        img = Image.open(io.BytesIO(result))
        assert img.width == 200
        assert img.height == 150

    def test_preserves_aspect_ratio_when_downscaling(self):
        result = preprocess_image(_jpeg_bytes(size=(4000, 2000)), max_dimension=1000)
        img = Image.open(io.BytesIO(result))
        assert abs((img.width / img.height) - (4000 / 2000)) < 0.01

    def test_grayscale_input_is_converted_to_rgb(self):
        buf = io.BytesIO()
        Image.new("L", (300, 300), 128).save(buf, format="JPEG")
        result = preprocess_image(buf.getvalue(), max_dimension=2000)
        img = Image.open(io.BytesIO(result))
        assert img.mode == "RGB"

    def test_rgba_png_input_is_converted_to_rgb(self):
        buf = io.BytesIO()
        Image.new("RGBA", (300, 300), (255, 255, 255, 128)).save(buf, format="PNG")
        result = preprocess_image(buf.getvalue(), max_dimension=2000)
        img = Image.open(io.BytesIO(result))
        assert img.mode == "RGB"
