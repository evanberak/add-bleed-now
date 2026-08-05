from __future__ import annotations

from io import BytesIO

import fitz
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject

from models import BleedSettings, ProcessResult, SourceDocument


def export_png_bytes(result: ProcessResult, dpi: int) -> bytes:
    buffer = BytesIO()
    result.image.save(buffer, format="PNG", dpi=(dpi, dpi), optimize=True)
    return buffer.getvalue()


def _image_png_bytes(image: Image.Image, dpi: int) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG", dpi=(dpi, dpi), optimize=True)
    return buffer.getvalue()


def export_pdf_bytes(
    source: SourceDocument,
    result: ProcessResult,
    settings: BleedSettings,
) -> bytes:
    bleed_pt = settings.bleed_inches * 72.0
    full_width_pt = source.trim_width_pt + bleed_pt * 2
    full_height_pt = source.trim_height_pt + bleed_pt * 2

    output = fitz.open()
    page = output.new_page(width=full_width_pt, height=full_height_pt)
    full_rect = fitz.Rect(0, 0, full_width_pt, full_height_pt)
    trim_rect = fitz.Rect(
        bleed_pt,
        bleed_pt,
        bleed_pt + source.trim_width_pt,
        bleed_pt + source.trim_height_pt,
    )

    page.insert_image(
        full_rect,
        stream=export_png_bytes(result, settings.dpi),
        keep_proportion=False,
        overlay=False,
    )

    # Overlay the untouched original PDF page whenever possible so vector text,
    # QR codes, and logos remain original inside trim.
    if source.kind == "pdf":
        original_pdf = fitz.open(stream=source.original_bytes, filetype="pdf")
        page.show_pdf_page(trim_rect, original_pdf, 0, keep_proportion=False, overlay=True)
    else:
        page.insert_image(
            trim_rect,
            stream=_image_png_bytes(source.preview, settings.dpi),
            keep_proportion=False,
            overlay=True,
        )

    raw_pdf = output.tobytes(garbage=4, deflate=True)
    output.close()

    reader = PdfReader(BytesIO(raw_pdf))
    writer = PdfWriter()
    pdf_page = reader.pages[0]
    media = RectangleObject((0, 0, full_width_pt, full_height_pt))
    trim = RectangleObject(
        (
            bleed_pt,
            bleed_pt,
            bleed_pt + source.trim_width_pt,
            bleed_pt + source.trim_height_pt,
        )
    )
    pdf_page.mediabox = media
    pdf_page.cropbox = media
    pdf_page.bleedbox = media
    pdf_page.trimbox = trim
    pdf_page.artbox = trim
    writer.add_page(pdf_page)
    writer.add_metadata(
        {
            "/Title": f"{source.filename} - bleed",
            "/Creator": "Print Bleed Tool",
            "/Subject": f"{settings.bleed_inches:.3f} inch bleed with preserved trim artwork",
        }
    )
    final = BytesIO()
    writer.write(final)
    return final.getvalue()
