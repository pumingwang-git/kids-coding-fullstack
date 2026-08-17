<script setup>
// 外链直链媒体（MP4 / HLS）播放组件：交给 Video.js（UMD 完整构建）渲染。
//
// 为什么要独立组件而不是塞进 VideoPlayer.vue：
// VideoPlayer 的职责是「课时令牌播放」——签发 /v/ 前缀令牌并续签；直链没有令牌，
// 也不需要续签，混在一起会让令牌续签逻辑为「永远不需要续签」的场景空跑。
//
// 关键实现约束与 VideoPlayer.vue 一致：
// - videojs 必须用官方 UMD 完整构建（dist/video.min.js），不能用 ESM 入口——
//   其 VHS（HLS）source handler 在浏览器里不注册，m3u8 会直接 MEDIA_ERR_SRC_NOT_SUPPORTED；
// - `<video ref>` 常驻 DOM（v-show），不能进 v-if 条件链。
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import videojs from "video.js/dist/video.min.js";
import "video.js/dist/video-js.css";

const props = defineProps({
  src: { type: String, required: true },
  autoplay: { type: Boolean, default: false },
});
// progress(percent 0..100)：学习页用它做「看到 completion_percent 算完成」的判定。
// 节流在调用方（useLessonProgress）做——播放器只负责如实汇报。
const emit = defineEmits(["progress", "ended"]);

const playerEl = ref(null);
const error = ref("");
let player = null;

function sourceType(src) {
  if (/\.m3u8($|\?)/i.test(src)) return "application/vnd.apple.mpegurl";
  return "video/mp4";
}

onMounted(async () => {
  try {
    await nextTick();
    if (!playerEl.value) return;
    player = videojs(playerEl.value, {
      controls: true,
      fluid: false,
      fill: true,
      preload: "auto",
      autoplay: props.autoplay,
      sources: [{ src: props.src, type: sourceType(props.src) }],
    });
    player.on("timeupdate", () => {
      const dur = player.duration();
      // 载荷与 VideoPlayer 一字不差（壳只写一套 onVideoProgress）：报位置不报百分比，
      // 暂停时不报。理由见 VideoPlayer.vue 同名处理器的注释。
      if (dur > 0 && !player.paused()) {
        emit("progress", { position: player.currentTime(), duration: dur });
      }
    });
    player.on("ended", () => emit("ended"));
    player.on("error", () => {
      const detail = player.error?.();
      console.error("[DirectVideo] media error:", detail);
      error.value =
        detail?.message || "视频加载失败，请确认直链地址可访问且格式受支持（MP4 / HLS）。";
    });
  } catch (err) {
    console.error("[DirectVideo] videojs init failed:", err);
    error.value = `播放器初始化失败（${err?.message || "未知原因"}）。`;
  }
});

onBeforeUnmount(() => {
  if (player) player.dispose();
});
</script>

<template>
  <div class="direct-video">
    <video
      ref="playerEl"
      class="video-js vjs-big-play-centered"
      :class="{ 'dv-hidden': error }"
      playsinline
    />
    <div v-if="error" class="direct-state direct-error">{{ error }}</div>
  </div>
</template>

<style scoped>
.direct-video {
  width: 100%;
  aspect-ratio: 16 / 9;
  position: relative;
  background: #0f1216;
  border-radius: 10px;
  overflow: hidden;
}
.dv-hidden {
  display: none;
}
.direct-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: #0f1216;
  color: #ff9d9d;
  font-size: 14px;
  text-align: center;
}
</style>
