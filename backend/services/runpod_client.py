"""
RunPod Serverless Client

Launches GPU pipeline jobs and polls their status.
"""

import runpod

from config import RUNPOD_API_KEY, RUNPOD_ENDPOINT_ID

runpod.api_key = RUNPOD_API_KEY
_endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)


def launch_job(scan_id: str, tag_size: float) -> str:
    """
    Launch a GPU pipeline job on RunPod Serverless.

    Returns the job_id for status polling.
    """
    result = _endpoint.run(
        {
            "scan_id": scan_id,
            "tag_size": tag_size,
            "input_key": f"inputs/{scan_id}.zip",
            "output_prefix": f"outputs/{scan_id}/",
        }
    )
    return result.job_id


def get_status(job_id: str) -> dict:
    """
    Get the status of a RunPod job.

    Returns dict with 'status' (QUEUED, IN_PROGRESS, COMPLETED, FAILED)
    and 'output' when completed.
    """
    status = _endpoint.status(job_id)

    return {
        "status": status.status,
        "output": getattr(status, "output", None),
    }


def cancel_job(job_id: str) -> bool:
    """Cancel a running job. Returns True if successful."""
    try:
        _endpoint.cancel(job_id)
        return True
    except Exception:
        return False
