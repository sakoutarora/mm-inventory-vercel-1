import os

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://admin:mexicanmama@localhost:27017/")
MONGODB_DB = os.getenv("MONGODB_DB", "inventory")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_EXPIRES_IN_HOURS = int(os.getenv("JWT_EXPIRES_IN_HOURS", "12"))
