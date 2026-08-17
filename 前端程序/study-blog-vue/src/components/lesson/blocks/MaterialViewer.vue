<script setup>
// 资料预览渲染器：按 mime_type 分派（交接文档 15 §7.1）。
//
// 可内嵌：Markdown/纯文本（走 renderMarkdown + DOMPurify 管线）、图片（点击放大）、
//         PDF（iframe 走浏览器内置阅读器）、音视频（原生控件）。
// 不可内嵌：Office / 归档等浏览器渲染不了的类型——本期诚实地只给下载 + 说明
//         （要做 Word 转 PDF 得自建 LibreOffice 服务，那是另一个模块）。
//
// 数据来自块内容 DTO（已含 material_id/display_name/mime_type/size_bytes）；
// 下载/内嵌走学生端两个接口，路径带 lesson_id + block_id（§7.3 安全红线，
// 校验绑定关系与两道闸门），凭证靠同源 cookie 自动携带。
import { computed, defineAsyncComponent, ref, watch } from "vue";
import { renderMarkdown } from "../../../services/markdown";
import { openLightbox } from "../../../stores/lightbox";
import LessonIcon from "../LessonIcon.vue";
// PDF.js 拖着 ~300KB 的 worker，异步加载：纯图文/音视频课时不该为它买单。
// 和 BlockPractice 拖 CodeMirror 同等待遇。加载失败时 iframe 降级（见下方 isPdf 分支）。
const PdfReader = defineAsyncComponent({
  loader: () => import("./PdfReader.vue"),
  // PDF.js 加载失败 → errorComponent 渲染 iframe 降级（iOS Safari/微信内置浏览器
  // 可能不支持 worker，iframe 兜底比空白强）
  errorComponent: {
    template: '<iframe class="mat-frame" :src="url" title="资料预览"></iframe>',
    props: ["url"],
  },
  delay: 0,
});

// 把内嵌的 PdfReader 实例透传给父组件：BlockMaterials 在 mat-preview-bar 里复用
// 它的翻页/缩放状态（合并工具栏，腾高度给阅读区）。异步组件，加载完成前为 null。
const pdfRef = ref(null);
defineExpose({ pdfRef });

const props = defineProps({
  material: { type: Object, required: true },
  lessonId: { type: Number, required: true },
  blockId: { type: Number, required: true },
});

const apiBase = import.meta.env.VITE_API_BASE_URL || "";
const mime = computed(() => (props.material.mime_type || "").toLowerCase());

