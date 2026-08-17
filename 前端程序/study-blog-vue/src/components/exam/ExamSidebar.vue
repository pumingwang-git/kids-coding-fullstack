<script setup>
// 题卡侧栏：作答进度 + 答题卡。
//
// 宫格按题型分组（组头带 已答/总数），而不是原来那排「全部题目 / 单选题 / 多选题…」
// 的题型过滤按钮——236px 的栏里放五个整行按钮太占地方，分组组头能给出同样的
// 「这一类做完没有」信息，还顺带把定位也解决了。过滤开关是 全部 / 未答 / 标记。
import { computed, nextTick, ref, watch, useTemplateRef } from "vue";
import { QUESTION_TYPE_TEXT } from "../../services/exam";

const props = defineProps({
  questions: { type: Array, default: () => [] },
  currentIndex: { type: Number, default: 0 },
  answeredKeys: { type: Object, required: true }, // Set of problem_id_no
  markedKeys: { type: Object, default: () => new Set() }, // Set of problem_id_no
  playful: { type: Boolean, default: true },
});
const emit = defineEmits(["select"]);

// 20 题以内整张摊开；再多就切紧凑模式（每行 7 个、26px 格、容器内部滚动），
// 否则百题卷的宫格能把左栏顶出三屏。
const COMPACT_THRESHOLD = 20;

const filter = ref("all"); // all / unanswered / marked
const folded = ref(new Set()); // 折叠起来的题型
const scroller = useTemplateRef("scroller");

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "unanswered", label: "未答" },
  { key: "marked", label: "标记" },
];

const compact = computed(() => props.questions.length > COMPACT_THRESHOLD);

// 题号始终是全卷序号——否则学员在过滤后看到的"第 3 题"和交卷提示里的不是同一道。
const indexed = computed(() => props.questions.map((item, index) => ({ ...item, index })));
const answeredCount = computed(
  () => indexed.value.filter((item) => props.answeredKeys.has(item.problem_id_no)).length,
);
const unansweredCount = computed(() => props.questions.length - answeredCount.value);
const percent = computed(() =>
  props.questions.length ? Math.round((answeredCount.value / props.questions.length) * 100) : 0,
);

function isAnswered(item) {
  return props.answeredKeys.has(item.problem_id_no);
}
function isMarked(item) {
  return props.markedKeys.has(item.problem_id_no);
}

const markedCount = computed(() => indexed.value.filter(isMarked).length);
const counts = computed(() => ({
  all: props.questions.length,
  unanswered: unansweredCount.value,
  marked: markedCount.value,
}));

function passFilter(item) {
  if (filter.value === "unanswered") return !isAnswered(item);
  if (filter.value === "marked") return isMarked(item);
  return true;
}

const groups = computed(() =>
  Object.keys(QUESTION_TYPE_TEXT)
    .map((type) => {
      const all = indexed.value.filter((item) => item.type === type);
      return {
        type,
        label: QUESTION_TYPE_TEXT[type],
        total: all.length,
        done: all.filter(isAnswered).length,
        items: all.filter(passFilter),
      };
    })
    .filter((group) => group.total),
);

const emptyText = computed(() => (filter.value === "marked" ? "这一类没有标记" : "这一类都答完了"));

function toggleFold(type) {
  const next = new Set(folded.value);
  if (next.has(type)) next.delete(type);
  else next.add(type);
  folded.value = next;
}

// 百题卷里当前题很可能滚在容器外，切题后拉回视野；块内滚动用 nearest，
// 免得每切一题整页都跳一下。
watch(
  () => props.currentIndex,
  async () => {
    if (!compact.value) return;
    await nextTick();
    scroller.value?.querySelector(".qchip.is-current")?.scrollIntoView({ block: "nearest" });
  },
);
</script>

<template>
  <aside class="exam-rail">
    <section class="panel">
      <div class="panel-head">
        <h2>作答进度</h2>
        <span class="sub">{{ answeredCount }} / {{ questions.length }}</span>
      </div>
      <div class="panel-body">
        <div class="progress-track">
          <!-- scaleX 而不是 width：动画 width 每帧都要重排（见 exam.css 该类的注释） -->
          <div class="progress-fill" :style="{ transform: `scaleX(${percent / 100})` }" />
        </div>
        <div class="legend">
          <span><i class="l-done" />已答</span>
          <span><i />未答</span>
          <span><i class="l-mark" />标记</span>
          <span><i class="l-cur" />当前</span>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>答题卡</h2>
        <span class="sub">{{ compact ? "紧凑" : "" }}</span>
      </div>

      <div class="filter-row" role="group" aria-label="答题卡过滤">
        <button
          v-for="item in FILTERS"
          :key="item.key"
          type="button"
          class="filter-btn"
          :class="{ 'is-on': filter === item.key }"
          :aria-pressed="filter === item.key"
          :data-filter="item.key"
          @click="filter = item.key"
        >
          {{ item.label }}<span class="cnt">{{ counts[item.key] }}</span>
        </button>
      </div>

      <div ref="scroller" class="panel-body card-scroll" :class="{ 'is-compact': compact }">
        <div v-for="group in groups" :key="group.type" class="card-group">
          <button
            type="button"
            class="group-name"
            :aria-expanded="!folded.has(group.type)"
            @click="toggleFold(group.type)"
          >
            <span>{{ group.label }}</span>
            <span>
              {{ group.done }}/{{ group.total }}
              <span class="fold">{{ folded.has(group.type) ? "▸" : "▾" }}</span>
            </span>
          </button>
          <div v-if="!folded.has(group.type)" class="card-grid">
            <button
              v-for="item in group.items"
              :key="item.problem_id_no"
              type="button"
              class="qchip"
              :class="{
                'is-current': item.index === currentIndex,
                'is-done': isAnswered(item) && item.index !== currentIndex,
                'is-marked': isMarked(item),
              }"
              :title="`第 ${item.index + 1} 题 · ${group.label}${isMarked(item) ? ' · 已标记' : ''}`"
              :aria-current="item.index === currentIndex ? 'true' : undefined"
              @click="emit('select', item.index)"
            >
              {{ item.index + 1 }}
            </button>
            <span v-if="!group.items.length" class="card-empty">{{ emptyText }}</span>
          </div>
        </div>
      </div>
    </section>

    <p v-if="playful" class="side-note cheer">答完每一题，离满分就更近一步。</p>
  </aside>
</template>
