<script setup>
// 一次提交判题的详情：摘要条 → 测试点卡片网格 → 当次代码。
//
// 提交判题后的主反馈和历史记录里点开的详情是同一个组件——两处如果各写一套，
// 迟早出现「刚才提交时说 25 分，翻记录变成 0 分」这种不可能排查的错觉。
import { computed } from "vue";
import { casesVisible, metricText, verdictOf } from "../../services/verdict";

const props = defineProps({
  submission: { type: Object, required: true },
  // 满分条件=编译通过的题不跑测试点，只出编译横幅
  compileOnly: { type: Boolean, default: false },
});
const emit = defineEmits(["copied"]);

const verdict = computed(() => verdictOf(props.submission.status));
const visible = computed(() => casesVisible(props.submission));
const cases = computed(() => (visible.value ? props.submission.cases : []));
const codeLength = computed(() => new Blob([props.submission.code || ""]).size);

async function copyCode() {
  try {
    await navigator.clipboard.writeText(props.submission.code || "");
    emit("copied", "代码已复制");
  } catch {
    emit("copied", "浏览器拒绝了剪贴板访问，请手动选中复制");
  }
}
</script>

<template>
  <div>
    <div class="hist-summary">
      <div>
        <div class="k">状态</div>
        <div
          class="v is-big"
          :class="submission.status === 'accepted' ? 'is-ok' : 'is-bad'"
          data-testid="verdict-abbr"
        >
          {{ verdict.abbr }}
        </div>
      </div>
      <div>
        <div class="k">得分</div>
        <div class="v is-big">{{ "score" in submission ? submission.score + " 分" : "—" }}</div>
      </div>
      <div>
        <div class="k">运行时间</div>
        <div class="v">{{ metricText(submission.time_ms, "ms") }}</div>
      </div>
      <div>
        <div class="k">运行内存</div>
        <div class="v">{{ metricText(submission.memory_kb, "KB") }}</div>
      </div>
      <div>
        <div class="k">代码长度</div>
        <div class="v">{{ codeLength }}B</div>
      </div>
    </div>

    <!-- 编译通过型：只出编译横幅，不渲染测试点。学员看到「全错却满分」会以为系统坏了。 -->
    <template v-if="compileOnly">
      <div class="verdict-banner" :class="submission.status === 'compile_error' ? 'v-ce' : 'v-ac'">
        <span class="v-name">
          {{ submission.status === "compile_error" ? "✗ 编译失败" : "✓ 编译通过" }}
        </span>
        <span>本题以编译通过为满分条件，不运行测试点</span>
      </div>
      <div v-if="submission.compile_message" class="compile-msg">
        {{ submission.compile_message }}
      </div>
    </template>

    <template v-else>
      <template v-if="submission.status === 'compile_error'">
        <h4 style="font-size: 12px; margin: 0 0 6px">编译错误信息</h4>
        <div class="compile-msg">
          {{ submission.compile_message || "（编译器没有给出更多信息）" }}
        </div>
      </template>

      <p v-else-if="!visible" class="mono-dim" data-testid="cases-hidden">
        本场考试暂不显示逐测试点结果，以最终成绩为准。
      </p>

      <template v-else-if="cases.length">
        <h4 style="font-size: 12px; margin: 0 0 6px">测试点详情</h4>
        <!-- 样例实线框、隐藏点虚线框；隐藏点只有状态，连字段都是 null。 -->
        <div class="case-cards">
          <div
            v-for="item in cases"
            :key="item.index"
            class="case-card"
            :class="[`cc-${item.status}`, { 'is-hidden': !item.is_sample }]"
          >
            <!-- 后端的 index 从 0 起（judge 层 enumerate），给人看的编号要 +1。 -->
            <div class="cc-name">{{ item.is_sample ? "样例" : "隐藏点" }} {{ item.index + 1 }}</div>
            <div class="cc-verdict">{{ verdictOf(item.status).abbr }}</div>
            <div class="cc-meta">{{ item.time_ms }}ms/{{ item.memory_kb }}KB</div>
          </div>
        </div>
      </template>
    </template>

    <div class="code-head">
      <h4>当次代码</h4>
      <button class="btn btn-sm" type="button" @click="copyCode">复制代码</button>
    </div>
    <pre class="code-view">{{ submission.code || "（这次提交没有留下代码）" }}</pre>
  </div>
</template>
