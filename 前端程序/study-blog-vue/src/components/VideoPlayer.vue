<script setup>
// 学员端视频播放组件：POST /api/lessons/{lessonId}/play 拿播放地址 →
// Video.js 播放 /v/{id}/master.m3u8?e=..&u=..&s=..（多码率 HLS）。
//
// 地址形状（P2-5，B 站 / 腾讯视频同款）：**路径稳定，签名放 query**，生产由 nginx
// 在边缘校验后直连对象存储，切片不进应用。子列表和切片的签名由服务端改写 m3u8 时
// 逐条补上——播放器不会把父 URL 的 query 继承下去，这里什么都不用做。
// 过期时刻在服务端对齐到时间片，所以同一时间片内重新进课时 / F5 拿到的地址逐字节
// 相同，浏览器磁盘缓存直接命中，切片不再重下（见 app/video_sign.py）。
//
// 续签（口径 2026-08-09 拍板）：TTL = 视频时长 + 10 分钟（1–4 小时，量化后只多不少）。
// 播放器负责在地址失效前把播放续下去：
//   1. 临近过期（剩 60s）→ 自动重新签发并换源（保留当前播放位置）；
//   2. 页面从后台恢复可见 → 若令牌临近过期立即续签（挂后台久了回来）；
//   3. 播放报错（HLS 401/加载失败）→ 距上次续签超过冷却期则续签重试一次。
// 换源会短暂重载 HLS，但只发生在令牌临近过期时，正常观看不受影响。
//
// 关键实现约束：`<video ref="playerEl">` 必须**常驻 DOM**（v-show 控制显隐），
// 不能放进 v-if/v-else 条件链——否则 loading/ready/error 状态切换时元素被销毁重建，
// videojs(playerEl.value) 会拿到 null 抛 "The element or ID supplied is not valid"。
// 关键：videojs 必须用**官方 UMD 完整构建**（dist/video.min.js），不能用包的
// ESM 入口（video.js 默认 exports → dist/video.es.js）——其 VHS（HLS）source
// handler 在浏览器里不注册，m3u8 会直接 MEDIA_ERR_SRC_NOT_SUPPORTED（code 4）。
// 与后台 videos.js 的约定一致（「不要用 esbuild ESM bundle」），后台就是靠
// UMD 才能播 HLS 的。
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import videojs from "video.js/dist/video.min.js";
import "video.js/dist/video-js.css";
import { request } from "../services/auth";
import { takePlayToken } from "../services/prefetch";

const props = defineProps({
  lessonId: { type: Number, required: true },
  // 内容块模型：指定视频块（0..N 个视频块时逐个拿令牌）；不传则走旧字段兜底
  blockId: { type: Number, default: null },
  // Scratch 解析视频不属于普通视频内容块，必须走题目专属、提交后才放行的签发端点。
  // 空值保持原有课时视频契约，避免影响现有预签与学习进度。
  playPath: { type: String, default: "" },
  autoplay: { type: Boolean, default: false },
  // 续播断点（秒）：课时详情块下发 resume_position_seconds（服务端账本最远位置），
  // loadedmetadata 后 seek 到这里；0 / 缺省 = 从头播。
  resumePositionSeconds: { type: Number, default: 0 },
});
// progress(percent 0..100)：学习页用它做「看到 completion_percent 算完成」的判定。
// 节流在调用方（useLessonProgress）做——播放器只负责如实汇报。
const emit = defineEmits(["progress", "ended"]);

const playerEl = ref(null);
const loading = ref(true);
const ready = ref(false);
const error = ref("");
let player = null;
let expiresAt = 0; // 令牌过期时间（epoch 秒），0 = 尚未签发
let lastRenewAt = 0; // 上次续签时间（epoch 毫秒），防 401/加载失败风暴
let renewing = false;
let renewTimer = null;

const RENEW_LEAD = 60; // 距过期 60 秒内续签
const RENEW_COOLDOWN = 30_000; // 30 秒内不重复续签（错误风暴闸）

