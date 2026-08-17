// 后台管理 API 封装：CSRF double-submit + 统一错误文案。
// 管理端与学生端 cookie 完全隔离（admin_* 前缀），同源部署。

function cookie(name) {
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=");
}

function errorMessage(body) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const field = detail[0]?.loc?.at(-1) || "";
    const label = { username: "用户名", password: "密码" }[field] || "输入内容";
    if (detail[0]?.type === "missing") return `请填写${label}。`;
    if (detail[0]?.type === "string_too_short") return `${label}至少需要 ${detail[0]?.ctx?.min_length} 个字符。`;
    return detail[0]?.msg?.replace(/^Value error,\s*/i, "") || "输入格式不正确。";
  }
  if (typeof body?.message === "string") return body.message;
  return "请求失败，请稍后再试。";
}

async function parseBody(response) {
  return response.status === 204 ? null : response.json().catch(() => ({}));
}

async function fetchAdminCsrf() {
  const response = await fetch("/api/admin/csrf", { credentials: "include" });
  if (!response.ok) throw new Error("获取会话安全令牌失败，请刷新页面后重试。");
  const token = cookie("admin_csrf_token");
  if (!token) throw new Error("未获取到会话安全令牌。");
  return decodeURIComponent(token);
}

async function adminCsrf(forceRefresh = false) {
  const token = !forceRefresh && cookie("admin_csrf_token");
  return token ? decodeURIComponent(token) : fetchAdminCsrf();
}

// 并发 401 时共享同一次刷新：若各请求各自携带同一个旧 refresh token 调 /refresh，
// 第二个请求会被服务端判定为“轮换后重放”并吊销整个会话族，表现为隔一段时间就被迫重新登录。
let refreshPromise = null;
function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = adminRequest("/refresh", { method: "POST", body: "{}" }, false).finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

export async function adminRequest(path, options = {}, retryOnUnauthorized = true) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const isMutation = options.method && options.method !== "GET";
  if (isMutation) headers["X-CSRF-Token"] = await adminCsrf();
  const send = () => fetch(`/api/admin${path}`, { credentials: "include", ...options, headers });
  let response = await send();
  let body = await parseBody(response);
  if (isMutation && response.status === 403 && body?.detail === "CSRF 校验失败。") {
    headers["X-CSRF-Token"] = await adminCsrf(true);
    response = await send();
    body = await parseBody(response);
  }
  // 会话过期：刷新 refresh token 后重试一次（登录接口除外）
  if (retryOnUnauthorized && response.status === 401 && path !== "/login") {
    try {
      await refreshSession();
      if (isMutation) headers["X-CSRF-Token"] = await adminCsrf();
      response = await send();
      body = await parseBody(response);
    } catch {
      // 刷新失败（会话真正失效）→ 保留原始 401
    }
  }
  if (!response.ok) {
    // 错误带上 HTTP 状态码：调用方（如解析视频删除）需要区分 409 引用冲突与其它失败。
    const error = new Error(errorMessage(body));
    error.status = response.status;
    throw error;
  }
  return body;
}

// 文件上传不能预设 Content-Type，浏览器会附带 multipart boundary。
export async function adminUpload(path, formData, options = {}, retryOnUnauthorized = true) {
  const headers = { "X-CSRF-Token": await adminCsrf(), ...(options.headers || {}) };
  const send = () =>
    fetch(`/api/admin${path}`, {
      method: "POST",
      credentials: "include",
      headers,
      body: formData,
    });
  let response = await send();
  let body = await parseBody(response);
  if (response.status === 403 && body?.detail === "CSRF 校验失败。") {
    headers["X-CSRF-Token"] = await adminCsrf(true);
    response = await send();
    body = await parseBody(response);
  }
  if (retryOnUnauthorized && response.status === 401) {
    try {
      await refreshSession();
      headers["X-CSRF-Token"] = await adminCsrf();
      response = await send();
      body = await parseBody(response);
    } catch {
      // 保留原始 401，由页面统一处理会话失效。
    }
  }
  if (!response.ok) {
    // 错误带上 HTTP 状态码：调用方（如解析视频删除）需要区分 409 引用冲突与其它失败。
    const error = new Error(errorMessage(body));
    error.status = response.status;
    throw error;
  }
  return body;
}

/**
 * 下载一个受保护的文件，并直接唤起浏览器的保存流程。
 *
 * 为什么不用 `<a href download>`：那条路绕开了 adminRequest 的会话续期与错误处理，
 * 会话一过期，浏览器就把一段 JSON 报错当成文件存下来，或者干脆跳到一个 401 页面。
 * 走 fetch 拿 blob，续期、报错、文件名都还在我们手里。
 *
 * 文件名优先用服务端 Content-Disposition 里的那个（它才知道题号），取不到再用兜底名。
 */
export async function adminDownload(path, fallbackName, retryOnUnauthorized = true) {
  const send = () => fetch(`/api/admin${path}`, { credentials: "include" });
  let response = await send();
  if (retryOnUnauthorized && response.status === 401) {
    try {
      await refreshSession();
      response = await send();
    } catch {
      // 刷新失败 → 保留原始 401，下面统一抛
    }
  }
  if (!response.ok) throw new Error(errorMessage(await parseBody(response)));

  const disposition = response.headers.get("content-disposition") || "";
  // filename*=utf-8''xxx 优先：非 ASCII 文件名走的是这个字段
  const encoded = /filename\*=utf-8''([^;]+)/i.exec(disposition);
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  const name = encoded ? decodeURIComponent(encoded[1]) : plain ? plain[1] : fallbackName;

  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name || fallbackName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // 立刻撤销会让部分浏览器来不及取数据，下一帧再放
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return name;
}

export function adminLogin(payload) {
  return adminRequest("/login", { method: "POST", body: JSON.stringify(payload) }, false);
}

export function adminLogout() {
  return adminRequest("/logout", { method: "POST", body: "{}" });
}

export function adminMe() {
  return adminRequest("/me");
}

// If-Match 乐观锁封装：所有写操作必须携带服务端读到的 revision。
// 此前各页面手写 { "If-Match": String(revision) } 共 6 处，统一从这里取。
export function ifMatch(revision) {
  return { "If-Match": String(revision) };
}

export function adminSliderCaptcha() {
  return adminRequest("/captcha-slider");
}

export function adminVerifySlider(payload) {
  return adminRequest("/captcha-slider/verify", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
