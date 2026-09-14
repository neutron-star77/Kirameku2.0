# -*- coding: utf-8 -*-
"""Ed25519 设备密钥登录（SSH 公钥私钥式）：私钥签名换 JWT。

用法:
    python device-login.py [base_url]
    # base_url 默认 https://kirameku-api.neutronstar.fun；内网可传 http://192.168.5.4:8100
    # 输出: accessToken
私钥路径: F:\\AI\\secrets\\kirameku-device-key.pem（绝不入库，公钥在 NAS backend/.env DEVICE_PUBLIC_KEY）
"""
import base64
import json
import os
import secrets
import sys
import time
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

PRIV_PATH = r"F:\AI\secrets\kirameku-device-key.pem"


def load_private_key() -> Ed25519PrivateKey:
    with open(PRIV_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def device_login(base: str) -> str:
    priv = load_private_key()
    ts = int(time.time())
    nonce = secrets.token_hex(16)
    sig = base64.b64encode(priv.sign(f"{ts}|{nonce}".encode())).decode()
    body = json.dumps({"ts": ts, "nonce": nonce}).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/api/auth/device",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Signature": sig,
            "User-Agent": "Kirameku-Device/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if data.get("code") != 0:
        raise RuntimeError(f"登录失败: {data}")
    return data["data"]["accessToken"]


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "https://kirameku-api.neutronstar.fun"
    print(device_login(base))
