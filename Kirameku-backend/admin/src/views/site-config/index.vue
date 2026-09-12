<script setup lang="ts">
import { ref, onMounted } from "vue";
import { message as msg } from "@/utils/message";
import {
  getAllSiteConfig,
  updateSiteConfig,
  createSiteConfig,
  deleteSiteConfig
} from "@/api/siteConfig";
import type { SiteConfigItem } from "@/api/siteConfig";

defineOptions({ name: "SiteConfigIndex" });

const loading = ref(false);
const dataList = ref<SiteConfigItem[]>([]);

// 编辑对话框
const dialogVisible = ref(false);
const dialogTitle = ref("编辑配置");
const formRef = ref();
const form = ref({
  key: "",
  value: "",
  description: ""
});
const isEdit = ref(false);
const defaultNavigation = JSON.stringify(
  [
    { id: "home", label: "首页", href: "/", visible: true, target: "_self" },
    { id: "posts", label: "文章", href: "/posts", visible: true, target: "_self" },
    { id: "archive", label: "归档", href: "/archive", visible: true, target: "_self" },
    { id: "moments", label: "说说", href: "/moments", visible: true, target: "_self" },
    { id: "albums", label: "相册", href: "/albums", visible: true, target: "_self" },
    { id: "friends", label: "友链", href: "/friends", visible: true, target: "_self" },
    { id: "messages", label: "杂谈", href: "/messages", visible: true, target: "_self" },
    { id: "novel", label: "小说", href: "/novel", visible: true, target: "_self" },
    { id: "about", label: "关于", href: "/about", visible: true, target: "_self" }
  ],
  null,
  2
);
const defaultSidebarWidgets = JSON.stringify(
  {
    profile: true,
    announcement: true,
    categories: true,
    tags: true,
    stats: true,
    calendar: true
  },
  null,
  2
);

const rules = {
  key: [{ required: true, message: "请输入配置键名", trigger: "blur" }],
  value: [{ required: true, message: "请输入配置值", trigger: "blur" }]
};

const columns: TableColumnList = [
  { label: "ID", prop: "id", width: 60 },
  { label: "配置键名", prop: "key", width: 220 },
  {
    label: "配置值",
    prop: "value",
    minWidth: 200,
    slot: "value"
  },
  { label: "说明", prop: "description", minWidth: 160 },
  {
    label: "更新时间",
    prop: "updated_at",
    width: 170,
    formatter: ({ updated_at }: SiteConfigItem) =>
      updated_at ? updated_at.replace("T", " ").slice(0, 19) : ""
  },
  {
    label: "操作",
    fixed: "right",
    width: 150,
    slot: "operation"
  }
];

async function onSearch() {
  loading.value = true;
  try {
    dataList.value = await getAllSiteConfig();
  } finally {
    loading.value = false;
  }
}

function openAdd() {
  isEdit.value = false;
  dialogTitle.value = "新增配置";
  form.value = { key: "", value: "", description: "" };
  dialogVisible.value = true;
}

async function initializeNavigation() {
  try {
    await updateSiteConfig("navigation", {
      value: defaultNavigation,
      description: "博客主站一级/二级导航 JSON 配置"
    });
    msg("导航配置已初始化，可继续编辑 navigation", { type: "success" });
    onSearch();
  } catch (e: any) {
    msg(e?.message ?? "初始化失败", { type: "error" });
  }
}

async function initializeSidebarWidgets() {
  try {
    await updateSiteConfig("sidebar_widgets", {
      value: defaultSidebarWidgets,
      description: "新版主题侧边栏卡片显示开关 JSON 配置"
    });
    msg("侧边栏配置已初始化，可继续编辑 sidebar_widgets", { type: "success" });
    onSearch();
  } catch (e: any) {
    msg(e?.message ?? "初始化失败", { type: "error" });
  }
}

function openEdit(row: SiteConfigItem) {
  isEdit.value = true;
  dialogTitle.value = "编辑配置";
  form.value = {
    key: row.key,
    value: typeof row.value === "string" ? row.value : JSON.stringify(row.value),
    description: row.description || ""
  };
  dialogVisible.value = true;
}

