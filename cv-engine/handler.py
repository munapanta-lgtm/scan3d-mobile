"""
SCAN3D MOBILE — RunPod Serverless Handler

Entry point for GPU pipeline execution on RunPod.
Reuses the same stages/ modules as pipeline.py.

Flow:
  1. Download .zip from R2
  2. Extract images
  3. Run GPU pipeline (DISK+LightGlue → AliceVision)
  4. Upload results to R2
  5. Return file list + metrics
"""

import os
import shutil
import time
import zipfile
from pathlib import Path

import boto3
import runpod
from botocore.config import Config as BotoConfig

# --- Early dependency validation ---
# Catch numpy/torch compatibility issues before entering the handler loop.
# RunPod base image has PyTorch 2.2 which requires numpy<2.
import sys
print(f"[boot] Python {sys.version}")
try:
    import numpy as np
    print(f"[boot] numpy {np.__version__}")
except Exception as e:
    print(f"[boot] FATAL: numpy import failed: {e}")
    sys.exit(1)
try:
    import torch
    print(f"[boot] torch {torch.__version__}, CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"[boot] GPU: {torch.cuda.get_device_name(0)}")
except Exception as e:
    print(f"[boot] FATAL: torch import failed: {e}")
    sys.exit(1)
try:
    import cv2
    print(f"[boot] opencv {cv2.__version__}")
except Exception as e:
    print(f"[boot] WARN: opencv import failed: {e}")
try:
    import pycolmap
    print(f"[boot] pycolmap OK")
except Exception as e:
    print(f"[boot] WARN: pycolmap import failed: {e}")
print("[boot] All core dependencies loaded successfully")


def _get_s3_client():
    """Create S3 client for Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=f'https://{os.environ["R2_ACCOUNT_ID"]}.r2.cloudflarestorage.com',
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


def _find_image_dir(extract_dir: Path) -> Path:
    """
    Find the actual image directory inside the extracted zip.

    Handles both flat layout and scan_<uuid>/frames/ structure
    from the mobile app's ZipService.
    """
    # Check for frames/ directly
    frames = extract_dir / "frames"
    if frames.exists():
        return frames

    # Check one level deep (scan_<uuid>/frames/)
    for child in extract_dir.iterdir():
        if child.is_dir():
            sub_frames = child / "frames"
            if sub_frames.exists():
                return sub_frames

    # Fallback: use the extract dir itself
    return extract_dir


def handler(event):
    """RunPod serverless handler."""
    inp = event["input"]
    scan_id = inp["scan_id"]
    tag_size = float(inp["tag_size"])
    bucket = inp.get("bucket", os.environ.get("R2_BUCKET", "scan3d-uploads"))
    input_key = inp["input_key"]
    output_prefix = inp["output_prefix"]

    work_dir = Path(f"/tmp/{scan_id}")
    work_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    print(f"[handler] Processing scan {scan_id}")
    print(f"[handler]   tag_size: {tag_size}m, input: {input_key}")

    try:
        s3 = _get_s3_client()

        # ---- Download .zip from R2 -----------------------------------------
        zip_path = work_dir / "input.zip"
        print(f"[handler] Downloading {input_key}...")
        s3.download_file(bucket, input_key, str(zip_path))
        t_download = time.time()
        zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"[handler]   Downloaded {zip_size_mb:.1f} MB in {t_download - t_start:.1f}s")

        # ---- Extract -------------------------------------------------------
        extract_dir = work_dir / "extracted"
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
        zip_path.unlink()  # free disk space

        image_dir = _find_image_dir(extract_dir)
        print(f"[handler] Image dir: {image_dir}")

        # ---- Import pipeline stages (GPU-aware) ----------------------------
        import torch
        from stages import apriltags, export, prepare

        if torch.cuda.is_available():
            from stages import dense_gpu as dense
            from stages import poses_gpu as poses

            gpu_name = torch.cuda.get_device_name(0)
            print(f"[handler] GPU mode: {gpu_name}")
        else:
            from stages import dense, poses

            print("[handler] CPU mode (no GPU detected)")

        # ---- Stage 1: Prepare ----------------------------------------------
        print("[handler] Stage 1/5: Prepare")
        prepare.validate(str(image_dir))

        # ---- Stage 2: Poses ------------------------------------------------
        print("[handler] Stage 2/5: Poses")
        output_dir = work_dir / "output"
        reconstruction, sfm_path = poses.reconstruct(
            str(image_dir), str(output_dir)
        )
        t_poses = time.time()

        # ---- Stage 3: AprilTags --------------------------------------------
        print("[handler] Stage 3/5: AprilTags")
        scale_factor, metrics = apriltags.compute_scale(
            reconstruction, str(image_dir), tag_size
        )
        t_tags = time.time()

        # ---- Stage 4: Dense ------------------------------------------------
        print("[handler] Stage 4/5: Dense")
        if torch.cuda.is_available():
            mesh, pcd = dense.reconstruct(
                reconstruction, scale_factor,
                input_dir=str(image_dir), output_dir=str(output_dir),
            )
        else:
            mesh, pcd = dense.reconstruct(reconstruction, scale_factor)
        t_dense = time.time()

        # ---- Stage 5: Export -----------------------------------------------
        print("[handler] Stage 5/5: Export")
        export.export_all(mesh, pcd, str(output_dir), metrics)
        t_export = time.time()

        # ---- Upload results to R2 ------------------------------------------
        print("[handler] Uploading results to R2...")
        result_files = []
        output_exts = {".ply", ".glb", ".obj", ".e57"}

        for f in output_dir.iterdir():
            if f.is_file() and f.suffix.lower() in output_exts:
                key = f"{output_prefix}{f.name}"
                s3.upload_file(str(f), bucket, key)
                result_files.append(key)
                print(f"[handler]   Uploaded {f.name}")

        t_upload = time.time()
        t_total = t_upload - t_start

        print(f"[handler] Pipeline complete in {t_total:.1f}s")
        print(f"[handler]   Download: {t_download - t_start:.1f}s")
        print(f"[handler]   Poses:    {t_poses - t_download:.1f}s")
        print(f"[handler]   Tags:     {t_tags - t_poses:.1f}s")
        print(f"[handler]   Dense:    {t_dense - t_tags:.1f}s")
        print(f"[handler]   Export:   {t_export - t_dense:.1f}s")
        print(f"[handler]   Upload:   {t_upload - t_export:.1f}s")

        return {
            "status": "ok",
            "scan_id": scan_id,
            "files": result_files,
            "metrics": metrics,
            "timing_s": round(t_total, 1),
        }

    except Exception as e:
        print(f"[handler] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "scan_id": scan_id,
            "message": str(e),
        }

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


runpod.serverless.start({"handler": handler})
