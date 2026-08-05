from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from models import BleedSettings, EdgeAnalysis, EdgeKind, ExtensionMode, ProcessResult


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        raise ValueError("Background color must use six hexadecimal characters.")
    return tuple(int(clean[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _corner_mask_for_opaque_white(rgb: np.ndarray) -> np.ndarray:
    """Detect white corner cutouts without treating normal white artwork as a cutout."""
    height, width = rgb.shape[:2]
    radius = max(4, int(min(height, width) * 0.08))
    mask = np.zeros((height, width), dtype=np.uint8)
    corners = [
        (slice(0, radius), slice(0, radius), (0, 0)),
        (slice(0, radius), slice(width - radius, width), (0, radius - 1)),
        (slice(height - radius, height), slice(0, radius), (radius - 1, 0)),
        (slice(height - radius, height), slice(width - radius, width), (radius - 1, radius - 1)),
    ]
    for ys, xs, seed in corners:
        patch = rgb[ys, xs]
        corner_pixel = patch[seed]
        if np.min(corner_pixel) < 242:
            continue
        interior = patch[radius // 2 :, radius // 2 :]
        if interior.size == 0:
            continue
        if float(np.linalg.norm(interior.mean(axis=(0, 1)) - corner_pixel.astype(float))) < 35:
            continue
        distance = np.linalg.norm(patch.astype(np.int16) - corner_pixel.astype(np.int16), axis=2)
        local = (distance < 14).astype(np.uint8) * 255
        _, labels = cv2.connectedComponents(local)
        label = labels[seed]
        if label == 0:
            continue
        connected = (labels == label).astype(np.uint8) * 255
        mask[ys, xs] = np.maximum(mask[ys, xs], connected)
    return mask


def _repair_square_corners(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = rgba[:, :, :3].copy()
    alpha_mask = (rgba[:, :, 3] < 250).astype(np.uint8) * 255
    white_mask = _corner_mask_for_opaque_white(rgb)
    mask = np.maximum(alpha_mask, white_mask)
    if np.count_nonzero(mask) == 0:
        return rgb
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    return cv2.inpaint(rgb, mask, 5, cv2.INPAINT_TELEA)


def _background_clusters(border_pixels: np.ndarray, strength: int) -> tuple[np.ndarray, np.ndarray]:
    pixels = border_pixels.reshape(-1, 3).astype(np.float32)
    if len(pixels) > 60000:
        rng = np.random.default_rng(42)
        pixels = pixels[rng.choice(len(pixels), 60000, replace=False)]
    cluster_count = min(6, max(2, len(pixels) // 3000))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, centers = cv2.kmeans(
        pixels,
        cluster_count,
        None,
        criteria,
        4,
        cv2.KMEANS_PP_CENTERS,
    )
    counts = np.bincount(labels.ravel(), minlength=cluster_count)
    order = np.argsort(counts)[::-1]
    centers = centers[order]
    counts = counts[order]

    center_lab = cv2.cvtColor(centers.reshape(1, -1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB)[0].astype(float)
    base = center_lab[0]
    threshold = 20 + (100 - strength) * 0.42
    accepted = [0]
    coverage = counts[0] / counts.sum()
    for index in range(1, len(centers)):
        distance = float(np.linalg.norm(center_lab[index] - base))
        cluster_share = counts[index] / counts.sum()
        if distance <= threshold or (coverage < 0.60 and cluster_share > 0.08):
            accepted.append(index)
            coverage += cluster_share
        if coverage >= 0.82:
            break
    return centers.astype(np.uint8), np.asarray(accepted, dtype=int)


def _background_mask(rgb: np.ndarray, depth: int, strength: int) -> tuple[np.ndarray, np.ndarray]:
    height, width = rgb.shape[:2]
    border_region = np.zeros((height, width), dtype=np.uint8)
    border_region[:depth, :] = 255
    border_region[-depth:, :] = 255
    border_region[:, :depth] = 255
    border_region[:, -depth:] = 255

    border_pixels = rgb[border_region > 0]
    centers, accepted_indices = _background_clusters(border_pixels, strength)
    accepted_centers = centers[accepted_indices].astype(np.float32)
    pixels = rgb.astype(np.float32)
    squared = np.sum(
        (pixels[:, :, None, :] - accepted_centers[None, None, :, :]) ** 2,
        axis=3,
    )
    distances = np.sqrt(np.min(squared, axis=2))
    distance_threshold = 35 + (100 - strength) * 0.55
    return distances <= distance_threshold, accepted_centers.astype(np.uint8)


def _sanitize_border(rgb: np.ndarray, depth: int, strength: int) -> tuple[np.ndarray, float]:
    height, width = rgb.shape[:2]
    border_region = np.zeros((height, width), dtype=np.uint8)
    border_region[:depth, :] = 255
    border_region[-depth:, :] = 255
    border_region[:, :depth] = 255
    border_region[:, -depth:] = 255
    background, _ = _background_mask(rgb, depth, strength)

    foreground = ((~background) & (border_region > 0)).astype(np.uint8) * 255
    kernel = np.ones((3, 3), np.uint8)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
    foreground = cv2.dilate(foreground, np.ones((5, 5), np.uint8), iterations=1)
    masked_fraction = float(np.count_nonzero(foreground) / max(1, np.count_nonzero(border_region)))

    if np.count_nonzero(foreground) == 0:
        return rgb.copy(), masked_fraction
    cleaned = cv2.inpaint(rgb, foreground, 7, cv2.INPAINT_TELEA)
    return cleaned, masked_fraction


def _integral_area(integral: np.ndarray, x: int, y: int, size: int) -> float:
    x2, y2 = x + size, y + size
    return float(integral[y2, x2] - integral[y, x2] - integral[y2, x] + integral[y, x])


def _find_clean_texture_patch(
    rgb: np.ndarray,
    background: np.ndarray,
    bleed: int,
) -> tuple[np.ndarray | None, float]:
    height, width = rgb.shape[:2]
    foreground = (~background).astype(np.uint8)
    integral = cv2.integral(foreground)
    maximum = min(240, max(48, min(height, width) // 3))
    minimum = max(32, min(64, min(height, width) // 8))
    candidate_sizes = sorted(
        {maximum, int(maximum * 0.8), int(maximum * 0.65), 128, 96, 64, minimum},
        reverse=True,
    )
    candidate_sizes = [size for size in candidate_sizes if minimum <= size <= min(height, width)]

    best: tuple[float, float, int, int, int] | None = None
    for size in candidate_sizes:
        step = max(8, size // 6)
        for y in range(0, height - size + 1, step):
            for x in range(0, width - size + 1, step):
                foreground_ratio = _integral_area(integral, x, y, size) / float(size * size)
                if foreground_ratio > 0.18:
                    continue
                patch = rgb[y : y + size, x : x + size]
                texture_variance = float(np.mean(np.std(patch.reshape(-1, 3), axis=0)))
                # Strongly favor clean patches, then larger patches, then useful texture variation.
                score = foreground_ratio * 1000.0 - min(texture_variance, 50.0) * 0.25 - size * 0.015
                candidate = (score, foreground_ratio, x, y, size)
                if best is None or candidate < best:
                    best = candidate
        if best is not None and best[1] <= 0.02:
            break

    if best is None:
        return None, 1.0
    _, ratio, x, y, size = best
    patch = rgb[y : y + size, x : x + size].copy()
    patch_foreground = (~background[y : y + size, x : x + size]).astype(np.uint8) * 255
    if np.count_nonzero(patch_foreground):
        patch_foreground = cv2.dilate(patch_foreground, np.ones((3, 3), np.uint8), iterations=1)
        patch = cv2.inpaint(patch, patch_foreground, 5, cv2.INPAINT_TELEA)
    return patch, ratio


def _make_seamless_mirror_tile(patch: np.ndarray) -> np.ndarray:
    top = np.concatenate((patch, patch[:, ::-1]), axis=1)
    bottom = top[::-1]
    return np.concatenate((top, bottom), axis=0)


def _edge_samples(
    original: np.ndarray,
    background: np.ndarray,
    bleed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    height, width = original.shape[:2]
    points: list[tuple[int, int]] = []
    colors: list[np.ndarray] = []
    stride = max(1, min(height, width) // 250)

    for x in range(0, width, stride):
        if background[0, x]:
            points.append((bleed + x, bleed - 1))
            colors.append(original[0, x])
        if background[-1, x]:
            points.append((bleed + x, bleed + height))
            colors.append(original[-1, x])
    for y in range(0, height, stride):
        if background[y, 0]:
            points.append((bleed - 1, bleed + y))
            colors.append(original[y, 0])
        if background[y, -1]:
            points.append((bleed + width, bleed + y))
            colors.append(original[y, -1])

    if not points:
        return np.empty((0,), dtype=int), np.empty((0,), dtype=int), np.empty((0, 3), dtype=np.uint8)
    coordinates = np.asarray(points, dtype=int)
    return coordinates[:, 0], coordinates[:, 1], np.asarray(colors, dtype=np.uint8)


def _best_tile_phase(
    tile: np.ndarray,
    original: np.ndarray,
    background: np.ndarray,
    bleed: int,
) -> tuple[int, int]:
    x_coords, y_coords, target = _edge_samples(original, background, bleed)
    if len(target) == 0:
        return 0, 0
    tile_height, tile_width = tile.shape[:2]
    x_offsets = np.unique(np.linspace(0, tile_width - 1, min(28, tile_width), dtype=int))
    y_offsets = np.unique(np.linspace(0, tile_height - 1, min(28, tile_height), dtype=int))
    best_score = float("inf")
    best = (0, 0)
    target_float = target.astype(np.float32)
    for offset_y in y_offsets:
        tile_y = (y_coords + offset_y) % tile_height
        for offset_x in x_offsets:
            tile_x = (x_coords + offset_x) % tile_width
            predicted = tile[tile_y, tile_x].astype(np.float32)
            score = float(np.mean(np.abs(predicted - target_float)))
            if score < best_score:
                best_score = score
                best = (int(offset_x), int(offset_y))
    return best


def _tile_canvas(tile: np.ndarray, height: int, width: int, offset_x: int, offset_y: int) -> np.ndarray:
    tile_height, tile_width = tile.shape[:2]
    y_index = (np.arange(height) + offset_y) % tile_height
    x_index = (np.arange(width) + offset_x) % tile_width
    return tile[y_index[:, None], x_index[None, :]].copy()


def _lock_background_seams(
    canvas: np.ndarray,
    original: np.ndarray,
    background: np.ndarray,
    bleed: int,
) -> None:
    height, width = original.shape[:2]
    top_mask = background[0]
    bottom_mask = background[-1]
    left_mask = background[:, 0]
    right_mask = background[:, -1]
    canvas[bleed - 1, bleed : bleed + width][top_mask] = original[0][top_mask]
    canvas[bleed + height, bleed : bleed + width][bottom_mask] = original[-1][bottom_mask]
    canvas[bleed : bleed + height, bleed - 1][left_mask] = original[:, 0][left_mask]
    canvas[bleed : bleed + height, bleed + width][right_mask] = original[:, -1][right_mask]


def _background_only_canvas(
    original: np.ndarray,
    bleed: int,
    source_depth: int,
    strength: int,
) -> tuple[np.ndarray, float, bool]:
    height, width = original.shape[:2]
    background, centers = _background_mask(original, source_depth, strength)
    patch, foreground_ratio = _find_clean_texture_patch(original, background, bleed)
    if patch is None:
        color = centers[0] if len(centers) else np.median(original.reshape(-1, 3), axis=0).astype(np.uint8)
        canvas = np.empty((height + bleed * 2, width + bleed * 2, 3), dtype=np.uint8)
        canvas[:] = color
        return canvas, foreground_ratio, False

    tile = _make_seamless_mirror_tile(patch)
    offset_x, offset_y = _best_tile_phase(tile, original, background, bleed)
    canvas = _tile_canvas(tile, height + bleed * 2, width + bleed * 2, offset_x, offset_y)
    _lock_background_seams(canvas, original, background, bleed)
    return canvas, foreground_ratio, True


def _apply_solid_edges(
    padded: np.ndarray,
    bleed: int,
    width: int,
    height: int,
    analysis: dict[str, EdgeAnalysis],
) -> None:
    for edge, report in analysis.items():
        if report.kind != EdgeKind.SOLID or report.confidence < 0.78:
            continue
        color = np.asarray(report.dominant_rgb, dtype=np.uint8)
        if edge == "top":
            padded[:bleed, bleed : bleed + width] = color
        elif edge == "bottom":
            padded[bleed + height :, bleed : bleed + width] = color
        elif edge == "left":
            padded[bleed : bleed + height, :bleed] = color
        elif edge == "right":
            padded[bleed : bleed + height, bleed + width :] = color


def _lock_all_seam_rows(padded: np.ndarray, clean: np.ndarray, bleed: int) -> None:
    height, width = clean.shape[:2]
    if bleed <= 0:
        return
    padded[bleed - 1, bleed : bleed + width] = clean[0, :]
    padded[bleed + height, bleed : bleed + width] = clean[-1, :]
    padded[bleed : bleed + height, bleed - 1] = clean[:, 0]
    padded[bleed : bleed + height, bleed + width] = clean[:, -1]


def _seam_scores(padded: np.ndarray, original: np.ndarray, bleed: int) -> dict[str, float]:
    height, width = original.shape[:2]
    comparisons = {
        "top": (padded[bleed - 1, bleed : bleed + width], original[0]),
        "bottom": (padded[bleed + height, bleed : bleed + width], original[-1]),
        "left": (padded[bleed : bleed + height, bleed - 1], original[:, 0]),
        "right": (padded[bleed : bleed + height, bleed + width], original[:, -1]),
    }
    scores: dict[str, float] = {}
    for edge, (outside, inside) in comparisons.items():
        difference = float(np.mean(np.abs(outside.astype(np.float32) - inside.astype(np.float32))))
        scores[edge] = round(max(0.0, 100.0 - difference / 2.55), 2)
    return scores


def generate_bleed(
    image: Image.Image,
    settings: BleedSettings,
    analysis: dict[str, EdgeAnalysis],
) -> ProcessResult:
    settings.validate()
    bleed = max(1, round(settings.bleed_inches * settings.dpi))
    source_depth = max(8, round(settings.source_strip_inches * settings.dpi))

    original = _repair_square_corners(image) if settings.square_corners else np.asarray(image.convert("RGB"))
    height, width = original.shape[:2]
    source_depth = min(source_depth, max(8, min(height, width) // 3))
    warnings: list[str] = []

    if settings.manual_background_hex:
        color = np.asarray(_hex_to_rgb(settings.manual_background_hex), dtype=np.uint8)
        padded = np.empty((height + bleed * 2, width + bleed * 2, 3), dtype=np.uint8)
        padded[:] = color
    elif settings.extension_mode == ExtensionMode.BACKGROUND_ONLY:
        padded, patch_foreground_ratio, used_texture = _background_only_canvas(
            original,
            bleed,
            source_depth,
            settings.protection_strength,
        )
        if not used_texture:
            warnings.append("A clean texture patch was not found, so the dominant background color was used.")
        elif patch_foreground_ratio > 0.06:
            warnings.append("The automatic background sample required foreground cleanup. Review the texture closely.")
    else:
        clean = original.copy()
        masked_fraction = 0.0
        if settings.protect_foreground and settings.extension_mode == ExtensionMode.AUTOMATIC:
            clean, masked_fraction = _sanitize_border(
                original,
                source_depth,
                settings.protection_strength,
            )
            if masked_fraction > 0.42:
                warnings.append(
                    "A large amount of edge content was suppressed. Inspect the bleed preview closely."
                )

        border_type = {
            ExtensionMode.EDGE_STRETCH: cv2.BORDER_REPLICATE,
            ExtensionMode.MIRROR: cv2.BORDER_REFLECT,
            ExtensionMode.AUTOMATIC: cv2.BORDER_REFLECT_101,
            ExtensionMode.BACKGROUND_ONLY: cv2.BORDER_REFLECT_101,
        }[settings.extension_mode]
        padded = cv2.copyMakeBorder(clean, bleed, bleed, bleed, bleed, border_type)
        _apply_solid_edges(padded, bleed, width, height, analysis)
        _lock_all_seam_rows(padded, clean, bleed)

    # The original trim region is always restored pixel-for-pixel after generating the bleed.
    padded[bleed : bleed + height, bleed : bleed + width] = original
    scores = _seam_scores(padded, original, bleed)

    complex_edges = [
        edge for edge, report in analysis.items() if report.kind == EdgeKind.PHOTO or report.foreground_risk > 0.65
    ]
    if complex_edges and settings.extension_mode != ExtensionMode.BACKGROUND_ONLY:
        warnings.append(
            "Complex content touches these edges: " + ", ".join(complex_edges) + ". Manual review is recommended."
        )
    if settings.extension_mode == ExtensionMode.MIRROR:
        warnings.append("Mirror mode can create visible repeating objects and should be reviewed before print.")

    if not warnings and min(scores.values()) >= 98:
        quality = "High confidence"
    elif min(scores.values()) >= 90:
        quality = "Review recommended"
    else:
        quality = "Manual correction required"

    return ProcessResult(
        image=Image.fromarray(padded, mode="RGB"),
        bleed_pixels=bleed,
        edge_analysis=analysis,
        warnings=warnings,
        quality_label=quality,
        seam_scores=scores,
    )
