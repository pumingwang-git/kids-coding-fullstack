<script setup>
// 课时学习页：/learn/:lessonId。
//
// 2026-08-10 重构（《14、单课时学习界面-开发交接》）：从「把所有内容块摞成长列表滚动」
// 改为「一次一整个内容块 + 右侧课程导航抽屉」的沉浸式学习闭环。
//
// 为什么改：长列表下一节课里视频、图文、单题、编程题混排，学生一屏能看到三种毫不相干
// 的东西，既无法专注也无法判断学到哪了；更关键的是**长列表承载不了闯关式解锁**——
// 块被锁住但学生仍能滚过去看到后面，锁就没有意义。
//
// 本组件是「壳」，只做四件事：加载态 / 顶栏 / 抽屉 / 主区分发。
// 每类块的渲染在 components/lesson/blocks/*，完成上报统一走 useLessonProgress——
// 块组件不调接口、不改路由，只 emit（契约见交接文档 §7.3）。
//
// 两道闸门（§4）：前端**只认 lock_reason 一个字段**，不自己算权限，也不自己算顺序。
//   not_enrolled 权限锁 → 可点进来看开通引导（转化路径）
//   sequential   顺序锁 → 抽屉里 disabled，点了只给 toast
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { request } from "../services/auth";
import {
  clearBlockPrefetch,
  clearLessonPrefetch,
  idle,
  prefetchPlayToken,
  takeLesson,
} from "../services/prefetch";
import { useLessonProgress } from "../composables/useLessonProgress";
import { useLessonPrefetch } from "../composables/useLessonPrefetch";
import LessonLoading from "../components/lesson/LessonLoading.vue";
import LessonDrawer from "../components/lesson/LessonDrawer.vue";
import LessonIcon from "../components/lesson/LessonIcon.vue";
import BlockLocked from "../components/lesson/blocks/BlockLocked.vue";
import BlockMarkdown from "../components/lesson/blocks/BlockMarkdown.vue";
import BlockVideo from "../components/lesson/blocks/BlockVideo.vue";
import BlockPractice from "../components/lesson/blocks/BlockPractice.vue";
import BlockHomework from "../components/lesson/blocks/BlockHomework.vue";
import BlockMaterials from "../components/lesson/blocks/BlockMaterials.vue";
import BlockScratch from "../components/lesson/blocks/BlockScratch.vue";
import ImageLightbox from "../components/exam/ImageLightbox.vue";
import "../styles/lesson.css";

const BLOCK_COMPONENTS = {
  markdown: BlockMarkdown,
  video: BlockVideo,
  practice: BlockPractice,
  homework: BlockHomework,
  materials: BlockMaterials,
  scratch: BlockScratch,
};
// 完成上报的 source（§5.1）：图文/资料是学生手点，练习/作业将来由作答链路触发
const COMPLETE_SOURCE = {
  markdown: "manual",
  materials: "manual",
  video: "video",
  practice: "practice",
  homework: "homework",
  // Scratch 块的完成只能由 Studio 提交后的服务器判定写入，壳绝不能代为 complete()。
  scratch: "scratch",
};
const DRAWER_STYLE_KEY = "lesson.drawerStyle";
// 加载态的两条规则（交接文档 17 §3.5）。以前这里是「不足 400ms 就补齐到 400ms」，
// 出发点是防闪烁，代价却是**所有人无条件多等 400ms**。正确的做法是两条一起上：
//   延迟显示：250ms 内返回就根本不显示加载页 —— 学生感知为「点了就开」，压根没得闪；
//   最短驻留：一旦显示了就至少停 350ms —— 真慢的时候才需要防闪。
const LOADING_DELAY_MS = 250;
const LOADING_MIN_MS = 350;

const route = useRoute();
const router = useRouter();
const lessonId = computed(() => Number(route.params.lessonId));

const lesson = ref(null);
const phase = ref("loading"); // loading | ready | error —— 数据状态
// 加载页显不显示，和数据状态**解耦**：快的时候数据在 loading 里也不该出加载页。
const loadingVisible = ref(false);
const loadStep = ref(0);
const loadGone = ref(false);
const error = ref("");
const currentId = ref(null);
const returnTo = ref(null); // 「返回到 xx」锚点：从抽屉跨块跳转后出现
const drawerOpen = ref(window.innerWidth > 1024);
const drawerStyle = ref(localStorage.getItem(DRAWER_STYLE_KEY) || "list");
const toastText = ref("");
const anchorEl = ref(null);
const videoShellEl = ref(null);
const advancingFromVideo = ref(false);
let toastTimer = null;
let videoResizeObserver = null;
let videoResizeTimer = null;
let loadingDelayTimer = null;