const isImage = computed(() => /^image\//.test(mime.value));
const isText = computed(() => /^text\/(markdown|plain|x-markdown)/.test(mime.value));
const isPdf = computed(() => mime.value === "application/pdf");
const isVideo = computed(() => /^video\//.test(mime.value));
const isAudio = computed(() => /^audio\//.test(mime.value));
const canEmbed = computed(
  () => isImage.value || isText.value || isPdf.value || isVideo.value || isAudio.value,
);

function mediaUrl(kind) {
  return `${apiBase}/api/lessons/${props.lessonId}/blocks/${props.blockId}/materials/${props.material.material_id}/${kind}`;
}
const inlineUrl = computed(() => mediaUrl("inline"));
const downloadUrl = computed(() => mediaUrl("download"));
// fetch 类消费方（PDF.js / md 文本拉取）必须走 ?proxy=1 同源流（2026-08-14 实测定案）：
// inline 默认 302 到 MinIO 预签名 URL，而 MinIO 的对象 GET 成功响应不带
// Access-Control-Allow-Origin（只有 403 等错误响应才带）——浏览器 fetch 一律被
// CORS 拦截（net::ERR_FAILED / PDF.js UnknownErrorException）。iframe/img/video
// 标签是 no-cors 不受限，继续用 302 直连省应用带宽；fetch 一律走 proxy=1，
// 后端 _proxy_material_stream 支持 Range 206，PDF 按页取/秒开不受影响。
const inlineProxyUrl = computed(() => `${mediaUrl("inline")}?proxy=1`);

// Markdown/纯文本：拉取文本后走统一渲染管线（空位标记 + DOMPurify，与题干同源）。
// 拿不到文本时（接口失败/权限变化）给出可见的提示而不是转圈转到底。
const mdText = ref("");
const mdLoading = ref(false);
const mdError = ref("");

async function loadMarkdown() {
  if (!isText.value) return;
  mdText.value = "";
  mdError.value = "";
  mdLoading.value = true;
  try {
    const response = await fetch(inlineProxyUrl.value, { credentials: "include" });
    if (!response.ok) {
      throw new Error(response.status === 404 ? "资料不存在或已失效。" : "资料加载失败。");
    }
    mdText.value = await response.text();
  } catch (error) {
    mdError.value = error?.message || "资料加载失败。";
  } finally {
    mdLoading.value = false;
  }
}

watch(() => props.material.material_id, loadMarkdown, { immediate: true });

// 图片点击放大。v-html 里的图是事件委托（见 MarkdownBody），这里 <img> 是本组件
// 直接渲染的，但保留同一套委托写法，防止以后换成多图列表时忘了绑。
function onImageClick(event) {
  const img = event.target;
  if (!img || img.tagName !== "IMG") return;
  const src = img.currentSrc || img.getAttribute("src");
  if (!src) return;
  openLightbox(src, props.material.display_name || "");
}
</script>

<template>
  <div class="mat-viewer">
    <!-- 图片：可点击放大（复用 ImageLightbox，学习壳里 LessonPlayer 挂了单例挂载点） -->
    <img
      v-if="isImage"
      class="mat-img"
      :src="inlineUrl"
      :alt="material.display_name"
      @click="onImageClick"
    />

    <!-- Markdown / 纯文本：renderMarkdown 管线（含 DOMPurify 净化） -->
    <div v-else-if="isText" class="mat-md">
      <p v-if="mdLoading" class="mat-hint">正在加载…</p>
      <p v-else-if="mdError" class="mat-hint mat-error">{{ mdError }}</p>
      <div v-else class="mat-md-body" v-html="renderMarkdown(mdText)"></div>
    </div>

    <!-- PDF：PDF.js 自托管按页渲染（交接文档 17 §5 S3-2）。
         PDF.js 是 fetch 消费方，必须走 ?proxy=1 同源流（302 到 MinIO 会被 CORS
         拦截，见 inlineProxyUrl 注释）；proxy 流支持 Range 206，按页取/首页秒开不变。
         组件加载失败（旧浏览器/worker 不支持）时 defineAsyncComponent 的 errorComponent
         退回 iframe 浏览器内置阅读器兜底（iframe 是 no-cors，继续用 302 直连）。 -->
    <PdfReader
      v-else-if="isPdf"
      ref="pdfRef"
      :url="inlineProxyUrl"
      :material-id="material.material_id"
      :title="material.display_name"
    />

    <!-- 音视频：原生控件 -->
    <video v-else-if="isVideo" class="mat-frame mat-video" :src="inlineUrl" controls></video>
    <audio v-else-if="isAudio" class="mat-audio" :src="inlineUrl" controls></audio>

    <!-- 不可内嵌：Office / 归档等，给明确的「需下载打开」而不是空白或转圈（§7.1） -->
    <div v-else class="mat-download-only">
      <LessonIcon name="materials" :size="30" />
      <p>{{ material.display_name }}</p>
      <p>该格式需下载后用本地软件打开。</p>
      <a class="lbtn lbtn-accent" :href="downloadUrl" :download="material.display_name">
        下载文件
      </a>
    </div>
  </div>
</template>

<style scoped>
/* flex:1 吃满 .mat-preview-body（flex 行）的全部宽度：不写的话查看器会收缩成
   内容宽度，PDF 阅读器只剩 canvas 那么宽、贴左，右侧空一大片——页面相对屏幕
   居中也就无从谈起。min-width:0 允许它比内容窄（放大溢出时由内部滚动接管）。 */
.mat-viewer {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.mat-img {
  margin: auto;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: var(--card-radius, 8px);
  cursor: zoom-in;
}

.mat-frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: var(--surface);
  border-radius: var(--card-radius, 8px);
}
.mat-video {
  display: block;
}

.mat-md {
  height: 100%;
  overflow-y: auto;
  padding: 2px 4px;
}
.mat-md-body {
  font-size: 15px;
  line-height: 1.85;
}
/* 代码块与图文块同款：墨绿底、等宽字体（lesson.css .block-article 的约定） */
.mat-md-body :deep(pre) {
  background: var(--editor-bg);
  color: var(--editor-fg);
  border-radius: var(--card-radius, 8px);
  padding: 14px 18px;
  overflow-x: auto;
  font-size: 12.5px;
  line-height: 1.8;
  margin: 14px 0;
}
.mat-md-body :deep(code) {
  font-family: var(--font-mono);
  background: var(--mint);
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 0.92em;
}
.mat-md-body :deep(pre code) {
  background: none;
  padding: 0;
}
.mat-md-body :deep(img) {
  max-width: 100%;
  border-radius: var(--card-radius, 8px);
}
.mat-md-body :deep(a) {
  color: var(--accent);
}

.mat-audio {
  margin: auto;
  width: 100%;
}

.mat-hint {
  margin: auto;
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}
.mat-error {
  color: var(--danger);
}

.mat-download-only {
  margin: auto;
  text-align: center;
  color: var(--muted);
  display: grid;
  gap: 10px;
  justify-items: center;
  font-size: 12.5px;
}
.mat-download-only p {
  margin: 0;
}
</style>
