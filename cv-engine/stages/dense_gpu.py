"""
Stage 4 GPU — Dense: GPU-accelerated dense reconstruction.

Primary:  AliceVision CLI (MPL 2.0 — commercial OK)
Fallback: pycolmap PatchMatch stereo + fusion

AliceVision pipeline:
    depthMapEstimation → depthMapFiltering → meshing → texturing

Produces dense point cloud + textured mesh.
"""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import trimesh


def _alicevision_available() -> bool:
    """Check if AliceVision CLI binaries are installed."""
    try:
        result = subprocess.run(
            ["aliceVision_depthMapEstimation", "--help"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _export_sfm_to_alicevision(reconstruction, output_dir: Path) -> Path:
    """
    Export COLMAP reconstruction to AliceVision-compatible SfMData JSON.
    Returns path to the SfMData file.
    """
    sfm_path = output_dir / "sfm_data.json"

    views = []
    intrinsics = []
    poses = []
    cam_map = {}

    for cam_id, camera in reconstruction.cameras.items():
        intrinsic = {
            "intrinsicId": str(cam_id),
            "width": camera.width,
            "height": camera.height,
            "focalLength": camera.focal_length,
            "principalPoint": [
                camera.principal_point_x,
                camera.principal_point_y,
            ],
            "type": "pinhole",
        }
        intrinsics.append(intrinsic)
        cam_map[cam_id] = str(cam_id)

    for img_id, image in reconstruction.images.items():
        view = {
            "viewId": str(img_id),
            "poseId": str(img_id),
            "intrinsicId": cam_map.get(image.camera_id, "0"),
            "path": image.name,
            "width": reconstruction.cameras[image.camera_id].width,
            "height": reconstruction.cameras[image.camera_id].height,
        }
        views.append(view)

        # Rotation + translation
        R = image.rotmat().tolist()
        t = image.tvec.tolist()
        pose = {
            "poseId": str(img_id),
            "pose": {
                "transform": {
                    "rotation": [str(v) for row in R for v in row],
                    "center": [str(-np.dot(np.array(R).T, t)[i]) for i in range(3)],
                },
            },
        }
        poses.append(pose)

    sfm_data = {
        "version": ["1", "2", "6"],
        "views": views,
        "intrinsics": intrinsics,
        "poses": poses,
    }

    with open(sfm_path, "w") as f:
        json.dump(sfm_data, f, indent=2)

    return sfm_path


def _run_alicevision(reconstruction, input_dir: str, output_dir: Path):
    """
    Run AliceVision dense reconstruction pipeline.

    Returns (mesh, point_cloud) as trimesh objects.
    """
    av_dir = output_dir / "alicevision"
    av_dir.mkdir(parents=True, exist_ok=True)

    depth_dir = av_dir / "depth_maps"
    depth_dir.mkdir(exist_ok=True)
    filtered_dir = av_dir / "depth_maps_filtered"
    filtered_dir.mkdir(exist_ok=True)
    mesh_dir = av_dir / "mesh"
    mesh_dir.mkdir(exist_ok=True)
    texture_dir = av_dir / "textured"
    texture_dir.mkdir(exist_ok=True)

    # Export SfM data
    sfm_path = _export_sfm_to_alicevision(reconstruction, av_dir)

    # Step 1: Depth map estimation (GPU-accelerated)
    print("[dense_gpu] AliceVision: Depth map estimation (GPU)...")
    subprocess.run([
        "aliceVision_depthMapEstimation",
        "--input", str(sfm_path),
        "--imagesFolder", input_dir,
        "--output", str(depth_dir),
        "--downscale", "2",
    ], check=True, capture_output=True)

    # Step 2: Depth map filtering
    print("[dense_gpu] AliceVision: Depth map filtering...")
    subprocess.run([
        "aliceVision_depthMapFiltering",
        "--input", str(sfm_path),
        "--depthMapsFolder", str(depth_dir),
        "--output", str(filtered_dir),
    ], check=True, capture_output=True)

    # Step 3: Meshing
    print("[dense_gpu] AliceVision: Dense meshing...")
    mesh_file = mesh_dir / "mesh.obj"
    subprocess.run([
        "aliceVision_meshing",
        "--input", str(sfm_path),
        "--depthMapsFolder", str(filtered_dir),
        "--output", str(mesh_file),
    ], check=True, capture_output=True)

    # Step 4: Texturing
    print("[dense_gpu] AliceVision: Texturing...")
    subprocess.run([
        "aliceVision_texturing",
        "--input", str(mesh_file),
        "--imagesFolder", input_dir,
        "--inputMesh", str(mesh_file),
        "--output", str(texture_dir),
    ], check=True, capture_output=True)

    # Load results
    textured_mesh_path = texture_dir / "texturedMesh.obj"
    if textured_mesh_path.exists():
        mesh = trimesh.load(str(textured_mesh_path), force="mesh")
    elif mesh_file.exists():
        mesh = trimesh.load(str(mesh_file), force="mesh")
    else:
        mesh = None

    # Build point cloud from mesh vertices
    if mesh is not None:
        colors_rgba = np.full((len(mesh.vertices), 4), 200, dtype=np.uint8)
        colors_rgba[:, 3] = 255
        if hasattr(mesh.visual, "vertex_colors") and mesh.visual.vertex_colors is not None:
            colors_rgba = np.asarray(mesh.visual.vertex_colors)
        pcd = trimesh.PointCloud(mesh.vertices, colors=colors_rgba)
    else:
        pcd = trimesh.PointCloud(np.zeros((0, 3)))

    print(
        f"[dense_gpu] AliceVision complete: "
        f"{len(mesh.vertices) if mesh else 0} vertices, "
        f"{len(mesh.faces) if mesh else 0} faces"
    )

    return mesh, pcd


def _run_pycolmap_fallback(reconstruction, input_dir: str, output_dir: Path, scale_factor: float):
    """
    Fallback dense reconstruction using pycolmap PatchMatch stereo.
    Used when AliceVision is not available.
    """
    import pycolmap

    dense_dir = output_dir / "dense"
    dense_dir.mkdir(parents=True, exist_ok=True)

    # Undistort images — COLMAP expects the sparse model under input_path/
    # After our fix, reconstruction.write() saves to output/sparse/
    print("[dense_gpu] pycolmap: Undistorting images...")
    sparse_model_path = output_dir / "sparse"
    if not sparse_model_path.exists():
        # Fallback: try output/0/ (default incremental_mapping output)
        sparse_model_path = output_dir / "0"
    pycolmap.undistort_images(
        output_path=dense_dir,
        input_path=sparse_model_path,
        image_path=input_dir,
    )

    # PatchMatch stereo (GPU via COLMAP's built-in CUDA)
    print("[dense_gpu] pycolmap: PatchMatch stereo (GPU)...")
    pycolmap.patch_match_stereo(
        workspace_path=dense_dir,
    )

    # Stereo fusion
    print("[dense_gpu] pycolmap: Stereo fusion...")
    fused_ply = dense_dir / "fused.ply"
    pycolmap.stereo_fusion(
        output_path=fused_ply,
        workspace_path=dense_dir,
    )

    # Load fused point cloud
    if fused_ply.exists():
        cloud = trimesh.load(str(fused_ply))
        points = np.asarray(cloud.vertices) * scale_factor
        colors = np.asarray(cloud.colors) if hasattr(cloud, "colors") and cloud.colors is not None else None

        if colors is None:
            colors = np.full((len(points), 4), 200, dtype=np.uint8)
            colors[:, 3] = 255

        pcd = trimesh.PointCloud(points, colors=colors)

        # Attempt Poisson or Delaunay mesh from dense cloud
        try:
            from scipy.spatial import Delaunay
            if len(points) > 4:
                tri = Delaunay(points)
                mesh = trimesh.Trimesh(
                    vertices=points,
                    faces=tri.simplices[:, :3],
                    vertex_colors=colors,
                    process=True,
                )
                mesh.fix_normals()
            else:
                mesh = None
        except Exception:
            mesh = None

        print(
            f"[dense_gpu] pycolmap fallback complete: "
            f"{len(points)} dense points"
        )
    else:
        print("[dense_gpu] WARNING: Stereo fusion produced no output")
        pcd = trimesh.PointCloud(np.zeros((0, 3)))
        mesh = None

    return mesh, pcd


def reconstruct(reconstruction, scale_factor: float, input_dir: str = "", output_dir: str = ""):
    """
    GPU-accelerated dense reconstruction.

    Tries AliceVision first (full textured mesh), falls back to
    pycolmap PatchMatch stereo if AliceVision is not installed.

    Parameters
    ----------
    reconstruction : pycolmap.Reconstruction
        The SfM reconstruction with camera poses.
    scale_factor : float
        Metric scale factor from AprilTag triangulation.
    input_dir : str
        Path to original input images.
    output_dir : str
        Path to SfM output directory.

    Returns
    -------
    tuple[trimesh.Trimesh | None, trimesh.PointCloud]
    """
    output_path = Path(output_dir)

    if _alicevision_available():
        print("[dense_gpu] Using AliceVision dense reconstruction")
        mesh, pcd = _run_alicevision(reconstruction, input_dir, output_path)

        # Apply metric scale
        if mesh is not None:
            mesh.vertices *= scale_factor
        if len(pcd.vertices) > 0:
            pcd.vertices *= scale_factor

        return mesh, pcd
    else:
        print("[dense_gpu] AliceVision not found — using pycolmap PatchMatch fallback")
        return _run_pycolmap_fallback(
            reconstruction, input_dir, output_path, scale_factor
        )
