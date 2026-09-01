import { request } from "./auth";

const STUDENT_LINES_PATH = "/api/student/help-chat-lines";
const STUDENT_REQUESTS_PATH = "/api/student/help-requests";

export function idempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `help-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function listHelpChatLines({ page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort: "-last_message_at,-id",
  });
  return request(`${STUDENT_LINES_PATH}?${params}`);
}

export function getHelpChatLine(lineId, options = null) {
  if (!options) return request(`${STUDENT_LINES_PATH}/${encodeURIComponent(lineId)}`);
  const params = new URLSearchParams({ limit: String(options.limit || 50) });
  if (options.beforeId != null) params.set("before_id", String(options.beforeId));
  return request(`${STUDENT_LINES_PATH}/${encodeURIComponent(lineId)}?${params}`);
}

export function recallHelpMessage(messageId) {
  return request(`/api/student/help-messages/${encodeURIComponent(messageId)}/recall`, {
    method: "POST",
    body: "{}",
  });
}

export function uploadHelpAttachment(requestId, file, { requestKey, onProgress } = {}) {
  const csrf = (typeof document === "undefined" ? "" : document.cookie)
    .split("; ")
    .find((item) => item.startsWith("csrf_token="))
    ?.slice("csrf_token=".length);
  const form = new FormData();
  form.append("file", file);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/student/help-requests/${encodeURIComponent(requestId)}/attachments`);
    xhr.withCredentials = true;
    if (csrf) xhr.setRequestHeader("X-CSRF-Token", decodeURIComponent(csrf));
    xhr.setRequestHeader("Idempotency-Key", requestKey || idempotencyKey());
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new Error("网络断开，请重试。"));
    xhr.onload = () => {
      const body = JSON.parse(xhr.responseText || "{}");
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(body.detail || "图片上传失败，请重试。"));
        return;
      }
      resolve(body);
    };
    xhr.send(form);
  });
}

export function createHelpRequest(payload, { requestKey = idempotencyKey() } = {}) {
  const body = {
    class_id: payload.class_id,
    body: payload.body,
    context_type: payload.context_type || "general",
  };
  if (payload.context_id != null) body.context_id = payload.context_id;
  if (payload.context_source) body.context_source = payload.context_source;
  if (payload.problem_id_no != null) body.problem_id_no = payload.problem_id_no;

  return request(STUDENT_REQUESTS_PATH, {
    method: "POST",
    headers: { "Idempotency-Key": requestKey },
    body: JSON.stringify(body),
  });
}

export function itemsOf(payload) {
  return Array.isArray(payload?.items) ? payload.items : [];
}

export function messagesOf(payload) {
  if (Array.isArray(payload?.items)) return payload.items;
  return Array.isArray(payload?.messages) ? payload.messages : [];
}

export function subscribeToHelpChatEvents(onChange) {
  let socket;
  let stopped = false;
  let retryTimer;
  let retryDelay = 1000;

  const retry = () => {
    if (stopped) return;
    retryTimer = window.setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 30_000);
  };

  const connect = async () => {
    if (stopped) return;
    let ticket;
    try {
      ({ ticket } = await request(`${STUDENT_LINES_PATH}/events/ticket`, { method: "POST" }));
    } catch {
      retry();
      return;
    }
    if (stopped || typeof ticket !== "string") return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(
      `${protocol}//${window.location.host}/api/student/help-chat-lines/events`,
      ["help-v1", `help-ticket.${ticket}`],
    );
    socket.onopen = () => {
      retryDelay = 1000;
    };
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload?.type === "help_chat_line_changed" && payload.chat_line_id != null) {
          onChange(payload);
        }
      } catch {
        // 非法事件不影响既有 REST 读取流程。
      }
    };
    socket.onclose = () => {
      retry();
    };
  };

  connect();
  const unsubscribe = () => {
    stopped = true;
    window.clearTimeout(retryTimer);
    socket?.close();
  };
  unsubscribe.send = (payload) => {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload));
  };
  return unsubscribe;
}
