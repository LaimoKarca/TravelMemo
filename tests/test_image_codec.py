"""Unit tests for backend/image_codec.py."""

import io

import pytest
from PIL import Image

from backend.image_codec import (
    ImageCorruptError,
    ImageFormatError,
    ImageSizeError,
    extract_date_candidate,
    process_image,
)


def create_test_image(
    format: str = "JPEG",
    size: tuple[int, int] = (100, 100),
    color: str = "red",
    exif_date: str | None = None,
    orientation: int | None = None,
) -> bytes:
    img = Image.new("RGB", size, color=color)
    exif = img.getexif()
    if exif_date:
        exif[36867] = exif_date  # DateTimeOriginal
    if orientation:
        exif[274] = orientation  # Orientation

    buf = io.BytesIO()
    if format.upper() == "JPEG":
        img.save(buf, format="JPEG", exif=exif)
    elif format.upper() == "PNG":
        img.save(buf, format="PNG")
    elif format.upper() == "WEBP":
        img.save(buf, format="WEBP")
    return buf.getvalue()


def test_process_valid_jpeg():
    raw = create_test_image("JPEG", size=(400, 300), color="blue")
    result = process_image(raw)

    assert result.width == 400
    assert result.height == 300
    assert result.size_bytes <= 512 * 1024
    assert result.thumbnail_size_bytes <= 64 * 1024
    assert result.date_candidate is None

    # Verify output is valid WebP with no EXIF
    opened = Image.open(io.BytesIO(result.main_bytes))
    assert opened.format == "WEBP"
    assert list(opened.getexif().keys()) == []

    thumb = Image.open(io.BytesIO(result.thumbnail_bytes))
    assert thumb.format == "WEBP"
    assert max(thumb.width, thumb.height) <= 384


def test_process_valid_png_and_webp():
    png_raw = create_test_image("PNG", size=(200, 200))
    res_png = process_image(png_raw)
    assert res_png.width == 200
    assert Image.open(io.BytesIO(res_png.main_bytes)).format == "WEBP"

    webp_raw = create_test_image("WEBP", size=(150, 150))
    res_webp = process_image(webp_raw)
    assert res_webp.width == 150
    assert Image.open(io.BytesIO(res_webp.main_bytes)).format == "WEBP"


def test_process_mpo_uses_primary_photo_and_strips_metadata():
    primary = Image.new("RGB", (120, 80), "red")
    secondary = Image.new("RGB", (60, 40), "blue")
    exif = primary.getexif()
    exif[274] = 6  # Rotate the stored image 90 degrees clockwise.
    exif[36867] = "2024:10:25 15:45:00"
    exif[34853] = {1: "N", 2: (25.0, 0.0, 0.0)}  # GPS latitude.
    buf = io.BytesIO()
    primary.save(buf, format="MPO", append_images=[secondary], exif=exif)
    raw = buf.getvalue()
    with Image.open(io.BytesIO(raw)) as uploaded:
        assert uploaded.format == "MPO"
        assert uploaded.n_frames == 2

    result = process_image(raw)

    assert (result.width, result.height) == (80, 120)
    assert result.date_candidate == "2024-10-25T15:45:00"
    for output in (result.main_bytes, result.thumbnail_bytes):
        with Image.open(io.BytesIO(output)) as saved:
            assert saved.format == "WEBP"
            assert not saved.getexif()
            red, _, blue = saved.getpixel((0, 0))
            assert red > blue

    with pytest.raises(ImageSizeError, match="像素.*超過限制"):
        process_image(raw, max_megapixels=120 * 80 - 1)


def test_downscale_large_image():
    # Image larger than 2048px on longest side
    raw = create_test_image("JPEG", size=(3000, 1500))
    result = process_image(raw)

    assert result.width == 2048
    assert result.height == 1024
    assert result.size_bytes <= 512 * 1024


def test_exif_date_candidate_and_stripping():
    # EXIF date format 'YYYY:MM:DD HH:MM:SS'
    raw = create_test_image(
        "JPEG", size=(100, 100), exif_date="2024:10:25 15:45:00", orientation=6
    )
    result = process_image(raw)

    assert result.date_candidate == "2024-10-25T15:45:00"

    # Verify no GPS or other EXIF remains in main or thumbnail
    opened = Image.open(io.BytesIO(result.main_bytes))
    assert list(opened.getexif().keys()) == []

    thumb = Image.open(io.BytesIO(result.thumbnail_bytes))
    assert list(thumb.getexif().keys()) == []


def test_extract_date_candidate_date_only():
    img = Image.new("RGB", (10, 10))
    exif = img.getexif()
    exif[306] = "2023:05:12"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)

    opened = Image.open(io.BytesIO(buf.getvalue()))
    date_cand = extract_date_candidate(opened)
    assert date_cand == "2023-05-12"


def test_reject_empty_bytes():
    with pytest.raises(ImageCorruptError, match="檔案內容為空"):
        process_image(b"")


def test_reject_corrupt_bytes():
    with pytest.raises(ImageCorruptError, match="無法解析圖片檔案"):
        process_image(b"not an image data at all")


def test_reject_unsupported_format():
    # Create BMP
    img = Image.new("RGB", (50, 50))
    buf = io.BytesIO()
    img.save(buf, format="BMP")

    with pytest.raises(ImageFormatError, match="不支援的圖片格式"):
        process_image(buf.getvalue())


def test_reject_too_large_file():
    with pytest.raises(ImageSizeError, match="超過限制"):
        process_image(b"x" * (20 * 1024 * 1024 + 1))


def test_reject_excessive_megapixels():
    raw = create_test_image("JPEG", size=(200, 200))
    # Pass max_megapixels=100
    with pytest.raises(ImageSizeError, match="像素.*超過限制"):
        process_image(raw, max_megapixels=100)
