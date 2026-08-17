<script setup>
// 课程导航抽屉（交接文档 14 §3.4）。
//
// 两种形态都实现，用户偏好存 localStorage：
//   list     清单（默认）
//   timeline 时间轴（轴线 + 轴点，强调线性推进）
//
// 锁的可点性按 lock_reason 分（§4.5）：
//   not_enrolled 权限锁 → **可点**，点进去看开通引导，这是转化路径
//   sequential   顺序锁 → 不可点，点了也没有可做的事
import { computed } from "vue";
import LessonIcon from "./LessonIcon.vue";

const props = defineProps({
  lesson: { type: Object, required: true },
  currentId: { type: [Number, null], default: null },
  // 形态：list | timeline。**不能叫 style**——那是 Vue 的保留属性，
  // `:style="..."` 会被当成内联样式绑定，prop 永远收不到值。
  variant: { type: String, default: "list" },
});
const emit = defineEmits(["go", "toggle-style", "cert"]);

const progress = computed(() => props.lesson.progress || { total: 0, done: 0, percent: 0 });
const blocks = computed(() => props.lesson.blocks || []);
const allDone = computed(
  () => progress.value.total > 0 && progress.value.done >= progress.value.total,
);

function stateOf(block) {
  if (block.completed) return "done";
  if (block.id === props.currentId) return "current";
  if (block.lock_reason) return "lock";
  return "todo";
}
function lockIcon(block) {
  return block.lock_reason === "not_enrolled" ? "lock" : "steps";
}
function lockTip(block) {
  if (block.lock_reason === "not_enrolled") return "需要开通课包";
  if (block.lock_reason === "sequential") return "完成前面的内容块后解锁";
  return "";
}
function clickable(block) {
  return block.lock_reason !== "sequential";
}
</script>

<template>
  <aside class="lesson-drawer" aria-label="课程导航">
    <div class="drawer-head">
      <div class="dh-row">
        <span class="dh-title">{{ lesson.title }}</span>
        <span class="lspacer"></span>
        <button class="style-toggle" type="button" @click="emit('toggle-style')">
          {{ variant === "timeline" ? "清单" : "时间轴" }}
        </button>
      </div>
      <div class="dh-meta">
        <span
          >已完成 <b>{{ progress.done }}/{{ progress.total }}</b></span
        >
        <span class="lspacer"></span>
        <span class="ltag" :class="{ 'on-accent': allDone }">{{ progress.percent }}%</span>
      </div>
      <div class="lin-bar"><i :style="{ transform: `scaleX(${progress.percent / 100})` }"></i></div>
    </div>

    <div class="drawer-list">
      <div :class="variant === 'timeline' ? 'nav-timeline' : 'nav-list'">
        <button
          v-for="(block, i) in blocks"
          :key="block.id ?? `legacy-${block.sort_order}`"
          type="button"
          class="nav-item"
          :class="{
            'is-current': block.id === currentId,
            'is-locked': !!block.lock_reason,
            'is-done': block.completed,
          }"
          :title="lockTip(block)"
          :disabled="!clickable(block)"
          :aria-current="block.id === currentId ? 'true' : undefined"
          @click="emit('go', block.id)"
        >
          <span v-if="variant === 'timeline'" class="axis-dot" :class="`is-${stateOf(block)}`">
            <LessonIcon v-if="block.completed" name="check" :size="11" />
            <LessonIcon v-else-if="block.lock_reason" :name="lockIcon(block)" :size="10" />
          </span>
          <span class="nav-no">{{ String(i + 1).padStart(2, "0") }}</span>
          <span class="nav-ico"><LessonIcon :name="block.block_type" :size="15" /></span>
          <span class="nav-name">{{ block.title || "未命名内容块" }}</span>
          <span v-if="variant !== 'timeline'" class="nav-state">
            <span v-if="block.completed" class="st-done"
              ><LessonIcon name="check" :size="14"
            /></span>
            <span v-else-if="block.lock_reason" class="st-lock">
              <LessonIcon :name="lockIcon(block)" :size="13" />
            </span>
          </span>
        </button>
      </div>
    </div>

    <div class="drawer-foot">
      <button class="foot-link" type="button" :disabled="!allDone" @click="emit('cert')">
        <LessonIcon name="cert" :size="15" />查看结业证书
      </button>
    </div>
  </aside>
</template>