async function handleSubmit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }

  try {
    if (isEdit.value) {
      await updateSiteConfig(form.value.key, {
        value: form.value.value,
        description: form.value.description
      });
      msg("更新成功", { type: "success" });
    } else {
      await createSiteConfig({
        key: form.value.key,
        value: form.value.value,
        description: form.value.description
      });
      msg("新增成功", { type: "success" });
    }
    dialogVisible.value = false;
    onSearch();
  } catch (e: any) {
    msg(e?.message ?? "操作失败", { type: "error" });
  }
}

async function handleDelete(row: SiteConfigItem) {
  try {
    await deleteSiteConfig(row.key);
    msg("删除成功", { type: "success" });
    onSearch();
  } catch (e: any) {
    msg(e?.message ?? "删除失败", { type: "error" });
  }
}

function formatValue(val: unknown): string {
  if (typeof val === "string") return val;
  try {
    return JSON.stringify(val);
  } catch {
    return String(val);
  }
}

const sidebarLabels: Record<string, string> = {
  profile: "作者卡片",
  announcement: "公告",
  categories: "分类",
  tags: "标签",
  stats: "站点统计",
  calendar: "日历",
  music: "音乐播放器",
  toc: "文章目录"
};

function sidebarState(row: SiteConfigItem): Record<string, boolean> {
  try {
    const value = typeof row.value === "string" ? JSON.parse(row.value) : row.value;
    return { ...Object.fromEntries(Object.keys(sidebarLabels).map(key => [key, true])), ...value };
  } catch {
    return Object.fromEntries(Object.keys(sidebarLabels).map(key => [key, true]));
  }
}

async function toggleSidebar(row: SiteConfigItem, key: string, value: boolean) {
  const next = { ...sidebarState(row), [key]: value };
  try {
    await updateSiteConfig("sidebar_widgets", {
      value: JSON.stringify(next),
      description: "新版主题侧边栏卡片显示开关 JSON 配置"
    });
    msg(`${sidebarLabels[key]}卡片已${value ? "开启" : "关闭"}`, { type: "success" });
    onSearch();
  } catch (e: any) {
    msg(e?.message ?? "更新失败", { type: "error" });
  }
}

// ---------- 站点图片（site_images） ----------
const imagesDialogVisible = ref(false);
const imagesForm = ref({
  banner_desktop: "",
  banner_mobile: "",
  avatar: "",
  logo: ""
});

function imagesState(row: SiteConfigItem) {
  try {
    const value = typeof row.value === "string" ? JSON.parse(row.value) : row.value;
    return {
      banner_desktop: (value.bannerDesktop ?? []).join("\n"),
      banner_mobile: (value.bannerMobile ?? []).join("\n"),
      avatar: value.avatar ?? "",
      logo: value.logo ?? ""
    };
  } catch {
    return { banner_desktop: "", banner_mobile: "", avatar: "", logo: "" };
  }
}

function openImagesEditor(row: SiteConfigItem) {
  imagesForm.value = imagesState(row);
  imagesDialogVisible.value = true;
}

async function initializeSiteImages() {
  try {
    await updateSiteConfig("site_images", {
      value: JSON.stringify({ bannerDesktop: [], bannerMobile: [], avatar: "", logo: "" }),
      description: "固定窗口图片 URL：横幅(桌面/移动)、头像、Logo"
    });
    msg("图片配置已初始化，可继续编辑 site_images", { type: "success" });
    onSearch();
  } catch (e: any) {
    msg(e?.message ?? "初始化失败", { type: "error" });
  }
}

async function handleImagesSubmit() {
  const toList = (text: string) =>
    text.split("\n").map((s) => s.trim()).filter(Boolean);
  try {
    await updateSiteConfig("site_images", {
      value: JSON.stringify({
        bannerDesktop: toList(imagesForm.value.banner_desktop),
        bannerMobile: toList(imagesForm.value.banner_mobile),
        avatar: imagesForm.value.avatar.trim(),
        logo: imagesForm.value.logo.trim()
      }),
      description: "固定窗口图片 URL：横幅(桌面/移动)、头像、Logo"
    });
    msg("图片配置已保存，前台秒级生效", { type: "success" });
    imagesDialogVisible.value = false;
    onSearch();
  } catch (e: any) {
    msg(e?.message ?? "保存失败", { type: "error" });
  }
}

