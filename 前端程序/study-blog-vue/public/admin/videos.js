// 视频管理页：Uppy S3 Multipart 直传 MinIO。
// 所有后端调用都走 admin-api.js（已带 CSRF double-submit + 会话续期）。
import { Uppy, Dashboard, AwsS3 } from "./vendor/uppy/uppy.esm.js";
import { adminRequest, adminDownload } from "./admin-api.js";
import { initLayout } from "./admin-layout.js";
// videojs 来自 videos.html 里普通 <script> 加载的官方 UMD（window.videojs）。
// 不要用 esbuild ESM bundle——其 VHS source handler 注册在浏览器里不生效。
const videojs = window.videojs;

// 与后端 settings.video_part_size 保持一致（64MB）。若两者不一致，
// Uppy 算出的分片数会超过后端建会话时的 part_count，presign 会 400。
const PART_SIZE = 64 * 1024 * 1024;
const MAX_BYTES = 2 * 1024 * 1024 * 1024; // 与后端 video_source_max_bytes 一致

const STATUS_LABEL = {
  draft: "草稿",
  uploaded: "已上传待转码",
  transcoding: "转码中",
  ready: "可播放",
  failed: "转码失败",
};

initLayout();

const uppy = new Uppy({
  autoProceed: false,
  restrictions: {
    maxFileSize: MAX_BYTES,
    allowedFileTypes: ["video/*", ".mkv", ".mov", ".m4v", "application/octet-stream"],
  },
});

uppy.use(Dashboard, {
  inline: true,
  target: "#uppy-dashboard",
  showProgressDetails: true,
  proudlyDisplayPoweredByUppy: false,
  height: 300,
});

uppy.use(AwsS3, {
  // 强制走 multipart（S3 直传的分片会话），小文件也是 1 片。
  shouldUseMultipart: () => true,
  // v4 的分片大小选项是 getChunkSize（partSize 在 v4 已移除，传了会被忽略→Uppy 用默认
  // 算法分片，与后端 part_count 对不上就会 400「分片序号越界」）。
  getChunkSize: () => PART_SIZE,
  // 并发传 3 片，别把隧道带宽打满
  limit: 3,

  // 建 multipart 会话：后端建 Video(draft)+VideoUpload(initiated) 并返回 MinIO upload_id
  async createMultipartUpload(file) {
    const res = await adminRequest("/videos/uploads", {
      method: "POST",
      body: JSON.stringify({
        title: file.name.replace(/\.[^.]+$/, "") || file.name,
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        file_size: file.size,
      }),
    });
    return { uploadId: res.upload_id, key: res.object_key };
  },

  // 逐片预签名：浏览器拿到 URL 后直传 MinIO（服务端不碰字节）
  // 注：@uppy/aws-s3 v4 的选项名是 signPart（v3 及更早叫 prepareUploadPart）。
  async signPart(file, { uploadId, key, partNumber }) {
    const res = await adminRequest(`/videos/uploads/${uploadId}/parts/${partNumber}`);
    return { url: res.url };
  },

  // 全部传完：后端用 upload_id 向 MinIO 核对 ETag（不信前端）后合并
  async completeMultipartUpload(file, { uploadId, key, parts }) {
    const res = await adminRequest(`/videos/uploads/${uploadId}/complete`, {
      method: "POST",
      body: JSON.stringify({
        parts: parts.map((p) => ({ part_number: p.PartNumber, etag: p.ETag })),
      }),
    });
    // 必须返回对象：Uppy onSuccess 会读 result.location（undefined 会 TypeError）；
    // 同时把后端返回的 video_id 带上——它会被 Uppy 放进 upload-success 的
    // response.body，前端靠它触发 toast + 列表刷新。
    return { location: "", video_id: res.video_id };
  },

  // 取消/失败清理
  async abortMultipartUpload(file, { uploadId, key }) {
    await adminRequest(`/videos/uploads/${uploadId}/abort`, { method: "POST", body: "{}" });
  },
});

uppy.on("upload-success", (file, response) => {
  const body = response?.body || response;
  if (body?.video_id) {
    toast(`视频 #${body.video_id} 上传完成，已进入转码队列。`);
    loadVideos();
  }
});

uppy.on("upload-error", (file, error) => {
  console.error("upload-error", error);
  toast(error?.message || "上传失败，请重试。", true);
});

