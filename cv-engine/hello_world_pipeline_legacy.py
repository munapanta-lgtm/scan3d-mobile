"""
SCAN3D MOBILE — Hello World CV Pipeline

Produces a metrically-scaled sparse point cloud (.ply) from a folder of
photographs that include at least one AprilTag (tag36h11) of known size.

Usage:
    python hello_world_pipeline.py /path/to/photos --tag-size 0.15

Validation criterion: measure the distance between two tag corners in the
output PLY.  If it matches the physical measurement within ~1%, the pipeline
works.  Dense mesh generation is deferred to Phase 1 (AliceVision on GPU).
"""

import argparse
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
import pycolmap
import trimesh
from PIL import Image



# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def triangulate_multiview(observations):
    """
    Triangulate a single 3D point from multiple 2D observations.

    Parameters
    ----------
    observations : list of (P, point_2d)
        P is a 3×4 projection matrix, point_2d is (x, y).

    Returns
    -------
    np.ndarray, shape (3,)
        The triangulated 3D point.
    """
    A = []
    for P, (x, y) in observations:
        A.append(x * P[2, :] - P[0, :])
        A.append(y * P[2, :] - P[1, :])
    A = np.array(A)
    _, _, Vt = np.linalg.svd(A)
    X = Vt[-1]
    return X[:3] / X[3]


def reprojection_error(P, point_3d, point_2d):
    """
    Compute the reprojection error (pixels) for a single observation.
    """
    X_h = np.append(point_3d, 1.0)
    projected = P @ X_h
    projected = projected[:2] / projected[2]
    return np.linalg.norm(projected - np.array(point_2d))


