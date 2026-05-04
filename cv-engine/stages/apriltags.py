"""
Stage 3 — AprilTags: Metric scale computation via multi-view triangulation.

Detects AprilTags (tag36h11 family) in reconstructed images, triangulates
tag corners in 3D using COLMAP camera poses, and computes a metric scale
factor from the known physical tag size.

Key implementation notes:
- GPU pipeline (DISK) may create per-image cameras at downscaled resolution.
  Images are loaded, EXIF-transposed, and resized to match COLMAP camera
  dimensions so 2D tag corners align with COLMAP's coordinate space.
- img.cam_from_world() is a METHOD in pycolmap 4.x (call with parentheses).
- Two-pass triangulation filters outlier views by reprojection error.
"""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _triangulate_multiview(observations):
    """
    Triangulate a single 3D point from multiple 2D observations via DLT.

    Parameters
    ----------
    observations : list of (P, point_2d)
        P is a 3×4 projection matrix, point_2d is (x, y).

    Returns
    -------
    np.ndarray, shape (3,)
    """
    A = []
    for P, (x, y) in observations:
        A.append(x * P[2, :] - P[0, :])
        A.append(y * P[2, :] - P[1, :])
    A = np.array(A)
    _, _, Vt = np.linalg.svd(A)
    X = Vt[-1]
    return X[:3] / X[3]


def _reprojection_error(P, point_3d, point_2d):
    """Reprojection error in pixels for one observation."""
    X_h = np.append(point_3d, 1.0)
    projected = P @ X_h
    projected = projected[:2] / projected[2]
    return np.linalg.norm(projected - np.array(point_2d))


def _triangulate_filtered(observations, max_reproj_px=4.0):
    """
    Two-pass triangulation with reprojection-error outlier rejection.

    Returns
    -------
    point_3d : np.ndarray (3,)
    n_inliers : int
    n_total : int
    """
    # Pass 1: rough estimate from all views
    point_3d = _triangulate_multiview(observations)

    # Per-view reprojection errors
    errors = [
        _reprojection_error(P, point_3d, pt) for P, pt in observations
    ]

    # Filter inliers
    inliers = [
        obs for obs, err in zip(observations, errors) if err <= max_reproj_px
    ]

    n_total = len(observations)
    n_inliers = len(inliers)

    if n_inliers < 2:
        return point_3d, n_inliers, n_total

    # Pass 2: refined triangulation from inliers only
    point_3d = _triangulate_multiview(inliers)
    return point_3d, n_inliers, n_total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

MAX_REPROJ_PX = 4.0
MIN_INLIER_VIEWS = 5


