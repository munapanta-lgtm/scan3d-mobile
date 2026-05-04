"""
SCAN3D MOBILE — Modular CV Pipeline Orchestrator

Auto-detects GPU and selects the appropriate processing stages:
- GPU: DISK + LightGlue extraction → AliceVision dense reconstruction
- CPU: SIFT extraction → Delaunay sparse reconstruction

Usage:
    python pipeline.py /path/to/photos --tag-size 0.167
    python pipeline.py /path/to/photos --tag-size 0.167 --output-dir /path/to/output

Stages:
    1. prepare   — Validate inputs, check blur
    2. poses     — Feature extraction, matching, incremental SfM
    3. apriltags — AprilTag detection, multi-view triangulation, metric scale
    4. dense     — Mesh reconstruction (GPU: AliceVision / CPU: Delaunay)
    5. export    — PLY, GLB, OBJ, E57 output with validation report
"""

import argparse
import sys
import time
from pathlib import Path

# --- GPU auto-detection ---------------------------------------------------
_GPU_AVAILABLE = False
try:
    import torch
    _GPU_AVAILABLE = torch.cuda.is_available()
except ImportError:
    pass

if _GPU_AVAILABLE:
    from stages import poses_gpu as poses
    from stages import dense_gpu as dense
    print("[pipeline] GPU detected, using DISK+LightGlue + dense reconstruction")
else:
    from stages import poses, dense
    print("[pipeline] CPU mode, using SIFT + sparse reconstruction")

# These stages are always CPU (no GPU needed)
from stages import prepare, apriltags, export


def run(input_dir: str, tag_size: float, output_dir: str | None = None):
    """
    Execute the full reconstruction pipeline.

    Parameters
    ----------
    input_dir : str
        Path to directory containing input photographs.
    tag_size : float
        Physical side length of the AprilTag in meters.
    output_dir : str, optional
        Path for output files. Defaults to <input_dir>/output.
    """
    t_start = time.time()

    if output_dir is None:
        output_dir = str(Path(input_dir) / "output")

    mode = "GPU (DISK+LightGlue)" if _GPU_AVAILABLE else "CPU (SIFT)"

    print()
    print("=" * 60)
    print("  SCAN3D MOBILE — CV Pipeline")
    print("=" * 60)
    print(f"  Input:    {input_dir}")
    print(f"  Output:   {output_dir}")
    print(f"  Tag size: {tag_size * 1000:.1f} mm")
    print(f"  Mode:     {mode}")
    if _GPU_AVAILABLE:
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_mem / (1024**3)
        print(f"  GPU:      {gpu_name} ({gpu_mem:.0f} GB VRAM)")
    print("=" * 60)
    print()

    # ------------------------------------------------------------------
    # Stage 1: Prepare — validate inputs
    # ------------------------------------------------------------------
    print(">>> Stage 1/5: Prepare")
    try:
        image_files = prepare.validate(input_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"[FATAL] {e}")
        sys.exit(1)
    t_prepare = time.time()
    print(f"    ({t_prepare - t_start:.1f}s)\n")

    # ------------------------------------------------------------------
    # Stage 2: Poses — SfM reconstruction
    # ------------------------------------------------------------------
    print(">>> Stage 2/5: Poses (SfM)")
    try:
        reconstruction, sfm_output_path = poses.reconstruct(
            input_dir, output_dir
        )
    except RuntimeError as e:
        print(f"[FATAL] {e}")
        sys.exit(1)
    t_poses = time.time()
    print(f"    ({t_poses - t_prepare:.1f}s)\n")

    # ------------------------------------------------------------------
    # Stage 3: AprilTags — metric scale
    # ------------------------------------------------------------------
    print(">>> Stage 3/5: AprilTag Scale")
    try:
        scale_factor, metrics = apriltags.compute_scale(
            reconstruction, input_dir, tag_size
        )
    except RuntimeError as e:
        print(f"[FATAL] {e}")
        sys.exit(1)
    t_tags = time.time()
    print(f"    ({t_tags - t_poses:.1f}s)\n")

    # ------------------------------------------------------------------
    # Stage 4: Dense — mesh reconstruction
    # ------------------------------------------------------------------
    print(">>> Stage 4/5: Dense Reconstruction")
    if _GPU_AVAILABLE:
        mesh, pcd = dense.reconstruct(
            reconstruction, scale_factor,
            input_dir=input_dir, output_dir=output_dir,
        )
    else:
        mesh, pcd = dense.reconstruct(reconstruction, scale_factor)
    t_dense = time.time()
    print(f"    ({t_dense - t_tags:.1f}s)\n")

    # ------------------------------------------------------------------
    # Stage 5: Export — multi-format output
    # ------------------------------------------------------------------
    print(">>> Stage 5/5: Export")
    export.export_all(mesh, pcd, output_dir, metrics)
    t_export = time.time()
    print(f"    ({t_export - t_dense:.1f}s)\n")

    # ------------------------------------------------------------------
    # Timing summary
    # ------------------------------------------------------------------
    t_total = t_export - t_start
    print(f"Pipeline complete in {t_total:.1f}s ({mode})")
    print(f"  Prepare:    {t_prepare - t_start:.1f}s")
    print(f"  Poses:      {t_poses - t_prepare:.1f}s")
    print(f"  AprilTags:  {t_tags - t_poses:.1f}s")
    print(f"  Dense:      {t_dense - t_tags:.1f}s")
    print(f"  Export:     {t_export - t_dense:.1f}s")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SCAN3D MOBILE — Modular CV Pipeline"
    )
    parser.add_argument(
        "input_dir",
        type=str,
        help="Path to directory containing input images",
    )
    parser.add_argument(
        "--tag-size",
        type=float,
        required=True,
        help=(
            "Physical side length of the printed AprilTag in meters "
            "(e.g. 0.167 for 16.7 cm)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (defaults to <input_dir>/output)",
    )
    args = parser.parse_args()
    run(args.input_dir, args.tag_size, args.output_dir)
