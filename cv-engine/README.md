# SCAN3D MOBILE - CV Engine

## Overview
The Computer Vision Engine for the 3D reconstruction pipeline. It processes image sequences and ARCore telemetry to generate metric-scaled 3D models.

## Pipeline Stages
1. **Prepare**: Validate inputs and sort by ARCore timestamp.
2. **Poses**: Feature detection and matching (DISK + LightGlue), Incremental SfM (COLMAP).
3. **Dense**: Dense reconstruction (AliceVision for GPU production, pycolmap/OpenMVS for CPU).
4. **Scale**: Metric scale alignment using AprilTags (`pupil_apriltags`).
5. **Refinement (Premium)**: NeuS-facto neural refinement.
6. **Primitives (Pro)**: RANSAC primitive detection.
7. **Splat (Premium)**: 3D Gaussian Splatting for photorealistic visualization.
8. **Export**: Export to .glb, .ply, .e57, .ifc using Trimesh and Open3D.

## Local Development (CPU)
For local development, we use a CLI job runner approach.

```bash
# From the root of the monorepo:
docker-compose build cv-engine
docker-compose run cv-engine python hello_world_pipeline.py /data/samples/my_test_dataset
```
