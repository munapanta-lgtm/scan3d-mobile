"""
Stage 5 — Export: Multi-format output of scaled mesh and point cloud.

Exports the reconstructed 3D model in multiple formats:
- .ply  (point cloud — trimesh)
- .glb  (mesh — trimesh, for mobile viewer)
- .obj  (mesh — trimesh, for CAD/desktop tools)
- .e57  (point cloud — pye57, for professional metrology)

Prints a summary report with vertex/face counts and bounding box
dimensions in millimeters for quick validation.

No Open3D dependency (not available for Python 3.14).
"""

from pathlib import Path

import numpy as np
import trimesh


def export_all(
    mesh: trimesh.Trimesh | None,
    pcd: trimesh.PointCloud,
    output_dir: str,
    metrics: dict,
):
    """
    Export mesh and point cloud in multiple formats.

    Parameters
    ----------
    mesh : trimesh.Trimesh or None
        The scaled, cleaned mesh (None if meshing failed).
    pcd : trimesh.PointCloud
        The scaled point cloud.
    output_dir : str
        Directory to write output files.
    metrics : dict
        AprilTag validation metrics for the summary report.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    points = np.asarray(pcd.vertices)

    # ------------------------------------------------------------------
    # PLY — point cloud
    # ------------------------------------------------------------------
    ply_path = output_path / "sparse_scaled.ply"
    pcd.export(str(ply_path))
    print(f"[export] PLY point cloud: {ply_path}")

    # ------------------------------------------------------------------
    # Mesh exports (if mesh was generated)
    # ------------------------------------------------------------------
    if mesh is not None and len(mesh.faces) > 0:
        # GLB — binary glTF for mobile viewer
        glb_path = output_path / "mesh.glb"
        mesh.export(str(glb_path), file_type="glb")
        print(f"[export] GLB mesh: {glb_path}")

        # OBJ — for CAD and desktop tools
        obj_path = output_path / "mesh.obj"
        mesh.export(str(obj_path), file_type="obj")
        print(f"[export] OBJ mesh: {obj_path}")
    else:
        print("[export] No mesh available — skipping GLB/OBJ export.")

    # ------------------------------------------------------------------
    # E57 — point cloud for professional metrology
    # ------------------------------------------------------------------
    try:
        import pye57

        e57_path = output_path / "model.e57"
        e57_writer = pye57.E57(str(e57_path), mode="w")
        data = {
            "cartesianX": points[:, 0].astype(np.float64),
            "cartesianY": points[:, 1].astype(np.float64),
            "cartesianZ": points[:, 2].astype(np.float64),
        }
        # Add colors if available
        if pcd.colors is not None and len(pcd.colors) > 0:
            colors = np.asarray(pcd.colors)
            data["colorRed"] = colors[:, 0].astype(np.uint8)
            data["colorGreen"] = colors[:, 1].astype(np.uint8)
            data["colorBlue"] = colors[:, 2].astype(np.uint8)

        e57_writer.write_scan_raw(data)
        e57_writer.close()
        print(f"[export] E57 point cloud: {e57_path}")
    except ImportError:
        print("[export] pye57 not available, skipping E57 export.")
    except Exception as e:
        print(f"[export] E57 export failed: {e}")

    # ------------------------------------------------------------------
    # Summary report
    # ------------------------------------------------------------------
    n_vertices = len(mesh.vertices) if mesh is not None else 0
    n_faces = len(mesh.faces) if mesh is not None else 0

    bbox_min = points.min(axis=0)
    bbox_max = points.max(axis=0)
    bbox_dims = (bbox_max - bbox_min) * 1000  # mm

    print()
    print("=" * 60)
    print("  SCAN3D MOBILE — Export Summary")
    print("=" * 60)
    print(f"  Vertices:       {n_vertices:,}")
    print(f"  Faces:          {n_faces:,}")
    print(f"  Point cloud:    {len(points):,} points")
    print(
        f"  Bounding box:   "
        f"{bbox_dims[0]:.1f} x {bbox_dims[1]:.1f} x {bbox_dims[2]:.1f} mm"
    )
    print()
    print("  --- AprilTag Validation ---")
    print(f"  Tag ID:         {metrics.get('tag_id')}")
    print(f"  Views used:     {metrics.get('num_views')}")
    print(
        f"  Expected side:  {metrics.get('tag_size_m', 0) * 1000:.1f} mm"
    )
    print(
        f"  Measured sides: "
        f"{[f'{s:.1f}' for s in metrics.get('sides_metric_mm', [])]}"
    )
    print(f"  Side CV:        {metrics.get('cv_sides', 0):.2%}")
    print(f"  Diagonal 1:     {metrics.get('diag_1_mm', 0):.1f} mm")
    print(f"  Diagonal 2:     {metrics.get('diag_2_mm', 0):.1f} mm")
    print(f"  Expected diag:  {metrics.get('expected_diag_mm', 0):.1f} mm")
    diag_err = metrics.get("diag_error_pct", 0)
    passed = metrics.get("pass", False)
    print(
        f"  Diagonal error: {diag_err:.2f}%  "
        f"{'PASS' if passed else 'FAIL — >2%'}"
    )
    print("=" * 60)
    print()
    print(f"  Output directory: {output_path}")
    print(
        "  Verify: open mesh.glb in a 3D viewer or sparse_scaled.ply in "
        "CloudCompare."
    )
