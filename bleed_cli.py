from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzer import analyze_document
from bleed import generate_bleed
from document import read_source
from exporter import export_pdf_bytes, export_png_bytes
from models import BleedSettings, ExtensionMode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add print bleed while preserving the original trim artwork.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--bleed", type=float, default=0.125, help="Bleed per side in inches.")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in ExtensionMode],
        default=ExtensionMode.BACKGROUND_ONLY.value,
    )
    parser.add_argument("--no-protection", action="store_true")
    parser.add_argument("--protection-strength", type=int, default=65)
    parser.add_argument("--no-square-corners", action="store_true")
    parser.add_argument("--background-color", help="Optional six-character hex background, such as 0054A6.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    file_bytes = args.input.read_bytes()
    source = read_source(file_bytes, args.input.name, args.dpi)
    settings = BleedSettings(
        bleed_inches=args.bleed,
        dpi=args.dpi,
        extension_mode=ExtensionMode(args.mode),
        protect_foreground=not args.no_protection,
        protection_strength=args.protection_strength,
        square_corners=not args.no_square_corners,
        manual_background_hex=args.background_color,
    )
    analysis = analyze_document(source.preview, round(settings.source_strip_inches * settings.dpi))
    result = generate_bleed(source.preview, settings, analysis)

    stem = args.input.stem
    pdf_path = args.output_dir / f"{stem}_bleed.pdf"
    png_path = args.output_dir / f"{stem}_bleed.png"
    report_path = args.output_dir / f"{stem}_bleed_report.json"
    pdf_path.write_bytes(export_pdf_bytes(source, result, settings))
    png_path.write_bytes(export_png_bytes(result, settings.dpi))
    report_path.write_text(json.dumps(result.report_dict(source, settings), indent=2), encoding="utf-8")

    print(f"PDF: {pdf_path}")
    print(f"PNG: {png_path}")
    print(f"Report: {report_path}")
    print(f"Quality: {result.quality_label}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()
