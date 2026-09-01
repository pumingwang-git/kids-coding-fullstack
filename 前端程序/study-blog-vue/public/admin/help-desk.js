import { adminRequest, adminUpload, ifMatch } from "./admin-api.js";
import { escapeHtml, fmtTime } from "./admin-ui.js";
import { initLayout } from "./admin-layout.js";

const PAGE_SIZE = 20;
const CHAT_PAGE_SIZE = 40;
const EMOJIS = ["🙂", "😊", "👍", "👏", "💡", "🤔", "✅", "🎯", "💪", "🙏", "📌", "🌟"];

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function nestedName(value) {
  if (!value || typeof value !== "object") return "";
  return firstValue(value.display_name, value.username, value.name, value.title, "");
}

function studentName(item) {
  return firstValue(nestedName(item.student), item.student_name, item.student_username, "学生");
}

function className(item) {
  return firstValue(nestedName(item.class), item.class_name, item.class_title, "班级信息暂缺");
}

function lastStudentBody(item) {
  return firstValue(
    item.last_student_message?.body,
    item.last_message?.sender_type === "student" ? item.last_message.body : null,
    item.last_student_message_body,
    item.body,
    "学生尚未留下文字问题。",
  );
}

function waitingLabel(item) {
  return firstValue(
    item.waiting_status?.label,
    item.waiting_status_label,
    item.status_label,
    "等待状态暂缺",
  );
}

function waitingTone(item) {
  const tone = firstValue(
    item.waiting_status?.tone,
    item.waiting_status_tone,
    item.status_tone,
    "neutral",
  );
  return ["danger", "warning", "success", "neutral"].includes(tone) ? tone : "neutral";
}

function activeRequest(detail) {
  const requests = Array.isArray(detail.requests)
    ? detail.requests
    : Array.isArray(detail.help_requests)
      ? detail.help_requests
      : [];
  return firstValue(
    detail.active_help_request,
    detail.current_help_request,
    detail.help_request,
    requests.find((item) => item.status === "open"),
    requests[0],
    null,
  );
}

export function messageRows(detail) {
  const rows = Array.isArray(detail.messages)
    ? detail.messages
    : (Array.isArray(detail.requests)
        ? detail.requests
        : Array.isArray(detail.help_requests)
          ? detail.help_requests
          : []
      ).flatMap((request) => (Array.isArray(request.messages) ? request.messages : []));
  return [...rows].sort((left, right) => {
    const byTime = String(left.created_at || "").localeCompare(String(right.created_at || ""));
    if (byTime !== 0) return byTime;
    const leftId = Number(left.id);
    const rightId = Number(right.id);
    if (Number.isFinite(leftId) && Number.isFinite(rightId)) return leftId - rightId;
    return String(left.id || "").localeCompare(String(right.id || ""));
  });
}

function contextText(detail) {
  return detail.context_label ?? "";
}

function metadataOnly(detail) {
  return (
    detail.access_mode === "metadata" ||
    detail.can_view_content === false ||
    detail.content_visible === false
  );
}

