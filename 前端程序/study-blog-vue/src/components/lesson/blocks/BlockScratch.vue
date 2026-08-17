<script setup>
// Scratch 内容块：课程学习页与独立 Scratch Studio 之间的受控入口。
//
// 这里刻意不请求挑战、不上传 .sb3、更不调用 /complete：这些动作都属于 Studio / 后端。
// 课时 DTO 已经过课程访问和顺序解锁裁决，组件只渲染其中的服务器状态并带着非敏感上下文
// 打开同域工作台。Studio 提交后必须回到 /learn/:lessonId?block=:blockId&refresh=1，
// 由 LessonPlayer 重取权威进度，而不是让 URL 或浏览器声称“已通过”。
//
// 两个“交完才开放”的复盘资源（解析视频、示范项目）同理：显示与否只看 DTO 里的
// analysis_available / demo_available，组件不自己推断“应该可以看了吧”。示范项目的
// .sb3 地址压根不在 DTO 里，服务端在下发时会再跑一次同一套门控。
import { computed } from "vue";
import LessonIcon from "../LessonIcon.vue";
import VideoPlayer from "../../VideoPlayer.vue";

const props = defineProps({
  block: { type: Object, required: true },
  lessonId: { type: Number, required: true },
});

const emit = defineEmits(["toast"]);

const scratch = computed(() => props.block.scratch || {});
const challengeId = computed(() => scratch.value.challenge_id ?? props.block.challenge_id ?? null);
const rawStatus = computed(() =>
  String(scratch.value.submission_status || props.block.submission_status || "").toLowerCase(),
);
const state = computed(() => {
  if (props.block.completed || rawStatus.value === "passed") return "passed";
  if (rawStatus.value === "returned") return "returned";
  if (["evaluating", "queued", "submitted", "pending", "needs_review"].includes(rawStatus.value))
    return "evaluating";
  if (["failed", "needs_revision", "rejected"].includes(rawStatus.value)) return "retry";
  if (["saved", "draft", "in_progress"].includes(rawStatus.value)) return "saved";
  return "new";
});

const stateCopy = computed(() => {
  const copies = {
    new: ["开始创作", "打开工作台，完成本关的 Scratch 编程任务。"],
    saved: ["作品已保存", "可以继续编辑，完成后在工作台内提交。"],
    evaluating: ["正在判定", "服务器正在检查本次提交，请稍候刷新结果。"],
    retry: ["还需要调整", scratch.value.feedback || "根据反馈修改作品后再次提交。"],
    passed: ["本关已通过", "服务器已确认本关完成，可以继续学习或再次打开作品复习。"],
    // 退回重做 ≠ 未通过：这是老师看过之后让你再改一版，不是机器判的。
    returned: [
      "老师让你改一改",
      scratch.value.feedback || "这一关的进度已经记上了，老师希望你再改一版交上来。",
    ],
  };
  return copies[state.value];
});

// studio_url 由部署端下发时可覆盖默认路径；仍只允许同源相对路径，避免内容块把学生
// 导向任意外站。后端无配置时，WorkBuddy 子应用默认挂载在 /scratch-studio/。
const studioBase = computed(() => {
  const configured = scratch.value.studio_url;
  return typeof configured === "string" && configured.startsWith("/")
    ? configured
    : "/scratch-studio/";
});

function studioUrl(extra = {}) {
  const base = studioBase.value;
  const query = new URLSearchParams({
    lesson_id: String(props.lessonId),
    block_id: String(props.block.id),
    ...extra,
  });
  return `${base}${base.includes("?") ? "&" : "?"}${query.toString()}`;
}

const studioHref = computed(() => studioUrl());

// 示范项目入口。开放与否只信服务端的 demo_available（课时门控 + 一次终态提交），
// 这里不看 state 也不看 block.completed——判定中和只保存都不该放行，而那两个本地
// 状态推不出这件事。打开的是只读 Studio，服务端在下发 .sb3 时会再判一次。
const demoHref = computed(() => studioUrl({ mode: "student_demo" }));
const demoAvailable = computed(() => Boolean(scratch.value.demo_available));
const demoPending = computed(() => Boolean(scratch.value.has_demo) && !demoAvailable.value);

const analysisPlayPath = computed(() =>
  `/api/scratch/lesson-blocks/${props.block.id}/analysis-play`,
);

function unavailable(event) {
  if (challengeId.value) return;
  event.preventDefault();
  emit("toast", "该 Scratch 任务尚未配置，暂时不能进入工作台。");
}
</script>

