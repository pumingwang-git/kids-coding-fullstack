// 预取 / 预热的公共设施：护栏 + 三个短命缓存（课时详情 / 题面 / 播放令牌）。
// 交接文档 17 §3.4、§5 批次 2。
//
// 为什么要单独一个模块，而不是让各组件自己 fetch：**预取的发起方和消费方不是同一个
// 组件**——课包目录 hover 时发起、课时页消费；课时页停在第 3 块时发起、第 4 块的组件
// 消费。中间需要一个双方都够得着的地方放结果。
//
// 纪律（缺一条就会从"提速"变成"偷用户流量"）：
//   1. 只预取「下一步大概率会用到」的东西——hover 的那节课、相邻的那一块，不做全量；
//   2. saveData / 2g 直接不预取；
//   3. 走 requestIdleCallback，不和当前块的渲染抢主线程；
//   4. 同一目标只打一次；
//   5. **预取失败一律吞掉**——它只是提速手段，不允许影响正常链路的报错与重试。
//
// 缓存都放内存、都是"取走即消费"（take 一次就删）。刻意不落 sessionStorage：
// 这些是带权限的私有内容，留在磁盘上会活过登出。
import { request } from "./auth";

// 目录页 hover 到真正点进去，30 秒足够；超过就该重取了（进度/解锁状态会变）。
const LESSON_TTL_MS = 30_000;
// 命中缓存后数据在多旧时触发后台复核（P2）。目录 hover → 点击进入的常见间隔是
// 1~3 秒，刚预取完就消费不值得再打一次请求；隔了十几秒再进同一课时（返回目录、
// 切走切回）数据可能已过期，取旧数据的同时在后台刷一次，为下一次进入准备新数据。
const LESSON_REFRESH_MS = 10_000;

/** 用户是否愿意让我们花这份流量。没有 Network Information API 的浏览器按"愿意"处理。 */
export function canPrefetch() {
  const conn = navigator.connection;
  if (!conn) return true;
  if (conn.saveData === true) return false;
  // effectiveType 为 "2g" / "slow-2g" 时，预取只会拖慢当前真正要用的请求
  return !/(^|-)2g$/.test(conn.effectiveType || "");
}

/**
 * 空闲时执行。requestIdleCallback 在 Safari 与 jsdom 里都没有，退回一个短 setTimeout。
 * 护栏在这里统一兜住：不该预取时连回调都不排，调用方不必每处再判一次。
 */
export function idle(fn) {
  if (!canPrefetch()) return;
  if (typeof requestIdleCallback === "function") requestIdleCallback(fn, { timeout: 2000 });
  else setTimeout(fn, 300);
}

// ---------------------------------------------------------------------------
// 课时详情：课包目录 hover 时预取，课时页 load() 时消费
// ---------------------------------------------------------------------------

const lessons = new Map(); // lessonId -> { at, promise }

/** 预取一节课时的详情。重复调用（鼠标反复扫过）只会真的打一次。 */
export function prefetchLesson(lessonId, force = false) {
  if (!canPrefetch()) return;
  const hit = lessons.get(lessonId);
  if (!force && hit && Date.now() - hit.at < LESSON_TTL_MS) return;
  // force 复核时先存旧 promise 引用——catch 兜底要用它，不能现场 lessons.get()：
  // 下面 set 之后条目已被覆盖成新 promise，catch 里再取会拿到它自己（自引用死锁）。
  const oldPromise = hit ? hit.promise : null;
  const promise = request(`/api/lessons/${lessonId}`).catch(() => {
    // 复核失败保留旧数据；首次预取失败落 null（消费方走正常请求重来一遍）。
    // 如果直接落 null 会把已命中的好缓存覆盖掉，网络抖动反而多打一次请求。
    return oldPromise || null;
  });
  lessons.set(lessonId, { at: Date.now(), promise });
}

/**
 * 取预取结果，**同步返回 promise 或 null**（不是 async 函数）。
 *
 * 同步很关键：调用方要靠"有没有 pending 的预取"来决定加载页的延迟计时器怎么排。
 * 返回的 promise 可能还在飞——await 它正好，这样也不会重复发一次请求。
 *
 * P2 起**取走不删**：TTL 内再次进入同一课时（返回目录再进、切走切回）直接复用，
 * 不再重新请求。数据偏旧（≥ LESSON_REFRESH_MS）时后台复核一次，为下次进入准备
 * 新数据。F5 / 关标签页后内存清空、必然重新请求——带权限和进度的数据本就不该
 * 落持久缓存，属于正常设计。
 */
export function takeLesson(lessonId) {
  const hit = lessons.get(lessonId);
  if (!hit || Date.now() - hit.at > LESSON_TTL_MS) {
    lessons.delete(lessonId);
    return null;
  }
  if (Date.now() - hit.at >= LESSON_REFRESH_MS) prefetchLesson(lessonId, true);
  return hit.promise;
}

