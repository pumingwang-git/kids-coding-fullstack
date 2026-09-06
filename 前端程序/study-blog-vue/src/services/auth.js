const apiBase = import.meta.env.VITE_API_BASE_URL || "";

import { beginRequest, completeRequest, failRequest } from "./runtimeLogger";

const fieldNames = {
  username: "用户名",
  email: "邮箱",
  password: "密码",
  identifier: "用户名或邮箱",
  code: "验证码",
};

function validationMessage(item) {
  if (typeof item === "string") return item;
  if (!item || typeof item !== "object") return "";

  const field = Array.isArray(item.loc) ? item.loc.at(-1) : "";
  const label = fieldNames[field] || "输入内容";
  if (item.type === "missing") return `请填写${label}。`;
  if (item.type === "string_too_short") return `${label}至少需要 ${item.ctx?.min_length} 个字符。`;
  if (item.type === "string_too_long") return `${label}不能超过 ${item.ctx?.max_length} 个字符。`;
  if (item.type === "string_pattern_mismatch") return `${label}格式不正确。`;
  return item.msg?.replace(/^Value error,\s*/i, "") || `${label}格式不正确。`;
}

function errorMessage(body) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(validationMessage).filter(Boolean);
    if (messages.length) return messages.join("；");
  }
  if (detail && typeof detail === "object" && typeof detail.message === "string")
    return detail.message;
  if (typeof body?.message === "string") return body.message;
  return "请求失败，请稍后再试。";
}

function cookie(name) {
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=");
}

async function fetchCsrfToken() {
  const response = await fetch(`${apiBase}/api/auth/csrf`, { credentials: "include" });
  if (!response.ok) throw new Error("获取会话安全令牌失败，请刷新页面后重试。");
  const token = cookie("csrf_token");
  if (!token) throw new Error("未获取到会话安全令牌，请确认前端与接口使用同一地址访问。");
  return decodeURIComponent(token);
}

async function csrfToken(forceRefresh = false) {
  const token = !forceRefresh && cookie("csrf_token");
  return token ? decodeURIComponent(token) : fetchCsrfToken();
}

// 并发 401 时共享同一次刷新：若各请求各自携带同一个旧 refresh token 调 /refresh，
// 第二个请求会被服务端判定为“轮换后重放”并吊销整个会话族，导致用户被强制登出。
let refreshPromise = null;

// —— 续期失败后的两道闸 ——
// 单飞只管"同一时刻"，管不到"接连不断"：refreshPromise 在 finally 里清空（失败也清），
// 所以会话一旦真死，页面上每个后续请求都会各自再打一次 /refresh。
// 失败要分两种处理，混为一谈就会各错一半：
//   /refresh 回 401 = 会话真没了，刷一万次也一样 → 上闩，后续请求直接失败，不再打网络。
//   网络错误 / 5xx  = 可能只是网抖了一下 → 只上冷却期，冷却过后允许再试，不能把人锁死。
// 尤其要避免的是"轮换成功但响应丢失"（弱网、切网）后的连环重试：同一个旧令牌反复送上去，
// 一旦超出服务端 30 秒重放宽限期就会命中 reuse_detected 吊销整个会话族——
// 那等于把一次网络抖动升级成强制登出。服务端另有 refresh-token 桶兜底，见 auth_secure.refresh。
let sessionDead = false;
let refreshBlockedUntil = 0;
const REFRESH_COOLDOWN_MS = 5000;

/** 登录成功后解闩。续期成功也会解——那说明会话又活了。 */
export function resetSessionState() {
  sessionDead = false;
  refreshBlockedUntil = 0;
}

function sessionGoneError() {
  const error = new Error("登录已失效，请重新登录。");
  error.status = 401;
  return error;
}

/** 续期。**导出给 exam.js 共用同一个 promise**：两个模块各自持有一份的话，
 *  并发 401 会拿同一个旧 refresh token 各刷一次，白白触发一次令牌重放判定。 */
