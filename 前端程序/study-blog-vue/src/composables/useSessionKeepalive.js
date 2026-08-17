// 主动续期（文档17 P1）。设计对齐 VideoPlayer 的播放令牌续签：定时 + 可见性 + 冷却期防风暴。
//
// 为什么需要：access_token 只活 access_token_minutes 分钟，课时页是长驻页面——不主动续就会
// 在 15 分钟后必然 401。Layer 1（被动续期）能救回来，但用户要吃一次"多 RTT 的卡顿"，
// PracticeCoding 的 250ms 轮询撞上更是可见停顿。主动续期让 401 变成兜底而不是常态。
//
// 三个触发时机（缺一个就有一类场景漏网）：
//   1. 定时——距过期剩 20% 生命周期时续（15min→剩 3min 时续）
//   2. 页面恢复可见——合笔记本休眠 2 小时再打开，剩余不足半衰期则立刻续
//   3. 网络恢复——断网期间的失败不该当会话失效
//
// 时机由 /me 响应的 access_expires_at（绝对过期 ISO）+ access_token_minutes（生命周期）算，
// 不把 15 分钟硬编码两份。续期成功后用 /refresh 响应的 access_expires_at 更新 session.user，
// 下次定时器按新 exp 算——/refresh 经 create_login_response 返回这个字段。
// 失败交给 Layer 5（P2 的 session:expired 事件），这里不弹窗。
import { onBeforeUnmount, onMounted } from "vue";
import { refreshSession } from "../services/auth";
import { session } from "../stores/session";

const AHEAD_RATIO = 0.2; // 距过期剩 20% 生命周期时续
const VISIBLE_RATIO = 0.5; // 页面恢复可见时，剩余不足半衰期则立刻续
const COOLDOWN_MS = 60_000; // 两次续期最小间隔，防风暴（refreshSession 自身还有 5s 冷却期兜底）
const CHECK_INTERVAL_MS = 60_000; // 每分钟检查一次剩余时间

export function useSessionKeepalive() {
  let timer = null;
  let lastRefreshAt = 0;

  function lifetimeMs() {
    const m = session.user?.access_token_minutes;
    return m ? m * 60_000 : 0;
  }
  function expMs() {
    const iso = session.user?.access_expires_at;
    return iso ? new Date(iso).getTime() : 0;
  }

  async function tick(force = false) {
    if (!session.user) return; // 未登录不刷
    if (!force && Date.now() - lastRefreshAt < COOLDOWN_MS) return;
    const exp = expMs();
    const lifetime = lifetimeMs();
    if (!exp || !lifetime) return; // /me 还没回来或没带字段，等下一轮
    if (!force && exp - Date.now() > lifetime * AHEAD_RATIO) return; // 还没到续期窗口
    try {
      const body = await refreshSession();
      // /refresh 响应带 access_expires_at（create_login_response），更新它，
      // 下次定时器按新 exp 算。被动续期（401 触发）不走这里，但 cooldown 能挡住重复触发。
      if (body?.access_expires_at && session.user) {
        session.user.access_expires_at = body.access_expires_at;
      }
      lastRefreshAt = Date.now();
    } catch {
      // 续期失败（会话真死/网抖）交给 Layer 5，不在这里弹窗
    }
  }

  function onVisible() {
    if (document.visibilityState !== "visible" || !session.user) return;
    const lifetime = lifetimeMs();
    const remaining = expMs() - Date.now();
    // 休眠/切走回来：剩余不足半衰期才续。remaining 很大说明 token 还新，不浪费一次续期
    if (lifetime && remaining < lifetime * VISIBLE_RATIO) tick(true);
  }

  function onOnline() {
    tick(true); // 断网恢复，检查一下
  }

  onMounted(() => {
    timer = setInterval(() => tick(), CHECK_INTERVAL_MS);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onOnline);
  });
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onOnline);
  });
}
