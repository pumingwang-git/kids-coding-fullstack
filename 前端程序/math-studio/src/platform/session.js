import { ref } from "vue";

export const isOffline = ref(false);

let currentUser = null;
let currentScope = null;

function readCsrf() {
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith("csrf_token="))
    ?.slice("csrf_token=".length) || "";
}

async function refreshSession() {
  try {
    if (!readCsrf()) await fetch("/api/auth/csrf", { credentials: "include" });
    const token = readCsrf();
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: token ? { "X-CSRF-Token": token } : {},
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function fetchMe() {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 3500);
  try {
    let response = await fetch("/api/auth/me", {
      credentials: "include",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (response.status === 401 && await refreshSession()) {
      response = await fetch("/api/auth/me", {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
    }
    if (response.status === 401 || response.status === 403) return { kind: "unauthenticated" };
    if (!response.ok) return { kind: "network-error" };
    const data = await response.json();
    if (typeof data?.id !== "number") return { kind: "unauthenticated" };
    return { kind: "user", user: { id: data.id, username: String(data.username || "同学") } };
  } catch {
    return { kind: "network-error" };
  } finally {
    window.clearTimeout(timer);
  }
}

export async function resolveSession() {
  const result = await fetchMe();
  if (result.kind === "user") {
    currentUser = result.user;
    currentScope = `u${currentUser.id}`;
    isOffline.value = false;
    localStorage.setItem("math-studio:last-user", JSON.stringify(currentUser));
    return { user: currentUser, reason: null };
  }
  if (result.kind === "network-error") {
    try {
      const cached = JSON.parse(localStorage.getItem("math-studio:last-user") || "null");
      if (typeof cached?.id === "number") {
        currentUser = cached;
        currentScope = `u${cached.id}`;
        isOffline.value = true;
        return { user: currentUser, reason: "offline" };
      }
    } catch {
      // Invalid cached state is treated as unavailable.
    }
  }
  currentUser = null;
  currentScope = null;
  return { user: null, reason: result.kind };
}

export function getUser() {
  return currentUser;
}

export function getScope() {
  if (!currentScope) throw new Error("数学星球会话尚未初始化");
  return currentScope;
}

export function csrfToken() {
  return readCsrf();
}
