// 自动保存：按题防抖、切题强制冲、失败退避重试。
//
// 三条约束来自考试场景，别按普通表单的直觉改：
// 1. 同一题连续改只发最后一次（选项狂点、代码狂敲）；
// 2. 切题必须先把上一题冲出去——学员的心智是"我离开这题时它就存好了"；
// 3. 保存失败绝不清空本地内容，退避重试，仍失败则明确告警。

import { ref } from "vue";

export function createAutosave({ save, delay = 1500, retries = 3, retryBase = 400 }) {
  const status = ref("idle"); // idle / saving / saved / error
  const pending = new Map(); // problemIdNo -> answer（后写覆盖先写）
  const timers = new Map();
  let inflight = 0;

  function schedule(problemIdNo, answer, { immediate = false } = {}) {
    pending.set(problemIdNo, answer);
    const existing = timers.get(problemIdNo);
    if (existing) clearTimeout(existing);
    if (immediate) return flushOne(problemIdNo);
    timers.set(
      problemIdNo,
      setTimeout(() => {
        timers.delete(problemIdNo);
        flushOne(problemIdNo);
      }, delay),
    );
    return Promise.resolve();
  }

  async function flushOne(problemIdNo) {
    const timer = timers.get(problemIdNo);
    if (timer) {
      clearTimeout(timer);
      timers.delete(problemIdNo);
    }
    if (!pending.has(problemIdNo)) return;
    const answer = pending.get(problemIdNo);
    pending.delete(problemIdNo);

    inflight += 1;
    status.value = "saving";
    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        await save(problemIdNo, answer);
        inflight -= 1;
        if (inflight === 0 && status.value !== "error") status.value = "saved";
        return;
      } catch (error) {
        // 409 是"考试已结束/已交卷"，重试多少次都一样，直接抛给调用方处理。
        if (error?.status === 409 || attempt === retries) {
          inflight -= 1;
          status.value = "error";
          pending.set(problemIdNo, answer); // 保留内容，等下一次 flush 或用户手动重试
          throw error;
        }
        await new Promise((resolve) => setTimeout(resolve, retryBase * 2 ** attempt));
      }
    }
  }

  /** 切题、交卷前调用：把所有挂起的写出去。 */
  async function flushAll() {
    await Promise.allSettled([...pending.keys()].map((key) => flushOne(key)));
  }

  function hasPending() {
    return pending.size > 0;
  }

  function cancelAll() {
    timers.forEach((timer) => clearTimeout(timer));
    timers.clear();
    pending.clear();
  }

  return { status, schedule, flushOne, flushAll, hasPending, cancelAll };
}