// ---------------------------------------------------------------------------
// 块级预热：题面 / 播放令牌
// 都按 blockId 存。换课时时 clearBlockPrefetch()——块 id 不跨课时复用，但令牌是
// 按课时签的，留着上一节课的东西只会带来诡异的 403。
// ---------------------------------------------------------------------------

const problems = new Map(); // blockId -> Promise<data|null>
const playTokens = new Map(); // blockId -> Promise<payload|null>

/** 预取课中练习的题面。BlockPractice 挂载时 takeProblem 消费。 */
export function prefetchProblem(lessonId, blockId) {
  if (!canPrefetch() || problems.has(blockId)) return;
  problems.set(
    blockId,
    request(`/api/lessons/${lessonId}/blocks/${blockId}/problem`).catch(() => null),
  );
}

export function takeProblem(blockId) {
  const promise = problems.get(blockId) || null;
  problems.delete(blockId);
  return promise;
}

/**
 * 预签播放令牌。**返回的 promise 会被 VideoPlayer await**，所以即使播放器已经挂载、
 * 令牌还没签回来，也只会签这一次——不存在"预取和自签撞车签两次"的竞态。
 *
 * payload 里补一个 minted_at：expires_in_seconds 是相对值，消费方要靠签发时刻
 * 才能算出还剩多久（预签的令牌可能在缓存里躺了一会儿）。
 */
export function prefetchPlayToken(lessonId, blockId) {
  if (!blockId || playTokens.has(blockId)) return;
  playTokens.set(
    blockId,
    request(`/api/lessons/${lessonId}/play`, {
      method: "POST",
      body: JSON.stringify({ block_id: blockId }),
    })
      .then((data) => ({ ...data, minted_at: Date.now() }))
      .catch(() => null),
  );
}

export function takePlayToken(blockId) {
  const promise = playTokens.get(blockId) || null;
  playTokens.delete(blockId);
  return promise;
}

/** 离开课时时清掉块级缓存。课时详情缓存不清——目录页可能马上还要用。 */
export function clearBlockPrefetch() {
  problems.clear();
  playTokens.clear();
  materials.clear();
}

/** 清掉课时详情缓存（测试清理 / 登出时调用）。生产代码不主动调——TTL 自过期。 */
export function clearLessonPrefetch() {
  lessons.clear();
}

// ---------------------------------------------------------------------------
// 资料预热：停在第 N 块时把第 N+1 块第一份可内嵌资料的前 256KB 先拿了
// （交接文档 17 §5 S2-4）。走 inline?proxy=1 同源流（302 到 MinIO 对 fetch 是
// 死路——对象 GET 响应不带 ACAO，跨源必被 CORS 拦，2026-08-14 实测）；proxy 流
// 同样带 ETag / Cache-Control，浏览器 HTTP 缓存会留下这段字节，学生切过去时
// PDF.js 取首页直接走缓存。
//
// 只预热**第一份可内嵌**资料（和 BlockMaterials 的默认选中口径一致），
// 不全量预热整块资料——那是白烧流量。
// ---------------------------------------------------------------------------
const materials = new Set(); // 已预热的 material_id，去重

function canEmbedMaterial(material) {
  const mime = (material.mime_type || "").toLowerCase();
  return (
    /^image\//.test(mime) ||
    /^text\/(markdown|plain|x-markdown)/.test(mime) ||
    mime === "application/pdf" ||
    /^video\//.test(mime) ||
    /^audio\//.test(mime)
  );
}

/**
 * 预热一份资料的前 256KB（或小于 2MB 时整份）。
 * @param lessonId  当前课时
 * @param blockId   资料所在块
 * @param material  块 DTO 里的 material 条目（含 material_id / mime_type / size_bytes）
 */
export function prefetchMaterial(lessonId, blockId, material) {
  if (!canPrefetch()) return;
  if (!material || materials.has(material.material_id)) return;
  materials.add(material.material_id);

  // ?proxy=1：fetch 不能跟 302 到 MinIO（对象 GET 响应不带 ACAO，跨源必被 CORS
  // 拦截——2026-08-14 实测，此前预热一直在静默失败）。proxy 同源流一样有
  // ETag / Cache-Control:private,max-age=600，浏览器缓存照常留下这段字节，
  // 学生切过去时 PDF.js 取首页直接命中缓存。
  const url = `/api/lessons/${lessonId}/blocks/${blockId}/materials/${material.material_id}/inline?proxy=1`;
  // 小文件（< 2MB）整份取——反正一整个 TCP 窗口就传完了，省一次 Range 协商；
  // 大文件只取前 256KB——PDF 的 xref 目录在尾部，但首页 + 渲染初始化靠前 256KB 够了，
  // 尾部目录等学生真翻到时 PDF.js 会按 Range 取（那时走的是已预热的连接）。
  const small = (material.size_bytes || 0) > 0 && material.size_bytes <= 2 * 1024 * 1024;
  const headers = small ? {} : { Range: "bytes=0-262143" };
  // 失败吞掉（预取纪律第 5 条）：网络抖动/权限变化不影响正常链路。
  // credentials 带 cookie 过鉴权。
  fetch(url, { credentials: "include", headers }).catch(() => {});
}
