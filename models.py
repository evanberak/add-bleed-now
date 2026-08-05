from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from PIL import Image


class EdgeKind(str, Enum):
    SOLID = "solid"
    GRADIENT = "gradient"
    PATTERN = "pattern"
    TEXTURE = "texture"
    PHOTO = "photo"


class ExtensionMode(str, Enum):
    AUTOMATIC = "automatic"
    BACKGROUND_ONLY = "background_only"
    EDGE_STRETCH = "edge_stretch"
    MIRROR = "mirror"


@dataclass(slots=True)
class BleedSettings:
    bleed_inches: float = 0.125
    dpi: int = 300
    extension_mode: ExtensionMode = ExtensionMode.BACKGROUND_ONLY
    protect_foreground: bool = True
    protection_strength: int = 65
    square_corners: bool = True
    manual_background_hex: str | None = None
    source_strip_inches: float = 0.35

    def validate(self) -> None:
        if not 0 < self.bleed_inches <= 1:
            raise ValueError("Bleed must be greater than 0 and no more than 1 inch.")
        if not 72 <= self.dpi <= 1200:
            raise ValueError("DPI must be between 72 and 1200.")
        if not 0 <= self.protection_strength <= 100:
            raise ValueError("Protection strength must be between 0 and 100.")
        if not 0.05 <= self.source_strip_inches <= 2:
            raise ValueError("Source strip must be between 0.05 and 2 inches.")


@dataclass(slots=True)
class EdgeAnalysis:
    edge: str
    kind: EdgeKind
    confidence: float
    dominant_rgb: tuple[int, int, int]
    dominant_coverage: float
    palette_coverage: float
    color_std: float
    edge_density: float
    periodicity: float
    foreground_risk: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["dominant_rgb"] = list(self.dominant_rgb)
        return data


@dataclass(slots=True)
class SourceDocument:
    filename: str
    kind: str
    original_bytes: bytes
    preview: Image.Image
    page_count: int
    trim_width_pt: float
    trim_height_pt: float
    trim_width_inches: float
    trim_height_inches: float
    render_dpi: int


@dataclass(slots=True)
class ProcessResult:
    image: Image.Image
    bleed_pixels: int
    edge_analysis: dict[str, EdgeAnalysis]
    warnings: list[str]
    quality_label: str
    seam_scores: dict[str, float]

    def report_dict(self, source: SourceDocument, settings: BleedSettings) -> dict[str, Any]:
        return {
            "source": {
                "filename": source.filename,
                "kind": source.kind,
                "pages": source.page_count,
                "trim_width_inches": round(source.trim_width_inches, 4),
                "trim_height_inches": round(source.trim_height_inches, 4),
            },
            "settings": {
                "bleed_inches": settings.bleed_inches,
                "dpi": settings.dpi,
                "extension_mode": settings.extension_mode.value,
                "protect_foreground": settings.protect_foreground,
                "protection_strength": settings.protection_strength,
                "square_corners": settings.square_corners,
                "manual_background_hex": settings.manual_background_hex,
            },
            "result": {
                "quality_label": self.quality_label,
                "bleed_pixels": self.bleed_pixels,
                "finished_width_inches": round(source.trim_width_inches + settings.bleed_inches * 2, 4),
                "finished_height_inches": round(source.trim_height_inches + settings.bleed_inches * 2, 4),
                "warnings": self.warnings,
                "seam_scores": self.seam_scores,
                "edges": {name: report.to_dict() for name, report in self.edge_analysis.items()},
            },
        }
