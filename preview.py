from __future__ import annotations

from PIL import Image, ImageDraw


def add_preview_guides(image: Image.Image, bleed_pixels: int) -> Image.Image:
    preview = image.convert("RGB").copy()
    draw = ImageDraw.Draw(preview)
    width, height = preview.size
    trim_box = (
        bleed_pixels,
        bleed_pixels,
        width - bleed_pixels - 1,
        height - bleed_pixels - 1,
    )
    draw.rectangle(trim_box, outline=(225, 68, 68), width=max(2, bleed_pixels // 15))
    draw.rectangle((0, 0, width - 1, height - 1), outline=(64, 135, 255), width=max(2, bleed_pixels // 15))
    return preview
