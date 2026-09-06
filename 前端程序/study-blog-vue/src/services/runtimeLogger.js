const DEV = Boolean(import.meta.env?.DEV);

function requestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function safePath(url) {
  try {
    return new URL(url, globalThis.location?.origin || "http://localhost").pathname;
  } catch {
    return String(url).split("?")[0];
  }
}

function emit(level, message, fields = {}) {
  const payload = { message, ...fields };
  if (DEV && typeof console[level] === "function") console[level]("[runtime]", payload);
  if (!DEV && level === "error" && typeof console.error === "function") {
    // 生产只保留失败事件，避免把学习内容或请求参数写进浏览器日志。
    console.error("[runtime]", payload);
  }
}

export function beginRequest(url) {
  const id = requestId();
  const started = performance.now();
  emit("debug", "request started", { request_id: id, path: safePath(url) });
  return { id, started };
}

export function completeRequest(context, url, status) {
  emit("debug", "request completed", {
    request_id: context.id,
    path: safePath(url),
    status_code: status,
    duration_ms: Math.round((performance.now() - context.started) * 100) / 100,
  });
}

export function failRequest(context, url, error) {
  emit("error", "request failed", {
    request_id: context.id,
    path: safePath(url),
    status_code: error?.status ?? 0,
    code: error?.code ?? null,
    duration_ms: Math.round((performance.now() - context.started) * 100) / 100,
  });
}
