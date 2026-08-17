<script setup>
// 编程题工作区：左题面 / 右编辑器 + 控制台 + 操作条，整块锁在视口高度里，
// 两栏各自内部滚动。页面本身不滚——学员改到第 80 行时不该还要先把页面拉回去
// 才能点到「提交判题」。
//
// 只有两个动作：「▶ 运行」不计分（stdin 来自样例或学员自己），「提交判题」跑全部
// 测试点并固化成绩。这两者分得很开是有意的——参考 DEMO 用前端子串匹配判过关，
// 那在真实考试里等于改一行前端就能拿满分。这里前端不做任何判定，一切以服务端返回为准。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { EditorView, basicSetup } from "codemirror";
import { keymap } from "@codemirror/view";
import { indentWithTab } from "@codemirror/commands";
import { EditorState } from "@codemirror/state";
import { indentRange } from "@codemirror/language";
import { cpp } from "@codemirror/lang-cpp";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import {
  casesVisible,
  isCompileOnly,
  isPending,
  metricText,
  splitDiff,
  verdictOf,
} from "../../services/verdict";
import ExamModal from "./ExamModal.vue";
import MarkdownBody from "./MarkdownBody.vue";
import SubmissionDetail from "./SubmissionDetail.vue";

const props = defineProps({
  question: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  submissionCount: { type: Number, default: 0 },
  // false = 只给「▶ 运行」，隐藏计分提交（比如题目还没配测试点的场景）
  allowSubmit: { type: Boolean, default: true },
  // 提交记录弹窗是考试页独有的（按 attempt 查历史提交）。课时页有计分提交、
  // 但没有 attempt，也就没有这份历史——两个开关必须分开，否则课时页要么
  // 丢掉提交、要么挂一个点了必然报错的按钮。
  allowHistory: { type: Boolean, default: true },
  // 次数用完时只禁用提交、不禁用运行：调试是学习的一部分，不该跟着一起锁死。
  submitDisabled: { type: Boolean, default: false },
  // 操作条右侧那句说明。给了就用调用方的，没给按 allowSubmit / compileOnly 兜底。
  note: { type: String, default: "" },
});
const emit = defineEmits(["run", "history", "toast", "draft-change"]);

// 字号三档。记 localStorage 是因为这是个人视力偏好，不该每进一道题就重设一次。
const FONT_SIZES = [12, 13.5, 15];
const FONT_KEY = "exam.editor.fontIndex";
const CONSOLE_MIN = 80;
const CONSOLE_MAX = 320;
// 题面栏的可拖范围。下限保证题干还读得成句；上限由当前容器实宽动态计算。
const DESC_MIN = 220;
// 分隔条宽度与编辑器的最低可用宽度，与 question.css 的 grid-template-columns 同源。
// 拖拽夹紧要按**容器实宽**再算一次上限：课时页的可用宽度会变（开合课程导航抽屉
// 一次就是 300px），不能再用固定像素上限，否则抽屉关闭后分隔条无法继续向右调整。
const COL_GAP = 7;
const EDITOR_MIN = 320;

const wrap = ref(null);
const host = ref(null);
const desc = ref(null);
const view = shallowRef(null);
const code = ref(props.question.last_code || "");
const result = ref(props.question.last_submission || null);

// 控制台两页签。「运行」把样例试跑和自测并成一件事——它们本来就是同一个后端调用
// （kind="trial"、同一个 exam-judge 限流桶、都不计分），差别只在 stdin 从哪来。
// 真正需要学员分清的只有「不计分的运行」和「计分的提交判题」。
const tab = ref("run"); // run / result
const inputSource = ref("sample"); // sample / custom
const runOut = ref(null); // 上一次运行的结果
const runFrom = ref("sample"); // 那次结果是哪种输入源跑出来的，决定怎么渲染
const runBusy = ref(false);
const runError = ref("");

const collapsed = ref(false);
const consoleHeight = ref(190);
// null = 还没拖过，走 CSS 里的 5fr : 7fr 默认比例（窄屏下才好自适应）。
// 拖过之后才切成固定 px。
const descWidth = ref(null);
const focusMode = ref(false);
const fontIndex = ref(readFontIndex());
const expanded = ref(new Set()); // 判题结果里展开对比的样例序号

const customInput = ref("");
const submitError = ref(""); // 判题服务不可用等，与「答案错误」严格分开
const progress = ref(null); // 轮询中的中间态：queued / judging
const submitDetail = ref(null); // 本次计分提交完成后才打开的考试同款结果弹窗
const shortcutsOpen = ref(false);
let aborter = null; // 切题或卸载时掐断轮询
let pendingChord = null;
let chordTimer = null;

const language = props.question.sub_type === "cpp" ? "cpp" : "python";
const detail = computed(() => props.question.programming || {});
const samples = computed(() => detail.value.samples || []);
const compileOnly = computed(() => isCompileOnly(props.question));