// ---------- Umami 统计（umami） ----------
const umamiDialogVisible = ref(false);
const umamiForm = ref({
  enable: false,
  websiteId: "",
  scriptUrl: "",
  shareUrl: ""
});

function umamiState(row?: SiteConfigItem) {
  const fallback = { enable: false, websiteId: "", scriptUrl: "", shareUrl: "" };
  if (!row) return fallback;
  try {
    const value = typeof row.value === "string" ? JSON.parse(row.value) : row.value;
    return { ...fallback, ...(value ?? {}) };
  } catch {
    return fallback;
  }
}

function openUmamiEditor(row: SiteConfigItem) {
  umamiForm.value = umamiState(row);
  umamiDialogVisible.value = true;
}

async function initializeUmami() {
  try {
    await updateSiteConfig("umami", {
      value: JSON.stringify({ enable: false, websiteId: "", scriptUrl: "", shareUrl: "" }),
      description: "Umami 访问统计：总开关 + Website ID + 采集脚本 + 分享链接"
    });
    msg("统计配置已初始化，可继续编辑 umami", { type: "success" });
    onSearch();
  } catch (e: any) {
    msg(e?.message ?? "初始化失败", { type: "error" });
  }
}

async function handleUmamiSubmit() {
  if (umamiForm.value.enable && !umamiForm.value.websiteId && !umamiForm.value.shareUrl) {
    msg("开启统计至少需要填写 Website ID 或分享链接", { type: "warning" });
    return;
  }
  try {
    await updateSiteConfig("umami", {
      value: JSON.stringify({
        enable: umamiForm.value.enable,
        websiteId: umamiForm.value.websiteId.trim(),
        scriptUrl: umamiForm.value.scriptUrl.trim(),
        shareUrl: umamiForm.value.shareUrl.trim()
      }),
      description: "Umami 访问统计：总开关 + Website ID + 采集脚本 + 分享链接"
    });
    msg("统计配置已保存，前台约 1 分钟内生效", { type: "success" });
    umamiDialogVisible.value = false;
    onSearch();
  } catch (e: any) {
    msg(e?.message ?? "保存失败", { type: "error" });
  }
}

onMounted(() => onSearch());
</script>