const { complete, reportVideo } = useLessonProgress(lesson);
// 相邻块预热：停在第 N 块时把第 N+1 块的题面/播放令牌提前拿了（交接文档 17 §5 S2-4）
useLessonPrefetch(lesson, currentId, lessonId);

const blocks = computed(() => lesson.value?.blocks || []);
const currentBlock = computed(() => blocks.value.find((b) => b.id === currentId.value) || null);
const currentIndex = computed(() => blocks.value.findIndex((b) => b.id === currentId.value));
const isLast = computed(() => currentIndex.value === blocks.value.length - 1);
const returnBlock = computed(() =>
  returnTo.value == null ? null : blocks.value.find((b) => b.id === returnTo.value) || null,
);
const currentComponent = computed(() =>
  currentBlock.value ? BLOCK_COMPONENTS[currentBlock.value.block_type] || null : null,
);
// 自己渲染行动的块类型：练习在块内提交，试卷入口也在课程提示框内；
// 壳不再另给「完成，继续下一块」，避免和其主操作重复。
const FOOT_OWNERS = new Set(["practice", "homework", "scratch"]);
const ownsFoot = computed(() => FOOT_OWNERS.has(currentBlock.value?.block_type));

/**
 * 这个视频块的完成度是不是由**服务端账本**裁决。
 *
 * **不要在这里按 source_type 自己推**——服务端已经把结论放在 `completion_mode`
 * 里了（courses._student_block_dto），推错的后果是学生卡在一个永远完不成的块上。
 * 典型的坑：direct（外链 MP4）播放器报得出位置，看起来"有进度通道"，但服务端
 * 没有 Video 行、拿不到总时长，因而**算不出阈值**，只能降级成手动确认。
 *
 * 这个区分决定了 goNext() 能不能替学生"补一刀完成"：账本裁决的块补了就是撒谎
 * （等于点一下"下一步"就算看完，服务端的 completion_percent 白设）；
 * 降级的块不补则永远完不成。
 */
function isLedgerAdjudicated(block) {
  return block?.block_type === "video" && block.completion_mode === "ledger";
}

// 编程题要双栏工作区，880px 的 block-wrap 放不下 → 主区展开铺满（交接文档 15 §4.1）。
// **顶栏与抽屉完全不动**：换顶栏就是换壳，学生会以为自己离开了课时。
const isWorkspace = computed(
  () =>
    currentBlock.value?.block_type === "practice" &&
    currentBlock.value?.problem?.problem_type === "programming" &&
    !currentBlock.value?.lock_reason,
);
// Scratch 编辑器本身会吃键盘快捷键和方向键；即使此处只是工作台入口，也让壳在本块
// 让出左右键，避免焦点落在链接/嵌入式 Studio 时误切换课时内容。
const isScratch = computed(
  () => currentBlock.value?.block_type === "scratch" && !currentBlock.value?.lock_reason,
);
// 资料阅读器也要铺满：880px 窄栏 + 260px 清单 = 预览区只剩 ~580px，A4 正文缩到 7~8px
// （交接文档 17 §2.2）。复用 is-workspace 同款机制 → is-reader，不发明新东西。
// 顶栏与抽屉同样不动——换壳学生会以为自己离开了课时。
const isReader = computed(
  () => currentBlock.value?.block_type === "materials" && !currentBlock.value?.lock_reason,
);

/** 进课时停在哪一块。
 *
 * 优先 ?block=<id>：从课时作业交完卷回来时带着它，学生才会停在刚做完的那一块上，
 * 而不是被扔回第 1 块（顺序锁的块除外——那是闸门，query 不能绕过去）。
 *
 * 没带就落在**第一个没做完且能做的块**。以前这里取的是"第一个不是顺序锁的块"，
 * 那永远是第 1 块：学到第 8 块的人第二天进来，还得自己从头点到第 8 块。
 * 全做完了就落在最后一块——那时候人是回来复习的，不是回来重学第 1 块的。
 *
 * 权限锁的块要能停留：未开通的学生落在锁定块上看到开通引导，这是转化路径（§3.3）。
 */
