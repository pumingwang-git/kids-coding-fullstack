// 考试时钟：倒计时、与服务端对表、考中提醒。
//
// 本地系统时钟一律不信任——学员把电脑时间往前调不能延长考试。做法是记下
// "服务端时间 - 本地时间" 的偏移量，此后所有判断都用「本地时间 + 偏移量」。
// 每次接口响应都带 server_now，拿到就 sync() 一次，偏移量始终是新的。

/**
 * @param {object} options
 * @param {string|null} options.deadlineAt  ISO 字符串；null 表示不限时
 * @param {string} options.serverNow        ISO 字符串，建钟时的服务端时间
 * @param {string} options.remindMinutes    后端已规范化的降序逗号串，如 "30,10,5"
 * @param {(minute: number) => void} options.onRemind
 * @param {() => void} options.onExpire
 * @param {() => number} [options.localNow]  注入用，测试里替换成可控时钟
 */
export function createExamClock({
  deadlineAt,
  serverNow,
  remindMinutes = "",
  onRemind = () => {},
  onExpire = () => {},
  localNow = () => Date.now(),
}) {
  const deadline = deadlineAt ? Date.parse(deadlineAt) : null;
  let offset = Date.parse(serverNow) - localNow();
  // 后端存的就是「去重 + 降序」的规范形式，这里不再排序去重（重复且容易漏）。
  const thresholds = String(remindMinutes || "")
    .split(",")
    .map((item) => Number.parseInt(item, 10))
    .filter((item) => Number.isFinite(item) && item > 0);
  const fired = new Set();
  let expired = false;

  function serverTime() {
    return localNow() + offset;
  }

  /** 剩余毫秒；不限时返回 null。 */
  function remainingMs() {
    return deadline === null ? null : Math.max(deadline - serverTime(), 0);
  }

  /** 用任意一次接口响应里的 server_now 重新对表，不额外发请求。 */
  function sync(nextServerNow) {
    if (!nextServerNow) return;
    const parsed = Date.parse(nextServerNow);
    if (Number.isFinite(parsed)) offset = parsed - localNow();
  }

  /** 每秒调一次。触发过的提醒点不再触发——倒计时抖动会让同一个点反复命中。 */
  function tick() {
    const remaining = remainingMs();
    if (remaining === null) return null;
    const minutesLeft = remaining / 60000;
    for (const minute of thresholds) {
      if (!fired.has(minute) && minutesLeft <= minute && remaining > 0) {
        fired.add(minute);
        onRemind(minute);
      }
    }
    if (remaining <= 0 && !expired) {
      expired = true;
      onExpire();
    }
    return remaining;
  }

  return {
    remainingMs,
    sync,
    tick,
    serverTime,
    isExpired: () => expired,
    unlimited: deadline === null,
  };
}

/** 毫秒 → mm:ss / hh:mm:ss。倒计时和正计时共用。 */
export function formatDuration(ms) {
  const total = Math.max(Math.floor((ms || 0) / 1000), 0);
  const seconds = String(total % 60).padStart(2, "0");
  const minutes = String(Math.floor(total / 60) % 60).padStart(2, "0");
  const hours = Math.floor(total / 3600);
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${minutes}:${seconds}`
    : `${minutes}:${seconds}`;
}
