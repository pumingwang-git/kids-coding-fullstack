// PDF document 模块级缓存（交接文档 17 批次3）。
//
// 解决的问题：PdfReader 组件每次切走再切回都要重新 getDocument（重新 fetch + 解析 PDF），
// 即使有 keep-alive，同块内切不同 PDF 也会重新加载。把 PDFDocumentProxy 缓存到模块级
// Map，key 用 material_id（稳定标识，不随预签名 URL 变），切回时直接复用——
// PDF.js 的 document 对象一旦加载完成，内部已持有数据，URL 过期不影响。
//
// 缓存策略（2026-08-12 定稿，改为「引用计数 + 闲置保留 + LRU 上限」）：
//   - 旧策略：release 计数归零立即 destroy → 跨资料切换（A→B→A）时 A 的 document
//     已被销毁，切回只能重新下载 + 解析，缓存形同虚设。
//   - 新策略：release 归零只把 entry 标记为「闲置」（不删不 destroy，保留内存中的
//     document 数据）；仅当缓存总量超过 MAX_CACHED 时，按 lastUsed 淘汰最久未用的
//     闲置项。正在使用的项绝不淘汰。这样同块内 4 份资料切来切去全部命中内存缓存，
//     秒开不重新加载。内存代价由 MAX_CACHED 兜底（默认 4 份）。
//
// 引用计数仍然保留：多个 PdfReader 实例可能引用同一 document（keep-alive 缓存的
// 旧实例 + 新实例短暂共存），refcount 只在淘汰/清空时真正 destroy。
// clearBlockPrefetch 时强制清理（换课时上一节课的 PDF 全部作废）。
//
// 失败不缓存：getDocument 抛错时删掉 entry，下次重试，不让坏 promise 卡住后续访问。
//
// ⚠️ pdfjsLib 用动态 import：clearPdfCache 被 useLessonPrefetch 静态引用，若顶层
// import pdfjsLib 会把 350KB 的 pdfjs-dist 拖进 LessonPlayer 主 chunk，违背懒加载。
// 只在实际加载 PDF 时才动态拉取。

const cache = new Map(); // materialId -> { doc, refcount, url, lastUsed }
const MAX_CACHED = 4; // 内存中最多保留几份 PDF document（LRU 淘汰，含闲置项）
let pdfjsLibPromise = null;
function getPdfjsLib() {
  if (!pdfjsLibPromise) pdfjsLibPromise = import("pdfjs-dist");
  return pdfjsLibPromise;
}

/**
 * 取一份 PDF 的 document（带缓存）。
 * @param materialId  稳定标识（MaterialAsset.id），不随预签名 URL 变
 * @param url         inline?proxy=1 同源流 URL（302 到 MinIO 对 fetch 是 CORS 死路），仅首次加载用
 * @returns Promise<PDFDocumentProxy>
 */
export async function takePdfDocument(materialId, url) {
  let entry = cache.get(materialId);
  if (entry) {
    // 命中（无论在用还是闲置）：计数 +1、刷新时间戳、直接复用内存 document
    entry.refcount += 1;
    entry.lastUsed = Date.now();
    return entry.doc;
  }
  // 超上限时先淘汰最久未用的闲置项（在用项不杀）
  evictIfNeeded();
  // 首次加载：动态拉 pdfjs-dist + 发起 getDocument，promise 缓存到 entry
  const lib = await getPdfjsLib();
  const promise = lib.getDocument({
    url,
    withCredentials: true, // 同源 proxy 流需 cookie 鉴权（不跟 302，MinIO 跨源无 ACAO 必被拦）
  }).promise;
  entry = { doc: promise, refcount: 1, url, lastUsed: Date.now() };
  cache.set(materialId, entry);
  try {
    return await promise;
  } catch (e) {
    cache.delete(materialId);
    throw e;
  }
}

/**
 * 释放对一份 PDF document 的引用（refcount -1）。
 * 归零只标记闲置、保留内存数据，等待 LRU 淘汰——不再立即 destroy。
 * PdfReader 的 onBeforeUnmount 调这个，不直接 destroy。
 */
export function releasePdfDocument(materialId) {
  const entry = cache.get(materialId);
  if (!entry) return;
  entry.refcount = Math.max(0, entry.refcount - 1);
  if (entry.refcount === 0) entry.lastUsed = Date.now(); // 转为闲置，记录闲置时刻
}

/**
 * 缓存超上限时按 lastUsed 淘汰最久未用的闲置项（LRU）。
 * 全部在用（refcount>0）时不淘汰——宁多占内存也不杀掉正在渲染的 document。
 */
function evictIfNeeded() {
  if (cache.size <= MAX_CACHED) return;
  let oldestId = null;
  let oldestUsed = Infinity;
  for (const [id, entry] of cache) {
    if (entry.refcount > 0) continue; // 在用项不参与淘汰
    if (entry.lastUsed < oldestUsed) {
      oldestUsed = entry.lastUsed;
      oldestId = id;
    }
  }
  if (oldestId == null) return;
  const entry = cache.get(oldestId);
  cache.delete(oldestId);
  Promise.resolve(entry.doc)
    .then((doc) => doc?.destroy?.())
    .catch(() => {});
}

/** 换课时清掉所有 PDF 缓存（上一节课的 PDF 不再需要）。 */
export function clearPdfCache() {
  for (const [, entry] of cache) {
    Promise.resolve(entry.doc)
      .then((doc) => doc?.destroy?.())
      .catch(() => {});
  }
  cache.clear();
}
