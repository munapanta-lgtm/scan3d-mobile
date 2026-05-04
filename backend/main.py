"""
SCAN3D MOBILE — FastAPI Backend

Stateless API connecting the Flutter app to the GPU pipeline via:
  App → signed URL → upload .zip to R2 → RunPod Serverless → results → App

Endpoints:
  POST /scans/upload-url          → Pre-signed PUT URL for R2
  POST /scans/{scan_id}/process   → Launch RunPod GPU job
  GET  /scans/{scan_id}/status    → Poll job status
  GET  /scans/{scan_id}/results   → Download URLs for outputs

No auth for MVP (Phase 4).
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services import r2, runpod_client

app = FastAPI(
    title="SCAN3D Backend",
    version="0.1.0",
    description="API for SCAN3D Mobile → GPU pipeline orchestration",
)

# Allow Flutter app to connect from any origin (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job tracking (MVP — use Redis/DB in production)
_jobs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class UploadUrlRequest(BaseModel):
    scan_id: str


class UploadUrlResponse(BaseModel):
    upload_url: str
    key: str


class ProcessRequest(BaseModel):
    tag_size: float = 0.167  # AprilTag side length in meters


class ProcessResponse(BaseModel):
    job_id: str
    status: str


class StatusResponse(BaseModel):
    scan_id: str
    job_id: str | None
    status: str  # pending_upload, queued, in_progress, completed, failed
    output: dict | None = None


class ResultFile(BaseModel):
    filename: str
    download_url: str


class ResultsResponse(BaseModel):
    scan_id: str
    files: list[ResultFile]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/scans/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(req: UploadUrlRequest):
    """Generate a pre-signed PUT URL for the mobile app to upload a .zip to R2."""
    result = r2.generate_upload_url(req.scan_id)
    return UploadUrlResponse(upload_url=result["url"], key=result["key"])


@app.post("/scans/{scan_id}/process", response_model=ProcessResponse)
async def process_scan(scan_id: str, req: ProcessRequest):
    """
    Trigger GPU pipeline processing on RunPod Serverless.

    The input .zip must already be uploaded to R2 via the pre-signed URL.
    """
    # Verify upload exists
    if not r2.check_input_exists(scan_id):
        raise HTTPException(
            status_code=404,
            detail=f"Input file inputs/{scan_id}.zip not found in R2. "
            "Upload it first via /scans/upload-url.",
        )

    # Launch RunPod job
    try:
        job_id = runpod_client.launch_job(scan_id, req.tag_size)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RunPod launch failed: {e}")

    # Track locally
    _jobs[scan_id] = {
        "job_id": job_id,
        "status": "queued",
        "output": None,
    }

    return ProcessResponse(job_id=job_id, status="queued")


@app.get("/scans/{scan_id}/status", response_model=StatusResponse)
async def get_scan_status(scan_id: str):
    """Poll the processing status of a scan."""
    job_info = _jobs.get(scan_id)

    if job_info is None:
        # Check if input exists but job hasn't been submitted
        if r2.check_input_exists(scan_id):
            return StatusResponse(
                scan_id=scan_id, job_id=None, status="pending_upload"
            )
        raise HTTPException(status_code=404, detail="Scan not found")

    # Poll RunPod for latest status
    try:
        rp_status = runpod_client.get_status(job_info["job_id"])
        status_map = {
            "QUEUED": "queued",
            "IN_QUEUE": "queued",
            "IN_PROGRESS": "in_progress",
            "COMPLETED": "completed",
            "FAILED": "failed",
        }
        job_info["status"] = status_map.get(rp_status["status"], rp_status["status"])
        job_info["output"] = rp_status.get("output")
    except Exception:
        pass  # Return cached status on poll failure

    return StatusResponse(
        scan_id=scan_id,
        job_id=job_info["job_id"],
        status=job_info["status"],
        output=job_info["output"],
    )


@app.get("/scans/{scan_id}/results", response_model=ResultsResponse)
async def get_scan_results(scan_id: str):
    """Get signed download URLs for all output files of a completed scan."""
    files = r2.list_result_files(scan_id)

    if not files:
        raise HTTPException(
            status_code=404,
            detail="No results found. Check /status — job may still be running.",
        )

    result_files = []
    for key in files:
        filename = key.split("/")[-1]
        url = r2.generate_download_url(key)
        result_files.append(ResultFile(filename=filename, download_url=url))

    return ResultsResponse(scan_id=scan_id, files=result_files)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "scan3d-backend"}
