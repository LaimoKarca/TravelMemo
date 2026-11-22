"""Image decoding, validation, metadata extraction, and WebP compression."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import BinaryIO

from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except (ImportError, AttributeError, OSError):  # pragma: no cover
    pass

# Protect against decompression bomb attacks
Image.MAX_IMAGE_PIXELS = 55_000_000

MAX_UPLOAD_BYTES: int = 20 * 1024 * 1024  # 20 MiB
MAX_MEGAPIXELS: int = 50_000_000  # 50 MP
MAX_DIMENSION: int = 2048  # 2048px
MAX_MAIN_SIZE_BYTES: int = 512 * 1024  # 512 KiB
THUMB_MAX_DIMENSION: int = 384  # 384px
THUMB_MAX_SIZE_BYTES: int = 64 * 1024  # 64 KiB
SUPPORTED_FORMATS: set[str] = {"JPEG", "JPG", "PNG", "WEBP", "HEIF", "HEIC", "MPO"}


class ImageCodecError(Exception):
    """Base error for image codec operations."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ImageSizeError(ImageCodecError):
    """Raised when image exceeds allowed file size or megapixels."""

    def __init__(self, message: str = "圖片檔案或像素超出限制。"):
        super().__init__(message, status_code=413)


class ImageFormatError(ImageCodecError):
    """Raised when image format is unsupported."""

    def __init__(self, message: str = "不支援的圖片格式。"):
        super().__init__(message, status_code=415)


class ImageCorruptError(ImageCodecError):
    """Raised when image data is invalid or corrupt."""

    def __init__(self, message: str = "圖片資料損壞或無法讀取。"):
        super().__init__(message, status_code=422)


@dataclass
class ProcessedImage:
    main_bytes: bytes
    thumbnail_bytes: bytes
    width: int
    height: int
    size_bytes: int
    thumbnail_size_bytes: int
    date_candidate: str | None


def extract_date_candidate(img: Image.Image) -> str | None:
    """Extracts date/time candidate from EXIF tags before stripping.

    Never extracts or returns GPS coordinates.
    """
    try:
        exif = img.getexif()
        if not exif:
            return None
        # Tag IDs: 36867 = DateTimeOriginal, 36868 = DateTimeDigitized, 306 = DateTime
        for tag in (36867, 36868, 306):
            val = exif.get(tag)
            if val and isinstance(val, str):
                val = val.strip()
                # Typical format: 'YYYY:MM:DD HH:MM:SS' or 'YYYY-MM-DD HH:MM:SS' or 'YYYY:MM:DD'
                m = re.match(
                    r"^(\d{4})[:\-](\d{2})[:\-](\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2}))?",
                    val,
                )
                if m:
                    y, mo, d = m.group(1), m.group(2), m.group(3)
                    if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
                        if m.group(4) is not None:
                            h, mi, s = m.group(4), m.group(5), m.group(6)
                            return f"{y}-{mo}-{d}T{h}:{mi}:{s}"
                        return f"{y}-{mo}-{d}"
    except (AttributeError, ValueError, KeyError, TypeError):
        return None
    return None


def _compress_webp(
    img: Image.Image,
    max_dim: int,
    max_bytes: int,
    start_quality: int = 85,
) -> tuple[bytes, int, int]:
    """Resizes and compresses image to WebP within max_dim and max_bytes.

    No EXIF or metadata is saved into the output.
    """
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        current = img.resize((nw, nh), Image.Resampling.LANCZOS)
    else:
        current = img.copy()

    # WebP supports RGB and RGBA.
    if current.mode not in ("RGB", "RGBA"):
        if "A" in current.mode or (current.mode == "P" and "transparency" in current.info):
            current = current.convert("RGBA")
        else:
            current = current.convert("RGB")

    quality = start_quality
    while True:
        buf = io.BytesIO()
        # Explicitly do NOT pass exif argument to strip all EXIF/GPS
        current.save(buf, format="WEBP", quality=quality, method=4)
        data = buf.getvalue()
        if len(data) <= max_bytes or quality <= 15:
            if len(data) > max_bytes:
                # Still exceeds max_bytes, downscale further
                cw, ch = current.size
                nw, nh = max(1, int(cw * 0.85)), max(1, int(ch * 0.85))
                if (nw, nh) == (cw, ch):
                    return data, current.width, current.height
                current = current.resize((nw, nh), Image.Resampling.LANCZOS)
                quality = 50
                continue
            return data, current.width, current.height
        quality = max(15, quality - 10)


def process_image(
    data: bytes | BinaryIO,
    max_dimension: int = MAX_DIMENSION,
    max_size_bytes: int = MAX_MAIN_SIZE_BYTES,
    thumb_max_dimension: int = THUMB_MAX_DIMENSION,
    thumb_max_size_bytes: int = THUMB_MAX_SIZE_BYTES,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
    max_megapixels: int = MAX_MEGAPIXELS,
) -> ProcessedImage:
    """Validates raw image data, extracts date candidate, auto-orients,

    strips EXIF (no GPS), and compresses both main image and thumbnail to WebP.
    """
    if hasattr(data, "read"):
        raw_bytes = data.read()
    else:
        raw_bytes = data

    if len(raw_bytes) > max_upload_bytes:
        raise ImageSizeError(
            f"圖片檔案大小 ({len(raw_bytes)} bytes) 超過限制 ({max_upload_bytes} bytes)。"
        )
    if len(raw_bytes) == 0:
        raise ImageCorruptError("圖片檔案內容為空。")

    try:
        img = Image.open(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise ImageCorruptError(f"無法解析圖片檔案: {exc}") from exc

    fmt = (img.format or "").upper()
    if fmt not in SUPPORTED_FORMATS:
        raise ImageFormatError(f"不支援的圖片格式: {fmt or '未知'}")

    pixels = img.width * img.height
    if pixels > max_megapixels:
        raise ImageSizeError(
            f"圖片像素 ({pixels} pixels) 超過限制 ({max_megapixels} pixels)。"
        )

    # Pillow opens MPO at its primary JPEG frame. Decode only that frame.
    try:
        img.load()
    except (OSError, ValueError, SyntaxError) as exc:
        raise ImageCorruptError() from exc

    # Extract date candidate from EXIF before stripping
    date_candidate = extract_date_candidate(img)

    # Auto-orient based on EXIF Orientation tag
    try:
        img = ImageOps.exif_transpose(img)
    except (ValueError, TypeError, OSError):
        pass

    # Produce main WebP <= 2048px, <= 512 KiB
    main_bytes, mw, mh = _compress_webp(
        img,
        max_dim=max_dimension,
        max_bytes=max_size_bytes,
        start_quality=85,
    )

    # Produce thumbnail WebP <= 384px, <= 64 KiB
    thumb_bytes, _, _ = _compress_webp(
        img,
        max_dim=thumb_max_dimension,
        max_bytes=thumb_max_size_bytes,
        start_quality=80,
    )

    return ProcessedImage(
        main_bytes=main_bytes,
        thumbnail_bytes=thumb_bytes,
        width=mw,
        height=mh,
        size_bytes=len(main_bytes),
        thumbnail_size_bytes=len(thumb_bytes),
        date_candidate=date_candidate,
    )