async function mint() {
  const path = props.playPath || `/api/lessons/${props.lessonId}/play`;
  const data = await request(path, {
    method: "POST",
    // 有 block_id 就按块签发（内容块模型），否则旧字段兜底
    body: JSON.stringify(props.playPath ? {} : props.blockId ? { block_id: props.blockId } : {}),
  });
  expiresAt = Date.now() / 1000 + (data.expires_in_seconds || 0);
  // 诊断留痕：浏览器实际拿到的播放地址（含签名参数），定位 403 时与后端核对用
  console.info(
    "[VideoPlayer] play ok, master:",
    data.master_playlist,
    "ttl:",
    data.expires_in_seconds,
    "s",
  );
  return data;
}

/**
 * 首次取播放地址。优先用课时壳预签好的令牌（交接文档 17 §5 S2-3）——课时详情一到手
 * 壳就签了，那时这个组件的 chunk 还在下载路上，等于把一整个 RTT 藏进了下载时间里。
 *
 * takePlayToken 返回的是**可能还在飞的 promise**，await 它就不会出现「预签一次 +
 * 自己再签一次」。没预签过（比如后台预览页直接挂这个组件）就照常自己签。
 */
async function firstPlayData() {
  if (props.playPath) return mint();
  const pending = takePlayToken(props.blockId);
  const prefetched = pending ? await pending : null;
  if (prefetched?.master_playlist) {
    const age = (Date.now() - (prefetched.minted_at || Date.now())) / 1000;
    const left = (prefetched.expires_in_seconds || 0) - age;
    // 预签的令牌可能在缓存里躺过一会儿（学生在前面的块停留很久）。剩余寿命不够跨过
    // 续签窗口就直接重签——否则刚起播就要换源，比老老实实签一次还慢。
    if (left > RENEW_LEAD * 5) {
      expiresAt = Date.now() / 1000 + left;
      console.info("[VideoPlayer] play ok (prefetched), master:", prefetched.master_playlist);
      return prefetched;
    }
  }
  return mint();
}

/** 重新签发播放地址并换源，保留播放位置。失败时把错误落屏（403 = 权限已失效）。
 *
 * 同一时间片内重签会拿到**同一个地址**（服务端 deadline 量化），此时换源等于原地重载，
 * 切片走浏览器缓存，代价很小；跨时间片才会真换出新地址。 */
async function renew() {
  if (renewing) return;
  renewing = true;
  try {
    const data = await mint();
    lastRenewAt = Date.now();
    if (player) {
      const position = player.currentTime() || 0;
      player.src({ src: data.master_playlist, type: "application/vnd.apple.mpegurl" });
      player.one("loadedmetadata", () => {
        if (position) player.currentTime(position);
      });
      player.play().catch(() => {});
    }
  } catch (err) {
    error.value =
      err?.status === 403 || (err?.message || "").includes("权限")
        ? "该课时播放权限已失效。"
        : "播放地址刷新失败，请刷新页面重试。";
  } finally {
    renewing = false;
  }
}

function onVisibility() {
  if (document.visibilityState !== "visible") return;
  if (player && expiresAt && expiresAt - Date.now() / 1000 < RENEW_LEAD * 2) renew();
}

