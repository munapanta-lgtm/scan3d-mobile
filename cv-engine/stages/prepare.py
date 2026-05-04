"""
Stage 1 — Prepare: Input validation and quality control.

Validates the input directory, filters valid images, and checks for
blur to reject poor-quality captures before expensive SfM processing.
"""

from pathlib import Path

import cv2
import numpy as np


VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MIN_IMAGES = 10
BLUR_THRESHOLD = 100.0  # Laplacian variance below this = blurry
MAX_BLUR_RATIO = 0.15   # Warn if >15% of images are blurry


def validate(input_dir: str) -> list[Path]:
    """
    Validate input directory and return list of valid image paths.

    Parameters
    ----------
    input_dir : str
        Path to directory containing input photographs.

    Returns
    -------
    list[Path]
        Sorted list of valid image file paths.

    Raises
    ------
    SystemExit
        If the directory doesn't exist or has too few valid images.
    """
    input_path = Path(input_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"Directory not found: {input_dir}")

    image_files = sorted(
        f for f in input_path.iterdir()
        if f.suffix.lower() in VALID_EXTENSIONS
    )
    n_images = len(image_files)

    if n_images < MIN_IMAGES:
        raise ValueError(
            f"Only {n_images} valid image(s) found in {input_dir}. "
            f"Need at least {MIN_IMAGES} for a reliable reconstruction."
        )

    print(f"[prepare] Found {n_images} valid images.")

    # --- Blur detection (Laplacian variance) ---
    blurry_count = 0
    blur_scores = []
    for img_path in image_files:
        img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        # Resize to speed up blur computation — exact value doesn't matter
        if max(img.shape) > 1000:
            scale = 1000 / max(img.shape)
            img = cv2.resize(img, None, fx=scale, fy=scale)
        score = cv2.Laplacian(img, cv2.CV_64F).var()
        blur_scores.append((img_path.name, score))
        if score < BLUR_THRESHOLD:
            blurry_count += 1

    blur_ratio = blurry_count / len(blur_scores) if blur_scores else 0
    print(
        f"[prepare] Blur check: {blurry_count}/{len(blur_scores)} images "
        f"below threshold ({BLUR_THRESHOLD}). Ratio: {blur_ratio:.1%}"
    )

    if blur_ratio > MAX_BLUR_RATIO:
        print(
            f"[prepare] WARNING: {blur_ratio:.0%} of images are blurry "
            f"(>{MAX_BLUR_RATIO:.0%}). Reconstruction quality may suffer."
        )
        # Print the 5 worst offenders
        blur_scores.sort(key=lambda x: x[1])
        print("[prepare] Blurriest images:")
        for name, score in blur_scores[:5]:
            print(f"  {name}: {score:.1f}")

    return image_files
