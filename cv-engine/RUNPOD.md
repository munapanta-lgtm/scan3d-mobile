# SCAN3D MOBILE — RunPod GPU Deployment

## Overview

Deploy the CV pipeline on a RunPod GPU pod for ~40x faster processing:

| Stage | CPU (i5 8GB) | GPU (RTX 4090) |
|---|---|---|
| Feature extraction | ~90 min | ~2 min |
| Matching | ~30 min | ~1 min |
| SfM | ~5 min | ~1 min |
| Dense reconstruction | N/A (sparse only) | ~2 min |
| **Total** | **~2 hours** | **~5 min** |

## Build Docker Image

```bash
cd cv-engine

# Build GPU image
docker build -f Dockerfile.gpu -t scan3d-engine:gpu .

# Test locally (requires nvidia-docker)
docker run --gpus all scan3d-engine:gpu --help
```

## Push to Docker Hub

```bash
docker tag scan3d-engine:gpu <your-dockerhub>/scan3d-engine:gpu
docker push <your-dockerhub>/scan3d-engine:gpu
```

## Create RunPod GPU Pod

1. Go to [runpod.io](https://runpod.io) → **Pods** → **+ GPU Pod**
2. Select GPU: **RTX 4090 (24GB VRAM)** — best price/performance
   - Alternative: RTX 3090 (24GB) for budget, A100 (80GB) for large scenes
3. Container image: `<your-dockerhub>/scan3d-engine:gpu`
4. Volume: Mount a persistent volume at `/data` (50GB minimum)
5. Expose port: **22** (SSH)
6. Click **Deploy**

## Upload Test Dataset & Run

```bash
# SSH into the pod
ssh root@<pod-ip> -p <port> -i ~/.ssh/id_rsa

# Upload dataset (from local machine)
scp -P <port> -r /path/to/my_photos root@<pod-ip>:/data/my_test/

# Run pipeline
python pipeline.py /data/my_test --tag-size 0.167

# Download results
scp -P <port> -r root@<pod-ip>:/data/my_test/output/ ./results/
```

## Expected Output

```
============================================================
  SCAN3D MOBILE — CV Pipeline
============================================================
  Input:    /data/my_test
  Output:   /data/my_test/output
  Tag size: 167.0 mm
  Mode:     GPU (DISK+LightGlue)
  GPU:      NVIDIA GeForce RTX 4090 (24 GB VRAM)
============================================================

>>> Stage 1/5: Prepare
[prepare] Found 143 valid images
    (0.2s)

>>> Stage 2/5: Poses (SfM)
[poses_gpu] Device: cuda
[poses_gpu] 143 images
[poses_gpu] Extracting DISK features...
[poses_gpu] Matching with LightGlue (window=10)...
[poses_gpu] Matched 1330 pairs, 1287 with ≥15 matches
[poses_gpu] Incremental SfM reconstruction...
[poses_gpu] Reconstruction complete. Cameras: 1, Images: 143, Points: 48291
    (180.3s)

>>> Stage 3/5: AprilTag Scale
[apriltags] Detected tag 0 in 44/143 views
    (3.2s)

>>> Stage 4/5: Dense Reconstruction
[dense_gpu] Using AliceVision dense reconstruction
[dense_gpu] AliceVision: Depth map estimation (GPU)...
[dense_gpu] AliceVision: Depth map filtering...
[dense_gpu] AliceVision: Dense meshing...
[dense_gpu] AliceVision: Texturing...
[dense_gpu] AliceVision complete: 2,847,312 vertices, 5,694,624 faces
    (120.5s)

>>> Stage 5/5: Export
[export] PLY point cloud: /data/my_test/output/sparse_scaled.ply
[export] GLB mesh: /data/my_test/output/mesh.glb
[export] OBJ mesh: /data/my_test/output/mesh.obj
[export] E57 point cloud: /data/my_test/output/model.e57

Pipeline complete in 305.2s (GPU (DISK+LightGlue))
```

## GPU Selection Guide

| GPU | VRAM | Price/hr | Best for |
|---|---|---|---|
| RTX 3090 | 24GB | ~$0.30 | Budget, small scenes (<200 images) |
| RTX 4090 | 24GB | ~$0.50 | **Recommended** — best value |
| A100 40GB | 40GB | ~$1.20 | Large scenes (500+ images) |
| A100 80GB | 80GB | ~$1.80 | Very large scenes, batch processing |

## License Compliance

All GPU dependencies use commercial-friendly licenses:

| Library | License | Purpose |
|---|---|---|
| DISK | BSD-3 | Feature extraction |
| LightGlue | Apache 2.0 | Feature matching |
| AliceVision | MPL 2.0 | Dense reconstruction |
| pycolmap | BSD-3 | SfM framework |
| PyTorch | BSD-3 | GPU compute |
| kornia | Apache 2.0 | CV utilities |
| trimesh | MIT | Mesh I/O |

> ⚠️ **NEVER use SuperPoint** — it has a non-commercial license (Magic Leap).

## Troubleshooting

### CUDA out of memory
- Reduce `max_num_keypoints` in `poses_gpu.py` (4096 → 2048)
- Use `--downscale 4` in AliceVision depth map estimation
- Use a GPU with more VRAM

### AliceVision not found
- The Dockerfile tries to download pre-built binaries
- If download fails, pipeline falls back to pycolmap PatchMatch stereo
- To fix: manually install AliceVision in the Docker image

### pycolmap.verify_matches fails
- Ensure COLMAP was built with CUDA support
- Check `pycolmap` version: `pip show pycolmap`