def compute_scale(reconstruction, input_dir: str, tag_size_m: float):
    """
    Detect AprilTags, triangulate corners, and compute metric scale factor.

    Parameters
    ----------
    reconstruction : pycolmap.Reconstruction
        The SfM reconstruction with camera poses.
    input_dir : str
        Path to the original image directory.
    tag_size_m : float
        Physical side length of the AprilTag in meters.

    Returns
    -------
    tuple[float, dict]
        (scale_factor, metrics_dict) where metrics_dict contains validation
        data for the export report.
    """
    input_path = Path(input_dir)

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    aruco_params = cv2.aruco.DetectorParameters()
    aruco_detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    # Per-corner observation lists: each stores (P, point_2d) tuples
    corner_observations = {i: [] for i in range(4)}
    target_tag_id = None

    images = list(reconstruction.images.values())
    for img in images:
        img_path = input_path / img.name

        # Load image, apply EXIF transpose, and resize to match COLMAP
        # camera dimensions. The GPU pipeline (DISK) may create per-image
        # cameras at downscaled resolution — tag detection must match.
        camera = reconstruction.cameras[img.camera_id]
        try:
            pil_img = Image.open(str(img_path))
            pil_img = ImageOps.exif_transpose(pil_img)
            pil_img = pil_img.resize((camera.width, camera.height))
            cv_img = np.array(pil_img.convert("L"))
        except Exception:
            continue
        if cv_img is None:
            continue

        corners_arr, ids, _ = aruco_detector.detectMarkers(cv_img)
        if ids is None or len(ids) == 0:
            continue

        # Build projection matrix P = K @ [R | t]
        # Handle various COLMAP camera models:
        #   SIMPLE_PINHOLE (0): params = [f, cx, cy]
        #   PINHOLE (1):        params = [fx, fy, cx, cy]
        #   SIMPLE_RADIAL (2):  params = [f, cx, cy, k]
        #   RADIAL (3):         params = [f, cx, cy, k1, k2]
        p = camera.params
        model_id = camera.model.value if hasattr(camera.model, 'value') else camera.model_id
        if model_id == 1:  # PINHOLE
            fx, fy, cx, cy = p[0], p[1], p[2], p[3]
        else:  # SIMPLE_PINHOLE, SIMPLE_RADIAL, RADIAL — all f, cx, cy
            fx, fy, cx, cy = p[0], p[0], p[1], p[2]

        K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])

        # pycolmap 4.x: cam_from_world() is a method
        cam_from_world = img.cam_from_world()
        R = cam_from_world.rotation.matrix()
        t = cam_from_world.translation

        E = np.hstack((R, t.reshape(3, 1)))
        P = K @ E

        # Lock onto the first tag we find; filter by tag_id thereafter
        for idx in range(len(ids)):
            tag_id = int(ids[idx][0])
            if target_tag_id is None:
                target_tag_id = tag_id
            if tag_id == target_tag_id:
                tag_corners = corners_arr[idx][0]  # shape (4, 2)
                for i in range(4):
                    corner_observations[i].append((P, tag_corners[i]))
                break

    num_views = min(len(obs) for obs in corner_observations.values())
    print(f"[apriltags] Tag ID {target_tag_id} detected in {num_views} view(s).")

    if num_views < 2:
        raise RuntimeError(
            "Need at least 2 views of the AprilTag for triangulation. "
            "Metric scale cannot be applied."
        )

    # --- Triangulate with reprojection filtering ----------------------
    corners_3d = []
    corner_inlier_counts = []
    for i in range(4):
        c_3d, n_in, n_tot = _triangulate_filtered(
            corner_observations[i], max_reproj_px=MAX_REPROJ_PX
        )
        corners_3d.append(c_3d)
        corner_inlier_counts.append((n_in, n_tot))
        print(
            f"[apriltags]   Corner {i}: {n_in}/{n_tot} inlier views "
            f"(threshold {MAX_REPROJ_PX}px)"
        )
        if n_in < MIN_INLIER_VIEWS:
            print(
                f"[apriltags]   WARNING: Corner {i} has only {n_in} inlier "
                f"views (minimum recommended: {MIN_INLIER_VIEWS}). "
                "Scale accuracy may be degraded."
            )

    # --- Compute scale factor from tag geometry -----------------------
    side_lengths = [
        np.linalg.norm(corners_3d[0] - corners_3d[1]),
        np.linalg.norm(corners_3d[1] - corners_3d[2]),
        np.linalg.norm(corners_3d[2] - corners_3d[3]),
        np.linalg.norm(corners_3d[3] - corners_3d[0]),
    ]
    measured_size = np.median(side_lengths)

    # Consistency check
    std_sides = np.std(side_lengths)
    cv_sides = std_sides / measured_size
    if cv_sides > 0.05:
        print(
            f"[apriltags] WARNING: Scale inconsistency. "
            f"CV(sides) = {cv_sides:.1%}"
        )
        print(
            f"[apriltags]   Side lengths (COLMAP units): "
            f"{[f'{d:.6f}' for d in side_lengths]}"
        )

    scale_factor = tag_size_m / measured_size
    print(f"[apriltags] Median side in COLMAP units: {measured_size:.6f}")
    print(f"[apriltags] Scale factor: {scale_factor:.6f}")

    # --- Build metrics for validation report --------------------------
    corners_metric = [c * scale_factor for c in corners_3d]
    sides_metric = [s * scale_factor for s in side_lengths]
    diag_1 = np.linalg.norm(corners_metric[0] - corners_metric[2])
    diag_2 = np.linalg.norm(corners_metric[1] - corners_metric[3])
    expected_diag = tag_size_m * np.sqrt(2)
    diag_err = abs(diag_1 - expected_diag) / expected_diag

    metrics = {
        "tag_id": target_tag_id,
        "num_views": num_views,
        "corner_inliers": corner_inlier_counts,
        "tag_size_m": tag_size_m,
        "sides_metric_mm": [s * 1000 for s in sides_metric],
        "cv_sides": cv_sides,
        "diag_1_mm": diag_1 * 1000,
        "diag_2_mm": diag_2 * 1000,
        "expected_diag_mm": expected_diag * 1000,
        "diag_error_pct": diag_err * 100,
        "pass": diag_err < 0.02,
    }

    return scale_factor, metrics
