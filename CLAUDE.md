# AI 阅读协议（Kirameku2.0 / Neutronstar 博客）

> 本文件只是指路牌。**接到任务先读 [`docs/README.md`](docs/README.md)**（文档索引 + 30 秒现状 + 任务路由表），然后**只读路由表指定的文档/小节**——禁止一上来通读 `docs/HANDOFF-续开发交接文档.md` 全文（700 行深层档案，按 §4 小节号按需查）。

**三条铁律（违反会出事）：**
1. 不碰 NAS 的 `kirameku-pg` 容器与 `kirameku_pgdata` / `kirameku_uploads` 数据卷；
2. 不用 `git add -A`，一律显式路径 `git add <file>`（`web/` 是独立 git 仓，外仓看不到它的改动）；
3. 密钥 / `.env` / `.cf.local.env` / `backups/` 绝不入库。

**任务路由速记：**
- 改代码前按场景读 [`docs/坑大全.md`](docs/坑大全.md) 对应分区（40+ 踩坑，现象→原因→解法）
- 部署 / 排障 / 查凭据 / 关键 ID → [`docs/命令与运维速查.md`](docs/命令与运维速查.md)
- 用户问"怎么用 / 怎么改 / 内容去哪了" → [`docs/站点功能与使用说明.md`](docs/站点功能与使用说明.md)
- 项目全貌 / 历史时间线 → [`docs/项目全景与开发史.md`](docs/项目全景与开发史.md)
- 某阶段实现细节 → HANDOFF §4 对应小节（4.1–4.11）

**验证底线：** 前端改完必须 build+preview（`astro dev` 不可用）；SSR 页面必须验证响应完整性（footer 出现次数，不能用 `</html>` 判断——Astro 产物本就不输出闭合标签）。