// 限制条：逐点限制存在时后端只下发聚合范围 [min, max]（不下发逐条明细，防止暴露
// “第 7 个测试点特别重”这类信息）。max ≠ min 渲染成范围，相等/无范围仍是单值。
const timeLimitText = computed(() => {
  const range = detail.value.time_limit_range;
  if (Array.isArray(range) && range.length === 2 && range[0] !== range[1]) {
    return `限时 ${range[0]}–${range[1]} ms`;
  }
  return `限时 ${detail.value.time_limit_ms ?? 1000} ms`;
});
const memoryLimitText = computed(() => {
  const range = detail.value.memory_limit_range;
  if (Array.isArray(range) && range.length === 2 && range[0] !== range[1]) {
    return `内存 ${range[0]}–${range[1]} MB`;
  }
  return `内存 ${detail.value.memory_limit_mb ?? 256} MB`;
});

const verdict = computed(() => verdictOf(result.value?.status));
const visible = computed(() => casesVisible(result.value));
const cases = computed(() => (visible.value ? result.value.cases : []));
const passedCount = computed(() => cases.value.filter((item) => item.passed).length);

// 编译通过型的题只有"编译过没过"两种结局，与判题器给的 status 不是一回事：
// 代码编译通过但测试点全错时 status 仍是 wrong_answer，而这题该判满分。
const compiled = computed(() => result.value?.status !== "compile_error");
const bannerClass = computed(() =>
  compileOnly.value ? (compiled.value ? "v-ac" : "v-ce") : verdict.value.banner,
);
const bannerTitle = computed(() => {
  if (compileOnly.value) return compiled.value ? "✓ 编译通过" : "✗ 编译失败";
  return `${result.value?.status === "accepted" ? "✓" : "✗"} ${verdict.value.text}`;
});

function readFontIndex() {
  // 没存过时必须落回中档 1。别省掉 stored === null 这一步——Number(null) 是 0，
  // 而 0 是合法档位，于是第一次打开的人拿到的是最小号字。
  const stored = localStorage.getItem(FONT_KEY);
  if (stored === null) return 1;
  const raw = Number(stored);
  return Number.isInteger(raw) && raw >= 0 && raw < FONT_SIZES.length ? raw : 1;
}

function stepFont(delta) {
  fontIndex.value = Math.min(FONT_SIZES.length - 1, Math.max(0, fontIndex.value + delta));
  localStorage.setItem(FONT_KEY, String(fontIndex.value));
}

// basicSetup 自带的搜索面板（Ctrl+F）文案是英文的，phrases 是 CodeMirror 官方的
// 翻译出口：key 必须和扩展源码里的英文原文一字不差，漏掉的项会原样保留英文。
// 带 $ 的是占位符（匹配数 / 行号），翻译时要保留。
const CM_ZH_PHRASES = EditorState.phrases.of({
  Find: "查找",
  Replace: "替换",
  next: "下一个",
  previous: "上一个",
  all: "选中全部",
  "match case": "区分大小写",
  "by word": "全词匹配",
  regexp: "正则表达式",
  replace: "替换",
  "replace all": "全部替换",
  close: "关闭",
  "current match": "当前匹配",
  "replaced $ matches": "已替换 $ 处匹配",
  "replaced match on line $": "已替换第 $ 行的匹配",
  "Go to line": "跳转到行",
  go: "跳转",
});

function buildState(doc) {
  return EditorState.create({
    doc,
    extensions: [
      // basicSetup 里已经带了折叠槽和 Ctrl+F 搜索面板，不用另外装扩展。
      keymap.of([
        { key: "Shift-Alt-f", run: formatDocument },
        { key: "Mod-Enter", run: submitFromShortcut, stopPropagation: true },
        indentWithTab,
      ]),
      basicSetup,
      CM_ZH_PHRASES,
      language === "cpp" ? cpp() : python(),
      oneDark,
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          code.value = update.state.doc.toString();
          emit("draft-change", { language, code: code.value });
        }
      }),
    ],
  });
}

// VS Code 的 Shift+Alt+F 在此专注于「整理缩进」：只按当前语言的语法树重排
// 每一行前导空白，不擅自改动代码内容、引号或风格规则。
function formatDocument(editor) {
  const changes = indentRange(editor.state, 0, editor.state.doc.length);
  if (changes.empty) return false;
  editor.dispatch({ changes });
  return true;
}

function submitFromShortcut() {
  if (!props.allowSubmit) {
    emit("toast", "本练习仅支持运行调试，不能提交判题");
  } else if (props.busy || props.submitDisabled) {
    emit("toast", "当前不能提交判题，请等待或检查作答次数");
  } else {
    runSubmit();
  }
  // 这个键位与 CodeMirror 默认的「插入空行」冲突，必须由本组件消费。
  return true;
}

onMounted(() => {
  view.value = new EditorView({ state: buildState(code.value), parent: host.value });
  observeWrap();
  window.addEventListener("keydown", onWorkspaceKeydown);
});
onBeforeUnmount(() => {
  view.value?.destroy();
  // 拖到一半切走的话，window 上的监听得跟着拆，否则组件销毁了还在改已死的 ref。
  stopActiveDrag?.();
  // 轮询同理：组件都没了还每 250ms 打一次接口，纯浪费。
  aborter?.abort();
  wrapObserver?.disconnect();
  clearTimeout(clampTimer);
  clearTimeout(chordTimer);
  window.removeEventListener("keydown", onWorkspaceKeydown);
});

function inWorkspace(event) {
  return wrap.value?.contains(event.target);
}

