# SCAN3D MOBILE - Infrastructure

## Overview
Infrastructure as Code (IaC) configuration for the SCAN3D MOBILE platform.

## Resources
- **Supabase**: Managed Postgres and Authentication.
- **Cloudflare R2**: S3-compatible blob storage for raw uploads and processed 3D models.
- **RunPod Serverless**: GPU worker instances for the CV Engine pipeline.
- **Redis**: Rate limiting and queue management.
