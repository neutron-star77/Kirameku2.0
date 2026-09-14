<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import { message } from "@/utils/message";
import {
  getPostById,
  createPost,
  updatePost
} from "@/api/post";
import { uploadImage } from "@/api/album";
import { getCategories } from "@/api/category";
import { getTags } from "@/api/tag";
import { getFonts } from "@/api/font";
import type { CategoryItem } from "@/api/category";
import type { TagItem } from "@/api/tag";
import type { FontItem } from "@/api/font";
import Vditor from "@/views/markdown/components/Vditor.vue";

defineOptions({ name: "PostEdit" });

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const saving = ref(false);

const postId = computed(() => {
  const id = route.params.id;
  return id ? Number(id) : 0;
});

const form = ref({
  title: "",
  slug: "",
  description: "",
  content: "",
  cover: "",
  category_id: null as number | null,
  tags: [] as string[],
  status: "draft",
  is_pinned: false,
  reading_time: 0,
  word_count: 0,
  font_id: null as number | null
});

const categoryList = ref<CategoryItem[]>([]);
const tagList = ref<TagItem[]>([]);
const fontList = ref<FontItem[]>([]);
const tagInputVisible = ref(false);
const tagInputValue = ref("");
const coverUploading = ref(false);
const coverInputRef = ref<HTMLInputElement>();

// 正文字体实时预览：选中字体后动态注入 @font-face（走公开 file 接口，长缓存），
// 用 FontFace API 预加载再渲染，缺字由 font-family 链回退，不破版。
const previewMode = ref<"body" | "heading" | "poem">("body");
const previewLoaded = ref(true);
const previewStyleEl = ref<HTMLStyleElement | null>(null);

const selectedFont = computed(
  () => fontList.value.find(f => f.id === form.value.font_id) || null
);

const previewFontStyle = computed(() => {
  if (!selectedFont.value) return undefined;
  return { fontFamily: `'${selectedFont.value.family}', system-ui, sans-serif` };
});

const previewSamples: Record<string, { text: string; cls: string }> = {
  body: { text: "", cls: "text-base leading-8" },
  heading: {
    text: "风雅颂 · 兰亭集序",
    cls: "text-3xl font-bold"
  },
  poem: {
    text: "春江潮水连海平，海上明月共潮生。滟滟随波千万里，何处春江无月明！",
    cls: "text-lg leading-9"
  }
};