function isMod(event) {
  return event.ctrlKey || event.metaKey;
}

function resetChord() {
  pendingChord = null;
  clearTimeout(chordTimer);
}

function setChord(key) {
  pendingChord = key;
  clearTimeout(chordTimer);
  chordTimer = setTimeout(resetChord, 1200);
}

function toggleConsole() {
  focusMode.value = false;
  collapsed.value = !collapsed.value;
}

/**
 * 工作区级按键刻意只在焦点位于本题内时接管。编辑器原生的 Ctrl+F / Ctrl+H /
 * Ctrl+G / Ctrl+/ / Alt+↑↓ 仍由 CodeMirror 的 basicSetup 处理；这里不重复
 * 注册，避免抢走输入法或把浏览器常用键误变成判题操作。
 */
function onWorkspaceKeydown(event) {
  if (!inWorkspace(event)) return;

  const key = event.key.toLowerCase();
  if (pendingChord) {
    const chord = pendingChord;
    resetChord();
    if (!isMod(event)) return;
    if (chord === "k" && key === "s") {
      event.preventDefault();
      shortcutsOpen.value = !shortcutsOpen.value;
    } else if (chord === "k" && key === "z") {
      event.preventDefault();
      focusMode.value = !focusMode.value;
    }
    return;
  }

  if (isMod(event) && key === "k") {
    event.preventDefault();
    setChord("k");
    return;
  }
  if (isMod(event) && key === "`") {
    event.preventDefault();
    toggleConsole();
    return;
  }
  if (isMod(event) && event.key === "F5") {
    event.preventDefault();
    if (!props.busy && !runBusy.value) runOnce();
    return;
  }
}

/** 容器宽度变了就重新夹一次题面宽度，并让 CodeMirror 重新量。
 *
 * 两件事都必须做：
 *   夹紧——拖过之后题面是**固定像素**，容器一变窄（课时页开抽屉 −300px）编辑器那列
 *   就被挤没了，而 .prog-wrap 是 overflow:hidden，连滚动条都没有，编辑器直接消失；
 *   重新量——CodeMirror 只在自己改变时重排，容器宽度变化它不知道，行宽与点击命中
 *   位置会一直用旧的，表现就是"点一个地方光标落在另一个地方"。
 */
let wrapObserver = null;
let clampTimer = null;
function observeWrap() {
  if (typeof ResizeObserver === "undefined" || !wrap.value) return;
  wrapObserver = new ResizeObserver(() => {
    // 重新量每帧都要做（不做就会错位），它自带合并，很便宜。
    view.value?.requestMeasure();
    // 夹紧则要等宽度**稳定**下来再做。课时页的抽屉是 0.26s 过渡，动画中间帧的容器
    // 比终态更窄；每帧都夹的话，题面会被中间帧的下限一路压小，而我们又故意不把它
    // 撑回去（那会覆盖学员自己拖的选择）——表现就是"开合一次抽屉，题面莫名变窄一截"。
    clearTimeout(clampTimer);
    clampTimer = setTimeout(clampDesc, 120);
  });
  wrapObserver.observe(wrap.value);
}

/** 只在超界时回写，不主动把拖窄的题面撑回去。 */
function clampDesc() {
  if (descWidth.value == null) return;
  const clamped = clamp(descWidth.value, DESC_MIN, maxDescWidth());
  if (clamped !== descWidth.value) descWidth.value = clamped;
}

/** 题面栏当前允许的最大宽度：给编辑器保留最低可用宽度，分隔条仍可双向调整。 */
function maxDescWidth() {
  const total = wrap.value?.getBoundingClientRect().width || 0;
  if (total <= 0) return DESC_MIN;
  return Math.max(DESC_MIN, total - COL_GAP - EDITOR_MIN);
}

// 切题时组件被 key 重建，这里只处理"同一题回填了上次提交的代码"的情况。
watch(
  () => props.question.problem_id_no,
  () => {
    aborter?.abort(); // 上一题还在轮询就别轮了
    progress.value = null;
    code.value = props.question.last_code || "";
    result.value = props.question.last_submission || null;
    runOut.value = null;
    runError.value = "";
    submitError.value = "";
    submitDetail.value = null;
    customInput.value = "";
    expanded.value = new Set();
    view.value?.setState(buildState(code.value));
  },
);

// 专注模式和拖分隔条都会改变编辑器宽度，CodeMirror 得重新量一次才不会错位。
// requestMeasure 自己会合并到下一帧，拖拽时每像素调一次也不会卡。
watch([focusMode, descWidth], async () => {
  await nextTick();
  view.value?.requestMeasure();
});

function openTab(next) {
  tab.value = next;
  collapsed.value = false;
  // 专注模式下控制台是藏起来的。要往里写东西就得先把它露出来，否则「试跑样例」
  // 会变成点了没反应——输出确实产生了，只是学员看不见。
  focusMode.value = false;
}

function toggleExpand(index) {
  const next = new Set(expanded.value);
  if (next.has(index)) next.delete(index);
  else next.add(index);
  expanded.value = next;
}

function diffOf(item) {
  return splitDiff(item.expected, item.actual);
}