// ---------- 最近上传列表 ----------
async function loadVideos() {
  const tbody = document.querySelector("#video-list tbody");
  try {
    const list = await adminRequest("/videos");
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted">还没有上传记录。</td></tr>';
      return;
    }
    tbody.innerHTML = list
      .map(
        (v) => `
      <tr>
        <td>${v.id}</td>
        <td>${escapeHtml(v.title)}</td>
        <td>${formatBytes(v.file_size)}</td>
        <td>${STATUS_LABEL[v.status] || v.status}</td>
        <td class="muted">${v.created_at || ""}</td>
        <td>
          ${v.playable ? `<button class="btn-text" data-play="${v.id}" type="button">播放</button>` : ""}
        </td>
      </tr>`
      )
      .join("");
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="6" class="muted">列表加载失败：${escapeHtml(error.message)}</td></tr>`;
  }
}

// ---------- 播放预览（管理员令牌 → Video.js 播多码率 HLS） ----------
let previewPlayer = null;

async function openPreview(videoId, title) {
  closePreview(); // 防止对同一 <video> 元素重复初始化（videojs 会报 Player already exists）
  // 清空 wrap 容器并重建 <video>：videojs dispose 会从 DOM 移除 video 元素，
  // 固定 id 的旧元素引用会变 null（Cannot read properties of null (reading 'replaceWith')）。
  const wrap = document.getElementById("video-player-wrap");
  wrap.innerHTML = "";
  const fresh = document.createElement("video");
  fresh.className = "video-js vjs-big-play-centered";
  fresh.setAttribute("playsinline", "");
  wrap.appendChild(fresh);
  document.getElementById("video-modal-title").textContent = title || `视频 #${videoId}`;
  document.getElementById("video-modal").hidden = false;
  try {
    const data = await adminRequest(`/videos/${videoId}/play`, { method: "POST", body: "{}" });
    let selectedIndex = 0;
    const variants = data.variants || [];
    previewPlayer = videojs(fresh, {
      controls: true,
      // fill: true → video 元素填满容器（容器高度由 JS 按视频宽高比计算）。
      // 不用 fluid/aspectRatio（会与竖屏源打架）。
      fluid: false,
      fill: true,
      autoplay: true,
      // 倍速菜单档位
      playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 2],
      // 自定义 controlBar：截图按钮 + 画质菜单（来自 extensions.js 注册）
      controlBar: {
        children: [
          "playToggle",
          "volumePanel",
          "currentTimeDisplay",
          "timeDivider",
          "durationDisplay",
          "progressControl",
          "remainingTimeDisplay",
          "spacer",
          "QualityButton",
          "playbackRateMenuButton",
          "subsCapsButton",
          "pictureInPictureToggle",
          "ScreenshotButton",
          "fullscreenToggle",
        ],
      },
      // 传给 QualityButton（通过 options.createItems 取出）
      masterPlaylist: data.master_playlist,
      variants,
      selectedIndex,
      sources: [{ src: data.master_playlist, type: "application/vnd.apple.mpegurl" }],
    });
    // 切档后刷新 selectedIndex（QualityButton 打开时会重读）
    previewPlayer.on("loadedmetadata", () => { selectedIndex = 0; });
    previewPlayer.on("error", () => toast("视频加载失败，请稍后重试。", true));
  } catch (error) {
    toast(error?.message || "获取播放地址失败。", true);
    closePreview();
  }
}

function closePreview() {
  if (previewPlayer) {
    previewPlayer.dispose();
    previewPlayer = null;
  }
  document.getElementById("video-modal").hidden = true;
}

// 列表事件委托 + 模态框关闭
document.addEventListener("click", (event) => {
  const playBtn = event.target.closest("[data-play]");
  if (playBtn) {
    const row = playBtn.closest("tr");
    const title = row?.querySelector("td:nth-child(2)")?.textContent || "";
    openPreview(Number(playBtn.dataset.play), title);
    return;
  }
  if (event.target.closest("[data-video-close]")) closePreview();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closePreview();
});

// ---------- 小工具 ----------
let toastTimer;
function toast(message, isError = false) {
  let el = document.getElementById("video-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "video-toast";
    el.style.cssText =
      "position:fixed;left:50%;bottom:32px;transform:translateX(-50%);z-index:9999;" +
      "padding:10px 18px;border-radius:8px;color:#fff;font-size:14px;box-shadow:0 4px 16px rgba(0,0,0,.2)";
    document.body.appendChild(el);
  }
  el.style.background = isError ? "#d64545" : "#1f5c4f";
  el.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.style.display = "none"), 4000);
  el.style.display = "block";
}
// 供 videojs 扩展（extensions.js）回调：截图完成提示等
window.__videoToast = toast;

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatBytes(bytes) {
  if (!bytes) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

loadVideos();