function landingBlock(list) {
  if (!list.length) return null;
  const wanted = Number(route.query?.block) || 0;
  const asked = wanted ? list.find((b) => b.id === wanted && b.lock_reason !== "sequential") : null;
  if (asked) return asked;
  const firstMaterial = list.find(
    (b) => b.block_type === "materials" && b.lock_reason !== "sequential",
  );
  if (firstMaterial) return firstMaterial;
  return (
    list.find((b) => !b.completed && b.lock_reason !== "sequential") ||
    list[list.length - 1] ||
    null
  );
}

function toast(message) {
  toastText.value = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toastText.value = ""), 2200);
}

async function load({ keepCurrent = false } = {}) {
  phase.value = "loading";
  loadGone.value = false;
  loadStep.value = 0;
  error.value = "";

  // 课包目录 hover 时可能已经把这节课预取回来了（services/prefetch）。
  // 拿到的是**还可能在飞的 promise**：await 它既不会重复发请求，慢的时候也照样出加载页。
  //
  // ?refresh=1 时必须跳过缓存：它是"我刚在别处改过这节课的状态"的信号（交完作业回来）。
  // 缓存 TTL 有 30 秒且取走不删，用它会拿到**进作业之前**的那份——作业块还显示没做完、
  // 后面的块还锁着。顺手把缓存清掉，否则这一次绕过去了，下一次进来还是旧的。
  // 用可选链读 query：这个组件也被不带完整路由的场景挂过（测试、预览壳），
  // route.query 可能压根不存在，直接点属性会在 onMounted 里抛出去。
  const wantsFresh = !!route.query?.refresh;
  if (wantsFresh) clearLessonPrefetch();
  const prefetched = wantsFresh ? null : takeLesson(lessonId.value);
  clearTimeout(loadingDelayTimer);
  loadingVisible.value = false;
  let shownAt = 0;
  loadingDelayTimer = setTimeout(() => {
    loadingVisible.value = true;
    shownAt = Date.now();
  }, LOADING_DELAY_MS);

  try {
    loadStep.value = 0; // ① 拉取课时内容
    // 预取失败会落成 null（见 prefetch.js：不让它变成未捕获的 rejection）——
    // 这时正常请求一次，该报的错由这一次报出来。
    const data =
      (prefetched ? await prefetched : null) || (await request(`/api/lessons/${lessonId.value}`));
    clearTimeout(loadingDelayTimer);
    loadStep.value = 1; // ② 校验学习权限（响应已带 lock_reason）
    lesson.value = data;
    loadStep.value = 2; // ③ 定位到第一个内容块
    const keep = keepCurrent && blocks.value.some((b) => b.id === currentId.value);
    if (!keep) currentId.value = landingBlock(blocks.value)?.id ?? null;
    if (currentBlock.value?.block_type === "video") drawerOpen.value = false;
    returnTo.value = null;
    loadStep.value = 3;

    // 落点就是视频块：**立刻**签令牌，不排 idle——这个是马上要用的，不是顺手预热。
    // VideoPlayer 挂载时会 await 这个 promise，所以不会出现「预签 + 自签」两次。
    if (currentBlock.value?.block_type === "video" && !currentBlock.value.lock_reason) {
      prefetchPlayToken(lessonId.value, currentBlock.value.id);
    }

    // 加载页一旦露过脸就至少停 LOADING_MIN_MS，避免闪一下；没露过就直接进。
    if (loadingVisible.value) {
      const shown = Date.now() - shownAt;
      if (shown < LOADING_MIN_MS) await new Promise((r) => setTimeout(r, LOADING_MIN_MS - shown));
    }
    phase.value = "ready";
    loadingVisible.value = false;
    loadGone.value = true;
    focusAnchor();
    prefetchPlayerChunk();
  } catch (err) {
    clearTimeout(loadingDelayTimer);
    loadingVisible.value = true; // 失败必须让人看见，不管返回得多快
    const message = err?.message || "课时加载失败。";
    error.value =
      message.includes("开放") || message.includes("权限") ? "该课时尚未对你开放。" : message;
    phase.value = "error";
  }
}

