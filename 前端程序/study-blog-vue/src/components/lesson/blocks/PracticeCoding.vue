<script setup>
// 课中练习 · 单题编程题（形态 B「块内工作区」，交接文档 15 §4 / 文档 18 §3.1）。
//
// **直接挂考试页的 QuestionCoding**——它本身就是设计稿 3 那一屏（题面栏拖宽 +
// CodeMirror + 控制台 + 字号三档 + 判题六判定），而且不认 attempt、不认考试。
// 本组件只做适配：把它的 run 事件接到课时侧的两条链路上。
//
// **两条链路，别混**（这是本文件唯一需要记住的事）：
//   kind="trial"  → POST …/run     跑样例或自填输入，不计分、不计次、不写完成度；
//   kind="submit" → POST …/submit  跑**全部**测试点，计分、计次、判完写完成度。
// 隐藏测试点只在第二条里参与判题，且它的输入/期望/实际服务端一律不下发——
// 前端拿到的就是一排只有状态的行，这是设计而不是缺陷。
//
// 计分提交曾经写着"依赖 X1，本期不做"，直接 reject 掉。X1（attempt_source）早就
// 落地了，而单题块**没有走 PaperAttempt**：判定写回 lesson_problem_attempts，
// 与客观题共用同一张作答表（理由见后端 lesson_practice.submit_lesson_code）。
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { request } from "../../../services/auth";
import { createAutosave } from "../../../composables/useAutosave";
import QuestionCoding from "../../exam/QuestionCoding.vue";

const props = defineProps({
  question: { type: Object, required: true },
  blockId: { type: Number, required: true },
  lessonId: { type: Number, required: true },
  // 次数用尽后只锁提交，不锁运行——调试是学习的一部分。
  canAnswer: { type: Boolean, default: true },
  triesLeft: { type: Number, default: null },
});
const emit = defineEmits(["toast", "graded"]);

// QuestionCoding 要的 question 形状：sub_type / programming / stem。
// 课时侧 DTO 没有 problem_id_no（保密红线），它只被用作切题的 watch 键——
// 单题块里换块会整个重挂组件，用不上，给 uid 兜底即可。
const codingQuestion = computed(() => ({
  ...props.question,
  problem_id_no: props.question.uid,
}));

const base = computed(() => `/api/lessons/${props.lessonId}/blocks/${props.blockId}`);

const note = computed(() => {
  if (!props.canAnswer) return "作答次数已用完，仍可运行调试，但成绩不再更新";
  if (props.triesLeft != null) return `代码自动保存 · 还可提交 ${props.triesLeft} 次，取最后一次`;
  return "代码自动保存 · 成绩以最后一次「提交判题」为准";
});

/* ---------------- 草稿：写了就不能丢 ---------------- */
//
// 课时页的练习块**不在 keep-alive 白名单里**（LessonPlayer 只缓存资料块），切块必然
// 销毁编辑器。以前这个 draft-change 事件没人接，于是"切到下一块再切回来，代码没了"。
// 存服务端而不是 localStorage：这是带权限的私有内容，落磁盘会活过登出
// （services/prefetch.js 开头那条纪律）。
const autosave = createAutosave({
  save: (_key, payload) =>
    request(`${base.value}/draft`, { method: "PUT", body: JSON.stringify(payload) }),
});

function onDraftChange({ language, code }) {
  autosave.schedule(props.blockId, { language, code }).catch(() => {
    // 草稿存不上不该打断写代码：真要提交时 submit 带着完整代码走，丢不了。
  });
}

// 切块（组件销毁）前把最后一次改动冲出去。**不能 cancelAll**——学生最容易在
// 主动离开时丢掉刚写的东西，而防抖窗口正好是 1.5 秒。
onBeforeUnmount(() => {
  autosave.flushAll().catch(() => {});
});
watch(
  () => props.blockId,
  () => autosave.flushAll().catch(() => {}),
);

/* ---------------- 运行 / 提交 ---------------- */

/**
 * 落一条 run/submit → 轮询到终态。
 * 与 exam.js 的 runCodeAndWait 同一套节奏（250ms 轮询、120s 上限、signal 可掐断）——
 * 判题是异步的，切走之后还在打接口纯属浪费。
 */
async function judgeOnce(path, body, { signal, onProgress }) {
  const queued = await request(`${base.value}${path}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  onProgress?.(queued);
  if (queued.done) return queued;

  const deadline = Date.now() + 120_000;
  for (;;) {
    if (signal?.aborted) throw new Error("已取消。");
    await new Promise((r) => setTimeout(r, 250));
    if (signal?.aborted) throw new Error("已取消。");
    const current = await request(`${base.value}/runs/${queued.run_id}`);
    onProgress?.(current);
    if (current.done) return current;
    if (Date.now() > deadline) {
      throw new Error("判题超时未返回结果，请稍后重试。");
    }
  }
}

/** QuestionCoding 把 run 包成了 emit + resolve/reject，这里照它的契约回话。 */
async function onRun(payload) {
  const { resolve, reject, kind, customInput, language, code, signal, onProgress } = payload;
  try {
    if (kind === "submit") {
      // 提交前先把草稿冲干净：提交带的是完整代码，但草稿要跟着对上，
      // 否则判题期间刷新页面会拿回一份更旧的代码。
      await autosave.flushAll().catch(() => {});
      const result = await judgeOnce("/submit", { language, code }, { signal, onProgress });
      resolve?.(result);
      // 判完才通知外层：成绩、次数、完成度、后续块的解锁状态全在这一刻变。
      emit("graded", result);
      return;
    }
    resolve?.(
      await judgeOnce(
        "/run",
        {
          language,
          code,
          scope: customInput == null ? "samples" : "custom",
          custom_input: customInput ?? null,
        },
        { signal, onProgress },
      ),
    );
  } catch (error) {
    reject?.(error);
  }
}
</script>

<template>
  <QuestionCoding
    :question="codingQuestion"
    :allow-history="false"
    :submit-disabled="!canAnswer"
    :note="note"
    @run="onRun"
    @draft-change="onDraftChange"
    @toast="emit('toast', $event)"
  />
</template>
