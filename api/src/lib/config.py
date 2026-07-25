import os

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://admin:mexicanmama@13.234.226.253:27017/")
MONGODB_DB = os.getenv("MONGODB_DB", "inventory")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_EXPIRES_IN_HOURS = int(os.getenv("JWT_EXPIRES_IN_HOURS", "12"))
S3_BILLS_BUCKET = os.getenv("S3_BILLS_BUCKET", "inventory-bills")
S3_REGION = os.getenv("S3_REGION", "ap-south-1")