/** 统一的跑代码出口：把 emit 包成 Promise，错误一律回到调用方自己处理。
 *
 * 判题是异步的，所以这里还要往外递两样东西：onProgress 收中间态（排队位次），
 * signal 让上层在切题/卸载时掐断轮询——学员切走之后还在打接口是纯浪费。 */
function ask(payload) {
  aborter?.abort();
  aborter = new AbortController();
  progress.value = null;
  return new Promise((resolve, reject) => {
    emit("run", {
      ...payload,
      language,
      code: code.value,
      signal: aborter.signal,
      onProgress: (current) => {
        progress.value = current;
      },
      resolve,
      reject,
    });
  });
}

/** 「排队中 第 3 位」/「判题中…」。终态时返回 null，交给结果区渲染。 */
const pendingText = computed(() => {
  if (!isPending(progress.value)) return null;
  const ahead = progress.value.queue_position;
  if (progress.value.status === "queued" && typeof ahead === "number" && ahead > 0)
    return `排队中，前面还有 ${ahead} 个`;
  return progress.value.status === "queued" ? "排队中…" : "判题中…";
});

/** 「▶ 运行」：不计分地跑一次，stdin 来自样例还是自定义由输入源开关决定。 */
async function runOnce() {
  openTab("run");
  const source = inputSource.value;
  runBusy.value = true;
  runError.value = "";
  runOut.value = null;
  try {
    // 自定义时空串是合法的「用空 stdin 跑一次」，后端明确支持，这里不拦。
    runOut.value = await ask(
      source === "custom" ? { kind: "trial", customInput: customInput.value } : { kind: "trial" },
    );
    runFrom.value = source;
  } catch (error) {
    if (error.message !== "已取消。") runError.value = error.message;
  } finally {
    runBusy.value = false;
    progress.value = null;
  }
}

async function runSubmit() {
  openTab("result");
  submitError.value = "";
  try {
    const payload = await ask({ kind: "submit" });
    // 异步之后，沙箱故障不再是 HTTP 异常——那一刻只是排上队而已，故障是**轮询到的
    // judge_failed 终态**。只 catch 不看终态的话，判题挂了会安静地显示成一次判定。
    if (payload.status === "judge_failed") {
      submitError.value = payload.compile_message || "判题服务暂时不可用，请稍后重试。";
      return;
    }
    // 课中练习接口不会回传代码；详情弹窗与考试页共用 SubmissionDetail，补入本次代码
    // 才能让“当次代码”始终和本次测试点结果对应。
    const submission = { ...payload, code: code.value };
    result.value = submission;
    submitDetail.value = submission;
    expanded.value = new Set();
  } catch (error) {
    // 走到这里的是真的网络/权限错误（429 排队已满、409 已封卷等）。
    // 不能借用 WA 那套横幅——把系统故障说成「答案错误」是验收手册四级明令禁止的。
    if (error.message !== "已取消。") submitError.value = error.message;
  } finally {
    progress.value = null;
  }
}

function fillSample(index = 0) {
  customInput.value = samples.value[index]?.input ?? "";
}

async function copySample(text) {
  try {
    await navigator.clipboard.writeText(text);
    emit("toast", "样例输入已复制");
  } catch {
    emit("toast", "浏览器拒绝了剪贴板访问，请手动选中复制");
  }
}

/* ---- 两条分隔条：题面↔编辑器（横向）、编辑器↔控制台（纵向）---- */

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

// 拖拽期间监听挂在 window 上而不是分隔条上：指针一旦滑出那 7px 宽的条，
// 挂在条上的 move 就断了，手感会变成"拖一下丢一下"。
//
// 用 Pointer Events 而不是 mouse*：后者在触屏上完全不触发，平板与二合一设备上
// 这两条分隔条等于不存在。pointer 一套覆盖鼠标/触控/触控笔，代码还少一半。
let stopActiveDrag = null;

function drag(event, onMove) {
  event.preventDefault();
  stopActiveDrag?.();
  const move = (moved) => onMove(moved);
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
    stopActiveDrag = null;
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  // 触屏上手指被系统手势接管时只发 pointercancel，不补这条就会卡在拖拽态。
  window.addEventListener("pointercancel", up);
  stopActiveDrag = up;
}

function startRowDrag(event) {
  collapsed.value = false;
  const startY = event.clientY;
  const base = consoleHeight.value;
  drag(event, (moved) => {
    consoleHeight.value = clamp(base + (startY - moved.clientY), CONSOLE_MIN, CONSOLE_MAX);
  });
}

/** 拖拽起点：拖过就用记下的宽度，没拖过就量当前实宽；量不出来（元素还没布局）回落到下限。 */
function currentDescWidth() {
  if (descWidth.value) return descWidth.value;
  const measured = desc.value?.getBoundingClientRect().width || 0;
  // 别写成 ?? ——宽度量不出来时是 0 而不是 undefined，?? 兜不住，基准会变成 0，
  // 于是第一下拖拽会把题面直接甩到下限。
  return measured > 0 ? measured : DESC_MIN;
}

function startColDrag(event) {
  const startX = event.clientX;
  const base = currentDescWidth();
  const limit = maxDescWidth();
  drag(event, (moved) => {
    const distance = moved.clientX - startX;
    const next = base + distance;
    descWidth.value = clamp(next, DESC_MIN, limit);
  });
}

