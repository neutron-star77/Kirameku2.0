import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72

# Ed25519 设备密钥登录（SSH 式）：私钥在站长/自动化侧，公钥进容器 env，不进任何 git
DEVICE_PUBLIC_KEY = os.environ.get("DEVICE_PUBLIC_KEY", "")
DEVICE_SIGN_WINDOW = int(os.environ.get("DEVICE_SIGN_WINDOW", "300"))  # 签名时间戳允许偏移（秒）
# 内网自动登录白名单（CIDR 列表）：来源 IP 命中即免密签发管理员 JWT（家用 NAS 内网视为可信域）
AUTO_LOGIN_CIDRS = [
    c.strip()
    for c in os.environ.get(
        "AUTO_LOGIN_CIDRS", "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    ).split(",")
    if c.strip()
]

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
