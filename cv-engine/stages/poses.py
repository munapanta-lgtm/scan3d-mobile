"""
Stage 2 — Poses: Feature extraction, matching, and SfM reconstruction.

Uses pycolmap for SIFT extraction and sequential matching, then runs
incremental Structure from Motion to produce camera poses and a sparse
3D point cloud.
"""

import shutil
from pathlib import Path

import pycolmap


def reconstruct(input_dir: str, output_dir: str):
    """
    Run feature extraction, matching, and incremental SfM.

    Parameters
    ----------
    input_dir : str
        Path to directory containing input images.
    output_dir : str
        Path to directory where reconstruction outputs will be stored.
        Will be wiped if it already exists.

    Returns
    -------
    tuple[pycolmap.Reconstruction, Path]
        The best reconstruction object and the path to the output directory.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Clean stale outputs to avoid corrupt database issues
    if output_path.exists():
        print("[poses] Cleaning stale output directory...")
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True)

    database_path = output_path / "database.db"

    # --- Count images for progress reporting ---
    valid_ext = {".jpg", ".jpeg", ".png"}
    n_images = sum(
        1 for f in input_path.iterdir() if f.suffix.lower() in valid_ext
    )

    # ------------------------------------------------------------------
    # Feature Extraction
    # ------------------------------------------------------------------
    print("[poses] Feature extraction (SIFT)...")
    # TODO: replace with DISK + LightGlue for production (SIFT is slow on
    #       metallic / textureless surfaces common in industrial scans).
    extraction_options = pycolmap.FeatureExtractionOptions()
    extraction_options.max_image_size = 2000        # downscale 12MP → ~2K
    extraction_options.num_threads = 2              # limit RAM on 8GB machines
    extraction_options.sift.max_num_features = 4096

    print(
        f"[poses]   max_image_size={extraction_options.max_image_size}, "
        f"num_threads={extraction_options.num_threads}, "
        f"max_num_features={extraction_options.sift.max_num_features}"
    )

    pycolmap.extract_features(
        database_path, input_path, extraction_options=extraction_options
    )

    # ------------------------------------------------------------------
    # Feature Matching — sequential with overlap window
    # ------------------------------------------------------------------
    n_seq_pairs = n_images * 10  # each image matched against 10 neighbors
    print(
        f"[poses] Sequential matching (~{n_seq_pairs} pairs, "
        f"window=10)..."
    )
    # TODO: replace with DISK + LightGlue matching for production.
    pairing_options = pycolmap.SequentialPairingOptions()
    pairing_options.overlap = 10
    pycolmap.match_sequential(database_path, pairing_options=pairing_options)

    # ------------------------------------------------------------------
    # Incremental SfM
    # ------------------------------------------------------------------
    print("[poses] Incremental SfM reconstruction...")
    maps = pycolmap.incremental_mapping(
        database_path, input_path, output_path
    )

    if not maps:
        raise RuntimeError("Reconstruction failed — no valid model produced.")

    # pycolmap returns dict {model_id: Reconstruction}
    if isinstance(maps, dict):
        reconstruction = maps.get(0) or next(iter(maps.values()))
    else:
        reconstruction = maps[0]

    # Export un-scaled sparse cloud for reference
    sparse_ply_path = output_path / "sparse.ply"
    reconstruction.export_PLY(sparse_ply_path)

    print(
        f"[poses] Reconstruction complete. "
        f"Cameras: {reconstruction.num_cameras()}, "
        f"Images: {reconstruction.num_reg_images()}, "
        f"Points: {reconstruction.num_points3D()}"
    )

    return reconstruction, output_path