// 键盘也要能调：拖拽是鼠标专属，只给鼠标等于把键盘用户挡在门外。
function nudgeConsole(delta) {
  consoleHeight.value = clamp(consoleHeight.value + delta, CONSOLE_MIN, CONSOLE_MAX);
}

function nudgeDesc(delta) {
  const base = currentDescWidth();
  descWidth.value = clamp(base + delta, DESC_MIN, maxDescWidth());
}

/** 双击分隔条回到默认比例——拖歪了不用一点点挪回去。 */
function resetDesc() {
  descWidth.value = null;
}
</script>

<template>
  <!-- 拖过之后才改成固定像素列宽；专注模式下不能挂这个内联样式，
       否则它会盖掉 .is-focus 的单列布局（内联样式优先级高于类）。
       第三列的下限是 320px 而不是 0：写 minmax(0,1fr) 的话，容器一变窄
       （课时页开抽屉就 −300px）编辑器那列会被压到 0，而 .prog-wrap 是
       overflow:hidden——编辑器不是变窄，是整个消失，还没有滚动条能找回来。
       宁可溢出一点，也不能让主工作区归零。 -->
  <div
    ref="wrap"
    class="prog-wrap"
    :class="{ 'is-focus': focusMode }"
    :style="
      !focusMode && descWidth
        ? { gridTemplateColumns: `${descWidth}px ${COL_GAP}px minmax(${EDITOR_MIN}px, 1fr)` }
        : null
    "
  >
    <div ref="desc" class="prog-desc">
      <h3>{{ detail.title || "编程题" }}</h3>
      <div class="limit-chips">
        <span>{{ timeLimitText }}</span>
        <span>{{ memoryLimitText }}</span>
        <span>{{ language === "cpp" ? "C++" : "Python" }}</span>
        <span v-if="compileOnly" class="pass-cond">满分条件：编译通过</span>
      </div>

      <div class="desc-sec">
        <h4>题目描述</h4>
        <MarkdownBody :source="question.stem" />
      </div>
      <div v-if="detail.input_format" class="desc-sec">
        <h4>输入</h4>
        <MarkdownBody :source="detail.input_format" />
      </div>
      <div v-if="detail.output_format" class="desc-sec">
        <h4>输出</h4>
        <MarkdownBody :source="detail.output_format" />
      </div>
      <div v-if="samples.length" class="desc-sec">
        <h4>样例</h4>
        <div v-for="(sample, index) in samples" :key="index" class="sample-box">
          <div class="sample-head">
            <span>样例 {{ index + 1 }} · 输入</span>
            <button class="copy-btn" type="button" @click="copySample(sample.input)">
              复制输入
            </button>
          </div>
          <pre>{{ sample.input }}</pre>
          <div class="sample-head is-mid"><span>期望输出</span></div>
          <pre>{{ sample.output }}</pre>
        </div>
      </div>
      <div v-if="detail.hints && detail.hints !== '无'" class="desc-sec">
        <h4>提示</h4>
        <MarkdownBody :source="detail.hints" />
      </div>
    </div>

    <!-- 题面 ↔ 编辑器：双向调整，双击回默认比例，方向键左右微调。 -->
    <button
      class="divider-col"
      type="button"
      aria-label="调整题面宽度，左右方向键可微调，双击复位"
      data-testid="divider-col"
      @pointerdown="startColDrag"
      @dblclick="resetDesc"
      @keydown.left.prevent="nudgeDesc(-24)"
      @keydown.right.prevent="nudgeDesc(24)"
    />

    <div class="prog-right">
      <div class="editor-head">
        <span class="lang">{{ language === "cpp" ? "C++" : "Python" }}</span>
        <button
          class="tool-btn"
          type="button"
          title="减小字号"
          :disabled="fontIndex === 0"
          @click="stepFont(-1)"
        >
          A⁻
        </button>
        <button
          class="tool-btn"
          type="button"
          title="增大字号"
          :disabled="fontIndex === FONT_SIZES.length - 1"
          @click="stepFont(1)"
        >
          A⁺
        </button>
        <button
          class="tool-btn"
          :class="{ 'is-on': focusMode }"
          type="button"
          title="收起题面，编辑器占满"
          :aria-pressed="focusMode"
          @click="focusMode = !focusMode"
        >
          ⛶ 专注
        </button>
        <button
          class="tool-btn"
          type="button"
          title="查看快捷键（Ctrl+K Ctrl+S）"
          :aria-expanded="shortcutsOpen"
          aria-controls="coding-shortcuts"
          @click="shortcutsOpen = !shortcutsOpen"
        >
          快捷键
        </button>
        <span class="last-verdict">
          <template v-if="result">
            上次提交
            <span :class="result.status === 'accepted' ? 'ok' : 'bad'">
              {{ result.status === "accepted" ? "✓" : "✗" }} {{ verdict.text }}
            </span>
            <template v-if="'score' in result">· {{ result.score }} 分</template>
          </template>
          <template v-else>尚未提交判题</template>
        </span>
      </div>

      <div ref="host" class="editor-host" :style="{ fontSize: FONT_SIZES[fontIndex] + 'px' }" />

      <section
        v-if="shortcutsOpen"
        id="coding-shortcuts"
        class="shortcut-guide"
        aria-label="编程器快捷键"
      >
        <div class="shortcut-guide-head">
          <div>
            <strong>快捷键</strong>
            <span>VS Code 常用习惯</span>
          </div>
          <button
            class="tool-btn"
            type="button"
            aria-label="关闭快捷键说明"
            @click="shortcutsOpen = false"
          >
            ×
          </button>
        </div>
        <div class="shortcut-grid">
          <div><kbd>Ctrl</kbd><kbd>F</kbd><span>查找</span></div>
          <div><kbd>Ctrl</kbd><kbd>H</kbd><span>替换</span></div>
          <div><kbd>Ctrl</kbd><kbd>G</kbd><span>跳转到行</span></div>
          <div><kbd>Ctrl</kbd><kbd>/</kbd><span>切换行注释</span></div>
          <div><kbd>Shift</kbd><kbd>Alt</kbd><kbd>A</kbd><span>切换块注释</span></div>
          <div><kbd>Tab</kbd><span>缩进所选行</span></div>
          <div><kbd>Shift</kbd><kbd>Tab</kbd><span>反缩进所选行</span></div>
          <div><kbd>Shift</kbd><kbd>Alt</kbd><kbd>F</kbd><span>整理整份代码的缩进</span></div>
          <div><kbd>Alt</kbd><kbd>↑ / ↓</kbd><span>移动当前行</span></div>
          <div><kbd>Ctrl</kbd><kbd>F5</kbd><span>运行代码</span></div>
          <div><kbd>Ctrl</kbd><kbd>Enter</kbd><span>提交判题</span></div>
          <div><kbd>Ctrl</kbd><kbd>`</kbd><span>展开或收起控制台</span></div>
          <div><kbd>Ctrl</kbd><kbd>K</kbd><kbd>Z</kbd><span>切换专注模式</span></div>
          <div><kbd>Ctrl</kbd><kbd>K</kbd><kbd>S</kbd><span>打开此快捷键表</span></div>
        </div>
        <p>Mac 请将 Ctrl 替换为 ⌘。提交判题是本平台操作；其余遵循 VS Code 常用按键。</p>
      </section>

      <button
        class="divider"
        type="button"
        aria-label="调整控制台高度，方向键可微调"
        data-testid="divider-row"
        @pointerdown="startRowDrag"
        @keydown.up.prevent="nudgeConsole(16)"
        @keydown.down.prevent="nudgeConsole(-16)"
      />

      <div
        class="console"
        :class="{ 'is-collapsed': collapsed }"
        :style="{ height: collapsed ? undefined : consoleHeight + 'px' }"
      >
        <div class="console-head">
          <button
            class="ctab"
            :class="{ 'is-on': tab === 'run' }"
            type="button"
            @click="openTab('run')"
          >
            运行结果
          </button>
          <button
            class="ctab"
            :class="{ 'is-on': tab === 'result' }"
            type="button"
            @click="openTab('result')"
          >
            判题结果
          </button>

          <span class="spacer" />

          <!-- 输入源开关放在页签行而不是面板里：控制台只有一百多像素高，
               body 里每多一行都是从输出区抠出来的。 -->
          <div v-if="tab === 'run'" class="source-switch" role="group" aria-label="运行输入源">
            <span class="mono-dim">输入</span>
            <button
              class="seg-btn"
              :class="{ 'is-on': inputSource === 'sample' }"
              type="button"
              :aria-pressed="inputSource === 'sample'"
              data-source="sample"
              @click="inputSource = 'sample'"
            >
              样例
            </button>
            <button
              class="seg-btn"
              :class="{ 'is-on': inputSource === 'custom' }"
              type="button"
              :aria-pressed="inputSource === 'custom'"
              data-source="custom"
              @click="inputSource = 'custom'"
            >
              自定义
            </button>
          </div>

          <button class="console-fold" type="button" title="Ctrl+`" @click="collapsed = !collapsed">
            {{ collapsed ? "展开 ▴" : "收起 ▾" }}
          </button>
        </div>

        <div class="console-body">
          <!-- ---- 运行结果（样例 / 自定义共用）---- -->
          <template v-if="tab === 'run'">
            <!-- 自定义输入源：stdin 框常驻，跑完在右边出 stdout -->
            <div v-if="inputSource === 'custom'" class="custom-run">
              <div class="col">
                <label for="custom-stdin">
                  输入（stdin）
                  <button
                    v-if="samples.length"
                    class="copy-btn"
                    type="button"
                    @click="fillSample(0)"
                  >
                    填入样例 1
                  </button>
                </label>
                <textarea
                  id="custom-stdin"
                  v-model="customInput"
                  placeholder="在这里输入测试内容。留空表示用空输入运行。"
                />
              </div>
              <div class="col">
                <label>输出<span class="mono-dim">stdout / stderr</span></label>
                <div class="custom-out" data-testid="custom-out">
                  <span v-if="runBusy" class="mono-dim">{{ pendingText || "运行中…" }}</span>
                  <span v-else-if="runError" class="stderr">{{ runError }}</span>
                  <template v-else-if="runOut && runFrom === 'custom'">
                    <span class="mono-dim">
                      $ {{ metricText(runOut.time_ms, "ms") }} ·
                      {{ metricText(runOut.memory_kb, "KB") }}
                    </span>
                    <br />
                    <template v-if="runOut.compile_message">
                      <span class="stderr">{{ runOut.compile_message }}</span>
                    </template>
                    <template v-else>{{ runOut.cases?.[0]?.actual ?? "（没有输出）" }}</template>
                  </template>
                  <span v-else class="mono-dim">
                    点击下方「▶ 运行」。自定义输入不比对答案、不计分。
                  </span>
                </div>
              </div>
            </div>

            <!-- 样例输入源：逐条列出通过与否，没过的当场给期望/实际 -->
            <template v-else>
              <div v-if="runBusy" class="run-out">
                <span class="dim">{{ pendingText || "运行中…" }}</span>
              </div>
              <div v-else-if="runError" class="run-out">
                <span class="bad">✗ {{ runError }}</span>
              </div>
              <template v-else-if="runOut && runFrom === 'sample'">
                <div v-if="runOut.compile_message" class="compile-msg">
                  {{ runOut.compile_message }}
                </div>
                <table
                  v-if="casesVisible(runOut) && runOut.cases.length"
                  class="case-table"
                  data-testid="sample-run-table"
                >
                  <thead>
                    <tr>
                      <th>样例</th>
                      <th>状态</th>
                      <th>时间</th>
                      <th>内存</th>
                    </tr>
                  </thead>
                  <tbody>
                    <template v-for="item in runOut.cases" :key="item.index">
                      <tr>
                        <td class="mono-dim">{{ item.index + 1 }}</td>
                        <td>
                          <span class="case-badge" :class="verdictOf(item.status).badge">
                            {{ item.passed ? "✓ 通过" : "✗ " + verdictOf(item.status).abbr }}
                          </span>
                        </td>
                        <td class="mono-dim">{{ item.time_ms }}ms</td>
                        <td class="mono-dim">{{ item.memory_kb }}KB</td>
                      </tr>
                      <!-- 样例是公开的，没过就直接把期望/实际摆出来，不必再点一次展开 -->
                      <tr v-if="!item.passed && item.expected != null" class="case-expand">
                        <td colspan="4">
                          <div class="inline-diff">
                            <span class="mono-dim">期望</span>
                            <code>{{ item.expected }}</code>
                            <span class="mono-dim">实际</span>
                            <code class="is-mismatch"
                              >{{ diffOf(item).head
                              }}<span class="diff-mark" data-testid="diff-mark">{{
                                diffOf(item).mark
                              }}</span
                              >{{ diffOf(item).tail }}</code
                            >
                          </div>
                        </td>
                      </tr>
                    </template>
                  </tbody>
                </table>
                <p v-if="compileOnly" class="mono-dim" style="margin-top: 8px">
                  本题以编译通过为满分条件，样例结果仅供参考。
                </p>
              </template>
              <p v-else class="mono-dim">点击下方「▶ 运行」，用公开样例跑一次，不计分。</p>
            </template>

            <p class="mono-dim" style="margin-top: 8px">
              {{ allowSubmit ? "与提交判题共用限流：20 次 / 分钟" : "运行限流：20 次 / 分钟" }}
            </p>
          </template>

          <!-- ---- 判题结果（常驻回看）---- -->
          <template v-else>
            <!-- 还在排队/判题：给进度而不是把上一次的结果晾在那儿冒充本次。 -->
            <div v-if="pendingText" class="verdict-banner v-pending" data-testid="judge-pending">
              <span class="v-name">⏳ {{ pendingText }}</span>
              <span>成绩以判完为准，这期间可以继续看题或改代码</span>
            </div>

            <!-- 判题没跑成：横幅走中性的 v-failed，绝不复用 WA 那套红底，
                 并且明说成绩没记上——学员最怕的是"是不是已经按 0 分算了"。 -->
            <div v-if="submitError" class="verdict-banner v-failed" data-testid="judge-error">
              <span class="v-name">⚠ 判题未完成</span>
              <span>{{ submitError }}</span>
            </div>
            <p v-if="submitError" class="mono-dim" style="margin-bottom: 10px">
              本次提交没有记录成绩（不是 0 分）。稍后重试，或直接交卷后联系老师复核。
            </p>
            <!-- 判题挂了但之前判过：底下那块仍是旧结果，必须写明白它是哪一次的。
                 否则「⚠ 判题未完成」和「✗ 答案错误 25 分」两条横幅叠在一起，
                 学员只会读到后面那条，以为这次判成了答案错误。 -->
            <p v-if="submitError && result" class="stale-note" data-testid="stale-note">
              下面是上一次成功判题的结果，与刚才这次无关。
            </p>

            <template v-if="result">
              <!-- 编译通过型的横幅只能说编译过没过。这类题的 status 仍然是判题器给的
                   wrong_answer 之类（测试点确实没过），照搬会出现「✗ 答案错误」却拿满分，
                   而且与详情弹窗自相矛盾——同一次提交两处说法不一样最伤信任。 -->
              <div class="verdict-banner" :class="bannerClass" data-testid="verdict-banner">
                <span class="v-name">{{ bannerTitle }}</span>
                <span v-if="!compileOnly && visible && cases.length">
                  {{ passedCount }}/{{ cases.length }} 测试点通过
                </span>
                <span v-if="compileOnly">本题以编译通过为满分条件</span>
                <span class="v-meta">
                  <template v-if="'score' in result">{{ result.score }} 分 · </template>
                  {{ metricText(result.time_ms, "ms") }} ·
                  {{ metricText(result.memory_kb, "KB") }}
                </span>
              </div>

              <div v-if="result.compile_message" class="compile-msg">
                {{ result.compile_message }}
              </div>

              <p v-if="compileOnly" class="mono-dim">编译型题目不运行测试点，因此没有逐点结果。</p>
              <p v-else-if="!visible" class="mono-dim" data-testid="cases-hidden">
                本场考试暂不显示逐测试点结果，以最终成绩为准。
              </p>

              <table v-else-if="cases.length" class="case-table" data-testid="case-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>状态</th>
                    <th>时间</th>
                    <th>内存</th>
                    <th>类型</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  <template v-for="item in cases" :key="item.index">
                    <tr
                      :class="{ 'sample-row': item.is_sample }"
                      @click="item.is_sample && toggleExpand(item.index)"
                    >
                      <td class="mono-dim">{{ item.index + 1 }}</td>
                      <td>
                        <span class="case-badge" :class="verdictOf(item.status).badge">
                          {{ verdictOf(item.status).abbr }}
                        </span>
                      </td>
                      <td class="mono-dim">{{ item.time_ms }}ms</td>
                      <td class="mono-dim">{{ item.memory_kb }}KB</td>
                      <td>
                        <span class="case-badge" :class="item.is_sample ? 'cb-ac' : 'cb-hidden'">
                          {{ item.is_sample ? "样例" : "隐藏" }}
                        </span>
                      </td>
                      <td class="mono-dim">
                        {{ item.is_sample ? (expanded.has(item.index) ? "▾" : "▸") : "" }}
                      </td>
                    </tr>
                    <!-- 只有样例点有内容可展开；隐藏点的三个字段恒为 null。 -->
                    <tr v-if="item.is_sample && expanded.has(item.index)" class="case-expand">
                      <td colspan="6">
                        <div class="diff-grid">
                          <div>
                            <h5>输入</h5>
                            <pre>{{ item.input }}</pre>
                          </div>
                          <div>
                            <h5>期望输出</h5>
                            <pre>{{ item.expected }}</pre>
                          </div>
                          <div>
                            <h5>实际输出</h5>
                            <pre :class="{ 'is-mismatch': !diffOf(item).matched }">{{
                              diffOf(item).head
                            }}<span
                                v-if="!diffOf(item).matched"
                                class="diff-mark"
                                data-testid="diff-mark"
                                >{{ diffOf(item).mark }}</span
                              >{{ diffOf(item).tail }}</pre>
                          </div>
                        </div>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>

              <p
                v-if="!compileOnly && visible && cases.length"
                class="mono-dim"
                style="margin-top: 8px"
              >
                隐藏测试点的输入输出不下发（判分资产），此处只能看到状态。样例行点击可展开对比。
              </p>
            </template>
            <p v-else-if="!submitError" class="mono-dim">
              {{
                allowSubmit
                  ? "尚未提交判题。点击下方「提交判题」，成绩以最后一次提交为准。"
                  : "本练习只运行不计分，没有判题结果。"
              }}
            </p>
          </template>
        </div>
      </div>

      <div class="prog-actions">
        <button
          class="btn"
          type="button"
          title="Ctrl+F5"
          :disabled="busy || runBusy"
          @click="runOnce"
        >
          ▶ 运行
        </button>
        <!-- 课时内的「只运行不计分」场景（交接文档 15 §4）关掉这两个：
             计分提交依赖 X1（paper_attempts 来源改造），课时里还没有 attempt。
             显示一个点了必然报错的按钮，比不显示更糟。 -->
        <button
          v-if="allowSubmit"
          class="btn btn-primary"
          type="button"
          title="Ctrl+Enter"
          :disabled="busy || submitDisabled"
          @click="runSubmit"
        >
          提交判题
        </button>
        <button v-if="allowHistory" class="btn" type="button" @click="emit('history')">
          提交记录 ({{ submissionCount }})
        </button>
        <span class="note">
          {{
            note ||
            (!allowSubmit
              ? "本练习只运行不计分，用样例或自定义输入调试即可"
              : compileOnly
                ? "试跑仅供参考，本题以编译通过为满分条件"
                : "代码已自动保存 · 成绩以最后一次「提交判题」为准")
          }}
        </span>
      </div>
    </div>

    <ExamModal
      :open="!!submitDetail"
      title="判题结果"
      wide
      portal-target=".qz"
      @update:open="submitDetail = null"
    >
      <SubmissionDetail
        v-if="submitDetail"
        :submission="submitDetail"
        :compile-only="compileOnly"
        @copied="emit('toast', $event)"
      />
      <template #actions>
        <button class="btn" type="button" @click="submitDetail = null">关闭</button>
      </template>
    </ExamModal>
  </div>
</template>
