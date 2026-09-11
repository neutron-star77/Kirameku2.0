# 运维与一次性脚本

本目录收纳不属于线上服务运行路径的脚本。线上容器只从 `app/` 启动，这里的文件不会被打包进服务流程。

## 目录约定

- `ops/`：运维操作（如 `reset_admin.py` 重置管理员密码）。**仅限在 NAS 上、确认环境后手动运行**，不要对外暴露。
- `oneoff/`：一次性数据修复 / 生成 / 演示数据脚本，执行完即归档保留，供日后追溯或复用。

## 运行方式

这些脚本默认以 `Kirameku-backend/` 为工作目录、并读取同目录 `.env`：

```bash
cd Kirameku-backend
python -m scripts.ops.reset_admin        # 示例
python -m scripts.oneoff.gen_dashboard   # 示例
```

若直接 `python scripts/oneoff/xxx.py` 运行报 `app` 包导入失败，请设置：

```powershell
$env:PYTHONPATH = "."
```