onMounted(async () => {
  try {
    const data = await firstPlayData();
    // 元素常驻：先显示 <video>（v-show 去隐藏），nextTick 等 v-show 生效再初始化
    // videojs——在 display:none 元素上初始化播放器尺寸为 0、黑屏转圈。
    ready.value = true;
    await nextTick();
    if (!playerEl.value) {
      error.value = "播放器初始化失败，请刷新页面重试。";
      return;
    }
    try {
      player = videojs(playerEl.value, {
        controls: true,
        // fill: true → video 填满容器，容器宽高比由 CSS（aspect-ratio 16/9）保证，
        // 与外链 iframe 窗口一致。不用 fluid（HLS 初始无宽高比会塌陷）。
        fluid: false,
        fill: true,
        preload: "auto",
        autoplay: props.autoplay,
        sources: [
          {
            src: data.master_playlist, // /v/{id}/master.m3u8?e=..&u=..&s=..
            type: "application/vnd.apple.mpegurl",
          },
        ],
      });
    } catch (initErr) {
      // videojs 初始化抛错（元素/配置问题）时落屏原始信息，便于定位而非白屏
      console.error("[VideoPlayer] videojs init failed:", initErr);
      error.value = `播放器初始化失败（${initErr?.message || "未知原因"}），请刷新页面重试。`;
      return;
    }
    player.on("timeupdate", () => {
      const dur = player.duration();
      // 报**播放位置**而不是百分比：服务端要靠位置差记账（看了多少秒），
      // 百分比丢掉了"从第几秒到第几秒"这个信息。总时长以服务端的
      // videos.duration_seconds 为准，这里给出来只是让壳能算个显示用的百分比。
      // 暂停时不报：暂停还继续报等于给挂机记账，与记账的目的正相反。
      if (dur > 0 && !player.paused()) {
        emit("progress", { position: player.currentTime(), duration: dur });
      }
    });
    // 续播断点：HLS 元数据就绪后 seek。autoplay 时先挂 seek 再 play，避免起播即回 0。
    const resume = Math.max(0, props.resumePositionSeconds || 0);
    if (resume > 0) {
      player.one("loadedmetadata", () => {
        try {
          if (resume < (player.duration() || 0)) player.currentTime(resume);
        } catch {
          /* seek 失败不致命：学生手动拖进度即可 */
        }
      });
    }
    player.on("ended", () => emit("ended"));
    player.on("error", () => {
      // HLS 401 / 加载失败：令牌还在且距上次续签超过冷却期 → 续签重试一次；
      // 冷却期内再报错则落屏（避免 401 → 续签 → 401 的死循环风暴）。
      // 先把 Video.js/VHS 的内部错误打出来——通用 media error 看不出是 404、
      // HTML 被当 m3u8 还是分片加载失败，detail.message 里通常带着原因。
      const detail = player.error?.();
      console.error("[VideoPlayer] media error:", detail);
      if (expiresAt && Date.now() - lastRenewAt > RENEW_COOLDOWN) {
        renew();
        return;
      }
      error.value = detail?.message || "视频加载失败，请稍后重试或联系管理员。";
    });
  } catch (err) {
    error.value = err?.message || "无法获取播放地址，请确认你有该课时的权限。";
  } finally {
    loading.value = false;
  }
  // 临近过期自动续签：TTL 最短 60 分钟，30 秒检查一次足够，不空转 CPU。
  renewTimer = setInterval(() => {
    if (!player || !expiresAt || renewing) return;
    if (expiresAt - Date.now() / 1000 < RENEW_LEAD) renew();
  }, 30_000);
  document.addEventListener("visibilitychange", onVisibility);
});

onBeforeUnmount(() => {
  if (renewTimer) clearInterval(renewTimer);
  document.removeEventListener("visibilitychange", onVisibility);
  if (player) player.dispose();
});
</script>

<template>
  <div class="video-player">
    <!-- 常驻 DOM：ref 从挂载起稳定存在，杜绝 videojs 拿 null -->
    <video
      ref="playerEl"
      class="video-js vjs-big-play-centered"
      :class="{ 'vp-hidden': !ready }"
      playsinline
    />
    <div v-if="loading" class="player-state">正在获取播放地址…</div>
    <div v-else-if="error" class="player-state player-error">{{ error }}</div>
  </div>
</template>

<style scoped>
.video-player {
  width: 100%;
  /* 与外链 iframe（.external 的 aspect-ratio 16/9）同一窗口尺寸 */
  aspect-ratio: 16 / 9;
  position: relative;
  background: #0f1216;
  border-radius: 10px;
  overflow: hidden;
}
.vp-hidden {
  display: none;
}
.player-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f1216;
  color: #9aa3ad;
  font-size: 14px;
}
.player-error {
  color: #ff9d9d;
}
</style>
