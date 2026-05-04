"""
Stage 2 GPU — Poses: DISK feature extraction + LightGlue matching + SfM.

Replaces SIFT with learned features on GPU for:
- Better matching on textureless/metallic surfaces
- ~10x faster extraction on GPU vs CPU SIFT
- Higher inlier ratios → better reconstruction

Feature detector: DISK (BSD-3 license — commercial OK)
Feature matcher:  LightGlue (Apache 2.0 — commercial OK)
NEVER use SuperPoint (non-commercial license).

Requires: torch, kornia, lightglue, pycolmap
"""

import shutil
from pathlib import Path

import cv2
import numpy as np
import pycolmap
import torch


def _load_image_tensor(image_path: str, max_size: int = 2000, device: str = "cuda"):
    """Load image as normalized float tensor [1, 1, H, W] for DISK."""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    h, w = img.shape

    # Downscale if needed
    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale)

    tensor = torch.from_numpy(img).float() / 255.0
    return tensor.unsqueeze(0).unsqueeze(0).to(device), img.shape


def _init_disk_lightglue(device: str = "cuda"):
    """Initialize DISK extractor and LightGlue matcher."""
    from lightglue import DISK, LightGlue

    extractor = DISK(max_num_keypoints=4096).eval().to(device)
    matcher = LightGlue(features="disk").eval().to(device)

    return extractor, matcher


def _extract_all_features(
    image_paths: list[Path],
    extractor,
    device: str = "cuda",
    max_size: int = 2000,
):
    """
    Extract DISK features for all images.

    Returns dict: {image_path: {keypoints, descriptors, scales, orig_shape}}
    """
    features = {}

    for i, img_path in enumerate(image_paths):
        img_tensor, resized_shape = _load_image_tensor(
            str(img_path), max_size, device
        )

        with torch.no_grad():
            feats = extractor.extract(img_tensor)

        features[img_path.name] = {
            "keypoints": feats["keypoints"][0].cpu(),       # [N, 2]
            "descriptors": feats["descriptors"][0].cpu(),    # [N, D]
            "image_size": resized_shape,  # (H, W)
        }

        if (i + 1) % 10 == 0 or i == 0:
            n_kp = len(feats["keypoints"][0])
            print(
                f"[poses_gpu]   [{i+1}/{len(image_paths)}] "
                f"{img_path.name}: {n_kp} keypoints"
            )

    return features


def _match_sequential(
    image_paths: list[Path],
    features: dict,
    matcher,
    device: str = "cuda",
    window: int = 10,
):
    """
    Match features sequentially with LightGlue (window overlap).

    Returns list of (name_i, name_j, matches_array).
    """
    all_matches = []
    n = len(image_paths)
    n_pairs = 0

    for i in range(n):
        name_i = image_paths[i].name
        fi = features[name_i]

        for j in range(i + 1, min(i + window + 1, n)):
            name_j = image_paths[j].name
            fj = features[name_j]

            data = {
                "image0": {
                    "keypoints": fi["keypoints"].unsqueeze(0).to(device),
                    "descriptors": fi["descriptors"].unsqueeze(0).to(device),
                    "image_size": torch.tensor(
                        [fi["image_size"]], device=device
                    ),
                },
                "image1": {
                    "keypoints": fj["keypoints"].unsqueeze(0).to(device),
                    "descriptors": fj["descriptors"].unsqueeze(0).to(device),
                    "image_size": torch.tensor(
                        [fj["image_size"]], device=device
                    ),
                },
            }

            with torch.no_grad():
                result = matcher(data)

            matches = result["matches0"][0].cpu().numpy()
            valid = matches > -1
            n_matches = valid.sum()

            if n_matches >= 15:  # minimum for robust geometry
                idx_i = np.where(valid)[0]
                idx_j = matches[valid]
                match_pairs = np.column_stack([idx_i, idx_j])
                all_matches.append((name_i, name_j, match_pairs))

            n_pairs += 1

    print(
        f"[poses_gpu] Matched {n_pairs} pairs, "
        f"{len(all_matches)} with ≥15 matches"
    )
    return all_matches