export function refreshSession() {
  if (sessionDead) return Promise.reject(sessionGoneError());
  if (Date.now() < refreshBlockedUntil) {
    const error = new Error("续期失败，请稍后重试。");
    error.status = 0; // 不是服务端给的状态，调用方别拿它当 401 处理
    return Promise.reject(error);
  }
  if (!refreshPromise) {
    refreshPromise = request("/refresh", { method: "POST", body: "{}" })
      .then((body) => {
        resetSessionState();
        return body;
      })
      .catch((error) => {
        // 429 也算"服务端明确拒绝但会话没死"，跟网络错误一样只冷却，不上闩。
        if (error?.status === 401) {
          sessionDead = true;
          // 会话真死，通知全局接管（文档17 P2）：App.vue 清 session + 跳 /auth?next=...。
          // sessionDead 上闩后后续请求不再进 catch，事件只发一次。
          if (typeof window !== "undefined")
            window.dispatchEvent(new CustomEvent("session:expired"));
        } else {
          refreshBlockedUntil = Date.now() + REFRESH_COOLDOWN_MS;
        }
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

async function parseBody(response) {
  return response.status === 204 ? null : response.json().catch(() => ({}));
}

// 这些接口的 401 是"凭据不对"而不是"会话过期"，续期救不回来，只会平白多打一次 /refresh。
// /refresh 自己也必须在列——否则续期失败会递归触发续期。
const NO_REFRESH =
  /^\/(login|register|refresh|csrf|captcha|password-reset|verify-email|resend-verification)/;

/**
 * @param retryOnUnauthorized 401 时自动续期并重放。**默认开**，与后台的 adminRequest 一致。
 *
 * 默认值曾经是 false，于是每个业务调用点都得自己记得传 true——9 个调用点一个都没传，
 * access_token 只活 15 分钟而课时页是长驻页面，结果"看完视频点练习"必然弹「登录已过期」，
 * 手动刷新才好（整页重载会走 getCurrentUser，那是当时唯一传了 true 的调用）。
 * 漏传不会立刻暴露、要等 15 分钟才现形，所以这个默认值只能是 true，例外走上面的白名单。
 */
async function request(path, options = {}, retryOnUnauthorized = true) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const isMutation = options.method && options.method !== "GET";
  if (isMutation) {
    headers["X-CSRF-Token"] = await csrfToken();
  }
  // path 以 /api/ 开头视为绝对路径（如 /api/lessons/2/play，绕过 /api/auth 前缀）
  const url = path.startsWith("/api/") ? `${apiBase}${path}` : `${apiBase}/api/auth${path}`;
  const context = beginRequest(url);
  const send = () => fetch(url, { credentials: "include", ...options, headers: { ...headers, "X-Request-ID": context.id } });
  let response;
  try {
    response = await send();
  } catch (error) {
    failRequest(context, url, error);
    throw error;
  }
  let body = await parseBody(response);
  if (isMutation && response.status === 403 && body?.detail === "CSRF 校验失败。") {
    headers["X-CSRF-Token"] = await csrfToken(true);
    response = await send();
    body = await parseBody(response);
  }
  if (retryOnUnauthorized && !NO_REFRESH.test(path) && response.status === 401) {
    try {
      await refreshSession();
      if (isMutation) headers["X-CSRF-Token"] = await csrfToken();
      response = await send();
      body = await parseBody(response);
    } catch {
      // Keep the original 401 when refresh fails or the session was revoked.
    }
  }
  if (!response.ok) {
    // status 是 refreshSession 判断"会话真死"还是"网抖了"的唯一依据，不能只抛文案。
    // message 保持原样——调用方读的都是 err.message，加字段不影响它们。
    const error = new Error(errorMessage(body));
    error.status = response.status;
    error.code = body?.detail?.code ?? null;
    failRequest(context, url, error);
    throw error;
  }
  completeRequest(context, url, response.status);
  return body;
}

export { request };

export async function getCsrf() {
  return request("/csrf");
}
export async function getCaptcha() {
  return request("/captcha");
}

// 单飞（P1-3 的第二道保险）：真同时发起时共享同一个 in-flight promise，只打一次请求。
// settle 后清空——登出/换号后的下次调用必须重新拉，绝不能复用旧会话的结果。
// 注意这一条挡不住"守卫先拉完、App.vue 才轮到"的**串行**重复（那时 promise 已清空），
// 整页刷新只打一次的保证在 stores/session.ensureSession 的 session.loaded 收口。
let mePromise = null;
export function getCurrentUser() {
  if (!mePromise) {
    mePromise = request("/me").finally(() => {
      mePromise = null;
    });
  }
  return mePromise;
}
export async function register(payload) {
  return request("/register", { method: "POST", body: JSON.stringify(payload) });
}
export async function login(payload) {
  const body = await request("/login", { method: "POST", body: JSON.stringify(payload) });
  resetSessionState(); // 上一个会话死掉时上的闩，新会话必须解开，否则这个页面再也不会续期
  mePromise = null; // 同上：换号后 AuthView 那次 getCurrentUser 必须真去拉新用户
  return body;
}
export async function verifyEmail(payload) {
  return request("/verify-email", { method: "POST", body: JSON.stringify(payload) });
}
export async function resendVerification(payload) {
  return request("/resend-verification", { method: "POST", body: JSON.stringify(payload) });
}
export async function requestPasswordReset(payload) {
  return request("/password-reset/request", { method: "POST", body: JSON.stringify(payload) });
}
export async function confirmPasswordReset(payload) {
  return request("/password-reset/confirm", { method: "POST", body: JSON.stringify(payload) });
}
export async function requestPasswordChangeVerification(payload) {
  return request("/password-change/request", { method: "POST", body: JSON.stringify(payload) });
}
export async function setupMfa() {
  return request("/mfa/setup", { method: "POST", body: "{}" });
}
export async function confirmMfa(payload) {
  return request("/mfa/confirm", { method: "POST", body: JSON.stringify(payload) });
}
export async function changePassword(payload) {
  // 改密会吊销全部旧会话并当场签发一个新的（后端 create_login_response），
  // 和 login 一样属于"新会话诞生"的入口，闩要跟着解。
  const body = await request("/password-change", { method: "POST", body: JSON.stringify(payload) });
  resetSessionState();
  return body;
}
export async function logout() {
  // 身份边界：登出后绝不能让还在飞的那次 /me 把上一个用户的资料交给下一次调用
  mePromise = null;
  return request("/logout", { method: "POST", body: "{}" });
}

// ---------- 学生个人资料（文档 28 P2） ----------

export async function getProfile() {
  return request("/api/student/profile");
}
export async function updateProfile(payload) {
  return request("/api/student/profile", { method: "PATCH", body: JSON.stringify(payload) });
}
/**
 * 头像上传。FormData 走独立实现而不是 request()：multipart 的 Content-Type
 * 必须由浏览器带上 boundary，request() 固定塞 application/json 会直接判 400。
 * CSRF 续期重试逻辑与 request() 保持同一套（403 强制刷新 token 重放 / 401 续期重放）。
 */
export async function uploadAvatar(file) {
  const form = new FormData();
  form.append("file", file);
  const url = `${apiBase}/api/student/profile/avatar`;
  const send = (headers) =>
    fetch(url, { method: "POST", credentials: "include", headers, body: form });
  let response = await send({ "X-CSRF-Token": await csrfToken() });
  let body = await parseBody(response);
  if (response.status === 403 && body?.detail === "CSRF 校验失败。") {
    response = await send({ "X-CSRF-Token": await csrfToken(true) });
    body = await parseBody(response);
  }
  if (response.status === 401) {
    try {
      await refreshSession();
      response = await send({ "X-CSRF-Token": await csrfToken() });
      body = await parseBody(response);
    } catch {
      // 会话真死时保留原始 401，由调用方（资料页）统一提示重新登录。
    }
  }
  if (!response.ok) {
    const error = new Error(errorMessage(body));
    error.status = response.status;
    throw error;
  }
  return body;
}
