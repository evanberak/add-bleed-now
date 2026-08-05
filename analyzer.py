from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image

from models import EdgeAnalysis, EdgeKind


def _edge_strip(array: np.ndarray, edge: str, depth: int) -> np.ndarray:
    if edge == "top":
        return array[:depth, :, :3]
    if edge == "bottom":
        return array[-depth:, :, :3]
    if edge == "left":
        return array[:, :depth, :3]
    if edge == "right":
        return array[:, -depth:, :3]
    raise ValueError(f"Unknown edge: {edge}")


def _quantized_palette(strip: np.ndarray) -> tuple[tuple[int, int, int], float, float]:
    pixels = strip.reshape(-1, 3).astype(np.uint8)
    quantized = (pixels // 16) * 16 + 8
    packed = (
        quantized[:, 0].astype(np.uint32) << 16
        | quantized[:, 1].astype(np.uint32) << 8
        | quantized[:, 2].astype(np.uint32)
    )
    values, counts = np.unique(packed, return_counts=True)
    order = np.argsort(counts)[::-1]
    counts = counts[order]
    values = values[order]
    total = max(1, int(counts.sum()))
    dominant = int(values[0])
    rgb = ((dominant >> 16) & 255, (dominant >> 8) & 255, dominant & 255)
    dominant_coverage = float(counts[0] / total)
    palette_coverage = float(counts[:4].sum() / total)
    return rgb, dominant_coverage, palette_coverage


def _periodicity(strip: np.ndarray, edge: str) -> float:
    gray = cv2.cvtColor(strip, cv2.COLOR_RGB2GRAY).astype(np.float32)
    signal = gray.mean(axis=0 if edge in {"top", "bottom"} else 1)
    signal -= signal.mean()
    variance = float(np.dot(signal, signal))
    if variance < 1e-6 or len(signal) < 12:
        return 0.0
    autocorrelation = np.correlate(signal, signal, mode="full")[len(signal) - 1 :]
    max_lag = min(160, len(signal) // 3)
    if max_lag <= 4:
        return 0.0
    useful = autocorrelation[4:max_lag] / variance
    return float(np.clip(np.max(useful), 0.0, 1.0))


def _classify(
    color_std: float,
    dominant_coverage: float,
    palette_coverage: float,
    edge_density: float,
    periodicity: float,
) -> tuple[EdgeKind, float, list[str]]:
    notes: list[str] = []
    if dominant_coverage > 0.82 and color_std < 14:
        notes.append("The edge is dominated by one color.")
        return EdgeKind.SOLID, min(0.99, 0.72 + dominant_coverage * 0.25), notes
    if palette_coverage > 0.72 and periodicity > 0.18:
        notes.append("A limited palette and repeating signal were detected.")
        return EdgeKind.PATTERN, min(0.98, 0.62 + periodicity * 0.35), notes
    if edge_density < 0.055 and color_std < 42:
        notes.append("Low edge density suggests a smooth gradient or soft background.")
        return EdgeKind.GRADIENT, 0.82, notes
    if palette_coverage > 0.58 and edge_density < 0.18:
        notes.append("The edge appears to be a non-uniform texture.")
        return EdgeKind.TEXTURE, 0.74, notes
    notes.append("Complex detail was detected; visual review is recommended.")
    return EdgeKind.PHOTO, 0.58, notes


def analyze_document(image: Image.Image, strip_pixels: int) -> dict[str, EdgeAnalysis]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    depth = max(4, min(strip_pixels, max(4, min(rgb.shape[:2]) // 3)))
    results: dict[str, EdgeAnalysis] = {}

    for edge in ("top", "right", "bottom", "left"):
        strip = _edge_strip(rgb, edge, depth)
        dominant_rgb, dominant_coverage, palette_coverage = _quantized_palette(strip)
        gray = cv2.cvtColor(strip, cv2.COLOR_RGB2GRAY)
        canny = cv2.Canny(gray, 70, 160)
        edge_density = float(np.count_nonzero(canny) / canny.size)
        color_std = float(np.mean(np.std(strip.reshape(-1, 3), axis=0)))
        periodicity = _periodicity(strip, edge)
        kind, confidence, notes = _classify(
            color_std,
            dominant_coverage,
            palette_coverage,
            edge_density,
            periodicity,
        )
        # Large palette spread and many edges usually mean content is touching the trim.
        foreground_risk = float(
            np.clip((1.0 - palette_coverage) * 0.65 + edge_density * 1.7, 0.0, 1.0)
        )
        if foreground_risk > 0.55:
            notes.append("Foreground content may touch this edge.")

        results[edge] = EdgeAnalysis(
            edge=edge,
            kind=kind,
            confidence=round(confidence, 3),
            dominant_rgb=dominant_rgb,
            dominant_coverage=round(dominant_coverage, 3),
            palette_coverage=round(palette_coverage, 3),
            color_std=round(color_std, 3),
            edge_density=round(edge_density, 4),
            periodicity=round(periodicity, 3),
            foreground_risk=round(foreground_risk, 3),
            notes=notes,
        )

    return results
