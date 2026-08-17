import { ref } from "vue";
import { request } from "../services/auth";

/**
 * 课时学习进度：完成上报 + 视频节流 + 乐观更新（交接文档 14 §5 / §7.3）。
 *
 * **完成判定只有一处实现**——块组件不自己调接口，只 emit("complete") / emit("progress")，
 * 由壳统一走这里。与后端 course_access 的红线同构：加第二处就会两边不一致。
 *
 * 上报成功后用返回的 progress / unlocked_block_ids 就地更新，不重拉课时详情——
 * 那个响应带着全部图文正文，为刷一个锁图标重拉一遍太浪费。
 */
export function useLessonProgress(lessonRef) {
  const busy = ref(false);
  // blockId -> 上一次发心跳的时刻（毫秒）。按**时间**节流，不按百分比——
  // 记账要的是均匀采样，跨度节流会让快进时一拍顶很久。
  const lastBeatAt = new Map();
  // blockId -> 服务端账本快照，供界面显示「还差多久」
  const watchState = ref({});

  function applyResult(blockId, result) {
    const lesson = lessonRef.value;
    if (!lesson || !result) return;
    if (result.progress) lesson.progress = result.progress;
    const unlocked = new Set(result.unlocked_block_ids || []);
    for (const block of lesson.blocks || []) {
      if (block.id === blockId && result.completed) block.completed = true;
      if (unlocked.has(block.id)) {
        block.is_unlocked = true;
        block.lock_reason = null;
      }
    }
  }

  /**
   * 上报一个块完成。
   * @returns {Promise<{completed:boolean, unlocked_block_ids:number[]}|null>}
   */
  async function complete(blockId, source = "manual", progressPercent = 100) {
    const lesson = lessonRef.value;
    if (!lesson || !blockId || busy.value) return null;
    busy.value = true;
    try {
      const result = await request(`/api/lessons/${lesson.id}/blocks/${blockId}/complete`, {
        method: "POST",
        body: JSON.stringify({ source, progress_percent: progressPercent }),
      });
      applyResult(blockId, result);
      return result;
    } catch {
      // 上报失败不打断学习：进度是可以补的，把人卡在这里才是真的坏体验。
      // 换块时会重拉详情，届时以服务端为准。
      return null;
    } finally {
      busy.value = false;
    }
  }

  // 心跳间隔（毫秒）。服务端的 BEAT_CAP 按 3× 这个值设（45 秒），两边要一起改：
  // 心跳变稀而 BEAT_CAP 不动，正常观看会被当成"丢拍"而少记时长。
  const HEARTBEAT_MS = 15_000;

  /**
   * 视频播放心跳：把**播放位置**报给服务端记账（`POST …/watch`）。
   *
   * 与旧实现的三处差别，每一处都关乎记账正确性：
   *   1. 打 /watch 不打 /complete —— 完成与否由服务端账本裁决，客户端说了不算；
   *   2. 报位置不报百分比 —— 服务端要靠位置差算「看了多少秒」；
   *   3. 按时间节流（15 秒一拍）不按百分比跨度 —— 记账要均匀采样。
   *
   * `force` 供播放结束时立即补一拍用，绕过节流。
   */
  async function reportVideo(blockId, position, { force = false } = {}) {
    const lesson = lessonRef.value;
    if (!lesson || !blockId) return null;
    const now = Date.now();
    const last = lastBeatAt.get(blockId) ?? 0;
    if (!force && now - last < HEARTBEAT_MS) return null;
    lastBeatAt.set(blockId, now);
    try {
      const result = await request(`/api/lessons/${lesson.id}/blocks/${blockId}/watch`, {
        method: "POST",
        body: JSON.stringify({ position_seconds: Math.max(0, Math.round(position)) }),
      });
      watchState.value = { ...watchState.value, [blockId]: result };
      applyResult(blockId, result);
      return result;
    } catch {
      // 丢一拍就是丢一拍（最多 15 秒），不打断学习。下一拍照常发。
      return null;
    }
  }

  return { complete, reportVideo, busy, watchState, HEARTBEAT_MS };
}
