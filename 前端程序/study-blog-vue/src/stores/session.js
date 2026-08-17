import { reactive } from "vue";
import { getCurrentUser } from "../services/auth";

export const session = reactive({ user: null, loaded: false });

// 身份加载的**唯一入口**（P1-3）。
//
// 整页刷新时有两个地方要身份：路由守卫（router.install() 里就开跑）和 App.vue 的
// onMounted。两次 /me 通常**不重叠**——App.vue 那次要排在自己的 getCsrf() 之后，
// 那时守卫的 /me 多半已经回来了——所以只靠 auth.js 里的 in-flight 单飞挡不住
// （第一发已 settle、promise 已清空，第二发照打）。
//
// 这里按 session.loaded 收口：已加载直接返回，未加载时谁先到谁负责拉、后到的
// 等同一个 promise。整页刷新因此稳定只有一次 /me，不再看两个请求谁快谁慢。
//
// session.loaded = false 是唯一的"重新拉"信号（会话过期时 App.vue 置回 false，
// 见 onSessionExpired）——绝不能因为拿到了缓存的用户就跳过重新校验。
let inflight = null;

export function ensureSession() {
  if (session.loaded) return Promise.resolve();
  if (!inflight) {
    inflight = getCurrentUser()
      .then((user) => {
        session.user = user;
      })
      .catch(() => {
        // 未登录/网络失败都落 null：调用方（守卫）只看 session.user 决定放不放行，
        // 报错交给真正的业务请求去报。
        session.user = null;
      })
      .finally(() => {
        session.loaded = true;
        inflight = null;
      });
  }
  return inflight;
}
