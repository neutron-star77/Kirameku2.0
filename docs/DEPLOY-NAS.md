# 后端部署到 NAS（T1）

> 更新：2026-09-09 · NAS = hewll（192.168.5.4）
> 对外域名：**https://kirameku-api.neutronstar.fun**（CF 隧道 → NAS:8100）

## 现状

| 容器 | 镜像 | 端口 | 说明 |
|:--|:--|:--|:--|
| `kirameku-backend` | `kirameku-backend:latest` | `8100 → 8000` | FastAPI（含 `/admin` 静态后台、`/uploads`） |
| `kirameku-pg` | `postgres:16` | `15432 → 5432` | PostgreSQL，库名 `kirameku` |

- 数据卷：`kirameku_uploads`（→ `/app/uploads`）、`kirameku_pgdata`（→ `/var/lib/postgresql/data`）
- 源码（构建用）：`/share/CACHEDEV1_DATA/Container/kirameku/backend`（SMB `U:\kirameku\backend`）
- 回滚镜像：`kirameku-backend:bak-20260909`（T0 加固前的镜像）

## 一键重建（改完代码后）

```powershell
# 1) 推源码到 NAS（SMB 优先，禁止 ssh 写文件）
robocopy "f:\AI\projects\Kirameku2.0\Kirameku-backend" "U:\kirameku\backend" /MIR `
  /XD .venv __pycache__ .pytest_cache uploads .git "admin\node_modules" /XF *.db .env *.log

# 2) 在 NAS 上构建镜像
ssh hewll 'export DOCKER_HOST=unix:///var/run/docker.sock; cd /share/CACHEDEV1_DATA/Container/kirameku/backend && /share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker build -t kirameku-backend:latest .'

# 3) 替换容器（env/volume/端口必须一致）
ssh hewll 'export DOCKER_HOST=unix:///var/run/docker.sock; D=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker; $D stop kirameku-backend; $D rm kirameku-backend; $D run -d --name kirameku-backend --restart unless-stopped -p 8100:8000 -e DATABASE_URL=<...> -e SECRET_KEY=<...> -e CORS_ORIGINS=<...> -v kirameku_uploads:/app/uploads -v /share/CACHEDEV1_DATA/Container/kirameku/backend/admin/dist:/app/admin/dist:ro kirameku-backend:latest'
```

## 数据库迁移（Alembic）

库最初由 `SQLModel.metadata.create_all` 建立，已在生产库上打过基线：

```bash
docker exec kirameku-backend alembic stamp head   # 仅首次
docker exec kirameku-backend alembic current      # 查看版本
```

后续改模型：

```bash
docker exec kirameku-backend alembic revision --autogenerate -m "描述"
docker exec kirameku-backend alembic upgrade head
```

## 管理后台

```powershell
cd f:\AI\projects\Kirameku2.0\Kirameku-backend\admin
pnpm install
$env:NODE_OPTIONS="--max-old-space-size=8192"
npx vite build            # 产物 admin/dist
```

产物经 SMB 同步到 `U:\kirameku\backend\admin\dist`，由容器挂载到 `/app/admin/dist`，访问 `/admin`。

> 坑：pnpm 11 不再读 `package.json` 的 `pnpm.onlyBuiltDependencies`，改在 `pnpm-workspace.yaml` 写 `allowBuilds: {esbuild: true, ...}`，否则 esbuild 二进制不安装、vite 构建失败。
> 坑：Windows 下 `NODE_OPTIONS=... vite build` 是 bash 语法，PowerShell 需先 `$env:NODE_OPTIONS=...`。

## 验证清单

```powershell
curl.exe -s https://kirameku-api.neutronstar.fun/api/health                 # {"status":"ok"}
curl.exe -s -X POST https://kirameku-api.neutronstar.fun/api/auth/login `
  -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}'
# 无 token 调写接口 → 403/401
curl.exe -s -o NUL -w "%{http_code}" -X DELETE https://kirameku-api.neutronstar.fun/api/visitors/1
```

## 回滚

```bash
docker stop kirameku-backend && docker rm kirameku-backend
docker run -d --name kirameku-backend ... kirameku-backend:bak-20260909
```
