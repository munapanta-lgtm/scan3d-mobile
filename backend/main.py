"""
SCAN3D MOBILE — FastAPI Backend

Stateless API connecting the Flutter app to the GPU pipeline via:
  App → signed URL → upload .zip to R2 → RunPod Serverless → results → App

Credits system:
  - Welcome bonus: 3 free credits for new users
  - Basic scan: 1 credit | Premium: 2 | Pro: 3
  - Auto-refund on pipeline failure

No auth for MVP — uses hardcoded user_id from client.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models.credits import SCAN_COSTS
from services import r2, runpod_client
from services import credits as credits_svc

app = FastAPI(
    title="SCAN3D Backend",
    version="0.2.0",
    description="API for SCAN3D Mobile — GPU pipeline + credits",
)

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
    tag_size: float = 0.167
    scan_type: str = "basic"  # "basic", "premium", "pro"
    user_id: str = "default_user"


class ProcessResponse(BaseModel):
    job_id: str
    status: str
    credits_deducted: int
    balance_remaining: int


class StatusResponse(BaseModel):
    scan_id: str
    job_id: str | None
    status: str
    output: dict | None = None


class ResultFile(BaseModel):
    filename: str
    download_url: str


class ResultsResponse(BaseModel):
    scan_id: str
    files: list[ResultFile]


class BalanceResponse(BaseModel):
    user_id: str
    balance: int


class TransactionResponse(BaseModel):
    id: str
    amount: int
    balance_after: int
    reason: str
    scan_id: str | None
    created_at: str


class HistoryResponse(BaseModel):
    user_id: str
    transactions: list[TransactionResponse]


class PurchaseRequest(BaseModel):
    user_id: str = "default_user"
    product_id: str  # "credits_10", "credits_50", "credits_200"
    purchase_token: str | None = None  # Google Play verification token


# Product ID → credit amount
CREDIT_PACKS = {
    "credits_10": 10,
    "credits_50": 50,
    "credits_200": 200,
}


# ---------------------------------------------------------------------------
# Scan endpoints
# ---------------------------------------------------------------------------

@app.post("/scans/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(req: UploadUrlRequest):
    """Generate a pre-signed PUT URL for uploading a .zip to R2."""
    result = r2.generate_upload_url(req.scan_id)
    return UploadUrlResponse(upload_url=result["url"], key=result["key"])


@app.post("/scans/{scan_id}/process", response_model=ProcessResponse)
async def process_scan(scan_id: str, req: ProcessRequest):
    """
    Trigger GPU pipeline processing.

    Checks credit balance, deducts cost, then launches RunPod job.
    Auto-refunds on launch failure.
    """
    # Validate scan type
    if req.scan_type not in SCAN_COSTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scan_type '{req.scan_type}'. Must be: {list(SCAN_COSTS.keys())}",
        )

    cost = SCAN_COSTS[req.scan_type]

    # Check balance
    balance = credits_svc.get_balance(req.user_id)
    if balance < cost:
        raise HTTPException(
            status_code=402,
            detail={
                "message": f"Insufficient credits. Need {cost}, have {balance}.",
                "balance": balance,
                "cost": cost,
            },
        )

    # Verify upload exists
    if not r2.check_input_exists(scan_id):
        raise HTTPException(
            status_code=404,
            detail=f"Input file inputs/{scan_id}.zip not found in R2.",
        )

    # Deduct credits
    reason = f"scan_{req.scan_type}"
    txn = credits_svc.deduct_credits(req.user_id, cost, scan_id, reason)
    if txn is None:
        raise HTTPException(status_code=402, detail="Credit deduction failed.")

    # Launch RunPod job
    try:
        job_id = runpod_client.launch_job(scan_id, req.tag_size)
    except Exception as e:
        # Auto-refund on launch failure
        credits_svc.refund_credits(req.user_id, scan_id)
        raise HTTPException(status_code=502, detail=f"RunPod launch failed (credits refunded): {e}")

    _jobs[scan_id] = {
        "job_id": job_id,
        "status": "queued",
        "output": None,
        "user_id": req.user_id,
    }

    return ProcessResponse(
        job_id=job_id,
        status="queued",
        credits_deducted=cost,
        balance_remaining=txn.balance_after,
    )


@app.get("/scans/{scan_id}/status", response_model=StatusResponse)
async def get_scan_status(scan_id: str):
    """Poll the processing status of a scan."""
    job_info = _jobs.get(scan_id)

    if job_info is None:
        if r2.check_input_exists(scan_id):
            return StatusResponse(scan_id=scan_id, job_id=None, status="pending_upload")
        raise HTTPException(status_code=404, detail="Scan not found")

    try:
        rp_status = runpod_client.get_status(job_info["job_id"])
        status_map = {
            "QUEUED": "queued",
            "IN_QUEUE": "queued",
            "IN_PROGRESS": "in_progress",
            "COMPLETED": "completed",
            "FAILED": "failed",
        }
        new_status = status_map.get(rp_status["status"], rp_status["status"])

        # Auto-refund on pipeline failure
        if new_status == "failed" and job_info["status"] != "failed":
            user_id = job_info.get("user_id", "default_user")
            credits_svc.refund_credits(user_id, scan_id)

        job_info["status"] = new_status
        job_info["output"] = rp_status.get("output")
    except Exception:
        pass

    return StatusResponse(
        scan_id=scan_id,
        job_id=job_info["job_id"],
        status=job_info["status"],
        output=job_info["output"],
    )


@app.get("/scans/{scan_id}/results", response_model=ResultsResponse)
async def get_scan_results(scan_id: str):
    """Get signed download URLs for all output files."""
    files = r2.list_result_files(scan_id)

    if not files:
        raise HTTPException(
            status_code=404,
            detail="No results found. Job may still be running.",
        )

    result_files = [
        ResultFile(filename=key.split("/")[-1], download_url=r2.generate_download_url(key))
        for key in files
    ]
    return ResultsResponse(scan_id=scan_id, files=result_files)


# ---------------------------------------------------------------------------
# Credit endpoints
# ---------------------------------------------------------------------------

@app.get("/credits/{user_id}/balance", response_model=BalanceResponse)
async def get_credit_balance(user_id: str):
    """Get current credit balance. Grants welcome bonus for new users."""
    balance = credits_svc.get_balance(user_id)
    return BalanceResponse(user_id=user_id, balance=balance)


@app.get("/credits/{user_id}/history", response_model=HistoryResponse)
async def get_credit_history(user_id: str):
    """Get credit transaction history, newest first."""
    history = credits_svc.get_history(user_id)
    transactions = [
        TransactionResponse(
            id=t.id,
            amount=t.amount,
            balance_after=t.balance_after,
            reason=t.reason,
            scan_id=t.scan_id,
            created_at=t.created_at.isoformat(),
        )
        for t in history
    ]
    return HistoryResponse(user_id=user_id, transactions=transactions)


@app.post("/credits/{user_id}/purchase", response_model=BalanceResponse)
async def purchase_credits(user_id: str, req: PurchaseRequest):
    """
    Record a credit purchase after Google Play verification.

    For MVP, accepts without verification. In production, verify
    purchase_token with Google Play Developer API.
    """
    if req.product_id not in CREDIT_PACKS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid product_id. Must be: {list(CREDIT_PACKS.keys())}",
        )

    # TODO: Verify purchase_token with Google Play Developer API
    # google_play.verify_purchase(req.purchase_token, req.product_id)

    amount = CREDIT_PACKS[req.product_id]
    txn = credits_svc.add_credits(user_id, amount, reason="purchase")

    return BalanceResponse(user_id=user_id, balance=txn.balance_after)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "scan3d-backend", "version": "0.2.0"}
