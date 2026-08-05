from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageOps

from models import SourceDocument


PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


def _normalize_dpi(value: object, fallback: int) -> tuple[float, float]:
    try:
        x, y = value  # type: ignore[misc]
        x = float(x)
        y = float(y)
        if x > 0 and y > 0:
            return x, y
    except (TypeError, ValueError):
        pass
    return float(fallback), float(fallback)


def read_source(file_bytes: bytes, filename: str, render_dpi: int = 300) -> SourceDocument:
    if not file_bytes:
        raise ValueError("The uploaded file is empty.")

    suffix = Path(filename).suffix.lower()
    if suffix in PDF_EXTENSIONS:
        document = fitz.open(stream=file_bytes, filetype="pdf")
        if document.page_count < 1:
            raise ValueError("The PDF has no pages.")
        page = document[0]
        rect = page.rect
        matrix = fitz.Matrix(render_dpi / 72.0, render_dpi / 72.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False, annots=True)
        mode = "RGB" if pixmap.n < 4 else "RGBA"
        preview = Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples).convert("RGB")
        return SourceDocument(
            filename=filename,
            kind="pdf",
            original_bytes=file_bytes,
            preview=preview,
            page_count=document.page_count,
            trim_width_pt=float(rect.width),
            trim_height_pt=float(rect.height),
            trim_width_inches=float(rect.width) / 72.0,
            trim_height_inches=float(rect.height) / 72.0,
            render_dpi=render_dpi,
        )

    if suffix in IMAGE_EXTENSIONS:
        with Image.open(BytesIO(file_bytes)) as opened:
            image = ImageOps.exif_transpose(opened)
            dpi_x, dpi_y = _normalize_dpi(image.info.get("dpi"), render_dpi)
            preview = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            width_inches = preview.width / dpi_x
            height_inches = preview.height / dpi_y
            return SourceDocument(
                filename=filename,
                kind="image",
                original_bytes=file_bytes,
                preview=preview,
                page_count=1,
                trim_width_pt=width_inches * 72.0,
                trim_height_pt=height_inches * 72.0,
                trim_width_inches=width_inches,
                trim_height_inches=height_inches,
                render_dpi=render_dpi,
            )

    raise ValueError("Unsupported file type. Use PDF, PNG, JPG, JPEG, TIFF, or WebP.")