/**
 * 视频播放器拖着 video.js 的 UMD 完整构建（~600KB），现在是切到视频块才开始下载。
 * 这节课只要有视频块，就趁学生还在看第一块图文的空档把 chunk 拿了（交接文档 17 §5 S2-2）。
 * 失败无所谓——真切过去时 defineAsyncComponent 会自己再来一次。
 */
function prefetchPlayerChunk() {
  const kinds = new Set(
    blocks.value
      .filter((b) => b.block_type === "video" && !b.lock_reason)
      .map((b) => b.source_type),
  );
  if (kinds.has("platform")) idle(() => import("../components/VideoPlayer.vue").catch(() => {}));
  if (kinds.has("direct")) idle(() => import("../components/DirectVideo.vue").catch(() => {}));
}

/**
 * 静默刷新课时（不走加载页）。练习块提交后用它把权威的进度与解锁状态取回来——
 * 完成记录、进度分母、顺序锁的解锁都是服务端算的，前端自己拼会和服务端分叉。
 * 只换 blocks/progress 两个字段，不动 currentId，块组件自身的作答态因此不会被重置。
 */
async function refreshQuietly() {
  try {
    const data = await request(`/api/lessons/${lessonId.value}`);
    if (lesson.value) {
      lesson.value.blocks = data.blocks;
      lesson.value.progress = data.progress;
    }
  } catch {
    // 刷新失败不打断作答：判定已经拿到了，进度下次进课时会对上。
  }
}

function onBlockAnswered() {
  refreshQuietly();
}

/** 换块后把焦点移到块标题：否则键盘用户换完块焦点还留在抽屉里。 */
function focusAnchor() {
  nextTick(() => anchorEl.value?.focus?.());
}

function syncVideoFrameWidth() {
  const shell = videoShellEl.value;
  const stage = shell?.querySelector(".v-stage");
  if (!shell || !stage) return;
  const { width, height } = stage.getBoundingClientRect();
  const frameWidth = Math.floor(Math.min(width, (height * 16) / 9, 1600));
  if (frameWidth > 0) shell.style.setProperty("--video-frame-width", `${frameWidth}px`);
}

function queueVideoFrameSync() {
  syncVideoFrameWidth();
  clearTimeout(videoResizeTimer);
  videoResizeTimer = setTimeout(syncVideoFrameWidth, 160);
}

function observeVideoFrame() {
  videoResizeObserver?.disconnect();
  videoResizeObserver = null;

  const stage = videoShellEl.value?.querySelector(".v-stage");
  if (!stage) return;
  syncVideoFrameWidth();
  if (typeof ResizeObserver === "undefined") return;

  videoResizeObserver = new ResizeObserver(queueVideoFrameSync);
  videoResizeObserver.observe(stage);
  videoResizeObserver.observe(videoShellEl.value);
}

function goBlock(id, { viaDrawer = false } = {}) {
  const target = blocks.value.find((b) => b.id === id);
  if (!target) return;
  if (target.lock_reason === "sequential") {
    toast("完成前面的内容块后才会解锁");
    return;
  }
  // 从抽屉跨块（跨度 > 1）跳转时记来源 → 顶栏出现「返回到 xx」。
  // 相邻跳转不记：不然胶囊一直挂着很吵。
  if (viaDrawer && currentId.value != null) {
    const from = currentIndex.value;
    const to = blocks.value.findIndex((b) => b.id === id);
    returnTo.value = Math.abs(to - from) > 1 ? currentId.value : null;
  } else {
    returnTo.value = null;
  }
  currentId.value = id;
  if (target.block_type === "video" || window.innerWidth <= 1024) drawerOpen.value = false;
  focusAnchor();
}

