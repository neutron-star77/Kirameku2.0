<script setup lang="ts">
/**
 * 评论管理（P5 起评论是多态的，这里统一管两套评论表）
 *
 *  - 内容评论：`comment` 表，target_type = post / album
 *  - 说说评论：`chatter_comment` 表（后端独立的说说评论接口）
 *
 * 两套数据结构几乎一致，所以共用一个表格，只按当前 Tab 切换「取数/改状态/删除」的接口。
 * 列表项都带 `target`（所属内容标题 + 前台链接），方便运营直接点回前台核对。
 */
import { ref, onMounted, computed } from "vue";
import { message } from "@/utils/message";
import {
  getAdminComments,
  updateCommentStatus,
  deleteComment
} from "@/api/comment";
import type { CommentItem } from "@/api/comment";
import {
  getAdminChatterComments,
  updateChatterCommentStatus,
  deleteChatterComment
} from "@/api/chatter";

defineOptions({ name: "CommentIndex" });

const FRONTEND_ORIGIN = "https://neutronstar.fun";

const loading = ref(false);
const dataList = ref<CommentItem[]>([]);
const statusFilter = ref("");
/** post / album / ""（全部）—— 仅「内容评论」Tab 生效 */
const targetFilter = ref("");
const expandedRows = ref<number[]>([]);
/** content = 文章+相册评论；chatter = 说说评论 */
const activeTab = ref<"content" | "chatter">("content");

const TARGET_LABEL: Record<string, string> = {
  post: "文章",
  chatter: "说说",
  album: "相册"
};

const columns = computed<TableColumnList>(() => [
  { label: "ID", prop: "id", width: 60 },
  { label: "用户", prop: "github_user", width: 130, slot: "user" },
  { label: "内容", prop: "content", minWidth: 220 },
  { label: "所属内容", prop: "target", minWidth: 200, slot: "target" },
  { label: "IP", prop: "ip", width: 130 },
  { label: "回复", prop: "replies", width: 70, slot: "replies" },
  { label: "状态", prop: "status", width: 90, slot: "status" },
  {
    label: "时间",
    prop: "created_at",
    minWidth: 160,
    formatter: ({ created_at }) =>
      created_at ? created_at.replace("T", " ").slice(0, 19) : ""
  },
  { label: "操作", fixed: "right", width: 200, slot: "operation" }
]);

async function onSearch() {
  loading.value = true;
  try {
    const params: any = { size: 100 };
    if (statusFilter.value) params.status = statusFilter.value;

    dataList.value =
      activeTab.value === "content"
        ? await getAdminComments({
            ...params,
            target_type: targetFilter.value || undefined
          })
        : await getAdminChatterComments(params);
    expandedRows.value = [];
  } catch (e: any) {
    message(e?.message ?? "加载失败", { type: "error" });
  } finally {
    loading.value = false;
  }
}

function switchTab() {
  targetFilter.value = "";
  onSearch();
}

async function handleStatus(row: CommentItem, status: string) {
  try {
    if (activeTab.value === "content") {
      await updateCommentStatus(row.id, status);
    } else {
      await updateChatterCommentStatus(row.id, status);
    }
    message("操作成功", { type: "success" });
    onSearch();
  } catch (e: any) {
    message(e?.message ?? "操作失败", { type: "error" });
  }
}

async function handleDelete(row: CommentItem) {
  try {
    if (activeTab.value === "content") {
      await deleteComment(row.id);
    } else {
      await deleteChatterComment(row.id);
    }
    message("删除成功", { type: "success" });
    onSearch();
  } catch (e: any) {
    message(e?.message ?? "删除失败", { type: "error" });
  }
}

function toggleExpand(row: CommentItem) {
  const idx = expandedRows.value.indexOf(row.id);
  if (idx >= 0) {
    expandedRows.value.splice(idx, 1);
  } else {
    expandedRows.value.push(row.id);
  }
}

/** 递归统计所有嵌套回复数 */
function countAllReplies(c: CommentItem): number {
  if (!c.replies || c.replies.length === 0) return 0;
  return c.replies.reduce((sum, r) => sum + 1 + countAllReplies(r), 0);
}

/** 递归展开所有嵌套回复为扁平列表 */
function flattenReplies(
  replies: CommentItem[],
  depth = 0
): Array<CommentItem & { _depth: number }> {
  const result: Array<CommentItem & { _depth: number }> = [];
  for (const r of replies) {
    result.push({ ...r, _depth: depth });
    if (r.replies && r.replies.length > 0) {
      result.push(...flattenReplies(r.replies, depth + 1));
    }
  }
  return result;
}

function targetUrl(row: CommentItem): string | null {
  return row.target?.url ? FRONTEND_ORIGIN + row.target.url : null;
}

onMounted(() => onSearch());
</script>

