# SCAN3D MOBILE

A cross-platform mobile application that converts any modern smartphone into a metric 3D scanner.

## Vision
Democratize metric 3D scanning. Allow anyone with a conventional Android or iOS device to generate professional-quality digital twins without requiring specialized hardware like LiDAR.

## Monorepo Structure
- `app/`: Flutter mobile application and native modules.
- `backend/`: FastAPI API Gateway and webhooks.
- `cv-engine/`: 3D reconstruction and Computer Vision pipeline.
- `docs/`: Architecture and decision documentation.
- `infra/`: IaC configurations.
- `samples/`: Test datasets and capture guidelines.

## Quickstart (Local Development)

### Prerequisites
- Docker and Docker Compose

### Running the Environment
The local environment uses CPU-based containers for ease of development.

```bash
docker-compose build
docker-compose up backend
```

To run a test photogrammetry job through the CV engine CLI:
```bash
docker-compose run cv-engine python hello_world_pipeline.py /data/samples/my_test_dataset
```