<template>
  <div class="p-4">
    <el-card shadow="never">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-medium">站点配置</span>
          <div class="flex gap-2">
            <el-button @click="initializeNavigation">初始化导航配置</el-button>
            <el-button @click="initializeSidebarWidgets">初始化侧边栏配置</el-button>
            <el-button @click="initializeSiteImages">初始化图片配置</el-button>
            <el-button @click="initializeUmami">初始化统计配置</el-button>
            <el-button type="primary" @click="openAdd">新增配置</el-button>
          </div>
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
        <template #value="{ row }">
          <div v-if="row.key === 'site_images'" class="text-left">
            <div class="text-xs text-gray-500 mb-1">
              横幅桌面 {{ imagesState(row).banner_desktop.split("\n").filter(Boolean).length }} 张 ·
              横幅移动 {{ imagesState(row).banner_mobile.split("\n").filter(Boolean).length }} 张
            </div>
            <el-button link type="primary" size="small" @click="openImagesEditor(row)">
              编辑图片链接
            </el-button>
          </div>
          <div v-else-if="row.key === 'umami'" class="text-left">
            <div class="text-xs mb-1" :class="umamiState(row).enable ? 'text-green-600' : 'text-gray-400'">
              {{ umamiState(row).enable ? "● 统计已开启" : "○ 统计未开启" }}
              <span v-if="umamiState(row).websiteId" class="text-gray-500"> · ID {{ umamiState(row).websiteId.slice(0, 8) }}…</span>
            </div>
            <el-button link type="primary" size="small" @click="openUmamiEditor(row)">
              编辑统计配置
            </el-button>
          </div>
          <div v-else-if="row.key === 'sidebar_widgets'" class="flex flex-wrap gap-3 text-left">
            <label v-for="(label, key) in sidebarLabels" :key="key" class="inline-flex items-center gap-1.5 text-xs">
              <el-switch
                :model-value="sidebarState(row)[key]"
                size="small"
                @change="(value: boolean) => toggleSidebar(row, key, value)"
              />
              {{ label }}
            </label>
          </div>
          <div v-else class="text-left max-w-xs truncate" :title="formatValue(row.value)">
            {{ formatValue(row.value) }}
          </div>
        </template>

        <template #operation="{ row }">
          <el-button link type="primary" size="small" @click="openEdit(row)">
            编辑
          </el-button>
          <el-popconfirm
            :title="`确认删除配置 ${row.key}？`"
            @confirm="handleDelete(row)"
          >
            <template #reference>
              <el-button link type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </pure-table>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="520px"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="80px"
      >
        <el-form-item label="配置键名" prop="key">
          <el-input
            v-model="form.key"
            :disabled="isEdit"
            placeholder="如 cloud_music_playlist_id"
          />
        </el-form-item>
        <el-form-item label="配置值" prop="value">
          <el-input
            v-model="form.value"
            type="textarea"
            :rows="3"
            :placeholder="form.key === 'navigation' ? '填写一级/二级菜单 JSON，支持 visible、sort、target、children' : '配置值'"
          />
          <div v-if="form.key === 'navigation'" class="mt-1 text-xs text-gray-500">
            二级菜单示例：{"children":[{"id":"child","label":"子菜单","href":"/path"}]}
          </div>
        </el-form-item>
        <el-form-item label="说明" prop="description">
          <el-input
            v-model="form.description"
            placeholder="配置项说明（可选）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 站点图片编辑对话框 -->
    <el-dialog
      v-model="imagesDialogVisible"
      title="编辑固定窗口图片链接"
      width="560px"
      destroy-on-close
    >
      <el-form label-width="110px">
        <el-form-item label="横幅图(桌面)">
          <el-input
            v-model="imagesForm.banner_desktop"
            type="textarea"
            :rows="3"
            placeholder="每行一个图片 URL，第一张为默认横幅"
          />
        </el-form-item>
        <el-form-item label="横幅图(移动)">
          <el-input
            v-model="imagesForm.banner_mobile"
            type="textarea"
            :rows="2"
            placeholder="每行一个图片 URL（移动端竖版）"
          />
        </el-form-item>
        <el-form-item label="头像 URL">
          <el-input v-model="imagesForm.avatar" placeholder="侧边栏作者卡片头像" />
        </el-form-item>
        <el-form-item label="Logo URL">
          <el-input v-model="imagesForm.logo" placeholder="顶栏 Logo（可选，暂未启用）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="imagesDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleImagesSubmit">保存</el-button>
      </template>
    </el-dialog>

    <!-- Umami 统计配置对话框 -->
    <el-dialog
      v-model="umamiDialogVisible"
      title="编辑 Umami 访问统计"
      width="560px"
      destroy-on-close
    >
      <el-form label-width="110px">
        <el-form-item label="启用统计">
          <el-switch v-model="umamiForm.enable" />
          <span class="ml-2 text-xs text-gray-500">关闭后前台不加载任何统计脚本</span>
        </el-form-item>
        <el-form-item v-if="umamiForm.shareUrl" label="查看数据">
          <el-link type="primary" :href="umamiForm.shareUrl" target="_blank" rel="noopener">
            打开 Umami 统计面板（只读）
          </el-link>
        </el-form-item>
        <el-form-item label="Website ID">
          <el-input v-model="umamiForm.websiteId" placeholder="Umami 站点 ID（采集用）" />
        </el-form-item>
        <el-form-item label="采集脚本 URL">
          <el-input v-model="umamiForm.scriptUrl" placeholder="如 https://your-umami/script.js" />
        </el-form-item>
        <el-form-item label="分享链接">
          <el-input v-model="umamiForm.shareUrl" placeholder="Umami 只读分享页 URL（前台统计卡片用）" />
        </el-form-item>
        <div class="text-xs text-gray-400 pl-[110px]">
          Website ID + 采集脚本同时填写才会注入访问采集；分享链接用于前台展示访问量。
        </div>
      </el-form>
      <template #footer>
        <el-button @click="umamiDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleUmamiSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
