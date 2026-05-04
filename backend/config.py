"""
SCAN3D MOBILE — Backend Configuration

All secrets from environment variables. NEVER hardcode credentials.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Cloudflare R2 -----------------------------------------------------------
R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY = os.environ["R2_ACCESS_KEY"]
R2_SECRET_KEY = os.environ["R2_SECRET_KEY"]
R2_BUCKET = os.environ.get("R2_BUCKET", "scan3d-uploads")
R2_ENDPOINT = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# --- RunPod Serverless --------------------------------------------------------
RUNPOD_API_KEY = os.environ["RUNPOD_API_KEY"]
RUNPOD_ENDPOINT_ID = os.environ["RUNPOD_ENDPOINT_ID"]

# --- App ----------------------------------------------------------------------
UPLOAD_URL_EXPIRY = int(os.environ.get("UPLOAD_URL_EXPIRY", "3600"))
DOWNLOAD_URL_EXPIRY = int(os.environ.get("DOWNLOAD_URL_EXPIRY", "3600"))
