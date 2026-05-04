"""
Stage 4 — Dense: Mesh reconstruction from sparse point cloud.

Uses trimesh + scipy for geometry operations on CPU.
No Open3D dependency (not available for Python 3.14).

# TODO: Replace with AliceVision dense reconstruction when GPU available.
#       AliceVision's DepthMap + Meshing stages produce significantly
#       higher quality meshes but require CUDA.
"""

import numpy as np
import trimesh
from scipy.spatial import Delaunay


def _statistical_outlier_removal(points, colors, nb_neighbors=20, std_ratio=2.0):
    """
    Remove statistical outliers from a point cloud.
    Points whose mean distance to k-nearest neighbors exceeds
    (global_mean + std_ratio * global_std) are removed.
    """
    from scipy.spatial import KDTree

    tree = KDTree(points)
    # Query k+1 because the first neighbor is the point itself
    dists, _ = tree.query(points, k=nb_neighbors + 1)
    mean_dists = dists[:, 1:].mean(axis=1)  # skip self-distance

    global_mean = mean_dists.mean()
    global_std = mean_dists.std()
    threshold = global_mean + std_ratio * global_std

    mask = mean_dists <= threshold
    return points[mask], colors[mask], mask


def _estimate_alpha(points):
    """
    Heuristic alpha value based on median nearest-neighbor distance.
    """
    from scipy.spatial import KDTree

    tree = KDTree(points)
    dists, _ = tree.query(points, k=2)
    median_nn = np.median(dists[:, 1])
    # Alpha should be ~2-5x the median spacing for reasonable results
    return median_nn * 3.0


def reconstruct(reconstruction, scale_factor: float):
    """
    Generate a mesh from the sparse SfM reconstruction.

    Parameters
    ----------
    reconstruction : pycolmap.Reconstruction
        The SfM reconstruction containing sparse 3D points.
    scale_factor : float
        Metric scale factor from AprilTag triangulation.

    Returns
    -------
    tuple[trimesh.Trimesh | None, trimesh.PointCloud]
        The reconstructed mesh (or None if meshing fails) and the
        scaled point cloud.
    """
    # --- Extract sparse points and colors from COLMAP -----------------
    points = []
    colors = []
    for point in reconstruction.points3D.values():
        points.append(point.xyz * scale_factor)
        colors.append(point.color)  # uint8 RGB

    points = np.array(points, dtype=np.float64)
    colors = np.array(colors, dtype=np.uint8)

    print(f"[dense] Sparse cloud: {len(points)} points")

    # --- Statistical outlier removal ----------------------------------
    points, colors, mask = _statistical_outlier_removal(
        points, colors, nb_neighbors=20, std_ratio=2.0
    )
    n_removed = (~mask).sum()
    print(
        f"[dense] After outlier removal: {len(points)} points "
        f"(removed {n_removed})"
    )

    # --- Build trimesh PointCloud -------------------------------------
    # trimesh.PointCloud expects colors with alpha channel (RGBA)
    colors_rgba = np.hstack([
        colors,
        np.full((len(colors), 1), 255, dtype=np.uint8),
    ])
    pcd = trimesh.PointCloud(points, colors=colors_rgba)

    # --- Attempt mesh via Delaunay + alpha filtering ------------------
    mesh = None
    if len(points) >= 4:
        try:
            alpha = _estimate_alpha(points)
            print(f"[dense] Attempting Delaunay mesh (alpha={alpha:.4f})...")

            tri = Delaunay(points)
            faces = tri.simplices  # (n_tetra, 4)

            # Extract surface triangles from tetrahedra
            # Each tetrahedron has 4 triangular faces
            all_faces = []
            for tet in faces:
                all_faces.append([tet[0], tet[1], tet[2]])
                all_faces.append([tet[0], tet[1], tet[3]])
                all_faces.append([tet[0], tet[2], tet[3]])
                all_faces.append([tet[1], tet[2], tet[3]])
            all_faces = np.array(all_faces)

            # Filter by alpha: remove faces with circumradius > alpha
            # Compute edge lengths for each face
            keep = []
            for face in all_faces:
                verts = points[face]
                edges = [
                    np.linalg.norm(verts[0] - verts[1]),
                    np.linalg.norm(verts[1] - verts[2]),
                    np.linalg.norm(verts[0] - verts[2]),
                ]
                if max(edges) <= alpha:
                    keep.append(face)

            if keep:
                keep = np.array(keep)
                mesh = trimesh.Trimesh(
                    vertices=points,
                    faces=keep,
                    vertex_colors=colors_rgba,
                    process=True,
                )
                # Remove duplicate/degenerate faces
                mesh.remove_degenerate_faces()
                mesh.remove_duplicate_faces()
                mesh.fix_normals()

                print(
                    f"[dense] Mesh complete: "
                    f"{len(mesh.vertices)} vertices, "
                    f"{len(mesh.faces)} faces"
                )
            else:
                print(
                    "[dense] WARNING: No faces survived alpha filtering. "
                    "Exporting point cloud only."
                )
        except Exception as e:
            print(
                f"[dense] WARNING: Meshing failed ({e}). "
                "Exporting point cloud only."
            )
    else:
        print("[dense] Too few points for meshing. Exporting point cloud only.")

    return mesh, pcd
