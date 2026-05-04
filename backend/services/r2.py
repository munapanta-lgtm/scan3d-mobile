"""
Cloudflare R2 Storage Service

S3-compatible object storage for scan uploads and result downloads.
Uses boto3 with R2 endpoint.
"""

import boto3
from botocore.config import Config as BotoConfig

from config import (
    R2_ENDPOINT,
    R2_ACCESS_KEY,
    R2_SECRET_KEY,
    R2_BUCKET,
    UPLOAD_URL_EXPIRY,
    DOWNLOAD_URL_EXPIRY,
)

# R2 requires signature_version=s3v4
_client = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    config=BotoConfig(signature_version="s3v4"),
    region_name="auto",
)


def generate_upload_url(scan_id: str) -> dict:
    """
    Generate a pre-signed PUT URL for the mobile app to upload a .zip.

    Returns dict with 'url' and 'key'.
    """
    key = f"inputs/{scan_id}.zip"
    url = _client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": R2_BUCKET,
            "Key": key,
            "ContentType": "application/zip",
        },
        ExpiresIn=UPLOAD_URL_EXPIRY,
    )
    return {"url": url, "key": key}


def generate_download_url(key: str) -> str:
    """Generate a pre-signed GET URL to download a result file."""
    return _client.generate_presigned_url(
        "get_object",
        Params={"Bucket": R2_BUCKET, "Key": key},
        ExpiresIn=DOWNLOAD_URL_EXPIRY,
    )


def list_result_files(scan_id: str) -> list[str]:
    """List all output files for a scan in R2."""
    prefix = f"outputs/{scan_id}/"
    response = _client.list_objects_v2(Bucket=R2_BUCKET, Prefix=prefix)
    if "Contents" not in response:
        return []
    return [obj["Key"] for obj in response["Contents"]]


def check_input_exists(scan_id: str) -> bool:
    """Check if the input .zip has been uploaded."""
    try:
        _client.head_object(Bucket=R2_BUCKET, Key=f"inputs/{scan_id}.zip")
        return True
    except _client.exceptions.ClientError:
        return False
