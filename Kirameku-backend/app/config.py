import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:4321,"
    "https://neutronstar.fun,https://www.neutronstar.fun,https://boke.hiromu.top",
).split(",")

# GitHub OAuth
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

# 阿里云 OSS 配置（可选：留空则图片存 NAS 本地 uploads/ 目录）
OSS_ACCESS_KEY_ID = os.environ.get("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.environ.get("OSS_ACCESS_KEY_SECRET", "")
OSS_BUCKET_NAME = os.environ.get("OSS_BUCKET_NAME", "")
OSS_ENDPOINT = os.environ.get("OSS_ENDPOINT", "")
OSS_CUSTOM_DOMAIN = os.environ.get("OSS_CUSTOM_DOMAIN", "")
OSS_PREFIX = os.environ.get("OSS_PREFIX", "Boke/")
OSS_ENABLED = bool(OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET and OSS_BUCKET_NAME)