async function goNext() {
  const block = currentBlock.value;
  if (!block) return;
  // 练习/作业块的完成度由它们自己的提交链路写（提交即完成，§5.1）。壳在这里补一刀
  // complete()，等于给闯关闸门开了一个"点一下继续就算学过"的后门——一路按 → 就能
  // 把整节课刷成已完成，一道题都不用做。这类块只切块，不上报。
  //
  // 有播放进度通道的视频块同理：这里原本会带着默认的 progress_percent=100 上报，
  // 于是点一下"下一步"就把视频标成看完了，服务端的 completion_percent 根本挡不住
  // （它只能相信客户端报上来的进度）。这类块交给 reportVideo 按真实进度上报；
  // embed / 未就绪的 platform 没有播放器可读进度，仍走这条手动补报的路，
  // 否则学生会永远停在那一块。
  const skipManual = FOOT_OWNERS.has(block.block_type) || isLedgerAdjudicated(block);
  if (!block.completed && !skipManual) {
    await complete(block.id, COMPLETE_SOURCE[block.block_type] || "manual");
  }
  if (isLast.value) {
    // 练习 / 作业的完成只能由提交链路写入。最后一块如果还没完成，
    // 不能让「完成本课时」成为绕过判题的出口。
    if (!currentBlock.value?.completed) {
      toast("请先完成并提交本块内容");
      return;
    }
    await finishLesson();
    return;
  }
  const next = blocks.value[currentIndex.value + 1];
  returnTo.value = null;
  currentId.value = next.id;
  if (next.block_type === "video") drawerOpen.value = false;
  focusAnchor();
  if (next.lock_reason === "not_enrolled") toast("下一块需要开通课包");
  else if (next.lock_reason === "sequential") toast("下一块仍按顺序锁定");
}

/** 最后一块完成后的统一出口：下一课时优先，课程末尾回课程目录。 */
async function finishLesson() {
  const nextLessonId = lesson.value?.next_lesson_id;
  if (nextLessonId) {
    await router.push({ name: "lesson-player", params: { lessonId: nextLessonId } });
    return;
  }
  if (lesson.value?.course_id) {
    await router.push({ name: "course-detail", params: { courseId: lesson.value.course_id } });
    return;
  }
  toast("本课时已完成");
}

function goPrev() {
  if (currentIndex.value <= 0) return;
  returnTo.value = null;
  const previous = blocks.value[currentIndex.value - 1];
  currentId.value = previous.id;
  if (previous.block_type === "video") drawerOpen.value = false;
  focusAnchor();
}

function gotoNextTodo() {
  const target = blocks.value.find((b) => !b.completed && !b.lock_reason);
  if (target) goBlock(target.id);
  else toast("没有可继续的内容块了");
}

function goCourse() {
  if (lesson.value?.course_id) {
    router.push({ name: "course-detail", params: { courseId: lesson.value.course_id } });
  }
}

function toggleDrawerStyle() {
  drawerStyle.value = drawerStyle.value === "list" ? "timeline" : "list";
  localStorage.setItem(DRAWER_STYLE_KEY, drawerStyle.value);
}

// 播放器给的是 { position, duration }（秒），不是百分比——服务端要靠位置差记账。
function onVideoProgress(payload) {
  const block = currentBlock.value;
  if (!block || !isLedgerAdjudicated(block)) return null;
  return reportVideo(block.id, payload?.position ?? 0);
}

async function onVideoEnded() {
  const block = currentBlock.value;
  if (!block || advancingFromVideo.value) return;
  advancingFromVideo.value = true;
  const endedBlockId = block.id;
  try {
    if (isLedgerAdjudicated(block)) {
      // 播完补最后一拍（绕过 15 秒节流），把片尾那段零头记上。
      // 位置取块上的总时长——播放器此刻的 currentTime 可能差零点几秒，
      // 而服务端会把它钳进 [0, duration]，多报无害、少报会差一点。
      await reportVideo(endedBlockId, block.duration_seconds || 0, { force: true });
    }
    if (currentBlock.value?.id !== endedBlockId) return;

    await goNext();
  } finally {
    advancingFromVideo.value = false;
  }
}

/** 焦点是不是落在"自己要吃键盘"的地方。
 *
 * 这里曾经只按 tagName 白名单判断 INPUT/TEXTAREA/SELECT。**CodeMirror 的可编辑元素
 * 是 div[contenteditable]，tagName 是 DIV**，于是学生在编程题里按一下 → 想把光标
 * 右移，实际触发的是 goNext()：块被标成已完成、编辑器连同代码一起销毁。
 * 判"能不能编辑"，不判"叫什么标签"。
 */
function isTypingTarget(el) {
  if (!el) return false;
  if (el.isContentEditable) return true;
  return !!el.closest?.("input, textarea, select, [contenteditable=''], [contenteditable='true']");
}