def triangulate_filtered(observations, max_reproj_px=4.0, min_views=5):
    """
    Two-pass triangulation with reprojection-error filtering.

    1. Triangulate from ALL observations to get an initial 3D estimate.
    2. Compute per-view reprojection error; discard views > max_reproj_px.
    3. Re-triangulate from inlier views only.

    Returns
    -------
    point_3d : np.ndarray, shape (3,)
    n_inliers : int
    n_total : int
    """
    # Pass 1: rough triangulation from all views
    point_3d = triangulate_multiview(observations)

    # Compute per-view reprojection errors
    errors = [
        reprojection_error(P, point_3d, pt) for P, pt in observations
    ]

    # Filter inliers
    inliers = [
        obs for obs, err in zip(observations, errors) if err <= max_reproj_px
    ]

    n_total = len(observations)
    n_inliers = len(inliers)

    if n_inliers < 2:
        # Not enough inliers — return the unfiltered result
        return point_3d, n_inliers, n_total

    # Pass 2: refined triangulation from inliers only
    point_3d = triangulate_multiview(inliers)
    return point_3d, n_inliers, n_total


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def run_pipeline(input_dir: str, tag_size_m: float):
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"Error: Directory {input_dir} not found.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Pre-flight: count valid images and reject junk early
    # ------------------------------------------------------------------
    image_files = [
        f for f in sorted(input_path.iterdir())
        if f.suffix.lower() in VALID_EXTENSIONS
    ]
    n_images = len(image_files)
    if n_images < 10:
        print(
            f"Error: Only {n_images} valid image(s) found. "
            "Need at least 10 for a reliable reconstruction."
        )
        sys.exit(1)

    output_path = input_path / "output"
    if output_path.exists():
        print("Cleaning stale output directory...")
        shutil.rmtree(output_path)
    output_path.mkdir()

    database_path = output_path / "database.db"

    # ------------------------------------------------------------------
    # Step 1 — Feature extraction
    # ------------------------------------------------------------------
    print("=== Step 1: Feature Extraction ===")
    # TODO: replace with DISK + LightGlue for production (SIFT is slow on
    #       metallic / textureless surfaces common in industrial scans).
    extraction_options = pycolmap.FeatureExtractionOptions()
    extraction_options.max_image_size = 2000        # downscale 12MP → ~2K longest side
    extraction_options.num_threads = 2              # limit threads to avoid OOM on 8GB RAM
    extraction_options.sift.max_num_features = 4096 # cap features to limit RAM
    pycolmap.extract_features(
        database_path, input_path, extraction_options=extraction_options
    )

    # ------------------------------------------------------------------
    # Step 2 — Feature matching
    # ------------------------------------------------------------------
    n_pairs = n_images * (n_images - 1) // 2
    print(
        f"=== Step 2: Feature Matching "
        f"({n_pairs} pairs — this may take a while on CPU) ==="
    )
    # TODO: replace with DISK + LightGlue matching for production.
    # For >200 images consider sequential matching with a sliding window
    # instead of exhaustive to keep CPU time manageable.
    pycolmap.match_exhaustive(database_path)

    # ------------------------------------------------------------------
    # Step 3 — Incremental SfM
    # ------------------------------------------------------------------
    print("=== Step 3: Incremental SfM Reconstruction ===")
    maps = pycolmap.incremental_mapping(database_path, input_path, output_path)

    if not maps:
        print("Error: Reconstruction failed — no valid model produced.")
        sys.exit(1)

    # pycolmap returns a dict {model_id: Reconstruction}
    if isinstance(maps, dict):
        reconstruction = maps.get(0) or next(iter(maps.values()))
    else:
        reconstruction = maps[0]

    print(
        f"Reconstruction successful.  "
        f"Cameras: {reconstruction.num_cameras()}, "
        f"Images: {reconstruction.num_reg_images()}, "
        f"3D points: {reconstruction.num_points3D()}"
    )

    # Export the un-scaled sparse cloud for reference
    sparse_ply_path = output_path / "sparse.ply"
    reconstruction.export_PLY(sparse_ply_path)

    # ------------------------------------------------------------------
    # Step 4 — AprilTag multi-view triangulation for metric scale
    # ------------------------------------------------------------------
    print("=== Step 4: AprilTag Multi-view Triangulation ===")
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    aruco_params = cv2.aruco.DetectorParameters()
    aruco_detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    # Each corner keeps its own list of (P, point_2d) so that the
    # triangulation is self-contained per corner — no implicit assumption
    # that all four corners always appear together.
    corner_observations = {i: [] for i in range(4)}
    target_tag_id = None  # lock onto the first tag we find

    images = list(reconstruction.images.values())
    for img in images:
        img_path = input_path / img.name
        # Use PIL without EXIF transpose — COLMAP uses raw pixel orientation,
        # not EXIF-rotated. cv2.imread auto-applies EXIF in OpenCV 4.5.2+,
        # so we avoid it here to stay in the same coordinate space as COLMAP.
        try:
            pil_img = Image.open(str(img_path))
            cv_img = np.array(pil_img.convert('L'))
        except Exception:
            continue
        if cv_img is None:
            continue

        corners_arr, ids, _ = aruco_detector.detectMarkers(cv_img)
        if ids is None or len(ids) == 0:
            continue

        # --- Build the projection matrix P = K @ [R | t] ---------------
        # COLMAP stores intrinsics in original image dimensions, so the
        # raw-pixel tag corners are already in the same coordinate space.
        camera = reconstruction.cameras[img.camera_id]
        K = camera.calibration_matrix()

        # pycolmap 4.x exposes cam_from_world as a method.
        cam_from_world = img.cam_from_world()
        R = cam_from_world.rotation.matrix()
        t = cam_from_world.translation

        E = np.hstack((R, t.reshape(3, 1)))
        P = K @ E

        # --- Find the target tag in this frame -------------------------
        for idx in range(len(ids)):
            tag_id = int(ids[idx][0])
            if target_tag_id is None:
                target_tag_id = tag_id
            if tag_id == target_tag_id:
                tag_corners = corners_arr[idx][0]  # shape (4, 2)
                for i in range(4):
                    corner_observations[i].append((P, tag_corners[i]))
                break  # one tag per frame is enough

    num_views = min(len(obs) for obs in corner_observations.values())
    print(f"Tag ID {target_tag_id} detected in {num_views} view(s).")

    if num_views < 2:
        print(
            "Error: Need at least 2 views of the AprilTag for "
            "triangulation.  Metric scale cannot be applied."
        )
        sys.exit(1)

    # --- Triangulate the 4 corners with reprojection filtering --------
    MAX_REPROJ_PX = 4.0
    MIN_INLIER_VIEWS = 5

    corners_3d = []
    for i in range(4):
        c_3d, n_in, n_tot = triangulate_filtered(
            corner_observations[i],
            max_reproj_px=MAX_REPROJ_PX,
            min_views=MIN_INLIER_VIEWS,
        )
        corners_3d.append(c_3d)
        print(
            f"  Corner {i}: {n_in}/{n_tot} inlier views "
            f"(threshold {MAX_REPROJ_PX}px)"
        )
        if n_in < MIN_INLIER_VIEWS:
            print(
                f"  WARNING: Corner {i} has only {n_in} inlier views "
                f"(minimum recommended: {MIN_INLIER_VIEWS}). "
                "Scale accuracy may be degraded."
            )

    # --- Compute scale factor from tag side lengths --------------------
    side_lengths = [
        np.linalg.norm(corners_3d[0] - corners_3d[1]),
        np.linalg.norm(corners_3d[1] - corners_3d[2]),
        np.linalg.norm(corners_3d[2] - corners_3d[3]),
        np.linalg.norm(corners_3d[3] - corners_3d[0]),
    ]
    measured_size = np.median(side_lengths)  # median is more robust to outliers

    # Consistency check: a square tag should have 4 equal sides
    std_sides = np.std(side_lengths)
    cv_sides = std_sides / measured_size
    if cv_sides > 0.05:
        print(
            f"WARNING: Scale inconsistency detected.  "
            f"CV(sides) = {cv_sides:.1%}"
        )
        print(
            f"  Side lengths (COLMAP units): "
            f"{[f'{d:.6f}' for d in side_lengths]}"
        )
        print(
            "  This suggests triangulation errors.  "
            "Check image quality and tag visibility."
        )

    scale_factor = tag_size_m / measured_size
    print(f"Tag median side in COLMAP units: {measured_size:.6f}")
    print(f"Computed scale factor: {scale_factor:.6f}")

    # ------------------------------------------------------------------
    # Step 5 — Scale the sparse cloud and export
    # ------------------------------------------------------------------
    print("=== Step 5: Applying Metric Scale & Exporting PLY ===")
    # NOTE: sparse SfM produces a point cloud, NOT a mesh.  Dense
    # reconstruction (Phase 1, AliceVision on GPU) will produce the actual
    # surface mesh.  This PLY is the validation deliverable.
    cloud = trimesh.load(sparse_ply_path)
    cloud.apply_transform(trimesh.transformations.scale_matrix(scale_factor))

    scaled_ply_path = output_path / "sparse_scaled.ply"
    cloud.export(scaled_ply_path)

    # ------------------------------------------------------------------
    # Validation report
    # ------------------------------------------------------------------
    # Scale the triangulated corners to metric space for the report
    corners_metric = [c * scale_factor for c in corners_3d]

    diag_1 = np.linalg.norm(corners_metric[0] - corners_metric[2])
    diag_2 = np.linalg.norm(corners_metric[1] - corners_metric[3])
    expected_diag = tag_size_m * np.sqrt(2)

    sides_metric = [s * scale_factor for s in side_lengths]

    print()
    print("=== Validation Report ===")
    print(f"Tag ID:                 {target_tag_id}")
    print(f"Views used:             {num_views}")
    print(f"Expected tag side:      {tag_size_m * 1000:.1f} mm")
    print(
        f"Measured sides (mm):    "
        f"{[f'{s*1000:.1f}' for s in sides_metric]}"
    )
    print(
        f"Side CV (std/mean):     {cv_sides:.2%}  "
        f"({'OK' if cv_sides <= 0.05 else 'HIGH — check data'})"
    )
    print(f"Measured diagonal 1:    {diag_1 * 1000:.1f} mm")
    print(f"Measured diagonal 2:    {diag_2 * 1000:.1f} mm")
    print(f"Expected diagonal:      {expected_diag * 1000:.1f} mm")
    diag_err = abs(diag_1 - expected_diag) / expected_diag
    print(
        f"Diagonal error:         {diag_err:.2%}  "
        f"({'PASS' if diag_err < 0.02 else 'FAIL — >2%'})"
    )
    print()
    print(f"Scaled point cloud saved to: {scaled_ply_path}")
    print(
        "Next step: open in CloudCompare / MeshLab and measure between "
        "two known physical points to confirm metric accuracy."
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SCAN3D MOBILE — Hello World CV Pipeline"
    )
    parser.add_argument(
        "input_dir",
        type=str,
        help="Path to the directory containing input images",
    )
    parser.add_argument(
        "--tag-size",
        type=float,
        required=True,
        help=(
            "Physical side length of the printed AprilTag in meters "
            "(e.g. 0.10 for 10 cm)"
        ),
    )
    args = parser.parse_args()
    run_pipeline(args.input_dir, args.tag_size)