<template>
  <section class="block-scratch" aria-labelledby="scratch-title">
    <div class="scratch-mark" aria-hidden="true"><LessonIcon name="practice" :size="24" /></div>
    <div class="scratch-copy">
      <p class="leyebrow">SCRATCH 编程挑战</p>
      <h3 id="scratch-title">{{ stateCopy[0] }}</h3>
      <p>{{ stateCopy[1] }}</p>
      <p v-if="scratch.instructions_summary" class="scratch-summary">
        {{ scratch.instructions_summary }}
      </p>
      <div class="scratch-meta">
        <span class="ltag" :class="`is-${state}`">
          {{
            state === "passed"
              ? "已通过"
              : state === "returned"
                ? "已退回重做"
                : state === "evaluating"
                  ? "判定中"
                  : state === "retry"
                    ? "待修改"
                    : state === "saved"
                      ? "已保存"
                      : "未开始"
          }}
        </span>
        <span v-if="scratch.attempt_count != null" class="ltag"
          >已提交 {{ scratch.attempt_count }} 次</span
        >
      </div>
      <div class="scratch-actions">
        <a class="lbtn lbtn-chunky lbtn-accent" :href="studioHref" @click="unavailable">
          <LessonIcon name="arrowRight" :size="14" />{{
            state === "returned"
              ? "打开工作台改一改"
              : state === "passed"
                ? "查看作品"
                : "打开编程工作台"
          }}
        </a>
        <a v-if="demoAvailable" class="lbtn lbtn-chunky" :href="demoHref">
          <LessonIcon name="practice" :size="14" />查看示范项目
        </a>
        <span v-if="state === 'evaluating'" class="hint">判定完成后返回本课时即可看到结果</span>
      </div>
      <section v-if="scratch.analysis_available" class="scratch-analysis" aria-label="教师解析视频">
        <div class="scratch-analysis-heading">
          <strong>教师解析</strong>
          <span>已提交后可观看；用于复盘思路，不会影响本次得分。</span>
        </div>
        <VideoPlayer :lesson-id="lessonId" :play-path="analysisPlayPath" />
      </section>
      <p v-else-if="scratch.has_analysis_video" class="scratch-analysis-hint">
        教师已准备解析视频，提交作品并得到结果后可观看。
      </p>
      <!-- 提交前只说"有这么一份"，不给入口也不给地址：示范项目就是答案。 -->
      <p v-if="demoPending" class="scratch-analysis-hint">
        教师已准备示范项目，提交作品并得到结果后可只读查看。
      </p>
    </div>
  </section>
  <!-- 与作业块一致：壳负责实际的上一块/下一块导航。最后一块是否允许完成仍由
       LessonPlayer 根据 block.completed（服务器状态）裁决，不能在这里绕过。 -->
  <div class="block-foot">
    <slot name="prev" />
    <slot name="next" />
    <span class="hint">{{
      state === "passed"
        ? "本块已完成"
        : state === "returned"
          ? "老师看过你的作品，改一改再交一次"
          : "请在工作台内提交并通过本关"
    }}</span>
  </div>
</template>

<style scoped>
.block-scratch {
  display: flex;
  gap: 18px;
  align-items: flex-start;
  padding: 24px;
  border: 1px solid color-mix(in srgb, var(--blue, #4f8cff) 30%, #fff);
  border-radius: 20px;
  background: linear-gradient(135deg, #f3f8ff, #fff9ee);
}
.scratch-mark {
  display: grid;
  flex: 0 0 48px;
  width: 48px;
  height: 48px;
  place-items: center;
  color: #fff;
  border-radius: 15px;
  background: linear-gradient(135deg, #ff9f1c, #ff6b35);
}
.scratch-copy {
  min-width: 0;
}
.scratch-copy h3 {
  margin: 2px 0 8px;
  font-size: 21px;
}
.scratch-copy p {
  margin: 0;
  color: var(--muted, #64748b);
  line-height: 1.7;
}
.scratch-summary {
  margin-top: 10px !important;
}
.scratch-meta,
.scratch-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 14px;
}
.scratch-analysis {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid color-mix(in srgb, var(--blue, #4f8cff) 20%, #fff);
}
.scratch-analysis-heading {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: baseline;
  margin-bottom: 10px;
}
.scratch-analysis-heading span,
.scratch-analysis-hint {
  color: var(--muted, #64748b);
  font-size: 13px;
}
.scratch-analysis-hint {
  margin-top: 16px !important;
}
.ltag.is-passed {
  color: #0b7a4b;
  background: #e8fff2;
}
.ltag.is-evaluating {
  color: #8a5600;
  background: #fff4d7;
}
.ltag.is-retry {
  color: #b83c3c;
  background: #fff0f0;
}
.ltag.is-returned {
  color: #8a5600;
  background: #fff4d7;
}
.ltag.is-saved {
  color: #245aa8;
  background: #edf5ff;
}
@media (max-width: 560px) {
  .block-scratch {
    padding: 18px;
    gap: 13px;
  }
  .scratch-mark {
    flex-basis: 40px;
    width: 40px;
    height: 40px;
    border-radius: 13px;
  }
}
</style>