function onKeydown(event) {
  if (phase.value !== "ready") return;
  const active = document.activeElement;
  if (isTypingTarget(active)) {
    if (event.key === "Escape") active.blur?.();
    return;
  }
  if (event.key === "Escape") {
    drawerOpen.value = false;
    return;
  }
  // 工作区型的块（编程题双栏 / 资料阅读器）自己要用方向键翻页、移动光标、拖分隔条。
  // 壳在这类块上整体让出左右键——抢一个方向键，换来的是"我明明在改代码，它自己翻页了"。
  if (isWorkspace.value || isReader.value || isScratch.value) return;
  if (event.key === "ArrowRight") goNext();
  else if (event.key === "ArrowLeft") goPrev();
}

onMounted(() => {
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("resize", queueVideoFrameSync);
  window.visualViewport?.addEventListener("resize", queueVideoFrameSync);
  load();
});
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeydown);
  window.removeEventListener("resize", queueVideoFrameSync);
  window.visualViewport?.removeEventListener("resize", queueVideoFrameSync);
  clearTimeout(toastTimer);
  clearTimeout(videoResizeTimer);
  clearTimeout(loadingDelayTimer);
  videoResizeObserver?.disconnect();
  // 预签的令牌是按课时签的，别让它活过这个页面
  clearBlockPrefetch();
});
watch(lessonId, () => load());
watch([phase, currentId], () => nextTick(observeVideoFrame));
</script>

