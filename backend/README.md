# SCAN3D MOBILE - Backend API

## Overview
FastAPI backend that serves as the API gateway for the SCAN3D MOBILE ecosystem. It handles authentication, credit management, upload signed URLs, and coordinates jobs with the RunPod serverless CV engine.

## Tech Stack
- **Framework**: FastAPI (Python 3.11+)
- **Database / Auth**: Supabase (Postgres + Auth)
- **Storage**: Cloudflare R2
- **Queues**: Redis

## Development (Local)
Use the `docker-compose.yml` in the root of the monorepo to spin up the local backend API.

```bash
cd ..
docker-compose up backend
```
