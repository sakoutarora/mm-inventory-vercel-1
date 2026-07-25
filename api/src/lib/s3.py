import boto3
from src.lib.config import S3_BILLS_BUCKET, S3_REGION

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("s3", region_name=S3_REGION)
    return _client


def generate_presigned_upload_url(key: str, content_type: str = "application/pdf", expires_in: int = 300) -> str:
    return _get_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": S3_BILLS_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )


def generate_presigned_download_url(key: str, expires_in: int = 3600) -> str:
    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BILLS_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )


def build_bill_s3_key(branch_code: str, bill_date_str: str, filename: str) -> str:
    """Build a structured S3 key like bills/GGN01/2026-07/abc123.pdf"""
    month = bill_date_str[:7] if len(bill_date_str) >= 7 else "unknown"
    return f"bills/{branch_code}/{month}/{filename}"
