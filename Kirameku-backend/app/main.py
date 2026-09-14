from contextlib import asynccontextmanager
import ipaddress
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import AUTO_LOGIN_CIDRS, CORS_ORIGINS
from app.database import init_db
from app.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Kirameku Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def restrict_admin_to_lan(request: Request, call_next):
    """后台入口（/solarsystem、/admin）仅限内网访问；/api/* 不受影响。"""
    path = request.url.path
    if path.startswith("/solarsystem") or path.startswith("/admin"):
        ip = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
        try:
            src = ipaddress.ip_address(ip)
            allowed = any(src in ipaddress.ip_network(cidr) for cidr in AUTO_LOGIN_CIDRS if cidr)
        except ValueError:
            allowed = False
        if not allowed:
            return JSONResponse({"detail": "后台仅限内网访问"}, status_code=403)
    return await call_next(request)


# 一行挂载所有 API 路由
app.include_router(api_router)

# 挂载上传文件目录
uploads_dir = Path(__file__).resolve().parent.parent / "uploads"
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# 挂载 Vue 管理后台（路径改为 /solarsystem，/admin 旧地址 301 指到新入口）
admin_dist = Path(__file__).resolve().parent.parent / "admin" / "dist"
if admin_dist.exists():
    app.mount("/solarsystem", StaticFiles(directory=str(admin_dist), html=True), name="admin")
    @app.get("/admin", include_in_schema=False)
    async def admin_redirect():
        return RedirectResponse(url="/solarsystem/", status_code=301)
    @app.get("/admin/", include_in_schema=False)
    async def admin_redirect_slash():
        return RedirectResponse(url="/solarsystem/", status_code=301)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/routes")
def get_routes():
    return {"code": 0, "message": "success", "data": []}
