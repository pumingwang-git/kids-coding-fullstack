<script setup>
// 视频块：source_type 分三路（platform 令牌 HLS / embed iframe / direct Video.js）。
//
// 完成口径（交接文档 14 §5.1）：播放进度 ≥ lesson_video_blocks.completion_percent。
// **阈值判定在服务端**——前端只如实上报百分比，不猜阈值，也不写死 100%。
// embed（B 站等 iframe）拿不到播放进度，只能由学生手动点完成。
//
// VideoPlayer / DirectVideo 都依赖 video.js（打包约 600KB+），用 defineAsyncComponent
// 拆成独立 chunk：只有真的渲染视频块时才下载播放器代码。
import { defineAsyncComponent } from "vue";

const VideoPlayer = defineAsyncComponent(() => import("../../VideoPlayer.vue"));
const DirectVideo = defineAsyncComponent(() => import("../../DirectVideo.vue"));

const props = defineProps({
  block: { type: Object, required: true },
  lessonId: { type: Number, required: true },
});
const emit = defineEmits(["progress", "ended"]);

/**
 * 外链地址 → 可嵌入 iframe 的播放器地址。
 * 后台填的可能是普通播放页（如 B 站 www.bilibili.com/video/BVxxx），这类页面
 * 拒绝被 iframe 嵌入（X-Frame-Options / 播放器防盗链）→ 用户看到「网络异常」。
 * 只对 source_type=embed 调用；直链（MP4/HLS）走 DirectVideo，不进 iframe。
 */
function embedUrl(raw) {
  if (!raw) return raw;
  const bilibili = raw.match(
    /(?:bilibili\.com\/video\/|player\.bilibili\.com\/player\.html\?bvid=)(BV[0-9A-Za-z]+)/,
  );
  if (bilibili) {
    return `https://player.bilibili.com/player.html?bvid=${bilibili[1]}&page=1&high_quality=1&danmaku=0`;
  }
  return raw;
}
</script>

<template>
  <div class="block-video">
    <div class="v-stage">
      <VideoPlayer
        v-if="block.source_type === 'platform' && block.ready"
        :lesson-id="lessonId"
        :block-id="block.id || undefined"
        :resume-position-seconds="block.resume_position_seconds || 0"
        @progress="emit('progress', $event)"
        @ended="emit('ended')"
      />
      <p
        v-else-if="block.source_type === 'platform'"
        style="color: var(--editor-fg); text-align: center"
      >
        视频正在转码中，完成后即可播放。
      </p>
      <iframe
        v-else-if="block.source_type === 'embed'"
        class="v-external"
        :src="embedUrl(block.video_url)"
        title="课时视频"
        allowfullscreen
      ></iframe>
      <DirectVideo
        v-else-if="block.source_type === 'direct'"
        :src="block.video_url"
        @progress="emit('progress', $event)"
        @ended="emit('ended')"
      />
      <p v-else style="color: var(--editor-fg); text-align: center">该视频块尚未配置可播放内容。</p>
    </div>
  </div>
</template>