// 正文预览：把 Vditor 内容（markdown 或 HTML）转成纯文本，直接预览实际正文
function stripToText(raw: string): string {
  const src = String(raw || "");
  if (/<\/?[a-z][\s\S]*>/i.test(src) && !src.includes("```")) {
    try {
      const doc = new DOMParser().parseFromString(src, "text/html");
      const t = doc.body.textContent?.trim();
      if (t) return t;
    } catch {
      // fallthrough
    }
  }
  return src
    .replace(/```[\s\S]*?```/g, "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/[*_~`>]/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const previewBodyText = computed(() => stripToText(form.value.content));

const previewText = computed(() =>
  previewMode.value === "body"
    ? previewBodyText.value
    : previewSamples[previewMode.value].text
);

// 缺字检测：canvas 宽度对比法——所选字体与 monospace 测量宽度相同即视为该字体缺字（走回退）
const missingChars = ref<string[]>([]);
const previewCanvas = ref<HTMLCanvasElement | null>(null);
let detectTimer: ReturnType<typeof setTimeout> | null = null;

function detectMissing() {
  const f = selectedFont.value;
  if (!f || !previewText.value) {
    missingChars.value = [];
    return;
  }
  if (!previewCanvas.value) previewCanvas.value = document.createElement("canvas");
  const ctx = previewCanvas.value.getContext("2d")!;
  const seen = new Set<string>();
  const missing: string[] = [];
  for (const ch of previewText.value) {
    if (seen.has(ch)) continue;
    seen.add(ch);
    ctx.font = `16px '${f.family}', monospace`;
    const w1 = ctx.measureText(ch).width;
    ctx.font = "16px monospace";
    const w2 = ctx.measureText(ch).width;
    if (Math.abs(w1 - w2) < 0.01) missing.push(ch);
  }
  missingChars.value = missing.slice(0, 40);
}

const missingInfo = computed(() => {
  if (!selectedFont.value || !previewText.value) return "";
  if (missingChars.value.length === 0) return "所选字体支持预览内容全部字符";
  return `该字体缺少 ${missingChars.value.length} 个字符，将回退默认字体显示：${missingChars.value.join(" ")}`;
});

function scheduleDetect() {
  if (detectTimer) clearTimeout(detectTimer);
  detectTimer = setTimeout(() => {
    detectMissing();
    detectTimer = null;
  }, 300);
}

watch(
  () => form.value.font_id,
  async id => {
    previewLoaded.value = false;
    if (!previewStyleEl.value) {
      previewStyleEl.value = document.createElement("style");
      document.head.appendChild(previewStyleEl.value);
    }
    previewStyleEl.value.textContent = "";
    const f = fontList.value.find(x => x.id === id);
    if (!f) {
      previewLoaded.value = true;
      return;
    }
    previewStyleEl.value.textContent =
      `@font-face{font-family:"${f.family}";src:url("/api/fonts/${f.id}/file") format("woff2");font-display:swap;font-weight:400;}`;
    try {
      await document.fonts.load(`400 16px "${f.family}"`, previewText.value);
    } catch {
      // 加载失败（字体文件过大/网络）仍显示，交给字体回退
    }
    previewLoaded.value = true;
    detectMissing();
  },
  { immediate: true }
);

watch(
  () => form.value.content,
  () => scheduleDetect()
);

watch(previewMode, () => {
  if (previewLoaded.value) scheduleDetect();
});

const rules = {
  title: [{ required: true, message: "请输入标题", trigger: "blur" }],
  slug: [{ required: true, message: "请输入 URL 别名", trigger: "blur" }]
};

function autoSlug() {
  if (!form.value.slug && form.value.title) {
    form.value.slug = form.value.title
      .toLowerCase()
      .replace(/\s+/g, "-")
      .replace(/[^\w\-]/g, "");
  }
}

function handleTagClose(tag: string) {
  form.value.tags = form.value.tags.filter(t => t !== tag);
}

function handleTagConfirm() {
  if (tagInputValue.value && !form.value.tags.includes(tagInputValue.value)) {
    form.value.tags.push(tagInputValue.value);
  }
  tagInputVisible.value = false;
  tagInputValue.value = "";
}

function addExistingTag(name: string) {
  if (!form.value.tags.includes(name)) {
    form.value.tags.push(name);
  }
}

async function handleCoverUpload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  coverUploading.value = true;
  try {
    const res = await uploadImage(file);
    form.value.cover = res.url;
    message("封面上传成功", { type: "success" });
  } catch (e: any) {
    message(e?.message ?? "上传失败", { type: "error" });
  } finally {
    coverUploading.value = false;
    input.value = "";
  }
}

async function handleSave() {
  if (!form.value.title || !form.value.slug) {
    message("标题和 URL 别名必填", { type: "warning" });
    return;
  }
  saving.value = true;
  try {
    if (postId.value) {
      await updatePost(postId.value, form.value);
      message("更新成功", { type: "success" });
    } else {
      await createPost(form.value);
      message("创建成功", { type: "success" });
    }
    router.push("/post/index");
  } catch (e: any) {
    message(e?.message ?? "保存失败", { type: "error" });
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  const [cats, tags, fonts] = await Promise.all([
    getCategories().catch(() => []),
    getTags().catch(() => []),
    getFonts().catch(() => [])
  ]);
  categoryList.value = cats;
  tagList.value = tags;
  fontList.value = fonts;

  if (postId.value) {
    loading.value = true;
    try {
      const detail = await getPostById(postId.value);
      form.value = {
        title: detail.title,
        slug: detail.slug,
        description: detail.description,
        content: detail.content,
        cover: detail.cover,
        category_id: null,
        tags: detail.tags || [],
        status: detail.status,
        is_pinned: detail.is_pinned,
        reading_time: detail.reading_time ?? 0,
        word_count: detail.word_count ?? 0,
        font_id: detail.font_id ?? null
      };
      const cat = categoryList.value.find(c => c.name === detail.category);
      if (cat) form.value.category_id = cat.id;
    } finally {
      loading.value = false;
    }
  }
});
</script>

<template>
  <div v-loading="loading" class="p-4">
    <el-card shadow="never">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-medium">
            {{ postId ? "编辑文章" : "写文章" }}
          </span>
          <div class="flex gap-2">
            <el-button @click="router.push('/post/index')">返回</el-button>
            <el-button type="primary" :loading="saving" @click="handleSave">
              保存
            </el-button>
          </div>
        </div>
      </template>

      <el-form
        :model="form"
        :rules="rules"
        label-width="100px"
        class="max-w-5xl"
      >
        <el-form-item label="标题" prop="title">
          <el-input
            v-model="form.title"
            placeholder="文章标题"
            @blur="autoSlug"
          />
        </el-form-item>

        <el-form-item label="URL 别名" prop="slug">
          <el-input v-model="form.slug" placeholder="url-slug" />
        </el-form-item>

        <el-form-item label="摘要">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            placeholder="文章摘要（可选）"
          />
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="分类">
              <el-select
                v-model="form.category_id"
                placeholder="选择分类"
                clearable
                class="w-full"
              >
                <el-option
                  v-for="cat in categoryList"
                  :key="cat.id"
                  :label="cat.name"
                  :value="cat.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="正文字体">
              <el-select
                v-model="form.font_id"
                placeholder="默认字体"
                clearable
                class="w-full"
              >
                <el-option
                  v-for="f in fontList"
                  :key="f.id"
                  :label="f.name"
                  :value="f.id"
                >
                  <span :style="{ fontFamily: f.family + ', serif' }">{{ f.name }}</span>
                  <span class="text-gray-400 text-xs ml-1">（{{ f.family }}）</span>
                </el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select v-model="form.status" class="w-full">
                <el-option label="草稿" value="draft" />
                <el-option label="已发布" value="published" />
                <el-option label="已归档" value="archived" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="字体预览">
          <div class="w-full">
            <div class="flex justify-between items-center mb-2 flex-wrap gap-2">
              <span class="text-sm text-gray-500">
                {{
                  selectedFont
                    ? `当前：${selectedFont.name}（${selectedFont.family}）`
                    : "当前：默认字体（Yozai）"
                }}
              </span>
              <el-radio-group v-model="previewMode" size="small">
                <el-radio-button value="body">正文</el-radio-button>
                <el-radio-button value="heading">标题</el-radio-button>
                <el-radio-button value="poem">古诗</el-radio-button>
              </el-radio-group>
            </div>
            <div
              v-loading="!previewLoaded"
              class="rounded-md border border-gray-200 dark:border-gray-700 p-4 min-h-24 max-h-80 overflow-auto bg-white dark:bg-gray-900"
              :style="previewFontStyle"
            >
              <p :class="previewSamples[previewMode].cls">
                {{ previewText }}
              </p>
            </div>
            <el-alert
              v-if="missingInfo && selectedFont"
              :type="missingChars.length === 0 ? 'success' : 'warning'"
              :closable="false"
              class="mt-2"
              :title="missingInfo"
            />
          </div>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="置顶">
              <el-switch v-model="form.is_pinned" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="阅读时长(分钟)">
              <el-input-number v-model="form.reading_time" :min="0" class="w-full" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="字数">
              <el-input-number v-model="form.word_count" :min="0" class="w-full" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="封面图">
          <div class="flex gap-2 w-full">
            <el-input v-model="form.cover" placeholder="封面图 URL" />
            <input
              ref="coverInputRef"
              type="file"
              accept="image/*"
              class="hidden"
              @change="handleCoverUpload"
            />
            <el-button
              :loading="coverUploading"
              @click="coverInputRef?.click()"
            >
              上传图片
            </el-button>
          </div>
          <el-image
            v-if="form.cover"
            :src="form.cover"
            class="mt-2 rounded"
            fit="cover"
            style="max-width: 200px; max-height: 120px"
          />
        </el-form-item>

        <el-form-item label="标签">
          <div class="flex flex-wrap gap-2 items-center">
            <el-tag
              v-for="tag in form.tags"
              :key="tag"
              closable
              @close="handleTagClose(tag)"
            >
              {{ tag }}
            </el-tag>
            <el-input
              v-if="tagInputVisible"
              v-model="tagInputValue"
              size="small"
              class="w-24"
              @keyup.enter="handleTagConfirm"
              @blur="handleTagConfirm"
            />
            <el-button
              v-else
              size="small"
              @click="tagInputVisible = true"
            >
              + 添加
            </el-button>
          </div>
          <div
            v-if="tagList.length > 0"
            class="mt-2 text-sm text-gray-400"
          >
            快速添加：
            <el-button
              v-for="t in tagList.filter(t => !form.tags.includes(t.name))"
              :key="t.id"
              link
              type="primary"
              size="small"
              @click="addExistingTag(t.name)"
            >
              {{ t.name }}
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="正文">
          <div class="w-full">
            <Vditor
              v-model="form.content"
              :options="{ height: 500 }"
            />
          </div>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>