function idempotencyKey() {
  return (
    globalThis.crypto?.randomUUID?.() ||
    `help-reply-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}

export function createRetryKeyCache(makeKey = idempotencyKey) {
  let failedAttempt = null;
  return {
    keyFor(requestId, body) {
      return failedAttempt?.requestId === requestId && failedAttempt.body === body
        ? failedAttempt.key
        : makeKey();
    },
    markFailed(requestId, body, key) {
      failedAttempt = { requestId, body, key };
    },
    markSucceeded() {
      failedAttempt = null;
    },
  };
}

export function queueItemMarkup(item, selected = false) {
  const waiting = Number(item.waiting_seconds);
  const seconds =
    Number.isFinite(waiting) && waiting >= 0 ? formatWaitingSeconds(waiting) : "暂未返回";
  const lastAt = firstValue(item.last_message_at, item.updated_at, item.created_at);
  if (!("context_label" in item) || !("unread_count" in item) || !("has_attachments" in item)) {
    throw new Error("答疑队列缺少服务端字段：context_label、unread_count 或 has_attachments");
  }
  const task = item.context_label;
  const unread = Number(item.unread_count);
  const hasAttachment = item.has_attachments === true;
  return `<button class="help-queue-card${selected ? " is-selected" : ""}" type="button" data-line-id="${escapeHtml(item.id)}" aria-pressed="${selected}">
    <span class="help-queue-card-top"><strong>${escapeHtml(studentName(item))}</strong><span>${escapeHtml(lastAt ? fmtTime(lastAt) : "")}</span></span>
    <span class="help-queue-card-class">${escapeHtml(className(item))}</span><span class="help-queue-card-task">${escapeHtml(task)}</span>
    <span class="help-queue-card-bottom"><span class="help-waiting-status" data-tone="${escapeHtml(waitingTone(item))}">${escapeHtml(waitingLabel(item))}</span><span>已等待 ${escapeHtml(seconds)}</span>${hasAttachment ? '<span class="help-attachment-badge">含附件</span>' : ""}${unread ? `<span class="help-unread-badge">${escapeHtml(unread)}</span>` : ""}</span>
  </button>`;
}

export function formatWaitingSeconds(value) {
  const total = Math.max(0, Math.floor(Number(value)));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return minutes ? `${minutes} 分 ${seconds} 秒` : `${seconds} 秒`;
}

export function messageMarkup(message) {
  const isStudent =
    message.sender_type === "student" ||
    Boolean(message.sender_user_id) ||
    message.role === "student";
  const sender = firstValue(message.sender_label, isStudent ? "学生" : "教师");
  const recalled = message.recalled === true;
  const attachments = recalled ? [] : (Array.isArray(message.attachments) ? message.attachments : []);
  const attachmentMarkup = attachments
    .map((attachment) => {
      const url = firstValue(attachment.url, attachment.download_url, attachment.view_url, "");
      if (!url) return "";
      return `<a class="help-message-image" href="${escapeHtml(url)}" target="_blank" rel="noopener"><img src="${escapeHtml(url)}" alt="${escapeHtml(attachment.original_name || "消息图片")}" loading="lazy" /></a>`;
    })
    .join("");
  const recallControl = !isStudent && message.can_recall === true && !recalled
    ? `<button class="btn-text help-message-recall" type="button" data-recall-message-id="${escapeHtml(String(message.id ?? ""))}">撤回</button>`
    : "";
  return `<article class="help-message ${isStudent ? "is-student" : "is-admin"}" data-message-id="${escapeHtml(String(message.id ?? ""))}" data-help-request-id="${escapeHtml(String(message.help_request_id ?? ""))}">
    <header><strong>${escapeHtml(sender)}</strong>${message.created_at ? `<time>${escapeHtml(fmtTime(message.created_at))}</time>` : ""}${recallControl}</header>
    <p${recalled ? ' class="is-recalled"' : ""}>${recalled ? `${isStudent ? "对方" : "你"}撤回了一条消息` : escapeHtml(message.body || "")}</p>${attachmentMarkup}${isStudent && message.read_by_assigned_teacher ? '<small class="help-message-receipt">已读</small>' : ""}${!isStudent && message.read_by_student ? '<small class="help-message-receipt">学生已读</small>' : ""}
  </article>`;
}

export function createHelpDesk(root = document, request = adminRequest) {
  const $ = (id) => root.getElementById(id);
  const state = {
    items: [],
    total: 0,
    page: 1,
    filter: "waiting",
    selectedId: null,
    detail: null,
    messages: [],
    nextCursor: null,
    hasMoreMessages: false,
    loadingOlderMessages: false,
    replyAttachments: [],
    queueBusy: false,
    detailBusy: false,
  };
  const replyKeys = createRetryKeyCache();

  function clearReplyAttachments() {
    state.replyAttachments.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    state.replyAttachments = [];
    $("replyAttachmentInput").value = "";
    renderReplyAttachments();
  }

  function renderReplyAttachments() {
    const host = $("replyAttachmentPreview");
    host.hidden = !state.replyAttachments.length;
    host.innerHTML = state.replyAttachments
      .map(
        (item, index) => `<figure class="help-reply-image-preview"><img src="${escapeHtml(item.previewUrl)}" alt="待发送图片：${escapeHtml(item.file.name)}" /><figcaption>${escapeHtml(item.file.name)}</figcaption><button class="btn-text" type="button" data-remove-reply-attachment="${index}" aria-label="移除图片 ${escapeHtml(item.file.name)}">移除</button></figure>`,
      )
      .join("");
  }

  function renderMessages({ stickToBottom = false } = {}) {
    const host = $("messageList");
    const messages = state.messages;
    const olderButton = state.hasMoreMessages
      ? `<div class="help-message-history"><button class="btn" type="button" data-load-older-messages${state.loadingOlderMessages ? " disabled" : ""}>${state.loadingOlderMessages ? "正在加载…" : "加载更早消息"}</button></div>`
      : "";
    host.innerHTML = messages.length
      ? `${olderButton}${messages.map(messageMarkup).join("")}`
      : '<div class="help-chat-empty"><strong>这条会话还没有可显示的消息</strong><p>可以刷新队列后再试。</p></div>';
    if (stickToBottom) host.scrollTop = host.scrollHeight;
  }

  function setStatus(message = "", kind = "") {
    $("deskStatus").textContent = message;
    $("deskStatus").className = `help-desk-status${kind ? ` is-${kind}` : ""}`;
  }

  function renderQueue() {
    const host = $("queueList");
    if (!state.items.length) {
      host.innerHTML =
        '<div class="help-queue-state"><strong>当前没有等待中的答疑</strong><p>刷新后，新问题会按服务端顺序出现在这里。</p></div>';
    } else {
      host.innerHTML = state.items
        .map((item) => queueItemMarkup(item, String(item.id) === String(state.selectedId)))
        .join("");
    }
    host.setAttribute("aria-busy", "false");
    $("queueSummary").textContent = `共 ${state.total} 条会话，排序与等待状态由服务端提供。`;
    const pages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
    $("queuePager").innerHTML =
      `<span>第 ${state.page} / ${pages} 页</span><span class="spacer"></span><button class="btn" type="button" data-page="prev"${state.page <= 1 ? " disabled" : ""}>上一页</button><button class="btn" type="button" data-page="next"${state.page >= pages ? " disabled" : ""}>下一页</button>`;
  }

  function renderProfile(detail) {
    const name = studentName(detail || {});
    $("profileName").textContent = name;
    $("profileClass").textContent = className(detail || {});
    $("profileAvatar").textContent = name.slice(0, 1) || "学";
    const profile = detail?.student_profile;
    if (!profile) {
      $("profileProgress").textContent = "暂无数据";
      $("profileLastActivity").textContent = "暂无学习记录";
      $("profilePractice").textContent = "0 题";
      $("profileHomework").textContent = "0 项";
      $("profileHelpCount").textContent = "0 次";
      $("profileHistory").innerHTML = "<span>暂无历史会话</span>";
      return;
    }
    const progress = profile.course_progress || {};
    $("profileProgress").textContent =
      `${Number(progress.percent || 0)}%（${Number(progress.completed_lessons || 0)}/${Number(progress.total_lessons || 0)} 课时）`;
    const activity = profile.learning_activity || {};
    $("profileLastActivity").textContent = activity.last_activity_at
      ? `${fmtTime(activity.last_activity_at)} · ${activity.active ? "活跃" : "未活跃"}`
      : "暂无学习记录";
    $("profilePractice").textContent = `${Number(profile.weekly_practice_completed || 0)} 题`;
    $("profileHomework").textContent = `${Number(profile.pending_homework_count || 0)} 项`;
    $("profileHelpCount").textContent = `${Number(profile.help_request_count || 0)} 次`;
    const history = Array.isArray(profile.context_history) ? profile.context_history : [];
    $("profileHistory").innerHTML = history.length
      ? history
          .map(
            (
              item,
            ) => `<button class="help-profile-history-item" type="button" data-profile-message-id="${escapeHtml(String(item.first_message_id ?? ""))}"${item.first_message_id == null ? " disabled" : ""}>
          <strong>${escapeHtml(item.context_label || "通用问题")}</strong>
          <span>${escapeHtml(fmtTime(item.last_message_at || ""))} · ${escapeHtml(historyStatusLabel(item.status))}</span>
        </button>`,
          )
          .join("")
      : "<span>暂无历史会话</span>";
  }

  function historyStatusLabel(status) {
    return { open: "待回复", answered: "已回复", closed: "已关闭" }[status] || "状态未知";
  }

  function renderProfileLoading(item) {
    const name = studentName(item || {});
    $("profileName").textContent = name;
    $("profileClass").textContent = className(item || {});
    $("profileAvatar").textContent = name.slice(0, 1) || "学";
    $("profileProgress").textContent = "正在读取";
    $("profileLastActivity").textContent = "正在读取";
    $("profilePractice").textContent = "正在读取";
    $("profileHomework").textContent = "正在读取";
    $("profileHelpCount").textContent = "正在读取";
    $("profileHistory").innerHTML = "<span>正在读取历史会话</span>";
  }

  function renderProfileError() {
    $("profileProgress").textContent = "暂时无法读取";
    $("profileLastActivity").textContent = "暂时无法读取";
    $("profilePractice").textContent = "暂时无法读取";
    $("profileHomework").textContent = "暂时无法读取";
    $("profileHelpCount").textContent = "暂时无法读取";
    $("profileHistory").innerHTML = "<span>暂时无法读取历史会话</span>";
  }

  function renderQueueLoading() {
    $("queueList").setAttribute("aria-busy", "true");
    $("queueList").innerHTML =
      '<div class="help-queue-skeleton" aria-label="正在加载答疑队列"><span></span><span></span><span></span></div>';
    $("queuePager").replaceChildren();
  }

  function renderQueueError(error) {
    $("queueList").setAttribute("aria-busy", "false");
    $("queueList").innerHTML =
      `<div class="help-queue-state is-error"><strong>队列加载失败</strong><p>${escapeHtml(error.message || "请稍后重试。")}</p><button class="btn" type="button" data-retry-queue>重新加载</button></div>`;
    $("queuePager").replaceChildren();
    $("queueSummary").textContent = "暂时无法读取队列。";
  }

  async function loadQueue({ keepSelection = true } = {}) {
    if (state.queueBusy) return;
    state.queueBusy = true;
    $("refreshQueueBtn").disabled = true;
    renderQueueLoading();
    try {
      const params = new URLSearchParams({
        page: String(state.page),
        page_size: String(PAGE_SIZE),
        sort: "-waiting_seconds,-last_message_at,-id",
      });
      if (state.filter && state.filter !== "all") params.set("filter", state.filter);
      const payload = await request(`/help-chat-lines?${params}`);
      state.items = Array.isArray(payload.items) ? payload.items : [];
      state.total = Number(payload.total || 0);
      if (
        !keepSelection ||
        !state.items.some((item) => String(item.id) === String(state.selectedId))
      )
        state.selectedId = null;
      renderQueue();
      if (!state.selectedId && state.items.length && matchMedia("(min-width: 801px)").matches)
        await selectLine(state.items[0].id);
    } catch (error) {
      renderQueueError(error);
    } finally {
      state.queueBusy = false;
      $("refreshQueueBtn").disabled = false;
    }
  }

  function renderChatLoading(item) {
    $("chatTitle").textContent = studentName(item || {});
    $("chatMeta").textContent = className(item || {});
    $("contextStrip").hidden = true;
    setReplyAvailability(false);
    $("assignmentForm").hidden = true;
    $("toggleAssignmentBtn").hidden = true;
    $("messageList").innerHTML =
      '<div class="help-chat-loading"><span></span><span></span><span></span></div>';
    $("emojiPicker").hidden = true;
    $("emojiPickerBtn").setAttribute("aria-expanded", "false");
    clearReplyAttachments();
    renderProfileLoading(item);
  }

  function renderChatEmpty() {
    $("chatTitle").textContent = "选择一条学生会话";
    $("chatMeta").textContent = "从左侧队列开始处理答疑。";
    $("contextStrip").hidden = true;
    setReplyAvailability(false);
    $("assignmentForm").hidden = true;
    $("toggleAssignmentBtn").hidden = true;
    $("messageList").innerHTML =
      '<div class="help-chat-empty"><strong>还没有打开会话</strong><p>队列会把学生原话和等待状态放在最前面。</p></div>';
    clearReplyAttachments();
  }

  function renderDetail(detail) {
    const item = state.items.find((row) => String(row.id) === String(state.selectedId)) || detail;
    $("chatTitle").textContent = studentName(detail) || studentName(item);
    const detailWaitingLabel = firstValue(
      detail.waiting_status?.label,
      detail.waiting_status_label,
      detail.status_label,
    );
    $("chatMeta").textContent = [
      className(detail) || className(item),
      firstValue(detailWaitingLabel, waitingLabel(item)),
    ]
      .filter(Boolean)
      .join(" · ");
    const context = contextText(detail);
    $("contextLabel").textContent = context;
    $("contextStrip").hidden = !context;
    state.messages = messageRows(detail);
    state.nextCursor = detail.next_cursor ?? null;
    state.hasMoreMessages = detail.has_more === true && state.nextCursor != null;
    if (metadataOnly(detail)) {
      $("messageList").innerHTML =
        '<div class="help-chat-empty"><strong>当前仅可查看会话元数据</strong><p>正文与回复入口由服务端权限控制。</p></div>';
      setReplyAvailability(false);
      $("assignmentForm").hidden = true;
      $("toggleAssignmentBtn").hidden = true;
      return;
    }
    renderMessages({ stickToBottom: true });
    const requestRow = activeRequest(detail);
    const canReply = detail.can_reply === true && Boolean(requestRow?.id);
    setReplyAvailability(canReply);
    renderAssignmentCandidates(detail, requestRow, detail.can_reassign === true);
  }

  function setReplyAvailability(canReply) {
    $("replyForm").hidden = !canReply;
    $("replyBody").disabled = !canReply;
    $("sendReplyBtn").disabled = !canReply;
  }

  function renderAssignmentCandidates(detail, requestRow, canReassign) {
    const currentId = Number(requestRow?.assigned_admin_user_id);
    const candidates = (
      Array.isArray(detail.assignment_candidates) ? detail.assignment_candidates : []
    ).filter((item) => Number(item.id) !== currentId);
    $("assignmentTarget").innerHTML = candidates.length
      ? `<option value="">选择同班带课人员</option>${candidates
          .map(
            (item) =>
              `<option value="${escapeHtml(item.id)}">${escapeHtml(item.display_name || `后台账号 ${item.id}`)}</option>`,
          )
          .join("")}`
      : '<option value="">暂无其他可转派人员</option>';
    $("assignmentTarget").disabled = !candidates.length;
    $("assignBtn").disabled = !candidates.length;
    $("toggleAssignmentBtn").hidden = !canReassign || !requestRow?.id;
    if (!canReassign || !requestRow?.id) $("assignmentForm").hidden = true;
    $("assignmentHint").textContent = "";
  }

  function renderDetailError(error) {
    $("messageList").innerHTML =
      `<div class="help-chat-empty is-error"><strong>会话加载失败</strong><p>${escapeHtml(error.message || "请稍后重试。")}</p><button class="btn" type="button" data-retry-detail>重新加载</button></div>`;
    setReplyAvailability(false);
    $("assignmentForm").hidden = true;
    $("toggleAssignmentBtn").hidden = true;
    renderProfileError();
  }

  async function selectLine(id) {
    if (state.detailBusy || id == null) return;
    state.selectedId = id;
    state.detailBusy = true;
    renderQueue();
    $("deskWorkspace").classList.add("is-chat-open");
    renderChatLoading(state.items.find((row) => String(row.id) === String(id)));
    try {
      state.detail = await request(`/help-chat-lines/${encodeURIComponent(id)}`);
      if (String(state.selectedId) === String(id)) {
        renderDetail(state.detail);
        renderProfile(state.detail);
      }
    } catch (error) {
      renderDetailError(error);
    } finally {
      state.detailBusy = false;
    }
  }

  let profileHighlightTimer = null;
  function focusHistoryMessage(messageId) {
    if (!/^\d+$/.test(String(messageId))) return;
    const target = $("messageList").querySelector(`[data-message-id="${messageId}"]`);
    if (!target) return;
    $("messageList")
      .querySelectorAll(".is-history-target")
      .forEach((item) => item.classList.remove("is-history-target"));
    target.classList.add("is-history-target");
    target.scrollIntoView?.({ behavior: "smooth", block: "center" });
    clearTimeout(profileHighlightTimer);
    profileHighlightTimer = setTimeout(() => target.classList.remove("is-history-target"), 1800);
  }

  async function loadOlderMessages() {
    if (state.loadingOlderMessages || !state.hasMoreMessages || state.selectedId == null) return;
    const host = $("messageList");
    const previousHeight = host.scrollHeight;
    const previousTop = host.scrollTop;
    state.loadingOlderMessages = true;
    renderMessages();
    try {
      const params = new URLSearchParams({
        before_id: String(state.nextCursor),
        limit: String(CHAT_PAGE_SIZE),
      });
      const page = await request(`/help-chat-lines/${encodeURIComponent(state.selectedId)}?${params}`);
      if (String(state.selectedId) !== String(page.id ?? state.selectedId)) return;
      const earlier = messageRows(page);
      const known = new Set(state.messages.map((item) => String(item.id)));
      state.messages = [...earlier.filter((item) => !known.has(String(item.id))), ...state.messages];
      state.nextCursor = page.next_cursor ?? null;
      state.hasMoreMessages = page.has_more === true && state.nextCursor != null;
      renderMessages();
      host.scrollTop = previousTop + (host.scrollHeight - previousHeight);
    } catch (error) {
      setStatus(error.message || "更早消息加载失败，请重试。", "error");
    } finally {
      state.loadingOlderMessages = false;
      renderMessages();
      host.scrollTop = previousTop + (host.scrollHeight - previousHeight);
    }
  }

  async function uploadReplyAttachments(requestRow) {
    const uploadedIds = [];
    for (const attachment of state.replyAttachments) {
      if (attachment.id != null) {
        uploadedIds.push(attachment.id);
        continue;
      }
      const formData = new FormData();
      formData.append("file", attachment.file, attachment.file.name);
      const uploaded = await adminUpload(
        `/help-requests/${encodeURIComponent(requestRow.id)}/attachments`,
        formData,
        { headers: { "Idempotency-Key": attachment.key } },
      );
      attachment.id = uploaded.id;
      uploadedIds.push(uploaded.id);
    }
    return uploadedIds;
  }

  async function recallMessage(messageId) {
    const message = state.messages.find((item) => String(item.id) === String(messageId));
    if (!message || message.can_recall !== true || message.recalled === true) return;
    const control = $("messageList").querySelector(`[data-recall-message-id="${messageId}"]`);
    if (control) control.disabled = true;
    try {
      await request(`/help-messages/${encodeURIComponent(messageId)}/recall`, { method: "POST", body: "{}" });
      await selectLine(state.selectedId);
      await loadQueue();
    } catch (error) {
      setStatus(error.message || "撤回失败，请重试。", "error");
      if (control) control.disabled = false;
    }
  }

  async function sendReply(event) {
    event.preventDefault();
    const requestRow = activeRequest(state.detail || {});
    const body = $("replyBody").value.trim();
    if (state.detail?.can_reply !== true || !requestRow?.id || (!body && !state.replyAttachments.length)) return;
    const requestKey = replyKeys.keyFor(requestRow.id, body);
    $("replyBody").disabled = true;
    $("sendReplyBtn").disabled = true;
    $("sendReplyBtn").textContent = "发送中…";
    $("replyHint").textContent = "正在发送回复…";
    try {
      const attachmentIds = await uploadReplyAttachments(requestRow);
      await request(`/help-requests/${encodeURIComponent(requestRow.id)}/messages`, {
        method: "POST",
        headers: { "Idempotency-Key": requestKey },
        body: JSON.stringify({ body, attachment_ids: attachmentIds }),
      });
      replyKeys.markSucceeded();
      $("replyBody").value = "";
      clearReplyAttachments();
      $("replyHint").textContent = "回复已发送。";
      await selectLine(state.selectedId);
      await loadQueue();
    } catch (error) {
      replyKeys.markFailed(requestRow.id, body, requestKey);
      $("replyHint").textContent = error.message || "回复发送失败，请重试。";
      setStatus($("replyHint").textContent, "error");
    } finally {
      const canReply =
        state.detail?.can_reply === true && Boolean(activeRequest(state.detail || {})?.id);
      setReplyAvailability(canReply);
      $("sendReplyBtn").textContent = "发送回复";
    }
  }

  function closeAssignment() {
    $("assignmentForm").hidden = true;
    $("toggleAssignmentBtn").setAttribute("aria-expanded", "false");
  }

  async function reassign(event) {
    event.preventDefault();
    const requestRow = activeRequest(state.detail || {});
    const targetId = Number($("assignmentTarget").value);
    if (
      state.detail?.can_reassign !== true ||
      !requestRow?.id ||
      !Number.isInteger(targetId) ||
      targetId <= 0
    )
      return;
    $("assignmentTarget").disabled = true;
    $("assignBtn").disabled = true;
    $("assignmentHint").textContent = "正在转派…";
    try {
      await request(`/help-requests/${encodeURIComponent(requestRow.id)}/assignment`, {
        method: "PATCH",
        headers: ifMatch(requestRow.assignment_revision),
        body: JSON.stringify({ target_admin_user_id: targetId }),
      });
      $("assignmentHint").textContent = "已完成转派。";
      closeAssignment();
      state.selectedId = null;
      state.detail = null;
      renderChatEmpty();
      $("deskWorkspace").classList.remove("is-chat-open");
      await loadQueue({ keepSelection: false });
    } catch (error) {
      if (error.status === 409) {
        $("assignmentHint").textContent = error.message || "承办版本已变化，正在刷新会话…";
        setStatus($("assignmentHint").textContent, "error");
        await selectLine(state.selectedId);
      } else {
        $("assignmentHint").textContent = error.message || "转派失败，请重试。";
      }
    } finally {
      $("assignmentTarget").disabled = false;
      $("assignBtn").disabled = false;
    }
  }

  let realtimeSocket = null;
  let realtimeRetryTimer = null;
  let realtimeRefreshTimer = null;
  const pendingRealtimeLineIds = new Set();
  let realtimeStopped = false;
  let typingStopTimer = null;
  let studentTypingTimer = null;

  function publishTyping(isTyping) {
    if (state.selectedId == null || realtimeSocket?.readyState !== WebSocket.OPEN) return;
    realtimeSocket.send(
      JSON.stringify({
        type: "typing",
        chat_line_id: Number(state.selectedId),
        is_typing: isTyping,
      }),
    );
  }

  function showStudentTyping(isTyping, lineId) {
    if (String(state.selectedId) !== String(lineId)) return;
    $("replyHint").textContent = isTyping ? "学生正在输入…" : "回复将发送到当前会话。";
    clearTimeout(studentTypingTimer);
    if (isTyping) studentTypingTimer = setTimeout(() => showStudentTyping(false, lineId), 2500);
  }

  async function refreshFromRealtimeEvent(lineId) {
    if (state.queueBusy || state.detailBusy) {
      realtimeRefreshTimer = setTimeout(() => {
        realtimeRefreshTimer = null;
        refreshFromRealtimeEvent(lineId);
      }, 150);
      return;
    }
    await loadQueue({ keepSelection: true });
    if (String(state.selectedId) === String(lineId)) {
      await selectLine(state.selectedId);
    }
  }

  function scheduleRealtimeRefresh(event) {
    if (event.event === "student_typing") return showStudentTyping(true, event.chat_line_id);
    if (event.event === "student_stopped_typing")
      return showStudentTyping(false, event.chat_line_id);
    if (event.event?.includes("typing")) return;
    pendingRealtimeLineIds.add(String(event.chat_line_id));
    if (realtimeRefreshTimer != null) return;
    realtimeRefreshTimer = setTimeout(async () => {
      realtimeRefreshTimer = null;
      const changed = [...pendingRealtimeLineIds];
      pendingRealtimeLineIds.clear();
      await refreshFromRealtimeEvent(changed.at(-1));
    }, 80);
  }

  function startRealtime() {
    if (!globalThis.WebSocket) return;
    let retryDelay = 1000;
    const scheduleRetry = () => {
      if (realtimeStopped) return;
      realtimeRetryTimer = setTimeout(connect, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 30_000);
    };
    const connect = async () => {
      if (realtimeStopped) return;
      let ticket;
      try {
        ({ ticket } = await adminRequest("/help-chat-lines/events/ticket", { method: "POST" }));
      } catch {
        scheduleRetry();
        return;
      }
      if (realtimeStopped || typeof ticket !== "string") return;
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      realtimeSocket = new WebSocket(
        `${protocol}//${location.host}/api/admin/help-chat-lines/events`,
        ["help-v1", `help-ticket.${ticket}`],
      );
      realtimeSocket.addEventListener("open", () => {
        retryDelay = 1000;
      });
      realtimeSocket.addEventListener("message", (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload?.type === "help_chat_line_changed" && payload.chat_line_id != null) {
            scheduleRealtimeRefresh(payload);
          }
        } catch {
          // 不可信事件不能破坏已有的队列读取与回复流程。
        }
      });
      realtimeSocket.addEventListener("close", () => {
        scheduleRetry();
      });
    };
    connect();
    addEventListener(
      "beforeunload",
      () => {
        realtimeStopped = true;
        clearTimeout(realtimeRetryTimer);
        clearTimeout(realtimeRefreshTimer);
        realtimeSocket?.close();
      },
      { once: true },
    );
  }

  $("queueList").addEventListener("click", (event) => {
    const card = event.target.closest("[data-line-id]");
    if (card) selectLine(card.dataset.lineId);
    if (event.target.closest("[data-retry-queue]")) loadQueue();
  });
  $("queuePager").addEventListener("click", (event) => {
    const direction = event.target.dataset.page;
    if (!direction) return;
    state.page += direction === "next" ? 1 : -1;
    loadQueue({ keepSelection: false });
  });
  $("messageList").addEventListener("click", (event) => {
    if (event.target.closest("[data-retry-detail]")) selectLine(state.selectedId);
    if (event.target.closest("[data-load-older-messages]")) loadOlderMessages();
    const recall = event.target.closest("[data-recall-message-id]");
    if (recall) recallMessage(recall.dataset.recallMessageId);
  });
  $("profileHistory").addEventListener("click", (event) => {
    const item = event.target.closest("[data-profile-message-id]");
    if (item && !item.disabled) focusHistoryMessage(item.dataset.profileMessageId);
  });
  $("refreshQueueBtn").addEventListener("click", () => loadQueue());
  root.querySelectorAll(".help-queue-tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      root
        .querySelectorAll(".help-queue-tab")
        .forEach((item) => item.classList.toggle("is-active", item === tab));
      state.page = 1;
      state.filter = tab.dataset.filter;
      loadQueue({ keepSelection: false });
    }),
  );
  $("backToQueueBtn").addEventListener("click", () =>
    $("deskWorkspace").classList.remove("is-chat-open"),
  );
  $("toggleAssignmentBtn").addEventListener("click", () => {
    const opening = $("assignmentForm").hidden;
    $("assignmentForm").hidden = !opening;
    $("toggleAssignmentBtn").setAttribute("aria-expanded", String(opening));
    if (opening) $("assignmentTarget").focus();
  });
  $("cancelAssignmentBtn").addEventListener("click", closeAssignment);
  $("assignmentForm").addEventListener("submit", reassign);
  $("replyForm").addEventListener("submit", sendReply);
  $("emojiPicker").innerHTML = EMOJIS.map(
    (emoji) => `<button type="button" class="help-emoji-option" data-emoji="${emoji}" aria-label="插入表情 ${emoji}">${emoji}</button>`,
  ).join("");
  $("emojiPickerBtn").addEventListener("click", () => {
    const opening = $("emojiPicker").hidden;
    $("emojiPicker").hidden = !opening;
    $("emojiPickerBtn").setAttribute("aria-expanded", String(opening));
  });
  $("emojiPicker").addEventListener("click", (event) => {
    const option = event.target.closest("[data-emoji]");
    if (!option || $("replyBody").disabled) return;
    const input = $("replyBody");
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? start;
    input.setRangeText(option.dataset.emoji, start, end, "end");
    input.focus();
  });
  $("attachmentPickerBtn").addEventListener("click", () => $("replyAttachmentInput").click());
  $("replyAttachmentInput").addEventListener("change", () => {
    const files = [...$("replyAttachmentInput").files].filter((file) => file.type.startsWith("image/"));
    state.replyAttachments.push(
      ...files.map((file) => ({
        file,
        key: idempotencyKey(),
        previewUrl: URL.createObjectURL(file),
        id: null,
      })),
    );
    $("replyAttachmentInput").value = "";
    renderReplyAttachments();
  });
  $("replyAttachmentPreview").addEventListener("click", (event) => {
    const control = event.target.closest("[data-remove-reply-attachment]");
    if (!control) return;
    const [attachment] = state.replyAttachments.splice(Number(control.dataset.removeReplyAttachment), 1);
    if (attachment) URL.revokeObjectURL(attachment.previewUrl);
    renderReplyAttachments();
  });
  $("replyBody").addEventListener("input", () => {
    publishTyping(true);
    clearTimeout(typingStopTimer);
    typingStopTimer = setTimeout(() => publishTyping(false), 900);
  });

  return { loadQueue, selectLine, sendReply, reassign, recallMessage, loadOlderMessages, startRealtime, state };
}

const app = document.getElementById("helpDeskApp");
if (app) {
  initLayout();
  const desk = createHelpDesk(document);
  desk.startRealtime();
  desk.loadQueue().then(() => {
    const line = new URLSearchParams(window.location.search).get("line");
    if (line && desk.state.items.some((item) => String(item.id) === String(line)))
      desk.selectLine(line);
  });
}
