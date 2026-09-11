#!/usr/bin/env node
// Shirone 上游主题基线同步脚本
// 作用：把 LyraVoid/Shirone 完整仓库拉到 _upstream_shirone/（该目录已在 .gitignore，不入库）
// 用法：
//   node scripts/sync-upstream.mjs            # 对齐到下方 PINNED_COMMIT
//   node scripts/sync-upstream.mjs main       # 临时跟踪上游 main（升级评估用）
// 升级上游流程：先跑 main 看差异 → 验证无破坏 → 把新 SHA 写回本文件的 PINNED_COMMIT。
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const UPSTREAM_URL = "https://github.com/LyraVoid/Shirone.git";
// 2026-09-12 对齐基线（首页 1:1 复刻的对照源，升级时整体替换此 SHA）
const PINNED_COMMIT = "b79d301e5e6a8ec897e85b042de43187b571dd5b";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dest = join(root, "_upstream_shirone");
const ref = process.argv[2] || PINNED_COMMIT;

function run(cmd, cwd = root) {
  execSync(cmd, { cwd, stdio: "inherit", shell: true });
}

if (!existsSync(dest)) {
  run(`git clone ${UPSTREAM_URL} _upstream_shirone`);
}
run(`git fetch --depth 1 origin ${ref}`, dest);
run("git checkout --detach FETCH_HEAD", dest);
const head = execSync("git rev-parse HEAD", { cwd: dest }).toString().trim();
console.log("[sync-upstream] Shirone pinned at", head);
if (head !== PINNED_COMMIT) {
  console.warn("[sync-upstream] 注意：当前 HEAD 与 PINNED_COMMIT 不一致（跟踪模式）");
}