<template>
  <div class="lesson-root" :class="{ 'drawer-open': drawerOpen && phase === 'ready' }">
    <!-- 加载页「延迟显示」：250ms 内返回就不出场，学生看到的是「点了就开」。
         失败必须出场，所以 error 单独一条，不受延迟计时器管。 -->
    <LessonLoading
      v-if="phase === 'error' || (phase !== 'ready' && loadingVisible)"
      :step="loadStep"
      :error="error"
      :gone="loadGone"
      :lesson-title="lesson?.title || ''"
      :course-title="lesson?.course_title || ''"
      @retry="load"
    />

    <template v-if="phase === 'ready' && lesson">
      <header class="lesson-topbar">
        <button class="icon-btn" type="button" aria-label="返回课包" @click="goCourse">
          <LessonIcon name="arrowLeft" :size="16" />
        </button>
        <span class="tb-logo">学</span>
        <span class="tb-title">{{ lesson.title }}</span>
        <span class="tb-crumb">{{ lesson.course_title }}</span>
        <span class="lspacer"></span>

        <button
          v-if="returnBlock"
          class="return-pill"
          type="button"
          @click="goBlock(returnBlock.id)"
        >
          <LessonIcon name="arrowLeft" :size="12" />返回到 {{ returnBlock.title }}
        </button>

        <button class="lbtn" type="button" @click="drawerOpen = !drawerOpen">
          <LessonIcon name="menu" :size="13" />课程导航
        </button>
      </header>

      <div class="lesson-body">
        <main
          class="lesson-viewport"
          :class="{
            'is-full-bleed': currentBlock?.block_type === 'video' && !currentBlock?.lock_reason,
          }"
        >
          <!-- 锁定块：两种 lock_reason 两套文案与出口 -->
          <BlockLocked
            v-if="currentBlock && currentBlock.lock_reason"
            :block="currentBlock"
            :lesson="lesson"
            @go-course="goCourse"
            @goto-next-todo="gotoNextTodo"
          />

          <!-- 视频块整块出血，不套 block-wrap -->
          <template v-else-if="currentBlock && currentBlock.block_type === 'video'">
            <div ref="videoShellEl" class="video-block-shell">
              <h2 ref="anchorEl" tabindex="-1" class="block-anchor sr-title">
                {{ currentBlock.title }}
              </h2>
              <BlockVideo
                :block="currentBlock"
                :lesson-id="lessonId"
                @progress="onVideoProgress"
                @ended="onVideoEnded"
              />
              <div class="video-actions">
                <div class="block-foot">
                  <button
                    v-if="currentIndex > 0"
                    class="lbtn lbtn-chunky"
                    type="button"
                    @click="goPrev"
                  >
                    <LessonIcon name="chevronLeft" :size="14" />上一块
                  </button>
                  <button class="lbtn lbtn-chunky lbtn-accent" type="button" @click="goNext">
                    {{
                      isLast && lesson.next_lesson_id
                        ? "完成，进入下一章节"
                        : isLast
                          ? "完成本课时"
                          : "完成，继续下一块"
                    }}
                    <LessonIcon v-if="!isLast" name="arrowRight" :size="14" />
                  </button>
                  <span class="hint">
                    {{
                      currentBlock.completed
                        ? "本块已完成"
                        : currentBlock.source_type === "embed"
                          ? "外链视频无法自动跳转，请观看后手动继续"
                          : isLast && lesson.next_lesson_id
                            ? "视频结束后自动进入下一章节"
                            : isLast
                              ? "视频结束后自动完成本课时"
                              : "视频结束后自动继续"
                    }}
                  </span>
                </div>
              </div>
            </div>
          </template>

          <div
            v-else-if="currentBlock"
            class="block-wrap"
            :class="{ 'is-workspace': isWorkspace, 'is-reader': isReader }"
          >
            <h2 ref="anchorEl" tabindex="-1" class="block-anchor sr-title">
              {{ currentBlock.title }}
            </h2>
            <!-- 练习块自带底部行动条（提交/再试和「完成继续」是两套动作），
                 壳把上一块/下一块按钮通过具名插槽塞进去，避免出现两条 block-foot。
                 keep-alive 只缓存资料块：PDF.js 实例和已渲染页面切走不销毁，切回直接复用，
                 不再每次重新加载（交接文档 17 §5）。编程题/视频/练习不缓存——状态复杂。 -->
            <keep-alive :include="['BlockMaterials']">
              <component
                :is="currentComponent"
                v-if="currentComponent"
                :block="currentBlock"
                :lesson-id="lessonId"
                @answered="onBlockAnswered"
                @toast="toast"
              >
                <template #prev>
                  <button
                    v-if="currentIndex > 0"
                    class="lbtn lbtn-chunky"
                    type="button"
                    @click="goPrev"
                  >
                    <LessonIcon name="chevronLeft" :size="14" />上一块
                  </button>
                </template>
                <template #next>
                  <button class="lbtn lbtn-chunky lbtn-accent" type="button" @click="goNext">
                    {{ isLast ? "完成本课时" : "继续下一块" }}
                    <LessonIcon v-if="!isLast" name="arrowRight" :size="14" />
                  </button>
                </template>
              </component>
            </keep-alive>
            <p v-if="!currentComponent && currentBlock" class="block-placeholder">
              暂不支持的内容块类型：{{ currentBlock.block_type }}
            </p>

            <div v-if="!ownsFoot" class="block-foot">
              <button
                v-if="currentIndex > 0"
                class="lbtn lbtn-chunky"
                type="button"
                @click="goPrev"
              >
                <LessonIcon name="chevronLeft" :size="14" />上一块
              </button>
              <button class="lbtn lbtn-chunky lbtn-accent" type="button" @click="goNext">
                {{ isLast ? "完成本课时" : "完成，继续下一块" }}
                <LessonIcon v-if="!isLast" name="arrowRight" :size="14" />
              </button>
              <span class="hint">{{
                currentBlock.completed ? "本块已完成" : "学完后点这里继续"
              }}</span>
            </div>
          </div>

          <p v-else class="locked-state">这节课还没有配置内容。</p>
        </main>

        <button
          class="lesson-scrim"
          type="button"
          aria-label="关闭课程导航"
          @click="drawerOpen = false"
        ></button>

        <LessonDrawer
          :lesson="lesson"
          :current-id="currentId"
          :variant="drawerStyle"
          @go="(id) => goBlock(id, { viaDrawer: true })"
          @toggle-style="toggleDrawerStyle"
          @cert="toast('结业证书功能即将开放')"
        />
      </div>
    </template>

    <div class="lesson-toast" :class="{ 'is-shown': !!toastText }" role="status">
      {{ toastText }}
    </div>

    <!-- 图片大图查看器（资料区预览 / 题干配图共用）：
         单例挂载点必须与 MarkdownBody 的 openLightbox 配合，见 stores/lightbox。 -->
    <ImageLightbox />
  </div>
</template>

<style scoped>
/* 块标题：给屏幕阅读器与键盘焦点用，视觉上不重复显示（抽屉与顶栏已经有标题） */
.sr-title {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}
</style>