def _write_to_colmap_db(
    database_path: Path,
    image_dir: Path,
    features: dict,
    matches: list,
):
    """
    Write DISK features and LightGlue matches into a COLMAP database.
    This lets us use pycolmap.incremental_mapping() with learned features.
    """
    import sqlite3

    db = sqlite3.connect(str(database_path))
    cursor = db.cursor()

    # Create COLMAP database schema
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS cameras (
            camera_id INTEGER PRIMARY KEY, model INTEGER,
            width INTEGER, height INTEGER, params BLOB,
            prior_focal_length INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS images (
            image_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            camera_id INTEGER, prior_qw REAL, prior_qx REAL,
            prior_qy REAL, prior_qz REAL, prior_tx REAL,
            prior_ty REAL, prior_tz REAL
        );
        CREATE TABLE IF NOT EXISTS keypoints (
            image_id INTEGER PRIMARY KEY, rows INTEGER, cols INTEGER,
            data BLOB
        );
        CREATE TABLE IF NOT EXISTS descriptors (
            image_id INTEGER PRIMARY KEY, rows INTEGER, cols INTEGER,
            data BLOB
        );
        CREATE TABLE IF NOT EXISTS matches (
            pair_id INTEGER PRIMARY KEY, rows INTEGER, cols INTEGER,
            data BLOB
        );
        CREATE TABLE IF NOT EXISTS two_view_geometries (
            pair_id INTEGER PRIMARY KEY, rows INTEGER, cols INTEGER,
            data BLOB, config INTEGER, F BLOB, E BLOB, H BLOB,
            qvec BLOB, tvec BLOB
        );
    """)

    # Build name → image_id mapping
    name_to_id = {}
    image_id = 1

    for img_file in sorted(image_dir.iterdir()):
        if img_file.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        name = img_file.name
        if name not in features:
            continue

        feat = features[name]
        h, w = feat["image_size"]

        # Simple pinhole camera model (one per image for now)
        focal = max(h, w) * 1.2  # rough initial focal length
        cx, cy = w / 2.0, h / 2.0
        params = np.array([focal, cx, cy], dtype=np.float64)

        cursor.execute(
            "INSERT OR IGNORE INTO cameras VALUES (?, ?, ?, ?, ?, ?)",
            (image_id, 0, w, h, params.tobytes(), 0),  # model=0 → SIMPLE_PINHOLE
        )
        cursor.execute(
            "INSERT OR IGNORE INTO images VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (image_id, name, image_id, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )

        # Write keypoints [N, 6] (x, y, a11, a12, a21, a22)
        kp = feat["keypoints"].numpy()  # [N, 2]
        n_kp = len(kp)
        kp_data = np.zeros((n_kp, 6), dtype=np.float32)
        kp_data[:, :2] = kp
        kp_data[:, 2] = 1.0  # identity affine
        kp_data[:, 5] = 1.0

        cursor.execute(
            "INSERT OR IGNORE INTO keypoints VALUES (?, ?, ?, ?)",
            (image_id, n_kp, 6, kp_data.tobytes()),
        )

        # Write descriptors [N, D]
        desc = feat["descriptors"].numpy()
        cursor.execute(
            "INSERT OR IGNORE INTO descriptors VALUES (?, ?, ?, ?)",
            (image_id, desc.shape[0], desc.shape[1], desc.tobytes()),
        )

        name_to_id[name] = image_id
        image_id += 1

    # Write matches
    def _pair_id(id1, id2):
        if id1 > id2:
            id1, id2 = id2, id1
        return id1 * 2147483647 + id2

    for name_i, name_j, match_pairs in matches:
        id_i = name_to_id.get(name_i)
        id_j = name_to_id.get(name_j)
        if id_i is None or id_j is None:
            continue

        pair_id = _pair_id(id_i, id_j)
        if id_i > id_j:
            match_pairs = match_pairs[:, ::-1]

        data = match_pairs.astype(np.uint32).tobytes()
        cursor.execute(
            "INSERT OR IGNORE INTO matches VALUES (?, ?, ?, ?)",
            (pair_id, len(match_pairs), 2, data),
        )

    db.commit()
    db.close()

    print(
        f"[poses_gpu] Wrote {len(name_to_id)} images, "
        f"{len(matches)} match pairs to COLMAP DB"
    )


def reconstruct(input_dir: str, output_dir: str):
    """
    GPU-accelerated SfM: DISK extraction + LightGlue matching + COLMAP SfM.

    Parameters
    ----------
    input_dir : str
        Path to directory containing input images.
    output_dir : str
        Path to directory where reconstruction outputs will be stored.

    Returns
    -------
    tuple[pycolmap.Reconstruction, Path]
        The best reconstruction object and the output directory path.
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[poses_gpu] Device: {device}")

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if output_path.exists():
        print("[poses_gpu] Cleaning stale output directory...")
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True)

    database_path = output_path / "database.db"

    # Collect images
    valid_ext = {".jpg", ".jpeg", ".png"}
    image_paths = sorted(
        f for f in input_path.iterdir() if f.suffix.lower() in valid_ext
    )
    print(f"[poses_gpu] {len(image_paths)} images")

    # ------------------------------------------------------------------
    # Feature Extraction — DISK on GPU
    # ------------------------------------------------------------------
    print("[poses_gpu] Extracting DISK features...")
    extractor, matcher = _init_disk_lightglue(device)
    features = _extract_all_features(image_paths, extractor, device)

    # ------------------------------------------------------------------
    # Feature Matching — LightGlue, sequential window=10
    # ------------------------------------------------------------------
    print("[poses_gpu] Matching with LightGlue (window=10)...")
    matches = _match_sequential(image_paths, features, matcher, device, window=10)

    # Free GPU memory before SfM
    del extractor, matcher
    torch.cuda.empty_cache()

    # ------------------------------------------------------------------
    # Write to COLMAP database
    # ------------------------------------------------------------------
    print("[poses_gpu] Writing features to COLMAP database...")
    _write_to_colmap_db(database_path, input_path, features, matches)

    # Generate pairs.txt for geometric verification
    print("[poses_gpu] Geometric verification...")
    pairs_path = output_path / "pairs.txt"
    with open(pairs_path, "w") as f:
        for name_i, name_j, _ in matches:
            f.write(f"{name_i} {name_j}\n")

    pycolmap.verify_matches(
        database_path,
        pairs_path=pairs_path,
    )

    # ------------------------------------------------------------------
    # Incremental SfM
    # ------------------------------------------------------------------
    print("[poses_gpu] Incremental SfM reconstruction...")

    # TODO: Initialize with ARCore poses as prior when available.
    #       This would use pycolmap IncrementalMapperOptions with
    #       init_image_id set to an ARCore-tracked frame, and priors
    #       from the device's 6DOF tracking.

    maps = pycolmap.incremental_mapping(
        database_path, input_path, output_path
    )

    if not maps:
        raise RuntimeError(
            "GPU reconstruction failed — no valid model produced."
        )

    if isinstance(maps, dict):
        reconstruction = maps.get(0) or next(iter(maps.values()))
    else:
        reconstruction = maps[0]

    sparse_ply_path = output_path / "sparse.ply"
    reconstruction.export_PLY(sparse_ply_path)

    print(
        f"[poses_gpu] Reconstruction complete. "
        f"Cameras: {reconstruction.num_cameras()}, "
        f"Images: {reconstruction.num_reg_images()}, "
        f"Points: {reconstruction.num_points3D()}"
    )

    return reconstruction, output_path