<template>
  <div class="p-4">
    <el-card shadow="never">
      <template #header>
        <div class="flex justify-between items-center flex-wrap gap-3">
          <div class="flex items-center gap-3">
            <el-radio-group v-model="activeTab" @change="switchTab">
              <el-radio-button label="content">内容评论（文章/相册）</el-radio-button>
              <el-radio-button label="chatter">说说评论</el-radio-button>
            </el-radio-group>

            <el-select
              v-if="activeTab === 'content'"
              v-model="targetFilter"
              placeholder="全部内容类型"
              clearable
              class="w-36"
              @change="onSearch"
            >
              <el-option label="文章" value="post" />
              <el-option label="相册" value="album" />
            </el-select>

            <el-select
              v-model="statusFilter"
              placeholder="全部状态"
              clearable
              class="w-28"
              @change="onSearch"
            >
              <el-option label="待审核" value="pending" />
              <el-option label="已通过" value="approved" />
              <el-option label="已拒绝" value="rejected" />
            </el-select>
          </div>
          <el-button @click="onSearch">刷新</el-button>
        </div>
      </template>

      <pure-table
        :data="dataList"
        :columns="columns"
        :loading="loading"
        align-whole="center"
        row-key="id"
        table-layout="auto"
      >
        <template #user="{ row }">
          <div class="flex items-center gap-2">
            <el-avatar v-if="row.github_user" :src="row.github_user.avatar" :size="24" />
            <el-avatar v-else :size="24" class="bg-slate-300">?</el-avatar>
            <span>{{ row.github_user?.login ?? "匿名" }}</span>
          </div>
        </template>

        <template #target="{ row }">
          <div class="flex flex-col items-center gap-1">
            <el-tag size="small" type="info">
              {{ TARGET_LABEL[row.target?.type ?? row.target_type] ?? row.target_type }}
            </el-tag>
            <a
              v-if="targetUrl(row)"
              :href="targetUrl(row)!"
              target="_blank"
              rel="noreferrer"
              class="text-xs text-blue-500 hover:underline line-clamp-1 max-w-48"
              :title="row.target?.title ?? ''"
            >
              {{ row.target?.title || `#${row.target?.id ?? row.target_id}` }}
            </a>
            <span v-else class="text-xs text-gray-400">
              {{ row.target?.title || `#${row.target_id}` }}
            </span>
          </div>
        </template>

        <template #replies="{ row }">
          <el-button
            v-if="row.replies && row.replies.length > 0"
            link
            type="primary"
            size="small"
            @click="toggleExpand(row)"
          >
            {{ expandedRows.includes(row.id) ? "收起" : countAllReplies(row) + "条" }}
          </el-button>
          <span v-else class="text-gray-400">-</span>
        </template>

        <template #status="{ row }">
          <el-tag
            :type="
              row.status === 'approved'
                ? 'success'
                : row.status === 'pending'
                  ? 'warning'
                  : 'danger'
            "
            size="small"
          >
            {{
              row.status === "approved"
                ? "已通过"
                : row.status === "pending"
                  ? "待审核"
                  : "已拒绝"
            }}
          </el-tag>
        </template>

        <template #operation="{ row }">
          <el-button
            v-if="row.status !== 'approved'"
            link
            type="success"
            size="small"
            @click="handleStatus(row, 'approved')"
          >
            通过
          </el-button>
          <el-button
            v-if="row.status !== 'rejected'"
            link
            type="warning"
            size="small"
            @click="handleStatus(row, 'rejected')"
          >
            拒绝
          </el-button>
          <el-popconfirm
            title="确认删除这条评论？子回复将一并删除。"
            @confirm="handleDelete(row)"
          >
            <template #reference>
              <el-button link type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </pure-table>

      <!-- 展开的回复列表 -->
      <template v-for="row in dataList" :key="'expand-' + row.id">
        <div
          v-if="
            expandedRows.includes(row.id) &&
            row.replies &&
            row.replies.length > 0
          "
          class="mt-2 mb-4 ml-10 border-l-2 border-gray-200 dark:border-gray-700 pl-4"
        >
          <div class="text-sm text-gray-500 mb-2">
            回复（{{ countAllReplies(row) }}）
          </div>
          <div
            v-for="reply in flattenReplies(row.replies)"
            :key="reply.id"
            class="flex items-start gap-3 py-2 border-b border-gray-100 dark:border-gray-800 last:border-0"
            :style="{ marginLeft: reply._depth * 32 + 'px' }"
          >
            <el-avatar v-if="reply.github_user" :src="reply.github_user.avatar" :size="24" />
            <el-avatar v-else :size="24" class="bg-slate-300">?</el-avatar>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-sm font-medium">
                  {{ reply.github_user?.login ?? "匿名" }}
                </span>
                <el-tag
                  :type="
                    reply.status === 'approved'
                      ? 'success'
                      : reply.status === 'pending'
                        ? 'warning'
                        : 'danger'
                  "
                  size="small"
                >
                  {{
                    reply.status === "approved"
                      ? "已通过"
                      : reply.status === "pending"
                        ? "待审核"
                        : "已拒绝"
                  }}
                </el-tag>
                <span class="text-xs text-gray-400">
                  {{
                    reply.created_at
                      ? reply.created_at.replace("T", " ").slice(0, 19)
                      : ""
                  }}
                </span>
              </div>
              <div class="text-sm">{{ reply.content }}</div>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <el-button
                v-if="reply.status !== 'approved'"
                link
                type="success"
                size="small"
                @click="handleStatus(reply, 'approved')"
              >
                通过
              </el-button>
              <el-button
                v-if="reply.status !== 'rejected'"
                link
                type="warning"
                size="small"
                @click="handleStatus(reply, 'rejected')"
              >
                拒绝
              </el-button>
              <el-popconfirm title="确认删除这条回复？" @confirm="handleDelete(reply)">
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
        </div>
      </template>
    </el-card>
  </div>
</template>
