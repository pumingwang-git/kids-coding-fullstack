// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import {
  createHelpDesk,
  messageMarkup,
  messageRows,
  queueItemMarkup,
  formatWaitingSeconds,
} from "../public/admin/help-desk.js";

const adminFile = (name) => readFileSync(resolve(process.cwd(), "public", "admin", name), "utf8");

describe("教师文字答疑工作台", () => {
  it("入口由共享菜单呈现，页面继续交给服务端 allowed_pages 过滤", () => {
    const layout = adminFile("admin-layout.js");
    expect(layout).toContain('page: "help-desk.html"');
    expect(layout).toContain("filterPageLinks(me.allowed_pages)");
    expect(layout).not.toMatch(/role\s*===?\s*["'](?:teacher|assistant)/);
  });

  it("只实现文字答疑，不伪装实时主操作", () => {
    const html = adminFile("help-desk.html");
    const script = adminFile("help-desk.js");
    expect(html).not.toContain("连线（后续开放）");
    expect(html).not.toContain("help-realtime-later");
    expect(`${html}\n${script}`).not.toContain("Go Live");
    expect(script).not.toMatch(/WebRTC|RTCPeerConnection|realtime-sessions|realtime-invites/);
  });

  it("队列使用服务端等待秒数、状态文案与状态 tone，并固定服务端排序", () => {
    const script = adminFile("help-desk.js");
    expect(script).toContain('sort: "-waiting_seconds,-last_message_at,-id"');
    const html = queueItemMarkup({
      id: 7,
      student: { username: "<小明>" },
      class: { name: "一班" },
      last_student_message: { body: "数组为什么越界？" },
      waiting_seconds: 641,
      waiting_status: { label: "等待较久", tone: "danger" },
      context_label: "第 4 课 · 练习 2",
      unread_count: 2,
      has_attachments: true,
    });
    expect(html).toContain("已等待 10 分 41 秒");
    expect(html).toContain('data-tone="danger"');
    expect(html).toContain("等待较久");
    expect(html).toContain("&lt;小明&gt;");
  });

  it("队列字段缺失时显式失败，不用前端猜测别名", () => {
    expect(() => queueItemMarkup({ id: 1, waiting_seconds: 1 })).toThrow("缺少服务端字段");
    expect(formatWaitingSeconds(870)).toBe("14 分 30 秒");
  });

  it("消息正文按角色布局且所有服务端文本转义", () => {
    const html = messageMarkup({
      sender_type: "student",
      sender_label: "学生<script>",
      body: "<img onerror=alert(1)>",
    });
    expect(html).toContain("is-student");
    expect(html).toContain("学生&lt;script&gt;");
    expect(html).toContain("&lt;img onerror=alert(1)&gt;");
    expect(html).not.toContain("<img onerror");
  });

  it("聊天线详情合并多个上下文工单的连续消息并稳定排序", () => {
    const rows = messageRows({
      requests: [
        {
          id: 12,
          status: "open",
          messages: [
            { id: 4, body: "新上下文追问", created_at: "2026-08-30T10:02:00Z" },
            { id: 3, body: "同秒第二条", created_at: "2026-08-30T10:01:00Z" },
          ],
        },
        {
          id: 11,
          status: "closed",
          messages: [
            { id: 2, body: "同秒第一条", created_at: "2026-08-30T10:01:00Z" },
            { id: 1, body: "最早的问题", created_at: "2026-08-30T10:00:00Z" },
          ],
        },
      ],
    });

    expect(rows.map((item) => item.body)).toEqual([
      "最早的问题",
      "同秒第一条",
      "同秒第二条",
      "新上下文追问",
    ]);
  });

  it("顶层 messages 存在时不重复拼接 requests 消息", () => {
    const rows = messageRows({
      messages: [{ id: 9, body: "顶层消息", created_at: "2026-08-30T10:00:00Z" }],
      requests: [
        {
          messages: [{ id: 1, body: "分组消息", created_at: "2026-08-30T09:00:00Z" }],
        },
      ],
    });
    expect(rows.map((item) => item.body)).toEqual(["顶层消息"]);
  });

  it("使用聊天线详情的确定学生画像填充右侧档案，并可定位历史上下文", async () => {
    document.documentElement.innerHTML = adminFile("help-desk.html");
    const detail = {
      id: 7,
      student_name: "小明",
      class_name: "测试班",
      can_reply: true,
      requests: [{ id: 51, status: "answered" }],
      messages: [{ id: 41, help_request_id: 51, sender_type: "student", body: "第一条问题", created_at: "2026-08-31T08:00:00Z" }],
      student_profile: {
        course_progress: { completed_lessons: 3, total_lessons: 8, percent: 38 },
        learning_activity: { last_activity_at: "2026-08-31T08:00:00Z", active: true, inactive_days: 0 },
        weekly_practice_completed: 4,
        pending_homework_count: 2,
        help_request_count: 6,
        context_history: [{
          help_request_id: 51,
          context_label: "第 3 课 · 练习 2",
          status: "answered",
          last_message_at: "2026-08-31T08:00:00Z",
          first_message_id: 41,
        }],
      },
    };
    const request = vi.fn(async (path) => {
      if (path === "/help-chat-lines/7") return detail;
      return { items: [], total: 0 };
    });
    const desk = createHelpDesk(document, request);
    await desk.selectLine(7);

    expect(document.getElementById("profileProgress").textContent).toBe("38%（3/8 课时）");
    expect(document.getElementById("profilePractice").textContent).toBe("4 题");
    expect(document.getElementById("profileHomework").textContent).toBe("2 项");
    expect(document.getElementById("profileHelpCount").textContent).toBe("6 次");
    expect(document.getElementById("profileHistory").textContent).toContain("第 3 课 · 练习 2");
    expect(document.querySelector("[data-message-id='41']").dataset.helpRequestId).toBe("51");

    document.querySelector("[data-profile-message-id='41']").click();
    expect(document.querySelector("[data-message-id='41']").classList).toContain("is-history-target");
  });

  it("回复失败后重试同一正文复用 Idempotency-Key，成功后清除", async () => {
    document.documentElement.innerHTML = adminFile("help-desk.html");
    const requestKeys = [];
    const request = vi.fn(async (path, options) => {
      if (path.endsWith("/messages")) {
        requestKeys.push(options.headers["Idempotency-Key"]);
        if (requestKeys.length === 1) throw new Error("模拟网络失败");
        return {};
      }
      if (path === "/help-chat-lines/7") {
        return { id: 7, can_reply: true, requests: [{ id: 51, status: "open" }] };
      }
      if (path.startsWith("/help-chat-lines?")) return { items: [], total: 0 };
      return { items: [] };
    });
    const desk = createHelpDesk(document, request);
    desk.state.selectedId = 7;
    desk.state.detail = { can_reply: true, requests: [{ id: 51, status: "open" }] };
    document.getElementById("replyBody").value = "请打印 i 的值";

    await desk.sendReply({ preventDefault() {} });
    await desk.sendReply({ preventDefault() {} });
    document.getElementById("replyBody").value = "请打印 i 的值";
    await desk.sendReply({ preventDefault() {} });

    expect(requestKeys).toHaveLength(3);
    expect(requestKeys[1]).toBe(requestKeys[0]);
    expect(requestKeys[2]).not.toBe(requestKeys[1]);
  });

  it("兼容详情顶层 requests，直接使用详情候选并用 If-Match 转派", () => {
    const script = adminFile("help-desk.js");
    expect(script).toContain("Array.isArray(detail.requests)");
    expect(script).toContain("detail.assignment_candidates");
    expect(script).not.toContain("/teachers");
    expect(script).not.toContain("ended_at");
    expect(script).toContain('method: "PATCH"');
    expect(script).toContain("headers: ifMatch(requestRow.assignment_revision)");
    expect(script).toContain("error.status === 409");
    expect(script).not.toMatch(/role_in_class\s*===/);
  });

  it("详情权限字段缺失时操作 fail-closed，严格为 true 时才显示并启用", async () => {
    document.documentElement.innerHTML = adminFile("help-desk.html");
    let detail = {
      id: 7,
      requests: [{ id: 51, status: "open", assigned_admin_user_id: 8 }],
      assignment_candidates: [{ id: 99, display_name: "周老师" }],
    };
    const request = vi.fn(async (path) => {
      if (path === "/help-chat-lines/7") return detail;
      return { items: [] };
    });
    const desk = createHelpDesk(document, request);

    await desk.selectLine(7);

    expect(document.getElementById("replyForm").hidden).toBe(true);
    expect(document.getElementById("replyBody").disabled).toBe(true);
    expect(document.getElementById("sendReplyBtn").disabled).toBe(true);
    expect(document.getElementById("toggleAssignmentBtn").hidden).toBe(true);
    expect(document.getElementById("assignmentForm").hidden).toBe(true);
    document.getElementById("replyBody").value = "不应发送";
    document.getElementById("assignmentTarget").innerHTML = '<option value="99">周老师</option>';
    document.getElementById("assignmentTarget").value = "99";
    request.mockClear();

    await desk.sendReply({ preventDefault() {} });
    await desk.reassign({ preventDefault() {} });

    expect(request).not.toHaveBeenCalled();

    detail = { ...detail, can_reply: true, can_reassign: true };
    await desk.selectLine(7);

    expect(document.getElementById("replyForm").hidden).toBe(false);
    expect(document.getElementById("replyBody").disabled).toBe(false);
    expect(document.getElementById("sendReplyBtn").disabled).toBe(false);
    expect(document.getElementById("toggleAssignmentBtn").hidden).toBe(false);
  });

  it("聊天标题采用详情最新等待状态，不回退到队列旧状态", async () => {
    document.documentElement.innerHTML = adminFile("help-desk.html");
    const request = vi.fn(async (path) => {
      if (path === "/help-chat-lines/7") {
        return {
          id: 7,
          waiting_status: { label: "暂无待回复", tone: "neutral" },
          requests: [{ id: 51, status: "closed" }],
        };
      }
      return { items: [] };
    });
    const desk = createHelpDesk(document, request);
    desk.state.items = [
      {
        id: 7,
        waiting_status: { label: "等待超过 10 分钟", tone: "danger" },
        context_label: "通用问题",
        unread_count: 1,
        has_attachments: false,
      },
    ];

    await desk.selectLine(7);

    expect(document.getElementById("chatMeta").textContent).toContain("暂无待回复");
    expect(document.getElementById("chatMeta").textContent).not.toContain("等待超过 10 分钟");
  });

  it("转派携带详情 revision，409 显示服务端冲突并刷新详情", async () => {
    document.documentElement.innerHTML = adminFile("help-desk.html");
    document.getElementById("assignmentTarget").innerHTML = '<option value="99">周老师</option>';
    document.getElementById("assignmentTarget").value = "99";
    const calls = [];
    const request = vi.fn(async (path, options) => {
      calls.push({ path, options });
      if (path.endsWith("/assignment")) {
        const error = new Error("承办版本已变化，请刷新后重试。");
        error.status = 409;
        throw error;
      }
      if (path === "/help-chat-lines/7") {
        return {
          id: 7,
          requests: [
            {
              id: 51,
              status: "open",
              assigned_admin_user_id: 8,
              assignment_revision: 5,
            },
          ],
          assignment_candidates: [
            { id: 8, display_name: "林老师" },
            { id: 99, display_name: "周老师" },
          ],
        };
      }
      return { items: [] };
    });
    const desk = createHelpDesk(document, request);
    desk.state.selectedId = 7;
    desk.state.detail = {
      can_reassign: true,
      requests: [{ id: 51, status: "open", assigned_admin_user_id: 8, assignment_revision: 4 }],
      assignment_candidates: [
        { id: 8, display_name: "林老师" },
        { id: 99, display_name: "周老师" },
      ],
    };

    await desk.reassign({ preventDefault() {} });

    const patchCall = calls.find((call) => call.path.endsWith("/assignment"));
    expect(patchCall.options.headers).toEqual({ "If-Match": "4" });
    expect(JSON.parse(patchCall.options.body)).toEqual({ target_admin_user_id: 99 });
    expect(document.getElementById("deskStatus").textContent).toBe(
      "承办版本已变化，请刷新后重试。",
    );
    expect(calls.some((call) => call.path === "/help-chat-lines/7")).toBe(true);
    expect(
      [...document.querySelectorAll("#assignmentTarget option")].map((item) => item.textContent),
    ).toEqual(["选择同班带课人员", "周老师"]);
  });

  it("转派成功后立即清空旧承办人的会话与操作区", async () => {
    document.documentElement.innerHTML = adminFile("help-desk.html");
    document.getElementById("assignmentTarget").innerHTML = '<option value="99">周老师</option>';
    document.getElementById("assignmentTarget").value = "99";
    document.getElementById("assignmentForm").hidden = false;
    document.getElementById("deskWorkspace").classList.add("is-chat-open");
    const request = vi.fn(async (path) => {
      if (path.endsWith("/assignment")) return {};
      if (path.startsWith("/help-chat-lines?")) return { items: [], total: 0 };
      return { items: [] };
    });
    const desk = createHelpDesk(document, request);
    desk.state.selectedId = 7;
    desk.state.detail = {
      can_reply: true,
      can_reassign: true,
      requests: [{ id: 51, status: "open", assignment_revision: 4 }],
    };

    await desk.reassign({ preventDefault() {} });

    expect(document.getElementById("chatTitle").textContent).toBe("选择一条学生会话");
    expect(document.getElementById("replyForm").hidden).toBe(true);
    expect(document.getElementById("toggleAssignmentBtn").hidden).toBe(true);
    expect(document.getElementById("assignmentForm").hidden).toBe(true);
    expect(document.getElementById("deskWorkspace").classList.contains("is-chat-open")).toBe(false);
  });

  it("页面无内联样式，移动端采用结构切换避免双栏横向溢出", () => {
    const html = adminFile("help-desk.html");
    const css = adminFile("admin.css");
    expect(html).not.toContain('style="');
    expect(css).toContain(".help-desk-workspace.is-chat-open .help-chat-panel");
    expect(css).toContain("overflow-x: hidden");
  });
});
