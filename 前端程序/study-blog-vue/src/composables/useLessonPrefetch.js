// 相邻块预热：学生停在第 N 块时，把第 N+1 块要用的东西提前拿了（交接文档 17 §5 S2-4）。
//
// **只往前看一块**，不是进课时就把整节课全量缓存。理由很直接：学生大概率会点"继续下一块"，
// 但不一定会走完整节课；预取到第 5 块的编程题，八成是白花的流量。
//
// 按块类型分派：
//   practice  → 提前取题面（就是 BlockPractice 现在切过去才打的那个接口）
//   video     → 提前签播放令牌（VideoPlayer 会 await 它，不会重复签）
//   markdown  → 什么都不用做，正文已经在 /api/lessons/{id} 的响应里了
//   materials → **本期不预热**，原因见下面 warmMaterials 的注释（卡在后端缓存头上）
//
// 护栏（saveData / 2g / idle 排队 / 去重）全部在 services/prefetch 里，这里不重复判。
import { watch } from "vue";
import {
  clearBlockPrefetch,
  idle,
  prefetchMaterial,
  prefetchPlayToken,
  prefetchProblem,
} from "../services/prefetch";
import { clearPdfCache } from "../services/pdf-cache";

/**
 * @param lesson    ref(课时详情)
 * @param currentId ref(当前块 id)
 * @param lessonId  ref(课时 id)
 */
export function useLessonPrefetch(lesson, currentId, lessonId) {
  function blockAfterCurrent() {
    const blocks = lesson.value?.blocks || [];
    const index = blocks.findIndex((b) => b.id === currentId.value);
    return index >= 0 ? blocks[index + 1] || null : null;
  }

  function warmMaterials(block) {
    // 批次1 落地后 inline 接口 302 到 MinIO 预签名 URL，响应带 ETag/Accept-Ranges/
    // Content-Range，浏览器 HTTP 缓存会留下预热字节——学生切过去时 PDF.js 取首页走缓存。
    // 只预热第一份可内嵌资料（和 BlockMaterials 默认选中口径一致），不全量。
    const list = block.materials || [];
    const target = list.find((m) => {
      const mime = (m.mime_type || "").toLowerCase();
      return (
        /^image\//.test(mime) ||
        /^text\/(markdown|plain|x-markdown)/.test(mime) ||
        mime === "application/pdf" ||
        /^video\//.test(mime) ||
        /^audio\//.test(mime)
      );
    });
    if (target) prefetchMaterial(lessonId.value, block.id, target);
  }

  function prewarm(block) {
    // 锁着的块预了也用不上，还会在控制台打出一串 403，看着像出故障
    if (!block || block.lock_reason) return;
    const id = lessonId.value;
    if (block.block_type === "practice") prefetchProblem(id, block.id);
    else if (block.block_type === "video") prefetchPlayToken(id, block.id);
    else if (block.block_type === "materials") warmMaterials(block);
  }

  // 换块就预热下一块。首次落点由 load() 里设置 currentId 触发，不需要 immediate。
  watch(currentId, () => idle(() => prewarm(blockAfterCurrent())));
  // 换课时：上一节课的题面、令牌、PDF document 全部作废
  watch(lessonId, () => {
    clearBlockPrefetch();
    clearPdfCache();
  });

  return { clearBlockPrefetch };
}
